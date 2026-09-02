from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0019_reconcile_fractional_stock_content'),
    ]

    operations = [
        migrations.AddField(
            model_name='stock',
            name='maximum_quantity',
            field=models.DecimalField(
                blank=True, decimal_places=3, max_digits=14, null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name='stock',
            constraint=models.CheckConstraint(
                condition=Q(maximum_quantity__isnull=True)
                | Q(maximum_quantity__gte=0),
                name='inventory_stock_maximum_nonnegative',
            ),
        ),
        migrations.AddConstraint(
            model_name='stock',
            constraint=models.CheckConstraint(
                condition=Q(maximum_quantity__isnull=True)
                | Q(maximum_quantity__gte=F('minimum_quantity')),
                name='inventory_stock_maximum_gte_minimum',
            ),
        ),
    ]
