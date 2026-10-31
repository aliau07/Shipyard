from django.conf import settings
from django.db import models
from django.utils import timezone


class Status(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    IN_REVIEW = 'in_review', 'In review'
    APPROVED = 'approved', 'Approved'
    IN_PROGRESS = 'in_progress', 'In progress'
    RELEASED = 'released', 'Released'
    BLOCKED = 'blocked', 'Blocked'
    CANCELLED = 'cancelled', 'Cancelled'


OPEN_STATUSES = [Status.DRAFT, Status.IN_REVIEW, Status.APPROVED, Status.IN_PROGRESS, Status.BLOCKED]
FINAL_STATUSES = [Status.RELEASED, Status.CANCELLED]


class Release(models.Model):
    """A set of component changes that ship together, in dependency order."""

    project      = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='releases')
    title        = models.CharField(max_length=120)
    version      = models.CharField(max_length=40)
    description  = models.TextField(blank=True)
    status       = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+')
    target_date  = models.DateField(null=True, blank=True)
    blocked_from = models.CharField(max_length=12, choices=Status.choices, blank=True,
                                    help_text='Where the release returns to when it is unblocked.')
    blocked_reason = models.TextField(blank=True)
    reopen_count = models.PositiveSmallIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at  = models.DateTimeField(null=True, blank=True)
    started_at   = models.DateTimeField(null=True, blank=True)
    released_at  = models.DateTimeField(null=True, blank=True)
    closed_at    = models.DateTimeField(null=True, blank=True, help_text='When it was cancelled.')
    created_at   = models.DateTimeField(default=timezone.now)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['project', 'status'])]
        constraints = [models.UniqueConstraint(fields=['project', 'version'], name='unique_release_version_per_project')]

    def __str__(self):
        return f'{self.reference} {self.title}'

    @property
    def reference(self):
        return f'REL-{self.pk:04d}' if self.pk else 'REL-new'

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES


class ReleaseChange(models.Model):
    """One component that changes in a release."""

    class ChangeType(models.TextChoices):
        FEATURE = 'feature', 'Feature'
        FIX = 'fix', 'Fix'
        BREAKING = 'breaking', 'Breaking change'
        CHORE = 'chore', 'Maintenance'

    release     = models.ForeignKey(Release, on_delete=models.CASCADE, related_name='changes')
    component   = models.ForeignKey('projects.Component', on_delete=models.RESTRICT, related_name='release_changes')
    change_type = models.CharField(max_length=10, choices=ChangeType.choices, default=ChangeType.FEATURE)
    summary     = models.CharField(max_length=300)
    added_by    = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='+')
    created_at  = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['component__name', 'pk']
        constraints = [models.UniqueConstraint(fields=['release', 'component'], name='one_change_per_component')]

    def __str__(self):
        return f'{self.component} in {self.release.reference}'


class SignOff(models.Model):
    """The owner of a changed component agrees it is ready to ship."""

    release    = models.ForeignKey(Release, on_delete=models.CASCADE, related_name='sign_offs')
    component  = models.ForeignKey('projects.Component', on_delete=models.CASCADE, related_name='+')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    note       = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.UniqueConstraint(fields=['release', 'component'], name='one_sign_off_per_component')]

    def __str__(self):
        return f'{self.component} signed off for {self.release.reference}'


class ReleaseEvent(models.Model):
    """One entry in a release's timeline; also what notifications are built from."""

    class Kind(models.TextChoices):
        CREATED = 'created', 'Created'
        UPDATED = 'updated', 'Details updated'
        CHANGE_ADDED = 'change_added', 'Change added'
        CHANGE_REMOVED = 'change_removed', 'Change removed'
        SUBMITTED = 'submitted', 'Submitted for review'
        SIGNED_OFF = 'signed_off', 'Signed off'
        CHANGES_REQUESTED = 'changes_requested', 'Changes requested'
        APPROVED = 'approved', 'Approved'
        STARTED = 'started', 'Rollout started'
        RELEASED = 'released', 'Released'
        BLOCKED = 'blocked', 'Blocked'
        UNBLOCKED = 'unblocked', 'Unblocked'
        CANCELLED = 'cancelled', 'Cancelled'
        REOPENED = 'reopened', 'Reopened'
        COMMENTED = 'commented', 'Comment'

    release     = models.ForeignKey(Release, on_delete=models.CASCADE, related_name='events')
    actor       = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='+')
    kind        = models.CharField(max_length=20, choices=Kind.choices)
    from_status = models.CharField(max_length=12, choices=Status.choices, blank=True)
    to_status   = models.CharField(max_length=12, choices=Status.choices, blank=True)
    message     = models.TextField(blank=True)
    created_at  = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'{self.release.reference}: {self.get_kind_display()}'


class Comment(models.Model):
    release    = models.ForeignKey(Release, on_delete=models.CASCADE, related_name='comments')
    author     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    body       = models.TextField(max_length=4000)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'Comment by {self.author} on {self.release.reference}'


def screenshot_path(screenshot, filename):
    return f'releases/{screenshot.comment.release_id}/{filename}'


class Screenshot(models.Model):
    """An image attached to a comment, re-encoded on upload (metadata removed)."""

    comment    = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='screenshots')
    image      = models.ImageField(upload_to=screenshot_path)
    thumbnail  = models.ImageField(upload_to=screenshot_path)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'Screenshot on {self.comment}'
