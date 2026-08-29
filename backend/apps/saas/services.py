import hashlib
import json
import re
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.base.audit import audit_log
from apps.companies.models import Branch, Company, UserCompanyAccess
from apps.companies.services import create_company_with_matrix

from .models import (
    BillingRecord,
    Capability,
    CycleUsage,
    GlobalSaaSSettings,
    PlatformUserAccess,
    PlanEntitlement,
    PlanVersion,
    ProvisioningOperation,
    Subscription,
    SubscriptionRequest,
    SupportSession,
    TenantSaaSState,
)


CAPABILITY_CATALOG = (
    ('core.enabled', 'CORE Backoffice', Capability.ValueType.BOOLEAN),
    ('users.max', 'Usuarios com login', Capability.ValueType.INTEGER),
    ('branches.max', 'Filiais', Capability.ValueType.INTEGER),
    ('feature.tables', 'Mesas', Capability.ValueType.BOOLEAN),
    ('feature.commands', 'Comandas', Capability.ValueType.BOOLEAN),
    ('feature.counter', 'Balcao', Capability.ValueType.BOOLEAN),
    ('feature.consumption', 'Consumacao interna', Capability.ValueType.BOOLEAN),
    ('feature.cash_register', 'Caixa', Capability.ValueType.BOOLEAN),
    ('feature.production', 'Producao e impressao', Capability.ValueType.BOOLEAN),
)
FEATURE_CAPABILITY_CODES = frozenset(
    code for code, _, _ in CAPABILITY_CATALOG if code.startswith('feature.')
)
REQUIRED_CAPABILITY_CODES = frozenset(
    code for code, _, _ in CAPABILITY_CATALOG
    if not code.startswith('feature.')
)
SAFE_PROOF_REFERENCE = re.compile(r'^(?:https://[^\s]+|[A-Za-z0-9][A-Za-z0-9._/-]{0,499})$')


def ensure_capability_catalog():
    result = {}
    for code, name, value_type in CAPABILITY_CATALOG:
        capability, _ = Capability.objects.update_or_create(
            code=code,
            defaults={'name': name, 'value_type': value_type, 'is_active': True},
        )
        result[code] = capability
    return result


