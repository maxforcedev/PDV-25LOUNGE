from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.models import AuditLog
from apps.companies.models import AccessProfile, Company, UserCompanyAccess
from apps.companies.selectors import accessible_companies
from apps.companies.services import create_branch_with_access, create_company_with_matrix
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
    map_existing_company,
    process_subscription_lifecycle,
    provision_saas_tenant,
    record_manual_payment,
    resolve_effective_status,
    set_admin_suspension,
)


PASSWORD = 'Strong-owner-password-123!'


def create_user(email):
    return User.objects.create_user(email=email, password=PASSWORD)


def create_plan(code='basic', *, trial_days=0, price='99.00', public=True, users=3, branches=2):
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
    return version


def create_tenant(name='Tenant', *, plan_version=None, billing_mode=Subscription.BillingMode.PAID):
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
    def test_public_and_manual_use_equivalent_provisioning_and_are_idempotent(self):
        version = create_plan(trial_days=7)
        manual_owner = create_user('manual-owner@example.com')
        manual, created = provision_saas_tenant(
            source=ProvisioningOperation.Source.PLATFORM_MANUAL,
            idempotency_key='manual-1',
            plan_version=version,
            company_data={'trade_name': 'Manual', 'legal_name': 'Manual Legal'},
            owner_user=manual_owner,
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.assertTrue(created)
        retry, created = provision_saas_tenant(
            source=ProvisioningOperation.Source.PLATFORM_MANUAL,
            idempotency_key='manual-1',
            plan_version=version,
            company_data={'trade_name': 'Manual', 'legal_name': 'Manual Legal'},
            owner_user=manual_owner,
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
            self.assertEqual(operation.subscription.status, Subscription.Status.TRIALING)
            self.assertTrue(CycleUsage.objects.filter(subscription=operation.subscription).exists())

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
        self.assertTrue(effective['can_operate'])
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
        _, company, subscription = create_tenant('Trial Runtime', plan_version=trial_version)
        expired_at = subscription.trial_ends_at + timedelta(seconds=1)
        result = resolve_effective_status(company, at=expired_at)
        self.assertEqual(result['status'], Subscription.Status.TRIAL_EXPIRED)
        self.assertFalse(result['can_operate'])


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
