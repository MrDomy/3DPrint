"""Публичный интерфейс расчёта стоимости и сроков (спец. 6.3)."""
from decimal import Decimal

from django.db import transaction

from scheduling import services as scheduling_services

from .formulas import compute_quote
from .models import DEFAULT_TARIFF_PARAMS, Quote, TariffVersion


def get_active_tariff() -> TariffVersion:
    t = TariffVersion.objects.filter(is_active=True).first()
    if not t:
        t = TariffVersion.objects.create(params=DEFAULT_TARIFF_PARAMS, is_active=True)
    return t


def get_tariff_params() -> dict:
    return {**DEFAULT_TARIFF_PARAMS, **(get_active_tariff().params or {})}


class QuoteError(Exception):
    pass


def current_quote(order):
    return Quote.objects.filter(order=order, is_current=True).first()


@transaction.atomic
def calculate(order, mv, needs_support=False, adjustment=None):
    """Считает и сохраняет Quote. Бросает QuoteError, если не хватает параметров."""
    if not (order.technology and order.material and order.quality_profile and order.delivery_method):
        raise QuoteError('Заполнены не все параметры заказа.')
    if not mv.volume_cm3 or mv.volume_cm3 <= 0:
        raise QuoteError('Объём модели не определён.')
    tariff = get_active_tariff()
    params = {**DEFAULT_TARIFF_PARAMS, **(tariff.params or {})}
    prev = current_quote(order)
    if adjustment is None:
        adjustment = prev.adjustment if prev else Decimal(0)
    pps = list(order.post_processings.all())
    bbox = [mv.bbox_x or 0, mv.bbox_y or 0, mv.bbox_z or 0]
    wait = scheduling_services.queue_wait_hours(technology=order.technology, material=order.material,
                                                color=order.color, bbox=bbox)
    tech, q, mat, dm = order.technology, order.quality_profile, order.material, order.delivery_method
    r = compute_quote(
        volume_cm3=mv.volume_cm3, quantity=order.quantity, needs_support=needs_support,
        density=mat.density, price_per_gram=mat.price_per_gram, fill_factor=tech.fill_factor,
        support_factor=tech.support_factor, flow_cm3_h=q.flow_cm3_h, hourly_rate=tech.hourly_rate,
        setup_cost=tech.setup_cost, price_factor=q.price_factor,
        post_prices=[p.price for p in pps], post_hours=[p.hours for p in pps],
        delivery_price=dm.price, delivery_days=dm.days, adjustment=adjustment, queue_wait_h=wait,
        c_min=params['min_order_cost'], printer_hours_per_day=params['printer_hours_per_day'],
        post_hours_per_day=params['post_hours_per_day'])
    Quote.objects.filter(order=order, is_current=True).update(is_current=False)
    return Quote.objects.create(
        order=order, tariff_version=tariff, cost_material=round(r.cost_material, 2),
        cost_machine=round(r.cost_machine, 2), cost_post=round(r.cost_post, 2),
        cost_delivery=round(r.cost_delivery, 2), adjustment=adjustment, total=r.total,
        print_hours=round(r.print_hours, 2), mass_g=round(r.mass_g, 2), estimated_days=r.estimated_days,
        is_current=True)


@transaction.atomic
def apply_adjustment(order, adjustment):
    """Корректировка цены администратором: пересчитывает итог с сохранением остальных частей."""
    q = current_quote(order)
    if not q:
        raise QuoteError('Расчёт отсутствует.')
    old_adj = q.adjustment
    q.is_current = False
    q.save(update_fields=['is_current', 'updated_at'])
    new_total = q.total - old_adj + Decimal(adjustment)
    return Quote.objects.create(
        order=order, tariff_version=q.tariff_version, cost_material=q.cost_material,
        cost_machine=q.cost_machine, cost_post=q.cost_post, cost_delivery=q.cost_delivery,
        adjustment=adjustment, total=round(new_total), print_hours=q.print_hours, mass_g=q.mass_g,
        estimated_days=q.estimated_days, is_current=True)
