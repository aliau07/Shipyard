from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.serializers import PublicUserSerializer

from .models import MANAGER_ROLES, Component, Dependency, Membership, Project
from .scoping import role_in


def signed_in_user(serializer):
    request = serializer.context.get('request')
    user = getattr(request, 'user', None)
    return user if user is not None and user.is_authenticated else None


class MembershipSerializer(serializers.ModelSerializer):
    user = PublicUserSerializer(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'user', 'role', 'role_display', 'created_at']


class MemberAddSerializer(serializers.Serializer):
    user = serializers.CharField(help_text='Username or email address of an existing account.')
    role = serializers.ChoiceField(choices=Membership.Role.choices, default=Membership.Role.ENGINEER)


class MemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices)


class ProjectSerializer(serializers.ModelSerializer):
    viewer_role = serializers.SerializerMethodField()
    component_count = serializers.IntegerField(read_only=True, default=0)
    open_release_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'created_at', 'viewer_role', 'component_count', 'open_release_count']
        read_only_fields = ['created_at']

    def get_viewer_role(self, project) -> str:
        return role_in(project, self.context['request'].user)


class ProjectDetailSerializer(ProjectSerializer):
    members = MembershipSerializer(source='memberships', many=True, read_only=True)
    can_manage = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ['members', 'can_manage']

    def get_can_manage(self, project) -> bool:
        return role_in(project, self.context['request'].user) in MANAGER_ROLES


class ComponentSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), allow_null=True, required=False)
    owner_name = serializers.CharField(source='owner.display_name', read_only=True, default=None)
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    dependency_count = serializers.IntegerField(read_only=True, default=0)
    dependent_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Component
        fields = ['id', 'project', 'name', 'kind', 'kind_display', 'owner', 'owner_name', 'package_name',
                  'deploy_minutes', 'description', 'repository_url', 'dependency_count', 'dependent_count',
                  'created_at']
        read_only_fields = ['project', 'created_at']


class ComponentCreateSerializer(ComponentSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.none())

    class Meta(ComponentSerializer.Meta):
        read_only_fields = ['created_at']
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = signed_in_user(self)
        if user is not None:
            self.fields['project'].queryset = Project.objects.filter(memberships__user=user)


class DependencySerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component.name', read_only=True)
    depends_on_name = serializers.CharField(source='depends_on.name', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)

    class Meta:
        model = Dependency
        fields = ['id', 'component', 'component_name', 'depends_on', 'depends_on_name', 'source', 'source_display',
                  'created_at']
        read_only_fields = ['source', 'created_at']
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = signed_in_user(self)
        visible = Component.objects.none()
        if user is not None:
            visible = Component.objects.filter(project__memberships__user=user)
        if 'component' in self.fields and not self.fields['component'].read_only:
            self.fields['component'].queryset = visible
            self.fields['depends_on'].queryset = visible


class DependencyCreatedSerializer(DependencySerializer):
    cycle = serializers.ListField(child=serializers.CharField(), allow_null=True, read_only=True)

    class Meta(DependencySerializer.Meta):
        fields = DependencySerializer.Meta.fields + ['cycle']


class ManifestUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text='A requirements.txt (or other pip .txt file) or a package.json.')


class ManifestResultSerializer(serializers.Serializer):
    format = serializers.CharField()
    packages = serializers.IntegerField()
    created = serializers.ListField(child=serializers.CharField())
    existing = serializers.ListField(child=serializers.CharField())
    unmatched = serializers.ListField(child=serializers.CharField())
    cycle = serializers.ListField(child=serializers.CharField(), allow_null=True)


class ImpactSerializer(serializers.Serializer):
    name = serializers.CharField()
    depth = serializers.IntegerField()
    path = serializers.ListField(child=serializers.CharField())
    in_view = serializers.BooleanField()
