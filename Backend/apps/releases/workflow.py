"""The release state machine.

Each action names the statuses it can start from, which project roles may perform it, and what it changes. The
API exposes `allowed_actions(release, user)` so the React app only shows buttons that will work, and
`perform()` re-checks everything on the server.

    draft -> in_review -> approved -> in_progress -> released
    in_review/approved/in_progress -> blocked -> back where it was
    draft/in_review/approved/blocked -> cancelled;  released/cancelled -> draft (reopen)

Approval needs a sign-off for every changed component (from its owner, or from a manager when it has none),
and the changed components must not depend on each other in a cycle.
"""
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from rest_framework import status as http

from apps.core.exceptions import DomainError
from apps.projects.models import MANAGER_ROLES, Membership

from .models import ReleaseEvent, SignOff, Status
from .planning import forget_plan, plan_for
from .scoping import relationship
from .services import record_event

Kind = ReleaseEvent.Kind
Role = Membership.Role
EVERYONE = [Role.OWNER, Role.RELEASE_MANAGER, Role.ENGINEER]
MANAGERS = list(MANAGER_ROLES)


class WorkflowError(DomainError):
    pass


class TransitionNotAllowed(WorkflowError):
    status_code = http.HTTP_409_CONFLICT


@dataclass(frozen=True)
class Action:
    name: str
    label: str
    sources: frozenset
    roles: frozenset
    fields: tuple = field(default_factory=tuple)


def _action(name, label, sources, roles, fields=()):
    return Action(name, label, frozenset(sources), frozenset(roles), tuple(fields))


ACTIONS = {}
for _definition in [
    _action('submit', 'Submit for review', [Status.DRAFT], EVERYONE, ['note']),
    _action('sign_off', 'Sign off', [Status.IN_REVIEW], EVERYONE, ['note']),
    _action('approve', 'Approve release', [Status.IN_REVIEW], MANAGERS, ['note']),
    _action('request_changes', 'Request changes', [Status.IN_REVIEW], MANAGERS, ['reason']),
    _action('start', 'Start rollout', [Status.APPROVED], MANAGERS),
    _action('mark_released', 'Mark released', [Status.IN_PROGRESS], MANAGERS, ['note']),
    _action('block', 'Mark blocked', [Status.IN_REVIEW, Status.APPROVED, Status.IN_PROGRESS], EVERYONE, ['reason']),
    _action('unblock', 'Unblock', [Status.BLOCKED], MANAGERS, ['note']),
    _action('cancel', 'Cancel release', [Status.DRAFT, Status.IN_REVIEW, Status.APPROVED, Status.BLOCKED], MANAGERS,
            ['reason']),
    _action('reopen', 'Reopen', [Status.RELEASED, Status.CANCELLED], MANAGERS, ['reason']),
]:
    ACTIONS[_definition.name] = _definition


def pending_sign_offs(release):
    """Changed components still waiting for a sign-off, in name order."""
    signed = set()
    for sign_off in release.sign_offs.all():
        signed.add(sign_off.component_id)
    waiting = []
    for change in release.changes.all():
        if change.component_id not in signed:
            waiting.append(change.component)
    waiting.sort(key=str)
    return waiting


def components_to_sign(release, user, role):
    """Components `user` can sign off now: the ones they own, plus unowned ones for managers."""
    mine = []
    for component in pending_sign_offs(release):
        if component.owner_id == user.pk or (component.owner_id is None and role in MANAGERS):
            mine.append(component)
    return mine


def approval_blockers(release):
    """Why the release can't be approved yet, as sentences; empty when nothing stands in the way."""
    problems = []
    cycle = plan_for(release)['cycle']
    if cycle:
        problems.append('These components depend on each other in a cycle: ' + ' → '.join(cycle)
                        + '. Break the cycle before approving.')
    waiting = []
    for component in pending_sign_offs(release):
        who = component.owner.display_name if component.owner_id else 'a release manager'
        waiting.append(f'{component.name} ({who})')
    if waiting:
        problems.append('Waiting for sign-off on ' + ', '.join(waiting) + '.')
    return problems


def _extra_rule(release, user, action, role):
    """Rules beyond status and role. Returns an error message, or None when allowed."""
    if action.name == 'submit':
        if len(release.changes.all()) == 0:
            return 'Add at least one component change before submitting.'
        if role == Role.ENGINEER and release.created_by_id != user.pk:
            return 'Engineers can only submit releases they created.'
    if action.name == 'sign_off' and not components_to_sign(release, user, role):
        return 'Nothing in this release is waiting for your sign-off.'
    if action.name == 'approve':
        problems = approval_blockers(release)
        if problems:
            return ' '.join(problems)
    return None


