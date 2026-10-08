from decimal import Decimal

from apps.accounts.models import User
from apps.companies.services import create_company_with_matrix
from apps.saas.models import Plan, PlanEntitlement, PlanVersion, Subscription
from apps.saas.services import (
    current_subscription,
    ensure_capability_catalog,
    map_existing_company,
    resolve_capability_dependencies,
)


COMMERCIAL_FEATURES = (
    'tables', 'commands', 'counter', 'consumption', 'cash_register', 'production',
    'products', 'inventory', 'purchases', 'suppliers', 'customers', 'promotions',
    'reports', 'audit', 'financial',
)


def create_complete_test_plan(
    code,
    *,
    enabled_features=COMMERCIAL_FEATURES,
    pos_enabled=True,
    users=10,
    branches=10,
    price=Decimal('10.00'),
    trial_days=0,
):
    """Create an operational plan for tests that are not exercising SaaS denial paths."""
    code = str(code)[:50]
    capabilities = ensure_capability_catalog()
    plan, _ = Plan.objects.get_or_create(code=code, defaults={'name': code})
    version, created = PlanVersion.objects.get_or_create(
        plan=plan,
        version=1,
        defaults={'price': price, 'trial_days': trial_days},
    )
    if not created:
        return version
    boolean_capabilities = ('core.enabled', 'pos.enabled')
    for capability_code in boolean_capabilities:
        enabled = pos_enabled if capability_code == 'pos.enabled' else True
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities[capability_code],
            enabled=enabled,
            unlimited=enabled,
        )
    for capability_code, limit in (('users.max', users), ('branches.max', branches)):
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities[capability_code],
            limit_value=limit,
        )
    PlanEntitlement.objects.create(
        plan_version=version,
        capability=capabilities['pos.devices.max'],
        enabled=pos_enabled,
        limit_value=10 if pos_enabled else None,
    )
    enabled_features = {
        capability_code.removeprefix('feature.')
        for capability_code in resolve_capability_dependencies(
            {f'feature.{feature}' for feature in enabled_features}
        )
    }
    for feature in COMMERCIAL_FEATURES:
        enabled = feature in enabled_features
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities[f'feature.{feature}'],
            enabled=enabled,
            unlimited=enabled,
        )
    return version


def create_operational_company_with_matrix(
    *, creator, code='test-operational', plan_version=None, **company_data,
):
    """Create a mapped tenant for non-SaaS tests after the matrix bootstrap."""
    plan_version = plan_version or create_complete_test_plan(code)
    company = create_company_with_matrix(
        creator=creator,
        enforce_saas_limits=False,
        **company_data,
    )
    map_existing_company(
        company=company,
        plan_version=plan_version,
        billing_mode=Subscription.BillingMode.PAID,
    )
    return company


def create_operational_test_tenant(
    *,
    code,
    email,
    trade_name,
    legal_name,
    password='password-123',
    plan_version=None,
):
    owner = User.objects.create_user(email=email, password=password)
    company = create_operational_company_with_matrix(
        creator=owner,
        code=code,
        plan_version=plan_version,
        trade_name=trade_name,
        legal_name=legal_name,
    )
    subscription = current_subscription(company)
    return owner, company, subscription
