from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.attendance.services import open_table_attendance
from apps.base.exceptions import DomainValidationError
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
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.branch.settings.uses_tables = True
        self.branch.settings.save(update_fields=('uses_tables', 'updated_at'))

    def _plan(self, code, *, tables, pos=True, devices=1, products=False):
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
        return version

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
        )
        second_branch = second_company.branches.get(is_matrix=True)
        map_existing_company(
            company=second_company,
            plan_version=self._plan('products-enabled', tables=True, products=True),
            billing_mode=Subscription.BillingMode.PAID,
        )
        request.headers['X-Branch-ID'] = str(second_branch.pk)
        enforce_saas_request(request, self.user, view)


class CapabilityCatalogTests(TestCase):
    def test_catalog_contains_all_commercial_module_capabilities(self):
        ensure_capability_catalog()

        codes = set(Capability.objects.filter(code__startswith='feature.').values_list('code', flat=True))

        self.assertTrue({
            'feature.products', 'feature.inventory', 'feature.purchases',
            'feature.suppliers', 'feature.customers', 'feature.promotions',
            'feature.reports', 'feature.audit', 'feature.financial',
        }.issubset(codes))
