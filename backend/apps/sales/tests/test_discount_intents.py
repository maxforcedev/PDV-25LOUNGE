from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.sales.services import (
    _idempotency_discount, _preview_items, normalize_discount_intent, resolve_discount_intent,
)


class ManualDiscountIntentTests(SimpleTestCase):
    def test_percentage_is_resolved_by_the_canonical_financial_helper(self):
        intent, amount = resolve_discount_intent(
            {'type': 'percentage', 'value': '10.00'}, Decimal('199.95'),
            field='discount',
        )

        self.assertEqual(intent, {'type': 'percentage', 'value': Decimal('10.00')})
        self.assertEqual(amount, Decimal('20.00'))

    def test_amount_legacy_input_remains_an_amount_intent(self):
        self.assertEqual(
            normalize_discount_intent('12.50', field='discount'),
            {'type': 'amount', 'value': Decimal('12.50')},
        )

    def test_percentage_limits_and_idempotency_intent_are_distinct(self):
        with self.assertRaises(ValidationError):
            normalize_discount_intent(
                {'type': 'percentage', 'value': '100.01'}, field='discount',
            )
        self.assertNotEqual(
            _idempotency_discount({'type': 'percentage', 'value': '10.00'}),
            _idempotency_discount({'type': 'amount', 'value': '10.00'}),
        )

    def test_preview_exposes_official_totals_for_each_cart_line(self):
        item = _preview_items([{
            'client_item_id': '8f7402f0-90bb-4e13-bdc6-21d0fc49746f',
            'modifier_unit_total': Decimal('3.00'),
            'quantity': Decimal('2.000'),
            'subtotal': Decimal('34.00'),
            'promotion_benefit': Decimal('4.00'),
            'manual_discount': Decimal('2.50'),
            'net_subtotal': Decimal('27.50'),
        }])[0]

        self.assertEqual(item['modifiers_total'], Decimal('6.00'))
        self.assertEqual(item['gross_total'], Decimal('34.00'))
        self.assertEqual(item['item_discount'], Decimal('6.50'))
        self.assertEqual(item['line_total'], Decimal('27.50'))
