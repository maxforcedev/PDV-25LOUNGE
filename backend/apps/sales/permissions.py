from rest_framework.permissions import BasePermission

from apps.companies.models import Branch, Status
from apps.companies.selectors import user_has_branch_permission


class SalesFunctionalPermission(BasePermission):
    message = 'Você não possui permissão para esta operação nesta filial.'

    def _code(self, request, view):
        if view.basename == 'sale' and view.action == 'beneficiaries':
            return ('sales.create_consumption', 'sales.view_consumption')
        if view.basename == 'sale' and view.action in ('catalog', 'checkout_options', 'categories'):
            operation = request.query_params.get('operation_type', 'sale')
            return 'sales.create_consumption' if operation == 'consumption' else 'sales.create'
        if view.action in ('list', 'retrieve', 'cancel') and view.basename == 'sale':
            operation = getattr(getattr(view, '_permission_object', None), 'operation_type', None)
            if operation is None and view.action == 'list':
                operation = request.query_params.get('operation_type', 'sale')
            if view.action == 'cancel':
                return 'sales.cancel_consumption' if operation == 'consumption' else 'sales.cancel'
            return 'sales.view_consumption' if operation == 'consumption' else 'sales.view'
        if view.action in ('calculate', 'finalize'):
            operation = request.data.get('operation_type')
            return 'sales.create_consumption' if operation == 'consumption' else 'sales.create'
        return view.permission_codes.get(view.action)

    def _codes(self, request, view):
        code = self._code(request, view)
        return code if isinstance(code, tuple) else (code,)

    def has_permission(self, request, view):
        if (
            not request.user.is_authenticated
            or not request.user.can_login
            or not request.user.is_active
        ):
            return False
        if not view.action or not hasattr(view, view.action):
            return True
        if request.method.lower() not in view.http_method_names:
            return True
        branch_id = request.headers.get('X-Branch-ID')
        try:
            branch = Branch.objects.select_related('company').get(
                pk=branch_id, status=Status.ACTIVE, company__status=Status.ACTIVE
            )
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
        request.branch_context = branch
        if view.basename == 'sale' and view.action in ('retrieve', 'cancel'):
            codes = (
                'sales.view', 'sales.cancel',
                'sales.view_consumption', 'sales.cancel_consumption',
            ) if view.action == 'retrieve' else ('sales.cancel', 'sales.cancel_consumption')
            return request.user.is_superuser or any(
                user_has_branch_permission(request.user, branch.pk, code)
                for code in codes
            )
        codes = self._codes(request, view)
        return bool(all(codes) and (request.user.is_superuser or any(
            user_has_branch_permission(request.user, branch.pk, code)
            for code in codes
        )))

    def has_object_permission(self, request, view, obj):
        branch = request.branch_context
        object_branch_id = getattr(obj, 'branch_id', None)
        if object_branch_id is None and hasattr(obj, 'company_id'):
            if obj.company_id != branch.company_id:
                return False
        elif object_branch_id != branch.pk:
            return False
        view._permission_object = obj
        if view.basename == 'sale' and view.action == 'retrieve':
            codes = (
                ('sales.view_consumption', 'sales.cancel_consumption')
                if obj.operation_type == 'consumption'
                else ('sales.view', 'sales.cancel')
            )
        else:
            codes = self._codes(request, view)
        return request.user.is_superuser or any(
            user_has_branch_permission(request.user, branch.pk, code)
            for code in codes
        )
