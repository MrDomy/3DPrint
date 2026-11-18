"""Публичный интерфейс каталога: проверка совместимости параметров (спец. 6.2)."""
from .constants import COLOR_TRANSPARENT, PP_ASSEMBLY, PP_PAINTING, TECH_DMLS
from .models import (Color, DeliveryMethod, Material, PickupPoint, PostProcessing, QualityProfile,
                     Technology)


def check_compatibility(*, technology=None, material=None, quality_profile=None, color=None,
                        post_processing_names=(), model_format=None, body_count=1,
                        delivery_method=None, pickup_point=None):
    """Возвращает список русских сообщений о несовместимости (пустой список — всё хорошо)."""
    errors = []
    if technology and material and not material.technologies.filter(pk=technology.pk).exists():
        errors.append(f'Материал «{material.name}» не подходит для технологии {technology.code}.')
    if technology and quality_profile and quality_profile.technology_id != technology.pk:
        errors.append(f'Профиль качества «{quality_profile.name}» не относится к технологии {technology.code}.')
    if material and color and not material.colors.filter(pk=color.pk).exists():
        errors.append(f'Цвет «{color.name}» недоступен для материала «{material.name}».')
    names = set(post_processing_names)
    if PP_PAINTING in names:
        if technology and technology.code == TECH_DMLS:
            errors.append('Покраска недоступна для технологии DMLS.')
        if color and color.name.lower() == COLOR_TRANSPARENT:
            errors.append('Покраска недоступна для прозрачных материалов.')
    if PP_ASSEMBLY in names and not (model_format == '3MF' and (body_count or 1) > 1):
        errors.append('Сборка доступна только для 3MF-модели из нескольких тел.')
    if delivery_method and delivery_method.type == DeliveryMethod.Type.PICKUP:
        if not pickup_point or not pickup_point.is_active or pickup_point.delivery_method_id != delivery_method.pk:
            errors.append('Для самовывоза необходимо выбрать активный пункт выдачи.')
    return errors


def compatibility_matrix():
    """Данные для GET /api/catalog/compatibility — фронтенд только отображает правила."""
    techs = []
    for t in Technology.objects.filter(is_active=True).order_by('code'):
        mats = []
        for m in t.materials.filter(is_active=True).order_by('name'):
            mats.append({'id': str(m.id), 'colors': [str(c.id) for c in m.colors.all()]})
        techs.append({
            'id': str(t.id), 'code': t.code, 'materials': mats,
            'quality_profiles': [str(q.id) for q in t.quality_profiles.all()],
            'forbidden_post_processing': [PP_PAINTING] if t.code == TECH_DMLS else [],
        })
    return {
        'technologies': techs,
        'forbidden_post_processing_by_color': {COLOR_TRANSPARENT: [PP_PAINTING]},
        'assembly_requires': {'format': '3MF', 'min_bodies': 2, 'name': PP_ASSEMBLY},
        'max_upload_mb': 50,
        'formats': ['STL', 'OBJ', '3MF'],
    }


def get_active(model, pk):
    return model.objects.filter(pk=pk).first()


__all__ = ['check_compatibility', 'compatibility_matrix', 'Color', 'Material', 'PickupPoint',
           'PostProcessing', 'QualityProfile']
