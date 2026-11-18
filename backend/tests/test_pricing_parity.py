"""Паритет формул со всеми 30 эталонными заказами Приложения В (±1 ₽, 0 дней при W=0): T-01..T-24, P-01..P-06."""
import pytest

from models_app import services as model_services
from orders import services as os_
from orders.models import Order
from pricing import services as pricing_services
from validation import services as val_services

from .helpers import make_order, run_to_result

OVERHANG = {'watertight': True, 'min_thickness_mm': 5.0, 'overhang_ratio': 0.2}

CASES = [
    ('T-01', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый',
                  bbox=(60, 40, 20), volume=18, qty=1), 300, 1),
    ('T-02', dict(tech='FDM', material='ABS', quality='Стандартное', color='белый',
                  bbox=(90, 60, 35), volume=55, qty=2, pp=['Шлифовка'], delivery='COURIER'), 1748, 4),
    ('T-03', dict(tech='FDM', material='Нейлон (PA12)', quality='Высокое', color='белый',
                  fmt='OBJ', bbox=(50, 50, 12), volume=14, qty=4), 726, 1),
    ('T-04', dict(tech='FDM', material='PLA', quality='Черновое', color='белый',
                  bbox=(110, 80, 70), volume=60, qty=1, analysis=OVERHANG), 320, 1),
    ('T-05', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый',
                  bbox=(120, 80, 15), volume=40, qty=3, pp=['Покраска'], delivery='COURIER'), 3392, 6),
    ('T-06', dict(tech='FDM', material='ABS', quality='Стандартное', color='белый',
                  bbox=(45, 30, 25), volume=9, qty=10), 517, 1),
    ('T-07', dict(tech='FDM', material='PLA', quality='Высокое', color='белый',
                  fmt='OBJ', bbox=(150, 70, 40), volume=85, qty=1,
                  pp=['Шлифовка', 'Покраска'], delivery='COURIER'), 2475, 4),
    ('T-08', dict(tech='FDM', material='PLA', quality='Черновое', color='белый',
                  bbox=(200, 200, 100), volume=210, qty=1, analysis=OVERHANG), 783, 1),
    ('T-09', dict(tech='FDM', material='ABS', quality='Стандартное', color='белый',
                  bbox=(35, 35, 110), volume=48, qty=2, pp=['Шлифовка']), 1341, 2),
    ('T-10', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый',
                  bbox=(80, 50, 6), volume=12, qty=6, delivery='COURIER'), 795, 3),
    ('T-11', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый',
                  fmt='3MF', bodies=3, bbox=(100, 100, 60), volume=70, qty=1, pp=['Сборка']), 1037, 2),
    ('T-12', dict(tech='FDM', material='ABS', quality='Стандартное', color='белый',
                  fmt='3MF', bbox=(180, 180, 200), volume=150, qty=1,
                  pp=['Шлифовка', 'Покраска'], delivery='COURIER', analysis=OVERHANG), 2403, 4),
    ('T-13', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый',
                  bbox=(400, 300, 60), volume=320, qty=1), 1463, 1),
    ('T-14', dict(tech='FDM', material='ABS', quality='Черновое', color='белый',
                  bbox=(450, 200, 150), volume=380, qty=1, pp=['Шлифовка'], analysis=OVERHANG), 1697, 2),
    ('T-15', dict(tech='SLA', material='Стандартная смола', quality='Высокое', color='серый',
                  bbox=(40, 30, 50), volume=12, qty=3, pp=['Покраска']), 3490, 4),
    ('T-16', dict(tech='SLA', material='Стандартная смола', quality='Высокое', color='серый',
                  bbox=(25, 25, 10), volume=2, qty=5, delivery='COURIER'), 879, 3),
    ('T-17', dict(tech='SLA', material='Стандартная смола', quality='Стандартное', color='серый',
                  fmt='OBJ', bbox=(60, 50, 30), volume=15, qty=2), 588, 1),
    ('T-18', dict(tech='SLA', material='Стандартная смола', quality='Стандартное', color='серый',
                  bbox=(120, 90, 40), volume=50, qty=1, pp=['Шлифовка'], delivery='COURIER'), 1564, 4),
    ('T-19', dict(tech='SLA', material='Высокопрочная смола', quality='Стандартное', color='серый',
                  bbox=(100, 60, 25), volume=30, qty=2), 1231, 1),
    ('T-20', dict(tech='SLA', material='Высокопрочная смола', quality='Высокое', color='серый',
                  bbox=(70, 40, 40), volume=25, qty=4, delivery='COURIER'), 3456, 3),
    ('T-21', dict(tech='DMLS', material='Нержавеющая сталь 316L', quality='Стандартное', color='металлик',
                  bbox=(40, 40, 30), volume=10, qty=2), 19320, 1),
    ('T-22', dict(tech='DMLS', material='Нержавеющая сталь 316L', quality='Стандартное', color='металлик',
                  bbox=(90, 50, 40), volume=20, qty=1, pp=['Шлифовка'], delivery='COURIER'), 20070, 4),
    ('T-23', dict(tech='DMLS', material='Нержавеющая сталь 316L', quality='Стандартное', color='металлик',
                  bbox=(60, 60, 60), volume=22, qty=1, analysis=OVERHANG), 22747, 1),
    ('T-24', dict(tech='DMLS', material='Нержавеющая сталь 316L', quality='Стандартное', color='металлик',
                  bbox=(150, 30, 30), volume=30, qty=2, pp=['Шлифовка']), 52760, 2),
    ('P-06', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый',
                  bbox=(120, 80, 150), volume=60, qty=1,
                  analysis={'watertight': False, 'repaired': True, 'min_thickness_mm': 0.3,
                            'overhang_ratio': 0.3}), 433, 1),
]


