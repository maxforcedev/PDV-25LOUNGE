from django.db.models import CharField, DecimalField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from apps.companies.models import Status

from .models import (
    BranchProductPrice, InventoryBehavior, Product, ProductBranchConfig, SalesChannel,
)


def operational_product_configs(branch):
    return ProductBranchConfig.objects.filter(
        branch=branch,
        branch__status=Status.ACTIVE,
        branch__company__status=Status.ACTIVE,
        is_available=True,
        product__company_id=branch.company_id,
        product__status=Status.ACTIVE,
        product__archived_at__isnull=True,
    ).select_related('product', 'category', 'branch')


def operational_products(branch):
    return Product.objects.filter(
        branch_configs__in=operational_product_configs(branch),
    ).distinct()


def sellable_products_for_branch(branch, channel, *, search=None, barcode=None):
    """Return products that are currently sellable at a branch and sales channel."""
    if channel not in SalesChannel.values:
        raise ValueError('Canal de venda invalido.')

    channel_field = f'available_{channel}'
    branch_price = BranchProductPrice.objects.filter(
        branch=branch, product_id=OuterRef('pk')
    ).values('sale_price')[:1]
    branch_config = ProductBranchConfig.objects.filter(
        branch=branch, product_id=OuterRef('pk')
    )
    queryset = Product.objects.select_related('company', 'category').annotate(
        effective_sale_price=Coalesce(
            Subquery(branch_price), 'sale_price', output_field=DecimalField(),
        ),
        branch_available=Subquery(branch_config.values('is_available')[:1]),
        branch_channel=Coalesce(
            Subquery(branch_config.values(channel_field)[:1]), channel_field,
        ),
        effective_category_id=Coalesce(
            Subquery(branch_config.values('category_id')[:1]), 'category_id',
            output_field=Product._meta.get_field('category').target_field,
        ),
        effective_category_name=Coalesce(
            Subquery(branch_config.values('category__name')[:1]), 'category__name',
            output_field=CharField(),
        ),
    ).filter(
        company_id=branch.company_id,
        status=Status.ACTIVE,
        archived_at__isnull=True,
        is_sellable=True,
        branch_available=True,
        branch_channel=True,
        branch_configs__branch=branch,
        branch_configs__branch__status=Status.ACTIVE,
        branch_configs__branch__company__status=Status.ACTIVE,
    )
    if barcode is not None:
        queryset = queryset.filter(barcode=barcode)
    elif search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(internal_code__icontains=search)
            | Q(barcode__icontains=search)
        )
    return queryset.order_by('-is_favorite', 'name', 'id')


def inventory_products(branch):
    return operational_products(branch).filter(inventory_behavior=InventoryBehavior.DIRECT)


def countable_products(branch):
    return inventory_products(branch)


def purchasable_products(branch):
    return inventory_products(branch)


def priceable_products(branch=None, *, company=None):
    queryset = Product.objects.filter(
        status=Status.ACTIVE,
        archived_at__isnull=True,
        branch_configs__is_available=True,
        branch_configs__branch__status=Status.ACTIVE,
    )
    if branch is not None:
        queryset = queryset.filter(
            company_id=branch.company_id,
            branch_configs__branch=branch,
        )
    elif company is not None:
        queryset = queryset.filter(company=company)
    return queryset.distinct()


def historical_products(company):
    return Product.objects.filter(company=company)


def operational_category_filter(branch, prefix=''):
    return Q(**{
        f'{prefix}branch_configs__branch': branch,
        f'{prefix}branch_configs__is_available': True,
        f'{prefix}branch_configs__category__deleted_at__isnull': True,
    })
