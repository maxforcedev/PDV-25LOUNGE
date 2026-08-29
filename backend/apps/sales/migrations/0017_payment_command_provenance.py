import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sales', '0016_sale_customer'), ('commands', '0006_command_checkout_context')]

    operations = [
        migrations.AddField(
            model_name='payment', name='occurred_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='payment', name='source_command_payment',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                        related_name='final_payment', to='commands.commandpayment'),
        ),
    ]
