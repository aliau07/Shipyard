"""Builders shared by every app's tests (test code may import across apps)."""
import itertools

from apps.accounts.models import User
from apps.projects import services
from apps.projects.models import Component, Dependency, Membership
from apps.releases import services as release_services
from apps.releases import workflow

_counter = itertools.count(1)
PASSWORD = 'correct-horse-battery-staple'


def make_user(username=None, **extra):
    username = username or f'user{next(_counter)}'
    extra.setdefault('email', f'{username}@example.com')
    extra.setdefault('first_name', username.title())
    return User.objects.create_user(username, password=PASSWORD, **extra)


def make_project(owner, name=None):
    return services.create_project(owner, name=name or f'Project {next(_counter)}')


def add_member(project, user, role='engineer'):
    return Membership.objects.create(project=project, user=user, role=role)


def make_component(project, name, owner=None, kind='service', deploy_minutes=10, **extra):
    return Component.objects.create(project=project, name=name, owner=owner, kind=kind, deploy_minutes=deploy_minutes,
                                    **extra)


def depend(component, *targets):
    for target in targets:
        Dependency.objects.create(component=component, depends_on=target)


class Team:
    """A project with an owner, a release manager, two engineers and five components:

        web (frontend, ada, 8 min) -> api (service, li, 15 min) -> models (library, li, 5 min)
        web -> ui (library, ada, 4 min)
        worker (service, no owner, 12 min) -> models

    `outsider` has an account but is not in the project.
    """

    def __init__(self):
        self.owner = make_user()
        self.manager = make_user()
        self.li = make_user()
        self.ada = make_user()
        self.outsider = make_user()
        self.project = make_project(self.owner)
        add_member(self.project, self.manager, 'release_manager')
        add_member(self.project, self.li, 'engineer')
        add_member(self.project, self.ada, 'engineer')
        self.models = make_component(self.project, 'models', self.li, 'library', 5, package_name='acme-models')
        self.ui = make_component(self.project, 'ui', self.ada, 'library', 4, package_name='@acme/ui')
        self.api = make_component(self.project, 'api', self.li, 'service', 15)
        self.web = make_component(self.project, 'web', self.ada, 'frontend', 8)
        self.worker = make_component(self.project, 'worker', None, 'service', 12)
        depend(self.api, self.models)
        depend(self.web, self.api, self.ui)
        depend(self.worker, self.models)

    def release(self, *components, author=None, version=None, title='Release'):
        changes = []
        for component in components:
            changes.append({'component': component, 'summary': f'Update {component.name}'})
        return release_services.create_release(author or self.manager, project=self.project, title=title,
                                               version=version or f'1.{next(_counter)}.0', changes=changes)

    def sign_all(self, release):
        for person in (self.li, self.ada, self.manager):
            try:
                workflow.perform(release, person, 'sign_off')
            except workflow.WorkflowError:
                pass

    def advance(self, release, status):
        """Walk a release through the workflow to `status`."""
        if status == 'cancelled':
            return workflow.perform(release, self.manager, 'cancel', {'reason': 'Not needed'})
        workflow.perform(release, self.manager, 'submit')
        if status == 'in_review':
            return release
        if status == 'blocked':
            return workflow.perform(release, self.manager, 'block', {'reason': 'Waiting for QA'})
        self.sign_all(release)
        workflow.perform(release, self.manager, 'approve')
        if status == 'approved':
            return release
        workflow.perform(release, self.manager, 'start')
        if status == 'in_progress':
            return release
        return workflow.perform(release, self.manager, 'mark_released')
