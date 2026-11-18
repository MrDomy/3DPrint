"""Оркестрация заказов: FSM (14 статусов), валидация/расчёт, решения менеджера, назначение.
Взаимодействие с другими модулями — только через их публичные services.py."""
import datetime
import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_date

from catalog import models as catalog_models
from catalog import services as catalog_services
from config.exceptions import DomainError
from messaging import services as messaging_services
from models_app import services as model_services
from notifications import services as notification_services
from payment import services as payment_services
from pricing import services as pricing_services
from scheduling import services as scheduling_services
from validation import services as validation_services

from .models import AuditLog, Order, OrderEvent, Status

logger = logging.getLogger(__name__)
S = Status
CLIENT, MANAGER, SYSTEM, INTEGRATION = 'CLIENT', 'MANAGER', 'SYSTEM', 'INTEGRATION'
FINAL = {S.COMPLETED, S.REJECTED, S.CANCELLED}

TRANSITIONS = {
    (S.DRAFT, S.NEW): ({CLIENT}, set()),
    (S.DRAFT, S.CANCELLED): ({CLIENT}, set()),
    (S.NEW, S.CHECKED): ({SYSTEM}, set()),
    (S.NEW, S.MANUAL_REVIEW): ({SYSTEM}, set()),
    (S.MANUAL_REVIEW, S.CHECKED): ({MANAGER}, set()),
    (S.MANUAL_REVIEW, S.CLARIFICATION): ({MANAGER}, {MANAGER}),
    (S.MANUAL_REVIEW, S.REJECTED): ({MANAGER}, {MANAGER}),
    (S.CHECKED, S.CLARIFICATION): ({MANAGER}, {MANAGER}),
    (S.CHECKED, S.REJECTED): ({MANAGER}, {MANAGER}),
    (S.CHECKED, S.AWAITING_PAYMENT): ({MANAGER}, set()),
    (S.CLARIFICATION, S.NEW): ({CLIENT, SYSTEM}, set()),
    (S.CLARIFICATION, S.REJECTED): ({MANAGER}, {MANAGER}),
    (S.AWAITING_PAYMENT, S.PAID): ({CLIENT, SYSTEM}, set()),
    (S.PAID, S.DISTRIBUTED): ({MANAGER}, set()),
    (S.DISTRIBUTED, S.PRINTING): ({MANAGER, INTEGRATION}, set()),
    (S.PRINTING, S.POST_PROCESSING): ({MANAGER, INTEGRATION}, set()),
    (S.PRINTING, S.READY): ({MANAGER, INTEGRATION}, set()),
    (S.POST_PROCESSING, S.READY): ({MANAGER}, set()),
    (S.READY, S.COMPLETED): ({MANAGER}, set()),
}
for _s in (S.NEW, S.CHECKED, S.MANUAL_REVIEW, S.CLARIFICATION, S.AWAITING_PAYMENT):
    TRANSITIONS[(_s, S.CANCELLED)] = ({CLIENT, MANAGER}, {MANAGER})
for _s in (S.PAID, S.DISTRIBUTED):
    TRANSITIONS[(_s, S.CANCELLED)] = ({MANAGER}, {MANAGER})

ALL_STATUSES = [s.value for s in S]


def norm_role(user=None, role=None):
    if role:
        return role
    return MANAGER if user.role in ('MANAGER', 'ADMIN') else CLIENT


def err(msg, code='error', status=400):
    return DomainError(msg, code, status)


def audit(actor, entity_type, entity_id, action, before=None, after=None):
    return AuditLog.objects.create(actor=actor, entity_type=entity_type, entity_id=str(entity_id),
                                   action=action, before=before, after=after)


def _managers():
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(role__in=('MANAGER', 'ADMIN'), is_active=True)


def event(order, type_, actor=None, from_status='', to_status='', reason='', payload=None):
    return OrderEvent.objects.create(order=order, actor=actor, type=type_, from_status=from_status,
                                     to_status=to_status, reason=reason or '', payload=payload or {})


def _bump(order, **fields):
    """Оптимистичная блокировка: обновление только если version не изменилась."""
    n = Order.objects.filter(pk=order.pk, version=order.version).update(
        version=F('version') + 1, updated_at=timezone.now(), **fields)
    if not n:
        raise err('Заказ был изменён другим пользователем. Обновите страницу.', 'version_conflict', 409)
    order.version += 1
    for k, v in fields.items():
        setattr(order, k, v)


