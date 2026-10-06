from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attendance.services import open_table_attendance
from apps.base.exceptions import DomainValidationError
from apps.cash.models import CashRegister, CashSession
from apps.commands.models import Table
from apps.companies.features import branch_feature_states
from apps.companies.serializers import BranchSettingsSerializer
from apps.companies.services import create_company_with_matrix
from apps.pos.models import POSDevice
from apps.pos.services import assert_branch_device_limit, modules_for, pos_enabled
from apps.saas.models import Capability, Plan, PlanEntitlement, PlanVersion, Subscription
from apps.saas.permissions import enforce_saas_request
from apps.saas.services import (
    ensure_capability_catalog,
    get_entitled_features,
    map_existing_company,
    resolve_effective_status,
)


class CapabilityResolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='capability-resolution@example.com', password='password-123',
        )
        self.company = create_company_with_matrix(
            creator=self.user,
            trade_name='Capability Resolution',
            legal_name='Capability Resolution Ltda',
            enforce_saas_limits=False,
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.branch.settings.uses_tables = True
        self.branch.settings.save(update_fields=('uses_tables', 'updated_at'))

    def _plan(self, code, *, tables, pos=True, devices=1, products=False, features=()):
        capabilities = ensure_capability_catalog()
        version = PlanVersion.objects.create(
            plan=Plan.objects.create(code=code, name=code),
            version=1,
            price=Decimal('10.00'),
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['core.enabled'], unlimited=True,
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['users.max'], limit_value=2,
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['branches.max'], limit_value=1,
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['pos.enabled'],
            enabled=pos, unlimited=pos,
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['pos.devices.max'],
            enabled=pos, limit_value=devices if pos else None,
        )
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities['feature.tables'],
            enabled=tables,
            unlimited=tables,
        )
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities['feature.products'],
            enabled=products,
            unlimited=products,
        )
        for feature in set(features) - {'tables', 'products'}:
            PlanEntitlement.objects.create(
                plan_version=version,
                capability=capabilities[f'feature.{feature}'],
                unlimited=True,
            )
        return version

    def _superuser_client(self):
        superuser = User.objects.create_superuser(
            email='capability-superuser@example.com', password='password-123',
        )
        client = APIClient()
        client.force_authenticate(superuser)
        client.credentials(HTTP_X_BRANCH_ID=str(self.branch.pk))
        return client

    def test_company_without_subscription_has_no_features_and_cannot_operate(self):
        self.assertEqual(get_entitled_features(self.company), set())
        self.assertFalse(resolve_effective_status(self.company)['can_operate'])

    def test_expired_subscription_cannot_operate(self):
        subscription, _ = map_existing_company(
            company=self.company,
            plan_version=self._plan('expired', tables=True),
            billing_mode=Subscription.BillingMode.PAID,
        )
        subscription.current_period_start = timezone.now() - timedelta(days=2)
        subscription.current_period_end = timezone.now() - timedelta(days=1)
        subscription.save(
            update_fields=('current_period_start', 'current_period_end', 'updated_at'),
        )

        self.assertFalse(resolve_effective_status(self.company)['can_operate'])
        self.assertEqual(get_entitled_features(self.company), set())

    def test_tables_off_blocks_service_and_pos_module_payload(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('tables-off', tables=False),
            billing_mode=Subscription.BillingMode.PAID,
        )
        table = Table.objects.create(branch=self.branch, name='Mesa bloqueada')
        device = POSDevice.objects.create(
            branch=self.branch, name='POS bloqueado', status=POSDevice.Status.ACTIVE,
        )

        self.assertFalse(branch_feature_states(self.branch)['tables']['plan_allowed'])
        self.assertNotIn('feature.tables', get_entitled_features(self.company))
        self.assertFalse(BranchSettingsSerializer(self.branch.settings).data['feature_flags']['tables'])
        self.assertFalse(modules_for(
            self.user, device, permission_codes={'tables.view'},
        )[1]['tables']['enabled'])
        with self.assertRaises(PermissionDenied):
            open_table_attendance(
                branch=self.branch,
                table_id=table.pk,
                user=self.user,
                idempotency_key=uuid4(),
            )

    def test_tables_on_allows_service_and_pos_module_payload(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('tables-on', tables=True),
            billing_mode=Subscription.BillingMode.PAID,
        )
        table = Table.objects.create(branch=self.branch, name='Mesa liberada')
        device = POSDevice.objects.create(
            branch=self.branch, name='POS liberado', status=POSDevice.Status.ACTIVE,
        )

        self.assertTrue(branch_feature_states(self.branch)['tables']['enabled'])
        self.assertIn('feature.tables', get_entitled_features(self.company))
        self.assertTrue(BranchSettingsSerializer(self.branch.settings).data['feature_flags']['tables'])
        self.assertTrue(modules_for(
            self.user, device, permission_codes={'tables.view'},
        )[1]['tables']['enabled'])
        attendance, replayed = open_table_attendance(
            branch=self.branch,
            table_id=table.pk,
            user=self.user,
            idempotency_key=uuid4(),
        )
        self.assertFalse(replayed)
        self.assertEqual(attendance.table_id, table.pk)

    def test_pos_entitlement_and_device_limit_are_enforced(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('pos-disabled', tables=True, pos=False),
            billing_mode=Subscription.BillingMode.PAID,
        )
        with self.assertRaises(DomainValidationError) as context:
            pos_enabled(self.company)
        self.assertEqual(context.exception.payload['code'], 'pos_not_entitled')

        second_company = create_company_with_matrix(
            creator=self.user,
            trade_name='Device Limit',
            legal_name='Device Limit Ltda',
            enforce_saas_limits=False,
        )
        second_branch = second_company.branches.get(is_matrix=True)
        map_existing_company(
            company=second_company,
            plan_version=self._plan('device-limit', tables=True, devices=1),
            billing_mode=Subscription.BillingMode.PAID,
        )
        POSDevice.objects.create(
            branch=second_branch, name='Primeiro POS', status=POSDevice.Status.ACTIVE,
        )
        with self.assertRaises(DomainValidationError) as context:
            assert_branch_device_limit(second_branch)
        self.assertEqual(context.exception.payload['code'], 'pos_device_limit_reached')

    def test_commercial_endpoints_require_their_explicit_capability(self):
        version = self._plan('products-disabled', tables=True)
        map_existing_company(
            company=self.company,
            plan_version=version,
            billing_mode=Subscription.BillingMode.PAID,
        )
        request = SimpleNamespace(
            path='/api/v1/products/',
            headers={'X-Branch-ID': str(self.branch.pk)},
            query_params={},
            data={},
            method='GET',
        )
        view = SimpleNamespace(basename='product')

        with self.assertRaises(PermissionDenied):
            enforce_saas_request(request, self.user, view)

        second_company = create_company_with_matrix(
            creator=self.user,
            trade_name='Products Enabled',
            legal_name='Products Enabled Ltda',
            enforce_saas_limits=False,
        )
        second_branch = second_company.branches.get(is_matrix=True)
        map_existing_company(
            company=second_company,
            plan_version=self._plan('products-enabled', tables=True, products=True),
            billing_mode=Subscription.BillingMode.PAID,
        )
        request.headers['X-Branch-ID'] = str(second_branch.pk)
        enforce_saas_request(request, self.user, view)

    def test_disabled_commercial_capabilities_block_direct_api_for_superuser(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('commercial-api-disabled', tables=True),
            billing_mode=Subscription.BillingMode.PAID,
        )
        client = self._superuser_client()

        for path in ('/api/v1/products/', '/api/v1/payment-methods/', '/api/v1/audit-logs/'):
            response = client.get(path)
            self.assertEqual(response.status_code, 403, (path, response.data))

    def test_report_source_capabilities_block_direct_api(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'report-source-disabled',
                tables=False,
                features=('reports', 'commands'),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        client = self._superuser_client()

        for path in (
            '/api/v1/reports/purchases/',
            '/api/v1/reports/inventory-movements/',
            '/api/v1/reports/commands/',
            '/api/v1/reports/purchase-options/?scope=purchases',
            '/api/v1/reports/purchase-options/?scope=suppliers',
            '/api/v1/reports/purchase-options/?scope=payables',
            '/api/v1/reports/commercial-options/?scope=promotions',
            '/api/v1/reports/commercial-options/?scope=modifiers',
            '/api/v1/reports/commercial-options/?scope=customers',
        ):
            response = client.get(path)
            self.assertEqual(response.status_code, 403, (path, response.data))

    def test_reports_options_hide_disabled_module_filters(self):
        register = CashRegister.objects.create(branch=self.branch, name='Caixa bloqueado')
        CashSession.objects.create(
            cash_register=register,
            branch=self.branch,
            opened_by=self.user,
            opened_at=timezone.now(),
            opening_amount=Decimal('0.00'),
        )
        map_existing_company(
            company=self.company,
            plan_version=self._plan('report-options-disabled', tables=False, features=('reports',)),
            billing_mode=Subscription.BillingMode.PAID,
        )

        response = self._superuser_client().get('/api/v1/reports/options/')

        self.assertEqual(response.status_code, 200, response.data)
        for key in (
            'products', 'categories', 'payment_methods', 'cash_registers', 'cash_sessions',
            'movement_types', 'withdrawal_categories', 'user_types',
        ):
            self.assertEqual(response.data[key], [], key)

    def test_dashboard_omits_disabled_module_widgets(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('dashboard-modules-disabled', tables=False, features=('reports',)),
            billing_mode=Subscription.BillingMode.PAID,
        )

        response = self._superuser_client().get('/api/v1/dashboard/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('consumptions', response.data)
        self.assertNotIn('withdrawals', response.data)
        self.assertNotIn('current_cash', response.data)
        self.assertNotIn('inventory', response.data)

    def test_dashboard_keeps_enabled_module_widgets(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'dashboard-modules-enabled',
                tables=False,
                features=('reports', 'cash_register', 'consumption', 'inventory'),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )

        response = self._superuser_client().get('/api/v1/dashboard/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('consumptions', response.data)
        self.assertIn('current_cash', response.data)
        self.assertIn('inventory', response.data)

    def test_payables_options_require_financial_capability(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'payables-without-financial',
                tables=False,
                features=('reports', 'purchases'),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )

        response = self._superuser_client().get(
            '/api/v1/reports/purchase-options/?scope=payables',
        )

        self.assertEqual(response.status_code, 403, response.data)

    def test_payables_options_require_purchases_capability(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'payables-without-purchases',
                tables=False,
                features=('reports', 'financial'),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )

        response = self._superuser_client().get(
            '/api/v1/reports/purchase-options/?scope=payables',
        )

        self.assertEqual(response.status_code, 403, response.data)

    def test_payables_options_allow_purchases_and_financial(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'payables-enabled',
                tables=False,
                features=('reports', 'purchases', 'financial'),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )

        now = timezone.now()
        response = self._superuser_client().get('/api/v1/reports/purchase-options/', {
            'scope': 'payables',
            'start_datetime': (now - timedelta(days=1)).isoformat(),
            'end_datetime': now.isoformat(),
        })

        self.assertEqual(response.status_code, 200, response.data)

    def test_commercial_options_hide_catalog_without_products_capability(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'promotions-without-products',
                tables=False,
                features=('reports', 'promotions'),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )

        now = timezone.now()
        response = self._superuser_client().get('/api/v1/reports/commercial-options/', {
            'scope': 'promotions',
            'start_datetime': (now - timedelta(days=1)).isoformat(),
            'end_datetime': now.isoformat(),
        })

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['products'], [])
        self.assertEqual(response.data['categories'], [])

    def test_pos_modules_and_device_administration_respect_capabilities(self):
        self.branch.settings.uses_counter = True
        self.branch.settings.uses_commands = True
        self.branch.settings.uses_cash_register = True
        self.branch.settings.save(update_fields=(
            'uses_counter', 'uses_commands', 'uses_cash_register', 'updated_at',
        ))
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'pos-modules-disabled',
                tables=True,
                pos=False,
                features=('cash_register',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        device = POSDevice.objects.create(
            branch=self.branch, name='POS module gate', status=POSDevice.Status.ACTIVE,
        )

        with self.assertRaises(DomainValidationError):
            modules_for(
                self.user,
                device,
                permission_codes={'sales.create', 'commands.view'},
            )
        response = self._superuser_client().get(
            f'/api/v1/pos/admin/devices/?company={self.company.pk}',
        )
        self.assertEqual(response.status_code, 403, response.data)

    def test_counter_and_commands_are_hidden_when_their_features_are_disabled(self):
        self.branch.settings.uses_counter = True
        self.branch.settings.uses_commands = True
        self.branch.settings.uses_cash_register = True
        self.branch.settings.save(update_fields=(
            'uses_counter', 'uses_commands', 'uses_cash_register', 'updated_at',
        ))
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'pos-feature-modules-disabled',
                tables=True,
                features=('cash_register',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        device = POSDevice.objects.create(
            branch=self.branch, name='POS feature modules', status=POSDevice.Status.ACTIVE,
        )

        modules = modules_for(
            self.user,
            device,
            permission_codes={'sales.create', 'commands.view'},
        )[1]
        self.assertFalse(modules['quick_sale']['enabled'])
        self.assertFalse(modules['commands']['enabled'])


class CapabilityCatalogTests(TestCase):
    def test_catalog_contains_all_commercial_module_capabilities(self):
        ensure_capability_catalog()

        codes = set(Capability.objects.filter(code__startswith='feature.').values_list('code', flat=True))

        self.assertTrue({
            'feature.products', 'feature.inventory', 'feature.purchases',
            'feature.suppliers', 'feature.customers', 'feature.promotions',
            'feature.reports', 'feature.audit', 'feature.financial',
        }.issubset(codes))
