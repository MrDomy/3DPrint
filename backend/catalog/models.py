from django.core.exceptions import ValidationError
from django.db import models

from config.base import BaseModel


class Workshop(BaseModel):
    name = models.CharField('Название', max_length=128)
    address = models.CharField('Адрес', max_length=255, blank=True)
    is_main = models.BooleanField('Основной цех', default=False)

    class Meta:
        db_table = 'workshop'
        constraints = [models.UniqueConstraint(fields=['is_main'], condition=models.Q(is_main=True),
                                               name='uniq_main_workshop')]

    def __str__(self):
        return self.name


class Technology(BaseModel):
    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=128)
    fill_factor = models.DecimalField('φ', max_digits=6, decimal_places=3)
    support_factor = models.DecimalField('σ', max_digits=6, decimal_places=3)
    hourly_rate = models.DecimalField('R, ₽/ч', max_digits=10, decimal_places=2)
    setup_cost = models.DecimalField('S, ₽', max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'technology'

    def __str__(self):
        return self.code


class QualityProfile(BaseModel):
    technology = models.ForeignKey(Technology, on_delete=models.PROTECT, related_name='quality_profiles')
    name = models.CharField(max_length=64)
    layer_height_mm = models.DecimalField(max_digits=6, decimal_places=3)
    flow_cm3_h = models.DecimalField('Q, см³/ч', max_digits=8, decimal_places=2)
    price_factor = models.DecimalField('k', max_digits=5, decimal_places=2)

    class Meta:
        db_table = 'quality_profile'
        constraints = [models.UniqueConstraint(fields=['technology', 'name'], name='uniq_quality_tech_name')]

    def __str__(self):
        return f'{self.technology.code}/{self.name}'


class Color(BaseModel):
    name = models.CharField(max_length=64, unique=True)
    hex = models.CharField(max_length=7, default='#cccccc')

    class Meta:
        db_table = 'color'

    def __str__(self):
        return self.name


class Material(BaseModel):
    name = models.CharField(max_length=128, unique=True)
    density = models.DecimalField('ρ, г/см³', max_digits=6, decimal_places=3)
    price_per_gram = models.DecimalField('p, ₽/г', max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    technologies = models.ManyToManyField(Technology, through='MaterialTechnology', related_name='materials')
    colors = models.ManyToManyField(Color, through='MaterialColor', related_name='materials')

    class Meta:
        db_table = 'material'

    def __str__(self):
        return self.name


class MaterialTechnology(BaseModel):
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    technology = models.ForeignKey(Technology, on_delete=models.CASCADE)

    class Meta:
        db_table = 'material_technology'
        constraints = [models.UniqueConstraint(fields=['material', 'technology'], name='uniq_mat_tech')]


class MaterialColor(BaseModel):
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    color = models.ForeignKey(Color, on_delete=models.CASCADE)

    class Meta:
        db_table = 'material_color'
        constraints = [models.UniqueConstraint(fields=['material', 'color'], name='uniq_mat_color')]


class Printer(BaseModel):
    class Specialization(models.TextChoices):
        NONE = 'NONE', 'Нет'
        METAL = 'METAL', 'Металл'
        HIGH_STRENGTH_RESIN = 'HIGH_STRENGTH_RESIN', 'Высокопрочная смола'
        LARGE = 'LARGE', 'Крупноформатный'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Активен'
        MAINTENANCE = 'MAINTENANCE', 'На обслуживании'
        RETIRED = 'RETIRED', 'Списан'

    workshop = models.ForeignKey(Workshop, on_delete=models.PROTECT, related_name='printers')
    technology = models.ForeignKey(Technology, on_delete=models.PROTECT, related_name='printers')
    name = models.CharField(max_length=64, unique=True)
    max_x = models.DecimalField(max_digits=8, decimal_places=2)
    max_y = models.DecimalField(max_digits=8, decimal_places=2)
    max_z = models.DecimalField(max_digits=8, decimal_places=2)
    specialization = models.CharField(max_length=24, choices=Specialization.choices, default=Specialization.NONE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    materials = models.ManyToManyField(Material, through='PrinterMaterial', related_name='printers')

    class Meta:
        db_table = 'printer'
        constraints = [models.CheckConstraint(
            condition=models.Q(max_x__gt=0, max_y__gt=0, max_z__gt=0), name='printer_dims_positive')]

    def clean(self):
        if min(self.max_x or 0, self.max_y or 0, self.max_z or 0) <= 0:
            raise ValidationError('Габариты принтера должны быть больше нуля.')
        if self.specialization != self.Specialization.NONE and self.workshop_id and not self.workshop.is_main:
            raise ValidationError('Специализированные принтеры допускаются только в основном цехе.')

    @property
    def dims_sorted(self):
        return sorted([float(self.max_x), float(self.max_y), float(self.max_z)])

    def __str__(self):
        return self.name


class PrinterMaterial(BaseModel):
    printer = models.ForeignKey(Printer, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)

    class Meta:
        db_table = 'printer_material'
        constraints = [models.UniqueConstraint(fields=['printer', 'material'], name='uniq_printer_mat')]


class PostProcessing(BaseModel):
    name = models.CharField(max_length=64, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'post_processing'

    def __str__(self):
        return self.name


class DeliveryMethod(BaseModel):
    class Type(models.TextChoices):
        PICKUP = 'PICKUP', 'Самовывоз'
        COURIER = 'COURIER', 'Курьер'

    type = models.CharField(max_length=16, choices=Type.choices)
    name = models.CharField(max_length=128)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    days = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'delivery_method'

    def __str__(self):
        return self.name


class PickupPoint(BaseModel):
    delivery_method = models.ForeignKey(DeliveryMethod, on_delete=models.PROTECT, related_name='pickup_points')
    name = models.CharField(max_length=128)
    address = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'pickup_point'

    def __str__(self):
        return self.name
