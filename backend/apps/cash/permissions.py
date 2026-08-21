from rest_framework.permissions import BasePermission

from apps.companies.models import Branch
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.companies.selectors import (
    accessible_branches,
    user_has_branch_permission,
    user_has_company_permission,
)


class CashFunctionalPermission(BasePermission):
    message = 'Você não possui permissão para esta operação nesta filial.'

    def get_code(self, view):
        return view.permission_codes.get(view.action)

    def get_codes(self, view):
        code = self.get_code(view)
        return code if isinstance(code, tuple) else (code,)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if (
            request.method.lower() not in view.http_method_names
            or not hasattr(view, request.method.lower())
        ):
            return True
        codes = self.get_codes(view)
        if not all(codes):
            return False
        branch_id = request.headers.get('X-Branch-ID')
        if user.is_superuser:
            if not branch_id:
                return True
            try:
                request.branch_context = Branch.objects.get(pk=branch_id)
            except (Branch.DoesNotExist, TypeError, ValueError):
                return False
            return True
        if not branch_id:
            return False
        try:
            request.branch_context = Branch.objects.get(pk=branch_id)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
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
        return any(
            user_has_branch_permission(request.user, branch_id, code)
            if code in OPERATING_PERMISSION_CODES
            else user_has_company_permission(request.user, branch.company_id, code)
            for code in self.get_codes(view)
        )
