from django.db import migrations, models

import apps.inventory.storage


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0017_command_stock_traceability'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventorycount',
            name='mode',
            field=models.CharField(
                choices=[('FULL', 'Contagem completa'), ('PARTIAL', 'Contagem parcial')],
                default='PARTIAL', max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='inventorycount',
            name='observation',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='lossrecord',
            name='attachment',
            field=models.FileField(
                blank=True, max_length=500,
                storage=apps.inventory.storage.PrivateLossStorage(),
                upload_to=apps.inventory.storage.loss_attachment_path,
                validators=(apps.inventory.storage.validate_loss_attachment,),
            ),
        ),
        migrations.AlterField(
            model_name='lossrecord',
            name='observation',
            field=models.TextField(blank=True, default=''),
        ),
    ]
