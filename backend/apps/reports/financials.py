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
            or item.product.category_id == filters['category']
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
        service_fees = allocate_money(
            sale.service_fee_amount, [(item.pk, revenues[item.pk]) for item in items]
        )
        commissions = allocate_money(
            sale.commission_amount, [(item.pk, revenues[item.pk]) for item in items]
        )
        return [
            {
                'item': item,
                'gross': money(item.subtotal),
                'promotion_discount': money(item.promotion_benefit),
                'item_discount': money(item.manual_discount),
                'account_discount': account_discounts[item.pk],
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
                'effective_revenue', 'service_fee', 'commission', 'historical_cost',
            )
        }
        values['manual_discount'] = money(
            values['item_discount'] + values['account_discount']
        )
        values['total_discount'] = money(
            values['promotion_discount'] + values['manual_discount']
        )
        values['customer_total'] = money(
            values['effective_revenue'] + values['service_fee']
        )
        values['discount_reconstruction_delta'] = money(
            values['gross'] - values['promotion_discount'] - values['item_discount']
            - values['account_discount'] - values['effective_revenue']
        )
        values['received_reconstruction_delta'] = money(
            values['effective_revenue'] + values['service_fee'] - values['customer_total']
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
        weights = [
            (row['item'].pk, row['effective_revenue'] + row['service_fee'])
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
                'effective_revenue', 'service_fee', 'commission',
                'historical_sales_cogs', 'discount_reconstruction_delta',
                'received_reconstruction_delta',
            )
        }
        totals.update(count=0, discounted_count=0, manual_discount_count=0)
        received = ZERO
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
                'effective_revenue', 'service_fee', 'commission',
                'discount_reconstruction_delta', 'received_reconstruction_delta',
            ):
                totals[key] = money(totals[key] + values[key])
            totals['historical_sales_cogs'] = money(
                totals['historical_sales_cogs'] + values['historical_cost']
            )
            received = money(received + sum(
                (row['amount'] for row in self.payment_rows(sale)), ZERO
            ))
            if sale.commission_amount > ZERO:
                commission_sale_count += 1
                commission_attendants.add(sale.seller_user_id)
        totals['revenue'] = totals['effective_revenue']
        totals['total_received_sales'] = received
        totals['payment_reconciliation_delta'] = money(received - totals['customer_total'])
        totals['average'] = money(
            totals['effective_revenue'] / totals['count'] if totals['count'] else ZERO
        )
        totals['ticket_average_received'] = money(
            received / totals['count'] if totals['count'] else ZERO
        )
        totals['commission_sale_count'] = commission_sale_count
        totals['commission_attendant_count'] = len(commission_attendants)
        return totals

    def cancellations(self, *, operation_type=OperationType.SALE):
        totals = {
            'count': 0,
            'reversed_effective_revenue': ZERO,
            'reversed_service_fee': ZERO,
            'reversed_customer_total': ZERO,
            'reversed_total_received': ZERO,
        }
        for sale in self._sales(status=SaleStatus.CANCELLED, operation_type=operation_type):
            if operation_type == OperationType.SALE:
                values = self.sale_values(sale)
                if not values['has_items']:
                    continue
                effective = values['effective_revenue']
                fee = values['service_fee']
                semantic_total = values['customer_total']
            else:
                values = self.consumption_values(sale)
                if not values:
                    continue
                effective = ZERO
                fee = ZERO
                semantic_total = values['charged']
            reversed_received = money(sum(
                (row['amount'] for row in self.payment_rows(sale)), ZERO
            ))
            totals['count'] += 1
            totals['reversed_effective_revenue'] = money(
                totals['reversed_effective_revenue'] + effective
            )
            totals['reversed_service_fee'] = money(totals['reversed_service_fee'] + fee)
            totals['reversed_customer_total'] = money(
                totals['reversed_customer_total'] + semantic_total
            )
            totals['reversed_total_received'] = money(
                totals['reversed_total_received'] + reversed_received
            )
        totals['value'] = totals['reversed_total_received']
        totals['reconciliation_delta'] = money(
            totals['reversed_total_received'] - totals['reversed_customer_total']
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
            'benefit': money(reference - charged_total),
            'historical_cost': historical_cost,
            'quantity': sum((item.quantity for item in matching), Decimal('0.000')),
        }

    def consumption(self):
        totals = {
            'count': 0, 'reference': ZERO, 'charged': ZERO, 'benefit': ZERO,
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
        totals['payments'] = [
            {'code': code, 'name': value['name'], 'amount': value['amount']}
            for code, value in sorted(
                payments.items(), key=lambda row: (-row[1]['amount'], row[1]['name'])
            )
        ]
        totals['payment_reconciliation_delta'] = money(
            sum((row['amount'] for row in totals['payments']), ZERO) - totals['charged']
        )
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
            methods.append({
                'code': code,
                'name': values['name'],
                **values,
                'net_received': money(values['gross_received'] - values['reversals']),
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
        effective_revenue = money(gross_sales_effective - reversed_effective)
        service_fee = money(gross_sales_fee - reversed_fee)
        charged_consumption = money(gross_consumption - reversed_consumption)
        semantic_received = money(effective_revenue + service_fee + charged_consumption)
        return {
            'effective_revenue': effective_revenue,
            'sales_count': sales_count,
            'consumption_count': consumption_count,
            'service_fee': service_fee,
            'fee_contained': service_fee,
            'sales_received': money(commercial_payments - commercial_reversals),
            'commercial_payments': commercial_payments,
            'consumption_charged': charged_consumption,
            'charged_consumption_payments': consumption_payments,
            'consumption_received': money(consumption_payments - consumption_reversals),
            'gross_received': money(commercial_payments + consumption_payments),
            'reversals': reversals,
            'total_operational_received': total_operational_received,
            'semantic_operational_received': semantic_received,
            'reconciliation_delta': money(total_operational_received - semantic_received),
            'payment_methods': methods,
        }

    def operational_statement(self, *, operating_expenses=ZERO, fixed_cost=ZERO):
        commercial = self.commercial()
        consumption = self.consumption()
        operating_expenses = money(operating_expenses)
        fixed_cost = money(fixed_cost)
        operational_received = money(
            commercial['effective_revenue'] + commercial['service_fee']
            + consumption['charged']
        )
        estimated_result = money(
            operational_received - commercial['historical_sales_cogs']
            - consumption['historical_consumption_cogs'] - commercial['commission']
            - operating_expenses - fixed_cost
        )
        margin = money(
            estimated_result * Decimal('100') / operational_received
            if operational_received else ZERO
        )
        return {
            **commercial,
            'charged_consumption': consumption['charged'],
            'historical_consumption_cogs': consumption['historical_consumption_cogs'],
            'operational_received': operational_received,
            'operating_expenses': operating_expenses,
            'fixed_cost': fixed_cost,
            'estimated_result': estimated_result,
            'result': estimated_result,
            'margin': margin,
            'operational_reconciliation_delta': money(
                operational_received - commercial['effective_revenue']
                - commercial['service_fee'] - consumption['charged']
            ),
        }
