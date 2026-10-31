import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.projects.models import Component, Dependency, Membership

from .factories import Team, add_member, depend, make_component, make_project, make_user


def upload(name, content):
    return SimpleUploadedFile(name, content.encode() if isinstance(content, str) else content)


class ProjectApiTests(APITestCase):
    def setUp(self):
        self.team = Team()

    def as_user(self, user):
        self.client.force_authenticate(user)

    def test_projects_are_listed_only_for_members(self):
        self.as_user(self.team.owner)
        listing = self.client.get('/api/projects/').json()
        self.assertEqual(listing['count'], 1)
        self.assertEqual((listing['results'][0]['viewer_role'], listing['results'][0]['component_count']), ('owner', 5))

        self.as_user(self.team.outsider)
        self.assertEqual(self.client.get('/api/projects/').json()['count'], 0)

    def test_creating_a_project_makes_you_its_owner(self):
        self.as_user(self.team.outsider)
        response = self.client.post('/api/projects/', {'name': 'Billing', 'description': 'Invoices'})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['viewer_role'], 'owner')
        self.assertEqual([m['role'] for m in response.json()['members']], ['owner'])

    def test_non_members_get_404s(self):
        self.as_user(self.team.outsider)
        for url in (f'/api/projects/{self.team.project.pk}/', f'/api/projects/{self.team.project.pk}/graph/',
                    f'/api/components/{self.team.api.pk}/', f'/api/components/{self.team.api.pk}/impact/'):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.client.patch(f'/api/projects/{self.team.project.pk}/', {'name': 'x'}).status_code, 404)

    def test_engineers_cannot_edit_the_project_but_managers_can(self):
        url = f'/api/projects/{self.team.project.pk}/'
        self.as_user(self.team.li)
        self.assertEqual(self.client.patch(url, {'name': 'Renamed'}).status_code, 403)
        self.as_user(self.team.manager)
        self.assertEqual(self.client.patch(url, {'name': 'Renamed'}).json()['name'], 'Renamed')

    def test_only_owners_delete_projects(self):
        url = f'/api/projects/{self.team.project.pk}/'
        self.as_user(self.team.manager)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.as_user(self.team.owner)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_owners_add_members_by_email(self):
        self.as_user(self.team.owner)
        response = self.client.post(f'/api/projects/{self.team.project.pk}/members/',
                                    {'user': self.team.outsider.email.upper(), 'role': 'release_manager'})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['role'], 'release_manager')
        self.as_user(self.team.outsider)
        self.assertEqual(self.client.get('/api/projects/').json()['count'], 1)

    def test_member_errors(self):
        url = f'/api/projects/{self.team.project.pk}/members/'
        self.as_user(self.team.owner)
        self.assertIn('No account found', self.client.post(url, {'user': 'nobody'}).json()['detail'])
        self.assertIn('already in this project', self.client.post(url, {'user': self.team.li.username}).json()['detail'])
        self.as_user(self.team.li)
        self.assertEqual(self.client.post(url, {'user': self.team.outsider.username}).status_code, 403)

    def test_the_last_owner_cannot_leave_or_be_demoted(self):
        membership = Membership.objects.get(project=self.team.project, user=self.team.owner)
        url = f'/api/projects/{self.team.project.pk}/members/{membership.pk}/'
        self.as_user(self.team.owner)

        self.assertEqual(self.client.delete(url).status_code, 409)
        self.assertEqual(self.client.patch(url, {'role': 'engineer'}).status_code, 409)

    def test_removing_a_member_leaves_their_components_unowned(self):
        membership = Membership.objects.get(project=self.team.project, user=self.team.ada)
        self.as_user(self.team.owner)

        self.assertEqual(self.client.delete(f'/api/projects/{self.team.project.pk}/members/{membership.pk}/').status_code, 204)
        self.assertEqual(list(Component.objects.filter(owner=self.team.ada)), [])

    def test_members_may_leave_by_themselves(self):
        membership = Membership.objects.get(project=self.team.project, user=self.team.li)
        self.as_user(self.team.li)
        self.assertEqual(self.client.delete(f'/api/projects/{self.team.project.pk}/members/{membership.pk}/').status_code, 204)


