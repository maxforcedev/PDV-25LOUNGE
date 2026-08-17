from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from .models import AccessProfile, Branch, BranchSettings, Company, FunctionalPermission, Status
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
        'branch_settings': 'branches.change',
    }
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        permission_code = self.permission_codes.get(self.action, 'branches.view')
        return accessible_branches(
            self.request.user, permission_code
        ).select_related('company', 'settings')

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
            return Response(BranchSettingsSerializer(instance).data)
        serializer = BranchSettingsSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(BranchSettingsSerializer(instance).data)


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

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        profile = self.get_object()
        profile.status = Status.ACTIVE
        profile.save(update_fields=['status', 'updated_at'])
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
        return Response(self.get_serializer(profile).data)
