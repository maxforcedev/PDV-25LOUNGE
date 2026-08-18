from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

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
from apps.products.models import InventoryBehavior
from apps.sales.models import OperationType, Payment, Sale, SaleItem, SaleStatus


MONEY_FIELD = DecimalField(max_digits=20, decimal_places=2)
QUANTITY_FIELD = DecimalField(max_digits=20, decimal_places=3)
ZERO_MONEY = Value(Decimal('0.00'), output_field=MONEY_FIELD)
CENT = Decimal('0.01')


def period_filter(queryset, field, start, end):
    return queryset.filter(
        **{f'{field}__gte': start, f'{field}__lt': period_end_exclusive(end)}
    )


def period_end_exclusive(end):
    return end + timedelta(seconds=1) if end.microsecond == 0 else end + timedelta(microseconds=1)


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
    ).prefetch_related('items__product__category', 'payments').order_by('-created_at', '-id')


def _allocate_money(total, weighted_rows):
    """Allocate a cent value exactly, resolving residual cents by weight then stable id."""
    total = Decimal(total or 0).quantize(CENT)
    rows = [(key, max(Decimal(weight or 0), Decimal('0'))) for key, weight in weighted_rows]
    if not rows:
        return {}
    if total == 0:
        return {key: Decimal('0.00') for key, _weight in rows}
    weight_total = sum((weight for _key, weight in rows), Decimal('0'))
    if weight_total == 0:
        result = {key: Decimal('0.00') for key, _weight in rows}
        result[min(key for key, _weight in rows)] = total
        return result
    raw = {key: total * weight / weight_total for key, weight in rows}
    result = {
        key: value.quantize(CENT, rounding=ROUND_DOWN)
        for key, value in raw.items()
    }
    residual_cents = int((total - sum(result.values(), Decimal('0.00'))) / CENT)
    order = sorted(
        rows,
        key=lambda row: (-(raw[row[0]] - result[row[0]]), row[0]),
    )
    for key, _weight in order[:residual_cents]:
        result[key] += CENT
    return result


def _item_matches(item, filters):
    filters = filters or {}
    return (
        (filters.get('product') is None or item.product_id == filters['product'])
        and (
            filters.get('category') is None
            or item.product.category_id == filters['category']
        )
    )


def _sale_item_financials(sale, filters=None):
    items = sorted(sale.items.all(), key=lambda item: item.pk)
    account_discounts = _allocate_money(
        sale.discount, [(item.pk, item.net_subtotal) for item in items]
    )
    revenues = {
        item.pk: item.net_subtotal - account_discounts[item.pk]
        for item in items
    }
    service_fees = _allocate_money(
        sale.service_fee_amount, [(item.pk, revenues[item.pk]) for item in items]
    )
    commissions = _allocate_money(
        sale.commission_amount, [(item.pk, revenues[item.pk]) for item in items]
    )
    return [
        {
            'item': item,
            'gross': item.subtotal,
            'promotion_discount': item.promotion_benefit,
            'item_discount': item.manual_discount,
            'account_discount': account_discounts[item.pk],
            'effective_revenue': revenues[item.pk],
            'service_fee': service_fees[item.pk],
            'commission': commissions[item.pk],
        }
        for item in items
        if _item_matches(item, filters)
    ]


def _financial_sales(queryset):
    return queryset.select_related('created_by', 'seller_user').prefetch_related(
        'items__product__category', 'payments'
    ).order_by('id')


def _scoped_sale_values(sale, filters=None):
    rows = _sale_item_financials(sale, filters)
    values = {
        'gross': sum((row['gross'] for row in rows), Decimal('0.00')),
        'promotion_discount': sum(
            (row['promotion_discount'] for row in rows), Decimal('0.00')
        ),
        'item_discount': sum((row['item_discount'] for row in rows), Decimal('0.00')),
        'account_discount': sum(
            (row['account_discount'] for row in rows), Decimal('0.00')
        ),
        'effective_revenue': sum(
            (row['effective_revenue'] for row in rows), Decimal('0.00')
        ),
        'service_fee': sum((row['service_fee'] for row in rows), Decimal('0.00')),
        'commission': sum((row['commission'] for row in rows), Decimal('0.00')),
    }
    values['manual_discount'] = values['item_discount'] + values['account_discount']
    values['total_discount'] = values['promotion_discount'] + values['manual_discount']
    values['customer_total'] = values['effective_revenue'] + values['service_fee']
    values['has_items'] = bool(rows)
    return values


def _scoped_payment_rows(sale, filters=None):
    item_rows = _sale_item_financials(sale)
    matching_ids = {
        row['item'].pk for row in item_rows if _item_matches(row['item'], filters)
    }
    if not matching_ids:
        return []
    weights = [(row['item'].pk, row['effective_revenue']) for row in item_rows]
    result = []
    for payment in sale.payments.all():
        allocation = _allocate_money(payment.amount, weights)
        result.append({
            'payment_method_name': payment.payment_method_name,
            'payment_method_code': payment.payment_method_code,
            'amount': sum(
                (allocation[item_id] for item_id in matching_ids), Decimal('0.00')
            ),
            'payment_method_id': payment.payment_method_id,
        })
    return result


