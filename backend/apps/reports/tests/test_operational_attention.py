from decimal import Decimal
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.models import AuditLog
from apps.cash.models import CashDiscrepancyResolution, CashRegister, CashSession, CashSessionStatus
from apps.companies.models import (
    AccessProfile, Branch, FunctionalPermission, UserBranchAccess, UserCompanyAccess,
)
from apps.production.models import PrintDocument, PrintJob, PrintJobStatus, PrinterDevice
from apps.products.models import Category, Product, ProductBranchConfig
from apps.inventory.models import Stock
from apps.reports.selectors import inventory_kpis, stock_position_report
from apps.saas.tests.helpers import create_complete_test_plan, create_operational_test_tenant


class OperationalAttentionTests(TestCase):
    def setUp(self):
        plan = create_complete_test_plan(
            'operational-attention',
            enabled_features=(
                'reports', 'products', 'inventory', 'financial', 'commands', 'production',
                'cash_register',
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

    def _production_print_job(self, printer, **kwargs):
        document = PrintDocument.objects.create(
            company=self.company, branch=self.branch, document_type='ticket',
            source_type='operational-attention-test', source_id=str(uuid.uuid4()),
            snapshot={}, snapshot_hash=uuid.uuid4().hex,
        )
        return PrintJob.objects.create(
            company=self.company, branch=self.branch, printer_device=printer,
            print_document=document, **kwargs,
        )

    def _closed_difference(self, *, branch=None, difference=Decimal('-10.00')):
        branch = branch or self.branch
        register = CashRegister.objects.create(branch=branch, name=f'Caixa {uuid.uuid4()}')
        expected = Decimal('100.00')
        return CashSession.objects.create(
            cash_register=register, branch=branch, opened_by=self.user,
            opened_at=timezone.now(), opening_amount=Decimal('0.00'),
            status=CashSessionStatus.CLOSED, closed_by=self.user,
            closed_at=timezone.now(), closing_expected_amount=expected,
            closing_amount_informed=expected + difference,
            closing_difference=difference,
        )

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

    def test_inventory_alerts_include_active_unavailable_products_and_paginate_without_duplicates(self):
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
        self.assertEqual(unavailable.data['summary']['active_count'], 2)
        self.assertEqual(
            {alert['identity'] for alert in unavailable.data['results']},
            {f'inventory:zero:{first.pk}', f'inventory:negative:{second.pk}'},
        )

    def test_inventory_attention_includes_unavailable_but_excludes_archived_without_changing_stock_position(self):
        unavailable = self._stock(self.product, self.branch, Decimal('-2'))
        config = ProductBranchConfig.objects.get(product=self.product, branch=self.branch)
        config.is_available = False
        config.save(update_fields=('is_available', 'updated_at'))

        response = self.client.get('/api/v1/operational-attention/?category=inventory')
        dashboard = self.client.get('/api/v1/dashboard/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['summary']['active_count'], 1)
        self.assertEqual(inventory_kpis(self.branch)['negative_count'], 1)
        self.assertEqual(dashboard.data['operational_attention']['active_count'], 1)

        Product.objects.filter(pk=self.product.pk).update(archived_at=timezone.now())
        self.assertIn(
            unavailable.pk,
            stock_position_report(branch=self.branch, filters={}).values_list('pk', flat=True),
        )
        unavailable.current_quantity = Decimal('0')
        unavailable.save(update_fields=('current_quantity', 'updated_at'))
        self.assertNotIn(
            unavailable.pk,
            stock_position_report(branch=self.branch, filters={}).values_list('pk', flat=True),
        )
        self.assertIn(
            unavailable.pk,
            stock_position_report(
                branch=self.branch, filters={'lifecycle': 'archived'},
            ).values_list('pk', flat=True),
        )

    def test_print_failures_are_active_and_disappear_when_resolved(self):
        printer = PrinterDevice.objects.create(branch=self.branch, name='Cozinha')
        PrintJob.objects.create(
            company=self.company, branch=self.branch, printer_device=printer,
            is_test=True, status=PrintJobStatus.FAILED, last_error='Sem conexão',
        )
        job = self._production_print_job(
            printer, status=PrintJobStatus.FAILED, last_error='Sem conexão',
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

        job.status = PrintJobStatus.PRINTED
        job.save(update_fields=('status', 'updated_at'))
        resolved = self.client.get('/api/v1/operational-attention/?category=printing')
        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(resolved.data['summary']['active_count'], 0)

    def test_print_attention_uses_only_the_current_reprint_and_one_physical_batch(self):
        printer = PrinterDevice.objects.create(branch=self.branch, name='Bar')
        root = self._production_print_job(printer, status=PrintJobStatus.FAILED)
        failed_reprint = self._production_print_job(
            printer, status=PrintJobStatus.FAILED, reprint_of=root, reprint_number=1,
        )
        self._production_print_job(
            printer, status=PrintJobStatus.PRINTED, reprint_of=root, reprint_number=2,
        )
        batch_key = uuid.uuid4()
        first = self._production_print_job(
            printer, status=PrintJobStatus.FAILED, batch_key=batch_key,
        )
        second = self._production_print_job(
            printer, status=PrintJobStatus.FAILED, batch_key=batch_key,
        )

        response = self.client.get('/api/v1/operational-attention/?category=printing')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['summary']['active_count'], 1)
        self.assertIn(response.data['results'][0]['entity']['id'], {first.pk, second.pk})
        self.assertNotIn(f'printing:failed:{failed_reprint.pk}', {
            alert['identity'] for alert in response.data['results']
        })

    def test_print_failure_after_dispatch_requires_review_without_retrying(self):
        printer = PrinterDevice.objects.create(branch=self.branch, name='Expedição')
        job = self._production_print_job(
            printer, status=PrintJobStatus.FAILED,
            physical_dispatch_started_at=timezone.now(),
        )

        response = self.client.get('/api/v1/operational-attention/?category=printing')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'][0]['identity'], f'printing:failed:{job.pk}')
        self.assertIn('reimpressao explícita', response.data['results'][0]['recommended_action'])
        self.assertEqual(PrintJob.objects.filter(pk=job.pk).count(), 1)

    def test_confirmed_cash_closing_difference_is_visible_to_dashboard_and_central(self):
        session = self._closed_difference()

        central = self.client.get('/api/v1/operational-attention/?category=cash')
        dashboard = self.client.get('/api/v1/dashboard/')

        self.assertEqual(central.status_code, 200, central.data)
        self.assertEqual(central.data['results'][0]['identity'], f'cash:closing_difference:{session.pk}')
        self.assertEqual(
            dashboard.data['operational_attention']['by_category']['cash'], 1,
        )

    def test_cash_difference_resolution_preserves_closing_and_audits_actor(self):
        session = self._closed_difference(difference=Decimal('10.00'))
        original = (
            session.closing_expected_amount, session.closing_amount_informed,
            session.closing_difference,
        )

        response = self.client.post(
            f'/api/v1/cash-sessions/{session.pk}/address-difference/',
            {'justification': 'Conferido o numerário e a ocorrência foi registrada.'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['discrepancy_resolution']['addressed_by'], self.user.pk)
        self.assertEqual(
            response.data['discrepancy_resolution']['justification'],
            'Conferido o numerário e a ocorrência foi registrada.',
        )
        session.refresh_from_db()
        self.assertEqual(
            (session.closing_expected_amount, session.closing_amount_informed, session.closing_difference),
            original,
        )
        resolution = CashDiscrepancyResolution.objects.get(cash_session=session)
        self.assertEqual(resolution.addressed_by, self.user)
        self.assertTrue(resolution.addressed_at)
        audit = AuditLog.objects.get(action='cash_session.closing_difference_addressed')
        self.assertEqual(audit.actor, self.user)
        self.assertEqual(audit.branch, self.branch)
        self.assertEqual(audit.metadata['cash_session_id'], session.pk)
        central = self.client.get('/api/v1/operational-attention/?category=cash')
        dashboard = self.client.get('/api/v1/dashboard/')
        self.assertEqual(central.data['summary']['active_count'], 0)
        self.assertEqual(dashboard.data['operational_attention']['by_category']['cash'], 0)

    def test_cash_difference_resolution_requires_justification_and_close_permission(self):
        session = self._closed_difference()
        missing = self.client.post(
            f'/api/v1/cash-sessions/{session.pk}/address-difference/',
            {'justification': ' '}, format='json',
        )
        self.assertEqual(missing.status_code, 400)

        restricted_user = User.objects.create_user(
            email='cash-viewer@example.com', password='password-123',
        )
        profile = AccessProfile.objects.create(company=self.company, name='Somente consulta de caixa')
        profile.permissions.add(FunctionalPermission.objects.get(code='cash_registers.view'))
        company_access = UserCompanyAccess(
            user=restricted_user, company=self.company, access_profile=profile,
        )
        company_access.save(enforce_saas_limit=False)
        UserBranchAccess.objects.create(
            user=restricted_user, branch=self.branch, access_profile=profile,
        )
        restricted = APIClient()
        restricted.force_authenticate(restricted_user)
        restricted.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

        denied = restricted.post(
            f'/api/v1/cash-sessions/{session.pk}/address-difference/',
            {'justification': 'Tentativa sem autorização.'}, format='json',
        )
        self.assertEqual(denied.status_code, 403)
        foreign_owner, _foreign_company, _subscription = create_operational_test_tenant(
            code='cash-difference-foreign', email='cash-difference-foreign@example.com',
            trade_name='Foreign cash', legal_name='Foreign cash Ltda',
        )
        foreign = APIClient()
        foreign.force_authenticate(foreign_owner)
        foreign.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)
        foreign_denied = foreign.post(
            f'/api/v1/cash-sessions/{session.pk}/address-difference/',
            {'justification': 'Tentativa de outro tenant.'}, format='json',
        )
        self.assertEqual(foreign_denied.status_code, 403)
        self.assertFalse(CashDiscrepancyResolution.objects.filter(cash_session=session).exists())

    def test_non_owner_administrator_uses_the_selected_branch_permissions(self):
        administrator = User.objects.create_user(
            email='attention-administrator@example.com', password='password-123',
        )
        profile = AccessProfile.objects.get(company=self.company, name='Administrador')
        company_access = UserCompanyAccess(
            user=administrator, company=self.company, access_profile=profile,
        )
        company_access.save(enforce_saas_limit=False)
        UserBranchAccess.objects.create(
            user=administrator, branch=self.branch, access_profile=profile,
        )
        client = APIClient()
        client.force_authenticate(administrator)
        client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

        response = client.get('/api/v1/operational-attention/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('inventory', response.data['available_categories'])

    def test_access_is_limited_to_the_selected_tenant_and_branch_permissions(self):
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save(update_fields=('is_superuser', 'is_staff'))
        owner_access = self.client.get('/api/v1/operational-attention/')
        self.assertEqual(owner_access.status_code, 200, owner_access.data)
        same_tenant_other_branch = self.client.get(
            '/api/v1/operational-attention/', HTTP_X_BRANCH_ID=str(self.other_branch.pk),
        )
        self.assertEqual(same_tenant_other_branch.status_code, 403)
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
