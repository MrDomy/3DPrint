import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / '.env')
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ('1', 'true', 'yes', 'on')


SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
DEBUG = env_bool('DEBUG', True)
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
if not DEBUG:
    from django.core.exceptions import ImproperlyConfigured
    if SECRET_KEY == 'change-me-in-production':
        raise ImproperlyConfigured('В production необходимо задать SECRET_KEY.')
    if not os.getenv('ALLOWED_HOSTS'):
        raise ImproperlyConfigured('В production необходимо задать ALLOWED_HOSTS.')

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'rest_framework', 'drf_spectacular', 'corsheaders', 'django_rq', 'axes',
    'users', 'catalog', 'orders', 'models_app', 'validation', 'pricing', 'scheduling',
    'messaging', 'notifications', 'payment', 'integrations',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages']},
}]
WSGI_APPLICATION = 'config.wsgi.application'

if env_bool('USE_SQLITE', False):
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
else:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', '3dprint'),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.getenv('POSTGRES_HOST', 'db'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }}

AUTH_USER_MODEL = 'users.User'
AUTHENTICATION_BACKENDS = ['axes.backends.AxesStandaloneBackend', 'django.contrib.auth.backends.ModelBackend']
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # часы -> 15 минут
AXES_LOCKOUT_PARAMETERS = ['username']
AXES_ENABLED = env_bool('AXES_ENABLED', True)

LANGUAGE_CODE = 'ru-RU'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Сессии и CSRF
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 7 * 24 * 3600
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = ['http://localhost:5173']
CORS_ALLOWED_ORIGINS = [o for o in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173').split(',') if o]
CSRF_TRUSTED_ORIGINS = sorted(set(CSRF_TRUSTED_ORIGINS + CORS_ALLOWED_ORIGINS))
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'EXCEPTION_HANDLER': 'config.exceptions.api_exception_handler',
}
SPECTACULAR_SETTINGS = {'TITLE': '3DPrint API', 'VERSION': '1.0.0', 'SERVE_INCLUDE_SCHEMA': False}

# Redis / RQ
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
RQ_QUEUES = {'default': {'HOST': REDIS_HOST, 'PORT': REDIS_PORT, 'DB': 0, 'DEFAULT_TIMEOUT': 360}}
# Синхронное выполнение задач (тесты / локальная отладка без Redis)
TASKS_SYNC = env_bool('TASKS_SYNC', False)

# Почта (Mailpit)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'mailpit')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 1025))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', '3DPrint <no-reply@3dprint.local>')

# Хранилище моделей (MinIO / S3 или локальная папка)
USE_LOCAL_STORAGE = env_bool('USE_LOCAL_STORAGE', False)
LOCAL_STORAGE_ROOT = Path(os.getenv('LOCAL_STORAGE_ROOT', str(BASE_DIR / 'media_private')))
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
MINIO_PUBLIC_ENDPOINT = os.getenv('MINIO_PUBLIC_ENDPOINT', 'http://localhost:9000')
MINIO_ROOT_USER = os.getenv('MINIO_ROOT_USER', 'minioadmin')
MINIO_ROOT_PASSWORD = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
MINIO_BUCKET_NAME = os.getenv('MINIO_BUCKET_NAME', '3dprint-models')
PRESIGNED_URL_TTL = 300

# Бизнес-настройки
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_3MF_UNPACKED_BYTES = 500 * 1024 * 1024
PAY_STUB_ENABLED = env_bool('PAY_STUB_ENABLED', True)

LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
try:
    import structlog
    structlog.configure(processors=[
        structlog.processors.add_log_level, structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.JSONRenderer()])
except ImportError:  # pragma: no cover
    pass

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
