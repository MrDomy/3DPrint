import hashlib
import secrets

from django.db import models

from config.base import BaseModel


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiClient(BaseModel):
    name = models.CharField(max_length=128)
    api_key_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'api_client'

    @classmethod
    def issue(cls, name, scopes):
        raw = secrets.token_urlsafe(32)
        obj = cls.objects.create(name=name, api_key_hash=hash_key(raw), scopes=list(scopes))
        return obj, raw

    def __str__(self):
        return self.name
