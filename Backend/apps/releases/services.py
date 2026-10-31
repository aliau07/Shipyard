"""Release creation, edits, changes, comments and the event log. The workflow lives in workflow.py."""
from functools import partial

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status as http

from apps.core.exceptions import DomainError
from apps.core.images import process_upload
from apps.projects.models import MANAGER_ROLES
from apps.projects.scoping import role_in

from .models import Comment, Release, ReleaseChange, ReleaseEvent, Screenshot, Status
from .signals import release_event_recorded

Kind = ReleaseEvent.Kind


class ReleaseError(DomainError):
    pass


def record_event(release, actor, kind, *, from_status='', to_status='', message=''):
    """Add a timeline entry and announce it (after commit) for notifications."""
    event = ReleaseEvent.objects.create(release=release, actor=actor, kind=kind, from_status=from_status,
                                        to_status=to_status, message=message)
    transaction.on_commit(partial(release_event_recorded.send, sender=ReleaseEvent, event=event))
    return event


def _check_version(project, version, exclude=None):
    clash = Release.objects.filter(project=project, version=version)
    if exclude is not None:
        clash = clash.exclude(pk=exclude.pk)
    if clash.exists():
        raise ReleaseError(f'{project.name} already has a release with version {version}.')


def _check_component(release, component):
    if component.project_id != release.project_id:
        raise ReleaseError(f'{component.name} belongs to a different project.')
    for change in release.changes.all():
        if change.component_id == component.pk:
            raise ReleaseError(f'{component.name} is already in this release.')


@transaction.atomic
def create_release(user, *, project, title, version, description='', target_date=None, changes=()):
    """Any member can draft a release, optionally with its first component changes."""
    if role_in(project, user) is None:
        raise ReleaseError('Choose one of your projects.')
    _check_version(project, version)
    release = Release.objects.create(project=project, title=title, version=version, description=description,
                                     target_date=target_date, created_by=user)
    record_event(release, user, Kind.CREATED, to_status=release.status, message=description[:280])
    for change in changes:
        _add_change(release, user, change['component'], change['summary'], change.get('change_type'))
    return release


def _can_edit(release, user, role):
    return role in MANAGER_ROLES or release.created_by_id == user.pk


def _require_draft(release, what):
    if release.status != Status.DRAFT:
        raise ReleaseError(f'{what} only while the release is a draft. Request changes or reopen it first.',
                           http.HTTP_409_CONFLICT)


EDITABLE_FIELDS = ('title', 'version', 'description', 'target_date')


def update_release(release, user, role, changes):
    """Owners, release managers and the author edit the details of a draft."""
    if not _can_edit(release, user, role):
        raise ReleaseError('Only owners, release managers and the author can edit this release.', http.HTTP_403_FORBIDDEN)
    _require_draft(release, 'Details can be edited')
    if 'version' in changes:
        _check_version(release.project, changes['version'], exclude=release)
    changed = []
    for name in EDITABLE_FIELDS:
        if name in changes and getattr(release, name) != changes[name]:
            setattr(release, name, changes[name])
            changed.append(name.replace('_', ' '))
    if changed:
        release.save()
        record_event(release, user, Kind.UPDATED, message='Updated ' + ', '.join(changed))
    return release


def _add_change(release, user, component, summary, change_type=None):
    _check_component(release, component)
    summary = (summary or '').strip()
    if not summary:
        raise ReleaseError(f'Describe what changes in {component.name}.')
    change = ReleaseChange.objects.create(release=release, component=component, summary=summary, added_by=user,
                                          change_type=change_type or ReleaseChange.ChangeType.FEATURE)
    getattr(release, '_prefetched_objects_cache', {}).pop('changes', None)
    release.__dict__.pop('_plan', None)
    record_event(release, user, Kind.CHANGE_ADDED, message=f'{component.name}: {summary}')
    return change


@transaction.atomic
def add_change(release, user, role, component, summary, change_type=None):
    """Add a component change to a draft: managers, the author, or the component's owner."""
    if not (_can_edit(release, user, role) or component.owner_id == user.pk):
        raise ReleaseError('Only owners, release managers, the author and the component owner can add it.',
                           http.HTTP_403_FORBIDDEN)
    _require_draft(release, 'Changes can be added')
    return _add_change(release, user, component, summary, change_type)


@transaction.atomic
def remove_change(change, user, role):
    release = change.release
    if not (_can_edit(release, user, role) or change.added_by_id == user.pk):
        raise ReleaseError('Only owners, release managers, the author and whoever added it can remove a change.',
                           http.HTTP_403_FORBIDDEN)
    _require_draft(release, 'Changes can be removed')
    name = change.component.name
    change.delete()
    record_event(release, user, Kind.CHANGE_REMOVED, message=name)


@transaction.atomic
def add_comment(release, user, body, images=()):
    """Comment on a release in any state, optionally with screenshots (re-encoded, metadata removed)."""
    body = (body or '').strip()
    if not body:
        raise ReleaseError('Write a comment first.')
    limit = settings.MAX_SCREENSHOTS_PER_COMMENT
    if len(images) > limit:
        raise ReleaseError(f'A comment can have up to {limit} screenshots.')
    comment = Comment.objects.create(release=release, author=user, body=body)
    for upload in images:
        image, thumbnail = process_upload(upload)
        screenshot = Screenshot(comment=comment)
        screenshot.image.save(image.name, image, save=False)
        screenshot.thumbnail.save(thumbnail.name, thumbnail, save=False)
        screenshot.save()
    Release.objects.filter(pk=release.pk).update(updated_at=timezone.now())
    count = len(images)
    suffix = f' ({count} screenshot{"s" if count != 1 else ""})' if count else ''
    record_event(release, user, Kind.COMMENTED, message=body[:280] + suffix)
    return comment
