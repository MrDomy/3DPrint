from django.contrib import admin

from orders import services as order_services

from .models import Quote, TariffVersion


@admin.register(TariffVersion)
class TariffAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_active', 'created_by', 'created_at')

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        before = None
        if change and obj.pk:
            prev = TariffVersion.objects.filter(pk=obj.pk).first()
            if prev:
                before = {'params': prev.params, 'is_active': prev.is_active}
        if not obj.created_by_id:
            obj.created_by = request.user
        if obj.is_active:
            TariffVersion.objects.exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)
        order_services.audit(
            request.user if request.user.is_authenticated else None,
            'TariffVersion',
            obj.pk,
            'UPDATE' if change else 'CREATE',
            before=before,
            after={'params': obj.params, 'is_active': obj.is_active},
        )


admin.site.register(Quote)

