import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cash', '0007_withdrawal_effect_by_category'),
        ('suppliers', '0006_supplier_branch_ownership_soft_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashmovement',
            name='beneficiary_supplier',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name='cash_withdrawals',
                to='suppliers.supplier',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='cashmovement',
            name='cash_movement_required_beneficiary_coherent',
        ),
        migrations.AddConstraint(
            model_name='cashmovement',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        movement_type='manual_entry',
                        withdrawal_category__isnull=True,
                        beneficiary_user__isnull=True,
                        beneficiary_supplier__isnull=True,
                    )
                    | models.Q(
                        movement_type='withdrawal',
                        withdrawal_category='supplier',
                        beneficiary_supplier__isnull=True,
                    )
                    | models.Q(
                        movement_type='withdrawal',
                        withdrawal_category='supplier',
                        beneficiary_user__isnull=True,
                        beneficiary_supplier__isnull=False,
                    )
                    | models.Q(
                        movement_type='withdrawal',
                        withdrawal_category__in=('dj', 'artist', 'advance', 'promoter'),
                        beneficiary_user__isnull=False,
                        beneficiary_supplier__isnull=True,
                    )
                    | models.Q(
                        movement_type='withdrawal',
                        withdrawal_category='other',
                        beneficiary_supplier__isnull=True,
                    )
                ),
                name='cash_movement_required_beneficiary_coherent',
            ),
        ),
    ]
