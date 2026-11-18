from .models import Message


def post(order, author, text, model_version=None):
    return Message.objects.create(order=order, author=author, text=text, model_version=model_version)


def list_for(order, since=None):
    qs = Message.objects.filter(order=order).select_related('author', 'model_version')
    if since:
        qs = qs.filter(created_at__gt=since)
    return qs
