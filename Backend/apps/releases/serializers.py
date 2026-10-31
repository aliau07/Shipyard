from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.core.images import validate_image
from apps.projects.models import Component, Project
from apps.projects.serializers import signed_in_user

from . import workflow
from .models import Comment, Release, ReleaseChange, Screenshot, SignOff
from .planning import plan_for
from .scoping import relationship


class ReleaseListSerializer(serializers.ModelSerializer):
    reference = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.display_name', read_only=True, default=None)
    change_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Release
        fields = ['id', 'reference', 'project', 'project_name', 'title', 'version', 'status', 'status_display',
                  'target_date', 'created_by_name', 'change_count', 'blocked_reason', 'created_at', 'updated_at']


class ChangeSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component.name', read_only=True)
    component_kind = serializers.CharField(source='component.kind', read_only=True)
    owner = serializers.IntegerField(source='component.owner_id', read_only=True, default=None)
    owner_name = serializers.CharField(source='component.owner.display_name', read_only=True, default=None)
    change_type_display = serializers.CharField(source='get_change_type_display', read_only=True)
    added_by_name = serializers.CharField(source='added_by.display_name', read_only=True, default=None)

    class Meta:
        model = ReleaseChange
        fields = ['id', 'component', 'component_name', 'component_kind', 'owner', 'owner_name', 'change_type',
                  'change_type_display', 'summary', 'added_by_name', 'created_at']


class ChangeInputSerializer(serializers.Serializer):
    component = serializers.PrimaryKeyRelatedField(queryset=Component.objects.none())
    summary = serializers.CharField(max_length=300)
    change_type = serializers.ChoiceField(choices=ReleaseChange.ChangeType.choices, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = signed_in_user(self)
        if user is not None:
            self.fields['component'].queryset = Component.objects.filter(project__memberships__user=user)


class SignOffSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component.name', read_only=True)
    user_name = serializers.CharField(source='user.display_name', read_only=True, default=None)

    class Meta:
        model = SignOff
        fields = ['id', 'component', 'component_name', 'user', 'user_name', 'note', 'created_at']


class ScreenshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Screenshot
        fields = ['id', 'image', 'thumbnail']


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.display_name', read_only=True)
    screenshots = ScreenshotSerializer(many=True, read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'author_name', 'body', 'screenshots', 'created_at']


class CommentCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4000)
    images = serializers.ListField(child=serializers.ImageField(), required=False, default=list,
                                   max_length=settings.MAX_SCREENSHOTS_PER_COMMENT)

    def validate_images(self, images):
        for image in images:
            try:
                validate_image(image)
            except DjangoValidationError as error:
                raise serializers.ValidationError(error.messages)
        return images


class ReleaseDetailSerializer(ReleaseListSerializer):
    changes = ChangeSerializer(many=True, read_only=True)
    sign_offs = SignOffSerializer(many=True, read_only=True)
    viewer_role = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    approval = serializers.SerializerMethodField()
    plan = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta(ReleaseListSerializer.Meta):
        fields = ReleaseListSerializer.Meta.fields + [
            'description', 'blocked_from', 'reopen_count', 'submitted_at', 'approved_at', 'started_at', 'released_at',
            'closed_at', 'changes', 'sign_offs', 'viewer_role', 'allowed_actions', 'approval', 'plan', 'timeline',
        ]

    def get_viewer_role(self, release) -> str:
        return relationship(release, self.context['request'].user)

    def get_allowed_actions(self, release) -> list:
        return workflow.allowed_actions(release, self.context['request'].user)

    def get_approval(self, release) -> dict:
        waiting = []
        for component in workflow.pending_sign_offs(release):
            waiting.append({'component': component.name, 'owner_name': component.owner.display_name if component.owner_id else None})
        return {'blockers': workflow.approval_blockers(release), 'waiting_for': waiting,
                'cycle': plan_for(release)['cycle']}

    def get_plan(self, release) -> dict:
        return plan_for(release)

    def get_timeline(self, release) -> list:
        """Events and comments merged in time order."""
        entries = []
        for event in release.events.all():
            entries.append((event.created_at, 1, event.pk, {
                'type': 'event', 'id': event.pk, 'kind': event.kind, 'kind_display': event.get_kind_display(),
                'actor_name': event.actor.display_name if event.actor_id else 'Shipyard', 'message': event.message,
                'from_status': event.from_status, 'to_status': event.to_status, 'created_at': event.created_at,
            }))
        for comment in release.comments.all():
            data = CommentSerializer(comment, context=self.context).data
            data['type'] = 'comment'
            entries.append((comment.created_at, 0, comment.pk, data))
        entries.sort(key=_timeline_key)
        items = []
        for entry in entries:
            items.append(entry[3])
        return items


def _timeline_key(entry):
    return entry[0], entry[1], entry[2]


class ReleaseCreateSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.none())
    changes = ChangeInputSerializer(many=True, required=False)

    class Meta:
        model = Release
        fields = ['project', 'title', 'version', 'description', 'target_date', 'changes']
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = signed_in_user(self)
        if user is not None:
            self.fields['project'].queryset = Project.objects.filter(memberships__user=user)
            self.fields['changes'].child.fields['component'].queryset = Component.objects.filter(
                project__memberships__user=user)


class ReleaseUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Release
        fields = ['title', 'version', 'description', 'target_date']
        validators = []


class TransitionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=list(workflow.ACTIONS))
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)