def get_global_settings():
    settings, _ = GlobalSaaSSettings.objects.get_or_create(singleton=True)
    return settings


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _fingerprint(payload):
    normalized = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _advisory_transaction_lock(namespace, key):
    digest = hashlib.sha256(f'{namespace}:{key}'.encode('utf-8')).digest()
    lock_id = int.from_bytes(digest[:8], byteorder='big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [lock_id])


def validate_plan_version_complete(plan_version, *, lock=False):
    queryset = PlanVersion.objects.select_related('plan')
    if lock:
        queryset = queryset.select_for_update()
    plan_version = queryset.get(pk=plan_version.pk)
    if not plan_version.is_active or not plan_version.plan.is_active:
        raise ValidationError({'plan_version': 'A versao de plano nao esta ativa.'})
    entitlements = {
        item.capability.code: item
        for item in plan_version.entitlements.select_related('capability').filter(
            capability__is_active=True
        )
    }
    missing = sorted(REQUIRED_CAPABILITY_CODES - set(entitlements))
    invalid = []
    core = entitlements.get('core.enabled')
    if core and not core.enabled:
        invalid.append('core.enabled')
    for code in ('users.max', 'branches.max'):
        item = entitlements.get(code)
        if item and (
            not item.enabled
            or not item.unlimited and (item.limit_value is None or item.limit_value < 1)
        ):
            invalid.append(code)
    if missing or invalid:
        raise ValidationError({
            'plan_version': (
                f'Entitlements obrigatorios ausentes: {", ".join(missing)}. '
                f'Entitlements invalidos: {", ".join(sorted(invalid))}.'
            ).strip()
        })
    return plan_version


def _has_valid_owner(company):
    return UserCompanyAccess.objects.filter(
        company=company,
        is_owner=True,
        is_active=True,
        saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        user__is_active=True,
        user__can_login=True,
    ).count() == 1


def _is_valid_current_subscription(subscription):
    return bool(
        subscription
        and subscription.is_current
        and subscription.status not in (
            Subscription.Status.CANCELLED,
            Subscription.Status.SUPERSEDED,
        )
    )


def validate_company_ready_for_enforcement(company):
    if not get_global_settings().enforcement_enabled:
        return
    if not _has_valid_owner(company):
        raise ValidationError({'company': 'A empresa nao possui Owner valido para o cutover.'})
    subscription = current_subscription(company)
    if not _is_valid_current_subscription(subscription):
        raise ValidationError({'company': 'A empresa nao possui assinatura corrente valida.'})
    validate_plan_version_complete(subscription.plan_version)


def user_has_platform_permission(user, code):
    return PlatformUserAccess.objects.filter(
        user=user,
        is_active=True,
        role__permissions__code=code,
    ).exists()


def current_subscription(company):
    return Subscription.objects.filter(company=company, is_current=True).select_related(
        'plan_version__plan'
    ).first()


def effective_entitlement(company, code):
    subscription = current_subscription(company)
    if not subscription:
        return None
    return PlanEntitlement.objects.filter(
        plan_version=subscription.plan_version,
        capability__code=code,
        capability__is_active=True,
    ).select_related('capability').first()


def get_entitled_features(company):
    subscription = current_subscription(company)
    if not subscription:
        return set(FEATURE_CAPABILITY_CODES)
    enabled = set(
        PlanEntitlement.objects.filter(
            plan_version=subscription.plan_version,
            capability__code__in=FEATURE_CAPABILITY_CODES,
            capability__is_active=True,
            enabled=True,
        ).values_list('capability__code', flat=True)
    )
    known = set(enabled)
    for code in FEATURE_CAPABILITY_CODES:
        if code not in enabled and not PlanEntitlement.objects.filter(
            plan_version=subscription.plan_version,
            capability__code=code,
        ).exists():
            known.add(code)
    return known


def resource_usage(company, code):
    if code == 'users.max':
        return UserCompanyAccess.objects.filter(
            company=company,
            is_active=True,
            saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
            user__is_active=True,
            user__can_login=True,
        ).count()
    if code == 'branches.max':
        return Branch.objects.filter(company=company, status='active').count()
    raise ValidationError({'capability': 'Capacidade sem medicao implementada.'})


@transaction.atomic
def assert_resource_limit(company, code, delta=1, *, company_locked=False):
    if not company_locked:
        Company.objects.select_for_update().get(pk=company.pk)
    subscription = current_subscription(company)
    if not subscription:
        if get_global_settings().enforcement_enabled:
            raise ValidationError({'subscription': 'Tenant sem assinatura corrente apos o cutover.'})
        return
    entitlement = effective_entitlement(company, code)
    if entitlement is None:
        raise ValidationError({'limit': f'O plano nao define o entitlement obrigatorio {code}.'})
    if not entitlement.enabled:
        raise ValidationError({'limit': f'A capacidade {code} nao esta habilitada.'})
    if entitlement.unlimited:
        return
    if resource_usage(company, code) + delta > entitlement.limit_value:
        raise ValidationError({'limit': f'O limite contratado para {code} foi atingido.'})


@transaction.atomic
def enable_saas_enforcement(actor=None, reason='Validated SaaS cutover'):
    with connection.cursor() as cursor:
        cursor.execute('LOCK TABLE companies_company IN SHARE ROW EXCLUSIVE MODE')
    global_settings = GlobalSaaSSettings.objects.select_for_update().first()
    if global_settings is None:
        global_settings = GlobalSaaSSettings.objects.create()
    if global_settings.enforcement_enabled:
        return global_settings, False
    companies = list(
        Company.objects.select_for_update().filter(status='active').order_by('pk')
    )
    errors = []
    subscriptions = {
        item.company_id: item
        for item in Subscription.objects.select_for_update().filter(
            company_id__in=[company.pk for company in companies], is_current=True
        ).select_related('plan_version__plan')
    }
    for company in companies:
        if not _has_valid_owner(company):
            errors.append(f'{company.pk}:owner')
        subscription = subscriptions.get(company.pk)
        if not _is_valid_current_subscription(subscription):
            errors.append(f'{company.pk}:subscription')
            continue
        try:
            validate_plan_version_complete(subscription.plan_version, lock=True)
        except ValidationError:
            errors.append(f'{company.pk}:entitlements')
    if errors:
        raise ValidationError({
            'cutover': 'Pendencias impedem o cutover: ' + ', '.join(errors)
        })
    global_settings.enforcement_enabled = True
    global_settings.enforcement_enabled_at = timezone.now()
    global_settings.enforcement_enabled_by = actor
    global_settings.save(update_fields=(
        'enforcement_enabled', 'enforcement_enabled_at',
        'enforcement_enabled_by', 'updated_at',
    ))
    audit_log(
        actor=actor,
        action='saas.enforcement.enable',
        obj=global_settings,
        after={'enforcement_enabled': True, 'operational_companies': len(companies)},
        metadata={'reason': reason},
    )
    return global_settings, True


@transaction.atomic
def sync_cycle_usage(subscription):
    capabilities = ensure_capability_catalog()
    rows = []
    for code in ('users.max', 'branches.max'):
        row, _ = CycleUsage.objects.update_or_create(
            subscription=subscription,
            capability=capabilities[code],
            period_start=subscription.current_period_start,
            defaults={
                'period_end': subscription.current_period_end,
                'quantity': resource_usage(subscription.company, code),
            },
        )
        rows.append(row)
    return rows


@transaction.atomic
def apply_user_limit_states(company, actor=None):
    company = Company.objects.select_for_update().get(pk=company.pk)
    entitlement = effective_entitlement(company, 'users.max')
    if not entitlement or not entitlement.enabled:
        raise ValidationError({'limit': 'O plano nao possui users.max valido.'})
    if entitlement.unlimited:
        suspended = list(UserCompanyAccess.objects.select_for_update().filter(
            company=company,
            saas_status=UserCompanyAccess.SaaSStatus.SUSPENDED_BY_PLAN_LIMIT,
        ))
        for access in suspended:
            access.saas_status = UserCompanyAccess.SaaSStatus.ACTIVE
            access.save(update_fields=('saas_status', 'updated_at'), enforce_saas_limit=False)
        return []

    accesses = list(UserCompanyAccess.objects.select_for_update(of=('self',)).filter(
        company=company,
        is_active=True,
        user__is_active=True,
        user__can_login=True,
    ).select_related('access_profile').order_by('created_at', 'pk'))
    limit = entitlement.limit_value
    priority = sorted(
        accesses,
        key=lambda item: (
            not item.is_owner,
            not bool(item.access_profile and item.access_profile.is_system and item.access_profile.name == 'Administrador'),
            item.updated_at,
            item.created_at,
            item.pk,
        ),
    )
    keep_ids = {item.pk for item in priority[:limit]}
    owner_ids = {item.pk for item in accesses if item.is_owner}
    keep_ids.update(owner_ids)
    suspended = []
    for access in accesses:
        target = (
            UserCompanyAccess.SaaSStatus.ACTIVE
            if access.pk in keep_ids
            else UserCompanyAccess.SaaSStatus.SUSPENDED_BY_PLAN_LIMIT
        )
        if access.saas_status != target:
            access.saas_status = target
            access.save(update_fields=('saas_status', 'updated_at'), enforce_saas_limit=False)
            if target == UserCompanyAccess.SaaSStatus.SUSPENDED_BY_PLAN_LIMIT:
                suspended.append(access)
    if suspended:
        audit_log(
            actor=actor,
            action='saas.user_limit.apply',
            company=company,
            metadata={
                'object_type': 'companies.UserCompanyAccess',
                'suspended_access_ids': [item.pk for item in suspended],
                'owner_preserved': True,
            },
        )
    return suspended


def validate_branch_limit_for_plan(company, plan_version):
    entitlement = PlanEntitlement.objects.filter(
        plan_version=plan_version, capability__code='branches.max', capability__is_active=True
    ).first()
    if not entitlement or not entitlement.enabled:
        raise ValidationError({'plan_version': 'O novo plano nao possui branches.max valido.'})
    if not entitlement.unlimited and resource_usage(company, 'branches.max') > entitlement.limit_value:
        raise ValidationError({
            'plan_version': 'A mudanca permanece pendente ate regularizar o excesso de filiais.'
        })


@transaction.atomic
def validate_user_login_activation(user):
    company_ids = list(UserCompanyAccess.objects.filter(
        user=user,
        is_active=True,
        saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
    ).values_list('company_id', flat=True))
    for company in Company.objects.select_for_update().filter(pk__in=company_ids).order_by('pk'):
        assert_resource_limit(company, 'users.max', company_locked=True)


def resolve_effective_status(company, at=None):
    at = at or timezone.now()
    if company.status != 'active':
        return {'status': 'OPERATIONALLY_INACTIVE', 'can_operate': False, 'subscription': None}
    state = TenantSaaSState.objects.filter(company=company).first()
    if state:
        if state.archived_at:
            return {'status': 'ARCHIVED', 'can_operate': False, 'subscription': current_subscription(company)}
        if state.admin_suspended_at:
            return {'status': 'SUSPENDED_ADMIN', 'can_operate': False, 'subscription': current_subscription(company)}
        if state.approval_status == TenantSaaSState.ApprovalStatus.PENDING:
            return {'status': 'PENDING_APPROVAL', 'can_operate': False, 'subscription': current_subscription(company)}
        if state.approval_status == TenantSaaSState.ApprovalStatus.REJECTED:
            return {'status': 'APPROVAL_REJECTED', 'can_operate': False, 'subscription': current_subscription(company)}

    subscription = current_subscription(company)
    if not subscription:
        latest = Subscription.objects.filter(company=company).order_by('-created_at', '-pk').first()
        if latest and latest.status == Subscription.Status.CANCELLED:
            return {'status': Subscription.Status.CANCELLED, 'can_operate': False, 'subscription': latest}
        if latest:
            return {'status': 'INVALID_SUBSCRIPTION', 'can_operate': False, 'subscription': latest}
        enforcement_enabled = get_global_settings().enforcement_enabled
        return {
            'status': 'UNMAPPED' if enforcement_enabled else 'LEGACY_UNMAPPED',
            'can_operate': not enforcement_enabled,
            'subscription': None,
        }
    required = {
        item.capability.code: item
        for item in PlanEntitlement.objects.filter(
            plan_version=subscription.plan_version,
            capability__code__in=REQUIRED_CAPABILITY_CODES,
            capability__is_active=True,
        ).select_related('capability')
    }
    limits_valid = all(
        code in required
        and required[code].enabled
        and (
            required[code].unlimited
            or required[code].limit_value is not None and required[code].limit_value >= 1
        )
        for code in ('users.max', 'branches.max')
    )
    if (
        set(required) != REQUIRED_CAPABILITY_CODES
        or not required['core.enabled'].enabled
        or not limits_valid
    ):
        return {'status': 'INVALID_ENTITLEMENTS', 'can_operate': False, 'subscription': subscription}
    if subscription.status == Subscription.Status.CANCELLED:
        return {'status': Subscription.Status.CANCELLED, 'can_operate': False, 'subscription': subscription}
    if subscription.cancel_at_period_end and at >= subscription.current_period_end:
        return {'status': Subscription.Status.CANCELLED, 'can_operate': False, 'subscription': subscription}
    if subscription.status == Subscription.Status.TRIALING:
        if at >= subscription.trial_ends_at:
            return {'status': Subscription.Status.TRIAL_EXPIRED, 'can_operate': False, 'subscription': subscription}
        return {'status': Subscription.Status.TRIALING, 'can_operate': True, 'subscription': subscription}
    if subscription.status == Subscription.Status.TRIAL_EXPIRED:
        return {'status': Subscription.Status.TRIAL_EXPIRED, 'can_operate': False, 'subscription': subscription}
    if subscription.status == Subscription.Status.SUSPENDED_FINANCIAL:
        return {'status': Subscription.Status.SUSPENDED_FINANCIAL, 'can_operate': False, 'subscription': subscription}
    if subscription.billing_mode in (Subscription.BillingMode.FREE, Subscription.BillingMode.INTERNAL):
        return {'status': Subscription.Status.ACTIVE, 'can_operate': True, 'subscription': subscription}
    if at < subscription.current_period_end:
        return {'status': Subscription.Status.ACTIVE, 'can_operate': True, 'subscription': subscription}

    overdue_days = (at - subscription.current_period_end).days
    global_settings = get_global_settings()
    if overdue_days < global_settings.past_due_days:
        status = Subscription.Status.PAST_DUE
        can_operate = True
    elif overdue_days < global_settings.restricted_after_days:
        status = Subscription.Status.RESTRICTED
        can_operate = False
    else:
        status = Subscription.Status.SUSPENDED_FINANCIAL
        can_operate = False
    return {'status': status, 'can_operate': can_operate, 'subscription': subscription}


@transaction.atomic
def process_subscription_lifecycle(subscription, at=None):
    at = at or timezone.now()
    subscription = Subscription.objects.select_for_update().select_related(
        'company', 'plan_version'
    ).get(pk=subscription.pk)
    before_state = (
        subscription.status, subscription.is_current, subscription.cancelled_at,
        subscription.current_period_start, subscription.current_period_end,
    )
    before = {
        'status': subscription.status,
        'is_current': subscription.is_current,
        'cancelled_at': subscription.cancelled_at.isoformat() if subscription.cancelled_at else None,
    }

    if (
        subscription.billing_mode in (Subscription.BillingMode.FREE, Subscription.BillingMode.INTERNAL)
        and subscription.status == Subscription.Status.ACTIVE
        and not subscription.cancel_at_period_end
    ):
        while subscription.current_period_end <= at:
            subscription.current_period_start = subscription.current_period_end
            subscription.current_period_end = add_months(
                subscription.current_period_end,
                subscription.plan_version.billing_period_months,
            )

    effective = resolve_effective_status(subscription.company, at=at)
    target = effective['status']
    if target in Subscription.Status.values:
        subscription.status = target
    if target == Subscription.Status.CANCELLED and not subscription.cancelled_at:
        subscription.cancelled_at = at
        subscription.is_current = False
    after_state = (
        subscription.status, subscription.is_current, subscription.cancelled_at,
        subscription.current_period_start, subscription.current_period_end,
    )
    after = {
        'status': subscription.status,
        'is_current': subscription.is_current,
        'cancelled_at': subscription.cancelled_at.isoformat() if subscription.cancelled_at else None,
    }
    changed = after_state != before_state
    if changed:
        subscription.save()
        audit_log(
            action='saas.subscription.lifecycle', obj=subscription, company=subscription.company,
            before=before, after=after,
            metadata={'processed_at': at.isoformat()},
        )
    sync_cycle_usage(subscription)
    return subscription, changed


def _subscription_dates(plan_version, now):
    if plan_version.trial_days:
        end = now + timedelta(days=plan_version.trial_days)
        return Subscription.Status.TRIALING, end, now, end
    end = add_months(now, plan_version.billing_period_months)
    return Subscription.Status.ACTIVE, end, None, None


@transaction.atomic
def provision_saas_tenant(
    *, source, idempotency_key, plan_version, company_data, owner_email=None,
    owner_password=None, owner_user=None, actor=None, billing_mode=None,
):
    idempotency_key = (idempotency_key or '').strip()
    if not idempotency_key:
        raise ValidationError({'idempotency_key': 'Informe a chave de idempotencia.'})
    global_settings = get_global_settings()
    if source == ProvisioningOperation.Source.PUBLIC_SIGNUP:
        billing_mode = global_settings.public_signup_billing_mode
    elif billing_mode not in Subscription.BillingMode.values:
        raise ValidationError({'billing_mode': 'Informe explicitamente PAID, FREE ou INTERNAL.'})
    payload = {
        'source': source,
        'plan_version_id': plan_version.pk,
        'company_data': company_data,
        'owner_email': owner_email.lower() if owner_email else None,
        'owner_user_id': owner_user.pk if owner_user else None,
        'billing_mode': billing_mode,
    }
    fingerprint = _fingerprint(payload)
    _advisory_transaction_lock('provisioning', f'{source}:{idempotency_key}')
    existing = ProvisioningOperation.objects.filter(
        source=source, idempotency_key=idempotency_key
    ).select_related('user', 'company', 'subscription').first()
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise ValidationError({'idempotency_key': 'A chave ja foi usada com outros dados.'})
        return existing, False

    plan_version = validate_plan_version_complete(plan_version, lock=True)
    if source == ProvisioningOperation.Source.PUBLIC_SIGNUP and not plan_version.is_public:
        raise ValidationError({'plan_version': 'A versao de plano nao esta disponivel publicamente.'})

    if owner_user is None:
        normalized_email = User.objects.normalize_email(owner_email or '').lower()
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise ValidationError({'owner_email': 'Este e-mail ja possui uma conta.'})
        candidate = User(email=normalized_email)
        validate_password(owner_password or '', user=candidate)
        owner_user = User.objects.create_user(email=normalized_email, password=owner_password)
    elif not owner_user.is_active or not owner_user.can_login:
        raise ValidationError({'owner_user': 'O Owner deve estar ativo e habilitado para login.'})

    company = create_company_with_matrix(
        creator=owner_user, enforce_saas_limits=False, **company_data
    )
    validate_branch_limit_for_plan(company, plan_version)
    approval = (
        TenantSaaSState.ApprovalStatus.APPROVED
        if source == ProvisioningOperation.Source.PLATFORM_MANUAL or global_settings.auto_approve_signups
        else TenantSaaSState.ApprovalStatus.PENDING
    )
    now = timezone.now()
    TenantSaaSState.objects.create(
        company=company,
        approval_status=approval,
        approved_at=now if approval == TenantSaaSState.ApprovalStatus.APPROVED else None,
        approved_by=actor if approval == TenantSaaSState.ApprovalStatus.APPROVED and actor else None,
    )
    subscription_status, period_end, trial_start, trial_end = _subscription_dates(plan_version, now)
    subscription = Subscription.objects.create(
        company=company,
        plan_version=plan_version,
        billing_mode=billing_mode,
        status=subscription_status,
        current_period_start=now,
        current_period_end=period_end,
        trial_started_at=trial_start,
        trial_ends_at=trial_end,
    )
    operation = ProvisioningOperation.objects.create(
        source=source,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        user=owner_user,
        company=company,
        subscription=subscription,
    )
    sync_cycle_usage(subscription)
    apply_user_limit_states(company, actor=actor)
    audit_log(
        actor=actor or owner_user,
        action='saas.tenant.provision', obj=operation, company=company,
        after={
            'company_id': company.pk,
            'subscription_id': subscription.pk,
            'owner_user_id': owner_user.pk,
            'approval_status': approval,
        },
        metadata={'source': source, 'idempotency_key': idempotency_key},
    )
    return operation, True


@transaction.atomic
def map_existing_company(*, company, plan_version, billing_mode, actor=None):
    company = Company.objects.select_for_update().get(pk=company.pk)
    if not _has_valid_owner(company):
        raise ValidationError({'company': 'A empresa precisa de Owner ativo antes do mapeamento.'})
    if billing_mode not in Subscription.BillingMode.values:
        raise ValidationError({'billing_mode': 'Informe explicitamente PAID, FREE ou INTERNAL.'})
    plan_version = validate_plan_version_complete(plan_version, lock=True)
    existing = Subscription.objects.select_for_update().filter(
        company=company, is_current=True
    ).first()
    if existing:
        if existing.plan_version_id == plan_version.pk and existing.billing_mode == billing_mode:
            return existing, False
        raise ValidationError({'company': 'A empresa ja possui uma assinatura corrente.'})
    validate_branch_limit_for_plan(company, plan_version)
    now = timezone.now()
    status, period_end, trial_start, trial_end = _subscription_dates(plan_version, now)
    subscription = Subscription.objects.create(
        company=company,
        plan_version=plan_version,
        billing_mode=billing_mode,
        status=status,
        current_period_start=now,
        current_period_end=period_end,
        trial_started_at=trial_start,
        trial_ends_at=trial_end,
    )
    TenantSaaSState.objects.get_or_create(
        company=company,
        defaults={
            'approval_status': TenantSaaSState.ApprovalStatus.APPROVED,
            'approved_at': now,
            'approved_by': actor,
        },
    )
    sync_cycle_usage(subscription)
    apply_user_limit_states(company, actor=actor)
    audit_log(
        actor=actor, action='saas.company.map', obj=subscription, company=company,
        after={'plan_version_id': plan_version.pk, 'billing_mode': billing_mode},
        metadata={'source': 'explicit_mapping'},
    )
    return subscription, True


@transaction.atomic
def approve_tenant(company, actor, reason=''):
    state = TenantSaaSState.objects.select_for_update().get(company=company)
    if state.approval_status == TenantSaaSState.ApprovalStatus.APPROVED:
        return state, False
    state.approval_status = TenantSaaSState.ApprovalStatus.APPROVED
    state.approval_reason = (reason or '').strip()
    state.approved_at = timezone.now()
    state.approved_by = actor
    state.save()
    audit_log(
        actor=actor, action='saas.tenant.approve', obj=state, company=company,
        after={'approval_status': state.approval_status}, metadata={'reason': state.approval_reason},
    )
    return state, True


@transaction.atomic
def set_admin_suspension(company, actor, reason, suspended):
    reason = (reason or '').strip()
    if suspended and not reason:
        raise ValidationError({'reason': 'Informe o motivo da suspensao administrativa.'})
    state = TenantSaaSState.objects.select_for_update().get(company=company)
    state.admin_suspended_at = timezone.now() if suspended else None
    state.admin_suspended_by = actor if suspended else None
    state.admin_suspension_reason = reason if suspended else ''
    state.save()
    audit_log(
        actor=actor,
        action='saas.tenant.admin_suspend' if suspended else 'saas.tenant.admin_resume',
        obj=state,
        company=company,
        after={'admin_suspended': suspended},
        metadata={'reason': reason},
    )
    return state


@transaction.atomic
def set_subscription_billing_mode(subscription, actor, billing_mode, reason):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo da alteracao comercial.'})
    if billing_mode not in Subscription.BillingMode.values:
        raise ValidationError({'billing_mode': 'Billing mode invalido.'})
    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
    if not subscription.is_current or subscription.status in (
        Subscription.Status.CANCELLED, Subscription.Status.SUPERSEDED
    ):
        raise ValidationError({'subscription': 'A assinatura nao e corrente.'})
    before = subscription.billing_mode
    subscription.billing_mode = billing_mode
    if billing_mode in (Subscription.BillingMode.FREE, Subscription.BillingMode.INTERNAL) and subscription.status in (
        Subscription.Status.PAST_DUE,
        Subscription.Status.RESTRICTED,
        Subscription.Status.SUSPENDED_FINANCIAL,
    ):
        subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=('billing_mode', 'status', 'updated_at'))
    audit_log(
        actor=actor, action='saas.subscription.billing_mode.change', obj=subscription,
        company=subscription.company, before={'billing_mode': before},
        after={'billing_mode': billing_mode}, metadata={'reason': reason},
    )
    return subscription


