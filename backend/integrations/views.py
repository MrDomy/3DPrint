import csv

from django.http import Http404, HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import DomainError
from orders import services as order_services
from scheduling import services as scheduling_services

from .auth import ApiKeyAuthentication, has_scope

DANGEROUS_CSV_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _safe_csv_cell(val):
    if isinstance(val, str) and val.startswith(DANGEROUS_CSV_PREFIXES):
        return "'" + val
    return val


class _Base(APIView):
    authentication_classes = [ApiKeyAuthentication]


class IntegrationOrders(_Base):
    permission_classes = [has_scope('orders:read')]

    def get(self, request):
        return Response(order_services.list_for_integration())


class IntegrationStatus(_Base):
    permission_classes = [has_scope('orders:write')]

    def post(self, request, pk):
        to = request.data.get('status')
        if not to:
            raise DomainError('Укажите статус.', 'validation')
        payload = {k: request.data.get(k) for k in ('actual_print_hours', 'actual_mass_g', 'note')
                   if request.data.get(k) is not None}
        o = order_services.integration_update_by_id(pk, to, payload)
        if not o:
            raise Http404
        return Response({'id': str(o.pk), 'status': o.status, 'payload': payload})


def _respond(rows, fmt, name):
    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="{name}.csv"'
        resp.write('\ufeff')
        if rows:
            w = csv.DictWriter(resp, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow({k: _safe_csv_cell(v) for k, v in r.items()})
        return resp
    return Response(rows)


class ExportOrders(_Base):
    permission_classes = [has_scope('export:read')]

    def get(self, request):
        return _respond(order_services.export_orders_rows(), request.query_params.get('format'), 'orders')


class ExportEvents(_Base):
    permission_classes = [has_scope('export:read')]

    def get(self, request):
        return _respond(order_services.export_events_rows(), request.query_params.get('format'), 'events')


class ExportLoad(_Base):
    permission_classes = [has_scope('export:read')]

    def get(self, request):
        data = scheduling_services.equipment_load()
        rows = [{k: v for k, v in p.items() if k != 'jobs'} for p in data['printers']]
        return _respond(rows, request.query_params.get('format'), 'load')

