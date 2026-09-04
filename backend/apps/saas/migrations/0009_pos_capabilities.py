from django.db import migrations


CAPABILITIES = (
    ('pos.enabled', 'CORE POS', 'BOOLEAN'),
    ('pos.devices.max', 'Dispositivos CORE POS', 'INTEGER'),
)


def add_pos_capabilities(apps, schema_editor):
    Capability = apps.get_model('saas', 'Capability')
    for code, name, value_type in CAPABILITIES:
        Capability.objects.update_or_create(
            code=code,
            defaults={'name': name, 'value_type': value_type, 'is_active': True},
        )


class Migration(migrations.Migration):
    dependencies = [('saas', '0008_production_feature_capability')]
    operations = [migrations.RunPython(add_pos_capabilities, migrations.RunPython.noop)]
