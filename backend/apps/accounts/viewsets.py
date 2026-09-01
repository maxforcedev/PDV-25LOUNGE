from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot
from apps.companies.models import AccessProfile, Company, Status, UserCompanyAccess
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

    def context_company_id(self):
        value = self.request.query_params.get('company')
        if value is None:
            branch = getattr(self.request, 'branch_context', None)
            return branch.company_id if branch else None
        try:
            value = int(value)
            if value < 1:
                raise ValueError
            return value
        except (TypeError, ValueError) as error:
            raise ValidationError({'company': 'Informe uma empresa válida.'}) from error

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
        if support_session:
            company_ids = {support_session.company_id}
            queryset = queryset.filter(company_accesses__company_id=support_session.company_id)
            if company_id is not None:
                queryset = queryset.filter(company_accesses__company_id=company_id)
        elif user.is_superuser:
            if company_id is not None:
                queryset = queryset.filter(
                    company_accesses__company_id=company_id,
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
            }
            if company_id is None:
                company_access_filters['company_accesses__is_active'] = True
            if company_id is not None:
                company_access_filters['company_accesses__company_id'] = company_id
            queryset = queryset.filter(**company_access_filters)

        if company_id is not None and self.action != 'restore':
            queryset = queryset.filter(
                company_accesses__company_id=company_id,
                company_accesses__archived_at__isnull=True,
            )

        search = params.get('search', '').strip()
        for term in search.split():
            queryset = queryset.filter(
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
            )

        user_status = params.get('status')
        if user_status and user_status not in ('active', 'inactive', 'all'):
            raise ValidationError({'status': 'Informe active, inactive ou all.'})
        if user_status == 'active':
            queryset = queryset.filter(is_active=True, archived_at__isnull=True)
            if company_id is not None:
                queryset = queryset.filter(company_accesses__company_id=company_id, company_accesses__is_active=True)
        elif user_status == 'inactive':
            queryset = queryset.filter(archived_at__isnull=True)
            if company_id is None:
                queryset = queryset.filter(is_active=False)
            else:
                queryset = queryset.filter(
                    company_accesses__company_id=company_id,
                    company_accesses__is_active=False,
                )
        elif user_status == 'all':
            queryset = queryset.filter(archived_at__isnull=True)
        elif self.action != 'activate':
            queryset = queryset.filter(archived_at__isnull=True)

        can_login = params.get('can_login')
        if can_login:
            if can_login not in ('true', 'false'):
                raise ValidationError({'can_login': 'Informe true ou false.'})
            if company_id is not None:
                queryset = queryset.filter(
                    company_accesses__company_id=company_id,
                    company_accesses__can_login=can_login == 'true',
                )
            else:
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
        if branch_id is None and self.action == 'list':
            header_branch_id = self.request.headers.get('X-Branch-ID')
            if header_branch_id:
                try:
                    branch_id = int(header_branch_id)
                    if branch_id < 1:
                        raise ValueError
                except (TypeError, ValueError) as error:
                    raise ValidationError({
                        'branch': 'Informe um identificador válido.'
                    }) from error
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
        requested_company_id = self.context_company_id()
        if request.user.is_superuser:
            company_ids = [requested_company_id] if requested_company_id else list(Company.objects.values_list('id', flat=True))
        else:
            company_ids = sorted({
                company_id
                for code in management_codes
                for company_id in accessible_companies(
                    request.user, code
                ).values_list('id', flat=True)
            })
            if requested_company_id:
                if requested_company_id not in company_ids:
                    raise PermissionDenied('Empresa fora do contexto autorizado.')
                company_ids = [requested_company_id]
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
    def access_snapshot(user, company_id=None):
        company_filter = {'company_id': company_id} if company_id else {}
        branch_filter = {'branch__company_id': company_id} if company_id else {}
        return {
            'company_accesses': list(user.company_accesses.filter(**company_filter).order_by('company_id').values(
                'company_id', 'access_profile_id', 'is_active', 'can_login', 'is_owner'
            )),
            'branch_accesses': list(user.branch_accesses.filter(**branch_filter).order_by('branch_id').values(
                'branch_id', 'access_profile_id', 'is_active'
            )),
        }

    def audit_user(self, user, action, before=None, after=None, metadata=None):
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
                metadata={**(metadata or {}), 'scope_company_id': company.pk if company else None},
            )

    @transaction.atomic
    def perform_create(self, serializer):
        user = serializer.save()
        after = model_snapshot(user, self.audit_fields)
        after.update(self.access_snapshot(user))
        self.audit_user(user, 'user.create', after=after)

    @transaction.atomic
    def perform_update(self, serializer):
        company_id = self.context_company_id()
        before = model_snapshot(serializer.instance, self.audit_fields)
        before.update(self.access_snapshot(serializer.instance, company_id))
        user = serializer.save()
        after = model_snapshot(user, self.audit_fields)
        after.update(self.access_snapshot(user, company_id))
        self.audit_user(user, 'user.update', before=before, after=after)

    def _check_status_context(self, target):
        actor = self.request.user
        company_id = self.context_company_id()
        if actor.is_superuser and not company_id:
            return None
        if not company_id or not target.company_accesses.filter(company_id=company_id).exists():
            raise PermissionDenied('O usuário não pertence à empresa informada.')
        if not actor.is_superuser and not user_has_company_permission(actor, company_id, 'users.change_status'):
            raise PermissionDenied(
                'O usuário possui acessos fora do seu contexto autorizado.'
            )
        return company_id

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def activate(self, request, pk=None):
        user = self.get_object()
        company_id = self._check_status_context(user)
        if company_id is None:
            before = {'is_active': user.is_active}
            user.is_active = True
            user.archived_at = None
            user.save(update_fields=['is_active', 'archived_at', 'updated_at'])
            self.audit_user(user, 'user.activate', before=before, after={'is_active': True})
            return Response(self.get_serializer(user).data)
        membership = UserCompanyAccess.objects.select_for_update().get(user=user, company_id=company_id)
        before_active = membership.is_active
        membership.is_active = True
        membership.save(update_fields=['is_active', 'updated_at'])
        snapshot = self.access_snapshot(user, company_id)
        self.audit_user(
            user, 'user.activate',
            before={'membership_active': before_active, **snapshot},
            after={'membership_active': True, **snapshot},
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
        company_id = self._check_status_context(user)
        if company_id is None:
            user.is_active = False
            user.save(update_fields=['is_active', 'updated_at'])
            self.audit_user(user, 'user.deactivate', before={'is_active': True}, after={'is_active': False})
            return Response(self.get_serializer(user).data)
        membership = UserCompanyAccess.objects.select_for_update().get(user=user, company_id=company_id)
        before_active = membership.is_active
        membership.is_active = False
        membership.save(update_fields=['is_active', 'updated_at'])
        snapshot = self.access_snapshot(user, company_id)
        self.audit_user(
            user, 'user.deactivate',
            before={'membership_active': before_active, **snapshot},
            after={'membership_active': False, **snapshot},
        )
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=['post'], url_path='reset-password')
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
        company_id = self.context_company_id()
        snapshot = self.access_snapshot(user, company_id)
        self.audit_user(
            user, 'user.reset_password',
            before=snapshot, after=snapshot,
            metadata={'source': 'admin_reset'},
        )
        return Response({'detail': 'Senha redefinida com sucesso.'})

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def archive(self, request, pk=None):
        user = self.get_object()
        if user.pk == request.user.pk:
            raise ValidationError({'detail': 'Você não pode arquivar o próprio usuário.'})
        company_id = self._check_status_context(user)
        if company_id is None:
            raise ValidationError({'company': 'Informe a empresa do vínculo a arquivar.'})
        snapshot = self.access_snapshot(user, company_id)
        before = {'is_active': user.is_active, 'archived_at': user.archived_at.isoformat() if user.archived_at else None, **snapshot}
        membership = UserCompanyAccess.objects.select_for_update().get(
            user=user, company_id=company_id,
        )
        if membership.is_owner:
            raise ValidationError({'detail': 'Transfira a propriedade antes de arquivar este usuário.'})
        now = timezone.now()
        membership.is_active = False
        membership.archived_at = now
        membership.save(update_fields=('is_active', 'archived_at', 'updated_at'))
        user.branch_accesses.filter(branch__company_id=company_id).update(
            is_active=False, updated_at=now,
        )
        if not user.company_accesses.filter(
            is_active=True, archived_at__isnull=True,
        ).exclude(company_id=company_id).exists():
            user.archived_at = now
            user.is_active = False
            user.save(update_fields=('archived_at', 'is_active', 'updated_at'))
        user.refresh_from_db()
        after_snapshot = self.access_snapshot(user, company_id)
        self.audit_user(
            user, 'user.archive', before=before,
            after={
                'is_active': user.is_active,
                'archived_at': user.archived_at.isoformat() if user.archived_at else None,
                **after_snapshot,
            },
        )
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def restore(self, request, pk=None):
        company_id = self.context_company_id()
        if not company_id or not user_has_company_permission(request.user, company_id, 'users.add'):
            raise PermissionDenied('Empresa fora do contexto autorizado.')
        try:
            user = User.objects.select_for_update().get(
                pk=pk,
                company_accesses__company_id=company_id,
                company_accesses__archived_at__isnull=False,
            )
        except User.DoesNotExist as error:
            raise ValidationError({'detail': 'Usuário arquivado não encontrado nesta empresa.'}) from error
        before = model_snapshot(user, self.audit_fields)
        before.update(self.access_snapshot(user, company_id))
        serializer = self.get_serializer(
            user,
            data=request.data,
            partial=True,
            context={**self.get_serializer_context(), 'restoring_membership': True},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        after = model_snapshot(user, self.audit_fields)
        after.update(self.access_snapshot(user, company_id))
        self.audit_user(
            user,
            'user.restore',
            before=before,
            after=after,
            metadata={'restored_company_id': company_id},
        )
        return Response(self.get_serializer(user).data)
