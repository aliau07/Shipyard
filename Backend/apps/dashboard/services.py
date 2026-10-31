"""Read-only figures for the dashboard, across all your projects or for one of them."""
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from apps.projects import graph
from apps.projects.models import Component, Dependency
from apps.projects.scoping import projects_for
from apps.releases.models import OPEN_STATUSES, ReleaseChange, Status
from apps.releases.scoping import releases_for

RECENT_DAYS = 30
TOP_COMPONENTS = 5


def _compact(release):
    return {
        'id': release.id, 'reference': release.reference, 'title': release.title, 'version': release.version,
        'status': release.status, 'status_display': release.get_status_display(), 'project': release.project_id,
        'project_name': release.project.name, 'target_date': release.target_date,
        'blocked_reason': release.blocked_reason, 'updated_at': release.updated_at,
    }


def average_waves(releases):
    """How many deploy waves releases need on average.

    Cancelled releases and releases without changes don't count. Releases whose components form a cycle have no
    waves; they are counted under `with_cycles` instead. Two queries, whatever the number of releases.
    """
    changed = {}
    project_ids = set()
    rows = (ReleaseChange.objects.filter(release__in=releases).exclude(release__status=Status.CANCELLED)
            .values_list('release_id', 'release__project_id', 'component__name'))
    for release_id, project_id, name in rows:
        changed.setdefault(release_id, (project_id, []))[1].append(name)
        project_ids.add(project_id)
    graphs = {}
    pairs = (Dependency.objects.filter(component__project_id__in=project_ids)
             .values_list('component__project_id', 'component__name', 'depends_on__name'))
    for project_id, dependent, dependency in pairs:
        graphs.setdefault(project_id, {}).setdefault(dependent, []).append(dependency)

    total = counted = with_cycles = 0
    for release_id in sorted(changed):
        project_id, names = changed[release_id]
        waves, blocked = graph.layers(graph.contract(graphs.get(project_id, {}), names))
        if blocked:
            with_cycles += 1
            continue
        total += len(waves)
        counted += 1
    return {'average': round(total / counted, 1) if counted else None, 'releases': counted, 'with_cycles': with_cycles}


def most_depended_on(projects, limit=TOP_COMPONENTS):
    components = (Component.objects.filter(project__in=projects).select_related('project', 'owner')
                  .annotate(dependent_count=Count('dependents')).filter(dependent_count__gt=0)
                  .order_by('-dependent_count', 'name', 'pk')[:limit])
    rows = []
    for component in components:
        rows.append({
            'id': component.id, 'name': component.name, 'kind': component.kind, 'project': component.project_id,
            'project_name': component.project.name, 'dependents': component.dependent_count,
            'owner_name': component.owner.display_name if component.owner_id else None,
        })
    return rows


def dashboard_for(user, project=None):
    releases = releases_for(user)
    projects = projects_for(user)
    if project is not None:
        releases = releases.filter(project=project)
        projects = projects.filter(pk=project.pk)
    counts = {}
    for status, count in releases.order_by().values_list('status').annotate(n=Count('pk')).values_list('status', 'n'):
        counts[status] = count
    by_status = []
    for value, label in Status.choices:
        by_status.append({'key': value, 'label': label, 'count': counts.get(value, 0)})
    open_count = 0
    for status in OPEN_STATUSES:
        open_count += counts.get(status, 0)

    blocked = []
    for release in releases.filter(status=Status.BLOCKED).select_related('project').order_by('-updated_at')[:10]:
        blocked.append(_compact(release))
    upcoming = []
    soon = releases.filter(status__in=OPEN_STATUSES, target_date__isnull=False).exclude(status=Status.BLOCKED)
    for release in soon.select_related('project').order_by('target_date', 'pk')[:5]:
        upcoming.append(_compact(release))

    since = timezone.now() - timedelta(days=RECENT_DAYS)
    return {
        'project': project.pk if project else None,
        'summary': {
            'projects': projects.count(),
            'releases': sum(counts.values()),
            'open': open_count,
            'in_review': counts.get(Status.IN_REVIEW, 0),
            'blocked': counts.get(Status.BLOCKED, 0),
            'released_recently': releases.filter(released_at__gte=since).count(),
            'recent_days': RECENT_DAYS,
        },
        'by_status': by_status,
        'blocked_releases': blocked,
        'upcoming_releases': upcoming,
        'most_depended_on': most_depended_on(projects),
        'waves': average_waves(releases),
    }
