from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.companies.selectors import user_has_company_permission

from .models import User
from .permissions import UserFunctionalPermission
from .serializers import UserManagementSerializer


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserManagementSerializer
    permission_classes = [UserFunctionalPermission]
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        user = self.request.user
        company_param = self.request.query_params.get('company')
        company_id = None
        if company_param is not None:
            try:
                company_id = int(company_param)
                if company_id < 1:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise ValidationError({'company': 'Informe uma empresa valida.'}) from error
        queryset = User.objects.prefetch_related(
            'company_accesses__company',
            'company_accesses__access_profile__permissions',
            'branch_accesses__branch',
            'branch_accesses__access_profile__permissions',
        )
        if user.is_superuser:
            if company_id is not None:
                queryset = queryset.filter(
                    company_accesses__company_id=company_id,
                    company_accesses__is_active=True,
                ).distinct()
            return queryset.order_by('email')
        permission_code = UserFunctionalPermission.codes.get(self.action, 'users.view')
        company_ids = user.company_accesses.filter(
            is_active=True,
            access_profile__status='active',
            access_profile__permissions__status='active',
            access_profile__permissions__code=permission_code,
        ).values_list('company_id', flat=True)
        queryset = queryset.filter(
            company_accesses__company_id__in=company_ids,
            company_accesses__is_active=True,
        )
        if company_id is not None:
            queryset = queryset.filter(company_accesses__company_id=company_id)
        return queryset.distinct().order_by('email')

    def _check_status_context(self, target):
        actor = self.request.user
        if actor.is_superuser:
            return
        target_company_ids = set(
            target.company_accesses.filter(is_active=True).values_list(
                'company_id', flat=True
            )
        )
        if not target_company_ids or any(
            not user_has_company_permission(actor, company_id, 'users.change_status')
            for company_id in target_company_ids
        ):
            raise PermissionDenied(
                'O usuario possui acessos fora do seu contexto autorizado.'
            )

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        user = self.get_object()
        self._check_status_context(user)
        user.is_active = True
        user.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response(
                {'is_active': ['Voce nao pode inativar o proprio usuario.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self._check_status_context(user)
        user.is_active = False
        user.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(user).data)
