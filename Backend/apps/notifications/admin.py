from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'message', 'created_at', 'read_at']
    list_select_related = ['recipient']
    search_fields = ['recipient__username', 'message']