@transaction.atomic
def set_financial_suspension(subscription, actor, reason, suspended):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo da acao financeira.'})
    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
    if not subscription.is_current or subscription.status in (
        Subscription.Status.CANCELLED,
        Subscription.Status.SUPERSEDED,
        Subscription.Status.TRIALING,
        Subscription.Status.TRIAL_EXPIRED,
    ):
        raise ValidationError({'subscription': 'O estado atual nao aceita esta acao financeira.'})
    before = subscription.status
    if suspended:
        subscription.status = Subscription.Status.SUSPENDED_FINANCIAL
    else:
        subscription.status = (
            Subscription.Status.ACTIVE
            if subscription.billing_mode in (
                Subscription.BillingMode.FREE,
                Subscription.BillingMode.INTERNAL,
            ) or timezone.now() < subscription.current_period_end
            else Subscription.Status.PAST_DUE
        )
    subscription.save(update_fields=('status', 'updated_at'))
    audit_log(
        actor=actor,
        action='saas.subscription.financial_suspend' if suspended else 'saas.subscription.financial_resume',
        obj=subscription, company=subscription.company,
        before={'status': before}, after={'status': subscription.status},
        metadata={'reason': reason},
    )
    return subscription


@transaction.atomic
def extend_subscription_trial(subscription, actor, days, reason):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo da prorrogacao.'})
    if not 1 <= days <= 365:
        raise ValidationError({'days': 'Informe uma prorrogacao entre 1 e 365 dias.'})
    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
    if not subscription.is_current or subscription.status not in (
        Subscription.Status.TRIALING, Subscription.Status.TRIAL_EXPIRED
    ):
        raise ValidationError({'subscription': 'Somente trial corrente pode ser prorrogado.'})
    now = timezone.now()
    previous_end = subscription.trial_ends_at
    base = max(filter(None, (now, subscription.trial_ends_at)))
    subscription.trial_started_at = subscription.trial_started_at or now
    subscription.trial_ends_at = base + timedelta(days=days)
    subscription.current_period_end = subscription.trial_ends_at
    if subscription.current_period_start >= subscription.current_period_end:
        subscription.current_period_start = now
    subscription.status = Subscription.Status.TRIALING
    subscription.save()
    audit_log(
        actor=actor, action='saas.subscription.trial.extend', obj=subscription,
        company=subscription.company, before={'trial_ends_at': str(previous_end)},
        after={'trial_ends_at': str(subscription.trial_ends_at)},
        metadata={'reason': reason, 'days': days},
    )
    return subscription


