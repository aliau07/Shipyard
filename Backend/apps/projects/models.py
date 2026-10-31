from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

component_name_validator = RegexValidator(
    r'^[a-z0-9][a-z0-9._-]*$', 'Use lowercase letters, digits, dots, dashes and underscores, starting with a letter or digit.'
)


class Project(models.Model):
    """A product or system whose components are released together."""

    name        = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_by  = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='+')
    created_at  = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['name', 'pk']

    def __str__(self):
        return self.name


class Membership(models.Model):
    """A person's role in one project. Owners manage people; owners and release managers run releases."""

    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        RELEASE_MANAGER = 'release_manager', 'Release manager'
        ENGINEER = 'engineer', 'Engineer'

    project    = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    role       = models.CharField(max_length=16, choices=Role.choices, default=Role.ENGINEER)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['project', 'role', 'pk']
        constraints = [models.UniqueConstraint(fields=['project', 'user'], name='one_membership_per_user_and_project')]

    def __str__(self):
        return f'{self.user} is {self.get_role_display()} of {self.project}'


MANAGER_ROLES = (Membership.Role.OWNER, Membership.Role.RELEASE_MANAGER)


class Component(models.Model):
    """Something that is built and deployed on its own: a service, a library or a frontend."""

    class Kind(models.TextChoices):
        SERVICE = 'service', 'Service'
        LIBRARY = 'library', 'Library'
        FRONTEND = 'frontend', 'Frontend'

    project        = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='components')
    name           = models.CharField(max_length=80, validators=[component_name_validator])
    kind           = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SERVICE)
    owner          = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name='owned_components')
    package_name   = models.CharField(max_length=214, blank=True,
                                      help_text='Name in requirements.txt or package.json, if not the component name.')
    deploy_minutes = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1), MaxValueValidator(1440)],
                                                 help_text='Estimated time to deploy and verify.')
    description    = models.CharField(max_length=500, blank=True)
    repository_url = models.URLField(blank=True)
    created_at     = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['name', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['project', 'name'], name='unique_component_name_per_project'),
            models.CheckConstraint(condition=Q(deploy_minutes__gte=1, deploy_minutes__lte=1440),
                                   name='component_deploy_minutes_in_range'),
        ]

    def __str__(self):
        return self.name


class Dependency(models.Model):
    """`component` depends on `depends_on`, so `depends_on` has to be deployed first."""

    class Source(models.TextChoices):
        MANUAL = 'manual', 'Added by hand'
        MANIFEST = 'manifest', 'Imported from a manifest'

    component  = models.ForeignKey(Component, on_delete=models.CASCADE, related_name='dependencies')
    depends_on = models.ForeignKey(Component, on_delete=models.CASCADE, related_name='dependents')
    source     = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['component__name', 'depends_on__name']
        verbose_name_plural = 'dependencies'
        constraints = [
            models.UniqueConstraint(fields=['component', 'depends_on'], name='unique_dependency'),
            models.CheckConstraint(condition=~Q(component=F('depends_on')), name='no_self_dependency'),
        ]

    def __str__(self):
        return f'{self.component} -> {self.depends_on}'
