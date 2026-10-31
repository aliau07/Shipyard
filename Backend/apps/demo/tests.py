import os
from io import StringIO
from unittest import mock

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.test import TransactionTestCase

from apps.core.testing import TemporaryMediaMixin
from apps.notifications.models import Notification
from apps.projects.models import Project
from apps.releases import workflow
from apps.releases.models import Release, Screenshot
from apps.releases.planning import plan_for


class SeedDemoDataTests(TemporaryMediaMixin, TransactionTestCase):
    def seed(self, *args):
        out = StringIO()
        with mock.patch.dict(os.environ, {'DEMO_PASSWORD': 'demo-pass-123'}):
            call_command('seed_demo_data', *args, stdout=out)
        return out.getvalue()

    def test_seed_builds_a_working_demo(self):
        output = self.seed()

        self.assertIn('Demo data ready: 1 project, 12 components, 21 dependencies, 6 releases.', output)
        self.assertIn('nora    demo-pass-123', output)
        self.assertEqual(set(Release.objects.values_list('status', flat=True)),
                         {'draft', 'in_review', 'blocked', 'released', 'cancelled'})
        refunds = Release.objects.get(version='2026.11.1')
        self.assertEqual(plan_for(refunds)['cycle'], ['orders-service', 'payments-service', 'orders-service'])
        checkout = Release.objects.get(version='2026.11.0')
        self.assertEqual(plan_for(checkout)['waves'],
                         [['auth-service', 'design-system'], ['api-gateway'], ['web-storefront']])
        self.assertEqual(workflow.approval_blockers(checkout), ['Waiting for sign-off on auth-service (Li Wei).'])
        self.assertEqual(Screenshot.objects.count(), 2)
        self.assertTrue(Notification.objects.filter(read_at__isnull=True).exists())
        self.assertIsNotNone(authenticate(username='raj', password='demo-pass-123'))

    def test_rerun_and_reset(self):
        self.seed()

        self.assertIn('already exists', self.seed())
        self.assertEqual(Project.objects.count(), 1)
        self.seed('--reset')
        self.assertEqual((Project.objects.count(), Release.objects.count()), (1, 6))
