from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.saas.services import enable_saas_enforcement


class Command(BaseCommand):
    help = 'Habilita o cutover SaaS atomico somente quando todos os tenants operacionais estiverem prontos.'

    def add_arguments(self, parser):
        parser.add_argument('--reason', required=True)

    def handle(self, *args, **options):
        try:
            _, changed = enable_saas_enforcement(reason=options['reason'])
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        self.stdout.write(
            self.style.SUCCESS('Cutover SaaS habilitado.' if changed else 'Cutover SaaS ja estava habilitado.')
        )