@transaction.atomic
def archive_tenant(company, actor, reason):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo do arquivamento.'})
    state = TenantSaaSState.objects.select_for_update().get(company=company)
    if state.archived_at:
        return state, False
    state.archived_at = timezone.now()
    state.archived_by = actor
    state.archive_reason = reason
    state.save(update_fields=('archived_at', 'archived_by', 'archive_reason', 'updated_at'))
    audit_log(
        actor=actor, action='saas.tenant.archive', obj=state, company=company,
        after={'archived': True}, metadata={'reason': reason},
    )
    return state, True


@transaction.atomic
def reject_tenant(company, actor, reason):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo da rejeicao.'})
    state = TenantSaaSState.objects.select_for_update().get(company=company)
    if state.approval_status == TenantSaaSState.ApprovalStatus.APPROVED:
        raise ValidationError({'approval_status': 'Tenant aprovado deve ser suspenso ou arquivado, nao rejeitado.'})
    state.approval_status = TenantSaaSState.ApprovalStatus.REJECTED
    state.approval_reason = reason
    state.save(update_fields=('approval_status', 'approval_reason', 'updated_at'))
    audit_log(
        actor=actor, action='saas.tenant.reject', obj=state, company=company,
        after={'approval_status': state.approval_status}, metadata={'reason': reason},
    )
    return state


