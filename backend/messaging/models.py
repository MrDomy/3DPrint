from django.conf import settings
from django.db import models

from config.base import BaseModel


class Message(BaseModel):
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    text = models.TextField()
    model_version = models.ForeignKey('models_app.ModelVersion', null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='+')

    class Meta:
        db_table = 'message'
        ordering = ['created_at']
