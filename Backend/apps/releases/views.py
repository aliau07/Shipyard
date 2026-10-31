from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.views import ScopedQuerysetMixin

from . import services, workflow
from .export import plan_csv
from .models import Comment, Release, ReleaseChange, ReleaseEvent, SignOff
from .scoping import relationship, releases_for
from .serializers import (
    ChangeInputSerializer, ChangeSerializer, CommentCreateSerializer, CommentSerializer, ReleaseCreateSerializer,
    ReleaseDetailSerializer, ReleaseListSerializer, ReleaseUpdateSerializer, TransitionSerializer,
)


def with_detail_prefetches(releases):
    return releases.select_related('project', 'created_by').prefetch_related(
        Prefetch('changes', queryset=ReleaseChange.objects.select_related('component__owner', 'added_by')
                 .order_by('component__name')),
        Prefetch('sign_offs', queryset=SignOff.objects.select_related('component', 'user')),
        Prefetch('events', queryset=ReleaseEvent.objects.select_related('actor')),
        Prefetch('comments', queryset=Comment.objects.select_related('author').prefetch_related('screenshots')),
    )


class ReleaseViewSet(ScopedQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Releases of your projects. What you can do depends on your project role (see `allowed_actions`)."""

    queryset = Release.objects.none()
    filterset_fields = ['project', 'status']
    search_fields = ['title', 'version', 'description']
    ordering_fields = ['created_at', 'updated_at', 'target_date', 'version']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def scoped_queryset(self):
        releases = releases_for(self.request.user)
        if self.action == 'list':
            return releases.select_related('project', 'created_by').annotate(change_count=Count('changes'))
        return with_detail_prefetches(releases.annotate(change_count=Count('changes')))

    def get_serializer_class(self):
        return {
            'list': ReleaseListSerializer,
            'create': ReleaseCreateSerializer,
            'partial_update': ReleaseUpdateSerializer,
        }.get(self.action, ReleaseDetailSerializer)

    def detail_response(self, release, status_code=status.HTTP_200_OK):
        release = with_detail_prefetches(releases_for(self.request.user).annotate(change_count=Count('changes'))).get(
            pk=release.pk)
        return Response(ReleaseDetailSerializer(release, context=self.get_serializer_context()).data, status=status_code)

    def release_and_role(self):
        release = self.get_object()
        return release, relationship(release, self.request.user)

    @extend_schema(request=ReleaseCreateSerializer, responses={201: ReleaseDetailSerializer})
    def create(self, request, *args, **kwargs):
        serializer = ReleaseCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        release = services.create_release(request.user, **serializer.validated_data)
        return self.detail_response(release, status.HTTP_201_CREATED)

    @extend_schema(request=ReleaseUpdateSerializer, responses=ReleaseDetailSerializer)
    def partial_update(self, request, *args, **kwargs):
        release, role = self.release_and_role()
        serializer = ReleaseUpdateSerializer(release, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_release(release, request.user, role, serializer.validated_data)
        return self.detail_response(release)

    def update(self, request, *args, **kwargs):
        if not kwargs.get('partial'):
            return Response({'detail': 'Use PATCH to edit a release.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return super().update(request, *args, **kwargs)

    @extend_schema(request=TransitionSerializer, responses=ReleaseDetailSerializer)
    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        """Move the release through its workflow, e.g. {"action": "block", "reason": "Waiting for DBA"}."""
        release = self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        workflow.perform(release, request.user, data.pop('action'), data)
        return self.detail_response(release)

    @extend_schema(request=ChangeInputSerializer, responses={201: ChangeSerializer})
    @action(detail=True, methods=['post'])
    def changes(self, request, pk=None):
        """Add a component change to a draft release."""
        release, role = self.release_and_role()
        serializer = ChangeInputSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        change = services.add_change(release, request.user, role, **serializer.validated_data)
        return Response(ChangeSerializer(change).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=['delete'], url_path=r'changes/(?P<change_id>\d+)')
    def remove_change(self, request, pk=None, change_id=None):
        release, role = self.release_and_role()
        change = get_object_or_404(ReleaseChange.objects.select_related('component', 'release'), pk=change_id,
                                   release=release)
        services.remove_change(change, request.user, role)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request={'multipart/form-data': CommentCreateSerializer, 'application/json': CommentCreateSerializer},
                   responses={201: CommentSerializer})
    @action(detail=True, methods=['post'], parser_classes=[JSONParser, MultiPartParser, FormParser])
    def comments(self, request, pk=None):
        """Comment as JSON, or as multipart form data with a `body` and up to five `images` (screenshots)."""
        release = self.get_object()
        images = request.FILES.getlist('images') if hasattr(request.FILES, 'getlist') else []
        serializer = CommentCreateSerializer(data={'body': request.data.get('body', ''), 'images': images})
        serializer.is_valid(raise_exception=True)
        comment = services.add_comment(release, request.user, serializer.validated_data['body'],
                                       serializer.validated_data['images'])
        comment = Comment.objects.select_related('author').prefetch_related('screenshots').get(pk=comment.pk)
        return Response(CommentSerializer(comment, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(responses={(200, 'text/csv'): str})
    @action(detail=True)
    def export(self, request, pk=None):
        """Download the deploy plan as CSV: waves, order, owners, timings, sign-offs and impact."""
        return plan_csv(self.get_object())
