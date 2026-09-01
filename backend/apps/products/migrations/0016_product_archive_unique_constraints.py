from django.db import migrations, models
import django.db.models.functions.text


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0015_branch_operational_scope'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='product',
            name='products_product_company_normalized_name_unique',
        ),
        migrations.RemoveConstraint(
            model_name='product',
            name='products_product_company_internal_code_ci_unique',
        ),
        migrations.RemoveConstraint(
            model_name='product',
            name='products_product_company_barcode_ci_unique',
        ),
        migrations.RemoveConstraint(
            model_name='product',
            name='products_product_company_sku_ci_unique',
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                models.F('company'),
                django.db.models.functions.text.Lower('normalized_name'),
                condition=models.Q(('archived_at__isnull', True)),
                name='products_product_company_normalized_name_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                models.F('company'),
                django.db.models.functions.text.Lower('internal_code'),
                condition=models.Q(('archived_at__isnull', True)),
                name='products_product_company_internal_code_ci_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                models.F('company'),
                django.db.models.functions.text.Lower('barcode'),
                condition=models.Q(('archived_at__isnull', True)) & ~models.Q(('barcode', '')),
                name='products_product_company_barcode_ci_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                models.F('company'),
                django.db.models.functions.text.Lower('sku'),
                condition=(
                    models.Q(('archived_at__isnull', True))
                    & models.Q(('sku__isnull', False))
                    & ~models.Q(('sku', ''))
                ),
                name='products_product_company_sku_ci_unique',
            ),
        ),
    ]