@pytest.mark.parametrize('name,kw,total,days', CASES, ids=[c[0] for c in CASES])
def test_reference_cases(users, name, kw, total, days):
    o = run_to_result(make_order(users['client'], **kw))
    assert o.status == 'CHECKED', name
    q = pricing_services.current_quote(o)
    assert abs(int(q.total) - total) <= 1
    assert q.estimated_days == days


def test_p06_warnings(users):
    kw = CASES[-1][1]
    o = run_to_result(make_order(users['client'], **kw))
    mv = model_services.current_version(o)
    codes = {i['code'] for i in val_services.latest_for(mv).issues}
    assert {'W-01', 'W-02', 'W-03'} <= codes
    assert val_services.latest_for(mv).verdict == 'WARNING'


def test_p03_too_big_goes_manual_review(users):
    o = run_to_result(make_order(users['client'], tech='FDM', material='PLA', quality='Черновое',
                                 color='белый', volume=100, bbox=(700, 700, 700)))
    assert o.status == 'MANUAL_REVIEW'
    codes = [i['code'] for i in val_services.latest_for(model_services.current_version(o)).issues]
    assert 'E-04' in codes


def test_p04_incompatible_goes_manual_review(users):
    o = run_to_result(make_order(users['client'], tech='SLA', material='Стандартная смола',
                                 quality='Стандартное', color='красный', volume=20))
    assert o.status == 'MANUAL_REVIEW'
    codes = [i['code'] for i in val_services.latest_for(model_services.current_version(o)).issues]
    assert 'E-05' in codes


def test_p05_retired_dmls_goes_manual_review_with_e06(users):
    from catalog.models import Printer
    Printer.objects.filter(name='DMLS-01').update(status='RETIRED')
    o = run_to_result(make_order(users['client'], tech='DMLS', material='Нержавеющая сталь 316L',
                                 quality='Стандартное', color='металлик', volume=10, bbox=(60, 40, 40)))
    assert o.status == 'MANUAL_REVIEW'
    codes = [i['code'] for i in val_services.latest_for(model_services.current_version(o)).issues]
    assert 'E-06' in codes
    assert 'E-04' not in codes


def test_p01_step_rejected():
    from config.exceptions import DomainError
    from validation import mesh
    with pytest.raises(DomainError) as e:
        mesh.check_upload('part.step', b'ISO-10303-21;')
    assert e.value.code == 'E-01'


def test_p02_truncated_stl_rejected():
    import struct
    from config.exceptions import DomainError
    from validation import mesh
    data = b'\0' * 80 + struct.pack('<I', 100) + b'\0' * 100
    with pytest.raises(DomainError) as e:
        mesh.check_upload('part.stl', data)
    assert e.value.code == 'E-02'


def test_size_limit_e01(settings):
    from config.exceptions import DomainError
    from validation import mesh
    settings.MAX_UPLOAD_BYTES = 10
    with pytest.raises(DomainError) as e:
        mesh.check_upload('a.stl', b'x' * 11)
    assert e.value.code == 'E-01'