class ComponentApiTests(APITestCase):
    def setUp(self):
        self.team = Team()

    def test_managers_create_components_with_validation(self):
        self.client.force_authenticate(self.team.manager)
        data = {'project': self.team.project.pk, 'name': 'payments', 'kind': 'service', 'owner': self.team.li.pk,
                'deploy_minutes': 20}

        created = self.client.post('/api/components/', data)
        self.assertEqual((created.status_code, created.json()['owner_name']), (201, self.team.li.display_name))
        self.assertIn('already a component', self.client.post('/api/components/', data).json()['detail'])
        self.assertIn('name', self.client.post('/api/components/', {**data, 'name': 'Bad Name'}).json())
        self.assertIn('deploy_minutes', self.client.post('/api/components/', {**data, 'name': 'x', 'deploy_minutes': 0}).json())
        outsider = self.client.post('/api/components/', {**data, 'name': 'y', 'owner': self.team.outsider.pk})
        self.assertIn('must be a member', outsider.json()['detail'])

    def test_engineers_cannot_create_components(self):
        self.client.force_authenticate(self.team.li)
        response = self.client.post('/api/components/', {'project': self.team.project.pk, 'name': 'payments'})
        self.assertEqual(response.status_code, 403)

    def test_component_owners_edit_details_but_cannot_hand_over(self):
        url = f'/api/components/{self.team.api.pk}/'
        self.client.force_authenticate(self.team.li)
        self.assertEqual(self.client.patch(url, {'deploy_minutes': 25}).json()['deploy_minutes'], 25)
        self.assertEqual(self.client.patch(url, {'owner': self.team.ada.pk}).status_code, 403)
        self.client.force_authenticate(self.team.ada)
        self.assertEqual(self.client.patch(url, {'deploy_minutes': 5}).status_code, 403)

    def test_list_filters_by_project_and_counts_edges(self):
        make_component(make_project(self.team.manager), 'elsewhere')
        self.client.force_authenticate(self.team.manager)

        rows = self.client.get(f'/api/components/?project={self.team.project.pk}').json()['results']
        counts = {}
        for row in rows:
            counts[row['name']] = (row['dependency_count'], row['dependent_count'])
        self.assertEqual(counts, {'api': (1, 1), 'models': (0, 2), 'ui': (0, 1), 'web': (2, 0), 'worker': (1, 0)})

    def test_components_used_by_a_release_cannot_be_deleted(self):
        self.team.release(self.team.api)
        self.client.force_authenticate(self.team.manager)
        self.assertEqual(self.client.delete(f'/api/components/{self.team.api.pk}/').status_code, 409)
        self.assertEqual(self.client.delete(f'/api/components/{self.team.worker.pk}/').status_code, 204)

    def test_impact_endpoint_lists_every_dependent_with_its_path(self):
        self.client.force_authenticate(self.team.ada)
        hits = self.client.get(f'/api/components/{self.team.models.pk}/impact/').json()
        self.assertEqual([(hit['name'], hit['path']) for hit in hits], [
            ('api', ['models', 'api']), ('worker', ['models', 'worker']), ('web', ['models', 'api', 'web'])])

    def test_component_list_query_count_does_not_grow(self):
        self.client.force_authenticate(self.team.manager)
        url = f'/api/components/?project={self.team.project.pk}'
        with CaptureQueriesContext(connection) as small:
            self.client.get(url)
        for index in range(6):
            depend(make_component(self.team.project, f'extra-{index}', self.team.li), self.team.models)
        with CaptureQueriesContext(connection) as large:
            self.assertEqual(self.client.get(url).json()['count'], 11)
        self.assertEqual(len(small), len(large))


class DependencyApiTests(APITestCase):
    def setUp(self):
        self.team = Team()

    def test_adding_an_edge_that_closes_a_cycle_reports_it(self):
        self.client.force_authenticate(self.team.manager)
        response = self.client.post('/api/dependencies/', {'component': self.team.models.pk,
                                                           'depends_on': self.team.web.pk})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['cycle'], ['models', 'web', 'api', 'models'])

    def test_a_plain_edge_has_no_cycle(self):
        self.client.force_authenticate(self.team.ada)
        response = self.client.post('/api/dependencies/', {'component': self.team.web.pk,
                                                           'depends_on': self.team.worker.pk})
        self.assertEqual((response.status_code, response.json()['cycle']), (201, None))

    def test_dependency_rules(self):
        other = make_component(make_project(self.team.manager), 'other')
        self.client.force_authenticate(self.team.manager)
        post = self.client.post

        self.assertIn('itself', post('/api/dependencies/', {'component': self.team.api.pk, 'depends_on': self.team.api.pk}).json()['detail'])
        self.assertIn('already depends', post('/api/dependencies/', {'component': self.team.api.pk, 'depends_on': self.team.models.pk}).json()['detail'])
        self.assertIn('same project', post('/api/dependencies/', {'component': self.team.api.pk, 'depends_on': other.pk}).json()['detail'])
        self.client.force_authenticate(self.team.li)
        self.assertEqual(post('/api/dependencies/', {'component': self.team.web.pk, 'depends_on': self.team.worker.pk}).status_code, 403)
        self.client.force_authenticate(self.team.outsider)
        self.assertEqual(post('/api/dependencies/', {'component': self.team.web.pk, 'depends_on': self.team.worker.pk}).status_code, 400)

    def test_listing_and_removing(self):
        self.client.force_authenticate(self.team.li)
        rows = self.client.get(f'/api/dependencies/?component={self.team.api.pk}').json()
        self.assertEqual(sorted((row['component_name'], row['depends_on_name']) for row in rows),
                         [('api', 'models'), ('web', 'api')])

        edge = Dependency.objects.get(component=self.team.api)
        self.assertEqual(self.client.delete(f'/api/dependencies/{edge.pk}/').status_code, 204)


