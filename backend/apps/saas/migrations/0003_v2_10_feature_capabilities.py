from django.db import migrations


def seed_feature_capabilities(apps, schema_editor):
    Capability = apps.get_model('saas', 'Capability')
    for code, name, value_type in [
        ('feature.tables', 'Mesas', 'BOOLEAN'),
        ('feature.commands', 'Comandas', 'BOOLEAN'),
        ('feature.counter', 'Balcao', 'BOOLEAN'),
        ('feature.consumption', 'Consumacao interna', 'BOOLEAN'),
        ('feature.cash_register', 'Caixa', 'BOOLEAN'),
    ]:
        Capability.objects.update_or_create(
            code=code,
            defaults={'name': name, 'value_type': value_type, 'is_active': True},
        )


def remove_feature_capabilities(apps, schema_editor):
    Capability = apps.get_model('saas', 'Capability')
    Capability.objects.filter(
        code__in=[
            'feature.tables', 'feature.commands', 'feature.counter',
            'feature.consumption', 'feature.cash_register',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('saas', '0002_billingrecord_proof_reference_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_feature_capabilities, remove_feature_capabilities),
    ]
