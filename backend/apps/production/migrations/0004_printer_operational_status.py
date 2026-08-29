from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('production', '0003_printer_connections_and_test_jobs')]

    operations = [
        migrations.AddField(
            model_name='printerdevice',
            name='last_operational_error',
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name='printerdevice',
            name='last_test_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='printerdevice',
            name='operational_status',
            field=models.CharField(
                choices=[
                    ('not_tested', 'Não testada'), ('online', 'Online'),
                    ('offline', 'Offline'), ('bridge_unavailable', 'Bridge indisponível'),
                    ('failed', 'Falha'),
                ],
                default='not_tested', max_length=24,
            ),
        ),
    ]