class GraphApiTests(APITestCase):
    def setUp(self):
        self.team = Team()
        self.client.force_authenticate(self.team.li)
        self.url = f'/api/projects/{self.team.project.pk}/graph/'

    def test_graph_is_laid_out_in_waves_with_critical_path_and_impact(self):
        data = self.client.get(self.url).json()

        self.assertEqual(data['layers'], [['models', 'ui'], ['api', 'worker'], ['web']])
        self.assertEqual(data['waves'], data['layers'])
        self.assertIsNone(data['cycle'])
        self.assertEqual(data['critical_path'], {'minutes': 28, 'path': ['models', 'api', 'web']})
        self.assertEqual(data['estimated_minutes'], 28)
        self.assertIn({'from': 'web', 'to': 'api'}, data['edges'])
        self.assertEqual([hit['name'] for hit in data['impact']['models']], ['api', 'worker', 'web'])

    def test_cycles_are_reported_and_nodes_flagged(self):
        depend(self.team.models, self.team.web)

        data = self.client.get(self.url).json()

        self.assertEqual(data['cycle'], ['api', 'models', 'web', 'api'])
        self.assertEqual((data['waves'], data['blocked']), (None, ['api', 'models', 'web', 'worker']))
        flags = {}
        for node in data['nodes']:
            flags[node['name']] = (node['in_cycle'], node['wave'])
        self.assertEqual(flags['worker'], (False, None))
        self.assertEqual(flags['ui'], (False, 1))
        self.assertTrue(flags['api'][0] and flags['models'][0] and flags['web'][0])

    def test_graph_query_count_is_fixed(self):
        with CaptureQueriesContext(connection) as small:
            self.client.get(self.url)
        for index in range(5):
            depend(make_component(self.team.project, f'svc-{index}', self.team.li), self.team.api)
        with CaptureQueriesContext(connection) as large:
            self.client.get(self.url)
        self.assertEqual(len(small), len(large))


class ManifestApiTests(APITestCase):
    def setUp(self):
        self.team = Team()

    def post(self, user, component, name, content):
        self.client.force_authenticate(user)
        return self.client.post(f'/api/components/{component.pk}/manifest/', {'file': upload(name, content)},
                                format='multipart')

    def test_package_json_creates_dependencies_and_reports_unmatched_packages(self):
        content = json.dumps({'dependencies': {'@acme/ui': '^1.0.0', 'react': '^18.3.1', '@acme/worker': '2.0.0'}})

        response = self.post(self.team.ada, self.team.web, 'package.json', content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'format': 'package.json', 'packages': 3, 'created': ['worker'],
                                           'existing': ['ui'], 'unmatched': ['react'], 'cycle': None})
        self.assertEqual(Dependency.objects.get(component=self.team.web, depends_on=self.team.worker).source, 'manifest')

    def test_requirements_txt_matches_package_names(self):
        add_member(self.team.project, make_user(), 'engineer')
        cli = make_component(self.team.project, 'cli', self.team.li)

        response = self.post(self.team.li, cli, 'requirements.txt', 'acme-models==2.0  # shared\nDjango>=5\n-r base.txt\n')

        self.assertEqual((response.json()['created'], response.json()['unmatched']), (['models'], ['django']))

    def test_upload_reports_a_cycle_it_creates(self):
        response = self.post(self.team.li, self.team.models, 'requirements.txt', 'web==1.0\n')
        self.assertEqual(response.json()['cycle'], ['models', 'web', 'api', 'models'])

    def test_a_component_listing_itself_is_ignored(self):
        response = self.post(self.team.li, self.team.models, 'requirements.txt', 'acme_models\n')
        self.assertEqual((response.json()['packages'], response.json()['created'], response.json()['unmatched']), (1, [], []))

    def test_bad_uploads_are_explained(self):
        cases = [
            ('package.json', '{"dependencies": ', 'not valid JSON'),
            ('package.json', '[]', 'must contain a JSON object'),
            ('Pipfile', '[packages]', 'Upload a requirements.txt'),
            ('requirements.txt', '', 'is empty'),
        ]
        for name, content, message in cases:
            response = self.post(self.team.ada, self.team.web, name, content)
            self.assertEqual(response.status_code, 400, name)
            self.assertIn(message, str(response.json()), name)

    @override_settings(MAX_MANIFEST_SIZE_KB=1)
    def test_large_files_are_rejected(self):
        response = self.post(self.team.ada, self.team.web, 'requirements.txt', 'a\n' * 1000)
        self.assertIn('larger than 1 KB', response.json()['detail'])

    def test_missing_file_and_permissions(self):
        self.client.force_authenticate(self.team.ada)
        self.assertEqual(self.client.post(f'/api/components/{self.team.web.pk}/manifest/', {}, format='multipart').status_code, 400)
        self.assertEqual(self.post(self.team.li, self.team.web, 'requirements.txt', 'ui\n').status_code, 403)
        self.assertEqual(self.post(self.team.outsider, self.team.web, 'requirements.txt', 'ui\n').status_code, 404)