def _check_access(order, user, role):
    if role == CLIENT and user is not None and order.client_id != user.id:
        raise err('Заказ не найден.', 'not_found', 404)


def can_pass_guard(order, to) -> bool:
    to = S(to)
    frm = S(order.status)
    if (frm, to) == (S.PAID, S.DISTRIBUTED) and not scheduling_services.current_assignment(order):
        return False
    if (frm, to) == (S.PRINTING, S.POST_PROCESSING) and not order.post_processings.exists():
        return False
    if (frm, to) == (S.PRINTING, S.READY) and order.post_processings.exists():
        return False
    if (frm, to) == (S.CHECKED, S.AWAITING_PAYMENT) and not pricing_services.current_quote(order):
        return False
    return True


def _guard(order, to):
    if (order.status, to) == (S.PAID, S.DISTRIBUTED) and not scheduling_services.current_assignment(order):
        raise err('Сначала назначьте принтер.', 'no_assignment', 409)
    if (order.status, to) == (S.PRINTING, S.POST_PROCESSING) and not order.post_processings.exists():
        raise err('Постобработка не выбрана — переходите сразу в «Готов к выдаче».', 'guard', 409)
    if (order.status, to) == (S.PRINTING, S.READY) and order.post_processings.exists():
        raise err('Выбрана постобработка — сначала переведите заказ в «Постобработка».', 'guard', 409)
    if (order.status, to) == (S.CHECKED, S.AWAITING_PAYMENT) and not pricing_services.current_quote(order):
        raise err('Невозможно отправить заказ на оплату без расчёта стоимости.', 'no_quote', 409)


NOTIFY_CLIENT = {S.CHECKED, S.CLARIFICATION, S.AWAITING_PAYMENT, S.PAID, S.DISTRIBUTED, S.PRINTING,
                 S.POST_PROCESSING, S.READY, S.COMPLETED, S.REJECTED, S.CANCELLED, S.MANUAL_REVIEW}


def transition(order, to, *, user=None, role=None, reason='', payload=None):
    role = norm_role(user, role)
    _check_access(order, user, role)
    to = S(to)
    rule = TRANSITIONS.get((S(order.status), to))
    if not rule:
        raise err(f'Переход «{S(order.status).label}» → «{to.label}» недопустим.', 'invalid_transition', 409)
    roles, reason_roles = rule
    if role not in roles:
        raise err('Недостаточно прав для этого перехода.', 'forbidden', 403)
    if role in reason_roles and not (reason or '').strip():
        raise err('Необходимо указать причину.', 'reason_required', 400)
    _guard(order, to)
    prev = order.status
    extra = {}
    if to == S.REJECTED:
        extra['reject_reason'] = reason
    _bump(order, status=to.value, **extra)
    if to in (S.CANCELLED, S.REJECTED):
        scheduling_services.clear_assignment(order)
    event(order, 'STATUS_CHANGED', user, prev, to.value, reason, payload)
    if to in NOTIFY_CLIENT and role != CLIENT:
        text = f'Заказ {order.number}: статус изменён на «{to.label}».'
        if reason and to in (S.REJECTED, S.CLARIFICATION, S.CANCELLED):
            text += f' {reason}'
        notification_services.notify(order.client, text, order)
    if to in (S.MANUAL_REVIEW, S.PAID) or (prev == S.CLARIFICATION and to == S.NEW):
        for m in _managers():
            notification_services.notify(m, f'Заказ {order.number}: «{to.label}».', order)
    return order


def _next_number():
    today = timezone.localdate()
    prefix = f'3DP-{today:%y%m%d}-'
    last = Order.objects.filter(number__startswith=prefix).order_by('-number').first()
    seq = 1
    if last:
        try:
            seq = int(last.number.rsplit('-', 1)[-1]) + 1
        except ValueError:
            seq = Order.objects.filter(created_at__date=today).count() + 1
    return f'{prefix}{seq:04d}'


PARAM_MODELS = {
    'technology': (catalog_models.Technology, True),
    'material': (catalog_models.Material, True),
    'quality_profile': (catalog_models.QualityProfile, False),
    'color': (catalog_models.Color, False),
    'delivery_method': (catalog_models.DeliveryMethod, True),
    'pickup_point': (catalog_models.PickupPoint, True),
}
PARAM_FIELDS = tuple(PARAM_MODELS.keys())


