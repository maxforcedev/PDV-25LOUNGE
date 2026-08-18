from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response

from apps.companies.selectors import accessible_branches, accessible_companies, user_has_branch_permission, user_has_company_permission

from .models import AuditLog
from .serializers import AuditLogSerializer


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return JsonResponse({'status': 'unavailable'}, status=503)

    return JsonResponse({'status': 'ok'})


@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request):
    return Response({'name': 'CORE PDV API', 'version': 'v1'})


class AuditLogPermission(BasePermission):
    message = 'Voce nao possui permissao para visualizar auditoria.'

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if user.is_superuser:
            return True
        branch_id = request.query_params.get('branch') or request.headers.get('X-Branch-ID')
        company_id = request.query_params.get('company')
        if branch_id:
            return user_has_branch_permission(user, branch_id, 'audit_logs.view')
        if company_id:
            return user_has_company_permission(user, company_id, 'audit_logs.view')
        return accessible_companies(user, 'audit_logs.view').exists() or accessible_branches(user, 'audit_logs.view').exists()


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = (AuditLogPermission,)

    def get_queryset(self):
        queryset = AuditLog.objects.select_related('company', 'branch', 'actor')
        user = self.request.user
        if not user.is_superuser:
            company_ids = accessible_companies(user, 'audit_logs.view').values_list('id', flat=True)
            branch_ids = accessible_branches(user, 'audit_logs.view').values_list('id', flat=True)
            queryset = queryset.filter(company_id__in=company_ids) | queryset.filter(branch_id__in=branch_ids)
        params = self.request.query_params
        current_branch = self.request.headers.get('X-Branch-ID')
        if current_branch and not params.get('branch'):
            queryset = queryset.filter(branch_id=current_branch)
        if params.get('company'):
            queryset = queryset.filter(company_id=params['company'])
        if params.get('branch'):
            queryset = queryset.filter(branch_id=params['branch'])
        if params.get('actor'):
            queryset = queryset.filter(actor_id=params['actor'])
        if params.get('action'):
            queryset = queryset.filter(action__icontains=params['action'])
        if params.get('object_type'):
            queryset = queryset.filter(object_type__icontains=params['object_type'])
        if params.get('search'):
            search = params['search']
            queryset = queryset.filter(action__icontains=search) | queryset.filter(object_type__icontains=search) | queryset.filter(object_id__icontains=search)
        if params.get('start_datetime'):
            queryset = queryset.filter(created_at__gte=params['start_datetime'])
        if params.get('end_datetime'):
            queryset = queryset.filter(created_at__lte=params['end_datetime'])
        return queryset.distinct()
