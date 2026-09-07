from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('cash', '0008_cash_movement_supplier_beneficiary')]

    operations = [
        migrations.RunSQL(
            sql=(
                'ALTER TABLE cash_cashmovement '
                'DROP CONSTRAINT IF EXISTS cash_movement_withdrawal_classification_coherent;'
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
