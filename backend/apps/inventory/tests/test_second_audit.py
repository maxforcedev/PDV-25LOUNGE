from datetime import timedelta
from decimal import Decimal
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import (
    AccessProfile,
    Branch,
    Company,
    FunctionalPermission,
    UserBranchAccess,
    UserCompanyAccess,
)
from apps.companies.services import ensure_permission_catalog
from apps.products.models import Category, Product, ProductBranchConfig
from apps.reports.selectors import filtered_inventory_movements, inventory_kpis

from ..models import InventoryCountMode, Stock
from ..services import create_inventory_count, entry


class SecondAuditInventoryTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.user = User.objects.create_user(
            email='inventory-audit@example.com', password='password-123'
        )
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=('is_superuser', 'is_staff'))
        self.company = Company.objects.create(
            trade_name='Inventory Audit', legal_name='Inventory Audit Ltda'
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
        self.product = Product.objects.create(
            company=self.company,
            category=self.category,
            name='Coca Audit',
            internal_code='COCA-AUDIT',
            cost=Decimal('2.00'),
            sale_price=Decimal('5.00'),
        )
        ProductBranchConfig.objects.create(
            product=self.product, branch=self.branch, category=self.category
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

    def test_entry_options_and_entry_do_not_require_products_view(self):
        operator = User.objects.create_user(
            email='entry-only@example.com', password='password-123'
        )
        permissions = FunctionalPermission.objects.filter(
            code__in=('inventory.entry',)
        )
        profile = AccessProfile.objects.create(
            company=self.company, name='Somente entrada'
        )
        profile.permissions.set(permissions)
        UserCompanyAccess.objects.create(
            user=operator, company=self.company, access_profile=profile
        )
        UserBranchAccess.objects.create(
            user=operator, branch=self.branch, access_profile=profile
        )
        client = APIClient()
        client.force_authenticate(operator)
        client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

        options = client.get(
            '/api/v1/stock-movements/entry-options/?search=Coca'
        )
        self.assertEqual(options.status_code, 200, options.data)
        self.assertEqual(options.data['products'][0]['id'], self.product.pk)
        response = client.post(
            '/api/v1/stock-movements/entry/',
            {
                'idempotency_key': str(uuid.uuid4()),
                'branch': self.branch.pk,
                'product': self.product.pk,
                'quantity': '2',
                'nature': 'normal',
                'reason': 'Carga inicial',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_archived_balance_is_only_in_position_and_can_be_written_off(self):
        entry(
            product=self.product,
            branch=self.branch,
            user=self.user,
            quantity='3',
            reason='Carga inicial',
        )
        Product.objects.filter(pk=self.product.pk).update(
            archived_at=timezone.now(), archived_by=self.user
        )

        position = self.client.get('/api/v1/stocks/')
        self.assertEqual(position.status_code, 200, position.data)
        self.assertEqual(position.data['count'], 1)
        self.assertTrue(position.data['results'][0]['product_deleted'])
        summary = self.client.get('/api/v1/stocks/summary/')
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data['physical_products'], 0)

        stock = Stock.objects.get(product=self.product, branch=self.branch)
        response = self.client.post(
            f'/api/v1/stocks/{stock.pk}/write-off-residual/',
            {'reason': 'Baixa de item excluído'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        stock.refresh_from_db()
        self.assertEqual(stock.current_quantity, Decimal('0.000'))
        self.assertEqual(self.client.get('/api/v1/stocks/').data['count'], 0)

    def test_full_count_uses_only_operational_products_from_current_branch(self):
        other_category = Category.objects.create(
            company=self.company, branch=self.other_branch, name='Outra filial'
        )
        other_product = Product.objects.create(
            company=self.company,
            category=other_category,
            name='Produto B',
            internal_code='PROD-B',
            cost=Decimal('1.00'),
            sale_price=Decimal('2.00'),
        )
        ProductBranchConfig.objects.create(
            product=other_product,
            branch=self.other_branch,
            category=other_category,
        )

        count = create_inventory_count(
            branch=self.branch,
            mode=InventoryCountMode.FULL,
            items=[{'product': self.product.pk, 'counted_quantity': '0'}],
            user=self.user,
        )
        self.assertQuerySetEqual(
            count.items.values_list('product_id', flat=True),
            [self.product.pk],
        )

    def test_movement_category_filter_uses_current_branch_configuration(self):
        effective_category = Category.objects.create(
            company=self.company, branch=self.branch, name='Categoria efetiva'
        )
        config = ProductBranchConfig.objects.get(
            product=self.product, branch=self.branch
        )
        config.category = effective_category
        config.save(update_fields=('category', 'updated_at'))
        entry(
            product=self.product,
            branch=self.branch,
            user=self.user,
            quantity='1',
            reason='Entrada para filtro',
        )

        effective = self.client.get(
            f'/api/v1/stock-movements/?category={effective_category.pk}'
        )
        legacy = self.client.get(
            f'/api/v1/stock-movements/?category={self.category.pk}'
        )

        self.assertEqual(effective.status_code, 200, effective.data)
        self.assertEqual(effective.data['count'], 1)
        self.assertEqual(legacy.status_code, 200, legacy.data)
        self.assertEqual(legacy.data['count'], 0)
        period = {
            'start': timezone.now() - timedelta(days=1),
            'end': timezone.now() + timedelta(days=1),
        }
        self.assertEqual(filtered_inventory_movements(
            branch=self.branch,
            filters={'category': effective_category.pk},
            **period,
        ).count(), 1)
        self.assertEqual(filtered_inventory_movements(
            branch=self.branch,
            filters={'category': self.category.pk},
            **period,
        ).count(), 0)
        self.assertEqual(
            inventory_kpis(self.branch, category=effective_category.pk)['physical_products'],
            1,
        )
        self.assertEqual(
            inventory_kpis(self.branch, category=self.category.pk)['physical_products'],
            0,
        )
