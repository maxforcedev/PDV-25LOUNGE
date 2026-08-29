from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('companies', '0041_ticket_permissions')]

    operations = [
        migrations.AddField(
            model_name='branchsettings', name='table_range_start',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name='branchsettings', name='default_table_prefix',
            field=models.CharField(blank=True, default='Mesa ', max_length=50),
        ),
        migrations.AddField(
            model_name='branchsettings', name='table_range_end',
            field=models.PositiveIntegerField(default=20),
        ),
    ]
