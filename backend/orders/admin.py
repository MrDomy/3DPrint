from django.contrib import admin

from .models import AuditLog, Order, OrderEvent


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'client', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('number', 'client__email')


admin.site.register(OrderEvent, ReadOnlyAdmin)
admin.site.register(AuditLog, ReadOnlyAdmin)
