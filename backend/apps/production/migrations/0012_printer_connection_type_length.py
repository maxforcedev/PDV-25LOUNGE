from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('production', '0011_document_printing'),
    ]

    operations = [
        migrations.AlterField(
            model_name='printerdevice',
            name='connection_type',
            field=models.CharField(
                choices=[
                    ('network', 'Network'), ('stone_integrated', 'Stone integrada'),
                    ('usb', 'USB'), ('bluetooth', 'Bluetooth'),
                ],
                default='network', max_length=18,
            ),
        ),
    ]
