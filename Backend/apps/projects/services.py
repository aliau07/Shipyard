"""Projects, members, components and dependencies, plus the graph data the planner works on."""
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from rest_framework import status as http

from apps.accounts.models import User
from apps.core.exceptions import DomainError

from . import graph, manifests
from .models import MANAGER_ROLES, Component, Dependency, Membership, Project
from .scoping import require_role, role_in

Role = Membership.Role


class ProjectError(DomainError):
    pass


@transaction.atomic
def create_project(user, *, name, description=''):
    """Start a project; its creator becomes the owner."""
    project = Project.objects.create(name=name, description=description, created_by=user)
    Membership.objects.create(project=project, user=user, role=Role.OWNER)
    return project


def update_project(project, user, changes):
    require_role(project, user, MANAGER_ROLES, 'Only owners and release managers can edit the project.')
    for field in ('name', 'description'):
        if field in changes:
            setattr(project, field, changes[field])
    project.save()
    return project


def delete_project(project, user):
    require_role(project, user, [Role.OWNER], 'Only project owners can delete a project.')
    project.delete()


def add_member(project, actor, identifier, role):
    """Add an existing account, found by username or email, to the project."""
    require_role(project, actor, [Role.OWNER], 'Only project owners can add people.')
    identifier = (identifier or '').strip()
    user = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
    if user is None:
        raise ProjectError(f'No account found for "{identifier}". Ask them to sign up first.')
    if Membership.objects.filter(project=project, user=user).exists():
        raise ProjectError(f'{user.display_name} is already in this project.')
    return Membership.objects.create(project=project, user=user, role=role)


def _owner_count(project):
    return Membership.objects.filter(project=project, role=Role.OWNER).count()


def change_role(membership, actor, role):
    require_role(membership.project, actor, [Role.OWNER], 'Only project owners can change roles.')
    if membership.role == Role.OWNER and role != Role.OWNER and _owner_count(membership.project) == 1:
        raise ProjectError('A project needs at least one owner.', http.HTTP_409_CONFLICT)
    membership.role = role
    membership.save(update_fields=['role'])
    return membership


@transaction.atomic
def remove_member(membership, actor):
    """Owners remove anyone; everyone else may leave. Components they owned become unowned."""
    if membership.user_id != actor.pk:
        require_role(membership.project, actor, [Role.OWNER], 'Only project owners can remove people.')
    if membership.role == Role.OWNER and _owner_count(membership.project) == 1:
        raise ProjectError('A project needs at least one owner.', http.HTTP_409_CONFLICT)
    Component.objects.filter(project=membership.project, owner=membership.user).update(owner=None)
    membership.delete()


def _check_owner(project, owner):
    if owner is not None and not Membership.objects.filter(project=project, user=owner).exists():
        raise ProjectError('The component owner must be a member of the project.')


def create_component(project, user, **fields):
    require_role(project, user, MANAGER_ROLES, 'Only owners and release managers can add components.')
    if Component.objects.filter(project=project, name=fields['name']).exists():
        raise ProjectError(f'There is already a component called "{fields["name"]}".')
    _check_owner(project, fields.get('owner'))
    return Component.objects.create(project=project, **fields)


def update_component(component, user, changes):
    """Managers edit any component; a component's owner may edit its details but not hand it over."""
    role = role_in(component.project, user)
    if role not in MANAGER_ROLES:
        if component.owner_id != user.pk:
            raise ProjectError('Only owners, release managers and the component owner can edit it.', http.HTTP_403_FORBIDDEN)
        if 'owner' in changes and changes['owner'] != component.owner:
            raise ProjectError('Only owners and release managers can change who owns a component.', http.HTTP_403_FORBIDDEN)
    if 'name' in changes and Component.objects.filter(project=component.project, name=changes['name']).exclude(
            pk=component.pk).exists():
        raise ProjectError(f'There is already a component called "{changes["name"]}".')
    if 'owner' in changes:
        _check_owner(component.project, changes['owner'])
    for field, value in changes.items():
        setattr(component, field, value)
    component.save()
    return component


def delete_component(component, user):
    require_role(component.project, user, MANAGER_ROLES, 'Only owners and release managers can delete components.')
    component.delete()


def can_edit_dependencies(component, user):
    return role_in(component.project, user) in MANAGER_ROLES or component.owner_id == user.pk


def load_graph(project_id):
    """(components in name order, graph) for one project, in two queries."""
    components = list(Component.objects.filter(project_id=project_id).select_related('owner').order_by('name'))
    pairs = Dependency.objects.filter(component__project_id=project_id).values_list('component__name', 'depends_on__name')
    names = []
    for component in components:
        names.append(component.name)
    return components, graph.build_graph(names, pairs)


def cycle_closed_by(project_graph, name, targets):
    """The first cycle that edges name -> target close, as a path starting at `name`, or None.

    An edge closes a cycle when the target already depends on `name`, directly or indirectly.
    """
    reached = {}
    for hit in graph.impact(project_graph, name):
        reached[hit['node']] = hit['path']
    for target in sorted(targets):
        if target in reached:
            return [name] + reached[target][::-1]
    return None


