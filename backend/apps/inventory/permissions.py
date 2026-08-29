from rest_framework.permissions import BasePermission

from apps.companies.models import Branch
from apps.companies.selectors import user_has_branch_permission
from apps.saas.permissions import support_permission_decision


class InventoryFunctionalPermission(BasePermission):
    message = 'Você não possui permissão para esta operação.'

    def get_code(self, view):
        return view.permission_codes.get(view.action)

    def get_codes(self, view):
        code = self.get_code(view)
        return code if isinstance(code, tuple) else (code,)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if request.method == 'DELETE' and not getattr(view, 'action', None):
            return True
        codes = self.get_codes(view)
        if not all(codes):
            return False
        branch_id = request.headers.get('X-Branch-ID')
        support = support_permission_decision(request, branch_id=branch_id)
        if support is not None:
            return support
        if user.is_superuser and not branch_id:
            return True
        if not branch_id:
            return False
        try:
            request.branch_context = Branch.objects.get(pk=branch_id)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
        return user.is_superuser or any(
            user_has_branch_permission(user, branch_id, code) for code in codes
        )

    def has_object_permission(self, request, view, obj):
        support = support_permission_decision(request, obj=obj)
        if support is not None:
            return support
        if hasattr(obj, 'origin_branch_id'):
            branch_ids = {obj.origin_branch_id, obj.destination_branch_id}
        elif getattr(obj, 'transfer_item_id', None):
            transfer = obj.transfer_item.transfer
            branch_ids = {transfer.origin_branch_id, transfer.destination_branch_id}
        elif hasattr(obj, 'stock_id'):
            branch_ids = {obj.stock.branch_id}
        else:
            branch_ids = {obj.branch_id}
        branch = getattr(request, 'branch_context', None)
        if request.user.is_superuser:
            return branch is None or branch.pk in branch_ids
        return bool(
            branch
            and branch.pk in branch_ids
            and any(
                user_has_branch_permission(request.user, branch.pk, code)
                for code in self.get_codes(view)
            )
        )
