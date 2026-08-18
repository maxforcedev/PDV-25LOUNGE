from rest_framework.permissions import BasePermission

from .selectors import accessible_companies, user_has_company_permission


class CanCreateCompany(BasePermission):
    message = 'Apenas superusuarios podem cadastrar empresas.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.can_login
            and request.user.is_active
            and request.user.is_superuser
        )


class FunctionalCompanyPermission(BasePermission):
    message = 'Voce nao possui permissao para esta operacao.'

    def _code(self, view):
        return view.permission_codes.get(view.action)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if user.is_superuser or view.action == 'create' and view.basename == 'company':
            return True
        code = self._code(view)
        if not code:
            return False

        if view.action == 'create':
            company_id = request.data.get('company')
            return bool(company_id) and user_has_company_permission(user, company_id, code)

        return accessible_companies(user, code).exists()

    def has_object_permission(self, request, view, obj):
        code = self._code(view)
        if not code:
            return False
        if hasattr(obj, 'company_id'):
            return user_has_company_permission(request.user, obj.company_id, code)
        return user_has_company_permission(request.user, obj.id, code)
