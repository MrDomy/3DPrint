"""Постановка задач в django-rq после коммита транзакции. При TASKS_SYNC=True выполняются сразу."""
import importlib

from django.conf import settings
from django.db import transaction


def _resolve(path):
    mod, _, name = path.rpartition('.')
    return getattr(importlib.import_module(mod), name)


def _dispatch(func_path, *args):
    try:
        import django_rq
        return django_rq.get_queue('default').enqueue(func_path, *args)
    except Exception:
        return _resolve(func_path)(*args)


def enqueue(func_path, *args):
    if settings.TASKS_SYNC:
        return _resolve(func_path)(*args)
    transaction.on_commit(lambda: _dispatch(func_path, *args))
