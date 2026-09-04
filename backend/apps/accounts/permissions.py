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
        'archive': 'users.change_status',
        'restore': 'users.add',
        'send_password_reset': 'users.change',
        'send_pos_pin_reset': 'users.change',
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
        company_id = request.query_params.get('company')
        if not company_id:
            branch = getattr(request, 'branch_context', None)
            company_id = branch.company_id if branch else None
        try:
            company_id = int(company_id)
        except (TypeError, ValueError):
            return False
        if not obj.company_accesses.filter(company_id=company_id).exists():
            return False
        has_context = user_has_company_permission(user, company_id, code)
        if not has_context:
            return False
        if view.action in ('update', 'partial_update'):
            return (
                company_permission_codes(obj, company_id) - OPERATING_PERMISSION_CODES
                <= company_permission_codes(user, company_id) - OPERATING_PERMISSION_CODES
            )
        return True
