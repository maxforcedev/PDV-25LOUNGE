from django.db import migrations


def ensure_cielo_smart_provider(apps, schema_editor):
    PaymentProvider = apps.get_model('payment_integrations', 'PaymentProvider')
    PaymentProvider.objects.get_or_create(
        code='cielo',
        defaults={
            'name': 'Cielo Smart',
            'status': 'active',
            'integration_type': 'local_deep_link',
            'capabilities': {
                'payment': True,
                'reversal': True,
                'recovery': True,
                'enabled_products': True,
                'terminal_info': True,
                'payment_methods': [
                    'credit_card', 'debit_card', 'pix', 'food_voucher', 'meal_voucher',
                ],
            },
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('payment_integrations', '0003_paymentattempt_provider_transaction_unique'),
    ]

    operations = [
        migrations.RunPython(ensure_cielo_smart_provider, migrations.RunPython.noop),
    ]