def add_dependency(user, component, depends_on, source=Dependency.Source.MANUAL):
    """Record that `component` depends on `depends_on`. Returns (dependency, cycle path or None).

    Cycles are allowed so the graph can show reality, but they are reported, and a release whose components
    form a cycle can't be approved.
    """
    if not can_edit_dependencies(component, user):
        raise ProjectError('Only owners, release managers and the component owner can change its dependencies.',
                           http.HTTP_403_FORBIDDEN)
    if component.project_id != depends_on.project_id:
        raise ProjectError('Both components must belong to the same project.')
    if component.pk == depends_on.pk:
        raise ProjectError('A component can\'t depend on itself.')
    if Dependency.objects.filter(component=component, depends_on=depends_on).exists():
        raise ProjectError(f'{component.name} already depends on {depends_on.name}.')
    dependency = Dependency.objects.create(component=component, depends_on=depends_on, source=source, created_by=user)
    _, project_graph = load_graph(component.project_id)
    return dependency, cycle_closed_by(project_graph, component.name, [depends_on.name])


def remove_dependency(dependency, user):
    if not can_edit_dependencies(dependency.component, user):
        raise ProjectError('Only owners, release managers and the component owner can change its dependencies.',
                           http.HTTP_403_FORBIDDEN)
    dependency.delete()


@transaction.atomic
def import_manifest(component, user, uploaded_file):
    """Create dependencies from a requirements.txt or package.json upload.

    Returns the format, how many packages were read, which components were linked now or already, and which
    packages match no component in the project.
    """
    if not can_edit_dependencies(component, user):
        raise ProjectError('Only owners, release managers and the component owner can change its dependencies.',
                           http.HTTP_403_FORBIDDEN)
    limit = settings.MAX_MANIFEST_SIZE_KB * 1024
    if uploaded_file.size > limit:
        raise ProjectError(f'"{uploaded_file.name}" is larger than {settings.MAX_MANIFEST_SIZE_KB} KB.')
    try:
        manifest_format, packages = manifests.parse_manifest(uploaded_file.name, uploaded_file.read(), limit)
    except manifests.ManifestError as error:
        raise ProjectError(str(error))

    others = {}
    by_name = {}
    for other in Component.objects.filter(project=component.project_id).exclude(pk=component.pk):
        others[other.name] = [other.name, other.package_name]
        by_name[other.name] = other
    own_names = set()
    for alias in (component.name, component.package_name):
        if alias:
            own_names.add(manifests.normalize_name(alias))
    wanted = []
    for package in packages:
        if manifests.normalize_name(package) not in own_names:
            wanted.append(package)
    matched, unmatched = manifests.match_packages(wanted, others)

    existing_ids = set(Dependency.objects.filter(component=component).values_list('depends_on_id', flat=True))
    created, existing = [], []
    for target_name in sorted(set(matched.values())):
        target = by_name[target_name]
        if target.pk in existing_ids:
            existing.append(target_name)
            continue
        Dependency.objects.create(component=component, depends_on=target, source=Dependency.Source.MANIFEST,
                                  created_by=user)
        created.append(target_name)

    _, project_graph = load_graph(component.project_id)
    return {
        'format': manifest_format,
        'packages': len(packages),
        'created': created,
        'existing': existing,
        'unmatched': unmatched,
        'cycle': cycle_closed_by(project_graph, component.name, created),
    }


def graph_payload(components, project_graph, changed=None):
    """Nodes, edges, wave layout, cycle and impact paths, in the shape the React graph view draws.

    With `changed` (a release), the graph is contracted to those components; impact is always computed on the
    full project graph so it lists every dependent.
    """
    by_name = {}
    for component in components:
        by_name[component.name] = component
    shown = graph.contract(project_graph, changed) if changed is not None else project_graph
    waves, blocked = graph.layers(shown)
    cycle = graph.find_cycle(shown) if blocked else None
    layout = list(waves)
    if blocked:
        layout.append(blocked)
    layer_of = {}
    for index, layer in enumerate(layout):
        for name in layer:
            layer_of[name] = index
    on_cycle = set(cycle or [])

    nodes = []
    for name in sorted(shown):
        component = by_name[name]
        nodes.append({
            'id': component.pk, 'name': name, 'kind': component.kind, 'deploy_minutes': component.deploy_minutes,
            'owner': component.owner_id, 'owner_name': component.owner.display_name if component.owner_id else None,
            'layer': layer_of[name], 'wave': None if name in blocked else layer_of[name] + 1,
            'in_cycle': name in on_cycle,
        })
    edges = []
    for dependent in shown:
        for dependency in shown[dependent]:
            edges.append({'from': dependent, 'to': dependency})

    critical = None
    order = None
    estimated = None
    if not blocked:
        weights = {}
        for name in shown:
            weights[name] = by_name[name].deploy_minutes
        total, path = graph.critical_path(shown, weights)
        critical = {'minutes': total, 'path': path}
        order = graph.topological_order(shown)
        estimated = 0
        for wave in waves:
            longest = 0
            for name in wave:
                longest = max(longest, weights[name])
            estimated += longest

    impact = {}
    for name in sorted(shown):
        entries = []
        for hit in graph.impact(project_graph, name):
            entries.append({'name': hit['node'], 'depth': hit['depth'], 'path': hit['path'],
                            'in_view': hit['node'] in shown})
        impact[name] = entries

    return {
        'nodes': nodes, 'edges': edges, 'layers': layout, 'waves': None if blocked else waves,
        'blocked': blocked, 'cycle': cycle, 'order': order, 'critical_path': critical,
        'estimated_minutes': estimated, 'impact': impact,
    }


def project_graph(project):
    components, project_graph_data = load_graph(project.pk)
    return graph_payload(components, project_graph_data)
