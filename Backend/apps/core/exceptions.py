from django.db.models import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(Exception):
    """A request that breaks a business rule. Services raise it; the API answers with `status_code`."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


def exception_handler(exc, context):
    """DRF's default handler, plus domain errors and a 409 for deletes blocked by PROTECT or RESTRICT."""
    if isinstance(exc, DomainError):
        return Response({'detail': exc.message}, status=exc.status_code)
    if isinstance(exc, (ProtectedError, RestrictedError)):
        return Response(
            {'detail': 'This record is still referenced by other records and cannot be deleted.'},
            status=status.HTTP_409_CONFLICT,
        )
    return drf_exception_handler(exc, context)
