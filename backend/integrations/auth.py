from dataclasses import dataclass
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from .models import ApiClient, hash_key


@dataclass
class IntegrationPrincipal:
    client: ApiClient
    is_authenticated: bool = True
    is_active: bool = True
    role: str = 'INTEGRATION'
    pk: None = None

    @property
    def scopes(self):
        return set(self.client.scopes or [])


class ApiKeyAuthentication(BaseAuthentication):
    keyword = 'HTTP_X_API_KEY'

    def authenticate(self, request):
        raw = request.META.get(self.keyword) or request.headers.get('X-API-Key')
        if not raw:
            raise AuthenticationFailed('Требуется заголовок X-API-Key.')
        client = ApiClient.objects.filter(api_key_hash=hash_key(raw.strip()), is_active=True).first()
        if not client:
            raise AuthenticationFailed('Недействительный или отозванный API-ключ.')
        return (IntegrationPrincipal(client), client)

    def authenticate_header(self, request):
        return 'X-API-Key'


def has_scope(scope: str):
    class _ScopePermission(BasePermission):
        message = f'Недостаточно прав (требуется область {scope}).'

        def has_permission(self, request, view):
            client = getattr(request, 'auth', None)
            if not isinstance(client, ApiClient):
                return False
            return scope in (client.scopes or []) or '*' in (client.scopes or [])

    return _ScopePermission

