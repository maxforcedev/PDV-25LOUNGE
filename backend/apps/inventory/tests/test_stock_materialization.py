from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.db import close_old_connections
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase

from apps.inventory.materialization import materialize_stock
from apps.inventory.models import Stock

from .test_v2_5_inventory import fixture


class StockMaterializationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.company, self.branch, _destination, self.product, _user = fixture('MAT')
        Stock.objects.filter(product=self.product, branch=self.branch).delete()

    def _materialize(self):
        close_old_connections()
        try:
            return materialize_stock(product=self.product, branch=self.branch).pk
        finally:
            close_old_connections()

    def test_concurrent_materialization_creates_one_zero_stock(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            stock_ids = list(pool.map(lambda _: self._materialize(), range(2)))

        self.assertEqual(stock_ids[0], stock_ids[1])
        stocks = Stock.objects.filter(product=self.product, branch=self.branch)
        self.assertEqual(stocks.count(), 1)
        self.assertEqual(stocks.get().current_quantity, Decimal('0'))

    def test_materialization_rejects_branch_from_another_company(self):
        other_company, other_branch, _destination, _product, _user = fixture('MATX')

        with self.assertRaises(ValidationError):
            materialize_stock(product=self.product, branch=other_branch)

        self.assertFalse(Stock.objects.filter(
            product=self.product, branch__company=other_company,
        ).exists())

    def test_materialization_does_not_trust_spoofed_branch_company(self):
        other_company, other_branch, _destination, _product, _user = fixture('MATY')
        other_branch.company_id = self.company.pk

        with self.assertRaises(ValidationError):
            materialize_stock(product=self.product, branch=other_branch)

        self.assertFalse(Stock.objects.filter(
            product=self.product, branch__company=other_company,
        ).exists())
