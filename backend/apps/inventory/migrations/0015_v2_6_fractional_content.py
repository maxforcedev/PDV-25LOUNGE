from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0014_v2_5_static_review_hardening'),
        ('products', '0008_v2_6_product_configuration'),
    ]

    operations = [
        migrations.AlterField(model_name='stock', name='current_quantity', field=models.DecimalField(decimal_places=9, default=0, max_digits=24)),
        migrations.AddField(model_name='stock', name='current_content', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AlterField(model_name='stockmovement', name='previous_quantity', field=models.DecimalField(decimal_places=9, max_digits=24)),
        migrations.AlterField(model_name='stockmovement', name='quantity', field=models.DecimalField(decimal_places=9, max_digits=24)),
        migrations.AlterField(model_name='stockmovement', name='final_quantity', field=models.DecimalField(decimal_places=9, max_digits=24)),
        migrations.AddField(model_name='stockmovement', name='previous_content', field=models.DecimalField(blank=True, decimal_places=9, editable=False, max_digits=24, null=True)),
        migrations.AddField(model_name='stockmovement', name='content_quantity', field=models.DecimalField(blank=True, decimal_places=9, editable=False, max_digits=24, null=True)),
        migrations.AddField(model_name='stockmovement', name='final_content', field=models.DecimalField(blank=True, decimal_places=9, editable=False, max_digits=24, null=True)),
        migrations.RemoveConstraint(model_name='stockmovement', name='inventory_movement_quantity_nonzero'),
        migrations.RemoveConstraint(model_name='stockmovement', name='inventory_movement_quantity_sign'),
        migrations.AddConstraint(model_name='stockmovement', constraint=models.CheckConstraint(condition=models.Q(models.Q(('quantity', 0), _negated=True), models.Q(('content_quantity__isnull', False), models.Q(('content_quantity', 0), _negated=True)), _connector='OR'), name='inventory_movement_quantity_nonzero')),
        migrations.AddConstraint(model_name='stockmovement', constraint=models.CheckConstraint(condition=models.Q(models.Q(('movement_type__in', ('entry', 'sale_cancellation', 'consumption_cancellation')), ('quantity__gt', 0)), models.Q(('content_quantity__gt', 0), ('movement_type__in', ('entry', 'sale_cancellation', 'consumption_cancellation')), ('quantity', 0)), models.Q(('movement_type__in', ('exit', 'sale', 'consumption')), ('quantity__lt', 0)), models.Q(('content_quantity__lt', 0), ('movement_type__in', ('exit', 'sale', 'consumption')), ('quantity', 0)), ('movement_type', 'adjustment'), _connector='OR'), name='inventory_movement_quantity_sign')),
        migrations.AddField(model_name='stocktransferitem', name='package_content_snapshot', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AddField(model_name='stocktransferitem', name='content_unit_snapshot', field=models.CharField(blank=True, max_length=2)),
        migrations.AddField(model_name='stocktransferreceiptitem', name='received_content_snapshot', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AlterField(model_name='lossrecord', name='quantity', field=models.DecimalField(decimal_places=9, max_digits=24)),
        migrations.AddField(model_name='lossrecord', name='content_quantity', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AddField(model_name='lossrecord', name='content_unit', field=models.CharField(blank=True, max_length=2)),
        migrations.AddField(model_name='lossrecord', name='package_content_snapshot', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.RemoveConstraint(model_name='lossrecord', name='inventory_loss_values_valid'),
        migrations.AddConstraint(model_name='lossrecord', constraint=models.CheckConstraint(condition=models.Q(models.Q(('quantity__gt', 0), models.Q(('content_quantity__gt', 0), ('quantity', 0)), _connector='OR'), ('unit_cost_snapshot__gte', 0), ('sale_price_snapshot__gte', 0), ('cost_impact__gte', 0), ('potential_sale_value__gte', 0)), name='inventory_loss_values_valid')),
        migrations.AlterField(model_name='inventorycountitem', name='theoretical_quantity', field=models.DecimalField(decimal_places=9, max_digits=24)),
        migrations.AlterField(model_name='inventorycountitem', name='counted_quantity', field=models.DecimalField(decimal_places=9, max_digits=24)),
        migrations.AlterField(model_name='inventorycountitem', name='difference_quantity', field=models.DecimalField(decimal_places=9, max_digits=24)),
        migrations.AddField(model_name='inventorycountitem', name='theoretical_content', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AddField(model_name='inventorycountitem', name='counted_complete_packages', field=models.DecimalField(blank=True, decimal_places=0, max_digits=18, null=True)),
        migrations.AddField(model_name='inventorycountitem', name='counted_residual_content', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AddField(model_name='inventorycountitem', name='counted_content', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AddField(model_name='inventorycountitem', name='difference_content', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AddField(model_name='inventorycountitem', name='content_unit', field=models.CharField(blank=True, max_length=2)),
        migrations.AddField(model_name='inventorycountitem', name='package_content_snapshot', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
    ]
