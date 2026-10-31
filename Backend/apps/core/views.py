from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response


@extend_schema(responses={200: dict})
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def health(request):
    """Liveness/readiness probe for load balancers and uptime checks; fails if the database is unreachable."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return Response({'status': 'ok'})


class ScopedQuerysetMixin:
    """Viewsets whose rows depend on the signed-in user implement `scoped_queryset()`.

    The OpenAPI generator inspects views without a user, so it gets the empty `queryset` instead.
    """

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return self.scoped_queryset()
