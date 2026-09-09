import re

from django.db import migrations, models
from django.db.models import Q


def normalize_customer_identities(apps, schema_editor):
    Customer = apps.get_model('companies', 'Customer')
    normalized_rows = []
    identities = {'phone': {}, 'document': {}}
    for customer in Customer.objects.order_by('company_id', 'pk').iterator():
        phone = re.sub(r'\D', '', customer.phone or '')
        document = re.sub(r'\D', '', customer.document or '') or None
        normalized_rows.append((customer.pk, phone, document))
        for field, value in (('phone', phone), ('document', document)):
            if value:
                identities[field].setdefault((customer.company_id, value), []).append(customer.pk)

    collisions = []
    for field, values in identities.items():
        for (company_id, value), customer_ids in values.items():
            if len(customer_ids) > 1:
                collisions.append(
                    f'{field}={value} na empresa {company_id} (clientes {", ".join(map(str, customer_ids))})'
                )
    if collisions:
        raise RuntimeError(
            'Nao foi possivel normalizar clientes: identidades duplicadas apos a normalizacao. '
            f'Regularize manualmente antes de migrar: {"; ".join(collisions)}.'
        )

    for customer_id, phone, document in normalized_rows:
        Customer.objects.filter(pk=customer_id).update(phone=phone, document=document)


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
                condition=~Q(phone=''),
                fields=('company', 'phone'),
                name='companies_customer_company_phone_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.UniqueConstraint(
                condition=Q(document__isnull=False),
                fields=('company', 'document'),
                name='companies_customer_company_document_unique',
            ),
        ),
    ]