@transaction.atomic
def record_manual_payment(
    *, subscription, actor, idempotency_key, amount, paid_at, payment_method,
    competency_start=None, competency_end=None, note='', proof_reference='',
):
    idempotency_key = (idempotency_key or '').strip()
    if not idempotency_key:
        raise ValidationError({'idempotency_key': 'Informe a chave de idempotencia.'})
    proof_reference = (proof_reference or '').strip()
    payload = {
        'amount': str(Decimal(amount)), 'paid_at': paid_at, 'payment_method': payment_method,
        'competency_start': competency_start, 'competency_end': competency_end, 'note': note,
        'proof_reference': proof_reference,
    }
    fingerprint = _fingerprint(payload)
    subscription = Subscription.objects.select_for_update().select_related('plan_version').get(
        pk=subscription.pk
    )
    existing = BillingRecord.objects.filter(
        subscription=subscription, idempotency_key=idempotency_key
    ).first()
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise ValidationError({'idempotency_key': 'A chave ja foi usada com outro pagamento.'})
        return existing, False
    if subscription.billing_mode != Subscription.BillingMode.PAID:
        raise ValidationError({'subscription': 'Pagamento manual exige billing mode PAID.'})
    if not subscription.is_current or subscription.status in (
        Subscription.Status.CANCELLED,
        Subscription.Status.SUPERSEDED,
        Subscription.Status.TRIAL_EXPIRED,
        Subscription.Status.TRIALING,
    ) or subscription.cancel_at_period_end:
        raise ValidationError({'subscription': 'O estado atual nao aceita regularizacao por pagamento.'})
    if Decimal(amount) != subscription.plan_version.price:
        raise ValidationError({'amount': 'O valor deve corresponder ao preco contratado da PlanVersion.'})
    now = timezone.now()
    if competency_start is None and competency_end is None:
        if subscription.current_period_end > now:
            competency_start = subscription.current_period_start
            competency_end = subscription.current_period_end
        else:
            competency_start = subscription.current_period_end
            competency_end = add_months(
                competency_start, subscription.plan_version.billing_period_months
            )
            while competency_end <= now:
                competency_start = competency_end
                competency_end = add_months(
                    competency_end, subscription.plan_version.billing_period_months
                )
        current_period = competency_start == subscription.current_period_start
        renewal_period = competency_start >= subscription.current_period_end
    elif competency_start is None or competency_end is None:
        raise ValidationError({
            'competency_start': 'Informe inicio e fim da competencia juntos ou omita ambos.'
        })
    else:
        expected_end = add_months(
            competency_start, subscription.plan_version.billing_period_months
        )
        if competency_end != expected_end:
            raise ValidationError({'competency_end': 'A competencia deve respeitar o ciclo contratado.'})
        current_period = (
            competency_start == subscription.current_period_start
            and competency_end == subscription.current_period_end
        )
        renewal_period = competency_start == subscription.current_period_end
        if not current_period and not renewal_period:
            raise ValidationError({
                'competency_start': 'A competencia deve ser o ciclo atual ou o proximo ciclo contiguo.'
            })
    if proof_reference and not SAFE_PROOF_REFERENCE.fullmatch(proof_reference):
        raise ValidationError({'proof_reference': 'Informe uma referencia HTTPS ou identificador seguro.'})
    record = BillingRecord.objects.create(
        subscription=subscription,
        actor=actor,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        amount=amount,
        paid_at=paid_at,
        payment_method=payment_method.strip(),
        competency_start=competency_start,
        competency_end=competency_end,
        note=(note or '').strip(),
        proof_reference=proof_reference,
    )
    if renewal_period:
        subscription.current_period_start = competency_start
        subscription.current_period_end = competency_end
    if competency_end > now and subscription.status in (
        Subscription.Status.PAST_DUE,
        Subscription.Status.RESTRICTED,
        Subscription.Status.SUSPENDED_FINANCIAL,
    ):
        subscription.status = Subscription.Status.ACTIVE
    subscription.save()
    sync_cycle_usage(subscription)
    audit_log(
        actor=actor, action='saas.payment.record', obj=record, company=subscription.company,
        after={'amount': str(record.amount), 'competency_start': str(competency_start), 'competency_end': str(competency_end)},
        metadata={'idempotency_key': idempotency_key},
    )
    return record, True


