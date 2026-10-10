from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.saas.tests.helpers import create_operational_company_with_matrix as create_company_with_matrix
from apps.products.models import Category, Product, ProductBranchConfig, SalesChannel, Unit
from apps.products.selectors import sellable_products_for_branch


class SellableCatalogSelectorTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='catalog-domain@example.com', password='Strong-password-123!',
        )
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Catalog Domain', legal_name='Catalog Domain Ltda',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.category = Category.objects.create(
            company=self.company, branch=self.branch, name='Bebidas',
        )

    def product(self, *, name, code, **attributes):
        channel_attributes = {
            key: attributes.pop(key)
            for key in tuple(attributes)
            if key.startswith('available_')
        }
        product = Product.objects.create(
            company=self.company,
            category=self.category,
            name=name,
            internal_code=code,
            unit=Unit.UNIT,
            cost=Decimal('1.00'),
            sale_price=Decimal('5.00'),
            **attributes,
        )
        ProductBranchConfig.objects.create(
            product=product, branch=self.branch, category=self.category,
            **channel_attributes,
        )
        return product

    def test_selector_applies_branch_channel_override_and_keeps_barcode_textual(self):
        available = self.product(name='Agua', code='AGUA', barcode='001234')
        self.product(
            name='Apenas Mesa', code='MESA', barcode='001235', available_counter=False,
        )
        self.product(name='Insumo', code='INSUMO', barcode='001236', is_sellable=False)

        counter_ids = sellable_products_for_branch(
            self.branch, SalesChannel.COUNTER,
        ).values_list('pk', flat=True)
        scanned_ids = sellable_products_for_branch(
            self.branch, SalesChannel.COUNTER, barcode='001234',
        ).values_list('pk', flat=True)

        self.assertEqual(list(counter_ids), [available.pk])
        self.assertEqual(list(scanned_ids), [available.pk])
