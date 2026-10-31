from django.contrib import admin

from .models import Comment, Release, ReleaseChange, ReleaseEvent, SignOff


class ChangeInline(admin.TabularInline):
    model = ReleaseChange
    extra = 0
    raw_id_fields = ['component', 'added_by']


class SignOffInline(admin.TabularInline):
    model = SignOff
    extra = 0
    raw_id_fields = ['component', 'user']


@admin.register(Release)
class ReleaseAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'project', 'version', 'status', 'created_at']
    list_filter = ['status', 'project']
    list_select_related = ['project']
    search_fields = ['title', 'version']
    inlines = [ChangeInline, SignOffInline]


@admin.register(ReleaseEvent)
class ReleaseEventAdmin(admin.ModelAdmin):
    list_display = ['release', 'kind', 'actor', 'created_at']
    list_filter = ['kind']
    list_select_related = ['release', 'actor']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['release', 'author', 'created_at']
    list_select_related = ['release', 'author']
