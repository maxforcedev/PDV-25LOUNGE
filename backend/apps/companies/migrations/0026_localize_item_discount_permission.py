from django.db import migrations


def localize_item_discount_permission(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    Permission.objects.filter(code='sales.apply_item_discount').update(
        label='Aplicar desconto por item',
        description=(
            'Aplicar desconto manual em itens de venda, independente do '
            'desconto na conta.'
        ),
    )


class Migration(migrations.Migration):
    dependencies = [('companies', '0025_localize_permission_catalog')]
    operations = [
        migrations.RunPython(
            localize_item_discount_permission,
            migrations.RunPython.noop,
        )
    ]
