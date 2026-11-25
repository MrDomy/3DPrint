from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'channel', 'delivery_status', 'attempts', 'is_read', 'created_at')
    list_filter = ('channel', 'delivery_status', 'is_read')
