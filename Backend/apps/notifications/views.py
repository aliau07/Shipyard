from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.views import ScopedQuerysetMixin

from . import services
from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(ScopedQuerysetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Notification.objects.none()
    """Your notifications, newest first. ?unread=true for unread only."""

    serializer_class = NotificationSerializer
    filter_backends = []

    def scoped_queryset(self):
        notifications = Notification.objects.filter(recipient=self.request.user).select_related('release__project')
        if self.request.query_params.get('unread') == 'true':
            notifications = notifications.filter(read_at__isnull=True)
        return notifications

    @extend_schema(parameters=[OpenApiParameter('unread', bool)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(responses=inline_serializer('UnreadCount', {'unread': serializers.IntegerField()}))
    @action(detail=False, url_path='unread-count')
    def unread_count(self, request):
        """Cheap endpoint the React app polls for the bell badge."""
        return Response({'unread': services.unread(request.user).count()})

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=['read_at'])
        return Response(NotificationSerializer(notification).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        services.mark_all_read(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
