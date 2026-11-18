from datetime import datetime

from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils.dateparse import parse_datetime
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import DomainError
from config.permissions import IsAdminRole, IsClient, IsClientOrManager, IsManager
from messaging import services as messaging_services
from models_app import services as model_services
from models_app import storage
from pricing import services as pricing_services

from . import serializers as ser
from . import services
from .models import Order

PAGE_SIZE = 20


def get_order(request, pk, manager_only=False):
    qs = Order.objects.select_related('client', 'material', 'technology', 'quality_profile', 'color',
                                      'delivery_method', 'pickup_point')
    o = qs.filter(pk=pk).first()
    is_mgr = request.user.role in ('MANAGER', 'ADMIN')
    if not o or (not is_mgr and o.client_id != request.user.id):
        raise Http404
    if is_mgr and o.status == 'DRAFT':
        raise Http404  # черновики клиентов менеджерам не видны
    return o


class OrderListCreate(APIView):
    permission_classes = [IsClientOrManager]

    def get(self, request):
        qs = Order.objects.select_related('client', 'material', 'technology')
        p = request.query_params
        if request.user.role == 'CLIENT':
            qs = qs.filter(client=request.user)
        else:
            qs = qs.exclude(status='DRAFT')
        if p.get('status'):
            qs = qs.filter(status__in=p['status'].split(','))
        if p.get('priority'):
            qs = qs.filter(priority=p['priority'])
        if p.get('material'):
            qs = qs.filter(material_id=p['material'])
        if p.get('workshop'):
            qs = qs.filter(assignments__is_current=True, assignments__printer__workshop_id=p['workshop'])
        if p.get('date_from'):
            qs = qs.filter(created_at__date__gte=p['date_from'])
        if p.get('date_to'):
            qs = qs.filter(created_at__date__lte=p['date_to'])
        if p.get('q'):
            qs = qs.filter(Q(number__icontains=p['q']) | Q(client__email__icontains=p['q'])
                           | Q(client__full_name__icontains=p['q']))
        qs = qs.distinct().order_by('-created_at')
        page = max(int(p.get('page', 1)), 1)
        total = qs.count()
        items = qs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        return Response({'count': total, 'page': page, 'page_size': PAGE_SIZE,
                         'results': [ser.summary(o) for o in items]})

    def post(self, request):
        if request.user.role != 'CLIENT':
            raise DomainError('Создавать заказы могут только клиенты.', 'forbidden', 403)
        o = services.create_draft(request.user, request.data if request.data else None)
        return Response(ser.detail(o, request.user), status=201)


class OrderDetail(APIView):
    permission_classes = [IsClientOrManager]

    def get(self, request, pk):
        return Response(ser.detail(get_order(request, pk), request.user))

    def patch(self, request, pk):
        if request.user.role != 'CLIENT':
            raise DomainError('Недостаточно прав.', 'forbidden', 403)
        o = get_order(request, pk)
        services.update_draft(o, request.user, request.data)
        o.refresh_from_db()
        return Response(ser.detail(o, request.user))


class ModelUpload(APIView):
    permission_classes = [IsClient]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        o = get_order(request, pk)
        f = request.FILES.get('file')
        if not f:
            raise DomainError('E-01: Файл не передан.', 'E-01')
        from django.conf import settings
        if f.size > settings.MAX_UPLOAD_BYTES:
            raise DomainError('E-01: Размер файла превышает 50 МБ.', 'E-01')
        mv = services.attach_model(o, request.user, f.name, f.read())
        services.enqueue_process(o.pk)
        o.refresh_from_db()
        return Response({'model': ser.model_dto(mv), 'order': ser.detail(o, request.user)}, status=201)


class ModelFile(APIView):
    permission_classes = [IsClientOrManager]

    def get(self, request, pk, v):
        o = get_order(request, pk)
        mv = model_services.get_version(o, v)
        if not mv:
            raise Http404
        info = model_services.file_info(mv)
        info['download_url'] = f'/api/orders/{o.pk}/model/{mv.version}/download'
        return Response(info)


