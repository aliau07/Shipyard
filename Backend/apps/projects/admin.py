from django.contrib import admin

from .models import Component, Dependency, Membership, Project


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    raw_id_fields = ['user']


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name']
    inlines = [MembershipInline]


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'kind', 'owner', 'deploy_minutes']
    list_filter = ['kind', 'project']
    list_select_related = ['project', 'owner']
    search_fields = ['name', 'package_name']


@admin.register(Dependency)
class DependencyAdmin(admin.ModelAdmin):
    list_display = ['component', 'depends_on', 'source', 'created_at']
    list_filter = ['source']
    list_select_related = ['component', 'depends_on']
