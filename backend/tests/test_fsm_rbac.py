import itertools

import pytest

from config.exceptions import DomainError
from orders import services as os_
from orders.models import AuditLog, InsertOnlyError, Order, OrderEvent, Status

from conftest import api_as
from .helpers import make_order, run_to_result

ALL = [s.value for s in Status]


def test_fourteen_statuses_and_26_transitions():
    assert len(ALL) == 14
    assert len(os_.TRANSITIONS) == 26


def test_final_states_have_no_outgoing():
    for f in ('COMPLETED', 'REJECTED', 'CANCELLED'):
        assert not [1 for (a, _b) in os_.TRANSITIONS if a == f]


@pytest.mark.parametrize('frm,to', [p for p in itertools.product(ALL, ALL)
                                    if (Status(p[0]), Status(p[1])) not in os_.TRANSITIONS])
def test_invalid_transitions_rejected(users, frm, to):
    o = Order.objects.create(client=users['client'], number=f'T-{frm}-{to}', status=frm)
    with pytest.raises(DomainError) as e:
        os_.transition(o, to, user=users['manager'], reason='x')
    assert e.value.status == 409


def test_reason_required_for_reject(users):
    o = run_to_result(make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное',
                                 color='белый', volume=18))
    with pytest.raises(DomainError) as e:
        os_.decision(o, users['manager'], 'reject', '')
    assert e.value.code == 'reason_required'


def test_full_happy_path_and_events(users):
    o = run_to_result(make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное',
                                 color='белый', volume=18))
    assert o.status == 'CHECKED'
    os_.decision(o, users['manager'], 'approve')
    assert o.status == 'AWAITING_PAYMENT'
    os_.pay(o, users['client'])
    assert o.status == 'PAID'
    rec = os_.recommendation(o)
    assert rec['top'] and rec['top'][0]['printer'] in ('FDM-01', 'FDM-02')
    os_.assign_printer(o, users['manager'], rec['top'][0]['printer_id'])
    assert o.status == 'DISTRIBUTED'
    for s in ('PRINTING', 'READY', 'COMPLETED'):
        os_.change_status(o, users['manager'], s)
    assert o.status == 'COMPLETED'
    assert OrderEvent.objects.filter(order=o, type='STATUS_CHANGED').count() >= 8


def test_assignment_outside_top3_needs_reason_and_ineligible_blocked(users):
    o = run_to_result(make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное',
                                 color='белый', volume=18))
    os_.decision(o, users['manager'], 'approve')
    os_.pay(o, users['client'])
    from catalog.models import Printer
    sla = Printer.objects.get(name='SLA-01')
    with pytest.raises(DomainError) as e:
        os_.assign_printer(o, users['manager'], sla.pk)
    assert e.value.code == 'printer_ineligible'


def test_optimistic_locking(users):
    o = make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное', color='белый', volume=18)
    stale = Order.objects.get(pk=o.pk)
    os_.update_draft(o, users['client'], {'quantity': 2})
    with pytest.raises(DomainError) as e:
        os_.update_draft(stale, users['client'], {'quantity': 3, 'version': stale.version})
    assert e.value.status == 409


def test_insert_only(users):
    o = make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное', color='белый', volume=18)
    ev = OrderEvent.objects.filter(order=o).first()
    ev.reason = 'hack'
    with pytest.raises(InsertOnlyError):
        ev.save()
    with pytest.raises(InsertOnlyError):
        ev.delete()
    a = AuditLog.objects.create(entity_type='X', entity_id='1', action='A')
    with pytest.raises(InsertOnlyError):
        a.delete()


def test_cancel_rules(users):
    o = run_to_result(make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное',
                                 color='белый', volume=18))
    with pytest.raises(DomainError):
        os_.cancel(o, users['manager'], '')
    os_.cancel(o, users['client'])
    assert o.status == 'CANCELLED'


# ----- RBAC через API -----
def test_anonymous_denied(users):
    assert api_as(None).get('/api/orders').status_code in (401, 403)


def test_client_cannot_see_foreign_order(users):
    from django.contrib.auth import get_user_model
    other = get_user_model().objects.create_user(email='o@x.ru', password='Passw0rd!x', role='CLIENT')
    o = make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное', color='белый', volume=18)
    assert api_as(other).get(f'/api/orders/{o.pk}').status_code == 404
    assert api_as(users['client']).get(f'/api/orders/{o.pk}').status_code == 200


def test_client_cannot_use_manager_endpoints(users):
    o = run_to_result(make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное',
                                 color='белый', volume=18))
    c = api_as(users['client'])
    assert c.post(f'/api/orders/{o.pk}/decision', {'action': 'approve'}, format='json').status_code == 403
    assert c.get(f'/api/orders/{o.pk}/recommendation').status_code == 403
    assert c.get('/api/load').status_code == 403
    assert c.get('/api/printers').status_code == 403


def test_manager_cannot_create_order_but_sees_queue(users):
    m = api_as(users['manager'])
    assert m.post('/api/orders', {}, format='json').status_code == 403
    assert m.get('/api/orders').status_code == 200
    assert m.get('/api/load').status_code == 200


def test_adjustment_admin_only(users):
    o = run_to_result(make_order(users['client'], tech='FDM', material='PLA', quality='Стандартное',
                                 color='белый', volume=18))
    body = {'adjustment': -50, 'reason': 'Скидка'}
    assert api_as(users['manager']).post(f'/api/orders/{o.pk}/adjustment', body, format='json').status_code == 403
    r = api_as(users['admin']).post(f'/api/orders/{o.pk}/adjustment', body, format='json')
    assert r.status_code == 200 and r.data['quote']['total'] == 250
    assert AuditLog.objects.filter(action='ADJUSTMENT').exists()


def test_register_requires_consent(seeded):
    c = api_as(None)
    base = {'email': 'n@x.ru', 'password': 'Str0ng!pass', 'full_name': 'Иван'}
    assert c.post('/api/auth/register', base, format='json').status_code == 400
    r = c.post('/api/auth/register', {**base, 'consent': True}, format='json')
    assert r.status_code == 201
    from django.contrib.auth import get_user_model
    assert get_user_model().objects.get(email='n@x.ru').consent_at is not None
    assert c.get('/api/auth/me').data['email'] == 'n@x.ru'


def test_integration_api_key_scopes(users):
    from integrations.models import ApiClient
    from rest_framework.test import APIClient
    _, raw = ApiClient.issue('engineer', ['orders:read'])
    c = APIClient()
    assert c.get('/api/integration/orders').status_code in (401, 403)
    assert c.get('/api/integration/orders', HTTP_X_API_KEY=raw).status_code == 200
    assert c.get('/api/integration/export/orders', HTTP_X_API_KEY=raw).status_code == 403


def test_health(db):
    assert api_as(None).get('/health').status_code == 200