@transaction.atomic
def request_plan_change(subscription, actor, requested_plan_version, reason):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo da mudanca.'})
    validate_plan_version_complete(requested_plan_version)
    request = SubscriptionRequest.objects.create(
        subscription=subscription,
        request_type=SubscriptionRequest.RequestType.PLAN_CHANGE,
        requested_plan_version=requested_plan_version,
        reason=reason,
        requested_by=actor,
    )
    audit_log(actor=actor, action='saas.plan_change.request', obj=request, company=subscription.company)
    return request


@transaction.atomic
def request_cancellation(subscription, actor, reason):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo do cancelamento.'})
    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
    subscription.cancel_at_period_end = True
    subscription.cancellation_reason = reason
    subscription.save(update_fields=('cancel_at_period_end', 'cancellation_reason', 'updated_at'))
    request = SubscriptionRequest.objects.create(
        subscription=subscription,
        request_type=SubscriptionRequest.RequestType.CANCELLATION,
        reason=reason,
        status=SubscriptionRequest.Status.APPROVED,
        requested_by=actor,
        resolved_by=actor,
        resolved_at=timezone.now(),
    )
    audit_log(
        actor=actor, action='saas.cancellation.request', obj=request, company=subscription.company,
        after={'cancel_at_period_end': True}, metadata={'reason': reason},
    )
    return request


