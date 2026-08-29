from rest_framework.permissions import BasePermission

from apps.companies.models import Branch
from apps.companies.selectors import user_has_branch_permission, user_has_company_permission
from apps.saas.permissions import support_permission_decision


class ProductFunctionalPermission(BasePermission):
    message = 'Você não possui permissão para esta operação.'

    def get_code(self, request, view):
        if view.action == 'components':
            return (
                'products.configure_composition'
                if request.method == 'PUT'
                else 'products.view'
            )
        if view.action in ('branch_config', 'fraction_config', 'production_destinations'):
            if request.method == 'GET':
                return 'products.view'
        if view.action == 'minimum_stock' and request.method == 'GET':
            return 'products.view'
        return view.permission_codes.get(view.action)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        branch_id = request.headers.get('X-Branch-ID')
        support = support_permission_decision(request, branch_id=branch_id)
        if support is not None:
            return support
        if user.is_superuser:
            if branch_id:
                try:
                    request.branch_context = Branch.objects.get(pk=branch_id)
                except (Branch.DoesNotExist, TypeError, ValueError):
                    return False
            return True
        code = self.get_code(request, view)
        if not code:
            return False
        if not branch_id:
            return False
        try:
            request.branch_context = Branch.objects.get(pk=branch_id)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
        if view.basename == 'branchprice':
            company_id = request.branch_context.company_id
            if view.action in {'list', 'retrieve', 'table'}:
                return (
                    user_has_branch_permission(user, request.branch_context.pk, 'branch_prices.view')
                    or user_has_company_permission(user, company_id, 'branch_prices.view_company')
                )
            return (
                user_has_branch_permission(user, request.branch_context.pk, 'branch_prices.change')
                or user_has_company_permission(user, company_id, 'branch_prices.change_company')
            )
        if not user_has_branch_permission(user, request.branch_context.pk, code):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        support = support_permission_decision(request, obj=obj)
        if support is not None:
            return support
        branch = getattr(request, 'branch_context', None)
        if request.user.is_superuser and branch is None:
            return True
        if view.basename == 'branchprice' and branch:
            if obj.branch.company_id != branch.company_id:
                return False
            if view.action in {'retrieve', 'list', 'table'}:
                return (
                    user_has_branch_permission(request.user, branch.pk, 'branch_prices.view')
                    and obj.branch_id == branch.pk
                ) or user_has_company_permission(
                    request.user, branch.company_id, 'branch_prices.view_company'
                )
            return (
                user_has_branch_permission(request.user, branch.pk, 'branch_prices.change')
                and obj.branch_id == branch.pk
            ) or user_has_company_permission(
                request.user, branch.company_id, 'branch_prices.change_company'
            )
        if branch and getattr(obj, 'branch_id', None) and getattr(obj, 'product_id', None):
            return obj.branch_id == branch.pk
        company_id = getattr(obj, 'company_id', None)
        if company_id is None and getattr(obj, 'product_id', None):
            company_id = obj.product.company_id
        if company_id is None and getattr(obj, 'modifier_group_id', None):
            company_id = obj.modifier_group.company_id
        return bool(branch and branch.company_id == company_id)
