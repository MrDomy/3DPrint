from django.db import models

from config.base import BaseModel


class Assignment(BaseModel):
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='assignments')
    printer = models.ForeignKey('catalog.Printer', on_delete=models.PROTECT, related_name='assignments')
    planned_start = models.DateTimeField()
    planned_end = models.DateTimeField()
    is_manual = models.BooleanField(default=False)
    reason = models.TextField(blank=True, default='')
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = 'assignment'
        indexes = [models.Index(fields=['printer', 'planned_start'])]
