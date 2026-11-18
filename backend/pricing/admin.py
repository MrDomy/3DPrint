from django.contrib import admin

from .models import Quote, TariffVersion


@admin.register(TariffVersion)
class TariffAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_active', 'created_by', 'created_at')

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        if obj.is_active:
            TariffVersion.objects.exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)


admin.site.register(Quote)
