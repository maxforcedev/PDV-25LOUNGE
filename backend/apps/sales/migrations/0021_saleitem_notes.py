from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sales', '0020_sale_pos_device')]

    operations = [
        migrations.AddField(
            model_name='saleitem',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
    ]
