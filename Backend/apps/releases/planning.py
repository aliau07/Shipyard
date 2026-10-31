"""The deploy plan of a release: its changed components ordered by the project's dependency graph."""
from apps.projects.services import graph_payload, load_graph


def plan_for(release):
    """Waves, order, critical path, cycle and impact for the release's changes (cached on the instance).

    Uses the release's `changes` (prefetch them with their components) plus two queries for the project graph.
    """
    cached = release.__dict__.get('_plan')
    if cached is not None:
        return cached
    components, project_graph = load_graph(release.project_id)
    changes = {}
    for change in release.changes.all():
        changes[change.component.name] = change
    plan = graph_payload(components, project_graph, changed=list(changes))
    for node in plan['nodes']:
        change = changes[node['name']]
        node['change_type'] = change.change_type
        node['summary'] = change.summary
    affected = set()
    for name in plan['impact']:
        for entry in plan['impact'][name]:
            if not entry['in_view']:
                affected.add(entry['name'])
    plan['unchanged_dependents'] = sorted(affected)
    release.__dict__['_plan'] = plan
    return plan


def forget_plan(release):
    release.__dict__.pop('_plan', None)
