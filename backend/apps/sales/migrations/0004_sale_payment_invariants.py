from django.db import migrations, models
from django.db.models import Q


def normalize_normal_sales(apps, schema_editor):
    Sale = apps.get_model('sales', 'Sale')
    Sale.objects.filter(operation_type='sale').exclude(
        charged_amount__isnull=True
    ).update(charged_amount=None)


class Migration(migrations.Migration):
    dependencies = [('sales', '0003_sale_sales_sale_operation_amounts_coherent_and_more')]

    operations = [
        migrations.RunPython(normalize_normal_sales, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='payment',
            name='sales_payment_amount_nonnegative',
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='sales_payment_amount_positive',
            ),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.CheckConstraint(
                condition=(
                    Q(
                        operation_type='sale',
                        cash_session__isnull=False,
                        charged_amount__isnull=True,
                    )
                    | Q(operation_type='consumption', charged_amount=0)
                    | Q(
                        operation_type='consumption',
                        charged_amount__gt=0,
                        cash_session__isnull=False,
                    )
                ),
                name='sales_sale_cash_session_coherent',
            ),
        ),
    ]
