import unicodedata

from django.db import migrations, models
from django.db.models.functions import Lower


def normalize(value):
    display_name = ' '.join((value or '').split())
    decomposed = unicodedata.normalize('NFKD', display_name)
    return ''.join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()


def populate_and_detect_duplicates(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    seen = {}
    duplicates = []
    products = list(Product.objects.order_by('company_id', 'id'))
    for product in products:
        product.normalized_name = normalize(product.name)
        key = (product.company_id, product.normalized_name)
        if key in seen:
            duplicates.append({
                'company_id': product.company_id,
                'normalized_name': product.normalized_name,
                'product_ids': [seen[key], product.pk],
            })
        else:
            seen[key] = product.pk
    if duplicates:
        raise RuntimeError(
            'Duplicidades de nome de Product impedem a migration. '
            f'Resolva manualmente sem apagar ou renomear silenciosamente: {duplicates}'
        )
    Product.objects.bulk_update(products, ('normalized_name',))


class Migration(migrations.Migration):
    dependencies = [('products', '0005_sprint_11_5')]

    operations = [
        migrations.AddField(
            model_name='product',
            name='normalized_name',
            field=models.CharField(default='', editable=False, max_length=400),
            preserve_default=False,
        ),
        migrations.RunPython(populate_and_detect_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                'company',
                Lower('normalized_name'),
                name='products_product_company_normalized_name_unique',
            ),
        ),
    ]
