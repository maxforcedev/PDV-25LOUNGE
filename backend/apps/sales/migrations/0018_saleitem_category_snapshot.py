from django.db import migrations, models


def backfill_category_snapshots(apps, schema_editor):
    SaleItem = apps.get_model('sales', 'SaleItem')
    ProductBranchConfig = apps.get_model('products', 'ProductBranchConfig')

    configs = {
        (product_id, branch_id): (category_id, category_name)
        for product_id, branch_id, category_id, category_name in ProductBranchConfig.objects.filter(
            category_id__isnull=False,
        ).values_list('product_id', 'branch_id', 'category_id', 'category__name')
    }
    for item in SaleItem.objects.select_related('sale', 'product__category').iterator():
        category_id, category_name = configs.get(
            (item.product_id, item.sale.branch_id),
            (item.product.category_id, item.product.category.name),
        )
        SaleItem.objects.filter(pk=item.pk).update(
            category_id_snapshot=category_id,
            category_name_snapshot=category_name,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('products', '0018_category_soft_delete_financial_overrides'),
        ('sales', '0017_payment_command_provenance'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleitem',
            name='category_id_snapshot',
            field=models.PositiveBigIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='category_name_snapshot',
            field=models.CharField(blank=True, editable=False, max_length=150),
        ),
        migrations.RunPython(backfill_category_snapshots, migrations.RunPython.noop),
    ]
