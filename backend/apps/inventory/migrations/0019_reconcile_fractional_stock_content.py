from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


CONTENT_QUANTUM = Decimal('0.000000001')


def reconcile_fractional_stock_content(apps, schema_editor):
    FractionConfig = apps.get_model('products', 'FractionableProductConfig')
    Stock = apps.get_model('inventory', 'Stock')
    package_content_by_product = dict(
        FractionConfig.objects.filter(
            tracking_active=True,
            package_content__gt=0,
        ).values_list('product_id', 'package_content')
    )
    stocks = Stock.objects.select_for_update(of=('self',)).filter(
        product_id__in=package_content_by_product,
        current_content__isnull=True,
    ).order_by('pk')
    for stock in stocks.iterator():
        stock.current_content = (
            stock.current_quantity * package_content_by_product[stock.product_id]
        ).quantize(CONTENT_QUANTUM, rounding=ROUND_HALF_UP)
        stock.save(update_fields=('current_content',))


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0018_block_3_inventory_cockpit'),
    ]

    operations = [
        migrations.RunPython(
            reconcile_fractional_stock_content,
            migrations.RunPython.noop,
        ),
    ]
