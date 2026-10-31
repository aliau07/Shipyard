from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.scoping import projects_for

from .services import dashboard_for


class DashboardView(APIView):
    """Release figures across your projects, or for one project with ?project=<id>."""

    @extend_schema(parameters=[OpenApiParameter('project', int)], responses=dict)
    def get(self, request):
        project = None
        project_id = request.query_params.get('project')
        if project_id:
            project = get_object_or_404(projects_for(request.user), pk=project_id if project_id.isdigit() else 0)
        return Response(dashboard_for(request.user, project))
