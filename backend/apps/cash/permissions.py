from rest_framework.permissions import BasePermission

from apps.companies.features import require_branch_feature
from apps.companies.models import Branch
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.companies.selectors import (
    accessible_branches,
    user_has_branch_permission,
    user_has_company_permission,
)
from apps.saas.permissions import support_permission_decision


class CashFunctionalPermission(BasePermission):
    message = 'Você não possui permissão para esta operação nesta filial.'

    def get_code(self, view):
        return view.permission_codes.get(view.action)

    def get_codes(self, view):
        code = self.get_code(view)
        return code if isinstance(code, tuple) else (code,)

    @staticmethod
    def _requires_cash_feature(view):
        if view.basename == 'cash-register':
            return view.action not in ('list', 'retrieve')
        return view.action in ('open', 'entry', 'withdrawal')

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if not view.action:
            return True
        codes = self.get_codes(view)
        if not all(codes):
            return False
        branch_id = request.headers.get('X-Branch-ID')
        support = support_permission_decision(request, branch_id=branch_id)
        if support is False:
            return False
        if support:
            branch = request.branch_context
        elif user.is_superuser:
            if not branch_id:
                return False
            try:
                branch = Branch.objects.get(pk=branch_id)
            except (Branch.DoesNotExist, TypeError, ValueError):
                return False
            request.branch_context = branch
        else:
            if not branch_id:
                return False
            try:
                branch = Branch.objects.get(pk=branch_id)
            except (Branch.DoesNotExist, TypeError, ValueError):
                return False
            request.branch_context = branch
        if self._requires_cash_feature(view):
            require_branch_feature(branch, 'cash_register')
        if support or user.is_superuser:
            return True
        return any(
            user_has_branch_permission(user, branch_id, code)
            if code in OPERATING_PERMISSION_CODES
            else (
                accessible_branches(user).filter(pk=branch_id).exists()
                and user_has_company_permission(
                    user, request.branch_context.company_id, code
                )
            )
            for code in codes
        )

    def has_object_permission(self, request, view, obj):
        support = support_permission_decision(request, obj=obj)
        if support is not None:
            return support
        branch_id = (
            obj.cash_session.branch_id
            if hasattr(obj, 'cash_session_id')
            else obj.branch_id
        )
        branch = getattr(request, 'branch_context', None)
        if request.user.is_superuser:
            return branch is None or branch.pk == branch_id
        if not branch or branch.pk != branch_id:
            return False
        if self._requires_cash_feature(view):
            require_branch_feature(branch, 'cash_register')
        return any(
            user_has_branch_permission(request.user, branch_id, code)
            if code in OPERATING_PERMISSION_CODES
            else user_has_company_permission(request.user, branch.company_id, code)
            for code in self.get_codes(view)
        )
