import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Count, Q


DISPATCHED_STATUSES = {
    'IN_TRANSIT', 'PARTIALLY_RECEIVED', 'RECEIVED', 'RECEIVED_WITH_DIVERGENCE',
}


def backfill_v2_5_metadata(apps, schema_editor):
    StockTransfer = apps.get_model('inventory', 'StockTransfer')
    InventoryCount = apps.get_model('inventory', 'InventoryCount')
    InventoryCountItem = apps.get_model('inventory', 'InventoryCountItem')

    dispatched_transfers = list(
        StockTransfer.objects.filter(status__in=DISPATCHED_STATUSES).values_list(
            'pk', flat=True
        )
    )
    empty_open_counts = list(
        InventoryCount.objects.filter(status='OPEN').annotate(
            item_count=Count('items')
        ).filter(item_count=0).values_list('pk', flat=True)
    )
    duplicate_open_pairs = list(
        InventoryCountItem.objects.filter(inventory_count__status='OPEN').values(
            'inventory_count__branch_id', 'product_id'
        ).annotate(count_count=Count('inventory_count', distinct=True)).filter(
            count_count__gt=1
        ).values_list('inventory_count__branch_id', 'product_id')
    )
    if dispatched_transfers or empty_open_counts or duplicate_open_pairs:
        raise RuntimeError(
            'A migracao V2.5 exige estado novo e consistente; nenhum metadado '
            'idempotente sera fabricado. '
            f'Transferencias ja despachadas: {dispatched_transfers}; '
            f'Contagens sem itens: {empty_open_counts}; '
            f'pares filial/produto duplicados: {duplicate_open_pairs}.'
        )

    items = InventoryCountItem.objects.select_related('inventory_count')
    for item in items:
        count = item.inventory_count
        is_open = count.status == 'OPEN'
        InventoryCountItem.objects.filter(pk=item.pk).update(
            branch_id=count.branch_id,
            is_open=is_open,
            closed_at=None if is_open else (count.confirmed_at or count.updated_at),
        )


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0013_stockmovement_domain_origin_inventorycount_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='stocktransfer',
            name='dispatch_idempotency_key',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='stocktransfer',
            name='dispatch_payload',
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
        migrations.AddField(
            model_name='stocktransfer',
            name='dispatch_payload_fingerprint',
            field=models.CharField(blank=True, editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name='inventorycountitem',
            name='branch',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_count_items',
                to='companies.branch',
            ),
        ),
        migrations.AddField(
            model_name='inventorycountitem',
            name='closed_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='inventorycountitem',
            name='is_open',
            field=models.BooleanField(default=True, editable=False),
        ),
        migrations.RunPython(backfill_v2_5_metadata, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='inventorycountitem',
            name='branch',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_count_items',
                to='companies.branch',
            ),
        ),
        migrations.AddConstraint(
            model_name='stocktransfer',
            constraint=models.UniqueConstraint(
                fields=('origin_branch', 'dispatch_idempotency_key'),
                condition=Q(dispatch_idempotency_key__isnull=False),
                name='inventory_transfer_dispatch_idempotency_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='inventorycountitem',
            constraint=models.UniqueConstraint(
                fields=('branch', 'product'),
                condition=Q(is_open=True),
                name='inventory_open_count_branch_product_unique',
            ),
        ),
    ]