def check(release, user, action_name):
    """Raise unless `user` may perform `action_name` on `release` right now; returns (action, role)."""
    action = ACTIONS.get(action_name)
    if action is None:
        raise WorkflowError(f'Unknown action "{action_name}".')
    role = relationship(release, user)
    if role not in action.roles:
        raise WorkflowError(f'You can\'t use "{action.label}" on this release.', http.HTTP_403_FORBIDDEN)
    if release.status not in action.sources:
        raise TransitionNotAllowed(f'A release that is {release.get_status_display().lower()} can\'t be '
                                   f'changed with "{action.label}".')
    problem = _extra_rule(release, user, action, role)
    if problem:
        raise TransitionNotAllowed(problem)
    return action, role


def allowed_actions(release, user):
    """The actions `user` can take on `release` now, with the payload fields each one needs."""
    allowed = []
    for action in ACTIONS.values():
        try:
            check(release, user, action.name)
        except WorkflowError:
            continue
        allowed.append({'name': action.name, 'label': action.label, 'fields': list(action.fields)})
    return allowed


def _text(data, name, required=False, label=None):
    value = str(data.get(name) or '').strip()
    if required and not value:
        raise WorkflowError(f'{label or name.replace("_", " ").capitalize()} is required.')
    return value


@transaction.atomic
def perform(release, user, action_name, data=None):
    """Run an action on a release, recording it in the timeline. Returns the updated release."""
    data = data or {}
    action, role = check(release, user, action_name)
    before = release.status
    kind, message = HANDLERS[action.name](release, user, role, data)
    release.save()
    record_event(release, user, kind, from_status=before, to_status=release.status, message=message)
    return release


def _clear_sign_offs(release):
    release.sign_offs.all().delete()
    getattr(release, '_prefetched_objects_cache', {}).pop('sign_offs', None)


def _submit(release, user, role, data):
    release.status = Status.IN_REVIEW
    release.submitted_at = timezone.now()
    return Kind.SUBMITTED, _text(data, 'note')


def _sign_off(release, user, role, data):
    note = _text(data, 'note')
    names = []
    for component in components_to_sign(release, user, role):
        SignOff.objects.create(release=release, component=component, user=user, note=note)
        names.append(component.name)
    getattr(release, '_prefetched_objects_cache', {}).pop('sign_offs', None)
    return Kind.SIGNED_OFF, f'Signed off {", ".join(names)}. {note}'.strip()


def _approve(release, user, role, data):
    release.status = Status.APPROVED
    release.approved_at = timezone.now()
    return Kind.APPROVED, _text(data, 'note')


def _request_changes(release, user, role, data):
    reason = _text(data, 'reason', required=True, label='A reason')
    _clear_sign_offs(release)
    release.status = Status.DRAFT
    release.submitted_at = None
    return Kind.CHANGES_REQUESTED, reason


def _start(release, user, role, data):
    release.status = Status.IN_PROGRESS
    release.started_at = timezone.now()
    plan = plan_for(release)
    if plan['waves']:
        return Kind.STARTED, f'Deploying in {len(plan["waves"])} wave{"s" if len(plan["waves"]) != 1 else ""}.'
    return Kind.STARTED, ''


def _mark_released(release, user, role, data):
    release.status = Status.RELEASED
    release.released_at = timezone.now()
    return Kind.RELEASED, _text(data, 'note')


def _block(release, user, role, data):
    reason = _text(data, 'reason', required=True, label='A reason')
    release.blocked_from = release.status
    release.blocked_reason = reason
    release.status = Status.BLOCKED
    return Kind.BLOCKED, reason


def _unblock(release, user, role, data):
    release.status = release.blocked_from or Status.IN_REVIEW
    release.blocked_from = ''
    release.blocked_reason = ''
    return Kind.UNBLOCKED, _text(data, 'note')


def _cancel(release, user, role, data):
    reason = _text(data, 'reason', required=True, label='A reason')
    release.status = Status.CANCELLED
    release.closed_at = timezone.now()
    release.blocked_from = ''
    return Kind.CANCELLED, reason


def _reopen(release, user, role, data):
    reason = _text(data, 'reason', required=True, label='A reason')
    _clear_sign_offs(release)
    forget_plan(release)
    release.reopen_count += 1
    release.status = Status.DRAFT
    release.submitted_at = release.approved_at = release.started_at = None
    release.released_at = release.closed_at = None
    release.blocked_from = release.blocked_reason = ''
    return Kind.REOPENED, reason


HANDLERS = {
    'submit': _submit, 'sign_off': _sign_off, 'approve': _approve, 'request_changes': _request_changes,
    'start': _start, 'mark_released': _mark_released, 'block': _block, 'unblock': _unblock, 'cancel': _cancel,
    'reopen': _reopen,
}
assert set(HANDLERS) == set(ACTIONS), 'every action needs a handler'
