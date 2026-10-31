import json
import os
import secrets
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test.utils import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.demo.images import screenshot
from apps.notifications.models import Notification
from apps.projects import services as projects
from apps.projects.models import Component, Dependency, Membership, Project
from apps.releases import services as releases
from apps.releases import workflow
from apps.releases.models import Release, ReleaseEvent, Status

PROJECT_NAME = 'Atlas Commerce'

PEOPLE = [
    ('admin', 'Site', 'Admin', None, 'superuser: Django admin'),
    ('nora', 'Nora', 'Quinn', 'owner', 'project owner'),
    ('raj', 'Raj', 'Patel', 'release_manager', 'release manager, owns api-gateway'),
    ('li', 'Li', 'Wei', 'engineer', 'backend engineer: auth, payments, notifications, shared-models'),
    ('ada', 'Ada', 'Byrne', 'engineer', 'frontend engineer: design-system and both frontends'),
    ('tomas', 'Tomás', 'Novak', 'engineer', 'backend engineer: orders, inventory, http-client, feature-flags'),
]

COMPONENTS = [
    # name, kind, owner, deploy minutes, package name, description
    ('shared-models', 'library', 'li', 5, 'atlas-shared-models', 'Pydantic models shared by the Python services.'),
    ('http-client', 'library', 'tomas', 4, '@atlas/http-client', 'Typed fetch wrapper used by both frontends.'),
    ('design-system', 'library', 'ada', 6, '@atlas/design-system', 'React components and design tokens.'),
    ('feature-flags', 'library', 'tomas', 3, 'atlas-feature-flags', 'Flag evaluation for Python and JavaScript.'),
    ('auth-service', 'service', 'li', 12, '', 'Sign-in, sessions and API tokens.'),
    ('inventory-service', 'service', 'tomas', 15, '', 'Stock levels and reservations.'),
    ('payments-service', 'service', 'li', 20, '', 'Card payments and refunds.'),
    ('orders-service', 'service', 'tomas', 18, '', 'Carts, orders and fulfilment.'),
    ('notifications-service', 'service', 'li', 8, '', 'Order emails and push messages.'),
    ('api-gateway', 'service', 'raj', 10, '', 'Public REST API in front of the services.'),
    ('web-storefront', 'frontend', 'ada', 9, '@atlas/web-storefront', 'The customer-facing shop.'),
    ('admin-console', 'frontend', 'ada', 7, '@atlas/admin-console', 'Back-office tool for the support team.'),
]

DEPENDENCIES = [
    ('inventory-service', 'shared-models'),
    ('payments-service', 'shared-models'),
    ('payments-service', 'auth-service'),
    ('notifications-service', 'shared-models'),
    ('orders-service', 'shared-models'),
    ('orders-service', 'inventory-service'),
    ('orders-service', 'payments-service'),
    ('orders-service', 'notifications-service'),
    ('api-gateway', 'auth-service'),
    ('api-gateway', 'orders-service'),
    ('api-gateway', 'inventory-service'),
    ('web-storefront', 'api-gateway'),
    ('admin-console', 'design-system'),
    ('admin-console', 'http-client'),
    ('admin-console', 'api-gateway'),
]

AUTH_REQUIREMENTS = '''# auth-service runtime dependencies
Django==5.2.7
djangorestframework>=3.16
atlas-shared-models==2.3.1   # internal
atlas_feature_flags~=1.4
PyJWT[crypto]>=2.8
requests>=2.32 ; python_version >= "3.10"
'''

STOREFRONT_PACKAGE = {
    'name': '@atlas/web-storefront',
    'private': True,
    'dependencies': {
        '@atlas/design-system': '^3.2.0', '@atlas/http-client': '^1.8.0', '@atlas/feature-flags': '^1.4.0',
        'react': '^18.3.1', 'react-dom': '^18.3.1', 'react-router-dom': '^6.26.0',
    },
    'devDependencies': {'jest': '^29.7.0'},
}