@transaction.atomic
def resolve_subscription_request(subscription_request, actor, approved, reason=''):
    request = SubscriptionRequest.objects.select_for_update(of=('self',)).select_related(
        'subscription__company', 'requested_plan_version'
    ).get(pk=subscription_request.pk)
    if request.status != SubscriptionRequest.Status.PENDING:
        return request, False
    if request.request_type != SubscriptionRequest.RequestType.PLAN_CHANGE:
        raise ValidationError({'request': 'Somente mudancas de plano pendentes exigem resolucao.'})
    now = timezone.now()
    if approved:
        old = Subscription.objects.select_for_update().get(pk=request.subscription_id)
        if not old.is_current:
            raise ValidationError({'subscription': 'A assinatura solicitante nao e mais corrente.'})
        company = Company.objects.select_for_update().get(pk=old.company_id)
        requested_plan = validate_plan_version_complete(
            request.requested_plan_version, lock=True
        )
        validate_branch_limit_for_plan(company, requested_plan)
        old.is_current = False
        old.status = Subscription.Status.SUPERSEDED
        old.save(update_fields=('is_current', 'status', 'updated_at'))
        replacement = Subscription.objects.create(
            company=old.company,
            plan_version=requested_plan,
            billing_mode=old.billing_mode,
            status=Subscription.Status.ACTIVE,
            current_period_start=now,
            current_period_end=add_months(
                now, requested_plan.billing_period_months
            ),
        )
        apply_user_limit_states(company, actor=actor)
        sync_cycle_usage(replacement)
        request.status = SubscriptionRequest.Status.APPROVED
    else:
        request.status = SubscriptionRequest.Status.REJECTED
    request.resolved_by = actor
    request.resolved_at = now
    request.save(update_fields=('status', 'resolved_by', 'resolved_at', 'updated_at'))
    audit_log(
        actor=actor,
        action='saas.plan_change.approve' if approved else 'saas.plan_change.reject',
        obj=request,
        company=request.subscription.company,
        after={'status': request.status},
        metadata={'reason': (reason or '').strip()},
    )
    return request, True