def desired_date_ok(d):
    return d is None or d >= timezone.localdate()


@transaction.atomic
def create_draft(client, data=None):
    order = None
    for _ in range(10):
        try:
            with transaction.atomic():
                order = Order.objects.create(client=client, number=_next_number(), status=S.DRAFT)
            break
        except IntegrityError:
            continue
    if not order:
        raise err('Не удалось сформировать номер заказа.')
    event(order, 'CREATED', client, '', S.DRAFT)
    if data:
        update_draft(order, client, data, recalc=False)
    return order


@transaction.atomic
def update_draft(order, user, data, recalc=True):
    if order.status != S.DRAFT:
        raise err('Параметры можно менять только в черновике.', 'not_draft', 409)
    _check_access(order, user, CLIENT)
    ver = data.get('version')
    if ver is not None:
        try:
            ver_int = int(ver)
        except (TypeError, ValueError):
            raise err('Некорректная версия заказа.', 'validation')
        if ver_int != order.version:
            raise err('Заказ был изменён в другом окне. Обновите страницу.', 'version_conflict', 409)
    fields = {}
    if 'quantity' in data:
        try:
            qty = int(data['quantity'])
        except (TypeError, ValueError):
            raise err('Количество должно быть целым числом.', 'validation')
        if qty < 1:
            raise err('Количество должно быть не меньше 1.', 'validation')
        fields['quantity'] = qty
    if 'delivery_address' in data:
        fields['delivery_address'] = str(data['delivery_address'] or '').strip()[:255]
    if 'comment' in data:
        fields['comment'] = str(data['comment'] or '')
    if 'desired_date' in data:
        raw_d = data['desired_date']
        if not raw_d:
            fields['desired_date'] = None
        else:
            d = raw_d if isinstance(raw_d, datetime.date) else parse_date(str(raw_d))
            if not d:
                raise err('Некорректный формат желаемой даты.', 'validation')
            if not desired_date_ok(d):
                raise err('Желаемая дата не может быть в прошлом.', 'validation')
            fields['desired_date'] = d
    for key, (model_cls, has_active) in PARAM_MODELS.items():
        if key in data:
            val = data[key]
            if not val:
                fields[key + '_id'] = None
            else:
                qs = model_cls.objects.filter(pk=val)
                if has_active:
                    qs = qs.filter(is_active=True)
                try:
                    obj = qs.first()
                except Exception:
                    obj = None
                if not obj:
                    raise err(f'Недопустимое или неактивное значение справочника ({key}).', 'validation')
                fields[key + '_id'] = obj.pk
    if fields:
        _bump(order, **fields)
        order.refresh_from_db()
    if 'post_processing' in data:
        from .models import OrderPostProcessing
        pp_ids = data['post_processing'] or []
        if not isinstance(pp_ids, (list, tuple)):
            raise err('Список опций постобработки должен быть массивом.', 'validation')
        valid_pps = []
        for pid in pp_ids:
            try:
                p_obj = catalog_models.PostProcessing.objects.filter(pk=pid, is_active=True).first()
            except Exception:
                p_obj = None
            if not p_obj:
                raise err('Выбрана недействительная опция постобработки.', 'validation')
            valid_pps.append(p_obj)
        OrderPostProcessing.objects.filter(order=order).delete()
        for p_obj in valid_pps:
            OrderPostProcessing.objects.create(order=order, post_processing=p_obj)
    if recalc:
        process_order(order.pk)
    return order


@transaction.atomic
def attach_model(order, user, file_name, data):
    if order.status not in (S.DRAFT, S.CLARIFICATION):
        raise err('Загрузить модель можно только в черновике или при уточнении.', 'bad_status', 409)
    _check_access(order, user, CLIENT)
    mv = model_services.add_version(order, file_name, data)
    if order.status == S.CLARIFICATION:
        transition(order, S.NEW, user=user, reason=f'Загружена новая версия модели (v{mv.version})')
    enqueue_process(order.pk)
    return mv


