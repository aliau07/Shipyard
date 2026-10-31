"""Who hears about what. Recipients depend on the kind of event; nobody is told about their own action, and only
people still in the project are told anything."""
from django.db import transaction
from django.utils import timezone

from apps.core.emails import send_email
from apps.projects.models import MANAGER_ROLES, Membership
from apps.releases.models import ReleaseEvent

from .models import Notification

Kind = ReleaseEvent.Kind

AUDIENCE = {
    Kind.CREATED: {'managers'},
    Kind.SUBMITTED: {'component_owners', 'managers'},
    Kind.SIGNED_OFF: {'author', 'managers'},
    Kind.CHANGES_REQUESTED: {'author', 'component_owners'},
    Kind.APPROVED: {'author', 'component_owners'},
    Kind.STARTED: {'author', 'component_owners'},
    Kind.RELEASED: {'author', 'component_owners', 'managers'},
    Kind.BLOCKED: {'author', 'component_owners', 'managers'},
    Kind.UNBLOCKED: {'author', 'component_owners'},
    Kind.CANCELLED: {'author', 'component_owners'},
    Kind.REOPENED: {'author', 'managers'},
    Kind.COMMENTED: {'author', 'component_owners', 'managers'},
    Kind.UPDATED: set(),
    Kind.CHANGE_ADDED: set(),
    Kind.CHANGE_REMOVED: set(),
}

DETAILED_KINDS = (Kind.COMMENTED, Kind.BLOCKED, Kind.CHANGES_REQUESTED, Kind.CANCELLED, Kind.REOPENED, Kind.SIGNED_OFF)


def recipients(event):
    release = event.release
    audience = AUDIENCE.get(event.kind, set())
    members = {}
    for membership in Membership.objects.filter(project_id=release.project_id).select_related('user'):
        members[membership.user_id] = membership
    people = []
    if 'author' in audience and release.created_by_id:
        people.append(release.created_by_id)
    if 'component_owners' in audience:
        for owner_id in release.changes.values_list('component__owner_id', flat=True):
            if owner_id:
                people.append(owner_id)
    if 'managers' in audience:
        for membership in members.values():
            if membership.role in MANAGER_ROLES:
                people.append(membership.user_id)
    found = {}
    for user_id in people:
        membership = members.get(user_id)
        if membership is None or user_id == event.actor_id or not membership.user.is_active:
            continue
        found[user_id] = membership.user
    result = []
    for user_id in sorted(found):
        result.append(found[user_id])
    return result


def describe(event):
    release = event.release
    who = event.actor.display_name if event.actor_id else 'Shipyard'
    text = f'{release.reference} {release.title} ({release.version}): {event.get_kind_display()} by {who}'
    if event.message and event.kind in DETAILED_KINDS:
        text += f': {event.message}'
    return text[:297] + '...' if len(text) > 300 else text


@transaction.atomic
def notify_about(event):
    """Create in-app notifications (and send emails) for an event. Returns the notifications."""
    message = describe(event)
    created = []
    for person in recipients(event):
        created.append(Notification.objects.create(recipient=person, release=event.release, event=event, message=message))
        send_email(person, f'{event.release.reference}: {event.get_kind_display()}', 'notifications/email.txt',
                   {'event': event, 'release': event.release, 'message': message})
    return created


def unread(user):
    return Notification.objects.filter(recipient=user, read_at__isnull=True)


def mark_all_read(user):
    return unread(user).update(read_at=timezone.now())
