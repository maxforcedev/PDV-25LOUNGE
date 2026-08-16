from django.db import migrations


def create_missing_stocks(apps, schema_editor):
    Branch = apps.get_model('companies', 'Branch')
    Product = apps.get_model('products', 'Product')
    Stock = apps.get_model('inventory', 'Stock')

    for company_id, product_id in Product.objects.filter(
        inventory_behavior='direct'
    ).values_list('company_id', 'id').iterator():
        Stock.objects.bulk_create(
            [
                Stock(product_id=product_id, branch_id=branch_id)
                for branch_id in Branch.objects.filter(
                    company_id=company_id
                ).values_list('id', flat=True)
            ],
            ignore_conflicts=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0010_branch_access_profile_contract'),
        ('products', '0004_product_category_contract'),
        ('inventory', '0002_stockmovement_reason_optional'),
    ]

    operations = [
        migrations.RunPython(create_missing_stocks, migrations.RunPython.noop),
    ]
