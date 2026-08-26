from rest_framework.permissions import BasePermission

from apps.companies.features import require_branch_feature
from apps.companies.models import Branch, Status
from apps.companies.selectors import user_has_branch_permission
from apps.saas.permissions import support_permission_decision


class CommandFunctionalPermission(BasePermission):
    message = 'Você não possui permissão para esta operação.'

    codes = {
        'list': 'commands.view',
        'retrieve': 'commands.view',
        'open': 'commands.open',
        'open_list': 'commands.view',
        'add_item': 'commands.add_items',
        'add_items': 'commands.add_items',
        'confirm': 'commands.add_items',
        'cancel': 'commands.cancel_items',
        'finalize': 'commands.finalize',
        'calculate': 'commands.finalize',
        'checkout_options': 'commands.finalize',
        'sellers': 'commands.finalize',
        'discount_authorizers': 'commands.finalize',
        'service_fee_authorizers': 'commands.finalize',
        'operational': 'commands.view',
        'create': 'commands.open',
        'update': 'commands.open',
        'partial_update': 'commands.open',
        'activate': 'commands.open',
        'deactivate': 'commands.open',
        'batch_create': 'commands.open',
    }

    @staticmethod
    def _feature(view):
        if view.basename == 'table':
            return 'tables'
        if view.action in (
            'open', 'add_item', 'add_items', 'calculate', 'checkout_options', 'sellers',
            'discount_authorizers', 'service_fee_authorizers',
        ):
            return 'commands'
        return None

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        branch_id = request.headers.get('X-Branch-ID')
        support = support_permission_decision(request, branch_id=branch_id)
        if support is False:
            return False
        code = self.codes.get(view.action)
        if not code:
            return False
        if support:
            branch = request.branch_context
        else:
            try:
                branch = Branch.objects.select_related('company').get(
                    pk=branch_id, status=Status.ACTIVE, company__status=Status.ACTIVE,
                )
            except (Branch.DoesNotExist, TypeError, ValueError):
                return False
            request.branch_context = branch
        feature = self._feature(view)
        if feature:
            require_branch_feature(branch, feature)
        return bool(support) or user.is_superuser or user_has_branch_permission(user, branch.pk, code)

    def has_object_permission(self, request, view, obj):
        support = support_permission_decision(request, obj=obj)
        if support is not None:
            return support
        if request.user.is_superuser:
            return True
        code = self.codes.get(view.action)
        if not code:
            return False
        if hasattr(obj, 'branch_id'):
            branch_id = obj.branch_id
        elif hasattr(obj, 'order') and hasattr(obj.order, 'command'):
            branch_id = obj.order.command.branch_id
        else:
            return False
        feature = self._feature(view)
        if feature:
            require_branch_feature(Branch.objects.get(pk=branch_id), feature)
        return user_has_branch_permission(request.user, branch_id, code)