class Command(BaseCommand):
    help = (
        'Create a demo team and the "Atlas Commerce" project: 12 components with realistic dependencies (some '
        'imported from manifests), and releases in every stage, including one whose components form a dependency '
        'cycle and one valid release waiting for its last sign-off. Demo passwords are generated on every run (or '
        'taken from DEMO_PASSWORD) and printed to the console.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete the demo project first, then recreate it.')

    def handle(self, *args, **options):
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            with transaction.atomic():
                credentials, users = self.create_people()
                if options['reset']:
                    self.reset(self.demo_projects(users))
                if self.demo_projects(users).exists():
                    self.stdout.write('The demo project already exists (use --reset to rebuild it).')
                else:
                    self.build(users)
            Notification.objects.filter(release__status__in=[Status.RELEASED, Status.CANCELLED],
                                        read_at__isnull=True).update(read_at=timezone.now())

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Demo accounts'))
        for username, password, description in credentials:
            self.stdout.write(f'  {username:<7} {password:<20} ({description})')
        self.stdout.write('These passwords are not stored anywhere else; re-run this command to rotate them.')

    def create_people(self):
        shared_password = os.environ.get('DEMO_PASSWORD')
        credentials, users = [], {}
        for username, first, last, _, description in PEOPLE:
            password = shared_password or secrets.token_urlsafe(12)
            user, _ = User.objects.get_or_create(username=username, defaults={
                'email': f'{username}@example.com', 'first_name': first, 'last_name': last,
            })
            user.is_staff = user.is_superuser = username == 'admin'
            user.set_password(password)
            user.save()
            credentials.append((username, password, description))
            users[username] = user
        return credentials, users

    def demo_projects(self, users):
        return Project.objects.filter(name=PROJECT_NAME, memberships__user=users['nora'])

    def reset(self, existing):
        for project in existing:
            for release in project.releases.all():
                for comment in release.comments.all():
                    for shot in comment.screenshots.all():
                        shot.delete()
            Notification.objects.filter(release__project=project).delete()
            project.delete()
        self.stdout.write('Removed the existing demo project.')

    def build(self, users):
        nora = users['nora']
        project = projects.create_project(nora, name=PROJECT_NAME, description=(
            'Online shop: Python services behind an API gateway, two React frontends and shared libraries.'))
        for username, _, _, role, _ in PEOPLE:
            if role and username != 'nora':
                projects.add_member(project, nora, username, role)
        components = {}
        for name, kind, owner, minutes, package_name, description in COMPONENTS:
            components[name] = projects.create_component(
                project, nora, name=name, kind=kind, owner=users[owner], deploy_minutes=minutes,
                package_name=package_name, description=description)
        for dependent, dependency in DEPENDENCIES:
            projects.add_dependency(nora, components[dependent], components[dependency])
        projects.import_manifest(components['auth-service'], users['li'], SimpleUploadedFile(
            'requirements.txt', AUTH_REQUIREMENTS.encode()))
        projects.import_manifest(components['web-storefront'], users['ada'], SimpleUploadedFile(
            'package.json', json.dumps(STOREFRONT_PACKAGE, indent=2).encode()))

        self.releases(project, users, components)
        self.stdout.write(self.style.SUCCESS(
            f'Demo data ready: 1 project, {Component.objects.filter(project=project).count()} components, '
            f'{Dependency.objects.filter(component__project=project).count()} dependencies, '
            f'{Release.objects.filter(project=project).count()} releases.'
        ))

    def releases(self, project, users, components):
        nora, raj, li, ada, tomas = users['nora'], users['raj'], users['li'], users['ada'], users['tomas']

        def draft(author, title, version, changes, days_ago, description='', target_in_days=None):
            change_list = []
            for name, change_type, summary in changes:
                change_list.append({'component': components[name], 'summary': summary, 'change_type': change_type})
            target = timezone.localdate() + timedelta(days=target_in_days) if target_in_days is not None else None
            release = releases.create_release(author, project=project, title=title, version=version,
                                              description=description, target_date=target, changes=change_list)
            release.days_ago = days_ago
            return release

        def act(release, user, action, **data):
            workflow.perform(release, user, action, data)

        search = draft(raj, 'Search relevance', '2026.10.0', [
            ('inventory-service', 'feature', 'Expose stock counts to the search index.'),
            ('api-gateway', 'feature', 'New /search endpoint with typo tolerance.'),
            ('web-storefront', 'feature', 'Search results page with filters.'),
        ], days_ago=24, description='Better search results on the storefront.')
        act(search, raj, 'submit')
        act(search, tomas, 'sign_off', note='Index load tested at 3x peak.')
        act(search, raj, 'sign_off')
        act(search, ada, 'sign_off')
        act(search, raj, 'approve')
        act(search, raj, 'start')
        act(search, raj, 'mark_released', note='All three waves green.')

        coupons = draft(nora, 'Legacy coupon cleanup', '2026.10.1', [
            ('orders-service', 'chore', 'Remove the v1 coupon tables.'),
        ], days_ago=16)
        act(coupons, nora, 'submit')
        act(coupons, nora, 'cancel', reason='Marketing still needs v1 coupons until the end of Q1.')

        # A refund callback makes payments-service depend on orders-service, which already depends on it.
        projects.add_dependency(li, components['payments-service'], components['orders-service'])

        checkout = draft(raj, 'Checkout revamp', '2026.11.0', [
            ('design-system', 'feature', 'Checkout form components and address autocomplete.'),
            ('web-storefront', 'feature', 'One-page checkout.'),
            ('api-gateway', 'feature', 'Checkout session endpoints.'),
            ('auth-service', 'fix', 'Shorter guest-session tokens.'),
        ], days_ago=6, description='Valid plan in three waves; waiting for the auth-service sign-off.',
            target_in_days=5)
        act(checkout, raj, 'submit')
        act(checkout, ada, 'sign_off', note='Visual regression suite passes.')
        act(checkout, raj, 'sign_off')
        releases.add_comment(checkout, ada, 'Final checkout layout attached for review.',
                             [screenshot('Checkout: one-page layout', boxes=3)])

        refunds = draft(li, 'Payment refund callbacks', '2026.11.1', [
            ('payments-service', 'feature', 'Call orders-service when a refund settles.'),
            ('orders-service', 'feature', 'Refunded state for orders.'),
            ('notifications-service', 'feature', 'Refund confirmation emails.'),
        ], days_ago=4, description='Contains a dependency cycle between payments-service and orders-service.',
            target_in_days=9)
        act(refunds, li, 'submit')
        act(refunds, li, 'sign_off')
        act(refunds, tomas, 'sign_off')
        releases.add_comment(refunds, raj, 'Approval is blocked: payments-service and orders-service now depend on '
                             'each other. Could the refund callback go through an event instead?',
                             [screenshot('Dependency cycle: payments-service <-> orders-service', boxes=2, variant=1)])

        inventory = draft(tomas, 'Inventory sync v2', '2026.11.2', [
            ('shared-models', 'breaking', 'Stock level schema v2.'),
            ('inventory-service', 'feature', 'Sync stock from the warehouse every minute.'),
        ], days_ago=8, target_in_days=12)
        act(inventory, tomas, 'submit')
        act(inventory, li, 'sign_off')
        act(inventory, tomas, 'sign_off')
        act(inventory, raj, 'approve')
        act(inventory, raj, 'block', reason='Waiting for the database migration window.')

        tokens = draft(ada, 'Design tokens v3', '2026.12.0', [
            ('design-system', 'breaking', 'New colour and spacing tokens.'),
            ('admin-console', 'chore', 'Adopt the v3 tokens.'),
        ], days_ago=1, target_in_days=30)

        for release in (search, coupons, checkout, refunds, inventory, tokens):
            self.backdate(release, release.days_ago)

    def backdate(self, release, days, step_hours=7):
        """Pretend the release was drafted `days` ago, spreading its timeline out from then."""
        now = timezone.now()
        start = now - timedelta(days=days)
        events = list(ReleaseEvent.objects.filter(release=release).order_by('created_at', 'pk'))
        when = start
        for index, event in enumerate(events):
            when = min(start + timedelta(hours=step_hours * index), now)
            ReleaseEvent.objects.filter(pk=event.pk).update(created_at=when)
        release.comments.update(created_at=when)
        release.sign_offs.update(created_at=when)
        stamps = {'created_at': start}
        for field in ('submitted_at', 'approved_at', 'started_at', 'released_at', 'closed_at'):
            if getattr(release, field):
                stamps[field] = when
        Release.objects.filter(pk=release.pk).update(**stamps)
        Membership.objects.filter(project=release.project).update(created_at=now - timedelta(days=60))
