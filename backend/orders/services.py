"""Оркестрация заказов: FSM (14 статусов), валидация/расчёт, решения менеджера, назначение.
Взаимодействие с другими модулями — только через их публичные services.py."""
import datetime

from django.db import transaction
from django.db.models import F
from django.utils import timezone

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

S = Status
CLIENT, MANAGER, SYSTEM, INTEGRATION = 'CLIENT', 'MANAGER', 'SYSTEM', 'INTEGRATION'
FINAL = {S.COMPLETED, S.REJECTED, S.CANCELLED}

# (from, to) -> (роли, причина обязательна для ролей)
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


def _guard(order, to):
    if (order.status, to) == (S.PAID, S.DISTRIBUTED) and not scheduling_services.current_assignment(order):
        raise err('Сначала назначьте принтер.', 'no_assignment', 409)
    if (order.status, to) == (S.PRINTING, S.POST_PROCESSING) and not order.post_processings.exists():
        raise err('Постобработка не выбрана — переходите сразу в «Готов к выдаче».', 'guard', 409)
    if (order.status, to) == (S.PRINTING, S.READY) and order.post_processings.exists():
        raise err('Выбрана постобработка — сначала переведите заказ в «Постобработка».', 'guard', 409)


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


# ---------- Черновик ----------
def _new_number():
    today = timezone.localdate()
    base = Order.objects.filter(created_at__date=today).count() + 1
    for i in range(base, base + 50):
        n = f'3DP-{today:%y%m%d}-{i:04d}'
        if not Order.objects.filter(number=n).exists():
            return n
    raise err('Не удалось сформировать номер заказа.')


PARAM_FIELDS = ('technology', 'material', 'quality_profile', 'color', 'delivery_method', 'pickup_point')


@transaction.atomic
def create_draft(client, data=None):
    order = Order.objects.create(client=client, number=_new_number(), status=S.DRAFT)
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
    if ver is not None and int(ver) != order.version:
        raise err('Заказ был изменён в другом окне. Обновите страницу.', 'version_conflict', 409)
    fields = {}
    for key in ('quantity', 'delivery_address', 'desired_date', 'comment'):
        if key in data:
            fields[key] = data[key]
    if 'quantity' in fields and int(fields['quantity']) < 1:
        raise err('Количество должно быть не меньше 1.', 'validation')
    for key in PARAM_FIELDS:
        if key in data:
            fields[key + '_id'] = data[key] or None
    if fields:
        _bump(order, **fields)
        order.refresh_from_db()
    if 'post_processing' in data:
        from .models import OrderPostProcessing
        OrderPostProcessing.objects.filter(order=order).delete()
        for pid in data['post_processing'] or []:
            OrderPostProcessing.objects.create(order=order, post_processing_id=pid)
    if recalc:
        process_order(order.pk)
    return order


@transaction.atomic
def attach_model(order, user, file_name, data):
    if order.status not in (S.DRAFT, S.CLARIFICATION):
        raise err('Загрузить модель можно только в черновике или при уточнении.', 'bad_status', 409)
    _check_access(order, user, CLIENT)
    return model_services.add_version(order, file_name, data)


# ---------- Валидация и расчёт ----------
def process_order(order_id):
    """Валидация + расчёт (+ автопереход NEW → CHECKED/MANUAL_REVIEW). Выполняется воркером."""
    order = Order.objects.select_related('technology', 'material', 'quality_profile', 'color',
                                         'delivery_method', 'pickup_point', 'client').get(pk=order_id)
    mv = model_services.current_version(order)
    if not mv:
        return None
    vr = validation_services.validate(order, mv)
    quote = None
    try:
        quote = pricing_services.calculate(order, mv, needs_support=vr.needs_support)
    except pricing_services.QuoteError:
        quote = None
    if order.status == S.NEW:
        if vr.verdict != 'ERROR' and quote:
            transition(order, S.CHECKED, role=SYSTEM)
        else:
            transition(order, S.MANUAL_REVIEW, role=SYSTEM)
    return vr, quote


def quote_state(order):
    mv = model_services.current_version(order)
    vr = validation_services.latest_for(mv) if mv else None
    quote = pricing_services.current_quote(order)
    return mv, vr, quote, bool(mv and vr)


# ---------- Клиентские действия ----------
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


def pay(order, user):
    _check_access(order, user, CLIENT)
    if order.status != S.AWAITING_PAYMENT:
        raise err('Оплата доступна только для заказов в статусе «Ожидает оплаты».', 'bad_status', 409)
    quote = pricing_services.current_quote(order)
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


# ---------- Сообщения ----------
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
    else:
        notification_services.notify(order.client, f'Заказ {order.number}: новое сообщение от менеджера.', order)
    return msg


# ---------- Менеджер / администратор ----------
def decision(order, user, action, reason=''):
    st = S(order.status)
    if action == 'approve':
        if st == S.MANUAL_REVIEW:
            transition(order, S.CHECKED, user=user, reason=reason)
        elif st == S.CHECKED:
            transition(order, S.AWAITING_PAYMENT, user=user, reason=reason)
            if not payment_services.stub_enabled():
                quote = pricing_services.current_quote(order)
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


def change_status(order, user, to, reason=''):
    return transition(order, to, user=user, reason=reason)


def recommendation(order):
    mv, vr, quote, _ = quote_state(order)
    if not mv or not quote or not (order.technology_id and order.material_id):
        raise err('Недостаточно данных для рекомендации (нет модели или расчёта).', 'no_quote', 409)
    bbox = [mv.bbox_x, mv.bbox_y, mv.bbox_z]
    return scheduling_services.recommend(technology=order.technology, material=order.material, color=order.color,
                                         bbox=bbox, print_hours=quote.print_hours)


@transaction.atomic
def assign_printer(order, user, printer_id, reason=''):
    if order.status not in (S.PAID, S.DISTRIBUTED):
        raise err('Назначение принтера возможно для заказов в статусах «Оплачен» и «Распределён».', 'bad_status', 409)
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
    if order.status not in (S.MANUAL_REVIEW, S.CHECKED, S.CLARIFICATION):
        raise err('Корректировка возможна до отправки на оплату.', 'bad_status', 409)
    before = pricing_services.current_quote(order)
    q = pricing_services.apply_adjustment(order, amount)
    event(order, 'PRICE_ADJUSTED', user, reason=reason,
          payload={'adjustment': str(amount), 'total': str(q.total)})
    audit(user, 'Quote', q.pk, 'ADJUSTMENT', {'total': str(before.total), 'adjustment': str(before.adjustment)},
          {'total': str(q.total), 'adjustment': str(q.adjustment), 'reason': reason})
    return q


def integration_update(order, to, payload=None):
    transition(order, to, role=INTEGRATION, payload=payload or {})
    return order


def desired_date_ok(d):
    return d is None or d >= datetime.date.today()


__all__ = ['catalog_services']
