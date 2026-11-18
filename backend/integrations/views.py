import csv

from django.http import Http404, HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import DomainError
from orders import services as order_services
from orders.models import Order, OrderEvent
from orders.serializers import summary
from scheduling import services as scheduling_services

from .auth import ApiKeyAuthentication, has_scope

RANGE = ['PAID', 'DISTRIBUTED', 'PRINTING', 'POST_PROCESSING', 'READY']


class _Base(APIView):
    authentication_classes = [ApiKeyAuthentication]


class IntegrationOrders(_Base):
    permission_classes = [has_scope('orders:read')]

    def get(self, request):
        qs = Order.objects.filter(status__in=RANGE).select_related('client', 'material', 'technology')
        return Response([summary(o) for o in qs])


class IntegrationStatus(_Base):
    permission_classes = [has_scope('orders:write')]

    def post(self, request, pk):
        o = Order.objects.filter(pk=pk).first()
        if not o:
            raise Http404
        to = request.data.get('status')
        if not to:
            raise DomainError('Укажите статус.', 'validation')
        payload = {k: request.data.get(k) for k in ('actual_print_hours', 'actual_mass_g', 'note')
                   if request.data.get(k) is not None}
        order_services.integration_update(o, to, payload)
        return Response({'id': str(o.pk), 'status': o.status})


def _respond(rows, fmt, name):
    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="{name}.csv"'
        resp.write('﻿')
        if rows:
            w = csv.DictWriter(resp, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return resp
    return Response(rows)


class ExportOrders(_Base):
    permission_classes = [has_scope('export:read')]

    def get(self, request):
        rows = [{'number': o.number, 'status': o.status, 'client': o.client.email, 'quantity': o.quantity,
                 'material': o.material.name if o.material else '', 'created_at': o.created_at.isoformat()}
                for o in Order.objects.exclude(status='DRAFT').select_related('client', 'material')]
        return _respond(rows, request.query_params.get('format'), 'orders')


class ExportEvents(_Base):
    permission_classes = [has_scope('export:read')]

    def get(self, request):
        rows = [{'order': e.order.number, 'type': e.type, 'from': e.from_status, 'to': e.to_status,
                 'reason': e.reason, 'created_at': e.created_at.isoformat()}
                for e in OrderEvent.objects.select_related('order')]
        return _respond(rows, request.query_params.get('format'), 'events')


class ExportLoad(_Base):
    permission_classes = [has_scope('export:read')]

    def get(self, request):
        data = scheduling_services.equipment_load()
        rows = [{k: v for k, v in p.items() if k != 'jobs'} for p in data['printers']]
        return _respond(rows, request.query_params.get('format'), 'load')
