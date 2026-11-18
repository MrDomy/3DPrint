import io
import zipfile

import pytest

from config.exceptions import DomainError
from notifications import services as ns
from notifications.models import Notification
from validation import mesh


def _zip(entries, compression=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression) as z:
        for name, data in entries:
            z.writestr(name, data)
    return buf.getvalue()


def test_3mf_compression_bomb_rejected():
    data = _zip([('3D/3dmodel.model', b'0' * (20 * 1024 * 1024))])
    with pytest.raises(DomainError) as e:
        mesh.check_upload('bomb.3mf', data)
    assert e.value.code == 'E-02'


def test_3mf_too_many_entries_rejected():
    data = _zip([(f'f{i}.txt', b'x') for i in range(mesh.MAX_3MF_ENTRIES + 1)])
    with pytest.raises(DomainError) as e:
        mesh.check_upload('many.3mf', data)
    assert e.value.code == 'E-02'


def test_3mf_not_a_zip_rejected():
    with pytest.raises(DomainError) as e:
        mesh.check_upload('x.3mf', b'PK\x03\x04garbage')
    assert e.value.code == 'E-02'


@pytest.mark.django_db
def test_email_retry_schedule_5_15_60(users, settings):
    settings.EMAIL_BACKEND = 'tests.test_hardening.FailingBackend'
    n = Notification.objects.create(user=users['client'], channel='EMAIL', text='x', delivery_status='PENDING')
    expected = [(5, 'RETRY'), (15, 'RETRY'), (60, 'RETRY'), (None, 'FAILED')]
    from django.utils import timezone
    for minutes, status in expected:
        before = timezone.now()
        ns.send_email_notification(n.pk)
        n.refresh_from_db()
        assert n.delivery_status == status
        if minutes:
            delta = (n.next_attempt_at - before).total_seconds() / 60
            assert minutes - 0.5 < delta < minutes + 0.5
        else:
            assert n.next_attempt_at is None


from django.core.mail.backends.base import BaseEmailBackend  # noqa: E402


class FailingBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise ConnectionError('smtp down')


@pytest.mark.django_db
def test_recommendation_tie_break_is_deterministic(users):
    from catalog.models import Material, Technology
    from scheduling import services as sched
    t = Technology.objects.get(code='FDM')
    m = Material.objects.get(name='PLA')
    runs = [[r['printer'] for r in sched.recommend(technology=t, material=m, color=None, bbox=[10, 10, 10],
                                                     print_hours=1)['top']] for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
