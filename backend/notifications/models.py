from django.conf import settings
from django.db import models

from config.base import BaseModel


class Notification(BaseModel):
    class Channel(models.TextChoices):
        EMAIL = 'EMAIL', 'Email'
        INAPP = 'INAPP', 'В приложении'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    order = models.ForeignKey('orders.Order', null=True, blank=True, on_delete=models.CASCADE, related_name='+')
    channel = models.CharField(max_length=8, choices=Channel.choices)
    text = models.TextField()
    delivery_status = models.CharField(max_length=16, default='PENDING')
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        db_table = 'notification'
        indexes = [models.Index(fields=['user', 'is_read'])]
        ordering = ['-created_at']
