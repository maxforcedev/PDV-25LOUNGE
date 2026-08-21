from rest_framework.permissions import BasePermission

from apps.companies.models import Branch
from apps.companies.selectors import user_has_branch_permission


class InventoryFunctionalPermission(BasePermission):
    message = 'Você não possui permissão para esta operação.'

    def get_code(self, view):
        return view.permission_codes.get(view.action)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        code = self.get_code(view)
        if not code:
            return False
        branch_id = request.headers.get('X-Branch-ID')
        if user.is_superuser and not branch_id:
            return True
        if not branch_id:
            return False
        try:
            request.branch_context = Branch.objects.get(pk=branch_id)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
        return user.is_superuser or user_has_branch_permission(user, branch_id, code)

    def has_object_permission(self, request, view, obj):
        branch_id = obj.stock.branch_id if hasattr(obj, 'stock_id') else obj.branch_id
        branch = getattr(request, 'branch_context', None)
        if request.user.is_superuser:
            return branch is None or branch.pk == branch_id
        return bool(
            branch
            and branch.pk == branch_id
            and user_has_branch_permission(
                request.user, branch_id, self.get_code(view)
            )
        )
