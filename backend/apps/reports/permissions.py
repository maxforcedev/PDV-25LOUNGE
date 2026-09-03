from rest_framework.permissions import BasePermission

from apps.companies.models import Branch, Status
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.companies.selectors import (
    user_has_branch_permission,
    user_has_company_permission,
)
from apps.saas.permissions import support_permission_decision


REPORT_PERMISSIONS = (
    'reports.view_sales',
    'reports.view_consumptions',
    'reports.view_cash',
    'reports.view_withdrawals',
    'reports.view_inventory',
    'reports.view_operational_result',
    'reports.view_stock_consumption',
    'reports.view_products',
    'reports.view_receipts',
    'reports.view_team',
    'reports.view_discounts',
    'reports.view_cancellations',
    'reports.view_prices',
    'inventory.report.view',
    'commissions.view',
)


class ReportsPermission(BasePermission):
    message = 'Você não possui permissão para este relatório nesta filial.'

    @staticmethod
    def _has_code(user, branch, code):
        if code in OPERATING_PERMISSION_CODES:
            return user_has_branch_permission(user, branch.pk, code)
        return user_has_company_permission(user, branch.company_id, code)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        branch_id = request.headers.get('X-Branch-ID')
        support = support_permission_decision(request, branch_id=branch_id)
        if support is not None:
            return support
        try:
            branch = Branch.objects.select_related('company').get(
                pk=branch_id, status=Status.ACTIVE, company__status=Status.ACTIVE
            )
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
        request.branch_context = branch
        required = getattr(view, 'required_permission', None)
        permission_by_scope = getattr(view, 'permission_by_scope', None)
        if permission_by_scope:
            required = permission_by_scope.get(request.query_params.get('scope'), required)
        codes = getattr(view, 'required_permissions', None)
        if permission_by_scope:
            codes = (required,) if required else ()
        elif codes is None:
            codes = REPORT_PERMISSIONS if required is None else (required,)
        mandatory = 'dashboard.view' if 'dashboard.view' in codes else None
        if user.is_superuser:
            allowed = True
        elif mandatory:
            allowed = self._has_code(user, branch, mandatory)
        else:
            allowed = any(self._has_code(user, branch, code) for code in codes)
        required_all = getattr(view, 'required_permissions_all', ())
        if allowed and required_all and not user.is_superuser:
            allowed = all(self._has_code(user, branch, code) for code in required_all)
        if not allowed:
            return False
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            return user.is_superuser or self._has_code(user, branch, 'reports.export')
        return True
