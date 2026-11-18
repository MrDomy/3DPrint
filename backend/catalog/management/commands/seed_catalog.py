"""Загрузка справочников из спецификации (Приложение Б) и демо-пользователей. Идемпотентна."""
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import (Color, DeliveryMethod, Material, MaterialColor, MaterialTechnology, PickupPoint,
                            PostProcessing, Printer, PrinterMaterial, QualityProfile, Technology, Workshop)
from pricing.models import DEFAULT_TARIFF_PARAMS, TariffVersion

TECHS = [
    ('FDM', 'FDM (послойное наплавление)', '0.35', '0.15', '120', '150'),
    ('SLA', 'SLA (фотополимерная)', '0.60', '0.20', '200', '250'),
    ('DMLS', 'DMLS (печать металлом)', '1.00', '0.10', '2500', '3000'),
]
QUALITY = [
    ('FDM', 'Черновое', '0.300', '25', '0.90'), ('FDM', 'Стандартное', '0.200', '15', '1.00'),
    ('FDM', 'Высокое', '0.100', '7', '1.20'), ('SLA', 'Стандартное', '0.050', '20', '1.00'),
    ('SLA', 'Высокое', '0.025', '10', '1.25'), ('DMLS', 'Стандартное', '0.040', '5', '1.00'),
]
COLORS = {'белый': '#f5f5f5', 'чёрный': '#1a1a1a', 'серый': '#8a8a8a', 'красный': '#d32f2f',
          'синий': '#1976d2', 'прозрачный': '#d9eef7', 'металлик': '#b0b7c0'}
MATERIALS = [
    ('PLA', 'FDM', '1.24', '3.0', ['белый', 'чёрный', 'серый', 'красный', 'синий']),
    ('ABS', 'FDM', '1.04', '3.5', ['белый', 'чёрный', 'серый']),
    ('Нейлон (PA12)', 'FDM', '1.01', '6.0', ['белый', 'чёрный']),
    ('Стандартная смола', 'SLA', '1.10', '8.0', ['серый', 'прозрачный']),
    ('Высокопрочная смола', 'SLA', '1.15', '15.0', ['серый', 'чёрный']),
    ('Нержавеющая сталь 316L', 'DMLS', '7.90', '40.0', ['металлик']),
]
PRINTERS = [
    ('FDM-01', 'Основной цех', 'FDM', (220, 220, 250), 'NONE', ['PLA', 'ABS', 'Нейлон (PA12)']),
    ('FDM-02', 'Цех № 2', 'FDM', (220, 220, 250), 'NONE', ['PLA', 'ABS']),
    ('FDM-XL', 'Основной цех', 'FDM', (600, 600, 800), 'LARGE', ['PLA', 'ABS']),
    ('SLA-01', 'Цех № 2', 'SLA', (145, 145, 185), 'NONE', ['Стандартная смола']),
    ('SLA-HS', 'Основной цех', 'SLA', (200, 125, 210), 'HIGH_STRENGTH_RESIN',
     ['Высокопрочная смола', 'Стандартная смола']),
    ('DMLS-01', 'Основной цех', 'DMLS', (250, 250, 300), 'METAL', ['Нержавеющая сталь 316L']),
]
DEMO_USERS = [
    ('admin@3dprint.local', 'Admin123!', 'ADMIN', 'Администратор Демо', True),
    ('manager@3dprint.local', 'Manager123!', 'MANAGER', 'Менеджер Демо', False),
    ('client@3dprint.local', 'Client123!', 'CLIENT', 'Клиент Демо', False),
]


class Command(BaseCommand):
    help = 'Загружает справочники по умолчанию и демо-пользователей'

    @transaction.atomic
    def handle(self, *args, **opts):
        techs = {}
        for code, name, phi, sigma, r, s in TECHS:
            techs[code], _ = Technology.objects.update_or_create(
                code=code, defaults=dict(name=name, fill_factor=D(phi), support_factor=D(sigma),
                                         hourly_rate=D(r), setup_cost=D(s), is_active=True))
        for code, name, h, q, k in QUALITY:
            QualityProfile.objects.update_or_create(
                technology=techs[code], name=name,
                defaults=dict(layer_height_mm=D(h), flow_cm3_h=D(q), price_factor=D(k)))
        colors = {n: Color.objects.update_or_create(name=n, defaults={'hex': h})[0] for n, h in COLORS.items()}
        mats = {}
        for name, tech, rho, p, cols in MATERIALS:
            m, _ = Material.objects.update_or_create(name=name, defaults=dict(density=D(rho), price_per_gram=D(p),
                                                                              is_active=True))
            mats[name] = m
            MaterialTechnology.objects.get_or_create(material=m, technology=techs[tech])
            for c in cols:
                MaterialColor.objects.get_or_create(material=m, color=colors[c])
        for name, price, hours in (('Шлифовка', 400, 2), ('Покраска', 800, 6), ('Сборка', 600, 3)):
            PostProcessing.objects.update_or_create(name=name, defaults=dict(price=D(price), hours=D(hours),
                                                                              is_active=True))
        pickup, _ = DeliveryMethod.objects.update_or_create(
            type='PICKUP', defaults=dict(name='Самовывоз из пункта выдачи', price=0, days=0, is_active=True))
        DeliveryMethod.objects.update_or_create(
            type='COURIER', defaults=dict(name='Курьерская доставка', price=350, days=2, is_active=True))
        for n, a in (('Пункт выдачи «Центральный»', 'ул. Примерная, 1'),
                     ('Пункт выдачи «Северный»', 'пр. Образцовый, 10')):
            PickupPoint.objects.update_or_create(delivery_method=pickup, name=n, defaults=dict(address=a,
                                                                                                is_active=True))
        main, _ = Workshop.objects.update_or_create(name='Основной цех', defaults=dict(
            address='ул. Примерная, 1', is_main=True))
        w2, _ = Workshop.objects.update_or_create(name='Цех № 2', defaults=dict(address='ул. Примерная, 15',
                                                                                is_main=False))
        ws = {'Основной цех': main, 'Цех № 2': w2}
        for name, wname, tech, dims, spec, pm in PRINTERS:
            p, _ = Printer.objects.update_or_create(name=name, defaults=dict(
                workshop=ws[wname], technology=techs[tech], max_x=dims[0], max_y=dims[1], max_z=dims[2],
                specialization=spec))
            for mn in pm:
                PrinterMaterial.objects.get_or_create(printer=p, material=mats[mn])
        if not TariffVersion.objects.filter(is_active=True).exists():
            TariffVersion.objects.create(params=DEFAULT_TARIFF_PARAMS, is_active=True)
        User = get_user_model()
        for email, pw, role, name, senior in DEMO_USERS:
            u, created = User.objects.get_or_create(email=email, defaults=dict(
                role=role, full_name=name, is_staff=role == 'ADMIN', is_superuser=role == 'ADMIN',
                is_senior=senior))
            if created:
                u.set_password(pw)
                u.save()
        self.stdout.write(self.style.SUCCESS('Справочники и демо-пользователи загружены.'))
