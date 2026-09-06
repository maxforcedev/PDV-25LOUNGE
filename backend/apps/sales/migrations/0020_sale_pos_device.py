import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('pos', '0001_initial'),
        ('sales', '0019_sale_customer_name_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='pos_device',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sales',
                to='pos.posdevice',
            ),
        ),
    ]
