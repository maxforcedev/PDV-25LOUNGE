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
from django.db.models.functions import Coalesce, ExtractHour, ExtractIsoWeekDay, TruncHour
from django.utils import timezone

from apps.cash.models import CashMovement, CashMovementType, CashSession, CashSessionStatus, ResultEffect
from apps.companies.models import BranchSettings
from apps.inventory.models import Stock, StockMovement
from apps.inventory.models import MovementType
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
        'seller': 'seller_user_id',
        'product': 'items__product_id',
        'category': 'items__product__category_id',
        'payment_method': 'payments__payment_method_id',
        'payment_method_code': 'payments__payment_method_code',
        'status': 'status',
        'beneficiary': 'beneficiary_user_id',
        'user_type': 'beneficiary_user__user_type',
    }
    for parameter, lookup in mappings.items():
        if filters.get(parameter) is not None:
            queryset = queryset.filter(**{lookup: filters[parameter]})
    if filters.get('weekday') is not None:
        queryset = queryset.annotate(
            report_iso_weekday=ExtractIsoWeekDay('created_at')
        ).filter(report_iso_weekday=filters['weekday'] + 1)
    if filters.get('hour') is not None:
        queryset = queryset.annotate(
            report_hour=ExtractHour('created_at')
        ).filter(report_hour=filters['hour'])
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
        'created_by', 'seller_user', 'discount_approved_by', 'beneficiary_user'
    ).prefetch_related('items', 'payments').order_by('-created_at', '-id')


