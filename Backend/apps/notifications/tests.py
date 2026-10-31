from django.core import mail
from django.db import transaction
from rest_framework.test import APITestCase

from apps.projects.models import Membership
from apps.projects.tests.factories import Team
from apps.releases import services, workflow

from .models import Notification


class RecipientTests(APITestCase):
    def setUp(self):
        self.team = Team()

    def notified(self, kind):
        found = []
        for notification in Notification.objects.filter(event__kind=kind).select_related('recipient'):
            found.append(notification.recipient.username)
        return sorted(found)

    def run_on_commit(self, func, *args, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return func(*args, **kwargs)

    def usernames(self, *users):
        found = []
        for user in users:
            found.append(user.username)
        return sorted(found)

    def test_a_new_release_tells_the_managers(self):
        self.run_on_commit(self.team.release, self.team.api, author=self.team.li)

        self.assertEqual(self.notified('created'), self.usernames(self.team.owner, self.team.manager))
        self.assertEqual(self.notified('change_added'), [])

    def test_submitting_asks_component_owners_and_managers_but_not_the_actor(self):
        release = self.run_on_commit(self.team.release, self.team.api, self.team.web)
        self.run_on_commit(workflow.perform, release, self.team.manager, 'submit')

        self.assertEqual(self.notified('submitted'), self.usernames(self.team.owner, self.team.li, self.team.ada))

    def test_sign_offs_tell_the_author_and_managers(self):
        release = self.team.advance(self.team.release(self.team.api, author=self.team.ada), 'in_review')
        self.run_on_commit(workflow.perform, release, self.team.li, 'sign_off')

        self.assertEqual(self.notified('signed_off'), self.usernames(self.team.owner, self.team.manager, self.team.ada))

    def test_comments_include_the_text(self):
        release = self.team.release(self.team.api)
        self.run_on_commit(services.add_comment, release, self.team.ada, 'Smoke tests are red')

        self.assertEqual(self.notified('commented'), self.usernames(self.team.owner, self.team.manager, self.team.li))
        self.assertIn('Smoke tests are red', Notification.objects.first().message)

    def test_people_who_left_the_project_are_not_told(self):
        release = self.team.release(self.team.api, self.team.web)
        Membership.objects.filter(user=self.team.ada).delete()
        self.run_on_commit(workflow.perform, release, self.team.manager, 'submit')

        self.assertNotIn(self.team.ada.username, self.notified('submitted'))

    def test_emails_link_to_the_release(self):
        release = self.team.release(self.team.api)
        self.run_on_commit(workflow.perform, release, self.team.manager, 'submit')

        self.assertTrue(mail.outbox)
        self.assertIn(f'/releases/{release.pk}', mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].subject.startswith(f'[Shipyard] {release.reference}'))

    def test_nothing_is_sent_for_rolled_back_changes(self):
        try:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    self.team.release(self.team.api)
                    raise RuntimeError('boom')
        except RuntimeError:
            pass

        self.assertFalse(Notification.objects.exists())


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.team = Team()
        with self.captureOnCommitCallbacks(execute=True):
            self.team.release(self.team.api, author=self.team.li)
            self.team.release(self.team.web, author=self.team.li)
        self.client.force_authenticate(self.team.manager)

    def test_list_count_and_mark_read(self):
        listing = self.client.get('/api/notifications/').json()
        self.assertEqual(listing['count'], 2)
        self.assertEqual(listing['results'][0]['project_name'], self.team.project.name)
        self.assertEqual(self.client.get('/api/notifications/unread-count/').json(), {'unread': 2})

        read = self.client.post(f'/api/notifications/{listing["results"][0]["id"]}/read/').json()
        self.assertTrue(read['is_read'])
        self.assertEqual(self.client.get('/api/notifications/?unread=true').json()['count'], 1)

        self.client.post('/api/notifications/read-all/')
        self.assertEqual(self.client.get('/api/notifications/unread-count/').json(), {'unread': 0})

    def test_people_only_see_their_own(self):
        theirs = Notification.objects.filter(recipient=self.team.manager).first()
        self.client.force_authenticate(self.team.ada)

        self.assertEqual(self.client.get('/api/notifications/').json()['count'], 0)
        self.assertEqual(self.client.post(f'/api/notifications/{theirs.pk}/read/').status_code, 404)
