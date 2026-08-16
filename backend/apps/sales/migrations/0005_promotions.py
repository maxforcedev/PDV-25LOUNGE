import django.db.models.deletion
from decimal import Decimal

from django.db import migrations, models
from django.db.models import F, Q
from django.db.models.functions import Lower


def populate_promotion_amounts(apps, schema_editor):
    Sale = apps.get_model('sales', 'Sale')
    SaleItem = apps.get_model('sales', 'SaleItem')
    Sale.objects.update(promotion_discount_total=Decimal('0.00'))
    SaleItem.objects.update(
        promotion_benefit=Decimal('0.00'),
        net_subtotal=F('subtotal'),
    )


class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0015_promotions_permissions'),
        ('products', '0004_product_category_contract'),
        ('sales', '0004_sale_payment_invariants'),
    ]

    operations = [
        migrations.CreateModel(
            name='Promotion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=150)),
                ('discount_type', models.CharField(choices=[('percentage', 'Percentual'), ('fixed_amount', 'Valor fixo')], max_length=20)),
                ('discount_value', models.DecimalField(decimal_places=2, max_digits=14)),
                ('starts_at', models.DateTimeField()),
                ('ends_at', models.DateTimeField()),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
                ('categories', models.ManyToManyField(blank=True, related_name='promotions', to='products.category')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='promotions', to='companies.company')),
                ('products', models.ManyToManyField(blank=True, related_name='promotions', to='products.product')),
            ],
            options={'ordering': ('-starts_at', 'name', 'id')},
        ),
        migrations.AddField(
            model_name='sale',
            name='promotion_discount_total',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='net_subtotal',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='promotion',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sale_items', to='sales.promotion'),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='promotion_benefit',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='promotion_discount_type',
            field=models.CharField(blank=True, choices=[('percentage', 'Percentual'), ('fixed_amount', 'Valor fixo')], max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='promotion_discount_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='promotion_name',
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.RunPython(populate_promotion_amounts, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='sale', name='sales_sale_discount_lte_subtotal',
        ),
        migrations.RemoveConstraint(
            model_name='sale', name='sales_sale_operation_amounts_coherent',
        ),
        migrations.AddConstraint(
            model_name='promotion',
            constraint=models.UniqueConstraint('company', Lower('name'), name='sales_promotion_company_name_ci_unique'),
        ),
        migrations.AddConstraint(
            model_name='promotion',
            constraint=models.CheckConstraint(condition=Q(starts_at__lt=F('ends_at')), name='sales_promotion_period_valid'),
        ),
        migrations.AddConstraint(
            model_name='promotion',
            constraint=models.CheckConstraint(condition=Q(discount_value__gt=0), name='sales_promotion_value_positive'),
        ),
        migrations.AddConstraint(
            model_name='promotion',
            constraint=models.CheckConstraint(condition=Q(discount_type='fixed_amount') | Q(discount_type='percentage', discount_value__lte=100), name='sales_promotion_percentage_lte_100'),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.CheckConstraint(condition=Q(promotion_discount_total__gte=0), name='sales_sale_promotion_discount_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.CheckConstraint(condition=Q(promotion_discount_total__lte=F('subtotal')), name='sales_sale_promotion_discount_lte_subtotal'),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.CheckConstraint(condition=Q(discount__lte=F('subtotal') - F('promotion_discount_total')), name='sales_sale_discount_lte_remaining'),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.CheckConstraint(
                condition=(
                    Q(operation_type='sale', total=F('subtotal') - F('promotion_discount_total') - F('discount'))
                    | Q(operation_type='consumption', beneficiary_user__isnull=False, charged_amount__isnull=False, promotion_discount_total=0, discount=0, total=F('charged_amount'))
                ),
                name='sales_sale_operation_amounts_coherent',
            ),
        ),
        migrations.AddConstraint(
            model_name='saleitem',
            constraint=models.CheckConstraint(condition=Q(promotion_benefit__gte=0), name='sales_item_promotion_benefit_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='saleitem',
            constraint=models.CheckConstraint(condition=Q(promotion_benefit__lte=F('subtotal')), name='sales_item_promotion_benefit_lte_subtotal'),
        ),
        migrations.AddConstraint(
            model_name='saleitem',
            constraint=models.CheckConstraint(condition=Q(net_subtotal=F('subtotal') - F('promotion_benefit')), name='sales_item_net_subtotal_coherent'),
        ),
        migrations.AddConstraint(
            model_name='saleitem',
            constraint=models.CheckConstraint(
                condition=(
                    Q(promotion__isnull=True, promotion_name__isnull=True, promotion_discount_type__isnull=True, promotion_discount_value__isnull=True, promotion_benefit=0)
                    | Q(promotion__isnull=False, promotion_name__isnull=False, promotion_discount_type__isnull=False, promotion_discount_value__isnull=False)
                ),
                name='sales_item_promotion_snapshot_coherent',
            ),
        ),
    ]
