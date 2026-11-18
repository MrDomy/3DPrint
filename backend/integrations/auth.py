from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from .models import ApiClient, hash_key


class IntegrationUser:
    is_authenticated = True
    is_active = True
    role = 'INTEGRATION'
    pk = None


class ApiKeyAuthentication(BaseAuthentication):
    """Ключ передаётся в заголовке X-API-Key; в БД хранится только хэш."""

    def authenticate(self, request):
        raw = request.headers.get('X-API-Key')
        if not raw:
            return None
        c = ApiClient.objects.filter(api_key_hash=hash_key(raw), is_active=True).first()
        if not c:
            raise AuthenticationFailed('Неверный API-ключ.')
        return IntegrationUser(), c

    def authenticate_header(self, request):
        return 'X-API-Key'


def has_scope(scope):
    class _P(BasePermission):
        message = 'Недостаточно прав доступа (scope).'

        def has_permission(self, request, view):
            c = request.auth
            return isinstance(c, ApiClient) and (scope in c.scopes or '*' in c.scopes)
    return _P
