"""Who can see which projects. Non-members get 404s because these querysets leave the rows out."""
from rest_framework import status as http

from apps.core.exceptions import DomainError

from .models import MANAGER_ROLES, Component, Dependency, Membership, Project


def projects_for(user):
    return Project.objects.filter(memberships__user=user)


def components_for(user):
    return Component.objects.filter(project__memberships__user=user)


def dependencies_for(user):
    return Dependency.objects.filter(component__project__memberships__user=user)


def role_in(project, user):
    """`user`'s role in `project` ('owner', 'release_manager', 'engineer') or None; cached on the project."""
    cache = getattr(project, '_role_cache', None)
    if cache is None:
        cache = {}
        project._role_cache = cache
    if user.pk not in cache:
        cache[user.pk] = Membership.objects.filter(project=project, user=user).values_list('role', flat=True).first()
    return cache[user.pk]


def is_manager(project, user):
    return role_in(project, user) in MANAGER_ROLES


def require_role(project, user, roles, message):
    """Return the user's role, or raise a 403 DomainError when it isn't one of `roles`."""
    role = role_in(project, user)
    if role not in roles:
        raise DomainError(message, http.HTTP_403_FORBIDDEN)
    return role
