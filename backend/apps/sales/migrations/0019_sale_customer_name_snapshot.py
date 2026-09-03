from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sales', '0018_saleitem_category_snapshot')]

    operations = [
        migrations.AddField(
            model_name='sale', name='customer_name_snapshot',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
    ]
