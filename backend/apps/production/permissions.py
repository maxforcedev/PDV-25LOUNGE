from apps.inventory.permissions import InventoryFunctionalPermission
from apps.companies.features import require_branch_feature


class ProductionFunctionalPermission(InventoryFunctionalPermission):
    def has_permission(self, request, view):
        allowed = super().has_permission(request, view)
        if allowed:
            require_branch_feature(request.branch_context, 'production')
        return allowed
