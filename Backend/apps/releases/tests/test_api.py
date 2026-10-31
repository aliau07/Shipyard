import csv
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.core.testing import TemporaryMediaMixin, image_upload
from apps.projects.tests.factories import Team, depend, make_component, make_project
from apps.releases import workflow
from apps.releases.models import Comment, Release, Screenshot


class ReleaseApiTests(APITestCase):
    def setUp(self):
        self.team = Team()
        self.client.force_authenticate(self.team.manager)

    def detail(self, release):
        return self.client.get(f'/api/releases/{release.pk}/').json()

    def test_create_a_release_with_changes(self):
        response = self.client.post('/api/releases/', {
            'project': self.team.project.pk, 'title': 'Spring', 'version': '2026.3.0', 'target_date': '2026-11-20',
            'changes': [{'component': self.team.api.pk, 'summary': 'Faster search', 'change_type': 'feature'},
                        {'component': self.team.web.pk, 'summary': 'Search page'}],
        }, format='json')

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual((data['status'], data['viewer_role'], data['change_count']), ('draft', 'release_manager', 2))
        self.assertEqual([change['component_name'] for change in data['changes']], ['api', 'web'])
        self.assertEqual([action['name'] for action in data['allowed_actions']], ['submit', 'cancel'])
        self.assertEqual(data['plan']['waves'], [['api'], ['web']])
        self.assertEqual(data['reference'], f'REL-{data["id"]:04d}')

    def test_create_validation(self):
        foreign = make_component(make_project(self.team.manager), 'foreign')
        hidden = make_component(make_project(self.team.outsider), 'hidden')
        base = {'project': self.team.project.pk, 'title': 'T', 'version': '1.0'}

        self.assertIn('different project', self.client.post('/api/releases/', {
            **base, 'changes': [{'component': foreign.pk, 'summary': 'x'}]}, format='json').json()['detail'])
        self.assertEqual(self.client.post('/api/releases/', {
            **base, 'changes': [{'component': hidden.pk, 'summary': 'x'}]}, format='json').status_code, 400)
        self.client.post('/api/releases/', base, format='json')
        self.assertIn('already has a release', self.client.post('/api/releases/', base, format='json').json()['detail'])
        self.client.force_authenticate(self.team.outsider)
        self.assertIn('project', self.client.post('/api/releases/', base, format='json').json())

    def test_list_is_scoped_and_filterable(self):
        draft = self.team.release(self.team.api)
        self.team.advance(self.team.release(self.team.web), 'in_review')
        other = Team()
        other.release(other.api)

        rows = self.client.get('/api/releases/').json()
        self.assertEqual(rows['count'], 2)
        self.assertEqual([row['id'] for row in self.client.get('/api/releases/?status=draft').json()['results']], [draft.pk])
        self.assertEqual(self.client.get(f'/api/releases/?project={other.project.pk}').json()['count'], 0)

    def test_non_members_get_404s_everywhere(self):
        release = self.team.release(self.team.api)
        self.client.force_authenticate(self.team.outsider)
        base = f'/api/releases/{release.pk}'
        self.assertEqual(self.client.get(f'{base}/').status_code, 404)
        self.assertEqual(self.client.get(f'{base}/export/').status_code, 404)
        self.assertEqual(self.client.post(f'{base}/transition/', {'action': 'submit'}).status_code, 404)
        self.assertEqual(self.client.post(f'{base}/comments/', {'body': 'hi'}).status_code, 404)
        self.assertEqual(self.client.patch(f'{base}/', {'title': 'x'}).status_code, 404)

    def test_transitions_return_the_updated_release(self):
        release = self.team.release(self.team.api)
        response = self.client.post(f'/api/releases/{release.pk}/transition/', {'action': 'submit', 'note': 'Ready'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'in_review')
        self.assertEqual(response.json()['approval']['waiting_for'],
                         [{'component': 'api', 'owner_name': self.team.li.display_name}])
        self.assertEqual(response.json()['timeline'][-1]['message'], 'Ready')

    def test_transition_errors_carry_status_codes(self):
        release = self.team.advance(self.team.release(self.team.api), 'in_review')
        url = f'/api/releases/{release.pk}/transition/'

        self.assertEqual(self.client.post(url, {'action': 'explode'}).status_code, 400)
        conflict = self.client.post(url, {'action': 'approve'})
        self.assertEqual(conflict.status_code, 409)
        self.assertIn('Waiting for sign-off on api', conflict.json()['detail'])
        self.client.force_authenticate(self.team.ada)
        self.assertEqual(self.client.post(url, {'action': 'approve'}).status_code, 403)

    def test_cycle_is_shown_in_the_detail(self):
        depend(self.team.models, self.team.api)
        release = self.team.advance(self.team.release(self.team.api, self.team.models), 'in_review')
        self.team.sign_all(release)

        data = self.detail(release)

        self.assertEqual(data['approval']['cycle'], ['api', 'models', 'api'])
        self.assertEqual(len(data['approval']['blockers']), 1)
        self.assertIsNone(data['plan']['waves'])
        self.assertEqual(data['plan']['layers'], [['api', 'models']])
        self.assertTrue(all(node['in_cycle'] for node in data['plan']['nodes']))

    def test_add_and_remove_changes(self):
        release = self.team.release(self.team.api)
        added = self.client.post(f'/api/releases/{release.pk}/changes/', {'component': self.team.ui.pk,
                                                                          'summary': 'Buttons', 'change_type': 'fix'})
        self.assertEqual((added.status_code, added.json()['change_type_display']), (201, 'Fix'))

        removed = self.client.delete(f'/api/releases/{release.pk}/changes/{added.json()["id"]}/')
        self.assertEqual(removed.status_code, 204)
        self.assertEqual([c['component_name'] for c in self.detail(release)['changes']], ['api'])

    def test_patch_details(self):
        release = self.team.release(self.team.api)
        response = self.client.patch(f'/api/releases/{release.pk}/', {'title': 'Renamed', 'target_date': '2026-12-01'})
        self.assertEqual((response.json()['title'], response.json()['target_date']), ('Renamed', '2026-12-01'))
        self.assertEqual(self.client.put(f'/api/releases/{release.pk}/', {'title': 'x'}).status_code, 405)

    def test_detail_query_count_does_not_grow_with_changes(self):
        small = self.team.release(self.team.api)
        self.team.advance(small, 'in_review')
        self.client.post(f'/api/releases/{small.pk}/comments/', {'body': 'First'})
        extra = []
        for index in range(6):
            extra.append(make_component(self.team.project, f'svc-{index}', self.team.li))
            depend(extra[-1], self.team.api)
        large = self.team.release(self.team.api, self.team.web, self.team.ui, *extra)
        self.team.advance(large, 'in_review')
        self.client.post(f'/api/releases/{large.pk}/comments/', {'body': 'Looks good'})

        with CaptureQueriesContext(connection) as few:
            self.detail(small)
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(len(self.detail(large)['changes']), 9)
        self.assertEqual(len(few), len(many))
        self.assertLessEqual(len(many), 15)

    def test_list_query_count_is_fixed(self):
        self.team.release(self.team.api)
        with CaptureQueriesContext(connection) as one:
            self.client.get('/api/releases/')
        for index in range(5):
            self.team.release(self.team.web, self.team.ui)
        with CaptureQueriesContext(connection) as six:
            self.assertEqual(self.client.get('/api/releases/').json()['count'], 6)
        self.assertEqual(len(one), len(six))


class CommentApiTests(TemporaryMediaMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.team = Team()
        self.release = self.team.release(self.team.api)
        self.url = f'/api/releases/{self.release.pk}/comments/'
        self.client.force_authenticate(self.team.li)

    def test_comment_with_screenshots(self):
        response = self.client.post(self.url, {'body': 'Error page after deploy', 'images': [
            image_upload('one.png'), image_upload('two.jpg', image_format='JPEG')]}, format='multipart')

        self.assertEqual(response.status_code, 201)
        shots = response.json()['screenshots']
        self.assertEqual(len(shots), 2)
        self.assertTrue(shots[0]['thumbnail'].endswith('-thumb.jpg'))
        timeline = self.client.get(f'/api/releases/{self.release.pk}/').json()['timeline']
        self.assertEqual([item['type'] for item in timeline[-2:]], ['comment', 'event'])
        self.assertEqual(timeline[-1]['message'], 'Error page after deploy (2 screenshots)')

    def test_plain_json_comments(self):
        response = self.client.post(self.url, {'body': 'Ship it'}, format='json')
        self.assertEqual((response.status_code, response.json()['screenshots']), (201, []))

    def test_screenshot_validation(self):
        not_image = SimpleUploadedFile('notes.png', b'not an image', content_type='image/png')
        bad = self.client.post(self.url, {'body': 'x', 'images': [not_image]}, format='multipart')
        self.assertEqual(bad.status_code, 400)

        too_many = []
        for index in range(6):
            too_many.append(image_upload(f'{index}.png'))
        self.assertEqual(self.client.post(self.url, {'body': 'x', 'images': too_many}, format='multipart').status_code, 400)
        self.assertEqual(self.client.post(self.url, {'body': '  '}, format='json').status_code, 400)
        self.assertFalse(Comment.objects.exists())

    def test_deleting_a_screenshot_removes_its_files(self):
        self.client.post(self.url, {'body': 'x', 'images': [image_upload()]}, format='multipart')
        shot = Screenshot.objects.get()
        storage, image_name = shot.image.storage, shot.image.name

        self.assertTrue(storage.exists(image_name))
        shot.delete()
        self.assertFalse(storage.exists(image_name))


class ExportTests(APITestCase):
    def setUp(self):
        self.team = Team()
        self.client.force_authenticate(self.team.ada)

    def rows(self, release):
        response = self.client.get(f'/api/releases/{release.pk}/export/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        text = response.content.decode('utf-8-sig')
        return response, list(csv.reader(io.StringIO(text)))

    def test_plan_csv_in_deploy_order(self):
        release = self.team.release(self.team.models, self.team.api, self.team.web, self.team.ui)
        self.team.advance(release, 'approved')

        response, rows = self.rows(release)

        self.assertIn('attachment; filename="release-plan-', response['Content-Disposition'])
        self.assertEqual(rows[0][:4], ['Wave', 'Step', 'Component', 'Kind'])
        self.assertEqual([row[2] for row in rows[1:]], ['models', 'api', 'ui', 'web'])
        self.assertEqual(rows[2], ['2', '2', 'api', 'Service', self.team.li.display_name, '15', 'Feature', 'Update api',
                                   'models', 'yes', self.team.li.display_name, ''])
        self.assertEqual(rows[1][-1], 'worker')
        self.assertEqual(rows[3][9], 'no')

    def test_components_on_a_cycle_are_marked(self):
        depend(self.team.models, self.team.api)
        release = self.team.release(self.team.api, self.team.models, self.team.ui)

        _, rows = self.rows(release)

        self.assertEqual([(row[0], row[1], row[2]) for row in rows[1:]],
                         [('1', '', 'ui'), ('cycle', '', 'api'), ('cycle', '', 'models')])

    def test_formulas_are_escaped(self):
        release = Release.objects.create(project=self.team.project, title='T', version='9', created_by=self.team.ada)
        release.changes.create(component=self.team.ui, summary='=HYPERLINK("http://evil")')

        _, rows = self.rows(release)
        self.assertEqual(rows[1][7], '\'=HYPERLINK("http://evil")')


class TimelineOrderTests(APITestCase):
    def test_timeline_merges_events_and_comments(self):
        team = Team()
        release = team.release(team.api)
        workflow.perform(release, team.manager, 'submit')
        team.client = self.client
        self.client.force_authenticate(team.manager)
        self.client.post(f'/api/releases/{release.pk}/comments/', {'body': 'Note'}, format='json')

        kinds = []
        for item in self.client.get(f'/api/releases/{release.pk}/').json()['timeline']:
            kinds.append(item.get('kind', item['type']))
        self.assertEqual(kinds, ['created', 'change_added', 'submitted', 'comment', 'commented'])
