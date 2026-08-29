from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0012_product_archive_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='modifiergroup',
            name='inherit_component_quantity',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='modifiergroup',
            name='substitution_component',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='substitution_modifier_groups', to='products.product'),
        ),
        migrations.AddField(
            model_name='modifieroption',
            name='stock_product',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='modifier_stock_options', to='products.product'),
        ),
        migrations.AlterField(
            model_name='modifieroption',
            name='option_type',
            field=models.CharField(choices=[('add', 'Adicionar'), ('remove', 'Remover'), ('observation', 'Observação'), ('text', 'Texto'), ('product_input', 'Produto ou insumo'), ('component_substitution', 'Substituição de componente')], default='add', max_length=24),
        ),
    ]
