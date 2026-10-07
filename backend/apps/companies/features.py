from rest_framework.exceptions import PermissionDenied

from .models import BranchSettings


FEATURE_CAPABILITIES = {
    'tables': 'feature.tables',
    'commands': 'feature.commands',
    'counter': 'feature.counter',
    'consumption': 'feature.consumption',
    'cash_register': 'feature.cash_register',
    'production': 'feature.production',
    'products': 'feature.products',
    'inventory': 'feature.inventory',
    'purchases': 'feature.purchases',
    'suppliers': 'feature.suppliers',
    'customers': 'feature.customers',
    'promotions': 'feature.promotions',
    'reports': 'feature.reports',
    'audit': 'feature.audit',
    'financial': 'feature.financial',
    'pos': 'pos.enabled',
}

FEATURE_LABELS = {
    'tables': 'Mesas',
    'commands': 'Comandas',
    'counter': 'Balcão',
    'consumption': 'Consumação',
    'cash_register': 'Caixa',
    'production': 'Produção e impressão',
    'products': 'Produtos e catálogo',
    'inventory': 'Estoque',
    'purchases': 'Compras',
    'suppliers': 'Fornecedores',
    'customers': 'Clientes',
    'promotions': 'Promoções',
    'reports': 'Relatórios',
    'audit': 'Auditoria',
    'financial': 'Financeiro',
    'pos': 'CORE POS',
}

# RBAC definitions are durable records.  This map is only used when building
# current operational catalogs, so a disabled capability never deletes history.
PERMISSION_FEATURE_PREFIXES = {
    'audit': 'audit',
    'cash_registers': 'cash_register',
    'categories': 'products',
    'commands': 'commands',
    'consumption': 'consumption',
    'customers': 'customers',
    'dashboard': 'reports',
    'inventory': 'inventory',
    'payment_methods': 'financial',
    'pos_devices': 'pos',
    'printers': 'production',
    'print_documents': 'production',
    'print_jobs': 'production',
    'print_routes': 'production',
    'products': 'products',
    'promotions': 'promotions',
    'purchases': 'purchases',
    'reports': 'reports',
    'sales': 'counter',
    'suppliers': 'suppliers',
    'tables': 'tables',
    'tickets': 'production',
    'production': 'production',
}


def branch_feature_states(branch):
    """Resolve plano e configuração da filial sem misturar essa decisão ao RBAC."""
    try:
        settings = branch.settings
    except BranchSettings.DoesNotExist:
        settings = BranchSettings()
    flags = settings.feature_flags()
    # These modules have no branch-specific switch; their plan entitlement is decisive.
    for feature in FEATURE_CAPABILITIES:
        flags.setdefault(feature, True)

    from apps.saas.services import (
        effective_entitlement, get_entitled_features, resolve_effective_status,
    )

    entitled = get_entitled_features(branch.company)
    operational = resolve_effective_status(branch.company)['can_operate']
    states = {
        feature: {
            'enabled': enabled and (
                capability is None
                or capability in entitled
                or bool(
                    operational
                    and not capability.startswith('feature.')
                    and (entitlement := effective_entitlement(branch.company, capability))
                    and entitlement.enabled
                )
            ),
            'plan_allowed': capability is None or capability in entitled or bool(
                operational
                and not capability.startswith('feature.')
                and (entitlement := effective_entitlement(branch.company, capability))
                and entitlement.enabled
            ),
        }
        for feature, enabled in flags.items()
        for capability in (FEATURE_CAPABILITIES.get(feature),)
    }
    # Financial operation modules cannot be available without the Caixa feature.
    cash_enabled = states['cash_register']['enabled']
    for feature in ('counter', 'consumption', 'commands'):
        states[feature]['enabled'] = states[feature]['enabled'] and cash_enabled
    return states


def branch_feature_enabled(branch, feature):
    state = branch_feature_states(branch).get(feature)
    return bool(state and state['enabled'])


def require_branch_feature(branch, feature):
    state = branch_feature_states(branch).get(feature)
    if state is None:
        raise PermissionDenied('Funcionalidade operacional inválida.')
    label = FEATURE_LABELS.get(feature, feature)
    if not state['plan_allowed']:
        raise PermissionDenied(f'O plano não permite a funcionalidade {label}.')
    if not state['enabled']:
        raise PermissionDenied(f'A funcionalidade {label} está desativada nesta filial.')


def permission_feature(code):
    """Return the capability governing an operational permission code."""
    return PERMISSION_FEATURE_PREFIXES.get(str(code or '').split('.', 1)[0])


def capability_visible_permission_codes(branch, codes):
    return {
        code for code in codes
        if (feature := permission_feature(code)) is None
        or branch_feature_enabled(branch, feature)
    }
