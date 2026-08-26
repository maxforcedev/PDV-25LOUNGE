from datetime import timedelta
from decimal import Decimal
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, models
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.models import AuditLog
from apps.companies.models import (
    AccessProfile,
    Branch,
    BranchSettings,
    Company,
    UserBranchAccess,
    UserCompanyAccess,
)
from apps.companies.services import create_branch_with_access, create_company_with_matrix
from apps.saas.models import (
    BillingRecord,
    GlobalSaaSSettings,
    Plan,
    PlanEntitlement,
    PlanVersion,
    PlatformPermission,
    PlatformRole,
    PlatformUserAccess,
    Subscription,
    SubscriptionRequest,
    SupportSession,
    TenantSaaSState,
)
from apps.saas.services import (
    add_months,
    assert_resource_limit,
    create_support_session,
    enable_saas_enforcement,
    get_global_settings,
    map_existing_company,
    process_subscription_lifecycle,
    provision_saas_tenant,
    record_manual_payment,
    resource_usage,
    request_plan_change,
    resolve_effective_status,
    resolve_subscription_request,
    set_admin_suspension,
    set_financial_suspension,
)

from .test_v2_2_saas import PASSWORD, create_plan, create_tenant, create_user


class EnforcementCutoverTests(TestCase):
    def test_cutover_is_atomic_and_defaults_unmapped_to_deny_after_success(self):
        version = create_plan(code='cutover')
        _, pending, _ = create_tenant('Cutover Pending')
        with self.assertRaises(ValidationError):
            enable_saas_enforcement(reason='Release')
        self.assertFalse(get_global_settings().enforcement_enabled)

        map_existing_company(
            company=pending, plan_version=version,
            billing_mode=Subscription.BillingMode.PAID,
        )
        settings_row, changed = enable_saas_enforcement(reason='Release')
        self.assertTrue(changed)
        self.assertTrue(settings_row.enforcement_enabled)

        owner = create_user('post-cutover@example.com')
        unmapped = create_company_with_matrix(
            creator=owner,
            enforce_saas_limits=False,
            trade_name='Post Cutover Unmapped', legal_name='Post Cutover Unmapped Legal',
        )
        effective = resolve_effective_status(unmapped)
        self.assertEqual(effective['status'], 'UNMAPPED')
        self.assertFalse(effective['can_operate'])
        settings_row.enforcement_enabled = False
        with self.assertRaises(ValidationError):
            settings_row.save()

    def test_cancelled_history_is_not_reported_as_unmapped(self):
        version = create_plan(code='cancelled-state')
        _, company, subscription = create_tenant('Cancelled State', plan_version=version)
        now = timezone.now()
        subscription.cancel_at_period_end = True
        subscription.cancellation_reason = 'Requested'
        subscription.current_period_start = now - timedelta(days=31)
        subscription.current_period_end = now - timedelta(seconds=1)
        subscription.save()
        process_subscription_lifecycle(subscription, at=now)
        result = resolve_effective_status(company, at=now)
        self.assertEqual(result['status'], Subscription.Status.CANCELLED)
        self.assertFalse(result['can_operate'])

    def test_mapping_requires_owner_and_command_gate_is_safe(self):
        version = create_plan(code='mapping-owner')
        company = Company.objects.create(trade_name='No Owner', legal_name='No Owner Legal')
        with self.assertRaises(ValidationError):
            map_existing_company(
                company=company, plan_version=version,
                billing_mode=Subscription.BillingMode.PAID,
            )
        with self.assertRaises(CommandError):
            call_command('enable_saas_enforcement', reason='Not ready', stdout=StringIO())
        self.assertFalse(get_global_settings().enforcement_enabled)


class BoundRuntimeContextTests(TestCase):
    def setUp(self):
        self.version = create_plan(code='runtime-context')
        self.owner, self.active_company, _ = create_tenant(
            'Runtime Active', plan_version=self.version
        )
        self.blocked_company = create_company_with_matrix(
            creator=self.owner,
            trade_name='Runtime Blocked', legal_name='Runtime Blocked Legal',
        )
        self.blocked_subscription, _ = map_existing_company(
            company=self.blocked_company,
            plan_version=self.version,
            billing_mode=Subscription.BillingMode.PAID,
        )
        self.blocked_subscription.status = Subscription.Status.SUSPENDED_FINANCIAL
        self.blocked_subscription.save(update_fields=('status', 'updated_at'))
        self.active_branch = self.active_company.branches.get(is_matrix=True)
        self.client = APIClient()
        self.assertTrue(self.client.login(email=self.owner.email, password=PASSWORD))

    def test_spoofed_header_and_omitted_context_cannot_bypass_object_state(self):
        response = self.client.get(
            reverse('company-detail', args=[self.blocked_company.pk]),
            HTTP_X_BRANCH_ID=str(self.active_branch.pk),
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse('company-detail', args=[self.blocked_company.pk]))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse('company-list'))
        self.assertEqual(response.status_code, 403)

    def test_restricted_reads_are_denied_but_owner_billing_allowlist_remains(self):
        response = self.client.get(reverse('company-detail', args=[self.blocked_company.pk]))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(
            reverse('saas-owner-subscription'), {'company': self.blocked_company.pk}
        )
        self.assertEqual(response.status_code, 200, response.data)


