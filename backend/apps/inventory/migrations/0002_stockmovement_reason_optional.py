from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0001_initial'),
        ('products', '0004_product_category_contract'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stockmovement',
            name='reason',
            field=models.TextField(blank=True, default=''),
        ),
    ]
