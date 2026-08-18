from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot

from .models import (
    AccessProfile, Branch, BranchSettings, Company, FunctionalPermission, Status,
    UserCommissionOverride, UserPermissionBlock,
)
from .permissions import CanCreateCompany, FunctionalCompanyPermission
from .selectors import (
    accessible_branches,
    accessible_companies,
    user_has_company_permission,
)
from .serializers import (
    AccessProfileSerializer,
    BranchSerializer,
    BranchSettingsSerializer,
    CompanySerializer,
    FunctionalPermissionSerializer,
    UserCommissionOverrideSerializer,
    UserPermissionBlockSerializer,
)
from .services import activate_branch, activate_company, deactivate_company


class CompanyViewSet(viewsets.ModelViewSet):
    serializer_class = CompanySerializer
    permission_classes = [FunctionalCompanyPermission]
    permission_codes = {
        'list': 'companies.view',
        'retrieve': 'companies.view',
        'update': 'companies.change',
        'partial_update': 'companies.change',
        'activate': 'companies.change',
        'deactivate': 'companies.change',
    }
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        permission_code = self.permission_codes.get(self.action, 'companies.view')
        return accessible_companies(self.request.user, permission_code).prefetch_related(
            Prefetch(
                'branches',
                queryset=accessible_branches(
                    self.request.user, 'branches.view'
                ).select_related('company', 'settings'),
                to_attr='visible_branches',
            )
        )

    def get_permissions(self):
        if self.action == 'create':
            return [CanCreateCompany()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        company = self.get_object()
        company = activate_company(company=company)
        company = self.get_queryset().get(pk=company.pk)
        return Response(self.get_serializer(company).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        company = self.get_object()
        company = deactivate_company(company=company)
        company = self.get_queryset().get(pk=company.pk)
        return Response(self.get_serializer(company).data)


class BranchViewSet(viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    permission_classes = [FunctionalCompanyPermission]
    permission_codes = {
        'list': 'branches.view',
        'retrieve': 'branches.view',
        'create': 'branches.add',
        'update': 'branches.change',
        'partial_update': 'branches.change',
        'activate': 'branches.change',
        'deactivate': 'branches.change',
        'branch_settings': 'branches.change_settings',
    }
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        permission_code = self.permission_codes.get(self.action, 'branches.view')
        return accessible_branches(
            self.request.user, permission_code
        ).select_related('company', 'settings')

    def perform_create(self, serializer):
        branch = serializer.save()
        audit_log(
            actor=self.request.user, action='branch.create', obj=branch,
            company=branch.company, branch=branch,
            after=model_snapshot(branch, ('name', 'cnpj', 'phone', 'email', 'address', 'status')),
        )

    def perform_update(self, serializer):
        fields = ('name', 'cnpj', 'phone', 'email', 'address', 'address_pending', 'status')
        before = model_snapshot(serializer.instance, fields)
        branch = serializer.save()
        audit_log(
            actor=self.request.user, action='branch.update', obj=branch,
            company=branch.company, branch=branch, before=before,
            after=model_snapshot(branch, fields),
        )

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        branch = self.get_object()
        branch = activate_branch(branch=branch)
        return Response(self.get_serializer(branch).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        branch = self.get_object()
        branch.status = Status.INACTIVE
        branch.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(branch).data)

    @action(detail=True, methods=['get', 'put', 'patch'], url_path='settings')
    def branch_settings(self, request, pk=None):
        branch = self.get_object()
        instance, _ = BranchSettings.objects.get_or_create(branch=branch)
        if request.method == 'GET':
            return Response(BranchSettingsSerializer(instance, context={'request': request}).data)
        serializer = BranchSettingsSerializer(instance, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        before = model_snapshot(instance, ('allow_negative_stock', 'service_fee_rate', 'commission_rate', 'fixed_daily_cost'))
        serializer.save()
        audit_log(
            actor=request.user,
            action='branch_settings.update',
            obj=instance,
            company=branch.company,
            branch=branch,
            before=before,
            after=model_snapshot(instance, ('allow_negative_stock', 'service_fee_rate', 'commission_rate', 'fixed_daily_cost')),
        )
        return Response(BranchSettingsSerializer(instance, context={'request': request}).data)


class CanViewPermissionCatalog(BasePermission):
    message = 'Voce nao possui permissao para visualizar perfis de acesso.'

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        company_id = request.query_params.get('company')
        if company_id:
            return user_has_company_permission(user, company_id, 'access_profiles.view')
        return user.company_accesses.filter(
            is_active=True,
            access_profile__status=Status.ACTIVE,
            access_profile__permissions__status=Status.ACTIVE,
            access_profile__permissions__code='access_profiles.view',
        ).exists()


class FunctionalPermissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FunctionalPermissionSerializer
    permission_classes = [CanViewPermissionCatalog]
    queryset = FunctionalPermission.objects.filter(status=Status.ACTIVE)
    lookup_field = 'code'

    def get_queryset(self):
        queryset = super().get_queryset()
        module = self.request.query_params.get('module')
        return queryset.filter(module=module) if module else queryset


class AccessProfilePermission(BasePermission):
    message = 'Voce nao possui permissao para esta operacao.'
    codes = {
        'list': 'access_profiles.view',
        'retrieve': 'access_profiles.view',
        'create': 'access_profiles.add',
        'update': 'access_profiles.change',
        'partial_update': 'access_profiles.change',
        'activate': 'access_profiles.change_status',
        'deactivate': 'access_profiles.change_status',
    }

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        code = self.codes.get(view.action)
        company_id = (
            request.data.get('company')
            if view.action == 'create'
            else request.query_params.get('company')
        )
        if company_id:
            return user_has_company_permission(user, company_id, code)
        return user.company_accesses.filter(
            is_active=True,
            access_profile__status=Status.ACTIVE,
            access_profile__permissions__status=Status.ACTIVE,
            access_profile__permissions__code=code,
        ).exists()

    def has_object_permission(self, request, view, obj):
        return user_has_company_permission(
            request.user,
            obj.company_id,
            self.codes.get(view.action),
        )


class AccessProfileViewSet(viewsets.ModelViewSet):
    serializer_class = AccessProfileSerializer
    permission_classes = [AccessProfilePermission]
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        queryset = AccessProfile.objects.select_related('company').prefetch_related(
            'permissions'
        )
        user = self.request.user
        if not user.is_superuser:
            permission_code = AccessProfilePermission.codes.get(
                self.action, 'access_profiles.view'
            )
            queryset = queryset.filter(
                company__user_accesses__user=user,
                company__user_accesses__is_active=True,
                company__user_accesses__access_profile__status=Status.ACTIVE,
                company__user_accesses__access_profile__permissions__status=Status.ACTIVE,
                company__user_accesses__access_profile__permissions__code=permission_code,
            ).distinct()
        company_id = self.request.query_params.get('company')
        profile_status = self.request.query_params.get('status')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        if profile_status:
            queryset = queryset.filter(status=profile_status)
        return queryset

    def perform_create(self, serializer):
        profile = serializer.save()
        audit_log(
            actor=self.request.user,
            action='access_profile.create',
            obj=profile,
            company=profile.company,
            after=model_snapshot(profile, ('name', 'description', 'status', 'receives_commission', 'commission_rate')),
        )

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('name', 'description', 'status', 'receives_commission', 'commission_rate'))
        profile = serializer.save()
        audit_log(
            actor=self.request.user,
            action='access_profile.update',
            obj=profile,
            company=profile.company,
            before=before,
            after=model_snapshot(profile, ('name', 'description', 'status', 'receives_commission', 'commission_rate')),
        )

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        profile = self.get_object()
        before = model_snapshot(profile, ('status',))
        profile.status = Status.ACTIVE
        profile.save(update_fields=['status', 'updated_at'])
        audit_log(actor=request.user, action='access_profile.activate', obj=profile, company=profile.company, before=before, after=model_snapshot(profile, ('status',)))
        return Response(self.get_serializer(profile).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        profile = self.get_object()
        if not request.user.is_superuser and profile.user_accesses.filter(
            user=request.user,
            company=profile.company,
            is_active=True,
        ).exists():
            return Response(
                {'status': ['Voce nao pode inativar seu proprio perfil ativo nesta empresa.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile.status = Status.INACTIVE
        profile.save(update_fields=['status', 'updated_at'])
        audit_log(actor=request.user, action='access_profile.deactivate', obj=profile, company=profile.company, before={'status': Status.ACTIVE}, after=model_snapshot(profile, ('status',)))
        return Response(self.get_serializer(profile).data)


class UserPermissionBlockPermission(BasePermission):
    message = 'Voce nao possui permissao para bloqueios individuais.'

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if user.is_superuser:
            return True
        code = 'user_permission_blocks.view' if view.action in ('list', 'retrieve') else 'user_permission_blocks.change'
        company_id = request.query_params.get('company') or request.data.get('company')
        branch_id = request.query_params.get('branch') or request.data.get('branch')
        if branch_id and not company_id:
            branch = Branch.objects.filter(pk=branch_id).only('company_id').first()
            company_id = branch.company_id if branch else None
        if company_id:
            return user_has_company_permission(user, company_id, code)
        return user.company_accesses.filter(
            is_active=True,
            access_profile__status=Status.ACTIVE,
            access_profile__permissions__status=Status.ACTIVE,
            access_profile__permissions__code=code,
        ).exists()


class UserPermissionBlockViewSet(viewsets.ModelViewSet):
    serializer_class = UserPermissionBlockSerializer
    permission_classes = (UserPermissionBlockPermission,)
    http_method_names = ('get', 'post', 'head', 'options')

    def get_queryset(self):
        queryset = UserPermissionBlock.objects.select_related(
            'company', 'branch', 'user', 'permission', 'created_by', 'revoked_by'
        )
        user = self.request.user
        if not user.is_superuser:
            company_ids = accessible_companies(user, 'user_permission_blocks.view').values_list('id', flat=True)
            branch_ids = accessible_branches(user, 'user_permission_blocks.view').values_list('id', flat=True)
            queryset = queryset.filter(company_id__in=company_ids) | queryset.filter(branch_id__in=branch_ids)
        params = self.request.query_params
        for field in ('company', 'branch', 'user'):
            if params.get(field):
                queryset = queryset.filter(**{f'{field}_id': params[field]})
        if params.get('permission'):
            queryset = queryset.filter(permission__code=params['permission'])
        if params.get('active') in ('true', 'false'):
            queryset = queryset.filter(is_active=params['active'] == 'true')
        return queryset.distinct()

    def perform_create(self, serializer):
        block = serializer.save()
        audit_log(
            actor=self.request.user,
            action='user_permission_block.create',
            obj=block,
            company=block.company,
            branch=block.branch,
            after=model_snapshot(block, ('user_id', 'permission_id', 'reason', 'is_active')),
        )

    @action(detail=True, methods=('post',))
    def revoke(self, request, pk=None):
        block = self.get_object()
        if not block.is_active:
            return Response(self.get_serializer(block).data)
        before = model_snapshot(block, ('is_active', 'revoked_at', 'revoked_by_id'))
        block.is_active = False
        block.revoked_by = request.user
        block.revoked_at = timezone.now()
        block.save(update_fields=('is_active', 'revoked_by', 'revoked_at', 'updated_at'))
        audit_log(
            actor=request.user,
            action='user_permission_block.revoke',
            obj=block,
            company=block.company,
            branch=block.branch,
            before=before,
            after=model_snapshot(block, ('is_active', 'revoked_at', 'revoked_by_id')),
        )
        return Response(self.get_serializer(block).data)


class CommissionOverridePermission(BasePermission):
    message = 'Voce nao possui permissao para comissoes nesta filial.'

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if user.is_superuser:
            return True
        code = view.permission_codes.get(view.action, 'commissions.view')
        branch_id = request.data.get('branch') or request.query_params.get('branch')
        if branch_id:
            branch = Branch.objects.filter(pk=branch_id).only('company_id').first()
            return bool(branch) and user_has_company_permission(user, branch.company_id, code)
        return accessible_companies(user, code).exists()

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        return user_has_company_permission(
            request.user, obj.branch.company_id, view.permission_codes.get(view.action, 'commissions.view')
        )


class UserCommissionOverrideViewSet(viewsets.ModelViewSet):
    serializer_class = UserCommissionOverrideSerializer
    permission_classes = (CommissionOverridePermission,)
    permission_codes = {
        'list': 'commissions.view',
        'retrieve': 'commissions.view',
        'create': 'commissions.change_user_override',
        'update': 'commissions.change_user_override',
        'partial_update': 'commissions.change_user_override',
    }
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        permission_code = self.permission_codes.get(self.action, 'commissions.view')
        queryset = UserCommissionOverride.objects.select_related('branch', 'branch__company', 'user')
        user = self.request.user
        if user.is_superuser:
            return queryset
        return queryset.filter(
            branch__company__in=accessible_companies(user, permission_code)
        )

    def perform_create(self, serializer):
        override = serializer.save()
        audit_log(actor=self.request.user, action='commission_override.create', obj=override, company=override.branch.company, branch=override.branch, after=model_snapshot(override, ('user_id', 'receives_commission', 'commission_rate')))

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('receives_commission', 'commission_rate'))
        override = serializer.save()
        audit_log(actor=self.request.user, action='commission_override.update', obj=override, company=override.branch.company, branch=override.branch, before=before, after=model_snapshot(override, ('receives_commission', 'commission_rate')))
