import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.products.models import ContentUnit, FractionableProductConfig, Product
from apps.companies.models import Branch, Company
from apps.products.models import Category

from .test_v2_5_inventory import fixture, set_stock
from ..models import InventoryCountMode, InventoryCountStatus, LossRecord, Stock, StockMovement
from ..serializers import InventoryCountInputItemSerializer
from ..services import activate_fraction_tracking, create_inventory_count, exit, group_entry, record_loss


class Block3InventoryTests(TestCase):
    def setUp(self):
        self.company, self.branch, self.other_branch, self.product, self.user = fixture('B3')
        set_stock(self.branch, self.product, '5', '2')

    def test_full_count_includes_zero_stock_and_partial_is_limited(self):
        zero_product = Product.objects.create(
            company=self.company, category=self.product.category,
            name='Produto sem saldo', internal_code='ZERO-B3', unit='kg',
            cost='2', sale_price='4',
        )
        full = create_inventory_count(
            branch=self.branch,
            mode=InventoryCountMode.FULL,
            observation='',
            items=[
                {'product': self.product.pk, 'counted_quantity': '5'},
                {'product': zero_product.pk, 'counted_quantity': '0'},
            ],
            user=self.user,
        )
        self.assertEqual(full.mode, InventoryCountMode.FULL)
        self.assertEqual(full.items.count(), 2)
        self.assertEqual(
            full.items.get(product=zero_product).theoretical_quantity,
            Decimal('0.000000000'),
        )
        full_id = full.pk
        full.status = InventoryCountStatus.CONFIRMED
        with self.assertRaises(ValidationError):
            full.save()
        self.assertEqual(full_id, full.pk)

        partial = create_inventory_count(
            branch=self.other_branch,
            mode=InventoryCountMode.PARTIAL,
            items=[{'product': self.product.pk, 'counted_quantity': '0'}],
            user=self.user,
        )
        self.assertEqual(partial.items.count(), 1)

    def test_full_count_rejects_omitted_controlled_product(self):
        Product.objects.create(
            company=self.company, category=self.product.category,
            name='Produto omitido', internal_code='OMIT-B3', unit='kg',
            cost='2', sale_price='4',
        )
        with self.assertRaises(ValidationError):
            create_inventory_count(
                branch=self.branch,
                mode=InventoryCountMode.FULL,
                items=[{'product': self.product.pk, 'counted_quantity': '5'}],
                user=self.user,
            )

    def test_fractional_count_accepts_empty_residual_as_zero(self):
        serializer = InventoryCountInputItemSerializer(data={
            'product': self.product.pk,
            'counted_complete_packages': 2,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_normal_exit_creates_one_movement_without_a_loss_record(self):
        exit(
            self.product, self.branch, self.user,
            quantity='1', reason='Saída operacional',
        )
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(LossRecord.objects.count(), 0)

    def test_entry_accepts_multiple_categories_and_ignores_zero_items(self):
        other_category = Category.objects.create(company=self.company, name='Bebidas B3')
        other_product = Product.objects.create(
            company=self.company, category=other_category, name='Produto B3 dois',
            internal_code='B3-SECOND', unit='kg', cost='2', sale_price='4',
        )
        movements = group_entry(
            branch=self.branch,
            items=[
                {'product': self.product.pk, 'quantity': '2'},
                {'product': other_product.pk, 'quantity': '3'},
                {'product': self.product.pk, 'content_quantity': '0'},
            ],
            user=self.user, operation_reference=uuid.uuid4(),
        )
        self.assertEqual(len(movements), 2)
        self.assertEqual({movement.operation_reference for movement in movements}.__len__(), 1)
        self.assertEqual(Stock.objects.get(branch=self.branch, product=self.product).current_quantity, Decimal('7'))
        self.assertEqual(Stock.objects.get(branch=self.branch, product=other_product).current_quantity, Decimal('3'))

    def test_entry_rejects_duplicate_or_cross_tenant_items_without_partial_entry(self):
        other_company = Company.objects.create(trade_name='Entrada externa', legal_name='Entrada externa Ltda')
        other_category = Category.objects.create(company=other_company, name='Categoria externa')
        external_product = Product.objects.create(
            company=other_company, category=other_category, name='Produto externo entrada',
            internal_code='ENTRY-EXT', unit='kg', cost='1', sale_price='2',
        )
        with self.assertRaises(ValidationError):
            group_entry(
                branch=self.branch,
                items=[
                    {'product': self.product.pk, 'quantity': '1'},
                    {'product': external_product.pk, 'quantity': '1'},
                ],
                user=self.user, operation_reference=uuid.uuid4(),
            )
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_entry_accepts_exact_content_for_fractional_product(self):
        product = Product.objects.create(
            company=self.company, category=self.product.category, name='Produto fracionado B3',
            internal_code='B3-FRACTION', unit='un', cost='2', sale_price='4',
        )
        config = FractionableProductConfig.objects.create(
            product=product, package_content='1000', content_unit=ContentUnit.MILLILITER,
        )
        activate_fraction_tracking(config=config, user=self.user)
        group_entry(
            branch=self.branch,
            items=[{'product': product.pk, 'content_quantity': '250.5'}],
            user=self.user, operation_reference=uuid.uuid4(),
        )
        stock = Stock.objects.get(branch=self.branch, product=product)
        self.assertEqual(stock.current_content, Decimal('250.500000000'))
        self.assertEqual(stock.current_quantity, Decimal('0.250500000'))

    def test_entry_options_only_loads_products_on_explicit_query(self):
        Product.objects.create(
            company=self.company, category=self.product.category, name='Produto codigo barras B3',
            internal_code='B3-BAR', barcode='7890000000001', unit='kg', cost='2', sale_price='4',
        )
        client = APIClient()
        client.force_authenticate(self.user)
        url = reverse('stock-movement-entry-options')
        initial = client.get(url, HTTP_X_BRANCH_ID=str(self.branch.pk))
        self.assertEqual(initial.status_code, 200, initial.data)
        self.assertEqual(initial.data['products'], [])
        searched = client.get(
            f'{url}?search=7890000000001', HTTP_X_BRANCH_ID=str(self.branch.pk),
        )
        self.assertEqual(searched.status_code, 200, searched.data)
        self.assertEqual([item['internal_code'] for item in searched.data['products']], ['B3-BAR'])
        all_products = client.get(f'{url}?all=true', HTTP_X_BRANCH_ID=str(self.branch.pk))
        self.assertGreaterEqual(len(all_products.data['products']), 2)

    def test_loss_observation_is_optional_except_other(self):
        loss = record_loss(
            branch=self.branch, product=self.product, idempotency_key=uuid.uuid4(),
            quantity='1', reason='BREAKAGE', observation='', user=self.user,
        )
        self.assertEqual(loss.observation, '')
        with self.assertRaises(ValidationError):
            record_loss(
                branch=self.branch, product=self.product, idempotency_key=uuid.uuid4(),
                quantity='1', reason='OTHER', observation='', user=self.user,
            )

    def test_loss_rejects_cross_tenant_product_and_branch(self):
        other_company = Company.objects.create(trade_name='Outro B3', legal_name='Outro B3 Ltda')
        other_branch = Branch.objects.create(company=other_company, name='Outra matriz', is_matrix=True)
        other_category = Category.objects.create(company=other_company, name='Outra categoria')
        other_product = Product.objects.create(
            company=other_company, category=other_category, name='Produto externo',
            internal_code='EXT-B3', unit='kg', cost='1', sale_price='2',
        )
        with self.assertRaises(ValidationError):
            record_loss(
                branch=self.branch, product=other_product, idempotency_key=uuid.uuid4(),
                quantity='1', reason='BREAKAGE', user=self.user,
            )
        with self.assertRaises(ValidationError):
            record_loss(
                branch=other_branch, product=self.product, idempotency_key=uuid.uuid4(),
                quantity='1', reason='BREAKAGE', user=self.user,
            )

    def test_loss_attachment_is_private_and_branch_scoped(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(
            reverse('loss-record-list'),
            {
                'idempotency_key': str(uuid.uuid4()),
                'branch': str(self.branch.pk),
                'product': str(self.product.pk),
                'quantity': '1',
                'reason': 'BREAKAGE',
                'attachment': SimpleUploadedFile(
                    'quebra.png', b'\x89PNG\r\n\x1a\nloss-photo', content_type='image/png'
                ),
            },
            HTTP_X_BRANCH_ID=str(self.branch.pk),
        )
        self.assertEqual(response.status_code, 201, response.data)
        loss = LossRecord.objects.get(pk=response.data['id'])
        self.assertTrue(loss.attachment.name.startswith(f'losses/{self.company.pk}/'))
        self.assertNotIn('/private_media/', response.data['attachment']['download_url'])
        denied = client.get(
            reverse('loss-record-attachment', args=[loss.pk]),
            HTTP_X_BRANCH_ID=str(self.other_branch.pk),
        )
        self.assertIn(denied.status_code, (403, 404))
        loss.attachment.storage.delete(loss.attachment.name)
