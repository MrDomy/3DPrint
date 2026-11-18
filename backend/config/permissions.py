from rest_framework.permissions import BasePermission


def _role(request):
    u = request.user
    return getattr(u, 'role', None) if u and u.is_authenticated else None


class IsClient(BasePermission):
    message = 'Доступно только клиентам.'

    def has_permission(self, request, view):
        return _role(request) == 'CLIENT'


class IsManager(BasePermission):
    message = 'Доступно только менеджерам.'

    def has_permission(self, request, view):
        return _role(request) in ('MANAGER', 'ADMIN')


class IsAdminRole(BasePermission):
    message = 'Доступно только администратору.'

    def has_permission(self, request, view):
        return _role(request) == 'ADMIN'


class IsClientOrManager(BasePermission):
    def has_permission(self, request, view):
        return _role(request) in ('CLIENT', 'MANAGER', 'ADMIN')


class IsStaffRole(IsManager):
    pass
