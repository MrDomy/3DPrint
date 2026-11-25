from django.contrib import admin

from .models import Order, OrderEvent, OrderPostProcessing


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'client', 'status', 'priority', 'technology', 'material', 'quantity', 'created_at')
    list_filter = ('status', 'priority', 'technology')
    search_fields = ('number', 'client__email')


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ('order', 'type', 'from_status', 'to_status', 'actor', 'created_at')
    list_filter = ('type',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(OrderPostProcessing)
