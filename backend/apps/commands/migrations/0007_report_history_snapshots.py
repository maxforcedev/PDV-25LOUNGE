from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('commands', '0006_command_checkout_context')]

    operations = [
        migrations.AddField(
            model_name='command', name='table_name_snapshot',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='command', name='customer_name_snapshot',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='command', name='opened_by_name_snapshot',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='command', name='closed_by_name_snapshot',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='orderitem', name='category_id_snapshot',
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='orderitem', name='category_name_snapshot',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
    ]
