from rest_framework.permissions import BasePermission

from apps.companies.models import Branch, Status
from apps.companies.selectors import user_has_branch_permission


REPORT_PERMISSIONS = (
    'reports.view_sales',
    'reports.view_consumptions',
    'reports.view_cash',
    'reports.view_withdrawals',
    'reports.view_inventory',
    'reports.view_operational_result',
)


class ReportsPermission(BasePermission):
    message = 'Voce nao possui permissao para este relatorio nesta filial.'

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        branch_id = request.headers.get('X-Branch-ID')
        try:
            branch = Branch.objects.select_related('company').get(
                pk=branch_id, status=Status.ACTIVE, company__status=Status.ACTIVE
            )
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
        request.branch_context = branch
        required = getattr(view, 'required_permission', None)
        codes = getattr(view, 'required_permissions', None)
        if codes is None:
            codes = REPORT_PERMISSIONS if required is None else (required,)
        if user.is_superuser:
            allowed = True
        else:
            allowed = any(user_has_branch_permission(user, branch.pk, code) for code in codes)
        if not allowed:
            return False
        if request.query_params.get('export') == 'csv':
            return user.is_superuser or user_has_branch_permission(
                user, branch.pk, 'reports.export'
            )
        return True
