from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('commands', '0005_command_customer')]

    operations = [
        migrations.AddField(
            model_name='command', name='checkout_discount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddField(
            model_name='command', name='checkout_service_fee_waived',
            field=models.BooleanField(default=False),
        ),
    ]
