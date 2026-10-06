from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.base.exceptions import DomainValidationError
from apps.base.models import AuditLog
from apps.companies.models import AccessProfile, Company, UserCompanyAccess
from apps.companies.selectors import accessible_companies
from apps.companies.services import create_branch_with_access, create_company_with_matrix
from apps.pos.models import POSDevice
from apps.pos.services import assert_branch_device_limit, pos_enabled
from apps.saas.models import (
    BillingRecord,
    Capability,
    CycleUsage,
    GlobalSaaSSettings,
    Plan,
    PlanEntitlement,
    PlanVersion,
    PlatformUserAccess,
    ProvisioningOperation,
    Subscription,
    SupportSession,
    TenantSaaSState,
)
from apps.saas.services import (
    add_months,
    apply_user_limit_states,
    create_support_session,
    ensure_capability_catalog,
    get_entitled_features,
    map_existing_company,
    process_subscription_lifecycle,
    provision_saas_tenant,
    record_manual_payment,
    resolve_effective_status,
    set_admin_suspension,
    validate_plan_version_complete,
)
from apps.saas.permissions import enforce_saas_request


PASSWORD = 'Strong-owner-password-123!'


def create_user(email):
    return User.objects.create_user(email=email, password=PASSWORD)


def create_plan(code='basic', *, trial_days=0, price='99.00', public=True, users=3, branches=2,
                pos_enabled=True, pos_devices=1, features=()):
    capabilities = ensure_capability_catalog()
    plan = Plan.objects.create(code=code, name=code.title())
    version = PlanVersion.objects.create(
        plan=plan,
        version=1,
        price=Decimal(price),
        trial_days=trial_days,
        is_public=public,
    )
    PlanEntitlement.objects.create(
        plan_version=version,
        capability=capabilities['core.enabled'],
        enabled=True,
        unlimited=True,
    )
    PlanEntitlement.objects.create(
        plan_version=version,
        capability=capabilities['users.max'],
        limit_value=users,
    )
    PlanEntitlement.objects.create(
        plan_version=version,
        capability=capabilities['branches.max'],
        limit_value=branches,
    )
    PlanEntitlement.objects.create(
        plan_version=version,
        capability=capabilities['pos.enabled'],
        enabled=pos_enabled,
        unlimited=pos_enabled,
    )
    PlanEntitlement.objects.create(
        plan_version=version,
        capability=capabilities['pos.devices.max'],
        enabled=pos_enabled,
        limit_value=pos_devices if pos_enabled else None,
    )
    for feature in features:
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities[f'feature.{feature}'],
            unlimited=True,
        )
    return version


def create_tenant(
    name='Tenant', *, plan_version=None, billing_mode=Subscription.BillingMode.PAID,
    initial_subscription_mode=Subscription.Status.ACTIVE,
):
    owner = create_user(f'{name.lower().replace(" ", "-")}@example.com')
    company = create_company_with_matrix(
        creator=owner,
        trade_name=name,
        legal_name=f'{name} Legal',
    )
    subscription = None
    if plan_version:
        subscription, _ = map_existing_company(
            company=company,
            plan_version=plan_version,
            billing_mode=billing_mode,
            initial_subscription_mode=initial_subscription_mode,
        )
    return owner, company, subscription


