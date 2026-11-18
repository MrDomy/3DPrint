from django.db import models

from config.base import BaseModel


class Payment(BaseModel):
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    provider = models.CharField(max_length=32, default='STUB')
    status = models.CharField(max_length=16, default='PENDING')

    class Meta:
        db_table = 'payment'
