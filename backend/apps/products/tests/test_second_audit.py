from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Branch, Company

from ..models import (
    Category, FractionableProductConfig, InventoryBehavior, Product,
    ProductBranchConfig, ProductComponent, ProductFractionComponent,
)
from apps.inventory.services import activate_fraction_tracking
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
        self.assertEqual(recreated.status_code, 400, recreated.data)
        self.assertEqual(recreated.data['code'], 'archived_category_exists')
        self.assertEqual(recreated.data['details']['category_id'], self.category.pk)
        restored = self.client.post(
            f'/api/v1/categories/{self.category.pk}/restore/'
        )
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertEqual(restored.data['id'], self.category.pk)
        self.category.refresh_from_db()
        self.assertIsNone(self.category.deleted_at)
        self.assertEqual(self.category.status, 'active')

    def test_apply_category_config_is_branch_scoped_and_includes_financial_flags(self):
        active_configs = [self.config]
        for index in range(2):
            active = Product.objects.create(
                company=self.company, category=self.category,
                name=f'Ativo Audit {index}', internal_code=f'ACTIVE-AUDIT-{index}',
                cost='1.00', sale_price='2.00',
            )
            active_configs.append(ProductBranchConfig.objects.create(
                product=active, branch=self.branch, category=self.category,
            ))
        archived_configs = []
        for index in range(2):
            archived = Product.objects.create(
                company=self.company, category=self.category,
                name=f'Arquivado Audit {index}', internal_code=f'ARCH-AUDIT-{index}',
                cost='1.00', sale_price='2.00',
            )
            archived_configs.append(ProductBranchConfig.objects.create(
                product=archived, branch=self.branch, category=self.category,
            ))
            Product.objects.filter(pk=archived.pk).update(
                archived_at=timezone.now(), archived_by=self.user
            )
        unavailable = Product.objects.create(
            company=self.company, category=self.category, name='Indisponível Audit',
            internal_code='UNAV-AUDIT', cost='1.00', sale_price='2.00',
        )
        unavailable_config = ProductBranchConfig.objects.create(
            product=unavailable, branch=self.branch, category=self.category,
            is_available=False,
        )
        self.category.available_counter = False
        self.category.participates_in_service_fee = False
        self.category.participates_in_commission = False
        self.category.save()

        response = self.client.post(
            f'/api/v1/categories/{self.category.pk}/apply-config/'
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['updated_products'], 3)
        self.assertEqual(response.data['total_products'], 3)
        for config in active_configs:
            config.refresh_from_db()
        self.other_config.refresh_from_db()
        for config in archived_configs:
            config.refresh_from_db()
        unavailable_config.refresh_from_db()
        for config in active_configs:
            self.assertFalse(config.available_counter)
            self.assertFalse(config.participates_in_service_fee)
            self.assertFalse(config.participates_in_commission)
        self.assertIsNone(self.other_config.participates_in_service_fee)
        self.assertIsNone(self.other_config.participates_in_commission)
        for config in archived_configs:
            self.assertIsNone(config.participates_in_service_fee)
        self.assertIsNone(unavailable_config.participates_in_service_fee)

    def test_archived_name_requires_restoring_the_same_product(self):
        archived = self.client.post(
            f'/api/v1/products/{self.product.pk}/archive/'
        )
        self.assertEqual(archived.status_code, 200, archived.data)
        self.product.refresh_from_db()
        self.assertIsNotNone(self.product.archived_at)
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
        self.assertIsNotNone(conflict.data['details']['archived_at'])

        restored = self.client.post(f'/api/v1/products/{self.product.pk}/restore/')
        self.assertEqual(restored.status_code, 200, restored.data)
        self.product.refresh_from_db()
        self.assertIsNone(self.product.archived_at)
        self.assertEqual(restored.data['id'], self.product.pk)

    def test_price_matrix_marks_branches_without_availability(self):
        self.other_config.is_available = False
        self.other_config.save()
        data = branch_price_comparison(self.company.pk)
        row = next(item for item in data['products'] if item['id'] == self.product.pk)
        self.assertTrue(row['availability'][str(self.branch.pk)])
        self.assertFalse(row['availability'][str(self.other_branch.pk)])

    def test_product_detail_and_edit_use_effective_branch_financial_config(self):
        self.config.participates_in_service_fee = False
        self.config.participates_in_commission = False
        self.config.available_counter = False
        self.config.save()
        self.other_config.participates_in_service_fee = True
        self.other_config.participates_in_commission = True
        self.other_config.available_counter = True
        self.other_config.save()

        pavuna = self.client.get(f'/api/v1/products/{self.product.pk}/')
        self.assertEqual(pavuna.status_code, 200, pavuna.data)
        self.assertFalse(pavuna.data['participates_in_service_fee'])
        self.assertFalse(pavuna.data['participates_in_commission'])
        self.assertFalse(pavuna.data['available_counter'])

        beira_mar = self.client.get(
            f'/api/v1/products/{self.product.pk}/',
            HTTP_X_BRANCH_ID=str(self.other_branch.pk),
        )
        self.assertEqual(beira_mar.status_code, 200, beira_mar.data)
        self.assertTrue(beira_mar.data['participates_in_service_fee'])
        self.assertTrue(beira_mar.data['available_counter'])

        updated = self.client.patch(
            f'/api/v1/products/{self.product.pk}/',
            {
                'participates_in_service_fee': True,
                'participates_in_commission': False,
                'available_counter': True,
            },
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.config.refresh_from_db()
        self.other_config.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(self.config.participates_in_service_fee)
        self.assertFalse(self.config.participates_in_commission)
        self.assertTrue(self.config.available_counter)
        self.assertTrue(self.other_config.participates_in_service_fee)
        self.assertTrue(self.other_config.participates_in_commission)
        self.assertTrue(self.product.participates_in_service_fee)
        audit = self.product.branch_configs.get(branch=self.branch)
        from apps.base.models import AuditLog
        log = AuditLog.objects.filter(
            action='product.branch_config.update', object_id=str(audit.pk)
        ).latest('pk')
        self.assertFalse(log.before['participates_in_service_fee'])
        self.assertTrue(log.after['participates_in_service_fee'])

    def test_archive_blocks_common_component_until_relation_is_removed(self):
        parent = Product.objects.create(
            company=self.company, category=self.category, name='Combo Audit',
            internal_code='COMBO-AUDIT', cost='2.00', sale_price='10.00',
            inventory_behavior=InventoryBehavior.COMPONENTS, is_sellable=False,
        )
        relation = ProductComponent.objects.create(
            parent_product=parent, component_product=self.product, quantity='1'
        )
        parent.is_sellable = True
        parent.save()

        blocked = self.client.post(
            f'/api/v1/products/{self.product.pk}/archive/'
        )
        self.assertEqual(blocked.status_code, 400, blocked.data)
        self.assertIn(parent.name, str(blocked.data['product']))
        relation.delete()
        archived = self.client.post(
            f'/api/v1/products/{self.product.pk}/archive/'
        )
        self.assertEqual(archived.status_code, 200, archived.data)

    def test_archive_blocks_fraction_component_and_ignores_archived_parent(self):
        fraction = FractionableProductConfig.objects.create(
            product=self.product, package_content='1000', content_unit='ml'
        )
        activate_fraction_tracking(config=fraction, user=self.user)
        parent = Product.objects.create(
            company=self.company, category=self.category,
            name='Drink fracionado Audit', internal_code='FRAC-PARENT-AUDIT',
            cost='2.00', sale_price='10.00',
            inventory_behavior=InventoryBehavior.COMPONENTS, is_sellable=False,
        )
        ProductFractionComponent.objects.create(
            parent_product=parent,
            component_product=self.product,
            content_quantity='100',
        )
        parent.is_sellable = True
        parent.save()

        blocked = self.client.post(
            f'/api/v1/products/{self.product.pk}/archive/'
        )
        self.assertEqual(blocked.status_code, 400, blocked.data)
        self.assertIn(parent.name, str(blocked.data['product']))
        Product.objects.filter(pk=parent.pk).update(
            archived_at=timezone.now(), archived_by=self.user
        )
        allowed = self.client.post(
            f'/api/v1/products/{self.product.pk}/archive/'
        )
        self.assertEqual(allowed.status_code, 200, allowed.data)
