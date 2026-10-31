from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.projects.tests.factories import Team, depend
from apps.releases import workflow


class DashboardTests(APITestCase):
    def setUp(self):
        self.team = Team()
        team = self.team
        self.released = team.advance(team.release(team.models, team.api, team.web), 'released')
        self.blocked = team.advance(team.release(team.ui, title='Buttons'), 'blocked')
        self.draft = team.release(team.web, team.ui)
        self.cancelled = team.advance(team.release(team.api), 'cancelled')
        depend(team.models, team.worker)
        self.cyclic = team.release(team.worker, team.models)
        Team().release()

    def get(self, user, query=''):
        self.client.force_authenticate(user)
        response = self.client.get(f'/api/dashboard/{query}')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_figures(self):
        data = self.get(self.team.li)

        statuses = {}
        for row in data['by_status']:
            statuses[row['key']] = row['count']
        self.assertEqual(statuses, {'draft': 2, 'in_review': 0, 'approved': 0, 'in_progress': 0, 'released': 1,
                                    'blocked': 1, 'cancelled': 1})
        self.assertEqual((data['summary']['releases'], data['summary']['open'], data['summary']['blocked'],
                          data['summary']['released_recently']), (5, 3, 1, 1))
        self.assertEqual([(r['title'], r['blocked_reason']) for r in data['blocked_releases']],
                         [('Buttons', 'Waiting for QA')])
        self.assertEqual([(c['name'], c['dependents']) for c in data['most_depended_on']],
                         [('models', 2), ('api', 1), ('ui', 1), ('worker', 1)])
        # released: models, api, web -> 3 waves; blocked: ui -> 1; draft: ui then web -> 2; the release with
        # worker <-> models doesn't count and the cancelled one is ignored.
        self.assertEqual(data['waves'], {'average': 2.0, 'releases': 3, 'with_cycles': 1})

    def test_one_project_and_404_for_others(self):
        other = Team()
        self.assertEqual(self.get(self.team.li, f'?project={self.team.project.pk}')['summary']['releases'], 5)
        self.client.force_authenticate(self.team.li)
        self.assertEqual(self.client.get(f'/api/dashboard/?project={other.project.pk}').status_code, 404)
        self.assertEqual(self.client.get('/api/dashboard/?project=abc').status_code, 404)

    def test_outsiders_see_an_empty_dashboard(self):
        data = self.get(self.team.outsider)
        self.assertEqual((data['summary']['releases'], data['most_depended_on'], data['waves']['average']), (0, [], None))

    def test_query_count_does_not_grow_with_releases(self):
        with CaptureQueriesContext(connection) as before:
            self.get(self.team.manager)
        for index in range(4):
            workflow.perform(self.team.release(self.team.web, self.team.ui), self.team.manager, 'submit')
        with CaptureQueriesContext(connection) as after:
            self.get(self.team.manager)
        self.assertEqual(len(before), len(after))
