from django.contrib import admin

from .models import Quote


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'total', 'adjustment', 'estimated_days', 'is_current', 'created_at')
    list_filter = ('is_current',)
