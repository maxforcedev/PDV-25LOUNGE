from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0016_product_archive_unique_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='modifiergroup',
            name='min_total_quantity',
            field=models.DecimalField(decimal_places=3, default=Decimal('0'), max_digits=12),
        ),
        migrations.AddField(
            model_name='modifiergroup',
            name='max_total_quantity',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True),
        ),
    ]
