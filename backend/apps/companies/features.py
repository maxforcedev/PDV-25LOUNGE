from rest_framework.exceptions import PermissionDenied

from .models import BranchSettings


FEATURE_CAPABILITIES = {
    'tables': 'feature.tables',
    'commands': 'feature.commands',
    'counter': 'feature.counter',
    'consumption': 'feature.consumption',
    'cash_register': 'feature.cash_register',
    'production': 'feature.production',
}

FEATURE_LABELS = {
    'tables': 'Mesas',
    'commands': 'Comandas',
    'counter': 'Balcão',
    'consumption': 'Consumação',
    'cash_register': 'Caixa',
    'production': 'Produção e impressão',
}


def branch_feature_states(branch):
    """Resolve plano e configuração da filial sem misturar essa decisão ao RBAC."""
    try:
        settings = branch.settings
    except BranchSettings.DoesNotExist:
        settings = BranchSettings()
    flags = settings.feature_flags()
    # Production serves direct sales as well as commands, so it is not coupled to commands.
    flags['production'] = True

    from apps.saas.services import get_entitled_features

    entitled = get_entitled_features(branch.company)
    states = {
        feature: {
            'enabled': enabled and (
                capability is None or capability in entitled
            ),
            'plan_allowed': capability is None or capability in entitled,
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
