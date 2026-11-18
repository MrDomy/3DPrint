from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import exception_handler


class DomainError(Exception):
    """Бизнес-ошибка с кодом (E-01 и т.д.) и русским сообщением."""

    def __init__(self, message, code='error', status=400):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response({'code': exc.code, 'detail': exc.message}, status=exc.status)
    if isinstance(exc, DjangoValidationError):
        return Response({'code': 'validation', 'detail': '; '.join(exc.messages)}, status=400)
    if isinstance(exc, Http404):
        return Response({'code': 'not_found', 'detail': 'Не найдено.'}, status=404)
    if isinstance(exc, PermissionDenied):
        return Response({'code': 'forbidden', 'detail': 'Недостаточно прав.'}, status=403)
    return exception_handler(exc, context)