def commercial_summary(queryset, filters=None):
    totals = {
        'customer_total': Decimal('0.00'),
        'gross': Decimal('0.00'),
        'count': 0,
        'discounted_count': 0,
        'manual_discount_count': 0,
        'account_discount': Decimal('0.00'),
        'item_discount': Decimal('0.00'),
        'manual_discount': Decimal('0.00'),
        'promotion_discount': Decimal('0.00'),
        'total_discount': Decimal('0.00'),
        'effective_revenue': Decimal('0.00'),
        'service_fee': Decimal('0.00'),
        'commission': Decimal('0.00'),
    }
    for sale in _financial_sales(queryset.filter(status=SaleStatus.FINALIZED)):
        values = _scoped_sale_values(sale, filters)
        if not values['has_items']:
            continue
        totals['count'] += 1
        if values['total_discount'] > 0:
            totals['discounted_count'] += 1
        if values['manual_discount'] > 0:
            totals['manual_discount_count'] += 1
        for key in totals.keys() - {'count', 'discounted_count', 'manual_discount_count'}:
            totals[key] += values[key]
    totals['revenue'] = totals['effective_revenue']
    totals['average'] = (
        totals['effective_revenue'] / totals['count']
        if totals['count'] else Decimal('0.00')
    )
    cancelled = {'count': 0, 'value': Decimal('0.00')}
    for sale in _financial_sales(queryset.filter(status=SaleStatus.CANCELLED)):
        values = _scoped_sale_values(sale, filters)
        if values['has_items']:
            cancelled['count'] += 1
            cancelled['value'] += values['customer_total']
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
    totals = {'count': 0, 'reference': Decimal('0.00'), 'charged': Decimal('0.00')}
    for sale in _financial_sales(finalized):
        items = sorted(sale.items.all(), key=lambda item: item.pk)
        matching = [item for item in items if _item_matches(item, filters)]
        if not matching:
            continue
        charged = _allocate_money(
            sale.total, [(item.pk, item.subtotal) for item in items]
        )
        totals['count'] += 1
        totals['reference'] += sum((item.subtotal for item in matching), Decimal('0.00'))
        totals['charged'] += sum((charged[item.pk] for item in matching), Decimal('0.00'))
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
    grouped = {}
    for sale in _financial_sales(queryset.filter(status=SaleStatus.FINALIZED)):
        for payment in _scoped_payment_rows(sale, filters):
            if filters and filters.get('payment_method') is not None and payment['payment_method_id'] != filters['payment_method']:
                continue
            if filters and filters.get('payment_method_code') and payment['payment_method_code'] != filters['payment_method_code']:
                continue
            key = (payment['payment_method_code'], payment['payment_method_name'])
            grouped[key] = grouped.get(key, Decimal('0.00')) + payment['amount']
    return [
        {'payment_method_code': key[0], 'payment_method_name': key[1], 'amount': amount}
        for key, amount in sorted(grouped.items(), key=lambda row: (-row[1], row[0][1]))
    ]


def sale_rankings(queryset, *, limit=10, filters=None):
    by_product = {}
    by_category = {}
    for sale in _financial_sales(queryset.filter(status=SaleStatus.FINALIZED)):
        for row in _sale_item_financials(sale, filters):
            item = row['item']
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
            product_entry['revenue'] += row['effective_revenue']
            category_entry = by_category.setdefault(category_key, {
                'category_id': category_key,
                'category_name': item.product.category.name if item.product.category_id else 'Sem categoria',
                'quantity': Decimal('0.000'),
                'revenue': Decimal('0.00'),
            })
            category_entry['quantity'] += item.quantity
            category_entry['revenue'] += row['effective_revenue']
    products = sorted(by_product.values(), key=lambda row: (-row['quantity'], -row['revenue'], row['product_name']))[:limit]
    categories = sorted(by_category.values(), key=lambda row: (-row['quantity'], -row['revenue'], row['category_name']))[:limit]
    return products, categories


def hourly_sales(queryset, filters=None):
    grouped = {}
    for sale in _financial_sales(queryset.filter(status=SaleStatus.FINALIZED)):
        values = _scoped_sale_values(sale, filters)
        if not values['has_items']:
            continue
        hour = timezone.localtime(sale.created_at).replace(minute=0, second=0, microsecond=0)
        row = grouped.setdefault(hour, {
            'hour': hour, 'count': 0, 'effective_revenue': Decimal('0.00'),
            'service_fee': Decimal('0.00'), 'customer_total': Decimal('0.00'),
        })
        row['count'] += 1
        for key in ('effective_revenue', 'service_fee', 'customer_total'):
            row[key] += values[key]
    return [grouped[key] for key in sorted(grouped)]


