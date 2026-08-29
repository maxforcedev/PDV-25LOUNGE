from django.db import migrations


def add_production_capability(apps, schema_editor):
    Capability = apps.get_model('saas', 'Capability')
    Capability.objects.update_or_create(
        code='feature.production',
        defaults={
            'name': 'Producao e impressao',
            'value_type': 'BOOLEAN',
            'is_active': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [('saas', '0007_block_6_global_brand_assets')]

    operations = [migrations.RunPython(add_production_capability, migrations.RunPython.noop)]
