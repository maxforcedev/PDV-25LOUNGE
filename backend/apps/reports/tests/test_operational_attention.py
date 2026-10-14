from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.companies.models import AccessProfile, Branch, FunctionalPermission, UserBranchAccess
from apps.production.models import PrintJob, PrintJobStatus, PrinterDevice
from apps.products.models import Category, Product, ProductBranchConfig
from apps.inventory.models import Stock
from apps.saas.tests.helpers import create_complete_test_plan, create_operational_test_tenant


class OperationalAttentionTests(TestCase):
    def setUp(self):
        plan = create_complete_test_plan(
            'operational-attention',
            enabled_features=(
                'reports', 'products', 'inventory', 'financial', 'commands', 'production',
            ),
        )
        self.user, self.company, _subscription = create_operational_test_tenant(
            code='operational-attention', email='attention@example.com',
            trade_name='Attention', legal_name='Attention Ltda', plan_version=plan,
        )
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=('is_superuser', 'is_staff'))
        self.branch = self.company.branches.get(is_matrix=True)
        self.other_branch = Branch.objects.create(company=self.company, name='Outra filial')
        self.product = self._product(self.branch, 'Produto principal')
        self.other_product = self._product(self.other_branch, 'Produto externo')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

    def _product(self, branch, name):
        category = Category.objects.create(company=self.company, branch=branch, name=name)
        product = Product.objects.create(
            company=self.company, category=category, name=name,
            internal_code=f'ATT-{branch.pk}-{name}', cost='1.00', sale_price='2.00', unit='un',
        )
        ProductBranchConfig.objects.create(product=product, branch=branch, category=category)
        return product

    def _stock(self, product, branch, quantity):
        stock, _ = Stock.objects.get_or_create(product=product, branch=branch)
        stock.current_quantity = quantity
        stock.save(update_fields=('current_quantity', 'updated_at'))
        return stock

    def test_inventory_alerts_are_active_unique_and_branch_scoped(self):
        negative = self._stock(self.product, self.branch, Decimal('-1'))
        self._stock(self.other_product, self.other_branch, Decimal('-3'))

        response = self.client.get('/api/v1/operational-attention/?category=inventory')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['summary']['active_count'], 1)
        self.assertEqual(response.data['results'][0]['identity'], f'inventory:negative:{negative.pk}')
        self.assertEqual(response.data['results'][0]['entity']['branch_id'], self.branch.pk)
        self.assertEqual(response.data['results'][0]['route'], '/estoque?state=negative')

        dashboard = self.client.get('/api/v1/dashboard/')
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(
            dashboard.data['operational_attention']['active_count'],
            response.data['summary']['active_count'],
        )

        negative.current_quantity = Decimal('5')
        negative.save(update_fields=('current_quantity', 'updated_at'))
        recovered = self.client.get('/api/v1/operational-attention/?category=inventory')
        self.assertEqual(recovered.status_code, 200, recovered.data)
        self.assertEqual(recovered.data['summary']['active_count'], 0)

    def test_inventory_alerts_ignore_unavailable_products_and_paginate_without_duplicates(self):
        first = self._stock(self.product, self.branch, Decimal('0'))
        second_product = self._product(self.branch, 'Segundo produto')
        second = self._stock(second_product, self.branch, Decimal('-1'))

        response = self.client.get('/api/v1/operational-attention/?category=inventory&page_size=1')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 2)
        self.assertTrue(response.data['next'])
        self.assertIn(response.data['results'][0]['identity'], {
            f'inventory:zero:{first.pk}', f'inventory:negative:{second.pk}',
        })
        next_page = self.client.get('/api/v1/operational-attention/?category=inventory&page_size=1&page=2')
        self.assertEqual(next_page.status_code, 200, next_page.data)
        self.assertNotEqual(
            response.data['results'][0]['identity'], next_page.data['results'][0]['identity'],
        )

        first.current_quantity = Decimal('2')
        first.save(update_fields=('current_quantity', 'updated_at'))
        replenished = self.client.get('/api/v1/operational-attention/?category=inventory')
        self.assertEqual(replenished.status_code, 200, replenished.data)
        self.assertEqual(replenished.data['summary']['active_count'], 1)
        self.assertEqual(replenished.data['results'][0]['identity'], f'inventory:negative:{second.pk}')

        config = ProductBranchConfig.objects.get(product=self.product, branch=self.branch)
        config.is_available = False
        config.save(update_fields=('is_available', 'updated_at'))
        unavailable = self.client.get('/api/v1/operational-attention/?category=inventory')
        self.assertEqual(unavailable.status_code, 200, unavailable.data)
        self.assertEqual(unavailable.data['summary']['active_count'], 1)
        self.assertEqual(unavailable.data['results'][0]['identity'], f'inventory:negative:{second.pk}')

    def test_print_failures_are_active_and_disappear_when_resolved(self):
        printer = PrinterDevice.objects.create(branch=self.branch, name='Cozinha')
        job = PrintJob.objects.create(
            company=self.company, branch=self.branch, printer_device=printer,
            is_test=True, status=PrintJobStatus.FAILED, last_error='Sem conexão',
        )

        response = self.client.get('/api/v1/operational-attention/?category=printing')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['summary']['active_count'], 1)
        self.assertEqual(response.data['results'][0]['identity'], f'printing:failed:{job.pk}')
        self.assertEqual(response.data['results'][0]['route'], '/producao/falhas')
        dashboard = self.client.get('/api/v1/dashboard/')
        central = self.client.get('/api/v1/operational-attention/')
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(central.status_code, 200, central.data)
        self.assertEqual(
            dashboard.data['operational_attention']['active_count'],
            central.data['summary']['active_count'],
        )

        job.status = PrintJobStatus.PENDING
        job.save(update_fields=('status', 'updated_at'))
        resolved = self.client.get('/api/v1/operational-attention/?category=printing')
        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(resolved.data['summary']['active_count'], 0)

    def test_access_is_limited_to_the_selected_tenant_and_branch_permissions(self):
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save(update_fields=('is_superuser', 'is_staff'))
        foreign_owner, foreign_company, _ = create_operational_test_tenant(
            code='operational-attention-foreign', email='foreign-attention@example.com',
            trade_name='Foreign attention', legal_name='Foreign attention Ltda',
        )
        foreign_branch = foreign_company.branches.get(is_matrix=True)
        self.assertIsNotNone(foreign_owner)

        denied = self.client.get(
            '/api/v1/operational-attention/', HTTP_X_BRANCH_ID=str(foreign_branch.pk),
        )
        self.assertEqual(denied.status_code, 403)

        limited = AccessProfile.objects.create(company=self.company, name='Somente dashboard')
        limited.permissions.add(FunctionalPermission.objects.get(code='dashboard.view'))
        branch_access = UserBranchAccess.objects.get(user=self.user, branch=self.branch)
        branch_access.access_profile = limited
        branch_access.save(update_fields=('access_profile', 'updated_at'))
        restricted = self.client.get('/api/v1/operational-attention/')
        self.assertEqual(restricted.status_code, 200, restricted.data)
        self.assertEqual(restricted.data['available_categories'], [])
        self.assertEqual(restricted.data['summary']['active_count'], 0)

    def test_disabled_modules_do_not_expose_categories(self):
        plan = create_complete_test_plan(
            'operational-attention-reports-only', enabled_features=('reports',),
        )
        owner, company, _ = create_operational_test_tenant(
            code='operational-attention-reports-only', email='reports-only@example.com',
            trade_name='Reports only', legal_name='Reports only Ltda', plan_version=plan,
        )
        client = APIClient()
        client.force_authenticate(owner)
        client.defaults['HTTP_X_BRANCH_ID'] = str(company.branches.get(is_matrix=True).pk)

        response = client.get('/api/v1/operational-attention/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['available_categories'], [])
        self.assertEqual(response.data['summary']['active_count'], 0)

    def test_attention_rejects_unknown_filters_and_paginates(self):
        self._stock(self.product, self.branch, Decimal('0'))
        invalid = self.client.get('/api/v1/operational-attention/?category=cash')
        self.assertEqual(invalid.status_code, 400)

        response = self.client.get('/api/v1/operational-attention/?category=inventory&page_size=1')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)
