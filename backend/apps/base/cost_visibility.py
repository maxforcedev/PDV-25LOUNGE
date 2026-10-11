from copy import deepcopy

from apps.companies.selectors import user_has_branch_permission
from apps.saas.permissions import support_permission_decision


_COST_KEYS = frozenset({
    'stock_product_cost', 'unit_cost', 'unit_cost_snapshot',
    'unit_cost_contribution', 'average_unit_cost', 'last_unit_cost',
    'component_cost_snapshot', 'cost_total', 'total_cost', 'cost_impact',
    'inventory_cost_impact', 'estimated_cost', 'estimated_value',
    'inventory_value', 'margin_amount', 'margin_percentage',
})


def can_view_branch_costs(request, branch_id, *, permission_codes=None):
    if permission_codes is not None:
        return 'inventory.view_stock_costs' in permission_codes
    if not request or not branch_id:
        return False
    support = support_permission_decision(request, branch_id=branch_id)
    if support is not None:
        return support
    user = request.user
    return user.is_superuser or user_has_branch_permission(
        user, branch_id, 'inventory.view_stock_costs',
    )


def can_view_branch_commissions(request, branch_id, *, permission_codes=None):
    if permission_codes is not None:
        return 'commissions.view' in permission_codes
    if not request or not branch_id:
        return False
    support = support_permission_decision(request, branch_id=branch_id)
    if support is not None:
        return support
    user = request.user
    return user.is_superuser or user_has_branch_permission(
        user, branch_id, 'commissions.view',
    )


def redact_cost_payload(value, *, include_costs):
    """Return a copy safe for responses without changing historical snapshots."""
    if include_costs:
        return deepcopy(value)
    if isinstance(value, dict):
        return {
            key: redact_cost_payload(item, include_costs=False)
            for key, item in value.items()
            if not _is_cost_key(key)
        }
    if isinstance(value, list):
        return [redact_cost_payload(item, include_costs=False) for item in value]
    return deepcopy(value)


def _is_cost_key(key):
    normalized = str(key).lower()
    return (
        normalized in _COST_KEYS
        or 'component_cost' in normalized
        or normalized.startswith(('average_cost', 'last_cost'))
    )
