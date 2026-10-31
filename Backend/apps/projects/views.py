from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.views import ScopedQuerysetMixin

from . import graph, services
from .models import Component, Dependency, Membership, Project
from .scoping import components_for, dependencies_for, projects_for
from .serializers import (
    ComponentCreateSerializer, ComponentSerializer, DependencyCreatedSerializer, DependencySerializer,
    ImpactSerializer, ManifestResultSerializer, ManifestUploadSerializer, MemberAddSerializer, MemberRoleSerializer,
    MembershipSerializer, ProjectDetailSerializer, ProjectSerializer,
)

OPEN_RELEASE_STATUSES = ['draft', 'in_review', 'approved', 'in_progress', 'blocked']


class ProjectViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """Projects you belong to. Creating one makes you its owner."""

    queryset = Project.objects.none()
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def scoped_queryset(self):
        projects = projects_for(self.request.user).annotate(
            component_count=Count('components', distinct=True),
            open_release_count=Count('releases', filter=Q(releases__status__in=OPEN_RELEASE_STATUSES), distinct=True),
        )
        if self.action == 'retrieve':
            projects = projects.prefetch_related(
                Prefetch('memberships', queryset=Membership.objects.select_related('user').order_by('role', 'user__username')))
        return projects

    def get_serializer_class(self):
        return ProjectDetailSerializer if self.action == 'retrieve' else ProjectSerializer

    def detail_response(self, project, status_code=status.HTTP_200_OK):
        self.action = 'retrieve'
        project = self.scoped_queryset().get(pk=project.pk)
        return Response(ProjectDetailSerializer(project, context=self.get_serializer_context()).data, status=status_code)

    @extend_schema(request=ProjectSerializer, responses={201: ProjectDetailSerializer})
    def create(self, request, *args, **kwargs):
        serializer = ProjectSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        project = services.create_project(request.user, **serializer.validated_data)
        return self.detail_response(project, status.HTTP_201_CREATED)

    @extend_schema(request=ProjectSerializer, responses=ProjectDetailSerializer)
    def partial_update(self, request, *args, **kwargs):
        project = self.get_object()
        serializer = ProjectSerializer(project, data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        services.update_project(project, request.user, serializer.validated_data)
        return self.detail_response(project)

    def update(self, request, *args, **kwargs):
        if not kwargs.get('partial'):
            return Response({'detail': 'Use PATCH to edit a project.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        services.delete_project(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses=dict)
    @action(detail=True)
    def graph(self, request, pk=None):
        """The whole dependency graph laid out in waves, with any cycle and every component's impact paths."""
        return Response(services.project_graph(self.get_object()))

    @extend_schema(request=MemberAddSerializer, responses={201: MembershipSerializer})
    @action(detail=True, methods=['post'])
    def members(self, request, pk=None):
        """Owners add an existing account by username or email."""
        project = self.get_object()
        serializer = MemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.add_member(project, request.user, serializer.validated_data['user'],
                                         serializer.validated_data['role'])
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)

    @extend_schema(methods=['PATCH'], request=MemberRoleSerializer, responses=MembershipSerializer)
    @extend_schema(methods=['DELETE'], request=None, responses={204: None})
    @action(detail=True, methods=['patch', 'delete'], url_path=r'members/(?P<membership_id>\d+)')
    def member(self, request, pk=None, membership_id=None):
        """Owners change roles or remove people; anyone may remove themselves."""
        project = self.get_object()
        membership = get_object_or_404(Membership.objects.select_related('user', 'project'), pk=membership_id,
                                       project=project)
        if request.method == 'DELETE':
            services.remove_member(membership, request.user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = MemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_role(membership, request.user, serializer.validated_data['role'])
        return Response(MembershipSerializer(membership).data)


class ComponentViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """Components of your projects. Filter with ?project=<id>."""

    queryset = Component.objects.none()
    filterset_fields = ['project', 'kind', 'owner']
    search_fields = ['name', 'package_name', 'description']
    ordering_fields = ['name', 'deploy_minutes', 'dependent_count']
    ordering = ['name']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def scoped_queryset(self):
        return components_for(self.request.user).select_related('owner', 'project').annotate(
            dependency_count=Count('dependencies', distinct=True),
            dependent_count=Count('dependents', distinct=True),
        )

    def get_serializer_class(self):
        return ComponentCreateSerializer if self.action == 'create' else ComponentSerializer

    def component_response(self, component, status_code=status.HTTP_200_OK):
        component = self.scoped_queryset().get(pk=component.pk)
        return Response(ComponentSerializer(component, context=self.get_serializer_context()).data, status=status_code)

    @extend_schema(request=ComponentCreateSerializer, responses={201: ComponentSerializer})
    def create(self, request, *args, **kwargs):
        serializer = ComponentCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        component = services.create_component(data.pop('project'), request.user, **data)
        return self.component_response(component, status.HTTP_201_CREATED)

    @extend_schema(request=ComponentSerializer, responses=ComponentSerializer)
    def partial_update(self, request, *args, **kwargs):
        component = self.get_object()
        serializer = ComponentSerializer(component, data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        services.update_component(component, request.user, serializer.validated_data)
        return self.component_response(component)

    def update(self, request, *args, **kwargs):
        if not kwargs.get('partial'):
            return Response({'detail': 'Use PATCH to edit a component.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        services.delete_component(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request={'multipart/form-data': ManifestUploadSerializer}, responses=ManifestResultSerializer)
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def manifest(self, request, pk=None):
        """Upload a requirements.txt or package.json: packages that match components become dependencies."""
        component = self.get_object()
        serializer = ManifestUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(services.import_manifest(component, request.user, serializer.validated_data['file']))

    @extend_schema(responses=ImpactSerializer(many=True))
    @action(detail=True)
    def impact(self, request, pk=None):
        """Every component that depends on this one, directly or not, with the path that reaches it."""
        component = self.get_object()
        _, project_graph = services.load_graph(component.project_id)
        results = []
        for hit in graph.impact(project_graph, component.name):
            results.append({'name': hit['node'], 'depth': hit['depth'], 'path': hit['path'], 'in_view': True})
        return Response(results)


class DependencyViewSet(ScopedQuerysetMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin,
                        viewsets.GenericViewSet):
    """`component` depends on `depends_on`. Filter with ?project=<id> or ?component=<id>."""

    queryset = Dependency.objects.none()
    serializer_class = DependencySerializer
    filter_backends = []
    pagination_class = None

    def scoped_queryset(self):
        dependencies = dependencies_for(self.request.user).select_related('component', 'depends_on')
        project = self.request.query_params.get('project')
        component = self.request.query_params.get('component')
        if project and project.isdigit():
            dependencies = dependencies.filter(component__project_id=project)
        if component and component.isdigit():
            dependencies = dependencies.filter(Q(component_id=component) | Q(depends_on_id=component))
        return dependencies

    @extend_schema(parameters=[OpenApiParameter('project', int), OpenApiParameter('component', int)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=DependencySerializer, responses={201: DependencyCreatedSerializer})
    def create(self, request, *args, **kwargs):
        serializer = DependencySerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        dependency, cycle = services.add_dependency(request.user, serializer.validated_data['component'],
                                                    serializer.validated_data['depends_on'])
        data = DependencySerializer(dependency).data
        data['cycle'] = cycle
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        services.remove_dependency(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