@transaction.atomic
def create_support_session(*, actor, company, mode, reason, current_password='', impersonated_user=None, expires_at=None):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo do acesso de suporte.'})
    if not user_has_platform_permission(actor, 'platform.support.manage'):
        raise ValidationError({'actor': 'A permissao de suporte nao esta ativa.'})
    if mode == SupportSession.Mode.READ_WRITE and not actor.check_password(current_password or ''):
        raise ValidationError({'current_password': 'Senha atual invalida.'})
    if impersonated_user and not UserCompanyAccess.objects.filter(
        company=company, user=impersonated_user, is_active=True,
        saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        user__is_active=True, user__can_login=True,
    ).exists():
        raise ValidationError({'impersonated_user': 'O usuario nao pertence a empresa.'})
    now = timezone.now()
    maximum_expiry = now + timedelta(minutes=get_global_settings().support_session_minutes)
    expires_at = expires_at or maximum_expiry
    if expires_at <= now:
        raise ValidationError({'expires_at': 'A expiracao deve estar no futuro.'})
    if expires_at > maximum_expiry:
        raise ValidationError({'expires_at': 'A expiracao excede o limite global permitido.'})
    session = SupportSession.objects.create(
        actor=actor,
        company=company,
        impersonated_user=impersonated_user,
        mode=mode,
        reason=reason,
        expires_at=expires_at,
    )
    audit_log(
        actor=actor, action='saas.support.start', obj=session, company=company,
        after={'mode': mode, 'expires_at': expires_at.isoformat(), 'impersonated_user_id': session.impersonated_user_id},
        metadata={'reason': reason},
    )
    return session


@transaction.atomic
def end_support_session(session, actor):
    session = SupportSession.objects.select_for_update().get(pk=session.pk)
    if session.ended_at:
        return session, False
    session.ended_at = timezone.now()
    session.ended_by = actor
    session.save(update_fields=('ended_at', 'ended_by', 'updated_at'))
    audit_log(actor=actor, action='saas.support.end', obj=session, company=session.company)
    return session, True
