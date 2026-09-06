from django.db import migrations, models


OPERATING_EXPENSE_CATEGORIES = ('dj', 'artist', 'advance', 'promoter', 'supplier')


def classify_withdrawals(apps, schema_editor):
    CashMovement = apps.get_model('cash', 'CashMovement')
    CashMovement.objects.filter(
        movement_type='withdrawal',
        withdrawal_category__in=OPERATING_EXPENSE_CATEGORIES,
    ).update(result_effect='operating_expense')
    CashMovement.objects.filter(
        movement_type='withdrawal', withdrawal_category='other',
    ).update(result_effect='neutral')


class Migration(migrations.Migration):
    dependencies = [('cash', '0006_cash_movement_reason_optional')]

    operations = [
        migrations.RemoveConstraint(
            model_name='cashmovement',
            name='cash_movement_withdrawal_classification_coherent',
        ),
        migrations.RunPython(classify_withdrawals, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='cashmovement',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        movement_type='manual_entry',
                        withdrawal_category__isnull=True,
                        beneficiary_user__isnull=True,
                        result_effect='neutral',
                    )
                    | models.Q(
                        movement_type='withdrawal',
                        withdrawal_category__in=OPERATING_EXPENSE_CATEGORIES,
                        result_effect='operating_expense',
                    )
                    | models.Q(
                        movement_type='withdrawal',
                        withdrawal_category='other',
                        result_effect='neutral',
                    )
                ),
                name='cash_movement_withdrawal_classification_coherent',
            ),
        ),
    ]
