from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0011_stock_average_unit_cost_stock_last_unit_cost_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockmovement',
            name='unit_cost_snapshot',
            field=models.DecimalField(
                blank=True,
                decimal_places=12,
                editable=False,
                max_digits=28,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(unit_cost_snapshot__isnull=True)
                    | models.Q(unit_cost_snapshot__gte=0)
                ),
                name='inventory_movement_cost_snapshot_nonnegative',
            ),
        ),
    ]