class PlatformAuthorizationTests(TestCase):
    def test_platform_and_tenant_authorizations_are_explicit_and_separate(self):
        platform_user = create_user('platform-only@example.com')
        call_command('bootstrap_platform_admin', email=platform_user.email, stdout=StringIO())
        tenant_user, _, _ = create_tenant('Tenant Auth')

        client = APIClient()
        response = client.post(
            reverse('platform-login'),
            {'email': platform_user.email, 'password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(platform_user.company_accesses.exists())

        client = APIClient()
        response = client.post(
            reverse('accounts:login'),
            {'email': platform_user.email, 'password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

        client = APIClient()
        response = client.post(
            reverse('platform-login'),
            {'email': tenant_user.email, 'password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PlatformUserAccess.objects.filter(user=tenant_user).exists())

    def test_bootstrap_is_idempotent_and_does_not_grant_django_superuser(self):
        user = create_user('bootstrap@example.com')
        call_command('bootstrap_platform_admin', email=user.email, stdout=StringIO())
        audit_count = AuditLog.objects.filter(action='platform.admin.bootstrap').count()
        call_command('bootstrap_platform_admin', email=user.email, stdout=StringIO())

        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertEqual(PlatformUserAccess.objects.filter(user=user).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='platform.admin.bootstrap').count(), audit_count)


class PlanHistoryTests(TestCase):
    def test_plan_can_explicitly_disable_pos_and_still_be_complete(self):
        version = create_plan(code='pos-disabled', pos_enabled=False)

        validated = validate_plan_version_complete(version)

        self.assertEqual(validated.pk, version.pk)
        self.assertFalse(version.entitlements.get(capability__code='pos.enabled').enabled)
        self.assertFalse(version.entitlements.get(capability__code='pos.devices.max').enabled)

    def test_plan_missing_required_pos_entitlement_is_rejected(self):
        version = create_plan(code='missing-pos-entitlement')
        PlanEntitlement.objects.filter(
            plan_version=version, capability__code='pos.devices.max',
        ).delete()

        with self.assertRaises(ValidationError) as context:
            validate_plan_version_complete(version)

        self.assertIn('pos.devices.max', str(context.exception))

    def test_pos_entitlement_and_device_limit_are_enforced(self):
        enabled = create_plan(code='pos-enabled', pos_devices=1)
        _, company, _ = create_tenant('POS enabled', plan_version=enabled)
        branch = company.branches.get(is_matrix=True)
        self.assertTrue(pos_enabled(company))
        assert_branch_device_limit(branch)
        POSDevice.objects.create(branch=branch, name='First POS', status=POSDevice.Status.ACTIVE)
        with self.assertRaises(DomainValidationError) as context:
            assert_branch_device_limit(branch)
        self.assertEqual(context.exception.payload['code'], 'pos_device_limit_reached')

        disabled = create_plan(code='pos-disabled-entitlement', pos_enabled=False)
        _, disabled_company, _ = create_tenant('POS disabled', plan_version=disabled)
        with self.assertRaises(DomainValidationError) as context:
            pos_enabled(disabled_company)
        self.assertEqual(context.exception.payload['code'], 'pos_not_entitled')

    def test_used_plan_version_and_entitlements_are_immutable(self):
        version = create_plan()
        _, _, subscription = create_tenant('Immutable', plan_version=version)
        self.assertIsNotNone(subscription)

        version.price = Decimal('120.00')
        with self.assertRaises(ValidationError):
            version.save()
        entitlement = version.entitlements.get(capability__code='users.max')
        entitlement.limit_value = 10
        with self.assertRaises(ValidationError):
            entitlement.save()
        with self.assertRaises(ValidationError):
            version.delete()
        with self.assertRaises(ValidationError):
            version.plan.delete()


class ProvisioningTests(TestCase):
    def test_manual_provisioning_defaults_to_active_and_is_idempotent(self):
        version = create_plan(trial_days=7)
        manual_owner = create_user('manual-owner@example.com')
        manual, created = provision_saas_tenant(
            source=ProvisioningOperation.Source.PLATFORM_MANUAL,
            idempotency_key='manual-1',
            plan_version=version,
            company_data={'trade_name': 'Manual', 'legal_name': 'Manual Legal'},
            owner_email=manual_owner.email,
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.assertTrue(created)
        retry, created = provision_saas_tenant(
            source=ProvisioningOperation.Source.PLATFORM_MANUAL,
            idempotency_key='manual-1',
            plan_version=version,
            company_data={'trade_name': 'Manual', 'legal_name': 'Manual Legal'},
            owner_email=manual_owner.email,
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.assertFalse(created)
        self.assertEqual(retry.pk, manual.pk)

        public, _ = provision_saas_tenant(
            source=ProvisioningOperation.Source.PUBLIC_SIGNUP,
            idempotency_key='public-1',
            plan_version=version,
            company_data={'trade_name': 'Public', 'legal_name': 'Public Legal'},
            owner_email='public-owner@example.com',
            owner_password=PASSWORD,
        )
        for operation in (manual, public):
            self.assertEqual(operation.company.branches.count(), 1)
            self.assertTrue(operation.company.user_accesses.get(user=operation.user).is_owner)
            self.assertTrue(CycleUsage.objects.filter(subscription=operation.subscription).exists())
        self.assertEqual(manual.user_id, manual_owner.pk)
        self.assertEqual(manual.subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNone(manual.subscription.trial_started_at)
        self.assertEqual(public.subscription.status, Subscription.Status.TRIALING)

    def test_global_manual_approval_policy_does_not_deactivate_company(self):
        settings = GlobalSaaSSettings.objects.create(auto_approve_signups=False)
        version = create_plan(code='approval')
        operation, _ = provision_saas_tenant(
            source=ProvisioningOperation.Source.PUBLIC_SIGNUP,
            idempotency_key='pending-1',
            plan_version=version,
            company_data={'trade_name': 'Pending', 'legal_name': 'Pending Legal'},
            owner_email='pending@example.com',
            owner_password=PASSWORD,
        )
        self.assertFalse(settings.auto_approve_signups)
        self.assertEqual(operation.company.status, 'active')
        self.assertTrue(operation.company.branches.filter(status='active').exists())
        self.assertEqual(operation.company.saas_state.approval_status, TenantSaaSState.ApprovalStatus.PENDING)
        self.assertEqual(resolve_effective_status(operation.company)['status'], 'PENDING_APPROVAL')


class LifecycleTests(TestCase):
    def setUp(self):
        self.settings = GlobalSaaSSettings.objects.create(past_due_days=2, restricted_after_days=4)
        self.version = create_plan()

    def test_paid_lifecycle_runtime_expiry_and_processing_are_deterministic(self):
        _, company, subscription = create_tenant('Paid Lifecycle', plan_version=self.version)
        now = timezone.now()
        subscription.current_period_start = now - timedelta(days=31)
        subscription.current_period_end = now - timedelta(days=1)
        subscription.save()

        effective = resolve_effective_status(company, at=now)
        self.assertEqual(effective['status'], Subscription.Status.PAST_DUE)
        self.assertFalse(effective['can_operate'])
        subscription, changed = process_subscription_lifecycle(subscription, at=now)
        self.assertTrue(changed)
        self.assertEqual(subscription.status, Subscription.Status.PAST_DUE)
        audit_count = AuditLog.objects.filter(action='saas.subscription.lifecycle').count()
        _, changed = process_subscription_lifecycle(subscription, at=now)
        self.assertFalse(changed)
        self.assertEqual(AuditLog.objects.filter(action='saas.subscription.lifecycle').count(), audit_count)

        restricted_at = subscription.current_period_end + timedelta(days=3)
        self.assertEqual(resolve_effective_status(company, at=restricted_at)['status'], Subscription.Status.RESTRICTED)
        suspended_at = subscription.current_period_end + timedelta(days=5)
        self.assertEqual(resolve_effective_status(company, at=suspended_at)['status'], Subscription.Status.SUSPENDED_FINANCIAL)

    def test_free_and_internal_cycles_advance_without_erasing_usage(self):
        for index, mode in enumerate((Subscription.BillingMode.FREE, Subscription.BillingMode.INTERNAL)):
            _, _, subscription = create_tenant(
                f'Automatic {index}', plan_version=self.version, billing_mode=mode
            )
            old_start = timezone.now() - timedelta(days=70)
            subscription.current_period_start = old_start
            subscription.current_period_end = add_months(old_start, 1)
            subscription.save()
            old_usage_ids = set(subscription.usage_history.values_list('pk', flat=True))
            subscription, _ = process_subscription_lifecycle(subscription, at=timezone.now())
            self.assertGreater(subscription.current_period_end, timezone.now())
            self.assertTrue(old_usage_ids.issubset(set(subscription.usage_history.values_list('pk', flat=True))))
            self.assertGreater(subscription.usage_history.count(), len(old_usage_ids))

    def test_trial_expiry_is_effective_before_cron(self):
        trial_version = create_plan(code='trial', trial_days=2)
        _, company, subscription = create_tenant(
            'Trial Runtime',
            plan_version=trial_version,
            initial_subscription_mode=Subscription.Status.TRIALING,
        )
        expired_at = subscription.trial_ends_at + timedelta(seconds=1)
        result = resolve_effective_status(company, at=expired_at)
        self.assertEqual(result['status'], Subscription.Status.TRIAL_EXPIRED)
        self.assertFalse(result['can_operate'])

    def test_period_end_immediately_blocks_every_billing_mode(self):
        now = timezone.now()
        for billing_mode in Subscription.BillingMode.values:
            _, company, subscription = create_tenant(
                f'Expired {billing_mode}', plan_version=self.version, billing_mode=billing_mode,
            )
            subscription.current_period_start = now - timedelta(days=31)
            subscription.current_period_end = now
            subscription.save()

            effective = resolve_effective_status(company, at=now)

            self.assertFalse(effective['can_operate'])
            self.assertEqual(effective['status'], Subscription.Status.PAST_DUE)


class BillingAndSuspensionTests(TestCase):
    def test_payment_is_idempotent_append_only_and_only_clears_financial_state(self):
        version = create_plan()
        actor = create_user('billing-actor@example.com')
        _, company, subscription = create_tenant('Billing', plan_version=version)
        now = timezone.now()
        subscription.status = Subscription.Status.SUSPENDED_FINANCIAL
        subscription.current_period_start = now - timedelta(days=30)
        subscription.current_period_end = now - timedelta(days=1)
        subscription.save()
        set_admin_suspension(company, actor, 'Security review', True)

        values = {
            'subscription': subscription,
            'actor': actor,
            'idempotency_key': 'payment-1',
            'amount': Decimal('99.00'),
            'paid_at': now,
            'payment_method': 'PIX',
            'competency_start': subscription.current_period_end,
            'competency_end': add_months(subscription.current_period_end, 1),
            'note': 'Manual confirmation',
        }
        record, created = record_manual_payment(**values)
        self.assertTrue(created)
        retry, created = record_manual_payment(**values)
        self.assertFalse(created)
        self.assertEqual(record.pk, retry.pk)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(resolve_effective_status(company)['status'], 'SUSPENDED_ADMIN')
        record.note = 'Changed'
        with self.assertRaises(ValidationError):
            record.save()
        with self.assertRaises(ValidationError):
            record.delete()
        with self.assertRaises(ValidationError):
            BillingRecord.objects.filter(pk=record.pk).update(note='Changed')


class ExistingCompanyMappingTests(TestCase):
    def test_mapping_command_requires_all_commercial_decisions_and_is_idempotent(self):
        version = create_plan()
        _, company, _ = create_tenant('Legacy')
        output = StringIO()
        call_command('map_existing_company_subscription', stdout=output)
        self.assertIn(f'{company.pk}\t{company.trade_name}', output.getvalue())
        with self.assertRaises(CommandError):
            call_command('map_existing_company_subscription', company_id=company.pk)

        options = {
            'company_id': company.pk,
            'plan_version_id': version.pk,
            'billing_mode': Subscription.BillingMode.FREE,
            'stdout': StringIO(),
        }
        call_command('map_existing_company_subscription', **options)
        call_command('map_existing_company_subscription', **options)
        subscription = company.subscriptions.get(is_current=True)
        self.assertEqual(subscription.plan_version, version)
        self.assertEqual(subscription.billing_mode, Subscription.BillingMode.FREE)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNone(subscription.trial_started_at)

    def test_mapping_trial_requires_explicit_mode_and_trial_capable_plan(self):
        version = create_plan(code='mapping-trial', trial_days=7)
        _, active_company, _ = create_tenant('Mapping Active')
        active, _ = map_existing_company(
            company=active_company,
            plan_version=version,
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.assertEqual(active.status, Subscription.Status.ACTIVE)
        self.assertIsNone(active.trial_started_at)

        _, trial_company, _ = create_tenant('Mapping Trial')
        trial, _ = map_existing_company(
            company=trial_company,
            plan_version=version,
            billing_mode=Subscription.BillingMode.PAID,
            initial_subscription_mode=Subscription.Status.TRIALING,
        )
        self.assertEqual(trial.status, Subscription.Status.TRIALING)
        self.assertIsNotNone(trial.trial_started_at)

        no_trial_version = create_plan(code='mapping-no-trial')
        _, no_trial_company, _ = create_tenant('Mapping No Trial')
        with self.assertRaises(ValidationError):
            map_existing_company(
                company=no_trial_company,
                plan_version=no_trial_version,
                billing_mode=Subscription.BillingMode.PAID,
                initial_subscription_mode=Subscription.Status.TRIALING,
            )


class OwnerAreaTests(TestCase):
    def test_owner_history_and_actions_are_tenant_isolated(self):
        version = create_plan()
        owner, company, _ = create_tenant('Owner Area', plan_version=version)
        outsider, other_company, _ = create_tenant('Other Area', plan_version=version)
        client = APIClient()
        client.force_authenticate(owner)
        response = client.get(reverse('saas-owner-subscription'), {'company': company.pk})
        self.assertEqual(response.status_code, 200, response.data)
        response = client.get(reverse('saas-owner-payments'), {'company': other_company.pk})
        self.assertEqual(response.status_code, 403)
        response = client.post(
            reverse('saas-owner-change-requests'),
            {
                'company': company.pk, 'requested_plan_version': version.pk,
                'reason': 'Need review', 'current_password': PASSWORD,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        response = client.post(
            reverse('saas-owner-cancel'),
            {
                'company': company.pk, 'reason': 'Closing business',
                'current_password': PASSWORD,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(company.subscriptions.get(is_current=True).cancel_at_period_end)
        self.assertNotEqual(owner.pk, outsider.pk)


class SupportSessionTests(TestCase):
    def setUp(self):
        self.version = create_plan()
        self.owner, self.company, _ = create_tenant('Support Target', plan_version=self.version)
        self.agent = create_user('support-agent@example.com')
        call_command('bootstrap_platform_admin', email=self.agent.email, stdout=StringIO())

    def test_support_requires_reason_and_reauthentication_and_never_creates_membership(self):
        with self.assertRaises(ValidationError):
            create_support_session(
                actor=self.agent, company=self.company,
                mode=SupportSession.Mode.READ_ONLY, reason='',
            )
        with self.assertRaises(ValidationError):
            create_support_session(
                actor=self.agent, company=self.company,
                mode=SupportSession.Mode.READ_WRITE, reason='Fix issue', current_password='wrong',
            )
        session = create_support_session(
            actor=self.agent,
            company=self.company,
            impersonated_user=self.owner,
            mode=SupportSession.Mode.READ_WRITE,
            reason='Reproduce reported issue',
            current_password=PASSWORD,
        )
        self.assertFalse(UserCompanyAccess.objects.filter(user=self.agent, company=self.company).exists())
        self.assertTrue(AuditLog.objects.filter(action='saas.support.start', object_id=str(session.pk)).exists())

    def test_read_only_and_expired_sessions_are_rejected(self):
        read_only = create_support_session(
            actor=self.agent,
            company=self.company,
            impersonated_user=self.owner,
            mode=SupportSession.Mode.READ_ONLY,
            reason='Inspect issue',
            current_password=PASSWORD,
        )
        client = APIClient()
        self.assertTrue(client.login(email=self.agent.email, password=PASSWORD))
        response = client.post(
            reverse('company-deactivate', args=[self.company.pk]),
            HTTP_X_SUPPORT_SESSION_ID=str(read_only.pk),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.company.status, 'active')

        from django.db import models
        models.QuerySet(model=SupportSession).filter(pk=read_only.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        response = client.get(
            reverse('company-list'),
            HTTP_X_SUPPORT_SESSION_ID=str(read_only.pk),
        )
        self.assertIn(response.status_code, (401, 403))


class EntitlementAndLimitTests(TestCase):
    def test_branch_limit_and_user_state_preserve_owner(self):
        version = create_plan(users=1, branches=1)
        owner, company, _ = create_tenant('Limited')
        profile = AccessProfile.objects.get(company=company, name='Administrador')
        extra_users = [create_user(f'extra-{index}@example.com') for index in range(2)]
        accesses = [
            UserCompanyAccess.objects.create(
                user=user, company=company, access_profile=profile
            )
            for user in extra_users
        ]
        map_existing_company(
            company=company, plan_version=version,
            billing_mode=Subscription.BillingMode.PAID,
        )
        with self.assertRaises(ValidationError):
            create_branch_with_access(creator=owner, company=company, name='Second')
        owner_access = UserCompanyAccess.objects.get(company=company, user=owner)
        self.assertEqual(owner_access.saas_status, UserCompanyAccess.SaaSStatus.ACTIVE)
        self.assertEqual(
            set(UserCompanyAccess.objects.filter(
                pk__in=[item.pk for item in accesses],
                saas_status=UserCompanyAccess.SaaSStatus.SUSPENDED_BY_PLAN_LIMIT,
            ).values_list('pk', flat=True)),
            {item.pk for item in accesses},
        )
        self.assertFalse(accessible_companies(extra_users[0]).filter(pk=company.pk).exists())

    def test_unlimited_entitlement_allows_growth(self):
        version = create_plan(code='unlimited', branches=1)
        entitlement = version.entitlements.get(capability__code='branches.max')
        entitlement.unlimited = True
        entitlement.limit_value = None
        entitlement.save()
        owner, company, _ = create_tenant('Unlimited', plan_version=version)
        branch = create_branch_with_access(creator=owner, company=company, name='Second')
        self.assertEqual(branch.company, company)


class FailClosedSaaSContextTests(TestCase):
    def test_unmapped_tenant_has_no_features_and_cannot_login(self):
        owner, company, _ = create_tenant('Unmapped Tenant')

        self.assertFalse(resolve_effective_status(company)['can_operate'])
        self.assertEqual(get_entitled_features(company), set())
        response = APIClient().post(
            reverse('accounts:login'),
            {'email': owner.email, 'password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 403, response.data)

    def test_features_require_an_explicit_enabled_entitlement(self):
        version = create_plan(code='explicit-features')
        capabilities = ensure_capability_catalog()
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities['feature.tables'],
            enabled=True,
            unlimited=True,
        )
        _, company, _ = create_tenant('Explicit Features', plan_version=version)

        self.assertEqual(get_entitled_features(company), {'feature.tables'})

    def test_login_and_me_keep_only_operational_company_and_branches(self):
        version = create_plan(code='multi-company-context')
        owner, active_company, _ = create_tenant('Operational Company', plan_version=version)
        expired_company = create_company_with_matrix(
            creator=owner,
            enforce_saas_limits=False,
            trade_name='Expired Company',
            legal_name='Expired Company Legal',
        )
        expired_subscription, _ = map_existing_company(
            company=expired_company,
            plan_version=version,
            billing_mode=Subscription.BillingMode.PAID,
        )
        expired_subscription.current_period_start = timezone.now() - timedelta(days=31)
        expired_subscription.current_period_end = timezone.now() - timedelta(seconds=1)
        expired_subscription.save()

        client = APIClient()
        response = client.post(
            reverse('accounts:login'),
            {'email': owner.email, 'password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item['id'] for item in response.data['companies']], [active_company.pk])
        self.assertEqual(
            {item['company_id'] for item in response.data['branches']},
            {active_company.pk},
        )

        response = client.get(reverse('accounts:me'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item['id'] for item in response.data['companies']], [active_company.pk])
        self.assertEqual(
            {item['company_id'] for item in response.data['branches']},
            {active_company.pk},
        )

    def test_unscoped_request_uses_an_operational_membership_or_denies(self):
        version = create_plan(code='unscoped-context')
        owner, active_company, _ = create_tenant('Unscoped Active', plan_version=version)
        expired_company = create_company_with_matrix(
            creator=owner,
            enforce_saas_limits=False,
            trade_name='Unscoped Expired',
            legal_name='Unscoped Expired Legal',
        )
        expired_subscription, _ = map_existing_company(
            company=expired_company,
            plan_version=version,
            billing_mode=Subscription.BillingMode.PAID,
        )
        expired_subscription.current_period_end = timezone.now() - timedelta(seconds=1)
        expired_subscription.save()
        request = SimpleNamespace(
            path='/api/v1/products/', headers={}, query_params={}, data={},
            parser_context={'kwargs': {}},
        )
        view = SimpleNamespace(queryset=Company.objects.none(), serializer_class=None)

        enforce_saas_request(request, owner, view)

        active_subscription = active_company.subscriptions.get(is_current=True)
        active_subscription.current_period_end = timezone.now() - timedelta(seconds=1)
        active_subscription.save()
        with self.assertRaises(PermissionDenied):
            enforce_saas_request(request, owner, view)
