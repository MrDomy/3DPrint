"""Помощники тестов: заказ с синтетической моделью (без разбора сетки)."""
import uuid

from catalog.models import (Color, DeliveryMethod, Material, PickupPoint, PostProcessing, QualityProfile,
                            Technology)
from models_app.models import ModelVersion
from orders import services as os_
from orders.models import Order


def make_order(client, *, tech, material, quality, color, volume, bbox=(50, 50, 20), qty=1, pp=(),
               delivery='PICKUP', fmt='STL', bodies=1, analysis=None, status=None):
    t = Technology.objects.get(code=tech)
    m = Material.objects.get(name=material)
    q = QualityProfile.objects.get(technology=t, name=quality)
    c = Color.objects.get(name=color)
    dm = DeliveryMethod.objects.get(type=delivery)
    pickup = PickupPoint.objects.filter(delivery_method=dm).first() if delivery == 'PICKUP' else None
    o = os_.create_draft(client, {
        'technology': t.pk, 'material': m.pk, 'quality_profile': q.pk, 'color': c.pk, 'delivery_method': dm.pk,
        'pickup_point': pickup.pk if pickup else None, 'quantity': qty,
        'post_processing': [PostProcessing.objects.get(name=n).pk for n in pp]}, )
    ModelVersion.objects.create(order=o, version=1, file_name='m.' + fmt.lower(), format=fmt, size_bytes=1,
                                storage_key=f'models/{uuid.uuid4()}', bbox_x=bbox[0], bbox_y=bbox[1],
                                bbox_z=bbox[2], volume_cm3=volume, body_count=bodies,
                                analysis=analysis or {'watertight': True, 'min_thickness_mm': 5.0,
                                                      'overhang_ratio': 0.0}, is_current=True)
    o.refresh_from_db()
    return o


def run_to_result(order):
    """DRAFT -> NEW -> (CHECKED | MANUAL_REVIEW) как делает confirm()."""
    os_.confirm(order, order.client)
    order.refresh_from_db()
    return order
