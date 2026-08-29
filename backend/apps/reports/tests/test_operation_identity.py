from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.reports.serializers import ReportSaleSerializer


class ReportOperationIdentityTests(SimpleTestCase):
    def test_same_numeric_id_from_distinct_operation_types_has_distinct_key(self):
        serializer = ReportSaleSerializer()
        sale = SimpleNamespace(pk=10, operation_type='sale')
        consumption = SimpleNamespace(pk=10, operation_type='consumption')

        self.assertEqual(serializer.get_operation_key(sale), 'sale:10:record')
        self.assertEqual(serializer.get_operation_key(consumption), 'consumption:10:record')
        self.assertNotEqual(
            serializer.get_operation_key(sale), serializer.get_operation_key(consumption)
        )
