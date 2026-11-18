"""Публичный интерфейс моделей: загрузка версии, метаданные, ссылка для 3D-просмотра."""
import uuid

from django.db import transaction

from validation import mesh

from . import storage
from .models import ModelVersion


@transaction.atomic
def add_version(order, file_name: str, data: bytes) -> ModelVersion:
    """E-01/E-02 поднимаются до создания записи — существующие данные заказа не затрагиваются."""
    fmt = mesh.check_upload(file_name, data)
    info = mesh.analyze(data, fmt)
    last = ModelVersion.objects.filter(order=order).order_by('-version').first()
    key = f'models/{uuid.uuid4()}'
    storage.put(key, data)
    ModelVersion.objects.filter(order=order, is_current=True).update(is_current=False)
    b = info['bbox']
    return ModelVersion.objects.create(
        order=order, version=(last.version + 1) if last else 1, file_name=file_name[:255], format=fmt,
        size_bytes=len(data), storage_key=key, bbox_x=b[0], bbox_y=b[1], bbox_z=b[2],
        volume_cm3=info['volume_cm3'], body_count=info['body_count'], analysis=info['analysis'], is_current=True)


def current_version(order):
    return ModelVersion.objects.filter(order=order, is_current=True).first()


def get_version(order, number):
    return ModelVersion.objects.filter(order=order, version=number).first()


def file_info(mv: ModelVersion) -> dict:
    return {'version': mv.version, 'file_name': mv.file_name, 'format': mv.format,
            'size_bytes': mv.size_bytes, 'url': storage.presigned_url(mv.storage_key, mv.file_name),
            'bbox': [mv.bbox_x, mv.bbox_y, mv.bbox_z], 'volume_cm3': mv.volume_cm3, 'body_count': mv.body_count}


def clone_current(src_order, dst_order):
    """Копирует текущую версию модели в другой заказ (повтор заказа)."""
    mv = current_version(src_order)
    if not mv:
        return None
    key = f'models/{uuid.uuid4()}'
    storage.put(key, storage.get(mv.storage_key))
    return ModelVersion.objects.create(
        order=dst_order, version=1, file_name=mv.file_name, format=mv.format, size_bytes=mv.size_bytes,
        storage_key=key, bbox_x=mv.bbox_x, bbox_y=mv.bbox_y, bbox_z=mv.bbox_z, volume_cm3=mv.volume_cm3,
        body_count=mv.body_count, analysis=mv.analysis, is_current=True)
