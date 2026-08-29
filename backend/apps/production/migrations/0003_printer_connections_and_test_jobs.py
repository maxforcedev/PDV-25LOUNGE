from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('production', '0002_tickets_sale_sources')]

    operations = [
        migrations.AddField(
            model_name='printerdevice', name='connection_type',
            field=models.CharField(choices=[('network', 'Network'), ('usb', 'USB'), ('bluetooth', 'Bluetooth')], default='network', max_length=12),
        ),
        migrations.AddField(
            model_name='printjob', name='is_test', field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='printjob', name='production_job',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name='print_jobs', to='production.productionjob'),
        ),
    ]
