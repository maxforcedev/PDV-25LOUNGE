from django.test import SimpleTestCase

from apps.base.cost_visibility import redact_cost_payload


class CostVisibilityTests(SimpleTestCase):
    def test_redacts_nested_modifier_costs_without_mutating_snapshot(self):
        snapshot = [{
            'option_name': 'Coca-Cola Lata',
            'selected_quantity': '2',
            'additional_price': '8.00',
            'stock_product_cost': '3.20',
            'stock_components': [{
                'product_name': 'Xarope',
                'unit_cost_contribution': '0.40',
            }],
        }]

        visible = redact_cost_payload(snapshot, include_costs=False)

        self.assertEqual(visible, [{
            'option_name': 'Coca-Cola Lata',
            'selected_quantity': '2',
            'additional_price': '8.00',
            'stock_components': [{'product_name': 'Xarope'}],
        }])
        self.assertEqual(snapshot[0]['stock_product_cost'], '3.20')
        self.assertEqual(snapshot[0]['stock_components'][0]['unit_cost_contribution'], '0.40')

    def test_keeps_historical_snapshot_for_authorized_rendering(self):
        snapshot = {'stock_product_cost': '3.20', 'unit_cost': '3.20'}

        visible = redact_cost_payload(snapshot, include_costs=True)

        self.assertEqual(visible, snapshot)
        self.assertIsNot(visible, snapshot)
