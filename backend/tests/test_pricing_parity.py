"""Паритет формул с Приложением В (±1 ₽, 0 дней при W=0): T-01..T-21, P-03..P-06."""
import pytest

from orders import services as os_
from orders.models import Order
from pricing import services as pricing_services
from validation import services as val_services
from models_app import services as model_services

from .helpers import make_order, run_to_result

GENERIC = dict(bbox=(50, 50, 20))

CASES = [
    ('T-01', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый', volume=18), 300, 1),
    ('T-02', dict(tech='FDM', material='ABS', quality='Стандартное', color='белый', volume=55, qty=2,
                  pp=['Шлифовка'], delivery='COURIER'), 1748, 4),
    ('T-03', dict(tech='FDM', material='Нейлон (PA12)', quality='Высокое', color='белый', volume=14, qty=4),
     726, 1),
    ('T-04', dict(tech='FDM', material='PLA', quality='Черновое', color='белый', volume=60,
                  analysis={'watertight': True, 'min_thickness_mm': 5, 'overhang_ratio': 0.2}), 320, 1),
    ('T-11', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый', volume=70, fmt='3MF',
                  bodies=3, bbox=(100, 100, 60), pp=['Сборка']), 1037, 2),
    ('T-13', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый', volume=320,
                  bbox=(400, 300, 60)), 1463, 1),
    ('T-19', dict(tech='SLA', material='Высокопрочная смола', quality='Стандартное', color='серый', volume=30,
                  qty=2), 1231, 1),
    ('T-21', dict(tech='DMLS', material='Нержавеющая сталь 316L', quality='Стандартное', color='металлик',
                  volume=10, qty=2), 19320, 1),
    ('P-06', dict(tech='FDM', material='PLA', quality='Стандартное', color='белый', volume=60,
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
    o = run_to_result(make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное',
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


def test_p05_retired_dmls_goes_manual_review(users):
    from catalog.models import Printer
    Printer.objects.filter(name='DMLS-01').update(status='RETIRED')
    o = run_to_result(make_order(users['client'], tech='DMLS', material='Нержавеющая сталь 316L',
                                 quality='Стандартное', color='металлик', volume=10, bbox=(40, 40, 40)))
    assert o.status == 'MANUAL_REVIEW'
    codes = [i['code'] for i in val_services.latest_for(model_services.current_version(o)).issues]
    assert 'E-04' in codes or 'E-06' in codes


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


def test_orders_module_unused():
    assert os_ and Order
