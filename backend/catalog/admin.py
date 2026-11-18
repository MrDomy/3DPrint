from django.contrib import admin

from . import models as m


class MatTechInline(admin.TabularInline):
    model = m.MaterialTechnology
    extra = 0


class MatColorInline(admin.TabularInline):
    model = m.MaterialColor
    extra = 0


class PrinterMatInline(admin.TabularInline):
    model = m.PrinterMaterial
    extra = 0


@admin.register(m.Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'density', 'price_per_gram', 'is_active')
    inlines = [MatTechInline, MatColorInline]


@admin.register(m.Printer)
class PrinterAdmin(admin.ModelAdmin):
    list_display = ('name', 'workshop', 'technology', 'specialization', 'status')
    list_filter = ('technology', 'status', 'workshop')
    inlines = [PrinterMatInline]


class NoDeleteAdmin(admin.ModelAdmin):
    """Справочники, использованные в заказах, нельзя удалять — только is_active=False."""

    def has_delete_permission(self, request, obj=None):
        return False


for model in (m.Technology, m.QualityProfile, m.PostProcessing, m.DeliveryMethod, m.PickupPoint, m.Color):
    admin.site.register(model, NoDeleteAdmin)
admin.site.register(m.Workshop)
