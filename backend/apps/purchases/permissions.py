from rest_framework.permissions import BasePermission

from apps.companies.models import Branch
from apps.companies.selectors import user_has_branch_permission
from apps.saas.permissions import support_permission_decision


class PurchaseFunctionalPermission(BasePermission):
    message = 'Voce nao possui permissao para esta operacao.'

    @staticmethod
    def _codes(view):
        codes = view.permission_codes.get(view.action)
        return codes if isinstance(codes, tuple) else (codes,)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        codes = tuple(code for code in self._codes(view) if code)
        if not codes:
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
            request.branch_context = Branch.objects.select_related('company').get(pk=branch_id)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
        return user.is_superuser or any(
            user_has_branch_permission(user, branch_id, code) for code in codes
        )

    def has_object_permission(self, request, view, obj):
        order = getattr(obj, 'purchase_order', obj)
        branch_id = order.branch_id
        support = support_permission_decision(request, obj=order)
        if support is not None:
            return support
        branch = getattr(request, 'branch_context', None)
        if request.user.is_superuser:
            return branch is None or branch.pk == branch_id
        return bool(
            branch
            and branch.pk == branch_id
            and any(
                user_has_branch_permission(request.user, branch_id, code)
                for code in self._codes(view) if code
            )
        )
