from decimal import Decimal

from django.db.models import (
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from apps.cash.models import CashMovement, CashMovementType, CashSession, CashSessionStatus
from apps.inventory.models import Stock, StockMovement
from apps.sales.models import OperationType, Payment, Sale, SaleItem, SaleStatus


MONEY_FIELD = DecimalField(max_digits=20, decimal_places=2)
QUANTITY_FIELD = DecimalField(max_digits=20, decimal_places=3)
ZERO_MONEY = Value(Decimal('0.00'), output_field=MONEY_FIELD)


def period_filter(queryset, field, start, end):
    return queryset.filter(**{f'{field}__gte': start, f'{field}__lte': end})


def filtered_sales(*, branch, start, end, operation_type, filters):
    queryset = period_filter(
        Sale.objects.filter(branch=branch, operation_type=operation_type),
        'created_at',
        start,
        end,
    )
    mappings = {
        'operator': 'created_by_id',
        'product': 'items__product_id',
        'category': 'items__product__category_id',
        'payment_method': 'payments__payment_method_id',
        'status': 'status',
        'beneficiary': 'beneficiary_user_id',
        'user_type': 'beneficiary_user__user_type',
    }
    for parameter, lookup in mappings.items():
        if filters.get(parameter) is not None:
            queryset = queryset.filter(**{lookup: filters[parameter]})
    if filters.get('number'):
        queryset = queryset.filter(sale_number__icontains=filters['number'])
    if filters.get('search'):
        value = filters['search']
        queryset = queryset.filter(
            Q(sale_number__icontains=value)
            | Q(items__product_name__icontains=value)
            | Q(items__internal_code__icontains=value)
        )
    return queryset.distinct()


def sale_rows(queryset):
    return queryset.select_related(
        'created_by', 'beneficiary_user'
    ).prefetch_related('items', 'payments').order_by('-created_at', '-id')


def commercial_summary(queryset):
    finalized = queryset.filter(status=SaleStatus.FINALIZED)
    totals = finalized.aggregate(
        revenue=Coalesce(Sum('total'), ZERO_MONEY),
        count=Count('id'),
        manual_discount=Coalesce(Sum('discount'), ZERO_MONEY),
        promotion_discount=Coalesce(Sum('promotion_discount_total'), ZERO_MONEY),
    )
    totals['total_discount'] = totals['manual_discount'] + totals['promotion_discount']
    totals['average'] = (
        totals['revenue'] / totals['count'] if totals['count'] else Decimal('0.00')
    )
    cancelled = queryset.filter(status=SaleStatus.CANCELLED).aggregate(
        count=Count('id'), value=Coalesce(Sum('total'), ZERO_MONEY)
    )
    return totals, cancelled


def filtered_sale_items(queryset, filters=None):
    items = SaleItem.objects.filter(sale_id__in=queryset.values('id'))
    filters = filters or {}
    if filters.get('product') is not None:
        items = items.filter(product_id=filters['product'])
    if filters.get('category') is not None:
        items = items.filter(product__category_id=filters['category'])
    return items


def consumption_summary(queryset, *, include_cost=False, filters=None):
    finalized = queryset.filter(status=SaleStatus.FINALIZED)
    totals = finalized.aggregate(
        count=Count('id'),
        reference=Coalesce(Sum('subtotal'), ZERO_MONEY),
        charged=Coalesce(Sum('total'), ZERO_MONEY),
    )
    totals['subsidy'] = totals['reference'] - totals['charged']
    items = filtered_sale_items(finalized, filters)
    totals['quantity'] = items.aggregate(
        value=Coalesce(Sum('quantity'), Value(Decimal('0.000'), output_field=QUANTITY_FIELD))
    )['value']
    if include_cost:
        cost = ExpressionWrapper(F('unit_cost') * F('quantity'), output_field=MONEY_FIELD)
        totals['historical_cost'] = items.aggregate(
            value=Coalesce(Sum(cost), ZERO_MONEY)
        )['value']
    return totals


def payment_totals(queryset, filters=None):
    payments = Payment.objects.filter(
        sale_id__in=queryset.filter(status=SaleStatus.FINALIZED).values('id')
    )
    if filters and filters.get('payment_method') is not None:
        payments = payments.filter(payment_method_id=filters['payment_method'])
    return list(
        payments
        .values('payment_method_code', 'payment_method_name')
        .annotate(amount=Sum('amount'))
        .order_by('-amount', 'payment_method_name')
    )


def sale_rankings(queryset, *, limit=10, filters=None):
    items = filtered_sale_items(
        queryset.filter(status=SaleStatus.FINALIZED), filters
    )
    products = list(
        items.values('product_id', 'product_name', 'internal_code')
        .annotate(quantity=Sum('quantity'), revenue=Sum('net_subtotal'))
        .order_by('-quantity', '-revenue', 'product_name')[:limit]
    )
    categories = list(
        items.values('product__category_id', 'product__category__name')
        .annotate(quantity=Sum('quantity'), revenue=Sum('net_subtotal'))
        .order_by('-quantity', '-revenue', 'product__category__name')[:limit]
    )
    for row in categories:
        row['category_id'] = row.pop('product__category_id')
        row['category_name'] = row.pop('product__category__name') or 'Sem categoria'
    return products, categories


def filtered_cash_sessions(*, branch, start, end, filters):
    movement_base = CashMovement.objects.filter(cash_session_id=OuterRef('pk'))
    manual = movement_base.filter(
        movement_type=CashMovementType.MANUAL_ENTRY
    ).values('cash_session').annotate(value=Sum('amount')).values('value')
    withdrawals = movement_base.filter(
        movement_type=CashMovementType.WITHDRAWAL
    ).values('cash_session').annotate(value=Sum('amount')).values('value')
    cash = Payment.objects.filter(
        sale__cash_session_id=OuterRef('pk'),
        sale__status=SaleStatus.FINALIZED,
        payment_method_code='cash',
    ).values('sale__cash_session').annotate(value=Sum('amount')).values('value')
    queryset = period_filter(
        CashSession.objects.filter(branch=branch), 'opened_at', start, end
    ).select_related('cash_register', 'opened_by').annotate(
        manual_entries=Coalesce(Subquery(manual, output_field=MONEY_FIELD), ZERO_MONEY),
        withdrawals=Coalesce(Subquery(withdrawals, output_field=MONEY_FIELD), ZERO_MONEY),
        cash_payments=Coalesce(Subquery(cash, output_field=MONEY_FIELD), ZERO_MONEY),
    ).annotate(
        calculated_expected=ExpressionWrapper(
            F('opening_amount') + F('manual_entries') + F('cash_payments') - F('withdrawals'),
            output_field=MONEY_FIELD,
        ),
        expected=Case(
            When(status=CashSessionStatus.CLOSED, then=F('closing_expected_amount')),
            default=F('calculated_expected'),
            output_field=MONEY_FIELD,
        ),
    )
    mappings = {
        'cash_register': 'cash_register_id',
        'operator': 'opened_by_id',
        'status': 'status',
    }
    for parameter, lookup in mappings.items():
        if filters.get(parameter) is not None:
            queryset = queryset.filter(**{lookup: filters[parameter]})
    return queryset.order_by('-opened_at', '-id')


def current_cash_sessions(branch):
    now = CashSession.objects.filter(branch=branch, status=CashSessionStatus.OPEN)
    # Reuse the same annotations without restricting an open session to its opening date.
    if not now.exists():
        return now
    first = now.order_by('opened_at').values_list('opened_at', flat=True).first()
    from django.utils import timezone

    return filtered_cash_sessions(
        branch=branch, start=first, end=timezone.now(), filters={'status': CashSessionStatus.OPEN}
    )


def filtered_withdrawals(*, branch, start, end, filters):
    queryset = period_filter(
        CashMovement.objects.filter(
            cash_session__branch=branch, movement_type=CashMovementType.WITHDRAWAL
        ),
        'created_at',
        start,
        end,
    ).select_related('cash_session__cash_register', 'user', 'beneficiary_user')
    mappings = {
        'category': 'withdrawal_category',
        'beneficiary': 'beneficiary_user_id',
        'operator': 'user_id',
        'cash_register': 'cash_session__cash_register_id',
    }
    for parameter, lookup in mappings.items():
        if filters.get(parameter) is not None:
            queryset = queryset.filter(**{lookup: filters[parameter]})
    return queryset.order_by('-created_at', '-id')


def withdrawal_summary(queryset):
    totals = queryset.aggregate(
        count=Count('id'), amount=Coalesce(Sum('amount'), ZERO_MONEY)
    )
    totals['by_category'] = list(
        queryset.values('withdrawal_category')
        .annotate(count=Count('id'), amount=Sum('amount'))
        .order_by('withdrawal_category')
    )
    return totals


def filtered_inventory_movements(*, branch, start, end, filters):
    queryset = period_filter(
        StockMovement.objects.filter(stock__branch=branch), 'created_at', start, end
    ).select_related('stock__product__category', 'user', 'sale')
    mappings = {
        'product': 'stock__product_id',
        'category': 'stock__product__category_id',
        'movement_type': 'movement_type',
        'user': 'user_id',
    }
    for parameter, lookup in mappings.items():
        if filters.get(parameter) is not None:
            queryset = queryset.filter(**{lookup: filters[parameter]})
    return queryset.order_by('-created_at', '-id')


def inventory_kpis(branch, *, include_value=False):
    stocks = Stock.objects.filter(branch=branch)
    result = {
        'zero_count': stocks.filter(current_quantity=0).count(),
        'below_minimum_count': stocks.filter(
            current_quantity__gt=0, current_quantity__lt=F('minimum_quantity')
        ).count(),
    }
    if include_value:
        value = ExpressionWrapper(
            F('current_quantity') * F('product__cost'), output_field=MONEY_FIELD
        )
        result['inventory_value'] = stocks.aggregate(
            value=Coalesce(Sum(value), ZERO_MONEY)
        )['value']
    return result
