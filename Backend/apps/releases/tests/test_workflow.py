from django.test import TestCase

from apps.projects.tests.factories import Team, depend, make_component, make_project
from apps.releases import services, workflow
from apps.releases.models import ReleaseEvent, SignOff
from apps.releases.planning import plan_for
from apps.releases.workflow import TransitionNotAllowed, WorkflowError


def names(actions):
    result = []
    for action in actions:
        result.append(action['name'])
    return result


class WorkflowTests(TestCase):
    def setUp(self):
        self.team = Team()

    def fresh(self, release):
        release.refresh_from_db()
        release.__dict__.pop('_plan', None)
        return release

    def test_happy_path_from_draft_to_released(self):
        release = self.team.release(self.team.api, self.team.web)
        manager = self.team.manager

        workflow.perform(release, manager, 'submit')
        workflow.perform(release, self.team.li, 'sign_off', {'note': 'Load tested'})
        workflow.perform(release, self.team.ada, 'sign_off')
        workflow.perform(release, manager, 'approve')
        workflow.perform(release, manager, 'start')
        workflow.perform(release, manager, 'mark_released')

        release = self.fresh(release)
        self.assertEqual(release.status, 'released')
        self.assertTrue(release.submitted_at and release.approved_at and release.started_at and release.released_at)
        self.assertEqual(list(release.events.values_list('kind', flat=True)), [
            'created', 'change_added', 'change_added', 'submitted', 'signed_off', 'signed_off', 'approved',
            'started', 'released'])
        self.assertEqual(release.events.get(kind='signed_off', actor=self.team.li).message, 'Signed off api. Load tested')
        self.assertEqual(release.events.get(kind='started').message, 'Deploying in 2 waves.')

    def test_submitting_needs_a_change(self):
        release = self.team.release()
        with self.assertRaisesMessage(TransitionNotAllowed, 'Add at least one component change before submitting.'):
            workflow.perform(release, self.team.manager, 'submit')

    def test_engineers_submit_only_their_own_drafts(self):
        theirs = self.team.release(self.team.api)
        with self.assertRaisesMessage(TransitionNotAllowed, 'Engineers can only submit releases they created.'):
            workflow.perform(theirs, self.team.li, 'submit')

        mine = self.team.release(self.team.api, author=self.team.li)
        self.assertEqual(workflow.perform(mine, self.team.li, 'submit').status, 'in_review')

    def test_roles_are_checked_before_status(self):
        release = self.team.release(self.team.api)
        with self.assertRaises(WorkflowError) as raised:
            workflow.perform(release, self.team.li, 'approve')
        self.assertEqual(raised.exception.status_code, 403)
        with self.assertRaises(WorkflowError) as raised:
            workflow.perform(release, self.team.outsider, 'submit')
        self.assertEqual(raised.exception.status_code, 403)

    def test_wrong_status_is_a_conflict(self):
        release = self.team.release(self.team.api)
        with self.assertRaises(TransitionNotAllowed) as raised:
            workflow.perform(release, self.team.manager, 'start')
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn('A release that is draft can\'t be changed with "Start rollout"', raised.exception.message)

    def test_unknown_action(self):
        with self.assertRaisesMessage(WorkflowError, 'Unknown action "ship-it".'):
            workflow.perform(self.team.release(self.team.api), self.team.manager, 'ship-it')

    def test_approval_waits_for_every_component_owner(self):
        release = self.team.advance(self.team.release(self.team.api, self.team.web), 'in_review')
        workflow.perform(release, self.team.li, 'sign_off')

        with self.assertRaises(TransitionNotAllowed) as raised:
            workflow.perform(release, self.team.manager, 'approve')
        self.assertEqual(raised.exception.message, f'Waiting for sign-off on web ({self.team.ada.display_name}).')

    def test_sign_off_covers_only_your_own_components(self):
        release = self.team.advance(self.team.release(self.team.api, self.team.models, self.team.web), 'in_review')

        workflow.perform(release, self.team.li, 'sign_off')

        signed = sorted(SignOff.objects.filter(release=release).values_list('component__name', flat=True))
        self.assertEqual(signed, ['api', 'models'])
        with self.assertRaisesMessage(TransitionNotAllowed, 'Nothing in this release is waiting for your sign-off.'):
            workflow.perform(release, self.team.li, 'sign_off')

    def test_managers_sign_off_components_without_an_owner(self):
        release = self.team.advance(self.team.release(self.team.worker), 'in_review')
        with self.assertRaises(TransitionNotAllowed):
            workflow.perform(release, self.team.li, 'sign_off')

        workflow.perform(release, self.team.manager, 'sign_off')
        self.assertEqual(workflow.perform(release, self.team.manager, 'approve').status, 'approved')

    def test_a_cycle_blocks_approval_even_with_every_sign_off(self):
        depend(self.team.models, self.team.api)
        release = self.team.advance(self.team.release(self.team.api, self.team.models), 'in_review')
        workflow.perform(release, self.team.li, 'sign_off')

        self.assertEqual(workflow.pending_sign_offs(release), [])
        with self.assertRaises(TransitionNotAllowed) as raised:
            workflow.perform(release, self.team.manager, 'approve')
        self.assertIn('depend on each other in a cycle: api → models → api', raised.exception.message)
        self.assertNotIn('approve', names(workflow.allowed_actions(release, self.team.manager)))

    def test_a_cycle_through_an_unchanged_component_still_blocks(self):
        depend(self.team.models, self.team.web)
        release = self.team.advance(self.team.release(self.team.web, self.team.models), 'in_review')
        self.team.sign_all(release)

        self.assertEqual(plan_for(release)['cycle'], ['models', 'web', 'models'])
        with self.assertRaisesMessage(TransitionNotAllowed, 'cycle: models → web → models'):
            workflow.perform(release, self.team.manager, 'approve')

    def test_a_cycle_elsewhere_in_the_project_does_not_block(self):
        depend(self.team.models, self.team.worker)
        release = self.team.advance(self.team.release(self.team.ui), 'approved')
        self.assertEqual(release.status, 'approved')

    def test_allowed_actions_follow_role_and_status(self):
        release = self.team.release(self.team.api, self.team.web)
        self.assertEqual(names(workflow.allowed_actions(release, self.team.manager)), ['submit', 'cancel'])
        self.assertEqual(names(workflow.allowed_actions(release, self.team.li)), [])
        self.assertEqual(names(workflow.allowed_actions(release, self.team.outsider)), [])

        workflow.perform(release, self.team.manager, 'submit')
        self.assertEqual(names(workflow.allowed_actions(release, self.team.li)), ['sign_off', 'block'])
        self.assertEqual(names(workflow.allowed_actions(release, self.team.manager)), ['request_changes', 'block', 'cancel'])

        self.team.sign_all(release)
        self.assertEqual(names(workflow.allowed_actions(release, self.team.owner)),
                         ['approve', 'request_changes', 'block', 'cancel'])
        self.assertEqual(workflow.allowed_actions(release, self.team.owner)[0],
                         {'name': 'approve', 'label': 'Approve release', 'fields': ['note']})

    def test_request_changes_returns_to_draft_and_clears_sign_offs(self):
        release = self.team.advance(self.team.release(self.team.api), 'in_review')
        workflow.perform(release, self.team.li, 'sign_off')
        with self.assertRaisesMessage(WorkflowError, 'A reason is required.'):
            workflow.perform(release, self.team.manager, 'request_changes')

        workflow.perform(release, self.team.manager, 'request_changes', {'reason': 'Split the migration out'})

        self.assertEqual((release.status, release.submitted_at), ('draft', None))
        self.assertFalse(SignOff.objects.filter(release=release).exists())

    def test_blocking_returns_to_where_it_was(self):
        release = self.team.advance(self.team.release(self.team.api), 'approved')
        workflow.perform(release, self.team.li, 'block', {'reason': 'Database upgrade first'})
        self.assertEqual((release.status, release.blocked_from, release.blocked_reason),
                         ('blocked', 'approved', 'Database upgrade first'))
        with self.assertRaises(WorkflowError) as raised:
            workflow.perform(release, self.team.li, 'unblock')
        self.assertEqual(raised.exception.status_code, 403)

        workflow.perform(release, self.team.manager, 'unblock')
        self.assertEqual((release.status, release.blocked_from, release.blocked_reason), ('approved', '', ''))

    def test_blocking_needs_a_reason(self):
        release = self.team.advance(self.team.release(self.team.api), 'in_review')
        with self.assertRaisesMessage(WorkflowError, 'A reason is required.'):
            workflow.perform(release, self.team.li, 'block', {'reason': '   '})

    def test_cancel_and_reopen(self):
        release = self.team.advance(self.team.release(self.team.api), 'in_review')
        workflow.perform(release, self.team.li, 'sign_off')
        workflow.perform(release, self.team.manager, 'cancel', {'reason': 'Merged into 2.0'})
        self.assertEqual(release.status, 'cancelled')
        self.assertEqual(names(workflow.allowed_actions(release, self.team.manager)), ['reopen'])

        workflow.perform(release, self.team.owner, 'reopen', {'reason': 'Needed after all'})

        release = self.fresh(release)
        self.assertEqual((release.status, release.reopen_count, release.closed_at), ('draft', 1, None))
        self.assertFalse(SignOff.objects.filter(release=release).exists())

    def test_released_releases_can_be_reopened_but_not_cancelled(self):
        release = self.team.advance(self.team.release(self.team.api), 'released')
        with self.assertRaises(TransitionNotAllowed):
            workflow.perform(release, self.team.manager, 'cancel', {'reason': 'x'})

        workflow.perform(release, self.team.manager, 'reopen', {'reason': 'Hotfix'})
        self.assertEqual((release.status, release.released_at, release.approved_at), ('draft', None, None))

    def test_events_record_the_status_change(self):
        release = self.team.advance(self.team.release(self.team.api), 'in_review')
        event = ReleaseEvent.objects.get(release=release, kind='submitted')
        self.assertEqual((event.from_status, event.to_status, event.actor), ('draft', 'in_review', self.team.manager))


