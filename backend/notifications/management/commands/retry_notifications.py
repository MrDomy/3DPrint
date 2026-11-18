from django.core.management.base import BaseCommand

from notifications.services import retry_due_emails


class Command(BaseCommand):
    help = 'Повторная отправка email-уведомлений (5, 15, 60 минут)'

    def handle(self, *args, **opts):
        self.stdout.write(f'Обработано: {retry_due_emails()}')
