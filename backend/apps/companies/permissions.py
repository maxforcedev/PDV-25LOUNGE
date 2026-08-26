from rest_framework.permissions import BasePermission

from .selectors import accessible_companies, user_has_company_permission
from apps.saas.permissions import support_permission_decision


class IsPlatformAdmin(BasePermission):
    message = 'A gestão de empresas pertence ao Platform Admin.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_active
            and request.user.is_superuser
        )


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
    message = 'Você não possui permissão para esta operação.'

    def _code(self, view):
        return view.permission_codes.get(view.action)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        support_session = getattr(request, 'support_session', None)
        if (
            view.action == 'transfer_owner'
            and support_session
            and not support_session.impersonated_user_id
        ):
            return False
        support = support_permission_decision(
            request,
            company_id=request.data.get('company') or request.query_params.get('company'),
            branch_id=request.headers.get('X-Branch-ID'),
        )
        if support is not None:
            return support
        if user.is_superuser or view.action == 'create' and view.basename == 'company':
            return True
        if view.action == 'transfer_owner':
            return user.company_accesses.filter(is_owner=True, is_active=True).exists()
        code = self._code(view)
        if not code:
            return False

        if view.action == 'create':
            company_id = request.data.get('company')
            return bool(company_id) and user_has_company_permission(user, company_id, code)

        return accessible_companies(user, code).exists()

    def has_object_permission(self, request, view, obj):
        support = support_permission_decision(request, obj=obj)
        if support is not None:
            return support
        if view.action == 'transfer_owner':
            return obj.user_accesses.filter(
                user=request.user, is_owner=True, is_active=True
            ).exists()
        code = self._code(view)
        if not code:
            return False
        if hasattr(obj, 'company_id'):
            return user_has_company_permission(request.user, obj.company_id, code)
        return user_has_company_permission(request.user, obj.id, code)
