from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot
from apps.companies.models import Company
from apps.companies.selectors import accessible_companies, user_has_company_permission

from .models import User
from .permissions import UserFunctionalPermission
from .serializers import UserManagementSerializer


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserManagementSerializer
    permission_classes = [UserFunctionalPermission]
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params
        company_param = params.get('company')
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
                )
        else:
            permission_code = UserFunctionalPermission.codes.get(self.action, 'users.view')
            company_ids = accessible_companies(user, permission_code).values_list('id', flat=True)
            queryset = queryset.filter(
                company_accesses__company_id__in=company_ids,
                company_accesses__is_active=True,
            )
            if company_id is not None:
                queryset = queryset.filter(company_accesses__company_id=company_id)

        search = params.get('search', '').strip()
        for term in search.split():
            queryset = queryset.filter(
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
            )

        user_status = params.get('status')
        if user_status:
            if user_status not in ('active', 'inactive'):
                raise ValidationError({'status': 'Informe active ou inactive.'})
            queryset = queryset.filter(is_active=user_status == 'active')

        can_login = params.get('can_login')
        if can_login:
            if can_login not in ('true', 'false'):
                raise ValidationError({'can_login': 'Informe true ou false.'})
            queryset = queryset.filter(can_login=can_login == 'true')

        user_type = params.get('user_type')
        if user_type:
            if user_type not in User.UserType.values:
                raise ValidationError({'user_type': 'Informe um tipo de usuario valido.'})
            queryset = queryset.filter(user_type=user_type)

        for parameter in ('access_profile', 'branch'):
            value = params.get(parameter)
            if not value:
                continue
            try:
                value = int(value)
                if value < 1:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise ValidationError({parameter: 'Informe um identificador valido.'}) from error
            if parameter == 'access_profile':
                filters = {
                    'company_accesses__access_profile_id': value,
                    'company_accesses__is_active': True,
                }
                if company_id is not None:
                    filters['company_accesses__access_profile__company_id'] = company_id
                elif not user.is_superuser:
                    filters['company_accesses__access_profile__company_id__in'] = company_ids
                queryset = queryset.filter(**filters)
            else:
                filters = {
                    'branch_accesses__branch_id': value,
                    'branch_accesses__branch__status': 'active',
                    'branch_accesses__is_active': True,
                    'branch_accesses__access_profile__status': 'active',
                }
                if company_id is not None:
                    filters['branch_accesses__branch__company_id'] = company_id
                elif not user.is_superuser:
                    filters['branch_accesses__branch__company_id__in'] = company_ids
                queryset = queryset.filter(**filters)

        return queryset.distinct().order_by('first_name', 'last_name', 'email', 'id')

    audit_fields = ('email', 'can_login', 'user_type', 'first_name', 'last_name', 'is_active')

    @staticmethod
    def access_snapshot(user):
        return {
            'company_accesses': list(user.company_accesses.order_by('company_id').values(
                'company_id', 'access_profile_id', 'is_active'
            )),
            'branch_accesses': list(user.branch_accesses.order_by('branch_id').values(
                'branch_id', 'access_profile_id', 'is_active'
            )),
        }

    def audit_user(self, user, action, before=None, after=None):
        company_ids = {
            item['company_id']
            for snapshot in (before or {}, after or {})
            for item in snapshot.get('company_accesses', [])
        }
        companies = Company.objects.in_bulk(company_ids)
        scopes = [companies[company_id] for company_id in sorted(companies)] or [None]
        for company in scopes:
            audit_log(
                actor=self.request.user, action=action, obj=user, company=company,
                before=before, after=after,
                metadata={'scope_company_id': company.pk if company else None},
            )

    def perform_create(self, serializer):
        user = serializer.save()
        after = model_snapshot(user, self.audit_fields)
        after.update(self.access_snapshot(user))
        self.audit_user(user, 'user.create', after=after)

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, self.audit_fields)
        before.update(self.access_snapshot(serializer.instance))
        user = serializer.save()
        after = model_snapshot(user, self.audit_fields)
        after.update(self.access_snapshot(user))
        self.audit_user(user, 'user.update', before=before, after=after)

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
        snapshot = self.access_snapshot(user)
        self.audit_user(
            user, 'user.activate',
            before={'is_active': False, **snapshot},
            after={'is_active': True, **snapshot},
        )
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
        snapshot = self.access_snapshot(user)
        self.audit_user(
            user, 'user.deactivate',
            before={'is_active': True, **snapshot},
            after={'is_active': False, **snapshot},
        )
        return Response(self.get_serializer(user).data)