class AuthSaaSIntegrationTests(TestCase):
    def test_restricted_and_pending_owners_can_login_and_discover_subscription(self):
        global_settings = get_global_settings()
        global_settings.past_due_days = 1
        global_settings.restricted_after_days = 3
        global_settings.save(update_fields=(
            'past_due_days', 'restricted_after_days', 'updated_at'
        ))
        version = create_plan(code='auth-saas-context')
        restricted_owner, restricted_company, restricted_subscription = create_tenant(
            'Auth Restricted', plan_version=version
        )
        now = timezone.now()
        restricted_subscription.current_period_start = now - timedelta(days=32)
        restricted_subscription.current_period_end = now - timedelta(days=2)
        restricted_subscription.save()

        pending_owner, pending_company, _ = create_tenant(
            'Auth Pending', plan_version=version
        )
        pending_state = pending_company.saas_state
        pending_state.approval_status = TenantSaaSState.ApprovalStatus.PENDING
        pending_state.save(update_fields=('approval_status', 'updated_at'))

        for owner, company, expected_status in (
            (restricted_owner, restricted_company, Subscription.Status.RESTRICTED),
            (pending_owner, pending_company, 'PENDING_APPROVAL'),
        ):
            client = APIClient()
            response = client.post(
                reverse('accounts:login'),
                {'email': owner.email, 'password': PASSWORD},
                format='json',
            )
            self.assertEqual(response.status_code, 200, response.data)
            context = next(item for item in response.data['companies'] if item['id'] == company.pk)
            self.assertEqual(context['effective_status'], expected_status)
            self.assertFalse(context['can_operate'])
            self.assertTrue(context['is_owner'])
            response = client.get(
                reverse('saas-owner-subscription'), {'company': company.pk}
            )
            self.assertEqual(response.status_code, 200, response.data)
            response = client.get(reverse('company-detail', args=[company.pk]))
            self.assertEqual(response.status_code, 403)

    def test_me_exposes_valid_support_context_with_true_actor_and_logout_ends_it(self):
        version = create_plan(code='auth-support-context')
        owner, company, _ = create_tenant('Auth Support', plan_version=version)
        agent = create_user('auth-support-agent@example.com')
        call_command('bootstrap_platform_admin', email=agent.email, stdout=StringIO())
        session = create_support_session(
            actor=agent,
            company=company,
            impersonated_user=owner,
            mode=SupportSession.Mode.READ_WRITE,
            reason='Investigate tenant session',
            current_password=PASSWORD,
        )
        client = APIClient()
        self.assertTrue(client.login(email=agent.email, password=PASSWORD))
        invalid = client.get(
            reverse('accounts:me'),
            HTTP_X_SUPPORT_SESSION_ID='999999999',
        )
        self.assertIn(invalid.status_code, (401, 403))
        response = client.get(
            reverse('accounts:me'),
            HTTP_X_SUPPORT_SESSION_ID=str(session.pk),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['id'], owner.pk)
        self.assertEqual(response.data['support_session']['actor'], agent.pk)
        self.assertEqual(response.data['support_session']['actor_email'], agent.email)
        self.assertEqual(response.data['support_session']['company'], company.pk)
        self.assertEqual(response.data['support_session']['impersonated_user'], owner.pk)
        self.assertFalse(UserCompanyAccess.objects.filter(user=agent, company=company).exists())

        response = client.post(
            reverse('accounts:logout'),
            HTTP_X_SUPPORT_SESSION_ID=str(session.pk),
        )
        self.assertEqual(response.status_code, 204)
        session.refresh_from_db()
        self.assertIsNotNone(session.ended_at)
        self.assertEqual(session.ended_by, agent)
        self.assertEqual(
            AuditLog.objects.filter(
                action='saas.support.end', object_id=str(session.pk), actor=agent
            ).count(),
            1,
        )
        self.assertTrue(AuditLog.objects.filter(action='auth.logout', actor=agent).exists())