def process_order(order_id):
    """Валидация + расчёт (+ автопереход NEW → CHECKED/MANUAL_REVIEW). Защищено от сбоев."""
    order = Order.objects.select_related('technology', 'material', 'quality_profile', 'color',
                                         'delivery_method', 'pickup_point', 'client').get(pk=order_id)
    mv = model_services.current_version(order)
    if not mv:
        return None
    try:
        vr = validation_services.validate(order, mv)
        quote = None
        try:
            quote = pricing_services.calculate(order, mv, needs_support=vr.needs_support)
        except (pricing_services.QuoteError, DomainError):
            quote = None
        if order.status == S.NEW:
            if vr.verdict != 'ERROR' and quote:
                transition(order, S.CHECKED, role=SYSTEM)
            else:
                transition(order, S.MANUAL_REVIEW, role=SYSTEM)
        return vr, quote
    except Exception as exc:
        logger.exception('Ошибка при автоматической проверке/расчёте заказа %s: %s', order.number, exc)
        if order.status == S.NEW:
            transition(order, S.MANUAL_REVIEW, role=SYSTEM, reason='Ошибка автоматической обработки')
        return None


def quote_state(order):
    mv = model_services.current_version(order)
    vr = validation_services.latest_for(mv) if mv else None
    quote = pricing_services.current_quote(order)
    return mv, vr, quote, bool(mv and vr)


def confirm(order, user):
    _check_access(order, user, CLIENT)
    if order.status != S.DRAFT:
        raise err('Подтвердить можно только черновик.', 'not_draft', 409)
    mv = model_services.current_version(order)
    if not mv:
        raise err('Загрузите 3D-модель.', 'no_model')
    missing = [n for n, v in (('технология', order.technology_id), ('материал', order.material_id),
                              ('качество', order.quality_profile_id), ('цвет', order.color_id),
                              ('способ получения', order.delivery_method_id)) if not v]
    if missing:
        raise err('Не заполнено: ' + ', '.join(missing) + '.', 'incomplete')
    if order.delivery_method.type == 'PICKUP' and not order.pickup_point_id:
        raise err('Выберите пункт выдачи.', 'incomplete')
    transition(order, S.NEW, user=user)
    enqueue_process(order.pk)
    return order


def enqueue_process(order_id):
    from config.tasks import enqueue
    enqueue('orders.services.process_order', str(order_id))


def cancel(order, user, reason=''):
    return transition(order, S.CANCELLED, user=user, reason=reason)


@transaction.atomic
def pay(order, user):
    Order.objects.select_for_update().filter(pk=order.pk).first()
    _check_access(order, user, CLIENT)
    if order.status != S.AWAITING_PAYMENT:
        raise err('Оплата доступна только для заказов в статусе «Ожидает оплаты».', 'bad_status', 409)
    quote = pricing_services.current_quote(order)
    if not quote:
        raise err('Расчёт стоимости для заказа отсутствует.', 'no_quote', 409)
    payment_services.pay(order, quote.total)
    return transition(order, S.PAID, user=user)


@transaction.atomic
def repeat(order, user):
    _check_access(order, user, CLIENT)
    new = create_draft(user)
    fields = {k + '_id': getattr(order, k + '_id') for k in PARAM_FIELDS}
    fields.update(quantity=order.quantity, delivery_address=order.delivery_address, comment=order.comment)
    _bump(new, **fields)
    new.refresh_from_db()
    from .models import OrderPostProcessing
    for pp in order.post_processings.all():
        OrderPostProcessing.objects.create(order=new, post_processing=pp)
    model_services.clone_current(order, new)
    event(new, 'REPEATED', user, payload={'source': str(order.pk)})
    process_order(new.pk)
    return new


@transaction.atomic
def post_message(order, user, text, file_name=None, file_bytes=None):
    role = norm_role(user)
    _check_access(order, user, role)
    text = (text or '').strip()
    if not text and not file_bytes:
        raise err('Введите текст сообщения или приложите модель.', 'validation')
    mv = None
    if file_bytes is not None:
        if order.status not in (S.DRAFT, S.CLARIFICATION, S.MANUAL_REVIEW):
            raise err('В текущем статусе новую версию модели загрузить нельзя.', 'bad_status', 409)
        mv = model_services.add_version(order, file_name or 'model', file_bytes)
        text = text or f'Загружена новая версия модели (v{mv.version}).'
    msg = messaging_services.post(order, user, text, mv)
    event(order, 'MESSAGE', user, payload={'model_version': mv.version if mv else None})
    if role == CLIENT:
        for m in _managers():
            notification_services.notify(m, f'Заказ {order.number}: новое сообщение от клиента.', order)
        if order.status == S.CLARIFICATION:
            transition(order, S.NEW, user=user)
            enqueue_process(order.pk)
        elif mv is not None:
            enqueue_process(order.pk)
    else:
        notification_services.notify(order.client, f'Заказ {order.number}: новое сообщение от менеджера.', order)
        if mv is not None:
            enqueue_process(order.pk)
    return msg


