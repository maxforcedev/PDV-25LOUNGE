from decimal import Decimal, InvalidOperation

from rest_framework.permissions import BasePermission

from apps.companies.features import require_branch_feature
from apps.companies.models import Branch, Status
from apps.companies.selectors import user_has_branch_permission
from apps.saas.permissions import support_permission_decision


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

    @staticmethod
    def _requested_operation(request, view):
        if view.action in ('calculate', 'finalize'):
            return request.data.get('operation_type')
        return request.query_params.get('operation_type', 'sale')

    @staticmethod
    def _requested_channel(request, view):
        if view.action in ('calculate', 'finalize'):
            return request.data.get('channel', 'counter')
        return request.query_params.get('channel', 'counter')

    def _require_features(self, request, view, branch):
        if view.basename != 'sale':
            return
        action = view.action
        if action in ('list', 'retrieve', 'cancel'):
            return
        operation = self._requested_operation(request, view)
        if action == 'beneficiaries':
            operation = 'consumption'
        if operation == 'consumption':
            require_branch_feature(branch, 'consumption')
            if action in ('calculate', 'finalize'):
                try:
                    charged = request.data.get('charged_amount', 0)
                    if Decimal(str(charged).replace(',', '.')) > 0:
                        require_branch_feature(branch, 'cash_register')
                except (InvalidOperation, TypeError, ValueError):
                    pass
            return
        if action in (
            'catalog', 'checkout_options', 'categories', 'calculate', 'finalize',
            'sellers', 'discount_authorizers', 'item_discount_authorizers',
        ):
            channel_feature = {
                'counter': 'counter',
                'table': 'tables',
                'command': 'commands',
            }.get(self._requested_channel(request, view), 'counter')
            require_branch_feature(branch, channel_feature)
            require_branch_feature(branch, 'cash_register')

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
        support = support_permission_decision(request, branch_id=branch_id)
        if support is False:
            return False
        if support:
            branch = request.branch_context
        else:
            try:
                branch = Branch.objects.select_related('company').get(
                    pk=branch_id, status=Status.ACTIVE, company__status=Status.ACTIVE
                )
            except (Branch.DoesNotExist, TypeError, ValueError):
                return False
            request.branch_context = branch
        self._require_features(request, view, branch)
        if view.basename == 'sale' and view.action in ('retrieve', 'cancel'):
            codes = (
                'sales.view', 'sales.cancel',
                'sales.view_consumption', 'sales.cancel_consumption',
            ) if view.action == 'retrieve' else ('sales.cancel', 'sales.cancel_consumption')
            return bool(support) or request.user.is_superuser or any(
                user_has_branch_permission(request.user, branch.pk, code)
                for code in codes
            )
        codes = self._codes(request, view)
        return bool(all(codes) and (support or request.user.is_superuser or any(
            user_has_branch_permission(request.user, branch.pk, code)
            for code in codes
        )))

    def has_object_permission(self, request, view, obj):
        support = support_permission_decision(request, obj=obj)
        if support is not None:
            return support
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
