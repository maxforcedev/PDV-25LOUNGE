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
    resolve_capability_dependencies,
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
        features = set(features)
        if tables:
            features.add('tables')
        if products:
            features.add('products')
        features = {
            capability_code.removeprefix('feature.')
            for capability_code in resolve_capability_dependencies(
                {f'feature.{feature}' for feature in features}
            )
        }
        tables = 'tables' in features
        products = 'products' in features
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
        for feature in features - {'tables', 'products'}:
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
        self.branch.settings.uses_commands = True
        self.branch.settings.save(update_fields=('uses_commands', 'updated_at'))
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

    def test_branch_settings_rejects_tables_or_consumption_without_commands(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'branch-settings-dependencies',
                tables=True,
                features=('consumption',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.branch.settings.uses_tables = False
        self.branch.settings.uses_consumption = False
        self.branch.settings.uses_commands = False
        self.branch.settings.save(update_fields=(
            'uses_tables', 'uses_consumption', 'uses_commands', 'updated_at',
        ))

        tables = BranchSettingsSerializer(
            self.branch.settings,
            data={'uses_commands': False, 'uses_tables': True},
            partial=True,
        )
        consumption = BranchSettingsSerializer(
            self.branch.settings,
            data={'uses_commands': False, 'uses_consumption': True},
            partial=True,
        )

        self.assertFalse(tables.is_valid())
        self.assertEqual(tables.errors['uses_tables'][0], 'Mesas requer Comandas habilitado nesta filial.')
        self.assertFalse(consumption.is_valid())
        self.assertEqual(consumption.errors['uses_consumption'][0], 'Consumação requer Comandas habilitado nesta filial.')

    def test_branch_settings_rejects_disabling_commands_with_dependents(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'branch-settings-disable-commands',
                tables=True,
                features=('consumption',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.branch.settings.uses_tables = True
        self.branch.settings.uses_consumption = True
        self.branch.settings.uses_commands = True
        self.branch.settings.save(update_fields=(
            'uses_tables', 'uses_consumption', 'uses_commands', 'updated_at',
        ))

        serializer = BranchSettingsSerializer(
            self.branch.settings, data={'uses_commands': False}, partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors['uses_commands'][0],
            'Não é possível desabilitar Comandas enquanto Mesas ou Consumação estiverem habilitadas.',
        )

    def test_downgraded_tables_flag_does_not_block_disabling_commands(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'downgraded-tables', tables=False, features=('commands',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.branch.settings.uses_tables = True
        self.branch.settings.uses_commands = True
        self.branch.settings.save(update_fields=('uses_tables', 'uses_commands', 'updated_at'))

        serializer = BranchSettingsSerializer(
            self.branch.settings, data={'uses_commands': False}, partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.branch.settings.refresh_from_db()
        self.assertTrue(self.branch.settings.uses_tables)
        self.assertFalse(self.branch.settings.uses_commands)
        self.assertFalse(branch_feature_states(self.branch)['tables']['enabled'])

        regularize = BranchSettingsSerializer(
            self.branch.settings, data={'uses_tables': False}, partial=True,
        )
        self.assertTrue(regularize.is_valid(), regularize.errors)
        regularize.save()
        self.branch.settings.refresh_from_db()
        self.assertFalse(self.branch.settings.uses_tables)
        self.assertFalse(branch_feature_states(self.branch)['tables']['enabled'])

    def test_downgraded_consumption_flag_does_not_block_disabling_commands(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'downgraded-consumption', tables=False, features=('commands',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.branch.settings.uses_consumption = True
        self.branch.settings.uses_commands = True
        self.branch.settings.save(update_fields=('uses_consumption', 'uses_commands', 'updated_at'))

        serializer = BranchSettingsSerializer(
            self.branch.settings, data={'uses_commands': False}, partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.branch.settings.refresh_from_db()
        self.assertTrue(self.branch.settings.uses_consumption)
        self.assertFalse(self.branch.settings.uses_commands)
        self.assertFalse(branch_feature_states(self.branch)['consumption']['enabled'])

    def test_disabled_plan_capability_rejects_reenabling_legacy_local_flag(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'tables-plan-disabled', tables=False, features=('commands',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.branch.settings.uses_commands = True
        self.branch.settings.save(update_fields=('uses_commands', 'updated_at'))

        serializer = BranchSettingsSerializer(
            self.branch.settings, data={'uses_tables': True}, partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('uses_tables', serializer.errors)
        self.assertFalse(branch_feature_states(self.branch)['tables']['enabled'])

    def test_pos_branch_switch_uses_the_pos_entitlement(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('pos-branch-switch-enabled', tables=False, pos=True),
            billing_mode=Subscription.BillingMode.PAID,
        )

        serializer = BranchSettingsSerializer(
            self.branch.settings, data={'uses_pos': True}, partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_pos_branch_switch_rejects_an_unentitled_enable(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('pos-branch-switch-disabled', tables=False, pos=False),
            billing_mode=Subscription.BillingMode.PAID,
        )

        serializer = BranchSettingsSerializer(
            self.branch.settings, data={'uses_pos': True}, partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('uses_pos', serializer.errors)

    def test_off_plan_legacy_switch_does_not_block_an_unrelated_patch(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('legacy-off-plan-patch', tables=False, products=True),
            billing_mode=Subscription.BillingMode.PAID,
        )

        serializer = BranchSettingsSerializer(
            self.branch.settings, data={'uses_products': True}, partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_off_plan_legacy_switch_can_be_regularized_but_not_reenabled(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('legacy-off-plan-regularization', tables=False, products=True),
            billing_mode=Subscription.BillingMode.PAID,
        )

        regularize = BranchSettingsSerializer(
            self.branch.settings, data={'uses_inventory': False}, partial=True,
        )
        reenabling = BranchSettingsSerializer(
            self.branch.settings, data={'uses_inventory': True}, partial=True,
        )

        self.assertTrue(regularize.is_valid(), regularize.errors)
        regularize.save()
        self.branch.settings.refresh_from_db()
        self.assertFalse(self.branch.settings.uses_inventory)
        self.assertFalse(reenabling.is_valid())
        self.assertIn('uses_inventory', reenabling.errors)

    def test_suspended_tenant_keeps_plan_allowed_but_disables_the_feature(self):
        subscription, _ = map_existing_company(
            company=self.company,
            plan_version=self._plan('suspended-plan-allowed', tables=False, products=True),
            billing_mode=Subscription.BillingMode.PAID,
        )
        subscription.status = Subscription.Status.SUSPENDED_FINANCIAL
        subscription.save(update_fields=('status', 'updated_at'))

        state = branch_feature_states(self.branch)['products']

        self.assertTrue(state['plan_allowed'])
        self.assertFalse(state['enabled'])

    def test_inventory_requires_products_when_both_features_are_entitled(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'inventory-branch-dependency', tables=False, features=('inventory',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.branch.settings.uses_products = False
        self.branch.settings.save(update_fields=('uses_products', 'updated_at'))

        serializer = BranchSettingsSerializer(
            self.branch.settings,
            data={'uses_inventory': True, 'uses_products': False},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('uses_inventory', serializer.errors)

    def test_off_plan_internal_settings_are_not_persisted(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('off-plan-internal-settings', tables=False, features=('reports',)),
            billing_mode=Subscription.BillingMode.PAID,
        )
        serializer = BranchSettingsSerializer(
            self.branch.settings,
            data={
                'allow_negative_stock': True,
                'service_fee_rate': '9.00',
                'command_consumption_limit': '15.00',
                'table_consumption_limit': '15.00',
            },
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.branch.settings.refresh_from_db()
        self.assertFalse(self.branch.settings.allow_negative_stock)
        self.assertEqual(self.branch.settings.service_fee_rate, Decimal('0.00'))
        self.assertIsNone(self.branch.settings.command_consumption_limit)
        self.assertIsNone(self.branch.settings.table_consumption_limit)
        self.assertFalse(branch_feature_states(self.branch)['tables']['enabled'])

    def test_branch_feature_states_fail_closed_for_legacy_local_dependencies(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan(
                'branch-state-dependencies',
                tables=True,
                features=('consumption', 'counter'),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.branch.settings.uses_cash_register = True
        self.branch.settings.uses_commands = False
        self.branch.settings.uses_tables = True
        self.branch.settings.uses_consumption = True
        self.branch.settings.save(update_fields=(
            'uses_cash_register', 'uses_commands', 'uses_tables', 'uses_consumption', 'updated_at',
        ))

        states = branch_feature_states(self.branch)
        self.assertFalse(states['tables']['enabled'])
        self.assertFalse(states['consumption']['enabled'])

        self.branch.settings.uses_cash_register = False
        self.branch.settings.uses_commands = True
        self.branch.settings.uses_counter = True
        self.branch.settings.save(update_fields=(
            'uses_cash_register', 'uses_commands', 'uses_counter', 'updated_at',
        ))
        states = branch_feature_states(self.branch)
        self.assertFalse(states['counter']['enabled'])
        self.assertFalse(states['commands']['enabled'])
        self.assertFalse(states['tables']['enabled'])
        self.assertFalse(states['consumption']['enabled'])

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
        version = self._plan('products-disabled', tables=False)
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
            plan_version=self._plan('products-enabled', tables=False, products=True),
            billing_mode=Subscription.BillingMode.PAID,
        )
        request.headers['X-Branch-ID'] = str(second_branch.pk)
        enforce_saas_request(request, self.user, view)

        second_branch.settings.uses_products = False
        second_branch.settings.save(update_fields=('uses_products', 'updated_at'))
        with self.assertRaises(PermissionDenied):
            enforce_saas_request(request, self.user, view)

    def test_disabled_commercial_capabilities_block_direct_api_for_superuser(self):
        map_existing_company(
            company=self.company,
            plan_version=self._plan('commercial-api-disabled', tables=False),
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
                features=('reports',),
            ),
            billing_mode=Subscription.BillingMode.PAID,
        )
        client = self._superuser_client()

        now = timezone.now()
        for path, query_params in (
            ('/api/v1/reports/purchases/', {}),
            ('/api/v1/reports/inventory-movements/', {}),
            ('/api/v1/reports/commands/', {}),
            ('/api/v1/reports/purchase-options/', {'scope': 'purchases'}),
            ('/api/v1/reports/purchase-options/', {'scope': 'suppliers'}),
            ('/api/v1/reports/purchase-options/', {'scope': 'payables'}),
            ('/api/v1/reports/commercial-options/', {'scope': 'promotions'}),
            ('/api/v1/reports/commercial-options/', {'scope': 'modifiers'}),
            ('/api/v1/reports/commercial-options/', {'scope': 'customers'}),
        ):
            response = client.get(path, {
                **query_params,
                'start_datetime': (now - timedelta(days=1)).isoformat(),
                'end_datetime': now.isoformat(),
            })
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
        self.branch.settings.uses_commands = True
        self.branch.settings.save(update_fields=('uses_commands', 'updated_at'))
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

    def test_commercial_options_resolve_product_dependency_for_promotions(self):
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
        self.assertEqual(response.data['code'], 'pos_not_entitled')

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
                tables=False,
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
