from django.conf import settings
from django.db import models

from config.base import BaseModel

DEFAULT_TARIFF_PARAMS = {
    'min_order_cost': 300, 'printer_hours_per_day': 20, 'post_hours_per_day': 8,
    'horizon_days': 7, 'k_change': 2, 'k_spec': 24,
    'thin_wall_mm': {'FDM': 0.8, 'SLA': 0.4, 'DMLS': 0.6},
    'overhang_angle_deg': 45,
}


class TariffVersion(BaseModel):
    params = models.JSONField(default=dict)
    is_active = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+')

    class Meta:
        db_table = 'tariff_version'
        constraints = [models.UniqueConstraint(fields=['is_active'], condition=models.Q(is_active=True),
                                               name='uniq_active_tariff')]


class Quote(BaseModel):
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='quotes')
    tariff_version = models.ForeignKey(TariffVersion, on_delete=models.PROTECT, related_name='+')
    cost_material = models.DecimalField(max_digits=12, decimal_places=2)
    cost_machine = models.DecimalField(max_digits=12, decimal_places=2)
    cost_post = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_delivery = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=0)
    print_hours = models.DecimalField(max_digits=10, decimal_places=2)
    mass_g = models.DecimalField(max_digits=12, decimal_places=2)
    estimated_days = models.PositiveIntegerField()
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = 'quote'
        constraints = [models.CheckConstraint(condition=models.Q(total__gte=0), name='quote_total_gte_0')]
        indexes = [models.Index(fields=['order', 'is_current'])]