class SupportHardeningTests(TestCase):
    def setUp(self):
        self.version = create_plan(code='support-hardening')
        self.owner, self.company, _ = create_tenant(
            'Support Hardening', plan_version=self.version
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.agent = create_user('strict-support@example.com')
        call_command('bootstrap_platform_admin', email=self.agent.email, stdout=StringIO())

    def _client(self):
        client = APIClient()
        self.assertTrue(client.login(email=self.agent.email, password=PASSWORD))
        return client

    def test_non_impersonated_session_stays_platform_actor_and_audits_true_actor(self):
        session = create_support_session(
            actor=self.agent, company=self.company,
            mode=SupportSession.Mode.READ_WRITE,
            reason='Correct tenant data', current_password=PASSWORD,
        )
        client = self._client()
        response = client.patch(
            reverse('company-detail', args=[self.company.pk]),
            {'phone': '11999999999'}, format='json',
            HTTP_X_SUPPORT_SESSION_ID=str(session.pk),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(UserCompanyAccess.objects.filter(user=self.agent, company=self.company).exists())
        self.assertFalse(UserCompanyAccess.objects.filter(user=self.agent, is_owner=True).exists())
        log = AuditLog.objects.filter(action='company.update').latest('pk')
        self.assertEqual(log.actor, self.agent)
        self.assertEqual(log.metadata['support_session_id'], session.pk)
        self.assertEqual(
            AuditLog.objects.filter(
                action='saas.support.request',
                metadata__support_session_id=session.pk,
            ).count(),
            1,
        )
        self.assertFalse(AuditLog.objects.filter(
            action__startswith='api.', metadata__support_session_id=session.pk
        ).exists())

    def test_non_impersonated_support_user_list_is_tenant_scoped(self):
        other_user = create_user('outside-support-tenant@example.com')
        session = create_support_session(
            actor=self.agent, company=self.company,
            mode=SupportSession.Mode.READ_ONLY,
            reason='Inspect tenant users', current_password=PASSWORD,
        )
        response = self._client().get(
            reverse('user-list'),
            HTTP_X_SUPPORT_SESSION_ID=str(session.pk),
        )
        self.assertEqual(response.status_code, 200, response.data)
        serialized = str(response.data)
        self.assertIn(self.owner.email, serialized)
        self.assertNotIn(other_user.email, serialized)
        self.assertFalse(UserCompanyAccess.objects.filter(user=self.agent, company=self.company).exists())

    def test_only_explicit_impersonation_gets_target_rbac(self):
        operator = create_user('impersonated-operator@example.com')
        profile = AccessProfile.objects.get(company=self.company, name='Operador de Caixa')
        UserCompanyAccess.objects.create(user=operator, company=self.company, access_profile=profile)
        UserBranchAccess.objects.create(user=operator, branch=self.branch, access_profile=profile)
        session = create_support_session(
            actor=self.agent, company=self.company, impersonated_user=operator,
            mode=SupportSession.Mode.READ_WRITE,
            reason='Reproduce operator view', current_password=PASSWORD,
        )
        response = self._client().patch(
            reverse('company-detail', args=[self.company.pk]),
            {'phone': '11888888888'}, format='json',
            HTTP_X_SUPPORT_SESSION_ID=str(session.pk),
        )
        self.assertEqual(response.status_code, 403)

    def test_permission_is_continuous_expiry_is_bounded_and_history_is_retained(self):
        with self.assertRaises(ValidationError):
            create_support_session(
                actor=self.agent, company=self.company,
                mode=SupportSession.Mode.READ_ONLY, reason='Too long',
                expires_at=timezone.now() + timedelta(hours=3),
            )
        session = create_support_session(
            actor=self.agent, company=self.company,
            mode=SupportSession.Mode.READ_ONLY, reason='Inspect',
        )
        permission = PlatformPermission.objects.get(code='platform.support.manage')
        self.agent.platform_access.role.permissions.remove(permission)
        response = self._client().get(
            reverse('company-detail', args=[self.company.pk]),
            HTTP_X_SUPPORT_SESSION_ID=str(session.pk),
        )
        self.assertIn(response.status_code, (401, 403))
        with self.assertRaises(ValidationError):
            SupportSession.objects.filter(pk=session.pk).update(reason='Changed')
        with self.assertRaises(ValidationError):
            SupportSession.objects.filter(pk=session.pk).delete()
        with self.assertRaises(ValidationError):
            session.delete()

    def test_read_only_blocks_writes_and_get_does_not_create_branch_settings(self):
        session = create_support_session(
            actor=self.agent, company=self.company,
            mode=SupportSession.Mode.READ_ONLY, reason='Inspect settings',
        )
        BranchSettings.objects.filter(branch=self.branch).delete()
        client = self._client()
        response = client.get(
            reverse('branch-branch-settings', args=[self.branch.pk]),
            HTTP_X_BRANCH_ID=str(self.branch.pk),
            HTTP_X_SUPPORT_SESSION_ID=str(session.pk),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(BranchSettings.objects.filter(branch=self.branch).exists())
        request_log = AuditLog.objects.get(
            action='saas.support.request', metadata__support_session_id=session.pk
        )
        self.assertEqual(request_log.actor, self.agent)
        self.assertEqual(request_log.company, self.company)
        self.assertEqual(request_log.object_id, str(session.pk))
        self.assertEqual(request_log.metadata['support_actor_id'], self.agent.pk)
        self.assertEqual(request_log.metadata['support_effective_user_id'], self.agent.pk)
        self.assertEqual(request_log.metadata['support_mode'], SupportSession.Mode.READ_ONLY)
        self.assertEqual(request_log.metadata['method'], 'GET')
        self.assertEqual(request_log.metadata['status_code'], 200)
        self.assertTrue(request_log.metadata['request_id'])
        self.assertEqual(request_log.after['result'], 'success')
        response = client.patch(
            reverse('company-detail', args=[self.company.pk]),
            {'phone': '11777777777'}, format='json',
            HTTP_X_SUPPORT_SESSION_ID=str(session.pk),
        )
        self.assertEqual(response.status_code, 403)


class ImmutabilityAndLimitBypassTests(TestCase):
    def test_used_version_and_entitlements_reject_bulk_and_plan_field_changes(self):
        version = create_plan(code='bulk-immutable')
        create_tenant('Bulk Immutable', plan_version=version)
        other_plan = Plan.objects.create(code='other-plan', name='Other Plan')
        with self.assertRaises(ValidationError):
            PlanVersion.objects.filter(pk=version.pk).update(plan=other_plan)
        version.version = 2
        with self.assertRaises(ValidationError):
            PlanVersion.objects.bulk_update([version], ['version'])
        entitlement = version.entitlements.get(capability__code='users.max')
        entitlement.limit_value = 50
        with self.assertRaises(ValidationError):
            PlanEntitlement.objects.bulk_update([entitlement], ['limit_value'])
        with self.assertRaises(ValidationError):
            version.entitlements.all().delete()

    def test_direct_branch_membership_bulk_and_user_activation_bypasses_are_blocked(self):
        version = create_plan(code='limit-bypass', users=1, branches=1)
        owner, company, _ = create_tenant('Limit Bypass', plan_version=version)
        with self.assertRaises(ValidationError):
            Branch.objects.create(company=company, name='Direct')
        inactive_branch = Branch.objects.create(
            company=company, name='Inactive', status='inactive'
        )
        inactive_branch.status = 'active'
        with self.assertRaises(ValidationError):
            inactive_branch.save()
        with self.assertRaises(ValidationError):
            Branch.objects.filter(pk=inactive_branch.pk).update(status='active')
        with self.assertRaises(ValidationError):
            Branch.objects.bulk_update([inactive_branch], ['status'])

        profile = AccessProfile.objects.get(company=company, name='Administrador')
        extra = create_user('blocked-seat@example.com')
        with self.assertRaises(ValidationError):
            UserCompanyAccess.objects.create(user=extra, company=company, access_profile=profile)
        disabled = create_user('disabled-seat@example.com')
        disabled.is_active = False
        disabled.save()
        access = UserCompanyAccess(
            user=disabled, company=company, access_profile=profile
        )
        access.save()
        disabled.is_active = True
        with self.assertRaises(ValidationError):
            disabled.save()
        with self.assertRaises(ValidationError):
            User.objects.bulk_update([disabled], ['is_active'])
        access.is_active = False
        access.save(update_fields=('is_active', 'updated_at'))
        access.is_active = True
        with self.assertRaises(ValidationError):
            UserCompanyAccess.objects.bulk_update([access], ['is_active'])
        self.assertTrue(UserCompanyAccess.objects.get(user=owner, company=company).is_owner)

    def test_subscription_queryset_delete_is_blocked(self):
        version = create_plan(code='subscription-delete')
        _, _, subscription = create_tenant('Subscription Delete', plan_version=version)
        with self.assertRaises(ValidationError):
            Subscription.objects.filter(pk=subscription.pk).delete()
        self.assertTrue(Subscription.objects.filter(pk=subscription.pk).exists())

    def test_branch_overage_keeps_downgrade_pending(self):
        current = create_plan(code='branch-current', branches=2)
        target = create_plan(code='branch-target', branches=1)
        owner, company, subscription = create_tenant(
            'Branch Downgrade', plan_version=current
        )
        create_branch_with_access(creator=owner, company=company, name='Second')
        request = request_plan_change(subscription, owner, target, 'Reduce plan')
        actor = create_user('downgrade-actor@example.com')
        with self.assertRaises(ValidationError):
            resolve_subscription_request(request, actor, True)
        request.refresh_from_db()
        subscription.refresh_from_db()
        self.assertEqual(request.status, SubscriptionRequest.Status.PENDING)
        self.assertTrue(subscription.is_current)


class EntitlementAndPaymentHardeningTests(TestCase):
    def test_incomplete_plan_fails_closed_for_mapping_and_provisioning(self):
        plan = Plan.objects.create(code='incomplete', name='Incomplete')
        version = PlanVersion.objects.create(plan=plan, version=1, price=Decimal('10.00'))
        owner, company, _ = create_tenant('Incomplete Mapping')
        with self.assertRaises(ValidationError):
            map_existing_company(
                company=company, plan_version=version,
                billing_mode=Subscription.BillingMode.PAID,
            )
        with self.assertRaises(ValidationError):
            provision_saas_tenant(
                source='PUBLIC_SIGNUP', idempotency_key='incomplete-1',
                plan_version=version,
                company_data={'trade_name': 'Bad', 'legal_name': 'Bad Legal'},
                owner_email='bad-plan@example.com', owner_password=PASSWORD,
            )

    def test_required_entitlement_missing_at_runtime_denies(self):
        version = create_plan(code='runtime-fail-closed')
        _, company, _ = create_tenant('Runtime Fail Closed', plan_version=version)
        core = version.entitlements.get(capability__code='core.enabled')
        models.QuerySet(model=PlanEntitlement).filter(pk=core.pk).delete()
        result = resolve_effective_status(company)
        self.assertEqual(result['status'], 'INVALID_ENTITLEMENTS')
        self.assertFalse(result['can_operate'])

    def test_payment_validates_contract_cycle_proof_and_only_financial_state(self):
        version = create_plan(code='payment-hardening', price='120.00')
        actor = create_user('strict-billing@example.com')
        _, company, subscription = create_tenant(
            'Payment Hardening', plan_version=version
        )
        now = timezone.now()
        subscription.current_period_start = now - timedelta(days=31)
        subscription.current_period_end = now - timedelta(days=1)
        subscription.status = Subscription.Status.SUSPENDED_FINANCIAL
        subscription.save()
        set_admin_suspension(company, actor, 'Security', True)
        start = subscription.current_period_end
        end = add_months(start, 1)
        base = {
            'subscription': subscription, 'actor': actor, 'idempotency_key': 'strict-pay',
            'amount': Decimal('120.00'), 'paid_at': now, 'payment_method': 'PIX',
            'competency_start': start, 'competency_end': end,
            'note': 'Confirmed', 'proof_reference': 'receipts/strict-pay.pdf',
        }
        with self.assertRaises(ValidationError):
            record_manual_payment(**{**base, 'amount': Decimal('119.00')})
        with self.assertRaises(ValidationError):
            record_manual_payment(**{**base, 'competency_end': end + timedelta(days=1)})
        with self.assertRaises(ValidationError):
            record_manual_payment(**{**base, 'proof_reference': 'javascript:alert(1)'})
        record, created = record_manual_payment(**base)
        self.assertTrue(created)
        self.assertEqual(record.proof_reference, 'receipts/strict-pay.pdf')
        replay, created = record_manual_payment(**base)
        self.assertFalse(created)
        self.assertEqual(replay.pk, record.pk)
        with self.assertRaises(ValidationError):
            record_manual_payment(**{**base, 'note': 'Different'})
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(resolve_effective_status(company)['status'], 'SUSPENDED_ADMIN')

        subscription.cancel_at_period_end = True
        subscription.save(update_fields=('cancel_at_period_end', 'updated_at'))
        with self.assertRaises(ValidationError):
            record_manual_payment(**{**base, 'idempotency_key': 'cancelled-pay'})

    def test_explicit_financial_suspension_applies_to_every_billing_mode(self):
        version = create_plan(code='explicit-financial-modes')
        actor = create_user('financial-modes@example.com')
        for mode in Subscription.BillingMode.values:
            _, company, subscription = create_tenant(
                f'Financial {mode}', plan_version=version, billing_mode=mode
            )
            subscription = set_financial_suspension(
                subscription, actor, 'Explicit review', True
            )
            effective = resolve_effective_status(company)
            self.assertEqual(effective['status'], Subscription.Status.SUSPENDED_FINANCIAL)
            self.assertFalse(effective['can_operate'])
            subscription = set_financial_suspension(
                subscription, actor, 'Review complete', False
            )
            if mode in (Subscription.BillingMode.FREE, Subscription.BillingMode.INTERNAL):
                self.assertEqual(subscription.status, Subscription.Status.ACTIVE)

    def test_suspended_memberships_do_not_consume_users_limit_and_owner_stays_active(self):
        version = create_plan(code='active-membership-usage', users=2)
        owner, company, _ = create_tenant(
            'Active Membership Usage', plan_version=version
        )
        profile = AccessProfile.objects.get(company=company, name='Administrador')
        suspended_user = create_user('suspended-membership@example.com')
        suspended_access = UserCompanyAccess.objects.create(
            user=suspended_user, company=company, access_profile=profile
        )
        suspended_access.saas_status = UserCompanyAccess.SaaSStatus.SUSPENDED_BY_PLAN_LIMIT
        suspended_access.save(update_fields=('saas_status', 'updated_at'))

        self.assertEqual(resource_usage(company, 'users.max'), 1)
        assert_resource_limit(company, 'users.max')
        admitted = create_user('admitted-after-suspension@example.com')
        UserCompanyAccess.objects.create(
            user=admitted, company=company, access_profile=profile
        )
        self.assertEqual(resource_usage(company, 'users.max'), 2)
        owner_access = UserCompanyAccess.objects.get(user=owner, company=company)
        self.assertTrue(owner_access.is_active)
        self.assertEqual(owner_access.saas_status, UserCompanyAccess.SaaSStatus.ACTIVE)


THROTTLED_REST_FRAMEWORK = {
    **settings.REST_FRAMEWORK,
    'DEFAULT_THROTTLE_RATES': {
        **settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'],
        'signup': '1/hour',
    },
}


class ProvisioningAbuseTests(TestCase):
    def test_public_signup_has_dedicated_abuse_throttle(self):
        cache.clear()
        client = APIClient()
        for _ in range(5):
            response = client.post(reverse('saas-public-signup'), {}, format='json')
            self.assertEqual(response.status_code, 400)
        response = client.post(reverse('saas-public-signup'), {}, format='json')
        self.assertEqual(response.status_code, 429)


class PublicPlanCatalogTests(TestCase):
    def test_anonymous_catalog_only_returns_eligible_public_active_versions(self):
        eligible = create_plan(
            code='public-eligible', price='149.00', trial_days=7, users=8, branches=3
        )
        create_plan(code='public-private', public=False)
        inactive = create_plan(code='public-inactive')
        inactive.is_active = False
        inactive.save(update_fields=('is_active', 'updated_at'))
        inactive_plan = create_plan(code='public-inactive-plan')
        inactive_plan.plan.is_active = False
        inactive_plan.plan.save(update_fields=('is_active', 'updated_at'))
        incomplete_plan = Plan.objects.create(code='public-incomplete', name='Incomplete')
        PlanVersion.objects.create(
            plan=incomplete_plan, version=1, price=Decimal('10.00'), is_public=True
        )

        client = APIClient()
        response = client.get(reverse('saas-public-plan-list'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item['id'] for item in response.data], [eligible.pk])
        summary = response.data[0]
        self.assertEqual(summary['price'], '149.00')
        self.assertEqual(summary['trial_days'], 7)
        self.assertEqual(summary['limits']['users'], {'unlimited': False, 'value': 8})
        self.assertNotIn('entitlements', summary)
        self.assertNotIn('is_active', summary)
        self.assertEqual(client.post(reverse('saas-public-plan-list'), {}, format='json').status_code, 405)

    def test_public_settings_returns_only_branding_without_creating_defaults(self):
        client = APIClient()
        response = client.get(reverse('saas-public-settings'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(GlobalSaaSSettings.objects.count(), 0)
        expected_fields = {
            'platform_name', 'logo_url', 'compact_logo_url', 'favicon_url',
            'primary_color', 'support_email', 'support_phone', 'institutional_links',
        }
        self.assertEqual(set(response.data), expected_fields)

        GlobalSaaSSettings.objects.create(
            platform_name='Safe Brand', support_email='support@example.com',
            auto_approve_signups=False, public_signup_billing_mode='FREE',
            support_whatsapp='5511999999999',
            institutional_links={'terms': 'https://example.com/terms'},
        )
        response = client.get(reverse('saas-public-settings'))
        self.assertEqual(response.data['platform_name'], 'Safe Brand')
        self.assertEqual(response.data['support_email'], 'support@example.com')
        self.assertNotIn('auto_approve_signups', response.data)
        self.assertNotIn('public_signup_billing_mode', response.data)
        self.assertNotIn('support_whatsapp', response.data)
        self.assertEqual(client.post(reverse('saas-public-settings'), {}).status_code, 405)


class PublicSignupCsrfTests(TestCase):
    def test_signup_rejects_missing_and_invalid_csrf_and_accepts_valid_token(self):
        cache.clear()
        version = create_plan(code='public-signup-csrf')
        payload = {
            'idempotency_key': 'csrf-signup',
            'plan_version': version.pk,
            'trade_name': 'CSRF Tenant',
            'legal_name': 'CSRF Tenant Legal',
            'owner_email': 'csrf-owner@example.com',
            'owner_password': PASSWORD,
        }
        missing = APIClient(enforce_csrf_checks=True)
        response = missing.post(reverse('saas-public-signup'), payload, format='json')
        self.assertEqual(response.status_code, 403)

        invalid = APIClient(enforce_csrf_checks=True)
        invalid.get(reverse('accounts:csrf'))
        response = invalid.post(
            reverse('saas-public-signup'), payload, format='json',
            HTTP_X_CSRFTOKEN='invalid-token',
        )
        self.assertEqual(response.status_code, 403)

        valid = APIClient(enforce_csrf_checks=True)
        csrf_response = valid.get(reverse('accounts:csrf'))
        token = csrf_response.data['csrf_token']
        response = valid.post(
            reverse('saas-public-signup'), payload, format='json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 201, response.data)
        operation_id = response.data['id']
        response = valid.post(
            reverse('saas-public-signup'), payload, format='json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['id'], operation_id)


class Tenant360PermissionTests(TestCase):
    def setUp(self):
        version = create_plan(code='tenant-360-permissions')
        self.owner, self.company, self.subscription = create_tenant(
            'Tenant 360 Permissions', plan_version=version
        )
        self.tenant_permission = PlatformPermission.objects.create(
            code='platform.tenants.manage', label='Manage tenants'
        )
        self.billing_permission = PlatformPermission.objects.create(
            code='platform.billing.manage', label='Manage billing'
        )
        self.support_permission = PlatformPermission.objects.create(
            code='platform.support.manage', label='Manage support'
        )

    def _actor(self, suffix, permissions):
        actor = create_user(f'tenant-360-{suffix}@example.com')
        role = PlatformRole.objects.create(
            code=f'tenant-360-{suffix}', name=f'Tenant 360 {suffix}'
        )
        role.permissions.set(permissions)
        PlatformUserAccess.objects.create(user=actor, role=role)
        return actor

    def _retrieve(self, actor):
        client = APIClient()
        client.force_authenticate(actor)
        return client.get(reverse('platform-tenant-detail', args=[self.company.pk]))

    def test_tenant_360_omits_billing_and_support_without_permissions(self):
        actor = self._actor('tenant-only', [self.tenant_permission])
        response = self._retrieve(actor)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('subscription', response.data)
        self.assertNotIn('payments', response.data)
        self.assertNotIn('support_sessions', response.data)

    def test_tenant_360_exposes_each_sensitive_section_only_with_its_permission(self):
        billing_actor = self._actor(
            'billing', [self.tenant_permission, self.billing_permission]
        )
        response = self._retrieve(billing_actor)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('subscription', response.data)
        self.assertIn('payments', response.data)
        self.assertNotIn('support_sessions', response.data)

        support_actor = self._actor(
            'support', [self.tenant_permission, self.support_permission]
        )
        create_support_session(
            actor=support_actor, company=self.company,
            mode=SupportSession.Mode.READ_ONLY, reason='Permission test',
        )
        response = self._retrieve(support_actor)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('subscription', response.data)
        self.assertNotIn('payments', response.data)
        self.assertIn('support_sessions', response.data)
        self.assertEqual(len(response.data['support_sessions']), 1)

    def test_tenant_manage_cannot_access_subscription_or_financial_actions(self):
        tenant_actor = self._actor('subscription-denied', [self.tenant_permission])
        client = APIClient()
        client.force_authenticate(tenant_actor)
        self.assertEqual(client.get(reverse('platform-subscription-list')).status_code, 403)
        self.assertEqual(
            client.get(reverse('platform-subscription-request-list')).status_code,
            403,
        )
        self.assertEqual(
            client.get(reverse(
                'platform-subscription-detail', args=[self.subscription.pk]
            )).status_code,
            403,
        )
        subscription_actions = (
            'platform-subscription-billing-mode',
            'platform-subscription-financial-suspend',
            'platform-subscription-financial-resume',
            'platform-subscription-extend-trial',
            'platform-subscription-process-lifecycle',
        )
        for action_name in subscription_actions:
            response = client.post(
                reverse(action_name, args=[self.subscription.pk]), {}, format='json'
            )
            self.assertEqual(response.status_code, 403, action_name)
        self.assertEqual(
            client.post(
                reverse('platform-tenant-financial-suspend', args=[self.company.pk]),
                {}, format='json',
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                reverse('platform-tenant-process-lifecycle', args=[self.company.pk]),
                {}, format='json',
            ).status_code,
            403,
        )

        billing_actor = self._actor(
            'subscription-allowed', [self.billing_permission]
        )
        client.force_authenticate(billing_actor)
        self.assertEqual(client.get(reverse('platform-subscription-list')).status_code, 200)
        self.assertEqual(
            client.get(reverse('platform-subscription-request-list')).status_code,
            200,
        )
        self.assertEqual(
            client.get(reverse(
                'platform-subscription-detail', args=[self.subscription.pk]
            )).status_code,
            200,
        )


class PlatformSubscriptionAdministrationTests(TestCase):
    def setUp(self):
        self.version = create_plan(code='platform-subscription', trial_days=3)
        self.owner, self.company, self.subscription = create_tenant(
            'Platform Subscription', plan_version=self.version
        )
        self.actor = create_user('subscription-admin@example.com')
        call_command('bootstrap_platform_admin', email=self.actor.email, stdout=StringIO())
        self.client = APIClient()
        self.client.force_authenticate(self.actor)

    def test_list_detail_billing_trial_and_owner_transfer_require_reauth(self):
        response = self.client.get(reverse('platform-subscription-list'))
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.get(
            reverse('platform-subscription-detail', args=[self.subscription.pk])
        )
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(
            reverse('platform-subscription-extend-trial', args=[self.subscription.pk]),
            {'days': 2, 'reason': 'Customer validation', 'current_password': 'wrong'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            reverse('platform-subscription-extend-trial', args=[self.subscription.pk]),
            {'days': 2, 'reason': 'Customer validation', 'current_password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(AuditLog.objects.filter(action='saas.subscription.trial.extend').exists())

        response = self.client.post(
            reverse('platform-subscription-billing-mode', args=[self.subscription.pk]),
            {
                'billing_mode': Subscription.BillingMode.FREE,
                'reason': 'Approved partnership', 'current_password': PASSWORD,
            }, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        target = create_user('new-platform-owner@example.com')
        profile = AccessProfile.objects.get(company=self.company, name='Administrador')
        UserCompanyAccess.objects.create(user=target, company=self.company, access_profile=profile)
        UserBranchAccess.objects.create(
            user=target, branch=self.company.branches.get(is_matrix=True),
            access_profile=profile,
        )
        response = self.client.post(
            reverse('platform-tenant-transfer-owner', args=[self.company.pk]),
            {
                'target_user_id': target.pk, 'reason': 'Verified ownership change',
                'current_password': PASSWORD,
            }, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(UserCompanyAccess.objects.get(company=self.company, user=target).is_owner)

    def test_manual_new_identity_password_is_validated(self):
        cache.clear()
        response = self.client.post(
            reverse('platform-tenant-list'),
            {
                'idempotency_key': 'weak-manual', 'plan_version': self.version.pk,
                'trade_name': 'Weak Manual', 'legal_name': 'Weak Manual Legal',
                'owner_email': 'weak-manual@example.com', 'owner_password': '123',
                'billing_mode': Subscription.BillingMode.PAID,
                'reason': 'New tenant', 'current_password': PASSWORD,
            }, format='json',
        )
        self.assertEqual(response.status_code, 400)
        public = APIClient().post(
            reverse('saas-public-signup'),
            {
                'idempotency_key': 'weak-public', 'plan_version': self.version.pk,
                'trade_name': 'Weak Public', 'legal_name': 'Weak Public Legal',
                'owner_email': 'weak-public@example.com', 'owner_password': '123',
            }, format='json',
        )
        self.assertEqual(public.status_code, 400)

    def test_reject_and_archive_are_separate_audited_saas_states(self):
        global_settings = get_global_settings()
        global_settings.auto_approve_signups = False
        global_settings.save(update_fields=('auto_approve_signups', 'updated_at'))
        pending, _ = provision_saas_tenant(
            source='PUBLIC_SIGNUP', idempotency_key='pending-reject',
            plan_version=self.version,
            company_data={'trade_name': 'Pending Reject', 'legal_name': 'Pending Reject Legal'},
            owner_email='pending-reject@example.com', owner_password=PASSWORD,
        )
        response = self.client.post(
            reverse('platform-tenant-reject', args=[pending.company_id]),
            {'reason': 'Duplicate registration', 'current_password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['approval_status'], 'REJECTED')
        response = self.client.post(
            reverse('platform-tenant-archive', args=[self.company.pk]),
            {'reason': 'Contract ended', 'current_password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(resolve_effective_status(self.company)['status'], 'ARCHIVED')

    def test_payment_without_competency_derives_future_period_and_replays(self):
        version = create_plan(code='derived-payment-period', price='130.00')
        _, company, subscription = create_tenant(
            'Derived Payment Period', plan_version=version
        )
        now = timezone.now()
        subscription.current_period_start = now - timedelta(days=95)
        subscription.current_period_end = now - timedelta(days=65)
        subscription.status = Subscription.Status.SUSPENDED_FINANCIAL
        subscription.save()
        payload = {
            'subscription': subscription.pk,
            'amount': '130.00',
            'paid_at': now.isoformat(),
            'payment_method': 'PIX',
            'proof_reference': 'receipts/derived-payment.pdf',
            'idempotency_key': 'derived-payment',
            'reason': 'Payment confirmed',
            'current_password': PASSWORD,
        }
        response = self.client.post(
            reverse('platform-payment-list'), payload, format='json'
        )
        self.assertEqual(response.status_code, 201, response.data)
        record_id = response.data['id']
        record = BillingRecord.objects.get(pk=record_id)
        self.assertEqual(
            record.competency_end,
            add_months(record.competency_start, version.billing_period_months),
        )
        self.assertGreater(record.competency_end, now)
        subscription.refresh_from_db()
        self.assertEqual(subscription.current_period_start, record.competency_start)
        self.assertEqual(subscription.current_period_end, record.competency_end)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)

        replay = self.client.post(
            reverse('platform-payment-list'), payload, format='json'
        )
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(replay.data['id'], record_id)
        self.assertEqual(
            BillingRecord.objects.filter(
                subscription=subscription, idempotency_key='derived-payment'
            ).count(),
            1,
        )


class ConcurrencyHardeningTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_payment_replay_creates_one_append_only_record(self):
        version = create_plan(code='concurrent-payment', price='80.00')
        actor = create_user('concurrent-billing@example.com')
        _, _, subscription = create_tenant(
            'Concurrent Payment', plan_version=version
        )
        now = timezone.now()
        subscription.current_period_start = now - timedelta(days=31)
        subscription.current_period_end = now - timedelta(days=1)
        subscription.status = Subscription.Status.SUSPENDED_FINANCIAL
        subscription.save()
        start = subscription.current_period_end
        end = add_months(start, 1)
        barrier = Barrier(2)

        def pay():
            close_old_connections()
            local_subscription = Subscription.objects.get(pk=subscription.pk)
            local_actor = type(actor).objects.get(pk=actor.pk)
            barrier.wait()
            result = record_manual_payment(
                subscription=local_subscription, actor=local_actor,
                idempotency_key='concurrent-replay', amount=Decimal('80.00'),
                paid_at=now, payment_method='PIX', competency_start=start,
                competency_end=end, proof_reference='receipts/concurrent.pdf',
            )
            close_old_connections()
            return result[1]

        with ThreadPoolExecutor(max_workers=2) as executor:
            created_flags = list(executor.map(lambda _: pay(), range(2)))
        self.assertEqual(sorted(created_flags), [False, True])
        self.assertEqual(BillingRecord.objects.filter(subscription=subscription).count(), 1)

    def test_concurrent_provisioning_is_idempotent(self):
        version = create_plan(code='concurrent-provision')
        barrier = Barrier(2)

        def provision():
            close_old_connections()
            local_version = PlanVersion.objects.get(pk=version.pk)
            barrier.wait()
            operation, created = provision_saas_tenant(
                source='PUBLIC_SIGNUP', idempotency_key='same-concurrent-key',
                plan_version=local_version,
                company_data={'trade_name': 'Concurrent', 'legal_name': 'Concurrent Legal'},
                owner_email='concurrent-owner@example.com', owner_password=PASSWORD,
            )
            close_old_connections()
            return operation.pk, created

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: provision(), range(2)))
        self.assertEqual({item[0] for item in results}, {results[0][0]})
        self.assertEqual(sorted(item[1] for item in results), [False, True])

    def test_direct_user_activation_holds_company_limit_lock_through_write(self):
        version = create_plan(code='activation-race', users=2)
        _, company, _ = create_tenant('Activation Race', plan_version=version)
        profile = AccessProfile.objects.get(company=company, name='Administrador')
        candidates = []
        for index in range(2):
            candidate = create_user(f'activation-race-{index}@example.com')
            candidate.is_active = False
            candidate.save(update_fields=('is_active', 'updated_at'))
            UserCompanyAccess.objects.create(
                user=candidate, company=company, access_profile=profile
            )
            candidates.append(candidate)
        barrier = Barrier(2)

        def activate(user_id):
            close_old_connections()
            user = User.objects.get(pk=user_id)
            user.is_active = True
            barrier.wait()
            try:
                user.save(update_fields=('is_active', 'updated_at'))
                result = True
            except ValidationError:
                result = False
            close_old_connections()
            return result

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(activate, [item.pk for item in candidates]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(
            User.objects.filter(pk__in=[item.pk for item in candidates], is_active=True).count(),
            1,
        )

    def test_finalized_cancellation_is_idempotent_under_repeat_and_concurrency(self):
        version = create_plan(code='cancellation-race')
        _, company, subscription = create_tenant(
            'Cancellation Race', plan_version=version
        )
        at = timezone.now()
        subscription.cancel_at_period_end = True
        subscription.cancellation_reason = 'Requested'
        subscription.current_period_start = at - timedelta(days=31)
        subscription.current_period_end = at - timedelta(seconds=1)
        subscription.save()
        barrier = Barrier(2)

        def finalize():
            close_old_connections()
            local = Subscription.objects.get(pk=subscription.pk)
            barrier.wait()
            _, changed = process_subscription_lifecycle(local, at=at)
            close_old_connections()
            return changed

        with ThreadPoolExecutor(max_workers=2) as executor:
            changed_flags = list(executor.map(lambda _: finalize(), range(2)))
        self.assertEqual(sorted(changed_flags), [False, True])
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.CANCELLED)
        self.assertFalse(subscription.is_current)
        self.assertIsNotNone(subscription.cancelled_at)
        _, changed = process_subscription_lifecycle(subscription, at=at)
        self.assertFalse(changed)
        self.assertEqual(
            AuditLog.objects.filter(
                action='saas.subscription.lifecycle', object_id=str(subscription.pk)
            ).count(),
            1,
        )

    def test_subscription_creation_and_version_update_serialize_history(self):
        version = create_plan(code='version-race')
        owner, company, _ = create_tenant('Version Race')
        barrier = Barrier(2)

        def subscribe():
            close_old_connections()
            now = timezone.now()
            barrier.wait()
            Subscription.objects.create(
                company_id=company.pk, plan_version_id=version.pk,
                billing_mode=Subscription.BillingMode.PAID,
                status=Subscription.Status.ACTIVE,
                current_period_start=now, current_period_end=add_months(now, 1),
            )
            close_old_connections()
            return 'subscribed'

        def change_version():
            close_old_connections()
            barrier.wait()
            try:
                PlanVersion.objects.filter(pk=version.pk).update(price=Decimal('101.00'))
                result = 'updated-first'
            except ValidationError:
                result = 'blocked'
            close_old_connections()
            return result

        with ThreadPoolExecutor(max_workers=2) as executor:
            subscription_future = executor.submit(subscribe)
            update_future = executor.submit(change_version)
            self.assertEqual(subscription_future.result(), 'subscribed')
            self.assertIn(update_future.result(), ('updated-first', 'blocked'))
        self.assertTrue(Subscription.objects.filter(company=company, is_current=True).exists())
        with self.assertRaises(ValidationError):
            PlanVersion.objects.filter(pk=version.pk).update(price=Decimal('102.00'))
