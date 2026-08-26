from rest_framework import serializers

from apps.companies.selectors import user_has_branch_permission
from apps.sales.serializers import readable_user_name

from .models import AuditLog
from .labels import audit_changes_values, audit_labels, audit_module_key


PURCHASE_COST_KEYS = frozenset({
    'amount', 'gross_total', 'global_discount', 'freight_total',
    'other_expenses_total', 'payable_total', 'purchase_unit_price',
    'gross_subtotal', 'allocated_discount', 'allocated_freight',
    'allocated_other_expenses', 'effective_total',
    'effective_stock_unit_cost', 'effective_stock_unit_cost_snapshot',
})
BRANCH_COST_KEYS = frozenset({
    'average_unit_cost', 'last_unit_cost', 'unit_cost', 'unit_cost_snapshot',
    'unit_cost_contribution', 'component_cost_snapshot', 'estimated_cost',
    'origin_unit_cost_snapshot', 'cost_impact', 'inventory_cost_impact',
    'loss_cost_impact', 'pending_divergence_cost_impact',
    'transfer_dispatched_cost_value', 'transfer_received_cost_value',
    'in_transit_cost_value',
    'total_cost', 'inventory_value', 'estimated_value',
})
_OMIT = object()


def _filter_cost_payload(value, *, purchase_module, can_purchase_costs,
                         can_stock_costs, field_name=None):
    normalized = str(field_name or '').lower()
    if not can_purchase_costs and purchase_module and normalized in PURCHASE_COST_KEYS:
        return _OMIT
    if not can_stock_costs and (
        normalized in BRANCH_COST_KEYS
        or 'component_cost' in normalized
        or normalized.startswith(('average_cost', 'last_cost'))
    ):
        return _OMIT
    if isinstance(value, dict):
        filtered = {}
        for key, item in value.items():
            visible = _filter_cost_payload(
                item,
                purchase_module=purchase_module,
                can_purchase_costs=can_purchase_costs,
                can_stock_costs=can_stock_costs,
                field_name=key,
            )
            if visible is not _OMIT:
                filtered[key] = visible
        return filtered
    if isinstance(value, list):
        return [
            visible
            for item in value
            if (visible := _filter_cost_payload(
                item,
                purchase_module=purchase_module,
                can_purchase_costs=can_purchase_costs,
                can_stock_costs=can_stock_costs,
                field_name=field_name,
            )) is not _OMIT
        ]
    return value


class AuditLogSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    actor_name = serializers.SerializerMethodField()
    action_label = serializers.SerializerMethodField()
    module_label = serializers.SerializerMethodField()
    object_label = serializers.SerializerMethodField()
    changes = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            'id', 'company', 'company_name', 'branch', 'branch_name', 'actor',
            'actor_name', 'action', 'action_label', 'module_label', 'object_label',
            'object_type', 'object_id', 'changes', 'before', 'after',
            'metadata', 'created_at',
        )

    def get_actor_name(self, log):
        return readable_user_name(log.actor) if log.actor_id else None

    def get_action_label(self, log):
        return audit_labels(log)['action_label']

    def get_module_label(self, log):
        return audit_labels(log)['module_label']

    def get_object_label(self, log):
        return audit_labels(log)['object_label']

    def get_changes(self, log):
        before, after, _metadata = self._visible_payloads(log)
        return audit_changes_values(before, after)

    def _visible_payloads(self, log):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        support_session = getattr(request, 'support_session', None) if request else None
        unrestricted_support = bool(
            support_session
            and not support_session.impersonated_user_id
            and support_session.company_id == log.company_id
        )
        branch_id = log.branch_id
        can_purchase_costs = bool(
            user
            and (
                user.is_superuser
                or unrestricted_support
                or branch_id and user_has_branch_permission(
                    user, branch_id, 'purchases.view_costs'
                )
            )
        )
        can_stock_costs = bool(
            user
            and (
                user.is_superuser
                or unrestricted_support
                or branch_id and user_has_branch_permission(
                    user, branch_id, 'inventory.view_stock_costs'
                )
            )
        )
        purchase_module = audit_module_key(log.action, log.object_type) == 'purchases'
        options = {
            'purchase_module': purchase_module,
            'can_purchase_costs': can_purchase_costs,
            'can_stock_costs': can_stock_costs,
        }
        return (
            _filter_cost_payload(log.before or {}, **options),
            _filter_cost_payload(log.after or {}, **options),
            _filter_cost_payload(log.metadata or {}, **options),
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        before, after, metadata = self._visible_payloads(instance)
        data['before'] = before
        data['after'] = after
        data['metadata'] = metadata
        data['changes'] = audit_changes_values(before, after)
        return data
