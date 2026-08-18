from collections import defaultdict

from django.db import migrations


def backfill_operations(apps, schema_editor):
    InventoryOperation = apps.get_model('inventory', 'InventoryOperation')
    StockMovement = apps.get_model('inventory', 'StockMovement')

    grouped = defaultdict(list)
    rows = StockMovement.objects.filter(
        movement_type__in=('entry', 'exit', 'adjustment'),
        sale__isnull=True,
    ).values(
        'id', 'operation_reference', 'movement_type', 'nature', 'reason',
        'quantity', 'final_quantity', 'user_id', 'stock__branch_id',
        'stock__product_id', 'stock__product__category_id',
    ).order_by('stock__branch_id', 'operation_reference', 'stock__product_id', 'id')
    for row in rows.iterator():
        grouped[(row['stock__branch_id'], row['operation_reference'])].append(row)

    operations = []
    for (branch_id, reference), movements in grouped.items():
        if InventoryOperation.objects.filter(
            branch_id=branch_id, idempotency_key=reference
        ).exists():
            continue
        first = movements[0]
        if len(movements) > 1 and all(
            movement['movement_type'] == 'entry' for movement in movements
        ):
            kind = 'group_entry'
            payload = {
                'category': first['stock__product__category_id'],
                'items': [
                    {
                        'product': movement['stock__product_id'],
                        'quantity': str(movement['quantity']),
                    }
                    for movement in movements
                ],
                'nature': first['nature'],
                'reason': first['reason'] or '',
            }
        else:
            movement = first
            kind = {
                'entry': 'manual_entry',
                'exit': 'manual_exit',
                'adjustment': 'manual_adjustment',
            }[movement['movement_type']]
            payload = {
                'product': movement['stock__product_id'],
                'quantity': (
                    None if movement['movement_type'] == 'adjustment'
                    else str(movement['quantity'])
                ),
                'final_quantity': (
                    str(movement['final_quantity'])
                    if movement['movement_type'] == 'adjustment' else None
                ),
                'nature': movement['nature'],
                'reason': movement['reason'] or '',
            }
        operations.append(InventoryOperation(
            branch_id=branch_id,
            idempotency_key=reference,
            kind=kind,
            payload=payload,
            created_by_id=first['user_id'],
        ))
    InventoryOperation.objects.bulk_create(operations, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0008_inventory_operation'),
    ]

    operations = [
        migrations.RunPython(backfill_operations, migrations.RunPython.noop),
    ]
