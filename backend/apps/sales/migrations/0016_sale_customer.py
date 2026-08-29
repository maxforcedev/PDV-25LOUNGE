import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sales', '0015_v2_7_modifiers'), ('companies', '0040_customer_and_permissions')]

    operations = [
        migrations.AddField(
            model_name='sale', name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='companies.customer'),
        ),
    ]
