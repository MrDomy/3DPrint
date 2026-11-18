from django.conf import settings
from django.db import connection
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """GET /health — liveness + DB / Redis readiness."""
    result = {'status': 'ok', 'db': 'ok', 'redis': 'skipped'}
    code = 200
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:  # noqa: BLE001
        result['db'] = 'error'
        result['status'] = 'error'
        code = 503
    if not settings.RQ_SYNC:
        try:
            import django_rq

            django_rq.get_connection('default').ping()
            result['redis'] = 'ok'
        except Exception:  # noqa: BLE001
            result['redis'] = 'error'
            result['status'] = 'degraded'
    return Response(result, status=code)
