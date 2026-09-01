from decimal import Decimal
import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.products.models import Product

from ..services import create_stock_transfer, dispatch_stock_transfer, entry
from .test_v2_5_inventory import fixture, set_stock


class MissionM3InventoryTests(TestCase):
    def setUp(self):
        self.company, self.branch, self.destination, category_product, self.user = fixture('M3')
        self.alpha = Product.objects.create(
            company=self.company,
            category=category_product.category,
            name='Alpha M3',
            internal_code='M3-ALPHA',
            sku='SKU-M3-ALPHA',
            barcode='7890000000301',
            unit='kg',
            cost=Decimal('3.00'),
            sale_price=Decimal('9.00'),
        )
        self.zulu = Product.objects.create(
            company=self.company,
            category=category_product.category,
            name='Zulu M3',
            internal_code='M3-ZULU',
            sku='SKU-M3-ZULU',
            barcode='7890000000302',
            unit='kg',
            cost=Decimal('5.00'),
            sale_price=Decimal('15.00'),
        )
        set_stock(self.branch, category_product, '2', '5')
        set_stock(self.branch, self.alpha, '10', '3')
        set_stock(self.branch, self.zulu, '1', '20')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

    def stock_url(self, ordering, page=1):
        return (
            f'/api/v1/stocks/?company={self.company.pk}&branch={self.branch.pk}'
            f'&ordering={ordering}&page_size=2&page={page}'
        )

    def test_stock_ordering_is_backend_paginated_and_stable(self):
        first = self.client.get(self.stock_url('balance'))
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(
            [item['product_name'] for item in first.data['results']],
            ['Zulu M3', 'Produto V25'],
        )
        second = self.client.get(self.stock_url('balance', page=2))
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(
            [item['product_name'] for item in second.data['results']], ['Alpha M3']
        )
        descending_balance = self.client.get(self.stock_url('-balance'))
        self.assertEqual(descending_balance.status_code, 200, descending_balance.data)
        self.assertEqual(
            [item['product_name'] for item in descending_balance.data['results']],
            ['Alpha M3', 'Produto V25'],
        )
        for field in ('product', 'category', 'average_unit_cost', 'last_unit_cost'):
            response = self.client.get(self.stock_url(field))
            self.assertEqual(response.status_code, 200, response.data)
        total_cost = self.client.get(self.stock_url('-total_cost'))
        self.assertEqual(total_cost.status_code, 200, total_cost.data)
        self.assertEqual(
            [item['product_name'] for item in total_cost.data['results']],
            ['Alpha M3', 'Zulu M3'],
        )

    def test_average_cost_ordering_places_missing_cost_last_in_both_directions(self):
        stock = self.alpha.stocks.get(branch=self.branch)
        stock.average_unit_cost = None
        stock.save(update_fields=('average_unit_cost', 'updated_at'))
        ascending = self.client.get(self.stock_url('average_unit_cost'))
        self.assertEqual(ascending.status_code, 200, ascending.data)
        self.assertEqual(
            [item['product_name'] for item in ascending.data['results']],
            ['Produto V25', 'Zulu M3'],
        )
        ascending_last = self.client.get(self.stock_url('average_unit_cost', page=2))
        self.assertEqual(
            [item['product_name'] for item in ascending_last.data['results']],
            ['Alpha M3'],
        )
        descending = self.client.get(self.stock_url('-average_unit_cost'))
        self.assertEqual(descending.status_code, 200, descending.data)
        self.assertEqual(
            [item['product_name'] for item in descending.data['results']],
            ['Zulu M3', 'Produto V25'],
        )

    def test_non_transfer_stock_movement_retrieve_never_dereferences_transfer_item(self):
        movement = entry(
            product=self.alpha, branch=self.branch, user=self.user,
            quantity='1', reason='Entrada manual M4.1',
        )
        self.assertIsNone(movement.transfer_item_id)
        response = self.client.get(
            f'/api/v1/stock-movements/{movement.pk}/?company={self.company.pk}'
            f'&branch={self.branch.pk}'
        )
        self.assertEqual(response.status_code, 200, response.data)

        unauthorized = User.objects.create_user(
            email='unauthorized.m41@example.com', password='password-123'
        )
        client = APIClient()
        client.force_authenticate(unauthorized)
        response = client.get(
            f'/api/v1/stock-movements/{movement.pk}/?company={self.company.pk}',
            HTTP_X_BRANCH_ID=str(self.branch.pk),
        )
        self.assertIn(response.status_code, (403, 404), response.data)

    def test_stock_ordering_rejects_unknown_fields(self):
        response = self.client.get(self.stock_url('created_at'))
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('ordering', response.data)

    def test_product_autocomplete_endpoint_searches_all_identifiers_paginated(self):
        for value in ('Alpha M3', 'M3-ALPHA', 'SKU-M3-ALPHA', '7890000000301'):
            response = self.client.get(
                f'/api/v1/products/?company={self.company.pk}&branch={self.branch.pk}'
                f'&inventory_behavior=direct&status=active&page_size=1&search={value}'
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['count'], 1)
            self.assertEqual(response.data['results'][0]['id'], self.alpha.pk)

    def test_history_exposes_a_typed_transfer_origin(self):
        set_stock(self.destination, self.alpha, '0', '0')
        transfer = create_stock_transfer(
            origin_branch=self.branch,
            destination_branch=self.destination,
            items=[{'product': self.alpha.pk, 'quantity': '1'}],
            notes='Transferência M3',
            user=self.user,
        )
        dispatch_stock_transfer(
            transfer=transfer, idempotency_key=uuid.uuid4(), user=self.user
        )
        movement = transfer.items.get().stock_movements.get()
        response = self.client.get(
            f'/api/v1/stock-movements/{movement.pk}/?company={self.company.pk}&branch={self.branch.pk}'
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['origin'], {
            'kind': 'transfer', 'id': str(transfer.pk), 'label': 'Transferência',
        })
