import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('commands', '0004_command_payment'), ('companies', '0040_customer_and_permissions')]

    operations = [
        migrations.AddField(
            model_name='command', name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='commands', to='companies.customer'),
        ),
    ]
