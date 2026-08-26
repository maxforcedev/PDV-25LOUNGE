from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.saas.models import Subscription
from apps.saas.services import process_subscription_lifecycle


class Command(BaseCommand):
    help = 'Processa o lifecycle deterministico das assinaturas correntes; adequado para cron.'

    def handle(self, *args, **options):
        processed_at = timezone.now()
        changed = 0
        total = 0
        for subscription in Subscription.objects.filter(is_current=True).order_by('pk').iterator():
            _, was_changed = process_subscription_lifecycle(subscription, at=processed_at)
            total += 1
            changed += int(was_changed)
        self.stdout.write(f'Assinaturas processadas: {total}; alteradas: {changed}.')