@transaction.atomic
def decision(order, user, action, reason=''):
    Order.objects.select_for_update().filter(pk=order.pk).first()
    st = S(order.status)
    if action == 'approve':
        quote = pricing_services.current_quote(order)
        if st == S.MANUAL_REVIEW:
            if not quote and order.technology_id and order.material_id and order.quality_profile_id and order.delivery_method_id:
                mv = model_services.current_version(order)
                if mv and (mv.volume_cm3 or 0) > 0:
                    vr = validation_services.latest_for(mv)
                    quote = pricing_services.calculate(order, mv, needs_support=bool(vr and vr.needs_support))
            if not quote:
                raise err('Невозможно одобрить заказ без расчёта стоимости.', 'no_quote', 409)
            transition(order, S.CHECKED, user=user, reason=reason)
        elif st == S.CHECKED:
            if not quote:
                raise err('Невозможно отправить заказ на оплату без расчёта стоимости.', 'no_quote', 409)
            transition(order, S.AWAITING_PAYMENT, user=user, reason=reason)
            if not payment_services.stub_enabled():
                payment_services.pay(order, quote.total)
                transition(order, S.PAID, role=SYSTEM, reason='Автооплата (заглушка отключена)')
        else:
            raise err('Одобрение возможно из статусов «Ручная проверка» и «Проверен».', 'invalid_transition', 409)
    elif action == 'reject':
        transition(order, S.REJECTED, user=user, reason=reason)
    elif action == 'clarify':
        transition(order, S.CLARIFICATION, user=user, reason=reason)
        messaging_services.post(order, user, reason)
    else:
        raise err('Неизвестное решение.', 'validation')
    return order


@transaction.atomic
def change_status(order, user, to, reason=''):
    Order.objects.select_for_update().filter(pk=order.pk).first()
    transition(order, to, user=user, reason=reason)
    if order.status == S.AWAITING_PAYMENT and not payment_services.stub_enabled():
        quote = pricing_services.current_quote(order)
        if quote:
            payment_services.pay(order, quote.total)
            transition(order, S.PAID, role=SYSTEM, reason='Автооплата (заглушка отключена)')
    return order


@transaction.atomic
def set_priority(order, user, priority):
    if user.role not in ('MANAGER', 'ADMIN'):
        raise err('Недостаточно прав.', 'forbidden', 403)
    try:
        p = int(priority)
    except (TypeError, ValueError):
        raise err('Приоритет должен быть целым числом (0 или 1).', 'validation')
    if p not in (0, 1):
        raise err('Допустимые значения приоритета: 0 (обычный), 1 (высокий).', 'validation')
    _bump(order, priority=p)
    event(order, 'PRIORITY_CHANGED', user, payload={'priority': p})
    return order


def recommendation(order):
    mv, vr, quote, _ = quote_state(order)
    if not mv or not quote or not (order.technology_id and order.material_id):
        raise err('Недостаточно данных для рекомендации (нет модели или расчёта).', 'no_quote', 409)
    bbox = [mv.bbox_x, mv.bbox_y, mv.bbox_z]
    return scheduling_services.recommend(technology=order.technology, material=order.material, color=order.color,
                                         bbox=bbox, print_hours=quote.print_hours, exclude_order=order)


@transaction.atomic
def assign_printer(order, user, printer_id, reason=''):
    Order.objects.select_for_update().filter(pk=order.pk).first()
    if order.status not in (S.PAID, S.DISTRIBUTED):
        raise err('Назначение принтера возможно для заказов в статусах «Оплачен» и «Распределён».', 'bad_status', 409)
    if not printer_id:
        raise err('Укажите принтер.', 'validation')
    rec = recommendation(order)
    pid = str(printer_id)
    for ex in rec['excluded']:
        if ex['printer_id'] == pid:
            raise err('Принтер не подходит: ' + ex['reason'], 'printer_ineligible')
    top_ids = [r['printer_id'] for r in rec['top']]
    all_ids = top_ids + [r['printer_id'] for r in rec['others']]
    if pid not in all_ids:
        raise err('Принтер не найден среди подходящих.', 'printer_ineligible')
    manual = pid not in top_ids
    if manual and not (reason or '').strip():
        raise err('Для выбора принтера вне тройки рекомендаций укажите причину.', 'reason_required')
    printer = scheduling_services.get_printer(pid)
    quote = pricing_services.current_quote(order)
    a = scheduling_services.assign(order=order, printer=printer, print_hours=quote.print_hours,
                                   actor_reason=reason, is_manual=manual)
    _bump(order, planned_date=a.planned_end.date())
    event(order, 'ASSIGNED', user, reason=reason, payload={'printer': printer.name, 'manual': manual})
    if order.status == S.PAID:
        transition(order, S.DISTRIBUTED, user=user)
    return a


