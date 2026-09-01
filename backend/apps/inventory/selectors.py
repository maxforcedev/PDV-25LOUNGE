from django.db.models import Exists, OuterRef

from apps.companies.models import Branch, Status
from apps.products.models import InventoryBehavior
from apps.products.selectors import countable_products

from .models import InventoryCountItem, Stock


def eligible_workflow_stocks(branch, *, exclude_open_counts=False):
    queryset = Stock.objects.select_related('product', 'product__fraction_config').filter(
        branch=branch,
        product__company_id=branch.company_id,
        product__status=Status.ACTIVE,
        product__archived_at__isnull=True,
        product__inventory_behavior=InventoryBehavior.DIRECT,
        product__branch_configs__branch=branch,
        product__branch_configs__is_available=True,
    )
    if exclude_open_counts:
        queryset = queryset.annotate(has_open_count=Exists(
            InventoryCountItem.objects.filter(
                branch=branch,
                product_id=OuterRef('product_id'),
                is_open=True,
            )
        )).filter(has_open_count=False)
    return queryset.order_by('product__name', 'product_id')


def eligible_inventory_products(branch):
    return countable_products(branch).select_related('fraction_config').order_by(
        'branch_configs__category__name', 'name', 'pk'
    )


def active_transfer_destinations(origin_branch):
    return Branch.objects.filter(
        company_id=origin_branch.company_id,
        company__status=Status.ACTIVE,
        status=Status.ACTIVE,
    ).exclude(pk=origin_branch.pk).order_by('name', 'pk')