def sale_user_groups(queryset, user_field, filters=None):
    if user_field not in ('created_by', 'seller_user'):
        raise ValueError('Campo de agrupamento invalido.')
    grouped = {}
    for sale in _financial_sales(queryset.filter(status=SaleStatus.FINALIZED)):
        values = _scoped_sale_values(sale, filters)
        if not values['has_items']:
            continue
        user = getattr(sale, user_field)
        user_id = getattr(sale, f'{user_field}_id')
        row = grouped.setdefault(user_id, {
            'user': {
                'id': user_id,
                'name': (user.get_full_name().strip() or user.email) if user else 'Nao informado',
            },
            'count': 0,
            **{
                key: Decimal('0.00') for key in (
                    'gross', 'account_discount', 'item_discount', 'manual_discount',
                    'promotion_discount', 'total_discount', 'effective_revenue',
                    'service_fee', 'customer_total',
                )
            },
        })
        if user_field == 'seller_user' and 'commission' not in row:
            row['commission'] = Decimal('0.00')
        row['count'] += 1
        for key in row.keys() - {'user', 'count', 'commission'}:
            row[key] += values[key]
        if user_field == 'seller_user':
            row['commission'] += values['commission']
    for row in grouped.values():
        row['average'] = row['effective_revenue'] / row['count'] if row['count'] else Decimal('0.00')
    return sorted(
        grouped.values(),
        key=lambda row: (-row['effective_revenue'], row['user']['name'], row['user']['id'] or 0),
    )


def cancellation_summary(*, branch, start, end, category=None, product=None):
    queryset = period_filter(
        Sale.objects.filter(
            branch=branch, operation_type=OperationType.SALE, status=SaleStatus.CANCELLED,
        ),
        'cancelled_at', start, end,
    )
    filters = {'category': category, 'product': product}
    filters = {key: value for key, value in filters.items() if value is not None}
    if category:
        queryset = queryset.filter(items__product__category_id=category)
    if product:
        queryset = queryset.filter(items__product_id=product)
    queryset = queryset.distinct()
    totals = {'count': 0, 'value': Decimal('0.00')}
    for sale in _financial_sales(queryset):
        values = _scoped_sale_values(sale, filters)
        if values['has_items']:
            totals['count'] += 1
            totals['value'] += values['customer_total']
    return queryset, totals


def dashboard_time_analysis(queryset, *, branch, start, end, category=None):
    filters = {'category': category} if category else {}
    finalized = list(_financial_sales(queryset.filter(status=SaleStatus.FINALIZED)))
    heatmap = {}
    for sale in finalized:
        local = timezone.localtime(sale.created_at)
        key = (local.weekday(), local.hour)
        row = heatmap.setdefault(key, {
            'weekday': local.weekday(), 'hour': local.hour, 'count': 0,
            'revenue': Decimal('0.00'),
        })
        values = _scoped_sale_values(sale, filters)
        if not values['has_items']:
            continue
        row['count'] += 1
        row['revenue'] += values['effective_revenue']
    heatmap_rows = []
    for row in heatmap.values():
        row['average'] = row['revenue'] / row['count'] if row['count'] else Decimal('0.00')
        heatmap_rows.append(row)
    heatmap_rows.sort(key=lambda row: (row['weekday'], row['hour']))

    current_end = period_end_exclusive(end)
    duration = current_end - start
    previous_start = start - duration
    previous_end = start
    previous = Sale.objects.filter(
            branch=branch,
            operation_type=OperationType.SALE,
            status=SaleStatus.FINALIZED,
            created_at__gte=previous_start,
            created_at__lt=previous_end,
        )
    if category:
        previous = previous.filter(items__product__category_id=category).distinct()

    def by_day(rows, range_start, range_end, *, end_exclusive=False):
        first_day = timezone.localtime(range_start).date()
        adjusted_end = range_end - timedelta(microseconds=1) if end_exclusive else range_end
        last_day = timezone.localtime(adjusted_end).date()
        grouped = {}
        day = first_day
        while day <= last_day:
            key = day.isoformat()
            grouped[key] = {'date': key, 'count': 0, 'revenue': Decimal('0.00')}
            day += timedelta(days=1)
        for sale in rows:
            day = timezone.localtime(sale.created_at).date().isoformat()
            values = _scoped_sale_values(sale, filters)
            if not values['has_items']:
                continue
            entry = grouped.setdefault(day, {'date': day, 'count': 0, 'revenue': Decimal('0.00')})
            entry['count'] += 1
            entry['revenue'] += values['effective_revenue']
        return sorted(grouped.values(), key=lambda row: row['date'])

    return (
        heatmap_rows,
        by_day(finalized, start, current_end, end_exclusive=True),
        by_day(_financial_sales(previous), previous_start, previous_end, end_exclusive=True),
    )


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
        'item_discount': summary['item_discount'],
        'account_discount': summary['account_discount'],
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
        queryset = queryset.filter(opened_at__lt=period_end_exclusive(end)) if end else queryset
        if start:
            queryset = queryset.filter(
                Q(closed_at__isnull=True) | Q(closed_at__gt=start)
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


def inventory_kpis(branch, *, include_value=False, category=None):
    stocks = Stock.objects.filter(
        branch=branch, product__inventory_behavior=InventoryBehavior.DIRECT,
    )
    if category:
        stocks = stocks.filter(product__category_id=category)
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
