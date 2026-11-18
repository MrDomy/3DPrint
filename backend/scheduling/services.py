"""Публичный интерфейс планирования: жёсткий фильтр, скоринг, загрузка оборудования (спец. 6.4)."""
from datetime import timedelta

from django.utils import timezone

from catalog.constants import MATERIAL_HS_RESIN, TECH_DMLS
from catalog.models import Printer, Workshop

from .models import Assignment

HORIZON_HOURS = 140.0
ACTIVE_ORDER_STATUSES = ('DISTRIBUTED', 'PRINTING', 'POST_PROCESSING')


def fits(dims_sorted, bbox):
    b = sorted(float(x) for x in bbox)
    return all(b[i] <= dims_sorted[i] + 1e-9 for i in range(3))


def required_specialization(technology, material, bbox):
    """Возвращает код требуемой специализации или None."""
    if technology.code == TECH_DMLS:
        return Printer.Specialization.METAL
    if material and material.name == MATERIAL_HS_RESIN:
        return Printer.Specialization.HIGH_STRENGTH_RESIN
    plain = Printer.objects.filter(technology=technology, status=Printer.Status.ACTIVE).exclude(
        specialization=Printer.Specialization.LARGE)
    if bbox and not any(fits(p.dims_sorted, bbox) for p in plain):
        return Printer.Specialization.LARGE
    return None


def _t_free_hours(printer, now):
    last = (Assignment.objects.filter(printer=printer, is_current=True, order__status__in=ACTIVE_ORDER_STATUSES
                                      + ('PAID',))
            .order_by('-planned_end').values_list('planned_end', flat=True).first())
    if not last or last <= now:
        return 0.0
    return (last - now).total_seconds() / 3600.0


def _last_material(printer):
    a = (Assignment.objects.filter(printer=printer, is_current=True).select_related('order__material')
         .order_by('-planned_end').first())
    return a.order.material_id if a else None


def eligible_printers(*, technology, material, color, bbox):
    """Жёсткий фильтр. Возвращает (подходящие, исключённые с причинами)."""
    need = required_specialization(technology, material, bbox)
    ok, excluded = [], []
    for p in Printer.objects.select_related('workshop', 'technology').filter(technology=technology):
        reason = None
        if p.status != Printer.Status.ACTIVE:
            reason = 'Принтер недоступен (не в статусе «Активен»).'
        elif material is not None and not p.materials.filter(pk=material.pk).exists():
            reason = 'Принтер не поддерживает выбранный материал.'
        elif material is not None and color is not None and not material.colors.filter(pk=color.pk).exists():
            reason = 'Выбранный цвет недоступен для материала.'
        elif bbox and not fits(p.dims_sorted, bbox):
            reason = 'Модель не помещается в область печати.'
        elif need and p.specialization != need:
            reason = 'Требуется принтер со специализацией «%s».' % Printer.Specialization(need).label
        elif p.specialization != Printer.Specialization.NONE and not p.workshop.is_main:
            reason = 'Специализированные принтеры допускаются только в основном цехе.'
        if reason:
            excluded.append({'printer_id': str(p.id), 'printer': p.name, 'reason': reason})
        else:
            ok.append(p)
    return ok, excluded, need


def recommend(*, technology, material, color, bbox, print_hours, now=None):
    now = now or timezone.now()
    ok, excluded, need = eligible_printers(technology=technology, material=material, color=color, bbox=bbox)
    rows = []
    for p in ok:
        t_free = _t_free_hours(p, now)
        last_mat = _last_material(p)
        change = 2 if (last_mat is not None and material is not None and last_mat != material.pk) else 0
        spec_pen = 24 if (p.specialization != Printer.Specialization.NONE and not need) else 0
        score = t_free + float(print_hours) + change + spec_pen
        start = now + timedelta(hours=t_free)
        rows.append({'printer_id': str(p.id), 'printer': p.name, 'workshop': p.workshop.name,
                     'score': round(score, 2), 't_free_h': round(t_free, 2),
                     'planned_start': start, 'planned_end': start + timedelta(hours=float(print_hours))})
    rows.sort(key=lambda r: (r['score'], r['printer'], r['printer_id']))
    return {'top': rows[:3], 'others': rows[3:], 'excluded': excluded}


def queue_wait_hours(*, technology, material, color, bbox, now=None):
    """W — ожидание в очереди наименее загруженного подходящего принтера (0, если свободен)."""
    now = now or timezone.now()
    ok, _, _ = eligible_printers(technology=technology, material=material, color=color, bbox=bbox)
    if not ok:
        return 0.0
    return min(_t_free_hours(p, now) for p in ok)


def has_eligible(*, technology, material, color, bbox):
    ok, _, _ = eligible_printers(technology=technology, material=material, color=color, bbox=bbox)
    return bool(ok)


def fits_any_active(*, technology, bbox):
    return any(fits(p.dims_sorted, bbox) for p in
               Printer.objects.filter(technology=technology, status=Printer.Status.ACTIVE))


def assign(*, order, printer, print_hours, actor_reason='', is_manual=False, now=None):
    now = now or timezone.now()
    Assignment.objects.filter(order=order, is_current=True).update(is_current=False)
    start = now + timedelta(hours=_t_free_hours(printer, now))
    return Assignment.objects.create(order=order, printer=printer, planned_start=start,
                                     planned_end=start + timedelta(hours=float(print_hours)),
                                     is_manual=is_manual, reason=actor_reason, is_current=True)


def current_assignment(order):
    return Assignment.objects.filter(order=order, is_current=True).select_related('printer__workshop').first()


def equipment_load(now=None):
    now = now or timezone.now()
    horizon_end = now + timedelta(days=7)
    printers_out, per_workshop = [], {}
    for p in Printer.objects.select_related('workshop', 'technology').order_by('workshop__name', 'name'):
        hours = 0.0
        jobs = []
        qs = Assignment.objects.filter(printer=p, is_current=True, planned_end__gt=now, planned_start__lt=horizon_end,
                                       order__status__in=('PAID', ) + ACTIVE_ORDER_STATUSES).select_related('order')
        for a in qs:
            s, e = max(a.planned_start, now), min(a.planned_end, horizon_end)
            h = max(0.0, (e - s).total_seconds() / 3600.0)
            hours += h
            jobs.append({'order_id': str(a.order_id), 'number': a.order.number, 'hours': round(h, 2)})
        hours = min(hours, HORIZON_HOURS)
        row = {'printer_id': str(p.id), 'printer': p.name, 'workshop': p.workshop.name,
               'workshop_id': str(p.workshop_id), 'technology': p.technology.code, 'status': p.status,
               'planned_hours': round(hours, 2), 'idle_hours': round(HORIZON_HOURS - hours, 2),
               'load_percent': round(hours / HORIZON_HOURS * 100, 1), 'jobs': jobs}
        printers_out.append(row)
        if p.status == Printer.Status.ACTIVE:
            per_workshop.setdefault(p.workshop_id, []).append(row['load_percent'])
    workshops = []
    for w in Workshop.objects.all():
        vals = per_workshop.get(w.id, [])
        workshops.append({'workshop_id': str(w.id), 'workshop': w.name,
                          'load_percent': round(sum(vals) / len(vals), 1) if vals else 0.0})
    return {'horizon_hours': HORIZON_HOURS, 'printers': printers_out, 'workshops': workshops}


def get_printer(pk):
    return Printer.objects.get(pk=pk)
