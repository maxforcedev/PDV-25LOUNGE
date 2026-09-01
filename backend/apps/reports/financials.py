from collections import defaultdict
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from apps.sales.models import OperationType, SaleStatus


CENT = Decimal('0.01')
ZERO = Decimal('0.00')


def money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def allocate_money(total, weighted_rows):
    """Allocate an amount exactly, using largest remainders and stable keys."""
    total = money(total)
    rows = [(key, max(Decimal(weight or 0), Decimal('0'))) for key, weight in weighted_rows]
    if not rows:
        return {}
    if total == ZERO:
        return {key: ZERO for key, _weight in rows}
    weight_total = sum((weight for _key, weight in rows), Decimal('0'))
    if weight_total == 0:
        result = {key: ZERO for key, _weight in rows}
        result[min(key for key, _weight in rows)] = total
        return result
    raw = {key: total * weight / weight_total for key, weight in rows}
    result = {
        key: value.quantize(CENT, rounding=ROUND_FLOOR)
        for key, value in raw.items()
    }
    residual = int((total - sum(result.values(), ZERO)) / CENT)
    order = sorted(rows, key=lambda row: (-(raw[row[0]] - result[row[0]]), row[0]))
    for key, _weight in order[:residual]:
        result[key] += CENT
    return result


def _allocate_capped(total, capacities):
    total = money(total)
    rows = [(key, money(capacity)) for key, capacity in capacities if capacity > 0]
    if total > sum((capacity for _key, capacity in rows), ZERO):
        raise ValueError('Allocation exceeds remaining capacity.')
    if total == sum((capacity for _key, capacity in rows), ZERO):
        return dict(rows)
    allocated = allocate_money(total, rows)
    return {key: min(value, dict(rows)[key]) for key, value in allocated.items()}


def allocate_payment_matrix(payments, item_weights):
    """Allocate payments across items with exact payment rows and item columns."""
    payment_rows = [(payment.pk, money(payment.amount)) for payment in payments]
    if not payment_rows:
        return {}, {key: ZERO for key, _weight in item_weights}
    total_received = sum((amount for _key, amount in payment_rows), ZERO)
    column_totals = allocate_money(total_received, item_weights)
    remaining = dict(column_totals)
    matrix = {}
    for index, (payment_id, amount) in enumerate(payment_rows):
        if index == len(payment_rows) - 1:
            row = dict(remaining)
        else:
            row = _allocate_capped(amount, sorted(remaining.items()))
            row = {key: row.get(key, ZERO) for key in remaining}
        if sum(row.values(), ZERO) != amount:
            raise ValueError('Payment allocation did not reconcile its row.')
        matrix[payment_id] = row
        remaining = {key: remaining[key] - row[key] for key in remaining}
    if any(value != ZERO for value in remaining.values()):
        raise ValueError('Payment allocation did not reconcile its columns.')
    return matrix, column_totals


def _item_matches(item, filters):
    filters = filters or {}
    return (
        (filters.get('product') is None or item.product_id == filters['product'])
        and (
            filters.get('category') is None
            or item.category_id_snapshot == filters['category']
        )
    )


