"""Постановка задач в django-rq. При TASKS_SYNC=True выполняются сразу (тесты, отладка без Redis)."""
import importlib

from django.conf import settings


def _resolve(path):
    mod, _, name = path.rpartition('.')
    return getattr(importlib.import_module(mod), name)


def enqueue(func_path, *args):
    if settings.TASKS_SYNC:
        return _resolve(func_path)(*args)
    try:
        import django_rq
        return django_rq.get_queue('default').enqueue(func_path, *args)
    except Exception:  # Redis недоступен — не ломаем запрос, выполняем синхронно
        return _resolve(func_path)(*args)
