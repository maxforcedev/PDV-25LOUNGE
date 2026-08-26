from django.db import DatabaseError, connection
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response

from apps.companies.selectors import accessible_branches, user_has_branch_permission

from .datetimes import filter_datetime_range, parse_datetime_range
from .labels import (
    AUDIT_MODULE_LABELS,
    action_label,
    audit_module_key,
)
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
    message = 'Você não possui permissão para visualizar auditoria.'

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        support_session = getattr(request, 'support_session', None)
        if support_session and not support_session.impersonated_user_id:
            return True
        if user.is_superuser:
            return True
        if request.query_params.get('scope') == 'all':
            return accessible_branches(user, 'audit_logs.view').exists()
        branch_id = request.query_params.get('branch') or request.headers.get('X-Branch-ID')
        company_id = request.query_params.get('company')
        if branch_id:
            return user_has_branch_permission(user, branch_id, 'audit_logs.view')
        if company_id:
            return accessible_branches(user, 'audit_logs.view').filter(
                company_id=company_id
            ).exists()
        return accessible_branches(user, 'audit_logs.view').exists()


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = (AuditLogPermission,)

    def scoped_queryset(self):
        queryset = AuditLog.objects.select_related('company', 'branch', 'actor')
        user = self.request.user
        support_session = getattr(self.request, 'support_session', None)
        if support_session and not support_session.impersonated_user_id:
            queryset = queryset.filter(company_id=support_session.company_id)
        elif not user.is_superuser:
            branches = accessible_branches(user, 'audit_logs.view')
            branch_ids = branches.values_list('id', flat=True)
            company_ids = branches.values_list('company_id', flat=True)
            queryset = queryset.filter(
                Q(branch_id__in=branch_ids)
                | Q(branch__isnull=True, company_id__in=company_ids)
            )
        params = self.request.query_params
        current_branch = self.request.headers.get('X-Branch-ID')
        if current_branch and not params.get('branch') and params.get('scope') != 'all':
            queryset = queryset.filter(branch_id=current_branch)
        if params.get('company'):
            queryset = queryset.filter(company_id=params['company'])
        if params.get('branch'):
            queryset = queryset.filter(branch_id=params['branch'])
        return queryset

    @staticmethod
    def filter_module(queryset, module):
        if module not in AUDIT_MODULE_LABELS:
            return queryset.none()
        module_query = Q()
        for action_code, object_type in queryset.values_list(
            'action', 'object_type'
        ).distinct():
            if audit_module_key(action_code, object_type) == module:
                module_query |= Q(
                    action=action_code,
                    object_type=object_type,
                )
        return queryset.filter(module_query) if module_query else queryset.none()

    def get_queryset(self):
        queryset = self.scoped_queryset()
        params = self.request.query_params
        if params.get('actor'):
            queryset = queryset.filter(actor_id=params['actor'])
        if params.get('action'):
            queryset = queryset.filter(action=params['action'])
        if params.get('module'):
            queryset = self.filter_module(queryset, params['module'])
        if params.get('object_type'):
            queryset = queryset.filter(object_type__icontains=params['object_type'])
        if params.get('search'):
            search = params['search']
            queryset = queryset.filter(
                Q(action__icontains=search)
                | Q(object_type__icontains=search)
                | Q(object_id__icontains=search)
            )
        start_datetime, end_datetime = parse_datetime_range(params)
        queryset = filter_datetime_range(
            queryset, 'created_at', start_datetime, end_datetime
        )
        return queryset.distinct()

    @action(detail=False, methods=['get'], url_path='options')
    def filter_options(self, request):
        queryset = self.scoped_queryset()
        pairs = list(
            queryset.values_list('action', 'object_type').distinct()
        )
        modules = sorted(
            {
                audit_module_key(action_code, object_type)
                for action_code, object_type in pairs
            },
            key=lambda value: AUDIT_MODULE_LABELS[value].casefold(),
        )
        actions = sorted(
            {action_code for action_code, _ in pairs if action_code},
            key=lambda value: (action_label(value).casefold(), value),
        )
        return Response({
            'modules': [
                {'value': value, 'label': AUDIT_MODULE_LABELS[value]}
                for value in modules
            ],
            'actions': [
                {'value': value, 'label': action_label(value)}
                for value in actions
            ],
        })
