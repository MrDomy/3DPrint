from django.db import models

from config.base import BaseModel


class ModelVersion(BaseModel):
    class Format(models.TextChoices):
        STL = 'STL', 'STL'
        OBJ = 'OBJ', 'OBJ'
        THREEMF = '3MF', '3MF'

    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='model_versions')
    version = models.PositiveIntegerField()
    file_name = models.CharField(max_length=255)
    format = models.CharField(max_length=4, choices=Format.choices)
    size_bytes = models.BigIntegerField()
    storage_key = models.CharField(max_length=128, unique=True)
    bbox_x = models.FloatField(null=True, blank=True)
    bbox_y = models.FloatField(null=True, blank=True)
    bbox_z = models.FloatField(null=True, blank=True)
    volume_cm3 = models.FloatField(null=True, blank=True)
    body_count = models.PositiveIntegerField(default=1)
    analysis = models.JSONField(default=dict, blank=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = 'model_version'
        constraints = [models.UniqueConstraint(fields=['order', 'version'], name='uniq_order_model_version')]
        ordering = ['-version']
