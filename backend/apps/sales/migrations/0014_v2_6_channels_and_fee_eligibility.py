from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('products', '0008_v2_6_product_configuration'),
        ('sales', '0013_localize_payment_method_names'),
    ]
    operations = [
        migrations.AddField(
            model_name='sale', name='channel',
            field=models.CharField(choices=[('counter', 'Balcao'), ('table', 'Mesa'), ('command', 'Comanda')], default='counter', max_length=10),
        ),
        migrations.AddField(model_name='saleitem', name='participates_in_service_fee', field=models.BooleanField(default=True, editable=False)),
        migrations.AddField(model_name='saleitem', name='participates_in_commission', field=models.BooleanField(default=True, editable=False)),
    ]
