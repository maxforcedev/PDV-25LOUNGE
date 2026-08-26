from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot
from apps.companies.models import AccessProfile, Company, Status
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.companies.selectors import (
    accessible_branches,
    accessible_companies,
    branch_permission_codes,
    company_permission_codes,
    user_has_company_permission,
)

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
                raise ValidationError({'company': 'Informe uma empresa válida.'}) from error
        queryset = User.objects.prefetch_related(
            'company_accesses__company',
            'branch_accesses__branch',
            'branch_accesses__access_profile__permissions',
        )
        support_session = getattr(self.request, 'support_session', None)
        if support_session and not support_session.impersonated_user_id:
            company_ids = {support_session.company_id}
            queryset = queryset.filter(
                company_accesses__company_id=support_session.company_id,
                company_accesses__is_active=True,
            )
            if company_id is not None:
                queryset = queryset.filter(company_accesses__company_id=company_id)
        elif user.is_superuser:
            if company_id is not None:
                queryset = queryset.filter(
                    company_accesses__company_id=company_id,
                    company_accesses__is_active=True,
                )
        else:
            permission_code = UserFunctionalPermission.codes.get(self.action, 'users.view')
            permission_codes = (
                permission_code if isinstance(permission_code, tuple)
                else (permission_code,)
            )
            company_ids = {
                accessible_company_id
                for code in permission_codes
                for accessible_company_id in accessible_companies(
                    user, code
                ).values_list('id', flat=True)
            }
            company_access_filters = {
                'company_accesses__company_id__in': company_ids,
                'company_accesses__is_active': True,
            }
            if company_id is not None:
                company_access_filters['company_accesses__company_id'] = company_id
            queryset = queryset.filter(**company_access_filters)

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
                raise ValidationError({'user_type': 'Informe um tipo de usuário válido.'})
            queryset = queryset.filter(user_type=user_type)

        relation_filters = {}
        for parameter in ('access_profile', 'branch'):
            value = params.get(parameter)
            if not value:
                continue
            try:
                value = int(value)
                if value < 1:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise ValidationError({parameter: 'Informe um identificador válido.'}) from error
            relation_filters[parameter] = value

        profile_id = relation_filters.get('access_profile')
        branch_id = relation_filters.get('branch')
        if branch_id is not None:
            filters = {
                'branch_accesses__branch_id': branch_id,
                'branch_accesses__branch__status': 'active',
                'branch_accesses__is_active': True,
                'branch_accesses__access_profile__status': 'active',
            }
            if profile_id is not None:
                filters['branch_accesses__access_profile_id'] = profile_id
            if company_id is not None:
                filters['branch_accesses__branch__company_id'] = company_id
            elif not user.is_superuser:
                filters['branch_accesses__branch__company_id__in'] = company_ids
            queryset = queryset.filter(**filters)
        elif profile_id is not None:
            filters = {
                'branch_accesses__access_profile_id': profile_id,
                'branch_accesses__is_active': True,
                'branch_accesses__access_profile__status': 'active',
            }
            if company_id is not None:
                filters['branch_accesses__branch__company_id'] = company_id
            elif not user.is_superuser:
                filters['branch_accesses__branch__company_id__in'] = company_ids
            queryset = queryset.filter(**filters)

        return queryset.distinct().order_by('first_name', 'last_name', 'email', 'id')

    @action(detail=False, methods=['get'], url_path='management-options')
    def management_options(self, request):
        management_codes = ('users.view', 'users.add', 'users.change')
        if request.user.is_superuser:
            company_ids = list(Company.objects.values_list('id', flat=True))
        else:
            company_ids = sorted({
                company_id
                for code in management_codes
                for company_id in accessible_companies(
                    request.user, code
                ).values_list('id', flat=True)
            })
        branches = list(accessible_branches(request.user).filter(
            company_id__in=company_ids
        ).order_by('company_id', 'name', 'id'))
        profiles = AccessProfile.objects.filter(
            company_id__in=company_ids, status=Status.ACTIVE
        ).prefetch_related('permissions').order_by('company_id', 'name', 'id')
        actor_company_codes = {
            company_id: company_permission_codes(request.user, company_id)
            for company_id in set(branch.company_id for branch in branches)
        }
        actor_branch_codes = {
            branch.pk: branch_permission_codes(request.user, branch.pk)
            for branch in branches
        }
        manageable_company_ids = {
            company_id for company_id in actor_company_codes
            if request.user.is_superuser or any(
                user_has_company_permission(request.user, company_id, code)
                for code in ('users.add', 'users.change')
            )
        }
        profile_options = []
        for profile in profiles:
            codes = set(profile.permissions.filter(status=Status.ACTIVE).values_list(
                'code', flat=True
            ))
            company_codes = codes - OPERATING_PERMISSION_CODES
            operating_codes = codes & OPERATING_PERMISSION_CODES
            profile_options.append({
                'id': profile.pk,
                'company_id': profile.company_id,
                'name': profile.name,
                'company_assignable': (
                    request.user.is_superuser
                    or (
                        profile.company_id in manageable_company_ids
                        and company_codes <= actor_company_codes.get(profile.company_id, set())
                    )
                ),
                'assignable_branch_ids': [
                    branch.pk for branch in branches
                    if (
                        branch.company_id == profile.company_id
                        and branch.status == Status.ACTIVE
                    ) and (
                        request.user.is_superuser
                        or (
                            profile.company_id in manageable_company_ids
                            and operating_codes <= actor_branch_codes[branch.pk]
                        )
                    )
                ],
            })
        return Response({
            'branches': [
                {
                    'id': branch.pk,
                    'company_id': branch.company_id,
                    'name': branch.name,
                    'status': branch.status,
                }
                for branch in branches
            ],
            'profiles': profile_options,
        })

    audit_fields = ('email', 'can_login', 'user_type', 'first_name', 'last_name', 'is_active')

    @staticmethod
    def access_snapshot(user):
        return {
            'company_accesses': list(user.company_accesses.order_by('company_id').values(
                'company_id', 'access_profile_id', 'is_active', 'is_owner'
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

    @transaction.atomic
    def perform_create(self, serializer):
        user = serializer.save()
        after = model_snapshot(user, self.audit_fields)
        after.update(self.access_snapshot(user))
        self.audit_user(user, 'user.create', after=after)

    @transaction.atomic
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
                'O usuário possui acessos fora do seu contexto autorizado.'
            )

    @action(detail=True, methods=['post'])
    @transaction.atomic
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
    @transaction.atomic
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response(
                {'is_active': ['Você não pode inativar o próprio usuário.']},
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

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reset_password(self, request, pk=None):
        user = self.get_object()
        if user.is_superuser and not request.user.is_superuser:
            raise PermissionDenied('Você não pode alterar um superusuário.')
        new_password = request.data.get('new_password', '')
        if not new_password:
            raise ValidationError({'new_password': 'A nova senha é obrigatória.'})
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(new_password, user=user)
        except Exception as error:
            raise ValidationError({'new_password': list(error.messages)}) from error
        user.set_password(new_password)
        user.save(update_fields=['password', 'updated_at'])
        snapshot = self.access_snapshot(user)
        self.audit_user(
            user, 'user.reset_password',
            before=snapshot, after=snapshot,
            metadata={'source': 'admin_reset'},
        )
        return Response({'detail': 'Senha redefinida com sucesso.'})
