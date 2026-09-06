from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('inventory', '0020_stock_maximum_quantity')]

    operations = [
        migrations.AlterField(
            model_name='transferdivergenceresolution',
            name='observation',
            field=models.TextField(blank=True),
        ),
    ]
