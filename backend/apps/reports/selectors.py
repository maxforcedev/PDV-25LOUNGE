from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
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
from apps.inventory.content import (
    exact_multiply, exact_multiply_quantized, exact_sum,
)
from apps.inventory.models import Stock, StockMovement
from apps.inventory.models import MovementType
from apps.products.models import InventoryBehavior
from apps.sales.models import OperationType, Payment, PaymentMethod, PaymentMethodCode, Sale, SaleItem, SaleStatus

from .financials import FinancialAggregator, allocate_money


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


def _apply_sale_filters(queryset, filters, *, timestamp_field):
    filters = filters or {}
    mappings = {
        'operator': 'created_by_id',
        'seller': 'seller_user_id',
        'product': 'items__product_id',
        'category': 'items__category_id_snapshot',
        'payment_method': 'payments__payment_method_id',
        'payment_method_code': 'payments__payment_method_code',
        'status': 'status',
        'beneficiary': 'beneficiary_user_id',
        'user_type': 'beneficiary_user__user_type',
        'channel': 'channel',
    }
    for parameter, lookup in mappings.items():
        if filters.get(parameter) is not None:
            queryset = queryset.filter(**{lookup: filters[parameter]})
    if filters.get('weekday') is not None:
        queryset = queryset.annotate(
            report_iso_weekday=ExtractIsoWeekDay(timestamp_field)
        ).filter(report_iso_weekday=filters['weekday'] + 1)
    if filters.get('hour') is not None:
        queryset = queryset.annotate(
            report_hour=ExtractHour(timestamp_field)
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


def filtered_sales(*, branch, start, end, operation_type, filters):
    queryset = period_filter(
        Sale.objects.filter(branch=branch, operation_type=operation_type),
        'created_at', start, end,
    )
    return _apply_sale_filters(queryset, filters, timestamp_field='created_at')


def filtered_reversals(
    *, branch, start, end, filters, operation_types=None, cash_session_ids=None,
):
    queryset = period_filter(
        Sale.objects.filter(branch=branch, status=SaleStatus.CANCELLED),
        'cancelled_at', start, end,
    )
    if operation_types is not None:
        queryset = queryset.filter(operation_type__in=operation_types)
    if cash_session_ids is not None:
        queryset = queryset.filter(cash_session_id__in=cash_session_ids)
    return _apply_sale_filters(queryset, filters, timestamp_field='cancelled_at')


def period_event_sales(*, branch, start, end, filters, operation_types):
    inflows = []
    for operation_type in operation_types:
        inflows.extend(_financial_sales(filtered_sales(
            branch=branch, start=start, end=end, operation_type=operation_type,
            filters=filters,
        )))
    reversals = list(_financial_sales(filtered_reversals(
        branch=branch, start=start, end=end, filters=filters,
        operation_types=operation_types,
    )))
    return inflows, reversals


def event_rows(inflows, reversals):
    rows = []
    for sale in inflows:
        sale._report_event_type = 'inflow'
        sale._report_event_at = sale.created_at
        sale._report_event_sign = 1
        rows.append(sale)
    for sale in reversals:
        sale._report_event_type = 'reversal'
        sale._report_event_at = sale.cancelled_at
        sale._report_event_sign = -1
        rows.append(sale)
    return sorted(
        rows,
        key=lambda sale: (
            sale._report_event_at, sale.pk,
            1 if sale._report_event_type == 'reversal' else 0,
        ),
        reverse=True,
    )


def sale_rows(queryset):
    return queryset.select_related(
        'created_by', 'seller_user', 'discount_approved_by', 'beneficiary_user'
    ).prefetch_related('items__product__category', 'payments').order_by('-created_at', '-id')


def _allocate_money(total, weighted_rows):
    return allocate_money(total, weighted_rows)


def _item_matches(item, filters):
    filters = filters or {}
    return (
        (filters.get('product') is None or item.product_id == filters['product'])
        and (
            filters.get('category') is None
            or item.category_id_snapshot == filters['category']
        )
    )


def _sale_item_financials(sale, filters=None):
    return FinancialAggregator([sale], filters).item_rows(sale)


def _financial_sales(queryset):
    if isinstance(queryset, (list, tuple)):
        return queryset
    return queryset.select_related(
        'created_by', 'seller_user', 'beneficiary_user', 'discount_approved_by'
    ).prefetch_related(
        'items__product__category', 'payments'
    ).order_by('id')


def _sales_with_status(queryset, status):
    if isinstance(queryset, (list, tuple)):
        return [sale for sale in queryset if sale.status == status]
    return _financial_sales(queryset.filter(status=status))


def _scoped_sale_values(sale, filters=None):
    return FinancialAggregator([sale], filters).sale_values(sale)


def _scoped_payment_rows(sale, filters=None):
    return FinancialAggregator([sale], filters).payment_rows(sale)


def commercial_summary(queryset, filters=None, reversals=None):
    aggregator = FinancialAggregator(_financial_sales(queryset), filters)
    if reversals is not None:
        return aggregator.commercial_events(_financial_sales(reversals)), aggregator.cancellations()
    return aggregator.commercial(), aggregator.cancellations()


def filtered_sale_items(queryset, filters=None):
    items = SaleItem.objects.filter(sale_id__in=queryset.values('id'))
    filters = filters or {}
    if filters.get('product') is not None:
        items = items.filter(product_id=filters['product'])
    if filters.get('category') is not None:
        items = items.filter(category_id_snapshot=filters['category'])
    return items


def consumption_summary(
    queryset, *, include_cost=False, filters=None, reversals=None,
):
    aggregator = FinancialAggregator(_financial_sales(queryset), filters)
    totals = (
        aggregator.consumption_events(_financial_sales(reversals))
        if reversals is not None else aggregator.consumption()
    )
    if include_cost:
        totals['historical_cost'] = totals['historical_consumption_cogs']
    return totals


def _scoped_consumption_values(sale, filters=None):
    return FinancialAggregator([sale], filters).consumption_values(sale)


def consumption_groupings(queryset, filters=None, reversals=()):
    by_beneficiary = {}
    by_user_type = {}
    for sales, sign in ((queryset, 1), (reversals, -1)):
        for sale in sales:
            values = _scoped_consumption_values(sale, filters)
            if not values:
                continue
            beneficiary = sale.beneficiary_user
            beneficiary_name = (
                beneficiary.get_full_name().strip() or beneficiary.email
                if beneficiary else 'Não informado'
            )
            beneficiary_row = by_beneficiary.setdefault(sale.beneficiary_user_id, {
                'beneficiary': {
                    'id': sale.beneficiary_user_id,
                    'name': beneficiary_name,
                    'user_type': beneficiary.user_type if beneficiary else None,
                },
                'count': 0, 'inflow_count': 0, 'reversal_count': 0,
                'reference': Decimal('0.00'),
                'charged': Decimal('0.00'),
                'benefit': Decimal('0.00'),
            })
            user_type = beneficiary.user_type if beneficiary else 'not_informed'
            type_row = by_user_type.setdefault(user_type, {
                'user_type': user_type,
                'count': 0, 'inflow_count': 0, 'reversal_count': 0,
                'reference': Decimal('0.00'),
                'charged': Decimal('0.00'),
                'benefit': Decimal('0.00'),
            })
            for row in (beneficiary_row, type_row):
                row['count'] += sign
                row['inflow_count' if sign > 0 else 'reversal_count'] += 1
                for key in ('reference', 'charged', 'benefit'):
                    row[key] += sign * values[key]
    beneficiary_rows = sorted(
        by_beneficiary.values(),
        key=lambda row: (-row['charged'], -row['reference'], row['beneficiary']['name']),
    )
    type_rows = sorted(
        by_user_type.values(),
        key=lambda row: (-row['charged'], -row['reference'], row['user_type']),
    )
    for row in beneficiary_rows + type_rows:
        row['sales_revenue'] = Decimal('0.00')
        row['consumption_charged'] = row['charged']
        row['effective_revenue'] = row['charged']
        row['service_fee'] = Decimal('0.00')
        row['total_received'] = row['charged']
    return beneficiary_rows, type_rows


def payment_totals(queryset, filters=None):
    return FinancialAggregator(_financial_sales(queryset), filters).payment_totals()


def sale_rankings(queryset, *, limit=None, filters=None, reversals=()):
    by_product = {}
    by_category = {}
    for sales, sign in ((queryset, 1), (reversals, -1)):
        for sale in sales:
            for row in _sale_item_financials(sale, filters):
                item = row['item']
                product_key = item.product_id
                category_key = item.category_id_snapshot
                product_entry = by_product.setdefault(product_key, {
                    'product_id': product_key,
                    'product_name': item.product_name,
                    'internal_code': item.internal_code,
                    'quantity': Decimal('0.000'),
                    'sales_revenue': Decimal('0.00'),
                })
                product_entry['quantity'] += sign * item.quantity
                product_entry['sales_revenue'] += sign * row['sales_revenue']
                category_entry = by_category.setdefault(category_key, {
                    'category_id': category_key,
                    'category_name': item.category_name_snapshot or 'Sem categoria',
                    'quantity': Decimal('0.000'),
                    'sales_revenue': Decimal('0.00'),
                })
                category_entry['quantity'] += sign * item.quantity
                category_entry['sales_revenue'] += sign * row['sales_revenue']
    products = sorted(by_product.values(), key=lambda row: (-row['quantity'], -row['sales_revenue'], row['product_name']))
    categories = sorted(by_category.values(), key=lambda row: (-row['quantity'], -row['sales_revenue'], row['category_name']))
    for row in products + categories:
        row['revenue'] = row['sales_revenue']
    if limit is not None:
        products = products[:limit]
        categories = categories[:limit]
    return products, categories


def hourly_sales(queryset, filters=None, reversals=()):
    grouped = {}
    for sales, sign, timestamp_field in (
        (queryset, 1, 'created_at'), (reversals, -1, 'cancelled_at'),
    ):
        for sale in sales:
            values = _scoped_sale_values(sale, filters)
            if not values['has_items']:
                continue
            hour = timezone.localtime(getattr(sale, timestamp_field)).replace(
                minute=0, second=0, microsecond=0
            )
            row = grouped.setdefault(hour, {
                'hour': hour, 'count': 0, 'inflow_count': 0, 'reversal_count': 0,
                'sales_revenue': Decimal('0.00'),
                'effective_revenue': Decimal('0.00'), 'service_fee': Decimal('0.00'),
                'total_received': Decimal('0.00'),
            })
            row['count'] += sign
            row['inflow_count' if sign > 0 else 'reversal_count'] += 1
            for key in ('sales_revenue', 'effective_revenue', 'service_fee', 'total_received'):
                row[key] += sign * values[key]
            row['customer_total'] = row['total_received']
    return [grouped[key] for key in sorted(grouped)]


def sale_user_groups(queryset, user_field, filters=None, reversals=()):
    if user_field not in ('created_by', 'seller_user'):
        raise ValueError('Campo de agrupamento inválido.')
    grouped = {}

    def group_for(sale):
        user = getattr(sale, user_field)
        user_id = getattr(sale, f'{user_field}_id')
        if user_field == 'seller_user' and user_id is None:
            return None
        row = grouped.setdefault(user_id, {
            'user': {
                'id': user_id,
                'name': (user.get_full_name().strip() or user.email) if user else 'Não informado',
            },
            'count': 0,
            'inflow_count': 0,
            'reversal_count': 0,
            'cancellation_count': 0,
            'cancellation_value': Decimal('0.00'),
            **{
                key: Decimal('0.00') for key in (
                    'gross', 'account_discount', 'item_discount', 'manual_discount',
                    'promotion_discount', 'total_discount', 'sales_revenue',
                    'consumption_charged', 'effective_revenue', 'service_fee',
                    'total_received', 'payment_total',
                )
            },
        })
        if user_field == 'seller_user' and 'commission' not in row:
            row['commission'] = Decimal('0.00')
        return row

    financial_fields = (
        'gross', 'account_discount', 'item_discount', 'manual_discount',
        'promotion_discount', 'total_discount', 'sales_revenue',
        'consumption_charged', 'effective_revenue', 'service_fee', 'total_received',
    )
    for sales, sign in ((queryset, 1), (reversals, -1)):
        for sale in sales:
            values = _scoped_sale_values(sale, filters)
            if not values['has_items']:
                continue
            row = group_for(sale)
            if row is None:
                continue
            row['count'] += sign
            row['inflow_count' if sign > 0 else 'reversal_count'] += 1
            for key in financial_fields:
                row[key] += sign * values[key]
            row['payment_total'] += sign * sum(
                (payment['amount'] for payment in _scoped_payment_rows(sale, filters)),
                Decimal('0.00'),
            )
            if sign < 0:
                row['cancellation_count'] += 1
                row['cancellation_value'] += values['total_received']
            if user_field == 'seller_user':
                row['commission'] += sign * values['commission']
                row.setdefault('commission_sale_count', 0)
                row['commission_sale_count'] += sign * int(values['commission'] > 0)
    for row in grouped.values():
        row['average'] = (
            row['sales_revenue'] / row['count']
            if row['count'] > 0 else Decimal('0.00')
        )
        row['reconciliation_delta'] = row['payment_total'] - row['total_received']
        row['payment_reconciliation_delta'] = row['reconciliation_delta']
        row['customer_total'] = row['total_received']
    return sorted(
        grouped.values(),
        key=lambda row: (-row['sales_revenue'], row['user']['name'], row['user']['id'] or 0),
    )


def cancellation_summary(*, branch, start, end, filters=None):
    filters = filters or {}
    queryset = filtered_reversals(
        branch=branch, start=start, end=end, filters=filters,
        operation_types=(OperationType.SALE,),
    )
    rows = _financial_sales(queryset)
    item_filters = {
        key: filters[key] for key in ('category', 'product')
        if filters.get(key) is not None
    }
    totals = FinancialAggregator(rows, item_filters).cancellations()
    return queryset.order_by('-cancelled_at', '-id'), totals


def receipt_summary(
    *, branch, start, end, filters, cash_session_ids=None, inflow_sales=None,
    operation_types=None,
):
    event_filters = dict(filters)
    operation_types = operation_types or (
        OperationType.SALE, OperationType.CONSUMPTION,
    )
    inflows = list(inflow_sales) if inflow_sales is not None else []
    if inflow_sales is None:
        for operation_type in operation_types:
            queryset = filtered_sales(
                branch=branch, start=start, end=end, operation_type=operation_type,
                filters=event_filters,
            )
            if cash_session_ids is not None:
                queryset = queryset.filter(cash_session_id__in=cash_session_ids)
            inflows.extend(_financial_sales(queryset))

    reversals = _financial_sales(filtered_reversals(
        branch=branch, start=start, end=end, filters=event_filters,
        operation_types=operation_types, cash_session_ids=cash_session_ids,
    ))
    result = FinancialAggregator(inflows, event_filters).receipts(reversals)

    method_id = filters.get('payment_method')
    method_code = filters.get('payment_method_code')
    if method_id is not None:
        method = PaymentMethod.objects.filter(pk=method_id).values(
            'code', 'name'
        ).first()
        if method:
            method_code = method['code']
            method_label = method['name']
        else:
            method_label = ''
    elif method_code:
        method = next(
            (row for row in result['payment_methods'] if row['code'] == method_code), None
        )
        method_label = method['name'] if method else method_code
    else:
        method_label = None
    if method_code:
        method_row = next(
            (row for row in result['payment_methods'] if row['code'] == method_code), None
        )
        result['filtered_payment_method'] = {
            'code': method_code,
            'name': method_label,
            'subtotal': method_row['net_received'] if method_row else Decimal('0.00'),
            'payment_total': (
                method_row['payment_total'] if method_row else Decimal('0.00')
            ),
            'is_integral_revenue': False,
        }
    return result


def dashboard_time_analysis(
    queryset, *, branch, start, end, category=None, reversals=(),
):
    filters = {'category': category} if category else {}
    heatmap = {}
    for sales, sign, timestamp_field in (
        (queryset, 1, 'created_at'), (reversals, -1, 'cancelled_at'),
    ):
        for sale in sales:
            local = timezone.localtime(getattr(sale, timestamp_field))
            key = (local.weekday(), local.hour)
            row = heatmap.setdefault(key, {
                'weekday': local.weekday(), 'hour': local.hour, 'count': 0,
                'inflow_count': 0, 'reversal_count': 0,
                'sales_revenue': Decimal('0.00'),
            })
            values = _scoped_sale_values(sale, filters)
            if not values['has_items']:
                continue
            row['count'] += sign
            row['inflow_count' if sign > 0 else 'reversal_count'] += 1
            row['sales_revenue'] += sign * values['sales_revenue']
    heatmap_rows = []
    for row in heatmap.values():
        row['average'] = (
            row['sales_revenue'] / row['count']
            if row['count'] > 0 else Decimal('0.00')
        )
        row['revenue'] = row['sales_revenue']
        heatmap_rows.append(row)
    heatmap_rows.sort(key=lambda row: (row['weekday'], row['hour']))

    current_end = period_end_exclusive(end)
    duration = current_end - start
    previous_start = start - duration
    previous_end = start - timedelta(microseconds=1)
    previous, previous_reversals = period_event_sales(
        branch=branch, start=previous_start, end=previous_end, filters=filters,
        operation_types=(OperationType.SALE,),
    )

    def by_day(rows, reversal_rows, range_start, range_end, *, end_exclusive=False):
        first_day = timezone.localtime(range_start).date()
        adjusted_end = range_end - timedelta(microseconds=1) if end_exclusive else range_end
        last_day = timezone.localtime(adjusted_end).date()
        grouped = {}
        day = first_day
        while day <= last_day:
            key = day.isoformat()
            grouped[key] = {
                'date': key, 'count': 0, 'inflow_count': 0,
                'reversal_count': 0, 'sales_revenue': Decimal('0.00'),
            }
            day += timedelta(days=1)
        for sales, sign, timestamp_field in (
            (rows, 1, 'created_at'), (reversal_rows, -1, 'cancelled_at'),
        ):
            for sale in sales:
                day = timezone.localtime(getattr(sale, timestamp_field)).date().isoformat()
                values = _scoped_sale_values(sale, filters)
                if not values['has_items']:
                    continue
                entry = grouped.setdefault(day, {
                    'date': day, 'count': 0, 'inflow_count': 0,
                    'reversal_count': 0, 'sales_revenue': Decimal('0.00'),
                })
                entry['count'] += sign
                entry['inflow_count' if sign > 0 else 'reversal_count'] += 1
                entry['sales_revenue'] += sign * values['sales_revenue']
        result = sorted(grouped.values(), key=lambda row: row['date'])
        for entry in result:
            entry['revenue'] = entry['sales_revenue']
        return result

    return (
        heatmap_rows,
        by_day(queryset, reversals, start, current_end, end_exclusive=True),
        by_day(previous, previous_reversals, previous_start, start, end_exclusive=True),
    )


def operational_result(*, branch, start, end, sales, cash_session=None, filters=None):
    consumptions = period_filter(
        Sale.objects.filter(
            branch=branch,
            operation_type=OperationType.CONSUMPTION,
        ),
        'created_at', start, end,
    )
    if cash_session:
        consumptions = consumptions.filter(cash_session=cash_session)
    operations = list(_financial_sales(sales)) + list(_financial_sales(consumptions))
    reversals = filtered_reversals(
        branch=branch, start=start, end=end, filters={},
        operation_types=(OperationType.SALE, OperationType.CONSUMPTION),
        cash_session_ids=(cash_session.pk,) if cash_session else None,
    )
    reversals = list(_financial_sales(reversals))
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
    fixed_cost = (daily_cost * seconds / Decimal('86400')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    result = FinancialAggregator(operations, filters).operational_statement(
        operating_expenses=expense, fixed_cost=fixed_cost,
        reversal_sales=reversals,
    )
    result['discounts'] = result['total_discount']
    result['cogs'] = result['historical_sales_cogs']
    result['unclassified_withdrawals'] = unclassified
    result['_event_inflows'] = operations
    result['_event_reversals'] = reversals
    return result


def filtered_cash_sessions(*, branch, start, end, filters):
    # Import lazily: CommandPayment already depends on cash and sales models.
    from apps.commands.models import CommandPayment, CommandPaymentStatus

    movement_base = CashMovement.objects.filter(cash_session_id=OuterRef('pk'))
    manual = movement_base.filter(
        movement_type=CashMovementType.MANUAL_ENTRY
    ).values('cash_session').annotate(value=Sum('amount')).values('value')
    withdrawals = movement_base.filter(
        movement_type=CashMovementType.WITHDRAWAL
    ).values('cash_session').annotate(value=Sum('amount')).values('value')
    cash = Payment.objects.filter(sale__cash_session_id=OuterRef('pk')).filter(
        Q(payment_method_code=PaymentMethodCode.CASH)
        | Q(payment_method__code=PaymentMethodCode.CASH)
    )

    def cash_sum(queryset):
        return queryset.values('sale__cash_session').annotate(
            value=Sum('amount')
        ).values('value')

    sale_cash = cash_sum(cash.filter(sale__operation_type=OperationType.SALE))
    consumption_cash = cash_sum(
        cash.filter(sale__operation_type=OperationType.CONSUMPTION)
    )
    cash_reversals = cash_sum(cash.filter(sale__status=SaleStatus.CANCELLED))
    cash_cancellations = Sale.objects.filter(
        cash_session_id=OuterRef('pk'), status=SaleStatus.CANCELLED,
    ).filter(
        Q(payments__payment_method_code=PaymentMethodCode.CASH)
        | Q(payments__payment_method__code=PaymentMethodCode.CASH)
    ).values('cash_session').annotate(
        value=Count('id', distinct=True)
    ).values('value')
    command_cash = CommandPayment.objects.filter(
        cash_session_id=OuterRef('pk'),
        payment_method__code=PaymentMethodCode.CASH,
        status=CommandPaymentStatus.APPLIED,
        reversal__isnull=True,
        command__sale__isnull=True,
    ).values('cash_session').annotate(value=Sum('amount')).values('value')
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
        sale_cash=Coalesce(Subquery(sale_cash, output_field=MONEY_FIELD), ZERO_MONEY),
        consumption_cash=Coalesce(Subquery(consumption_cash, output_field=MONEY_FIELD), ZERO_MONEY),
        cash_reversals=Coalesce(Subquery(cash_reversals, output_field=MONEY_FIELD), ZERO_MONEY),
        command_cash=Coalesce(Subquery(command_cash, output_field=MONEY_FIELD), ZERO_MONEY),
        cash_cancellations=Coalesce(
            Subquery(cash_cancellations, output_field=IntegerField()), 0,
        ),
    ).annotate(
        cash_payments=ExpressionWrapper(
            F('sale_cash') + F('consumption_cash') - F('cash_reversals') + F('command_cash'),
            output_field=MONEY_FIELD,
        ),
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
    ).select_related(
        'stock__product__category', 'stock__product__fraction_config', 'user', 'sale'
    )
    mappings = {
        'product': 'stock__product_id',
        'movement_type': 'movement_type',
        'user': 'user_id',
    }
    for parameter, lookup in mappings.items():
        if filters.get(parameter) is not None:
            queryset = queryset.filter(**{lookup: filters[parameter]})
    if filters.get('category') is not None:
        queryset = queryset.filter(
            stock__product__branch_configs__branch=branch,
            stock__product__branch_configs__category_id=filters['category'],
        )
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
    ).select_related(
        'stock__product__category', 'stock__product__fraction_config', 'user', 'sale',
        'original_movement__stock__product',
    ).prefetch_related('sale__items')
    if filters.get('product') is not None:
        rows = rows.filter(stock__product_id=filters['product'])
    if filters.get('category') is not None:
        rows = rows.filter(
            stock__product__branch_configs__branch=branch,
            stock__product__branch_configs__category_id=filters['category'],
        )
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

    def historical_unit_cost(movement):
        if movement.unit_cost_snapshot is not None:
            return movement.unit_cost_snapshot
        if movement.original_movement_id:
            return historical_unit_cost(movement.original_movement)
        if movement.sale_id:
            for sale_item in movement.sale.items.all():
                if sale_item.product_id == movement.stock.product_id:
                    return sale_item.unit_cost
                for component in sale_item.component_cost_snapshot or []:
                    if int(component.get('product', 0)) == movement.stock.product_id:
                        try:
                            return Decimal(component['unit_cost'])
                        except (KeyError, TypeError, ValueError):
                            break
        # Legacy manual movements predate immutable movement cost snapshots.
        return movement.stock.product.cost

    def add_quantity(entry, field, value):
        entry[field] = exact_sum((entry[field], value))

    for movement in rows:
        product = movement.stock.product
        key = product.pk
        entry = summary.setdefault(key, {
            'product': product,
            'gross_quantity': Decimal('0.000'),
            'returned_quantity': Decimal('0.000'),
            'net_quantity': Decimal('0.000'),
            'legacy_gross_equivalent_quantity': Decimal('0'),
            'legacy_returned_equivalent_quantity': Decimal('0'),
            'legacy_net_equivalent_quantity': Decimal('0'),
            'exact_gross_equivalent_quantity': Decimal('0'),
            'exact_returned_equivalent_quantity': Decimal('0'),
            'exact_net_equivalent_quantity': Decimal('0'),
            'estimated_cost': Decimal('0.00'),
            'movement_count': 0,
            'gross_content': Decimal('0.000000000'),
            'returned_content': Decimal('0.000000000'),
            'net_content': Decimal('0.000000000'),
            'package_content': None,
            'content_unit': None,
        })
        quantity = abs(movement.equivalent_quantity())
        content = abs(movement.content_quantity) if movement.content_quantity is not None else None
        if content is not None:
            config = product.fraction_config
            entry['package_content'] = config.package_content
            entry['content_unit'] = config.content_unit
        if movement.equivalent_quantity() < 0:
            add_quantity(entry, 'gross_quantity', quantity)
            if content is not None:
                entry['gross_content'] += content
                add_quantity(entry, 'exact_gross_equivalent_quantity', quantity)
            else:
                add_quantity(entry, 'legacy_gross_equivalent_quantity', quantity)
            entry['estimated_cost'] += exact_multiply_quantized(
                quantity, historical_unit_cost(movement), Decimal('0.01')
            )
        else:
            add_quantity(entry, 'returned_quantity', quantity)
            if content is not None:
                entry['returned_content'] += content
                add_quantity(entry, 'exact_returned_equivalent_quantity', quantity)
            else:
                add_quantity(entry, 'legacy_returned_equivalent_quantity', quantity)
            entry['estimated_cost'] -= exact_multiply_quantized(
                quantity, historical_unit_cost(movement), Decimal('0.01')
            )
        entry['movement_count'] += 1
    for entry in summary.values():
        entry['net_quantity'] = entry['gross_quantity'] - entry['returned_quantity']
        entry['legacy_net_equivalent_quantity'] = (
            entry['legacy_gross_equivalent_quantity']
            - entry['legacy_returned_equivalent_quantity']
        )
        entry['exact_net_equivalent_quantity'] = (
            entry['exact_gross_equivalent_quantity']
            - entry['exact_returned_equivalent_quantity']
        )
        entry['net_content'] = entry['gross_content'] - entry['returned_content']
    summary_rows = sorted(
        summary.values(), key=lambda item: (-item['net_quantity'], item['product'].name)
    )
    return rows.order_by('-created_at', '-id'), summary_rows


def inventory_kpis(branch, *, include_value=False, category=None):
    stocks = Stock.objects.select_related(
        'product', 'product__fraction_config'
    ).filter(
        branch=branch, product__inventory_behavior=InventoryBehavior.DIRECT,
    )
    if category:
        stocks = stocks.filter(
            product__branch_configs__branch=branch,
            product__branch_configs__category_id=category,
        )
    stocks = list(stocks)
    quantities = [stock.equivalent_quantity() for stock in stocks]
    result = {
        'zero_count': sum(quantity == 0 for quantity in quantities),
        'negative_count': sum(quantity < 0 for quantity in quantities),
        'below_minimum_count': sum(
            quantity > 0 and quantity < stock.minimum_quantity
            for stock, quantity in zip(stocks, quantities)
        ),
        'physical_products': len(stocks),
    }
    if include_value:
        result['inventory_value'] = exact_sum(
            exact_multiply(
                max(quantity, Decimal('0')),
                stock.average_unit_cost
                if stock.average_unit_cost is not None else stock.product.cost,
            )
            for stock, quantity in zip(stocks, quantities)
        ).quantize(CENT, rounding=ROUND_HALF_UP)
    return result
