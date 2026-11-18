from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from catalog import views as catalog_views
from integrations import views as integ
from notifications import views as notif
from orders import views as ov
from scheduling import views as sched


def health(request):
    from django.db import connection
    try:
        connection.ensure_connection()
        db = 'ok'
    except Exception:
        db = 'error'
    return JsonResponse({'status': 'ok' if db == 'ok' else 'degraded', 'db': db})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health', health),
    path('api/schema', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs', SpectacularSwaggerView.as_view(url_name='schema')),
    path('api/auth/', include('users.urls')),
    path('api/catalog/<str:name>', catalog_views.CatalogView.as_view()),
    path('api/printers', catalog_views.PrintersView.as_view()),
    path('api/workshops', catalog_views.WorkshopsView.as_view()),
    path('api/orders', ov.OrderListCreate.as_view()),
    path('api/orders/<uuid:pk>', ov.OrderDetail.as_view()),
    path('api/orders/<uuid:pk>/model', ov.ModelUpload.as_view()),
    path('api/orders/<uuid:pk>/model/<int:v>/file', ov.ModelFile.as_view()),
    path('api/orders/<uuid:pk>/model/<int:v>/download', ov.ModelDownload.as_view()),
    path('api/orders/<uuid:pk>/quote', ov.OrderQuote.as_view()),
    path('api/orders/<uuid:pk>/confirm', ov.OrderConfirm.as_view()),
    path('api/orders/<uuid:pk>/pay', ov.OrderPay.as_view()),
    path('api/orders/<uuid:pk>/cancel', ov.OrderCancel.as_view()),
    path('api/orders/<uuid:pk>/repeat', ov.OrderRepeat.as_view()),
    path('api/orders/<uuid:pk>/decision', ov.OrderDecision.as_view()),
    path('api/orders/<uuid:pk>/status', ov.OrderStatus.as_view()),
    path('api/orders/<uuid:pk>/adjustment', ov.OrderAdjustment.as_view()),
    path('api/orders/<uuid:pk>/messages', ov.OrderMessages.as_view()),
    path('api/orders/<uuid:pk>/recommendation', ov.OrderRecommendation.as_view()),
    path('api/orders/<uuid:pk>/assignment', ov.OrderAssignment.as_view()),
    path('api/load', sched.LoadView.as_view()),
    path('api/notifications', notif.NotificationList.as_view()),
    path('api/notifications/<uuid:pk>/read', notif.NotificationRead.as_view()),
    path('api/integration/orders', integ.IntegrationOrders.as_view()),
    path('api/integration/orders/<uuid:pk>/status', integ.IntegrationStatus.as_view()),
    path('api/integration/export/orders', integ.ExportOrders.as_view()),
    path('api/integration/export/events', integ.ExportEvents.as_view()),
    path('api/integration/export/load', integ.ExportLoad.as_view()),
]
