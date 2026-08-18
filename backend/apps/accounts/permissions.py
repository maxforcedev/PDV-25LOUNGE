from rest_framework.permissions import BasePermission

from apps.companies.selectors import (
    accessible_companies,
    company_permission_codes,
    user_has_company_permission,
)


class UserFunctionalPermission(BasePermission):
    message = 'Voce nao possui permissao para esta operacao.'
    codes = {
        'list': 'users.view',
        'retrieve': 'users.view',
        'create': 'users.add',
        'update': 'users.change',
        'partial_update': 'users.change',
        'activate': 'users.change_status',
        'deactivate': 'users.change_status',
    }

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if user.is_superuser:
            return True
        code = self.codes.get(view.action)
        return accessible_companies(user, code).exists()

    def has_object_permission(self, request, view, obj):
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
                company_permission_codes(obj, company_id)
                <= company_permission_codes(user, company_id)
                for company_id in target_company_ids
            )
        return True
