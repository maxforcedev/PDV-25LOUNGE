from django.db.models import Q

from apps.companies.models import Status

from .models import InventoryBehavior, Product, ProductBranchConfig


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