class ChangeRulesTests(TestCase):
    def setUp(self):
        self.team = Team()

    def test_changes_are_only_edited_in_drafts(self):
        release = self.team.advance(self.team.release(self.team.api), 'in_review')
        with self.assertRaises(services.ReleaseError) as raised:
            services.add_change(release, self.team.manager, 'release_manager', self.team.web, 'More')
        self.assertEqual(raised.exception.status_code, 409)
        with self.assertRaises(services.ReleaseError):
            services.remove_change(release.changes.get(), self.team.manager, 'release_manager')

    def test_who_may_add_a_change(self):
        release = self.team.release(self.team.api)
        services.add_change(release, self.team.ada, 'engineer', self.team.ui, 'New button')
        with self.assertRaises(services.ReleaseError) as raised:
            services.add_change(release, self.team.li, 'engineer', self.team.worker, 'Retry jobs')
        self.assertEqual(raised.exception.status_code, 403)

    def test_change_validation(self):
        release = self.team.release(self.team.api)
        foreign = make_component(make_project(self.team.manager), 'foreign')
        with self.assertRaisesMessage(services.ReleaseError, 'api is already in this release.'):
            services.add_change(release, self.team.manager, 'release_manager', self.team.api, 'Again')
        with self.assertRaisesMessage(services.ReleaseError, 'foreign belongs to a different project.'):
            services.add_change(release, self.team.manager, 'release_manager', foreign, 'Elsewhere')
        with self.assertRaisesMessage(services.ReleaseError, 'Describe what changes in web.'):
            services.add_change(release, self.team.manager, 'release_manager', self.team.web, '  ')

    def test_detail_edits(self):
        first = self.team.release(self.team.api, version='1.0.0')
        second = self.team.release(self.team.api, version='2.0.0')
        with self.assertRaisesMessage(services.ReleaseError, 'already has a release with version 1.0.0'):
            services.update_release(second, self.team.manager, 'release_manager', {'version': '1.0.0'})
        with self.assertRaises(services.ReleaseError) as raised:
            services.update_release(first, self.team.li, 'engineer', {'title': 'Mine now'})
        self.assertEqual(raised.exception.status_code, 403)

        services.update_release(first, self.team.manager, 'release_manager', {'title': 'Spring release'})
        self.assertEqual(first.events.last().message, 'Updated title')


class PlanTests(TestCase):
    def setUp(self):
        self.team = Team()

    def test_waves_order_critical_path_and_unchanged_dependents(self):
        release = self.team.release(self.team.models, self.team.api, self.team.web, self.team.ui)

        plan = plan_for(release)

        self.assertEqual(plan['waves'], [['models', 'ui'], ['api'], ['web']])
        self.assertEqual(plan['order'], ['models', 'api', 'ui', 'web'])
        self.assertEqual(plan['critical_path'], {'minutes': 28, 'path': ['models', 'api', 'web']})
        self.assertEqual(plan['estimated_minutes'], 28)
        self.assertEqual(plan['unchanged_dependents'], ['worker'])

    def test_plan_keeps_order_through_unchanged_components(self):
        release = self.team.release(self.team.web, self.team.models)

        plan = plan_for(release)

        self.assertEqual(plan['edges'], [{'from': 'web', 'to': 'models'}])
        self.assertEqual(plan['waves'], [['models'], ['web']])
        self.assertIn({'name': 'api', 'depth': 1, 'path': ['models', 'api'], 'in_view': False}, plan['impact']['models'])
