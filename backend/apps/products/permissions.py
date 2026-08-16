from rest_framework.permissions import BasePermission

from apps.companies.models import Branch
from apps.companies.selectors import user_has_branch_permission


class ProductFunctionalPermission(BasePermission):
    message = 'Voce nao possui permissao para esta operacao.'

    def get_code(self, request, view):
        if view.action == 'components':
            return (
                'products.configure_composition'
                if request.method == 'PUT'
                else 'products.view'
            )
        return view.permission_codes.get(view.action)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if user.is_superuser:
            branch_id = request.headers.get('X-Branch-ID')
            if branch_id:
                try:
                    request.branch_context = Branch.objects.get(pk=branch_id)
                except (Branch.DoesNotExist, TypeError, ValueError):
                    return False
            return True
        code = self.get_code(request, view)
        if not code:
            return False
        branch_id = request.headers.get('X-Branch-ID')
        if not branch_id or not user_has_branch_permission(user, branch_id, code):
            return False
        try:
            request.branch_context = Branch.objects.get(pk=branch_id)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        branch = getattr(request, 'branch_context', None)
        if request.user.is_superuser and branch is None:
            return True
        return bool(branch and branch.company_id == obj.company_id)
