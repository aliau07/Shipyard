from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    release_reference = serializers.CharField(source='release.reference', read_only=True)
    project_name = serializers.CharField(source='release.project.name', read_only=True)
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ['id', 'release', 'release_reference', 'project_name', 'message', 'created_at', 'read_at', 'is_read']

    def get_is_read(self, notification) -> bool:
        return notification.read_at is not None
