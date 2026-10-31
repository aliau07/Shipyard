"""Who can see which releases: members of the release's project. Everyone else gets 404s."""
from apps.projects.scoping import role_in

from .models import Release


def releases_for(user):
    return Release.objects.filter(project__memberships__user=user)


def relationship(release, user):
    """`user`'s role in the release's project: 'owner', 'release_manager', 'engineer' or None."""
    return role_in(release.project, user)