class ModelDownload(APIView):
    permission_classes = [IsClientOrManager]

    def get(self, request, pk, v):
        import io
        o = get_order(request, pk)
        mv = model_services.get_version(o, v)
        if not mv:
            raise Http404
        return FileResponse(io.BytesIO(storage.get(mv.storage_key)), as_attachment=True, filename=mv.file_name)


class OrderQuote(APIView):
    permission_classes = [IsClientOrManager]

    def get(self, request, pk):
        o = get_order(request, pk)
        mv, vr, quote, ready = services.quote_state(o)
        return Response({'ready': ready, 'quote': ser.quote_dto(quote), 'validation': ser.validation_dto(vr),
                         'model': ser.model_dto(mv), 'status': o.status})


class OrderConfirm(APIView):
    permission_classes = [IsClient]

    def post(self, request, pk):
        o = get_order(request, pk)
        services.confirm(o, request.user)
        o.refresh_from_db()
        return Response(ser.detail(o, request.user))


class OrderPay(APIView):
    permission_classes = [IsClient]

    def post(self, request, pk):
        o = get_order(request, pk)
        services.pay(o, request.user)
        o.refresh_from_db()
        return Response(ser.detail(o, request.user))


class OrderCancel(APIView):
    permission_classes = [IsClientOrManager]

    def post(self, request, pk):
        o = get_order(request, pk)
        services.cancel(o, request.user, request.data.get('reason', ''))
        o.refresh_from_db()
        return Response(ser.detail(o, request.user))


class OrderRepeat(APIView):
    permission_classes = [IsClient]

    def post(self, request, pk):
        o = get_order(request, pk)
        new = services.repeat(o, request.user)
        return Response(ser.detail(new, request.user), status=201)


class OrderDecision(APIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        o = get_order(request, pk)
        services.decision(o, request.user, request.data.get('action'), request.data.get('reason', ''))
        o.refresh_from_db()
        return Response(ser.detail(o, request.user))


class OrderStatus(APIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        o = get_order(request, pk)
        services.change_status(o, request.user, request.data.get('status'), request.data.get('reason', ''))
        o.refresh_from_db()
        return Response(ser.detail(o, request.user))


class OrderAdjustment(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        o = get_order(request, pk)
        try:
            amount = float(request.data.get('adjustment'))
        except (TypeError, ValueError):
            raise DomainError('Укажите сумму корректировки.', 'validation')
        services.adjust_price(o, request.user, amount, request.data.get('reason', ''))
        o.refresh_from_db()
        return Response(ser.detail(o, request.user))


class OrderMessages(APIView):
    permission_classes = [IsClientOrManager]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, pk):
        o = get_order(request, pk)
        since = parse_datetime(request.query_params.get('since', '')) if request.query_params.get('since') else None
        return Response([ser.message_dto(m) for m in messaging_services.list_for(o, since)])

    def post(self, request, pk):
        o = get_order(request, pk)
        f = request.FILES.get('file') if hasattr(request, 'FILES') else None
        if f and f.size > 50 * 1024 * 1024:
            raise DomainError('E-01: Размер файла превышает 50 МБ.', 'E-01')
        msg = services.post_message(o, request.user, request.data.get('text', ''),
                                    f.name if f else None, f.read() if f else None)
        return Response(ser.message_dto(msg), status=201)


class OrderRecommendation(APIView):
    permission_classes = [IsManager]

    def get(self, request, pk):
        o = get_order(request, pk)
        rec = services.recommendation(o)
        return Response(rec)


class OrderAssignment(APIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        o = get_order(request, pk)
        services.assign_printer(o, request.user, request.data.get('printer_id'), request.data.get('reason', ''))
        o.refresh_from_db()
        return Response(ser.detail(o, request.user))


__all__ = ['datetime', 'pricing_services']
