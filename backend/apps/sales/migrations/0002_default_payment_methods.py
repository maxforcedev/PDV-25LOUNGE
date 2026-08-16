from django.db import migrations


DEFAULTS = (
    ('cash', 'Dinheiro'),
    ('pix', 'PIX'),
    ('credit_card', 'Cartao de credito'),
    ('debit_card', 'Cartao de debito'),
)


def ensure_defaults(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    PaymentMethod = apps.get_model('sales', 'PaymentMethod')
    for company in Company.objects.iterator():
        for code, name in DEFAULTS:
            method, _ = PaymentMethod.objects.get_or_create(
                company=company,
                code=code,
                defaults={
                    'name': name,
                    'status': 'active',
                    'is_system': True,
                },
            )
            PaymentMethod.objects.filter(pk=method.pk).update(
                name=name,
                is_system=True,
            )


class Migration(migrations.Migration):
    dependencies = [('sales', '0001_initial')]

    operations = [
        migrations.RunPython(ensure_defaults, migrations.RunPython.noop),
    ]
