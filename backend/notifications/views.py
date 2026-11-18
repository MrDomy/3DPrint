from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsClientOrManager

from .models import Notification


def dto(n):
    return {'id': str(n.id), 'order_id': str(n.order_id) if n.order_id else None,
            'order_number': n.order.number if n.order else None, 'text': n.text, 'is_read': n.is_read,
            'created_at': n.created_at}


class NotificationList(APIView):
    permission_classes = [IsClientOrManager]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user, channel='INAPP').select_related('order')
        unread = qs.filter(is_read=False).count()
        return Response({'unread': unread, 'results': [dto(n) for n in qs[:100]]})


class NotificationRead(APIView):
    permission_classes = [IsClientOrManager]

    def post(self, request, pk):
        n = Notification.objects.filter(pk=pk, user=request.user).first()
        if not n:
            raise Http404
        n.is_read = True
        n.save(update_fields=['is_read', 'updated_at'])
        return Response(dto(n))
