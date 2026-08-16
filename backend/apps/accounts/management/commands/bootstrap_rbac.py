from django.core.management.base import BaseCommand

from apps.companies.models import Company
from apps.companies.services import ensure_default_access_profiles, ensure_permission_catalog


class Command(BaseCommand):
    help = 'Create or update functional permissions and default access profiles.'

    def handle(self, *args, **options):
        ensure_permission_catalog()
        for company in Company.objects.all():
            ensure_default_access_profiles(company)
        self.stdout.write(
            self.style.SUCCESS('Functional permissions and access profiles are ready.')
        )
