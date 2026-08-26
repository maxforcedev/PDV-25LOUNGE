from rest_framework.permissions import BasePermission

from apps.companies.selectors import (
    accessible_companies,
    company_permission_codes,
    user_has_company_permission,
)
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.saas.permissions import support_permission_decision


class UserFunctionalPermission(BasePermission):
    message = 'Você não possui permissão para esta operação.'
    codes = {
        'list': 'users.view',
        'retrieve': 'users.view',
        'create': 'users.add',
        'update': 'users.change',
        'partial_update': 'users.change',
        'activate': 'users.change_status',
        'deactivate': 'users.change_status',
        'reset_password': 'users.change',
        'management_options': ('users.view', 'users.add', 'users.change'),
    }

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        support = support_permission_decision(request)
        if support is not None:
            return support
        if user.is_superuser:
            return True
        code = self.codes.get(view.action)
        if isinstance(code, tuple):
            return any(accessible_companies(user, item).exists() for item in code)
        return accessible_companies(user, code).exists()

    def has_object_permission(self, request, view, obj):
        support = support_permission_decision(request, obj=obj)
        if support is not None:
            return support
        user = request.user
        if user.is_superuser:
            return True
        if obj.is_superuser:
            return False
        code = self.codes.get(view.action)
        target_company_ids = set(
            obj.company_accesses.filter(is_active=True).values_list('company_id', flat=True)
        )
        if view.action == 'retrieve':
            return any(
                user_has_company_permission(user, company_id, code)
                for company_id in target_company_ids
            )
        has_context = bool(target_company_ids) and all(
            user_has_company_permission(user, company_id, code)
            for company_id in target_company_ids
        )
        if not has_context:
            return False
        if view.action in ('update', 'partial_update'):
            return all(
                company_permission_codes(obj, company_id) - OPERATING_PERMISSION_CODES
                <= company_permission_codes(user, company_id) - OPERATING_PERMISSION_CODES
                for company_id in target_company_ids
            )
        return True
