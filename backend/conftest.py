import pytest
from django.core.management import call_command


@pytest.fixture(autouse=True)
def _settings(settings, tmp_path):
    settings.TASKS_SYNC = True
    settings.USE_LOCAL_STORAGE = True
    settings.LOCAL_STORAGE_ROOT = tmp_path / 'media'
    settings.AXES_ENABLED = False
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    settings.PAY_STUB_ENABLED = True


@pytest.fixture
def seeded(db):
    call_command('seed_catalog')


@pytest.fixture
def users(seeded):
    from django.contrib.auth import get_user_model
    U = get_user_model()
    return {'admin': U.objects.get(email='admin@3dprint.local'),
            'manager': U.objects.get(email='manager@3dprint.local'),
            'client': U.objects.get(email='client@3dprint.local')}


def api_as(user):
    from rest_framework.test import APIClient
    c = APIClient()
    if user:
        c.force_authenticate(user)
    return c
