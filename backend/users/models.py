import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError('Email обязателен')
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role='ADMIN', is_senior=True)
        return self._create(email, password, **extra)


class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = 'CLIENT', 'Клиент'
        MANAGER = 'MANAGER', 'Менеджер'
        ADMIN = 'ADMIN', 'Администратор'

    class ClientType(models.TextChoices):
        INDIVIDUAL = 'INDIVIDUAL', 'Физическое лицо'
        COMPANY = 'COMPANY', 'Юридическое лицо'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CLIENT)
    phone = models.CharField(max_length=32, blank=True, default='')
    company_name = models.CharField(max_length=255, blank=True, default='')
    full_name = models.CharField(max_length=255, blank=True, default='')
    client_type = models.CharField(max_length=16, choices=ClientType.choices, default=ClientType.INDIVIDUAL)
    consent_at = models.DateTimeField(null=True, blank=True)
    is_senior = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        db_table = 'app_user'

    def __str__(self):
        return self.email

    @property
    def is_manager_or_admin(self):
        return self.role in (self.Role.MANAGER, self.Role.ADMIN)
