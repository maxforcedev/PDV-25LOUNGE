from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.companies.models import Company
from apps.saas.models import PlanVersion, Subscription
from apps.saas.services import map_existing_company


class Command(BaseCommand):
    help = 'Lista Companies sem assinatura ou realiza mapeamento comercial explicitamente informado.'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int)
        parser.add_argument('--plan-version-id', type=int)
        parser.add_argument('--billing-mode', choices=Subscription.BillingMode.values)

    def handle(self, *args, **options):
        values = (
            options.get('company_id'),
            options.get('plan_version_id'),
            options.get('billing_mode'),
        )
        if not any(values):
            for company in Company.objects.exclude(subscriptions__is_current=True).order_by('pk'):
                self.stdout.write(f'{company.pk}\t{company.trade_name}')
            return
        if not all(values):
            raise CommandError(
                'Informe --company-id, --plan-version-id e --billing-mode; nenhum valor e inferido.'
            )
        try:
            company = Company.objects.get(pk=options['company_id'])
            plan_version = PlanVersion.objects.get(pk=options['plan_version_id'])
            _, created = map_existing_company(
                company=company,
                plan_version=plan_version,
                billing_mode=options['billing_mode'],
            )
        except (Company.DoesNotExist, PlanVersion.DoesNotExist) as error:
            raise CommandError('Company ou PlanVersion nao encontrada.') from error
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        self.stdout.write(
            self.style.SUCCESS('Assinatura criada.' if created else 'Mapeamento ja existente.')
        )
