from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('companies', '0035_functional_permission_scopes_and_branch_prices')]

    operations = [
        migrations.AddField(model_name='branchsettings', name='default_table_quantity', field=models.PositiveIntegerField(default=20)),
        migrations.AddField(model_name='branchsettings', name='default_table_seats', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='branchsettings', name='default_table_prefix', field=models.CharField(default='Mesa ', max_length=50)),
        migrations.AddField(model_name='branchsettings', name='consumption_limit_enabled', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='branchsettings', name='command_consumption_limit', field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
        migrations.AddField(model_name='branchsettings', name='table_consumption_limit', field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
    ]
