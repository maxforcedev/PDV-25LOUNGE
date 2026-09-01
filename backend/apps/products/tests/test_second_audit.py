from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Branch, Company

from ..models import Category, Product, ProductBranchConfig
from ..views import branch_price_comparison


class SecondAuditProductTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='products-audit@example.com', password='password-123'
        )
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=('is_superuser', 'is_staff'))
        self.company = Company.objects.create(
            trade_name='Products Audit', legal_name='Products Audit Ltda'
        )
        self.branch = Branch.objects.create(
            company=self.company, name='Filial A', is_matrix=True
        )
        self.other_branch = Branch.objects.create(
            company=self.company, name='Filial B'
        )
        self.category = Category.objects.create(
            company=self.company, branch=self.branch, name='Bebidas'
        )
        self.other_category = Category.objects.create(
            company=self.company, branch=self.other_branch, name='Outros'
        )
        self.product = Product.objects.create(
            company=self.company,
            category=self.category,
            name='Coca Audit',
            internal_code='COCA-AUDIT',
            cost=Decimal('2.00'),
            sale_price=Decimal('6.00'),
        )
        self.config = ProductBranchConfig.objects.create(
            product=self.product, branch=self.branch, category=self.category
        )
        self.other_config = ProductBranchConfig.objects.create(
            product=self.product,
            branch=self.other_branch,
            category=self.other_category,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

    def test_category_delete_blocks_operational_product_then_allows_reuse(self):
        blocked = self.client.delete(f'/api/v1/categories/{self.category.pk}/')
        self.assertEqual(blocked.status_code, 400, blocked.data)

        self.config.is_available = False
        self.config.save()
        deleted = self.client.delete(f'/api/v1/categories/{self.category.pk}/')
        self.assertEqual(deleted.status_code, 204, deleted.data)
        self.category.refresh_from_db()
        self.assertIsNotNone(self.category.deleted_at)
        recreated = self.client.post('/api/v1/categories/', {
            'company': self.company.pk,
            'name': 'Bebidas',
            'description': '',
            'available_counter': True,
            'available_table': True,
            'available_command': True,
            'participates_in_service_fee': True,
            'participates_in_commission': True,
        }, format='json')
        self.assertEqual(recreated.status_code, 201, recreated.data)

    def test_apply_category_config_is_branch_scoped_and_includes_financial_flags(self):
        self.category.available_counter = False
        self.category.participates_in_service_fee = False
        self.category.participates_in_commission = False
        self.category.save()

        response = self.client.post(
            f'/api/v1/categories/{self.category.pk}/apply-config/'
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.config.refresh_from_db()
        self.other_config.refresh_from_db()
        self.assertFalse(self.config.available_counter)
        self.assertFalse(self.config.participates_in_service_fee)
        self.assertFalse(self.config.participates_in_commission)
        self.assertIsNone(self.other_config.participates_in_service_fee)
        self.assertIsNone(self.other_config.participates_in_commission)

    def test_archived_name_requires_explicit_restore_or_create_new(self):
        Product.objects.filter(pk=self.product.pk).update(
            archived_at=timezone.now(), archived_by=self.user
        )
        payload = {
            'company': self.company.pk,
            'category': self.category.pk,
            'name': self.product.name,
            'internal_code': 'COCA-NEW',
            'unit': 'un',
            'cost': '2.00',
            'sale_price': '6.00',
        }
        conflict = self.client.post('/api/v1/products/', payload, format='json')
        self.assertEqual(conflict.status_code, 400, conflict.data)
        self.assertEqual(conflict.data['code'], 'archived_product_exists')
        self.assertEqual(conflict.data['details']['product_id'], self.product.pk)

        created = self.client.post(
            '/api/v1/products/', {**payload, 'create_new': True}, format='json'
        )
        self.assertEqual(created.status_code, 201, created.data)
        restored = self.client.post(f'/api/v1/products/{self.product.pk}/restore/')
        self.assertEqual(restored.status_code, 400, restored.data)
        self.assertIn('name', restored.data)

    def test_price_matrix_marks_branches_without_availability(self):
        self.other_config.is_available = False
        self.other_config.save()
        data = branch_price_comparison(self.company.pk)
        row = next(item for item in data['products'] if item['id'] == self.product.pk)
        self.assertTrue(row['availability'][str(self.branch.pk)])
        self.assertFalse(row['availability'][str(self.other_branch.pk)])
