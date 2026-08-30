import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, transaction

from apps.companies.models import Branch
from apps.products.models import FractionableProductConfig, InventoryBehavior, Product

from .content import exact_multiply_quantized
from .models import Stock


logger = logging.getLogger(__name__)
CONTENT_QUANTUM = Decimal('0.000000001')
MATERIALIZATION_LOCK_NAMESPACE = 0x53544F4300000000


def _active_fraction_config(product):
    return FractionableProductConfig.objects.filter(
        product_id=product.pk,
        tracking_active=True,
    ).first()


def _expected_fractional_content(product, config, quantity):
    if config is None:
        return None
    if config.package_content is None or config.package_content <= 0:
        logger.error('Invalid active fraction config for product_id=%s', product.pk)
        raise ValidationError({
            'product': 'O produto possui configuracao fracionada ativa invalida.'
        })
    return exact_multiply_quantized(quantity, config.package_content, CONTENT_QUANTUM)


def expected_fractional_content(product, quantity):
    return _expected_fractional_content(
        product, _active_fraction_config(product), quantity
    )


def _lock_company_materialization(company_id):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT pg_advisory_xact_lock(%s)',
            [MATERIALIZATION_LOCK_NAMESPACE + company_id],
        )


@transaction.atomic
def materialize_stock(*, product, branch):
    branch_id = branch.pk if hasattr(branch, 'pk') else branch
    product_id = product.pk if hasattr(product, 'pk') else product
    branch = Branch.objects.select_for_update().get(pk=branch_id)
    product = Product.objects.select_for_update().get(pk=product_id)
    if product.company_id != branch.company_id:
        raise ValidationError({'branch': 'A filial deve pertencer a empresa do produto.'})
    if product.inventory_behavior != InventoryBehavior.DIRECT:
        raise ValidationError({'product': 'Somente produtos com estoque proprio possuem saldo.'})

    config = FractionableProductConfig.objects.select_for_update().filter(
        product_id=product.pk,
        tracking_active=True,
    ).first()
    if config is None:
        product._state.fields_cache.pop('fraction_config', None)
    else:
        product._state.fields_cache['fraction_config'] = config
    current_content = _expected_fractional_content(product, config, Decimal('0'))
    defaults = {'current_quantity': Decimal('0')}
    if current_content is not None:
        defaults['current_content'] = current_content

    queryset = Stock.objects.select_for_update(of=('self',)).filter(
        product=product, branch=branch
    ).order_by('pk')
    stock = queryset.first()
    if stock is None:
        Stock.objects.bulk_create(
            [Stock(product=product, branch=branch, **defaults)],
            ignore_conflicts=True,
        )
        stock = queryset.get()
    elif current_content is not None and stock.current_content is None:
        stock.current_content = _expected_fractional_content(
            product, config, stock.current_quantity
        )
        stock.save(update_fields=('current_content', 'updated_at'))
        logger.warning(
            'Reconciled missing fractional content for stock_id=%s product_id=%s branch_id=%s',
            stock.pk,
            product.pk,
            branch.pk,
        )
    return stock


@transaction.atomic
def materialize_product_stocks(product):
    if product.inventory_behavior != InventoryBehavior.DIRECT:
        return
    _lock_company_materialization(product.company_id)
    branches = Branch.objects.filter(company_id=product.company_id).order_by('pk')
    Stock.objects.bulk_create(
        [
            Stock(product_id=product.pk, branch_id=branch_id)
            for branch_id in branches.values_list('pk', flat=True)
        ],
        ignore_conflicts=True,
    )


@transaction.atomic
def materialize_branch_stocks(branch):
    _lock_company_materialization(branch.company_id)
    products = list(Product.objects.select_for_update().filter(
        company_id=branch.company_id,
        inventory_behavior=InventoryBehavior.DIRECT,
    ).order_by('pk'))
    active_fraction_product_ids = set(
        FractionableProductConfig.objects.select_for_update().filter(
            product_id__in=[product.pk for product in products],
            tracking_active=True,
        ).values_list('product_id', flat=True)
    )
    Stock.objects.bulk_create(
        [
            Stock(
                product_id=product.pk,
                branch_id=branch.pk,
                current_content=(
                    Decimal('0') if product.pk in active_fraction_product_ids else None
                ),
            )
            for product in products
        ],
        ignore_conflicts=True,
    )
