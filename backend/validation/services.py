"""Публичный интерфейс валидации: проверки E-03..E-06 и предупреждения W-01..W-05."""
from catalog import services as catalog_services
from catalog.constants import PP_ASSEMBLY
from pricing.services import get_tariff_params
from scheduling import services as scheduling_services

from .models import ValidationResult

DEFAULT_THIN = {'FDM': 0.8, 'SLA': 0.4, 'DMLS': 0.6}


def _issue(code, message):
    return {'code': code, 'message': message}


def validate(order, mv) -> ValidationResult:
    """Создаёт ValidationResult для текущей версии модели заказа."""
    params = get_tariff_params()
    issues, needs_support = [], False
    bbox = [mv.bbox_x or 0, mv.bbox_y or 0, mv.bbox_z or 0]
    an = mv.analysis or {}
    tech, material = order.technology, order.material
    pp_names = list(order.post_processings.values_list('name', flat=True))

    # --- ошибки ---
    if (mv.volume_cm3 or 0) <= 0 or (mv.body_count or 0) < 1:
        issues.append(_issue('E-03', 'Модель вырождена: нулевой объём или нет твёрдых тел.'))
    fits_tech = True
    if tech and not scheduling_services.fits_any_active(technology=tech, bbox=bbox):
        fits_tech = False
        issues.append(_issue('E-04', 'Габариты модели превышают область печати всех доступных принтеров '
                                     'выбранной технологии.'))
    compat = catalog_services.check_compatibility(
        technology=tech, material=material, quality_profile=order.quality_profile, color=order.color,
        post_processing_names=pp_names, model_format=mv.format, body_count=mv.body_count,
        delivery_method=order.delivery_method, pickup_point=order.pickup_point)
    for msg in compat:
        issues.append(_issue('E-05', msg))
    if tech and material and fits_tech and not compat and not scheduling_services.has_eligible(
            technology=tech, material=material, color=order.color, bbox=bbox):
        issues.append(_issue('E-06', 'Не найден принтер, удовлетворяющий жёстким условиям распределения.'))

    # --- предупреждения ---
    if an.get('watertight') is False:
        msg = 'Сетка не замкнута (есть отверстия).'
        msg += ' Выполнено автоматическое исправление.' if an.get('repaired') else ''
        issues.append(_issue('W-01', msg))
    thin_map = params.get('thin_wall_mm', DEFAULT_THIN)
    if tech and an.get('min_thickness_mm') is not None and an['min_thickness_mm'] < thin_map.get(tech.code, 0.8):
        issues.append(_issue('W-02', 'Обнаружены слишком тонкие стенки для выбранной технологии.'))
    if (an.get('overhang_ratio') or 0) > 0.05:
        needs_support = True
        issues.append(_issue('W-03', 'Обнаружены нависания более 45°: потребуются поддержки.'))
    if (mv.body_count or 1) > 1 and PP_ASSEMBLY not in pp_names:
        issues.append(_issue('W-04', 'Модель состоит из нескольких несвязанных тел, а «Сборка» не выбрана.'))
    if bbox and (min(bbox) < 1 or max(bbox) > 1000):
        issues.append(_issue('W-05', 'Подозрительные единицы измерения: габарит < 1 мм или > 1000 мм.'))

    if any(i['code'].startswith('E-') for i in issues):
        verdict = ValidationResult.Verdict.ERROR
    elif issues:
        verdict = ValidationResult.Verdict.WARNING
    else:
        verdict = ValidationResult.Verdict.OK
    return ValidationResult.objects.create(model_version=mv, verdict=verdict, issues=issues,
                                           needs_support=needs_support)


def latest_for(mv):
    return ValidationResult.objects.filter(model_version=mv).order_by('-created_at').first()
