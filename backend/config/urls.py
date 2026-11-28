"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from orders import temp_auth


def health(request):
    try:
        connection.ensure_connection()
        db = 'ok'
    except Exception:
        db = 'error'
    return JsonResponse({'status': 'ok' if db == 'ok' else 'degraded', 'db': db}, status=200 if db == 'ok' else 503)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health', health),
    path('api/schema', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
    path('api/catalog/', include('catalog.urls')),
    path('api/', include('catalog.equipment_urls')),
    path('api/', include('scheduling.urls')),
    path('api/', include('orders.urls')),
    path('api/', include('notifications.urls')),
    # TEMPORARY auth endpoints для локальной проверки клиентского портала до слияния модуля `users` (П. А. Юшкова)
    path('api/auth/csrf', temp_auth.csrf_view, name='temp-auth-csrf'),
    path('api/auth/register', temp_auth.register_view, name='temp-auth-register'),
    path('api/auth/login', temp_auth.login_view, name='temp-auth-login'),
    path('api/auth/logout', temp_auth.logout_view, name='temp-auth-logout'),
    path('api/auth/me', temp_auth.me_view, name='temp-auth-me'),
    path('api/auth/password-reset', temp_auth.password_reset_view, name='temp-auth-password-reset'),
    path('api/auth/password-reset/confirm', temp_auth.password_reset_confirm_view, name='temp-auth-password-reset-confirm'),
    path('', RedirectView.as_view(url='/api/catalog/', permanent=False)),
]

