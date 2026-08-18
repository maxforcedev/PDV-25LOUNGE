import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('sales', '0008_sale_service_fee_waived_sale_service_fee_waived_by_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='sale', name='sales_sale_discount_lte_remaining',
        ),
        migrations.RemoveConstraint(
            model_name='sale', name='sales_sale_operation_amounts_coherent',
        ),
        migrations.RemoveConstraint(
            model_name='saleitem', name='sales_item_net_subtotal_coherent',
        ),
        migrations.AddField(
            model_name='sale',
            name='idempotency_key',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='sale',
            name='item_discount_total',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='component_cost_snapshot',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='discount_approved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='approved_sale_item_discounts',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='manual_discount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.UniqueConstraint(
                condition=models.Q(idempotency_key__isnull=False),
                fields=('company', 'branch', 'operation_type', 'idempotency_key'),
                name='sales_sale_finalize_idempotency_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.CheckConstraint(
                condition=models.Q(item_discount_total__gte=0),
                name='sales_sale_item_discount_nonnegative',
            ),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    discount__lte=(
                        models.F('subtotal')
                        - models.F('promotion_discount_total')
                        - models.F('item_discount_total')
                    )
                ),
                name='sales_sale_discount_lte_remaining',
            ),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        operation_type='sale',
                        seller_user__isnull=False,
                        total=(
                            models.F('subtotal')
                            - models.F('promotion_discount_total')
                            - models.F('item_discount_total')
                            - models.F('discount')
                            + models.F('service_fee_amount')
                        ),
                    )
                    | models.Q(
                        operation_type='consumption',
                        beneficiary_user__isnull=False,
                        charged_amount__isnull=False,
                        promotion_discount_total=0,
                        item_discount_total=0,
                        discount=0,
                        seller_user__isnull=True,
                        service_fee_rate=0,
                        service_fee_amount=0,
                        commission_rate=0,
                        commission_amount=0,
                        total=models.F('charged_amount'),
                    )
                ),
                name='sales_sale_operation_amounts_coherent',
            ),
        ),
        migrations.AddConstraint(
            model_name='saleitem',
            constraint=models.CheckConstraint(
                condition=models.Q(manual_discount__gte=0),
                name='sales_item_manual_discount_nonnegative',
            ),
        ),
        migrations.AddConstraint(
            model_name='saleitem',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    manual_discount__lte=(
                        models.F('subtotal') - models.F('promotion_benefit')
                    )
                ),
                name='sales_item_manual_discount_lte_remaining',
            ),
        ),
        migrations.AddConstraint(
            model_name='saleitem',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    net_subtotal=(
                        models.F('subtotal')
                        - models.F('promotion_benefit')
                        - models.F('manual_discount')
                    )
                ),
                name='sales_item_net_subtotal_coherent',
            ),
        ),
        migrations.AddConstraint(
            model_name='saleitem',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(manual_discount=0, discount_approved_by__isnull=True)
                    | models.Q(manual_discount__gt=0, discount_approved_by__isnull=False)
                ),
                name='sales_item_discount_approval_coherent',
            ),
        ),
    ]
