import re

from django.db import migrations, models
from django.db.models import Q


def normalize_customer_identities(apps, schema_editor):
    Customer = apps.get_model('companies', 'Customer')
    for customer in Customer.objects.exclude(phone='').iterator():
        normalized_phone = re.sub(r'\D', '', customer.phone)
        if normalized_phone != customer.phone:
            Customer.objects.filter(pk=customer.pk).update(phone=normalized_phone)
    for customer in Customer.objects.exclude(document__isnull=True).iterator():
        normalized_document = re.sub(r'\D', '', customer.document or '') or None
        if normalized_document != customer.document:
            Customer.objects.filter(pk=customer.pk).update(document=normalized_document)


class Migration(migrations.Migration):
    dependencies = [('companies', '0048_ticket_validate_permission')]

    operations = [
        migrations.RunPython(normalize_customer_identities, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='customer',
            name='companies_customer_company_document_unique',
        ),
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.UniqueConstraint(
                condition=Q(status='active') & ~Q(phone=''),
                fields=('company', 'phone'),
                name='companies_customer_company_phone_active_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.UniqueConstraint(
                condition=Q(status='active') & Q(document__isnull=False),
                fields=('company', 'document'),
                name='companies_customer_company_document_unique',
            ),
        ),
    ]
