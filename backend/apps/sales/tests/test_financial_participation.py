from decimal import Decimal

from django.test import SimpleTestCase

from apps.sales.services import _eligible_financial_bases


class FinancialParticipationTests(SimpleTestCase):
    def test_service_fee_and_commission_bases_are_independent(self):
        items = [
            {
                'net_subtotal': Decimal('100.00'),
                'participates_in_service_fee': True,
                'participates_in_commission': True,
            },
            {
                'net_subtotal': Decimal('100.00'),
                'participates_in_service_fee': True,
                'participates_in_commission': False,
            },
            {
                'net_subtotal': Decimal('100.00'),
                'participates_in_service_fee': False,
                'participates_in_commission': True,
            },
            {
                'net_subtotal': Decimal('100.00'),
                'participates_in_service_fee': False,
                'participates_in_commission': False,
            },
        ]

        service_base, commission_base = _eligible_financial_bases(
            items, Decimal('0.00'),
        )

        self.assertEqual(service_base, Decimal('200.00'))
        self.assertEqual(commission_base, Decimal('200.00'))
