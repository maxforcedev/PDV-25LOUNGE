from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.companies.models import Company
from apps.companies.services import assign_company_owner


class Command(BaseCommand):
    help = 'Lista empresas sem proprietário ou atribui um proprietário pendente.'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int)
        parser.add_argument('--user-id', type=int)

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        user_id = options.get('user_id')
        if company_id is None and user_id is None:
            pending = Company.objects.exclude(user_accesses__is_owner=True).order_by('pk')
            if not pending.exists():
                self.stdout.write('Nenhuma empresa pendente.')
                return
            for company in pending:
                self.stdout.write(f'{company.pk}\t{company.trade_name}')
            return
        if company_id is None or user_id is None:
            raise CommandError('Informe --company-id e --user-id juntos.')
        if not Company.objects.filter(pk=company_id).exists():
            raise CommandError('Empresa não encontrada.')
        if not User.objects.filter(pk=user_id).exists():
            raise CommandError('Usuário não encontrado.')

        try:
            access, created = assign_company_owner(
                company_id=company_id,
                user_id=user_id,
            )
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Proprietário atribuído: empresa={company_id} usuário={user_id}.'
                )
            )
        else:
            self.stdout.write(
                f'Proprietário já atribuído: empresa={company_id} usuário={access.user_id}.'
            )
