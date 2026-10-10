from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0057_remove_legacy_command_table_transfer_permission'),
    ]

    operations = [
        migrations.AddField(model_name='branchsettings', name='uses_audit', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_customers', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_financial', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_inventory', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_pos', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_products', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_production', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_promotions', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_purchases', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_reports', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='branchsettings', name='uses_suppliers', field=models.BooleanField(default=True)),
    ]
