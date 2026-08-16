from django.db import migrations
from django.db.models import Max


def assign_missing_categories(apps, schema_editor):
    Category = apps.get_model('products', 'Category')
    Product = apps.get_model('products', 'Product')

    company_ids = Product.objects.filter(category__isnull=True).values_list(
        'company_id', flat=True
    ).distinct()
    for company_id in company_ids:
        category = Category.objects.filter(
            company_id=company_id, name__iexact='Sem categoria'
        ).first()
        if category is None:
            last_order = Category.objects.filter(company_id=company_id).aggregate(
                value=Max('sort_order')
            )['value']
            category = Category.objects.create(
                company_id=company_id,
                name='Sem categoria',
                sort_order=(last_order + 1) if last_order is not None else 0,
            )
        Product.objects.filter(company_id=company_id, category__isnull=True).update(
            category=category
        )


class Migration(migrations.Migration):
    dependencies = [('products', '0002_sprint_6_1_expand')]

    operations = [
        migrations.RunPython(assign_missing_categories, migrations.RunPython.noop),
    ]