def commercial_summary(queryset):
    finalized = queryset.filter(status=SaleStatus.FINALIZED)
    totals = finalized.aggregate(
        customer_total=Coalesce(Sum('total'), ZERO_MONEY),
        gross=Coalesce(Sum('subtotal'), ZERO_MONEY),
        count=Count('id'),
        manual_discount=Coalesce(Sum('discount'), ZERO_MONEY),
        promotion_discount=Coalesce(Sum('promotion_discount_total'), ZERO_MONEY),
        service_fee=Coalesce(Sum('service_fee_amount'), ZERO_MONEY),
        commission=Coalesce(Sum('commission_amount'), ZERO_MONEY),
    )
    totals['total_discount'] = totals['manual_discount'] + totals['promotion_discount']
    totals['effective_revenue'] = totals['gross'] - totals['total_discount']
    totals['revenue'] = totals['customer_total']
    totals['average'] = (
        totals['customer_total'] / totals['count'] if totals['count'] else Decimal('0.00')
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
    finalized = queryset.filter(status=SaleStatus.FINALIZED)
    items = filtered_sale_items(finalized, filters).select_related('sale', 'product__category')
    by_product = {}
    by_category = {}
    for item in items:
        sale = item.sale
        net = item.net_subtotal
        # Allocate the sale's manual discount proportionally to the item's net subtotal
        # so that the ranking revenue reconciles with the effective revenue (Sale.total sum).
        sale_net_total = sale.subtotal - sale.promotion_discount_total
        if sale_net_total > 0 and sale.discount > 0:
            allocated_discount = (sale.discount * net / sale_net_total).quantize(Decimal('0.01'))
        else:
            allocated_discount = Decimal('0.00')
        revenue = (net - allocated_discount).quantize(Decimal('0.01'))
        product_key = item.product_id
        category_key = item.product.category_id
        product_entry = by_product.setdefault(product_key, {
            'product_id': product_key,
            'product_name': item.product_name,
            'internal_code': item.internal_code,
            'quantity': Decimal('0.000'),
            'revenue': Decimal('0.00'),
        })
        product_entry['quantity'] += item.quantity
        product_entry['revenue'] += revenue
        category_entry = by_category.setdefault(category_key, {
            'category_id': category_key,
            'category_name': item.product.category.name if item.product.category_id else 'Sem categoria',
            'quantity': Decimal('0.000'),
            'revenue': Decimal('0.00'),
        })
        category_entry['quantity'] += item.quantity
        category_entry['revenue'] += revenue
    products = sorted(by_product.values(), key=lambda row: (-row['quantity'], -row['revenue'], row['product_name']))[:limit]
    categories = sorted(by_category.values(), key=lambda row: (-row['quantity'], -row['revenue'], row['category_name']))[:limit]
    return products, categories


def hourly_sales(queryset):
    rows = queryset.filter(status=SaleStatus.FINALIZED).annotate(
        hour=TruncHour('created_at', tzinfo=timezone.get_current_timezone())
    ).values('hour').annotate(
        count=Count('id'),
        gross=Coalesce(Sum('subtotal'), ZERO_MONEY),
        discounts=Coalesce(
            Sum(F('discount') + F('promotion_discount_total'), output_field=MONEY_FIELD),
            ZERO_MONEY,
        ),
        service_fee=Coalesce(Sum('service_fee_amount'), ZERO_MONEY),
        customer_total=Coalesce(Sum('total'), ZERO_MONEY),
    ).order_by('hour')
    return [
        {**row, 'effective_revenue': row['gross'] - row['discounts']}
        for row in rows
    ]


def sale_user_groups(queryset, user_field):
    if user_field not in ('created_by', 'seller_user'):
        raise ValueError('Campo de agrupamento invalido.')
    finalized = queryset.filter(status=SaleStatus.FINALIZED)
    rows = finalized.values(
        f'{user_field}_id', f'{user_field}__first_name',
        f'{user_field}__last_name', f'{user_field}__email',
    ).annotate(
        count=Count('id'),
        gross=Coalesce(Sum('subtotal'), ZERO_MONEY),
        manual_discount=Coalesce(Sum('discount'), ZERO_MONEY),
        promotion_discount=Coalesce(Sum('promotion_discount_total'), ZERO_MONEY),
        service_fee=Coalesce(Sum('service_fee_amount'), ZERO_MONEY),
        customer_total=Coalesce(Sum('total'), ZERO_MONEY),
    ).order_by('-customer_total', f'{user_field}__first_name', f'{user_field}_id')
    result = []
    for row in rows:
        first_name = row.pop(f'{user_field}__first_name') or ''
        last_name = row.pop(f'{user_field}__last_name') or ''
        email = row.pop(f'{user_field}__email') or ''
        user_id = row.pop(f'{user_field}_id')
        row['user'] = {'id': user_id, 'name': f'{first_name} {last_name}'.strip() or email}
        row['total_discount'] = row['manual_discount'] + row['promotion_discount']
        row['effective_revenue'] = row['gross'] - row['total_discount']
        row['average'] = row['customer_total'] / row['count'] if row['count'] else Decimal('0.00')
        if user_field == 'seller_user':
            row['commission'] = finalized.filter(
                seller_user_id=user_id
            ).aggregate(value=Coalesce(Sum('commission_amount'), ZERO_MONEY))['value']
        result.append(row)
    return result


def cancellation_summary(*, branch, start, end, category=None):
    queryset = period_filter(
        Sale.objects.filter(
            branch=branch, operation_type=OperationType.SALE, status=SaleStatus.CANCELLED,
        ),
        'cancelled_at', start, end,
    )
    if category:
        queryset = queryset.filter(items__product__category_id=category).distinct()
    totals = queryset.aggregate(
        count=Count('id'), value=Coalesce(Sum('total'), ZERO_MONEY)
    )
    return queryset, totals


def dashboard_time_analysis(queryset, *, branch, start, end, category=None):
    finalized = list(queryset.filter(status=SaleStatus.FINALIZED).only(
        'id', 'created_at', 'subtotal', 'promotion_discount_total', 'discount'
    ))
    heatmap = {}
    for sale in finalized:
        local = timezone.localtime(sale.created_at)
        key = (local.weekday(), local.hour)
        row = heatmap.setdefault(key, {
            'weekday': local.weekday(), 'hour': local.hour, 'count': 0,
            'revenue': Decimal('0.00'),
        })
        row['count'] += 1
        row['revenue'] += sale.subtotal - sale.promotion_discount_total - sale.discount
    heatmap_rows = []
    for row in heatmap.values():
        row['average'] = row['revenue'] / row['count'] if row['count'] else Decimal('0.00')
        heatmap_rows.append(row)
    heatmap_rows.sort(key=lambda row: (row['weekday'], row['hour']))

    duration = end - start
    previous_start = start - duration
    previous_end = start
    previous = period_filter(
        Sale.objects.filter(
            branch=branch,
            operation_type=OperationType.SALE,
            status=SaleStatus.FINALIZED,
        ), 'created_at', previous_start, previous_end,
    )
    if category:
        previous = previous.filter(items__product__category_id=category).distinct()

    def by_day(rows):
        grouped = {}
        for sale in rows:
            day = timezone.localtime(sale.created_at).date().isoformat()
            entry = grouped.setdefault(day, {'date': day, 'count': 0, 'revenue': Decimal('0.00')})
            entry['count'] += 1
            entry['revenue'] += sale.subtotal - sale.promotion_discount_total - sale.discount
        return sorted(grouped.values(), key=lambda row: row['date'])

    return heatmap_rows, by_day(finalized), by_day(previous)


def operational_result(*, branch, start, end, sales, cash_session=None):
    finalized = sales.filter(status=SaleStatus.FINALIZED)
    summary, _ = commercial_summary(finalized)
    cost_expression = ExpressionWrapper(
        F('unit_cost') * F('quantity'), output_field=MONEY_FIELD
    )
    cogs = SaleItem.objects.filter(sale_id__in=finalized.values('id')).aggregate(
        value=Coalesce(Sum(cost_expression), ZERO_MONEY)
    )['value']
    withdrawals = period_filter(
        CashMovement.objects.filter(
            cash_session__branch=branch,
            movement_type=CashMovementType.WITHDRAWAL,
        ),
        'created_at', start, end,
    )
    if cash_session:
        withdrawals = withdrawals.filter(cash_session=cash_session)
    expense = withdrawals.filter(result_effect=ResultEffect.OPERATING_EXPENSE).aggregate(
        value=Coalesce(Sum('amount'), ZERO_MONEY)
    )['value']
    unclassified = withdrawals.filter(result_effect=ResultEffect.UNCLASSIFIED).aggregate(
        count=Count('id'), amount=Coalesce(Sum('amount'), ZERO_MONEY)
    )
    scoped_start, scoped_end = start, end
    if cash_session:
        scoped_start = max(start, cash_session.opened_at)
        scoped_end = min(end, cash_session.closed_at or end)
    seconds = max(Decimal('0'), Decimal(str((scoped_end - scoped_start).total_seconds())))
    settings = BranchSettings.objects.filter(branch=branch).first()
    daily_cost = settings.fixed_daily_cost if settings else Decimal('0.00')
    fixed_cost = (daily_cost * seconds / Decimal('86400')).quantize(Decimal('0.01'))
    result = (
        summary['effective_revenue'] - cogs - summary['commission'] - expense - fixed_cost
    )
    margin = (
        result * Decimal('100') / summary['effective_revenue']
        if summary['effective_revenue'] else Decimal('0.00')
    )
    return {
        'gross': summary['gross'],
        'promotion_discount': summary['promotion_discount'],
        'manual_discount': summary['manual_discount'],
        'discounts': summary['total_discount'],
        'effective_revenue': summary['effective_revenue'],
        'service_fee': summary['service_fee'],
        'customer_total': summary['customer_total'],
        'cogs': cogs,
        'commission': summary['commission'],
        'operating_expenses': expense,
        'fixed_cost': fixed_cost,
        'result': result,
        'margin': margin.quantize(Decimal('0.01')),
        'unclassified_withdrawals': unclassified,
    }


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
    queryset = CashSession.objects.filter(branch=branch)
    # Intersect the session's [opened_at, closed_at] with the requested period, so
    # sessions opened before the period or still open are included when relevant.
    if start or end:
        queryset = queryset.filter(opened_at__lte=end) if end else queryset
        if start:
            queryset = queryset.filter(
                Q(closed_at__isnull=True) | Q(closed_at__gte=start)
            )
    queryset = queryset.select_related('cash_register', 'opened_by').annotate(
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


def stock_consumption_report(*, branch, start, end, filters):
    movement_types = (
        MovementType.SALE,
        MovementType.SALE_CANCELLATION,
        MovementType.CONSUMPTION,
        MovementType.CONSUMPTION_CANCELLATION,
        MovementType.EXIT,
    )
    rows = period_filter(
        StockMovement.objects.filter(stock__branch=branch, movement_type__in=movement_types),
        'created_at', start, end,
    ).select_related('stock__product__category', 'user', 'sale', 'original_movement')
    if filters.get('product') is not None:
        rows = rows.filter(stock__product_id=filters['product'])
    if filters.get('category') is not None:
        rows = rows.filter(stock__product__category_id=filters['category'])
    origin = filters.get('origin')
    if origin == 'sale':
        rows = rows.filter(movement_type=MovementType.SALE)
    elif origin == 'consumption':
        rows = rows.filter(movement_type=MovementType.CONSUMPTION)
    elif origin == 'manual_exit':
        rows = rows.filter(movement_type=MovementType.EXIT)
    elif origin == 'reversal':
        rows = rows.filter(movement_type__in=(MovementType.SALE_CANCELLATION, MovementType.CONSUMPTION_CANCELLATION))
    summary = {}
    for movement in rows:
        product = movement.stock.product
        key = product.pk
        entry = summary.setdefault(key, {
            'product': product,
            'gross_quantity': Decimal('0.000'),
            'returned_quantity': Decimal('0.000'),
            'net_quantity': Decimal('0.000'),
            'estimated_cost': Decimal('0.00'),
            'movement_count': 0,
        })
        quantity = movement.quantity.copy_abs()
        if movement.quantity < 0:
            entry['gross_quantity'] += quantity
            entry['estimated_cost'] += (quantity * product.cost).quantize(Decimal('0.01'))
        else:
            entry['returned_quantity'] += quantity
            entry['estimated_cost'] -= (quantity * product.cost).quantize(Decimal('0.01'))
        entry['movement_count'] += 1
    for entry in summary.values():
        entry['net_quantity'] = entry['gross_quantity'] - entry['returned_quantity']
    summary_rows = sorted(
        summary.values(), key=lambda item: (-item['net_quantity'], item['product'].name)
    )
    return rows.order_by('-created_at', '-id'), summary_rows


def inventory_kpis(branch, *, include_value=False):
    stocks = Stock.objects.filter(branch=branch)
    result = {
        'zero_count': stocks.filter(current_quantity=0).count(),
        'negative_count': stocks.filter(current_quantity__lt=0).count(),
        'below_minimum_count': stocks.filter(
            current_quantity__gt=0, current_quantity__lt=F('minimum_quantity')
        ).count(),
        'physical_products': stocks.count(),
    }
    if include_value:
        value = ExpressionWrapper(
            Case(
                When(current_quantity__gt=0, then=F('current_quantity')),
                default=Value(Decimal('0.000')),
                output_field=QUANTITY_FIELD,
            ) * F('product__cost'), output_field=MONEY_FIELD
        )
        result['inventory_value'] = stocks.aggregate(
            value=Coalesce(Sum(value), ZERO_MONEY)
        )['value']
    return result
