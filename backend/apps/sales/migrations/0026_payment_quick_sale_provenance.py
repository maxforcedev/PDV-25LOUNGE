import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0006_quick_sale_payment_provider_source'),
        ('sales', '0025_saleitem_historical_promotion_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='source_quick_sale_payment',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='final_payment',
                to='pos.quicksalepayment',
            ),
        ),
    ]