@transaction.atomic
def adjust_price(order, user, amount, reason):
    if user.role != 'ADMIN':
        raise err('Корректировка цены доступна только администратору.', 'forbidden', 403)
    if not (reason or '').strip():
        raise err('Укажите причину корректировки.', 'reason_required')
    Order.objects.select_for_update().filter(pk=order.pk).first()
    if order.status not in (S.MANUAL_REVIEW, S.CHECKED, S.CLARIFICATION):
        raise err('Корректировка возможна до отправки на оплату.', 'bad_status', 409)
    before = pricing_services.current_quote(order)
    if not before:
        raise err('Расчёт отсутствует.', 'no_quote', 409)
    before_total, before_adj = str(before.total), str(before.adjustment)
    q = pricing_services.apply_adjustment(order, amount)
    event(order, 'PRICE_ADJUSTED', user, reason=reason,
          payload={'adjustment': str(q.adjustment), 'total': str(q.total)})
    audit(user, 'Quote', q.pk, 'ADJUSTMENT', {'total': before_total, 'adjustment': before_adj},
          {'total': str(q.total), 'adjustment': str(q.adjustment), 'reason': reason})
    return q


# ---------- Публичные сервисы для интеграционного контура (без прямого импорта моделей) ----------
INTEGRATION_STATUSES = ('PAID', 'DISTRIBUTED', 'PRINTING', 'POST_PROCESSING', 'READY')


def list_for_integration():
    from .serializers import integration_dto
    qs = (Order.objects.filter(status__in=INTEGRATION_STATUSES)
          .select_related('client', 'material', 'technology', 'quality_profile', 'color', 'delivery_method')
          .prefetch_related('post_processings', 'events__actor'))
    return [integration_dto(o) for o in qs]


@transaction.atomic
def integration_update_by_id(pk, to, payload=None):
    order = Order.objects.select_for_update().filter(pk=pk).first()
    if not order:
        return None
    transition(order, to, role=INTEGRATION, payload=payload or {})
    return order


def _actual_metrics(order):
    actual_h, actual_m = None, None
    for ev in order.events.all():
        p = ev.payload or {}
        if p.get('actual_print_hours') is not None:
            actual_h = p.get('actual_print_hours')
        if p.get('actual_mass_g') is not None:
            actual_m = p.get('actual_mass_g')
    return actual_h, actual_m


def export_orders_rows():
    qs = (Order.objects.exclude(status='DRAFT')
          .select_related('client', 'material', 'technology')
          .prefetch_related('events', 'quotes'))
    rows = []
    for o in qs:
        q = pricing_services.current_quote(o)
        actual_h, actual_m = _actual_metrics(o)
        rows.append({
            'number': o.number,
            'status': o.status,
            'client': o.client.email,
            'quantity': o.quantity,
            'technology': o.technology.code if o.technology else '',
            'material': o.material.name if o.material else '',
            'planned_print_hours': float(q.print_hours) if q else '',
            'planned_mass_g': float(q.mass_g) if q else '',
            'actual_print_hours': actual_h if actual_h is not None else '',
            'actual_mass_g': actual_m if actual_m is not None else '',
            'total': int(q.total) if q else '',
            'created_at': o.created_at.isoformat(),
        })
    return rows


def export_events_rows():
    return [{'order': e.order.number, 'type': e.type, 'from': e.from_status, 'to': e.to_status,
             'reason': e.reason, 'created_at': e.created_at.isoformat()}
            for e in OrderEvent.objects.select_related('order')]


__all__ = ['catalog_services']


def integration_update(order, to, payload=None):
    return integration_update_by_id(order.pk, to, payload)
