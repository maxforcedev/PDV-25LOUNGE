from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('cash', '0006_cash_movement_reason_optional')]

    operations = [
        migrations.RemoveConstraint(
            model_name='cashmovement',
            name='cash_movement_withdrawal_classification_coherent',
        ),
    ]
