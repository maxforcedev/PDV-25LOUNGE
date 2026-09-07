from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pos', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='posdevice', name='credential_fingerprint',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='posoperatorsession', name='token_fingerprint',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='branchpossettings', name='show_out_of_stock_products',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='posdevicesettings', name='show_out_of_stock_products',
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
