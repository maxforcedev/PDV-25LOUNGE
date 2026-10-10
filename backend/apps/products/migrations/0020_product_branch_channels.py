from django.db import migrations, models


def materialize_branch_channels(apps, schema_editor):
    ProductBranchConfig = apps.get_model('products', 'ProductBranchConfig')
    for config in ProductBranchConfig.objects.select_related('product').iterator():
        changes = {
            field: getattr(config.product, field)
            for field in ('available_counter', 'available_table', 'available_command')
            if getattr(config, field) is None
        }
        if changes:
            ProductBranchConfig.objects.filter(pk=config.pk).update(**changes)


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0019_product_private_image'),
    ]

    operations = [
        migrations.RunPython(materialize_branch_channels, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='productbranchconfig',
            name='available_counter',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='productbranchconfig',
            name='available_table',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='productbranchconfig',
            name='available_command',
            field=models.BooleanField(default=True),
        ),
        migrations.RemoveField(model_name='product', name='available_counter'),
        migrations.RemoveField(model_name='product', name='available_table'),
        migrations.RemoveField(model_name='product', name='available_command'),
    ]
