# Generated manually for Sprints 9 and 10.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0003_materialize_direct_product_stocks'),
        ('sales', '0003_sale_sales_sale_operation_amounts_coherent_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stockmovement',
            name='movement_type',
            field=models.CharField(
                choices=[
                    ('entry', 'Entrada'), ('exit', 'Saida'), ('adjustment', 'Ajuste'),
                    ('sale', 'Venda'), ('sale_cancellation', 'Cancelamento de venda'),
                    ('consumption', 'Consumacao'),
                    ('consumption_cancellation', 'Cancelamento de consumacao'),
                ],
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='sale',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='stock_movements', to='sales.sale'),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='original_movement',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='cancellation_movements', to='inventory.stockmovement'),
        ),
        migrations.RemoveConstraint(
            model_name='stockmovement', name='inventory_movement_quantity_sign',
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(movement_type__in=('entry', 'sale_cancellation',
                                                'consumption_cancellation'), quantity__gt=0)
                    | models.Q(movement_type__in=('exit', 'sale', 'consumption'), quantity__lt=0)
                    | models.Q(movement_type='adjustment')
                ),
                name='inventory_movement_quantity_sign',
            ),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(movement_type__in=('entry', 'exit', 'adjustment'), sale__isnull=True,
                             original_movement__isnull=True)
                    | models.Q(movement_type__in=('sale', 'consumption'), sale__isnull=False,
                               original_movement__isnull=True)
                    | models.Q(movement_type__in=('sale_cancellation', 'consumption_cancellation'),
                               sale__isnull=False, original_movement__isnull=False)
                ),
                name='inventory_movement_sales_links_coherent',
            ),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.UniqueConstraint(
                fields=('original_movement',), condition=models.Q(original_movement__isnull=False),
                name='inventory_movement_original_unique',
            ),
        ),
    ]