class FinancialAggregator:
    """Central financial semantics over an already-scoped, prefetched sale graph."""

    def __init__(self, sales, filters=None):
        self.sales = list(sales)
        self.filters = {
            key: value for key, value in (filters or {}).items()
            if key in ('product', 'category') and value is not None
        }

    def with_sales(self, sales):
        return FinancialAggregator(sales, self.filters)

    def _sales(self, *, status=None, operation_type=None):
        return [
            sale for sale in self.sales
            if (status is None or sale.status == status)
            and (operation_type is None or sale.operation_type == operation_type)
        ]

    def item_rows(self, sale, *, filters=None):
        filters = self.filters if filters is None else filters
        items = sorted(sale.items.all(), key=lambda item: item.pk)
        account_discounts = allocate_money(
            sale.discount, [(item.pk, item.net_subtotal) for item in items]
        )
        revenues = {
            item.pk: money(item.net_subtotal - account_discounts[item.pk])
            for item in items
        }
        service_fees = {item.pk: ZERO for item in items}
        service_fees.update(allocate_money(
            sale.service_fee_amount,
            [
                (item.pk, revenues[item.pk]) for item in items
                if item.participates_in_service_fee
            ],
        ))
        commissions = {item.pk: ZERO for item in items}
        commissions.update(allocate_money(
            sale.commission_amount,
            [
                (item.pk, revenues[item.pk]) for item in items
                if item.participates_in_commission
            ],
        ))
        return [
            {
                'item': item,
                'gross': money(item.subtotal),
                'promotion_discount': money(item.promotion_benefit),
                'item_discount': money(item.manual_discount),
                'account_discount': account_discounts[item.pk],
                'sales_revenue': revenues[item.pk],
                # Compatibility alias. New consumers must use sales_revenue.
                'effective_revenue': revenues[item.pk],
                'service_fee': service_fees[item.pk],
                'commission': commissions[item.pk],
                'historical_cost': money(item.unit_cost * item.quantity),
            }
            for item in items if _item_matches(item, filters)
        ]

    def sale_values(self, sale):
        rows = self.item_rows(sale)
        values = {
            key: money(sum((row[key] for row in rows), ZERO))
            for key in (
                'gross', 'promotion_discount', 'item_discount', 'account_discount',
                'sales_revenue', 'service_fee', 'commission', 'historical_cost',
            )
        }
        values['manual_discount'] = money(
            values['item_discount'] + values['account_discount']
        )
        values['total_discount'] = money(
            values['promotion_discount'] + values['manual_discount']
        )
        values['consumption_charged'] = ZERO
        values['effective_revenue'] = values['sales_revenue']
        values['total_received'] = money(values['effective_revenue'] + values['service_fee'])
        values['customer_total'] = values['total_received']
        values['discount_reconstruction_delta'] = money(
            values['gross'] - values['promotion_discount'] - values['item_discount']
            - values['account_discount'] - values['sales_revenue']
        )
        values['received_reconstruction_delta'] = money(
            values['effective_revenue'] + values['service_fee'] - values['total_received']
        )
        values['has_items'] = bool(rows)
        return values

    def payment_rows(self, sale):
        all_rows = self.item_rows(sale, filters={})
        matching_ids = {
            row['item'].pk for row in all_rows if _item_matches(row['item'], self.filters)
        }
        if not matching_ids:
            return []
        if sale.operation_type == OperationType.CONSUMPTION:
            charged = allocate_money(
                sale.total, [(row['item'].pk, row['item'].subtotal) for row in all_rows]
            )
            weights = [(row['item'].pk, charged[row['item'].pk]) for row in all_rows]
        else:
            weights = [
                (row['item'].pk, row['sales_revenue'] + row['service_fee'])
                for row in all_rows
            ]
        payments = list(sale.payments.all())
        matrix, _columns = allocate_payment_matrix(payments, weights)
        return [
            {
                'payment_method_name': payment.payment_method_name,
                'payment_method_code': payment.payment_method_code,
                'payment_method_id': payment.payment_method_id,
                'amount': money(sum(
                    (matrix[payment.pk][item_id] for item_id in matching_ids), ZERO
                )),
            }
            for payment in payments
        ]

    def commercial(self):
        totals = {
            key: ZERO for key in (
                'customer_total', 'gross', 'account_discount', 'item_discount',
                'manual_discount', 'promotion_discount', 'total_discount',
                'sales_revenue', 'consumption_charged', 'effective_revenue',
                'service_fee', 'total_received', 'commission',
                'historical_sales_cogs', 'discount_reconstruction_delta',
                'received_reconstruction_delta',
            )
        }
        totals.update(count=0, discounted_count=0, manual_discount_count=0)
        payment_total = ZERO
        commission_sale_count = 0
        commission_attendants = set()
        for sale in self._sales(
            status=SaleStatus.FINALIZED, operation_type=OperationType.SALE
        ):
            values = self.sale_values(sale)
            if not values['has_items']:
                continue
            totals['count'] += 1
            totals['discounted_count'] += int(values['total_discount'] > ZERO)
            totals['manual_discount_count'] += int(values['manual_discount'] > ZERO)
            for key in (
                'customer_total', 'gross', 'account_discount', 'item_discount',
                'manual_discount', 'promotion_discount', 'total_discount',
                'sales_revenue', 'consumption_charged', 'effective_revenue',
                'service_fee', 'total_received', 'commission',
                'discount_reconstruction_delta', 'received_reconstruction_delta',
            ):
                totals[key] = money(totals[key] + values[key])
            totals['historical_sales_cogs'] = money(
                totals['historical_sales_cogs'] + values['historical_cost']
            )
            payment_total = money(payment_total + sum(
                (row['amount'] for row in self.payment_rows(sale)), ZERO
            ))
            if values['commission'] > ZERO:
                commission_sale_count += 1
                commission_attendants.add(sale.seller_user_id)
        totals['revenue'] = totals['sales_revenue']
        totals['payment_total'] = payment_total
        totals['reconciliation_delta'] = money(payment_total - totals['total_received'])
        totals['payment_reconciliation_delta'] = totals['reconciliation_delta']
        # Compatibility aliases for clients predating the canonical contract.
        totals['total_received_sales'] = payment_total
        totals['customer_total'] = totals['total_received']
        totals['average'] = money(
            totals['sales_revenue'] / totals['count'] if totals['count'] else ZERO
        )
        totals['ticket_average_received'] = money(
            payment_total / totals['count'] if totals['count'] else ZERO
        )
        totals['commission_sale_count'] = commission_sale_count
        totals['commission_attendant_count'] = len(commission_attendants)
        return totals

    def commercial_events(self, reversal_sales=()):
        fields = (
            'gross', 'account_discount', 'item_discount', 'manual_discount',
            'promotion_discount', 'total_discount', 'sales_revenue',
            'consumption_charged', 'effective_revenue', 'service_fee',
            'total_received', 'commission', 'historical_sales_cogs',
            'discount_reconstruction_delta', 'received_reconstruction_delta',
        )
        totals = {key: ZERO for key in fields}
        totals.update(
            count=0, inflow_count=0, reversal_count=0,
            discounted_count=0, manual_discount_count=0,
            commission_sale_count=0,
            historical_sales_cogs_inflows=ZERO,
            historical_sales_cogs_reversals=ZERO,
            commission_inflows=ZERO, commission_reversals=ZERO,
        )
        payment_total = ZERO
        attendant_commissions = defaultdict(lambda: ZERO)
        for aggregator, sign in (
            (self, 1), (FinancialAggregator(reversal_sales, self.filters), -1),
        ):
            for sale in aggregator._sales(operation_type=OperationType.SALE):
                values = aggregator.sale_values(sale)
                if not values['has_items']:
                    continue
                totals['count'] += sign
                totals['inflow_count' if sign > 0 else 'reversal_count'] += 1
                totals['discounted_count'] += sign * int(values['total_discount'] > ZERO)
                totals['manual_discount_count'] += sign * int(
                    values['manual_discount'] > ZERO
                )
                for key in fields:
                    value_key = 'historical_cost' if key == 'historical_sales_cogs' else key
                    totals[key] = money(totals[key] + sign * values[value_key])
                direction = 'inflows' if sign > 0 else 'reversals'
                totals[f'historical_sales_cogs_{direction}'] = money(
                    totals[f'historical_sales_cogs_{direction}']
                    + values['historical_cost']
                )
                totals[f'commission_{direction}'] = money(
                    totals[f'commission_{direction}'] + values['commission']
                )
                sale_payment_total = sum(
                    (row['amount'] for row in aggregator.payment_rows(sale)), ZERO
                )
                payment_total = money(payment_total + sign * sale_payment_total)
                if values['commission'] > ZERO:
                    totals['commission_sale_count'] += sign
                attendant_commissions[sale.seller_user_id] = money(
                    attendant_commissions[sale.seller_user_id]
                    + sign * values['commission']
                )
        totals['payment_total'] = payment_total
        totals['reconciliation_delta'] = money(payment_total - totals['total_received'])
        totals['average'] = money(
            totals['sales_revenue'] / totals['count'] if totals['count'] > 0 else ZERO
        )
        totals['commission_attendant_count'] = sum(
            1 for user_id, value in attendant_commissions.items()
            if user_id is not None and value != ZERO
        )
        totals['revenue'] = totals['sales_revenue']
        totals['customer_total'] = totals['total_received']
        totals['total_received_sales'] = payment_total
        totals['payment_reconciliation_delta'] = totals['reconciliation_delta']
        totals['ticket_average_received'] = money(
            payment_total / totals['count'] if totals['count'] > 0 else ZERO
        )
        totals['event_accounting'] = 'created_inflows_plus_cancellation_reversals'
        return totals

    def cancellations(self, *, operation_type=OperationType.SALE):
        totals = {
            'count': 0,
            'reversed_sales_revenue': ZERO,
            'reversed_consumption_charged': ZERO,
            'reversed_effective_revenue': ZERO,
            'reversed_service_fee': ZERO,
            'reversed_customer_total': ZERO,
            'reversed_total_received': ZERO,
            'reversed_payment_total': ZERO,
        }
        for sale in self._sales(status=SaleStatus.CANCELLED, operation_type=operation_type):
            if operation_type == OperationType.SALE:
                values = self.sale_values(sale)
                if not values['has_items']:
                    continue
                sales_revenue = values['sales_revenue']
                consumption_charged = ZERO
                effective = values['effective_revenue']
                fee = values['service_fee']
                semantic_total = values['total_received']
            else:
                values = self.consumption_values(sale)
                if not values:
                    continue
                sales_revenue = ZERO
                consumption_charged = values['consumption_charged']
                effective = consumption_charged
                fee = ZERO
                semantic_total = values['total_received']
            reversed_received = money(sum(
                (row['amount'] for row in self.payment_rows(sale)), ZERO
            ))
            totals['count'] += 1
            totals['reversed_sales_revenue'] = money(
                totals['reversed_sales_revenue'] + sales_revenue
            )
            totals['reversed_consumption_charged'] = money(
                totals['reversed_consumption_charged'] + consumption_charged
            )
            totals['reversed_effective_revenue'] = money(
                totals['reversed_effective_revenue'] + effective
            )
            totals['reversed_service_fee'] = money(totals['reversed_service_fee'] + fee)
            totals['reversed_customer_total'] = money(
                totals['reversed_customer_total'] + semantic_total
            )
            totals['reversed_total_received'] = money(
                totals['reversed_total_received'] + semantic_total
            )
            totals['reversed_payment_total'] = money(
                totals['reversed_payment_total'] + reversed_received
            )
        totals['value'] = totals['reversed_payment_total']
        totals['reconciliation_delta'] = money(
            totals['reversed_payment_total'] - totals['reversed_total_received']
        )
        return totals

    def consumption_values(self, sale):
        items = sorted(sale.items.all(), key=lambda item: item.pk)
        matching = [item for item in items if _item_matches(item, self.filters)]
        if not matching:
            return None
        charged = allocate_money(sale.total, [(item.pk, item.subtotal) for item in items])
        reference = money(sum((item.subtotal for item in matching), ZERO))
        charged_total = money(sum((charged[item.pk] for item in matching), ZERO))
        historical_cost = money(sum(
            (money(item.unit_cost * item.quantity) for item in matching), ZERO
        ))
        return {
            'reference': reference,
            'charged': charged_total,
            'sales_revenue': ZERO,
            'consumption_charged': charged_total,
            'effective_revenue': charged_total,
            'service_fee': ZERO,
            'total_received': charged_total,
            'benefit': money(reference - charged_total),
            'historical_cost': historical_cost,
            'quantity': sum((item.quantity for item in matching), Decimal('0.000')),
        }

    def consumption(self):
        totals = {
            'count': 0, 'reference': ZERO, 'charged': ZERO, 'benefit': ZERO,
            'sales_revenue': ZERO, 'consumption_charged': ZERO,
            'effective_revenue': ZERO, 'service_fee': ZERO, 'total_received': ZERO,
            'historical_consumption_cogs': ZERO, 'quantity': Decimal('0.000'),
        }
        payments = defaultdict(lambda: {'amount': ZERO, 'name': ''})
        for sale in self._sales(
            status=SaleStatus.FINALIZED, operation_type=OperationType.CONSUMPTION
        ):
            values = self.consumption_values(sale)
            if not values:
                continue
            totals['count'] += 1
            for key in ('reference', 'charged', 'benefit'):
                totals[key] = money(totals[key] + values[key])
            totals['historical_consumption_cogs'] = money(
                totals['historical_consumption_cogs'] + values['historical_cost']
            )
            totals['quantity'] += values['quantity']
            for payment in self.payment_rows(sale):
                key = payment['payment_method_code']
                payments[key]['name'] = payment['payment_method_name']
                payments[key]['amount'] = money(payments[key]['amount'] + payment['amount'])
        totals['subsidy'] = totals['benefit']
        totals['consumption_charged'] = totals['charged']
        totals['effective_revenue'] = totals['consumption_charged']
        totals['total_received'] = totals['effective_revenue']
        totals['payments'] = [
            {'code': code, 'name': value['name'], 'amount': value['amount']}
            for code, value in sorted(
                payments.items(), key=lambda row: (-row[1]['amount'], row[1]['name'])
            )
        ]
        totals['payment_total'] = money(sum(
            (row['amount'] for row in totals['payments']), ZERO
        ))
        totals['reconciliation_delta'] = money(
            totals['payment_total'] - totals['total_received']
        )
        totals['payment_reconciliation_delta'] = totals['reconciliation_delta']
        totals['event_accounting'] = 'created_inflows_plus_cancellation_reversals'
        return totals

    def consumption_events(self, reversal_sales=()):
        totals = {
            'count': 0, 'inflow_count': 0, 'reversal_count': 0,
            'reference': ZERO, 'charged': ZERO, 'benefit': ZERO,
            'sales_revenue': ZERO, 'consumption_charged': ZERO,
            'effective_revenue': ZERO, 'service_fee': ZERO,
            'total_received': ZERO, 'historical_consumption_cogs': ZERO,
            'quantity': Decimal('0.000'),
            'historical_consumption_cogs_inflows': ZERO,
            'historical_consumption_cogs_reversals': ZERO,
        }
        payments = defaultdict(lambda: {'amount': ZERO, 'name': ''})
        for aggregator, sign in (
            (self, 1), (FinancialAggregator(reversal_sales, self.filters), -1),
        ):
            for sale in aggregator._sales(operation_type=OperationType.CONSUMPTION):
                values = aggregator.consumption_values(sale)
                if not values:
                    continue
                totals['count'] += sign
                totals['inflow_count' if sign > 0 else 'reversal_count'] += 1
                for key in ('reference', 'charged', 'benefit'):
                    totals[key] = money(totals[key] + sign * values[key])
                totals['historical_consumption_cogs'] = money(
                    totals['historical_consumption_cogs']
                    + sign * values['historical_cost']
                )
                direction = 'inflows' if sign > 0 else 'reversals'
                totals[f'historical_consumption_cogs_{direction}'] = money(
                    totals[f'historical_consumption_cogs_{direction}']
                    + values['historical_cost']
                )
                totals['quantity'] += sign * values['quantity']
                for payment in aggregator.payment_rows(sale):
                    key = payment['payment_method_code']
                    payments[key]['name'] = payment['payment_method_name']
                    payments[key]['amount'] = money(
                        payments[key]['amount'] + sign * payment['amount']
                    )
        totals['subsidy'] = totals['benefit']
        totals['consumption_charged'] = totals['charged']
        totals['effective_revenue'] = totals['consumption_charged']
        totals['total_received'] = totals['effective_revenue']
        totals['payments'] = [
            {'code': code, 'name': value['name'], 'amount': value['amount']}
            for code, value in sorted(
                payments.items(), key=lambda row: (-row[1]['amount'], row[1]['name'])
            )
            if value['amount'] != ZERO
        ]
        totals['payment_total'] = money(sum(
            (row['amount'] for row in totals['payments']), ZERO
        ))
        totals['reconciliation_delta'] = money(
            totals['payment_total'] - totals['total_received']
        )
        totals['payment_reconciliation_delta'] = totals['reconciliation_delta']
        totals['event_accounting'] = 'created_inflows_plus_cancellation_reversals'
        return totals

    def payment_totals(self, *, operation_type=OperationType.SALE):
        grouped = defaultdict(lambda: {'amount': ZERO, 'name': ''})
        for sale in self._sales(status=SaleStatus.FINALIZED, operation_type=operation_type):
            for payment in self.payment_rows(sale):
                key = payment['payment_method_code']
                grouped[key]['name'] = payment['payment_method_name']
                grouped[key]['amount'] = money(grouped[key]['amount'] + payment['amount'])
        return [
            {
                'payment_method_code': code,
                'payment_method_name': values['name'],
                'amount': values['amount'],
            }
            for code, values in sorted(
                grouped.items(), key=lambda row: (-row[1]['amount'], row[1]['name'])
            )
        ]

    def receipts(self, reversal_sales=()):
        """Summarize inflow events and cancellation reversal events by method."""
        by_method = defaultdict(lambda: {
            'name': '', 'commercial_received': ZERO,
            'consumption_received': ZERO, 'gross_received': ZERO, 'reversals': ZERO,
        })
        gross_sales_effective = ZERO
        gross_sales_fee = ZERO
        gross_consumption = ZERO
        sales_count = 0
        consumption_count = 0
        for sale in self.sales:
            values = self.sale_values(sale) if sale.operation_type == OperationType.SALE else None
            consumption = (
                self.consumption_values(sale)
                if sale.operation_type == OperationType.CONSUMPTION else None
            )
            if values and values['has_items']:
                sales_count += 1
                gross_sales_effective = money(gross_sales_effective + values['effective_revenue'])
                gross_sales_fee = money(gross_sales_fee + values['service_fee'])
            if consumption:
                consumption_count += 1
                gross_consumption = money(gross_consumption + consumption['charged'])
            for payment in self.payment_rows(sale):
                row = by_method[payment['payment_method_code']]
                row['name'] = payment['payment_method_name']
                row['gross_received'] = money(row['gross_received'] + payment['amount'])
                field = (
                    'commercial_received'
                    if sale.operation_type == OperationType.SALE
                    else 'consumption_received'
                )
                row[field] = money(row[field] + payment['amount'])

        reversal_aggregator = FinancialAggregator(reversal_sales, self.filters)
        reversed_effective = ZERO
        reversed_fee = ZERO
        reversed_consumption = ZERO
        commercial_reversals = ZERO
        consumption_reversals = ZERO
        for sale in reversal_aggregator.sales:
            if sale.operation_type == OperationType.SALE:
                values = reversal_aggregator.sale_values(sale)
                if values['has_items']:
                    reversed_effective = money(reversed_effective + values['effective_revenue'])
                    reversed_fee = money(reversed_fee + values['service_fee'])
            else:
                values = reversal_aggregator.consumption_values(sale)
                if values:
                    reversed_consumption = money(reversed_consumption + values['charged'])
            for payment in reversal_aggregator.payment_rows(sale):
                row = by_method[payment['payment_method_code']]
                row['name'] = payment['payment_method_name']
                row['reversals'] = money(row['reversals'] + payment['amount'])
                if sale.operation_type == OperationType.SALE:
                    commercial_reversals = money(commercial_reversals + payment['amount'])
                else:
                    consumption_reversals = money(consumption_reversals + payment['amount'])

        methods = []
        for code, values in by_method.items():
            payment_total = money(values['gross_received'] - values['reversals'])
            methods.append({
                'code': code,
                'name': values['name'],
                **values,
                'sales_payment_total': values['commercial_received'],
                'consumption_payment_total': values['consumption_received'],
                'payment_total_before_reversals': values['gross_received'],
                'reversal_payment_total': values['reversals'],
                'payment_total': payment_total,
                'net_received': payment_total,
            })
        methods.sort(key=lambda row: (-row['net_received'], row['name']))
        commercial_payments = money(sum(
            (row['commercial_received'] for row in methods), ZERO
        ))
        consumption_payments = money(sum(
            (row['consumption_received'] for row in methods), ZERO
        ))
        reversals = money(sum((row['reversals'] for row in methods), ZERO))
        total_operational_received = money(
            commercial_payments + consumption_payments - reversals
        )
        sales_revenue = money(gross_sales_effective - reversed_effective)
        service_fee = money(gross_sales_fee - reversed_fee)
        consumption_charged = money(gross_consumption - reversed_consumption)
        effective_revenue = money(sales_revenue + consumption_charged)
        total_received = money(effective_revenue + service_fee)
        return {
            'sales_revenue_before_reversals': gross_sales_effective,
            'effective_revenue_before_reversals': money(
                gross_sales_effective + gross_consumption
            ),
            'service_fee_before_reversals': gross_sales_fee,
            'sales_received_before_reversals': commercial_payments,
            'consumption_charged_before_reversals': gross_consumption,
            'consumption_received_before_reversals': consumption_payments,
            'commercial_reversals': commercial_reversals,
            'consumption_reversals': consumption_reversals,
            'reversal_payment_total': reversals,
            'sales_revenue': sales_revenue,
            'effective_revenue': effective_revenue,
            'sales_count': sales_count,
            'consumption_count': consumption_count,
            'service_fee': service_fee,
            'fee_contained': service_fee,
            'sales_received': money(commercial_payments - commercial_reversals),
            'commercial_payments': commercial_payments,
            'consumption_charged': consumption_charged,
            'charged_consumption_payments': consumption_payments,
            'consumption_received': money(consumption_payments - consumption_reversals),
            'gross_received': money(commercial_payments + consumption_payments),
            'reversals': reversals,
            'payment_total': total_operational_received,
            'total_received': total_received,
            'reconciliation_delta': money(total_operational_received - total_received),
            # Compatibility aliases.
            'total_operational_received': total_operational_received,
            'semantic_operational_received': total_received,
            'payment_methods': methods,
            'event_accounting': 'created_inflows_plus_cancellation_reversals',
        }

    def operational_statement(
        self, *, operating_expenses=ZERO, fixed_cost=ZERO, reversal_sales=None,
    ):
        if reversal_sales is None:
            commercial = self.commercial()
            consumption = self.consumption()
            event_breakdown = {}
        else:
            commercial = self.commercial_events(reversal_sales)
            consumption = self.consumption_events(reversal_sales)
            receipts = self.receipts(reversal_sales)
            event_breakdown = {
                'sales_inflow_count': commercial['inflow_count'],
                'sales_reversal_count': commercial['reversal_count'],
                'consumption_inflow_count': consumption['inflow_count'],
                'consumption_reversal_count': consumption['reversal_count'],
                'sales_revenue_inflows': receipts['sales_revenue_before_reversals'],
                'sales_revenue_reversals': money(
                    receipts['sales_revenue_before_reversals']
                    - receipts['sales_revenue']
                ),
                'consumption_charged_inflows': receipts[
                    'consumption_charged_before_reversals'
                ],
                'consumption_charged_reversals': money(
                    receipts['consumption_charged_before_reversals']
                    - receipts['consumption_charged']
                ),
                'service_fee_inflows': receipts['service_fee_before_reversals'],
                'service_fee_reversals': money(
                    receipts['service_fee_before_reversals'] - receipts['service_fee']
                ),
                'payment_total_inflows': receipts['gross_received'],
                'payment_total_reversals': receipts['reversal_payment_total'],
            }
        operating_expenses = money(operating_expenses)
        fixed_cost = money(fixed_cost)
        sales_revenue = commercial['sales_revenue']
        consumption_charged = consumption['consumption_charged']
        effective_revenue = money(sales_revenue + consumption_charged)
        total_received = money(effective_revenue + commercial['service_fee'])
        payment_total = money(commercial['payment_total'] + consumption['payment_total'])
        costs_and_expenses = money(
            commercial['historical_sales_cogs']
            + consumption['historical_consumption_cogs'] + commercial['commission']
            + operating_expenses + fixed_cost
        )
        estimated_result = money(
            total_received - costs_and_expenses
        )
        margin = (
            money(estimated_result * Decimal('100') / total_received)
            if total_received > ZERO else None
        )
        return {
            **commercial,
            'sales_revenue': sales_revenue,
            'consumption_charged': consumption_charged,
            'charged_consumption': consumption_charged,
            'effective_revenue': effective_revenue,
            'total_received': total_received,
            'payment_total': payment_total,
            'historical_consumption_cogs': consumption['historical_consumption_cogs'],
            'historical_consumption_cogs_inflows': consumption.get(
                'historical_consumption_cogs_inflows', ZERO
            ),
            'historical_consumption_cogs_reversals': consumption.get(
                'historical_consumption_cogs_reversals', ZERO
            ),
            'costs_and_expenses': costs_and_expenses,
            'operational_received': total_received,
            'operating_expenses': operating_expenses,
            'fixed_cost': fixed_cost,
            'estimated_result': estimated_result,
            'result': estimated_result,
            'margin': margin,
            'reconciliation_delta': money(payment_total - total_received),
            'operational_reconciliation_delta': money(payment_total - total_received),
            **event_breakdown,
            'event_accounting': 'created_inflows_plus_cancellation_reversals',
        }
