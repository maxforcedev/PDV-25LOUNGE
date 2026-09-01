import uuid

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from apps.accounts.models import User
from apps.base.audit import audit_log, model_snapshot
from apps.base.pagination import StandardPagination

from .features import branch_feature_states
from .models import (
    AccessProfile, Branch, BranchSettings, Company, Customer, FunctionalPermission, Status,
    UserBranchAccess, UserCommissionOverride, UserCompanyAccess,
    UserPermissionBlock,
)
from .permissions import CanCreateCompany, FunctionalCompanyPermission, IsPlatformAdmin
from .selectors import (
    accessible_branches,
    accessible_companies,
    blockable_permission_codes,
    user_has_branch_permission,
    user_has_company_permission,
)
from .serializers import (
    AccessProfileSerializer,
    BranchSerializer,
    BranchSettingsSerializer,
    CompanySerializer,
    CustomerSerializer,
    FunctionalPermissionSerializer,
    TransferCompanyOwnerSerializer,
    UserCommissionOverrideSerializer,
    UserPermissionBlockSerializer,
)


class CustomerSearchPagination(StandardPagination):
    page_size = 20
    page_size_query_param = 'limit'
    max_page_size = 100
from .services import (
    activate_branch,
    activate_company,
    deactivate_company,
    transfer_company_owner,
)


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    pagination_class = CustomerSearchPagination
    permission_classes = [FunctionalCompanyPermission]
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')
    permission_codes = {
        'list': 'customers.view', 'retrieve': 'customers.view',
        'create': 'customers.add', 'update': 'customers.change',
        'partial_update': 'customers.change', 'activate': 'customers.change',
        'deactivate': 'customers.deactivate', 'search': 'customers.view',
    }
    audit_fields = ('company_id', 'name', 'phone', 'document', 'email', 'birth_date', 'notes', 'status')

    def get_queryset(self):
        companies = accessible_companies(
            self.request.user, self.permission_codes.get(self.action, 'customers.view')
        )
        queryset = Customer.objects.filter(company__in=companies).select_related('company')
        company_id = self.request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        if self.action in ('list', 'search'):
            status_value = self.request.query_params.get('status')
            if status_value:
                queryset = queryset.filter(status=status_value)
            term = (self.request.query_params.get('q') or self.request.query_params.get('search', '')).strip()
            if term:
                queryset = queryset.filter(
                    Q(name__icontains=term) | Q(phone__icontains=term)
                    | Q(email__icontains=term) | Q(document__icontains=term)
                )
        return queryset

    def perform_create(self, serializer):
        customer = serializer.save()
        audit_log(actor=self.request.user, action='customer.create', obj=customer,
                  company=customer.company, after=model_snapshot(customer, self.audit_fields))

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, self.audit_fields)
        customer = serializer.save()
        audit_log(actor=self.request.user, action='customer.update', obj=customer,
                  company=customer.company, before=before,
                  after=model_snapshot(customer, self.audit_fields))

    @action(detail=True, methods=('post',))
    def deactivate(self, request, pk=None):
        customer = self.get_object()
        before = model_snapshot(customer, self.audit_fields)
        customer.status = Status.INACTIVE
        customer.save(update_fields=('status', 'updated_at'))
        audit_log(actor=request.user, action='customer.deactivate', obj=customer,
                  company=customer.company, before=before,
                  after=model_snapshot(customer, self.audit_fields))
        return Response(self.get_serializer(customer).data)

    @action(detail=True, methods=('post',))
    def activate(self, request, pk=None):
        customer = self.get_object()
        before = model_snapshot(customer, self.audit_fields)
        customer.status = Status.ACTIVE
        customer.save(update_fields=('status', 'updated_at'))
        audit_log(actor=request.user, action='customer.activate', obj=customer,
                  company=customer.company, before=before,
                  after=model_snapshot(customer, self.audit_fields))
        return Response(self.get_serializer(customer).data)

    @action(detail=False, methods=('get',))
    def search(self, request):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(queryset, many=True).data)


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
        support_session = getattr(self.request, 'support_session', None)
        if support_session:
            return Company.objects.filter(pk=support_session.company_id).prefetch_related(
                Prefetch(
                    'branches',
                    queryset=Branch.objects.filter(company_id=support_session.company_id).select_related('company', 'settings'),
                    to_attr='visible_branches',
                ),
                Prefetch(
                    'user_accesses',
                    queryset=UserCompanyAccess.objects.filter(is_owner=True).select_related('user'),
                    to_attr='owner_accesses',
                ),
            )
        if self.action == 'transfer_owner':
            companies = Company.objects.filter(
                user_accesses__user=self.request.user,
                user_accesses__is_owner=True,
                user_accesses__is_active=True,
            )
        else:
            permission_code = self.permission_codes.get(self.action, 'companies.view')
            companies = accessible_companies(self.request.user, permission_code)
        return companies.prefetch_related(
            Prefetch(
                'branches',
                queryset=accessible_branches(
                    self.request.user, 'branches.view'
                ).select_related('company', 'settings'),
                to_attr='visible_branches',
            ),
            Prefetch(
                'user_accesses',
                queryset=UserCompanyAccess.objects.filter(is_owner=True).select_related('user'),
                to_attr='owner_accesses',
            ),
        )

    def get_permissions(self):
        support_session = getattr(self.request, 'support_session', None)
        if self.action == 'transfer_owner' or (
            support_session
            and not support_session.impersonated_user_id
            and self.action in {'list', 'retrieve', 'update', 'partial_update'}
        ):
            return [FunctionalCompanyPermission()]
        return [IsPlatformAdmin()]

    def perform_create(self, serializer):
        company = serializer.save()
        operation_reference = str(uuid.uuid4())
        operation_metadata = {
            'source': 'company.create',
            'operation_reference': operation_reference,
        }
        fields = ('trade_name', 'legal_name', 'cnpj', 'email', 'phone', 'status')
        audit_log(
            actor=self.request.user, action='company.create', obj=company,
            company=company, after=model_snapshot(company, fields),
            metadata=operation_metadata,
        )
        matrix = company.branches.filter(is_matrix=True).first()
        if matrix:
            audit_log(
                actor=self.request.user, action='branch.create', obj=matrix,
                company=company, branch=matrix,
                after=model_snapshot(matrix, ('name', 'status', 'is_matrix', 'address_pending')),
                metadata=operation_metadata,
            )
            settings = BranchSettings.objects.filter(branch=matrix).first()
            if settings:
                audit_log(
                    actor=self.request.user, action='branch_settings.create',
                    obj=settings, company=company, branch=matrix,
                    after=model_snapshot(settings, (
                        'allow_negative_stock', 'service_fee_rate',
                        'commission_rate', 'fixed_daily_cost', 'uses_tables',
                        'uses_commands', 'uses_counter', 'uses_consumption',
                        'uses_cash_register', 'charges_service_fee',
                    )), metadata=operation_metadata,
                )
        for profile in company.access_profiles.prefetch_related('permissions'):
            after = model_snapshot(profile, (
                'name', 'description', 'status', 'receives_commission',
                'commission_rate',
            ))
            after['permission_codes'] = sorted(
                profile.permissions.values_list('code', flat=True)
            )
            audit_log(
                actor=self.request.user, action='access_profile.create',
                obj=profile, company=company, after=after,
                metadata=operation_metadata,
            )
        from apps.sales.models import PaymentMethod

        for method in PaymentMethod.objects.filter(company=company):
            audit_log(
                actor=self.request.user, action='payment_method.create',
                obj=method, company=company,
                after=model_snapshot(method, ('code', 'name', 'status', 'is_system')),
                metadata=operation_metadata,
            )
        for access in UserCompanyAccess.objects.filter(company=company):
            audit_log(
                actor=self.request.user, action='user_company_access.create',
                obj=access, company=company,
                after=model_snapshot(
                    access, ('user_id', 'access_profile_id', 'is_active', 'is_owner')
                ),
                metadata=operation_metadata,
            )
        for access in UserBranchAccess.objects.filter(branch__company=company).select_related('branch'):
            audit_log(
                actor=self.request.user, action='user_branch_access.create',
                obj=access, company=company, branch=access.branch,
                after=model_snapshot(access, ('user_id', 'access_profile_id', 'is_active')),
                metadata=operation_metadata,
            )

    def perform_update(self, serializer):
        fields = ('trade_name', 'legal_name', 'cnpj', 'email', 'phone', 'status')
        before = model_snapshot(serializer.instance, fields)
        company = serializer.save()
        audit_log(
            actor=self.request.user, action='company.update', obj=company,
            company=company, before=before, after=model_snapshot(company, fields),
        )

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        company = self.get_object()
        before = model_snapshot(company, ('status',))
        company = activate_company(company=company)
        audit_log(
            actor=request.user, action='company.activate', obj=company,
            company=company, before=before, after=model_snapshot(company, ('status',)),
        )
        company = self.get_queryset().get(pk=company.pk)
        return Response(self.get_serializer(company).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        company = self.get_object()
        before = model_snapshot(company, ('status',))
        active_branches = list(company.branches.filter(status=Status.ACTIVE))
        company = deactivate_company(company=company)
        audit_log(
            actor=request.user, action='company.deactivate', obj=company,
            company=company, before=before, after=model_snapshot(company, ('status',)),
        )
        for branch in active_branches:
            branch.status = Status.INACTIVE
            audit_log(
                actor=request.user, action='branch.deactivate', obj=branch,
                company=company, branch=branch,
                before={'status': Status.ACTIVE}, after={'status': Status.INACTIVE},
                metadata={'source': 'company.deactivate'},
            )
        company = self.get_queryset().get(pk=company.pk)
        return Response(self.get_serializer(company).data)

    @action(detail=True, methods=['post'], url_path='transfer-owner')
    def transfer_owner(self, request, pk=None):
        company = self.get_object()
        serializer = TransferCompanyOwnerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transfer_company_owner(
            company=company,
            actor=request.user,
            **serializer.validated_data,
        )
        company = Company.objects.prefetch_related(
            Prefetch(
                'user_accesses',
                queryset=UserCompanyAccess.objects.filter(is_owner=True).select_related('user'),
                to_attr='owner_accesses',
            )
        ).get(pk=company.pk)
        return Response(self.get_serializer(company).data)


class BranchViewSet(viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    permission_classes = [FunctionalCompanyPermission]
    permission_codes = {
        'list': 'branches.view',
        'retrieve': 'branches.view',
        'overview': 'branches.view',
        'create': 'branches.add',
        'update': 'branches.change',
        'partial_update': 'branches.change',
        'activate': 'branches.change',
        'deactivate': 'branches.change',
        'branch_settings': 'branches.change_settings',
    }
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        support_session = getattr(self.request, 'support_session', None)
        if support_session:
            return Branch.objects.filter(company_id=support_session.company_id).select_related(
                'company', 'settings'
            )
        company_id = self.request.query_params.get('company')
        if not company_id:
            branch_id = self.request.headers.get('X-Branch-ID')
            if branch_id:
                company_id = Branch.objects.filter(pk=branch_id).values_list('company_id', flat=True).first()
        if not company_id:
            raise ValidationError({'company': 'Selecione uma empresa para consultar filiais.'})
        try:
            company_id = int(company_id)
        except (TypeError, ValueError) as error:
            raise ValidationError({'company': 'Informe uma empresa válida.'}) from error
        permission_code = self.permission_codes.get(self.action, 'branches.view')
        return accessible_branches(
            self.request.user, permission_code
        ).filter(company_id=company_id).select_related('company', 'settings')

    @action(detail=False, methods=['get'])
    def overview(self, request):
        company_id = request.query_params.get('company')
        if not company_id:
            raise ValidationError({'company': 'Selecione uma empresa para consultar o negócio.'})
        try:
            company_id = int(company_id)
        except (TypeError, ValueError) as error:
            raise ValidationError({'company': 'Informe uma empresa válida.'}) from error
        branches = self.get_queryset().filter(company_id=company_id)
        company = Company.objects.filter(pk=company_id).first()
        if not company:
            raise PermissionDenied('Empresa fora do contexto autorizado.')
        branch_ids = branches.values_list('pk', flat=True)
        from apps.production.models import PrinterDevice
        from apps.products.models import Product

        return Response({
            'company': {
                'id': company.pk,
                'trade_name': company.trade_name,
                'status': company.status,
            },
            'counts': {
                'branches': branches.count(),
                'products': Product.objects.filter(
                    company_id=company_id, archived_at__isnull=True,
                ).count(),
                'active_users': User.objects.filter(
                    is_active=True,
                    archived_at__isnull=True,
                    company_accesses__company_id=company_id,
                    company_accesses__is_active=True,
                ).distinct().count(),
                'printer_devices': PrinterDevice.objects.filter(
                    branch_id__in=branch_ids
                ).count(),
            },
        })

    def perform_create(self, serializer):
        branch = serializer.save()
        operation_metadata = {
            'source': 'branch.create',
            'operation_reference': str(uuid.uuid4()),
        }
        audit_log(
            actor=self.request.user, action='branch.create', obj=branch,
            company=branch.company, branch=branch,
            after=model_snapshot(branch, ('name', 'cnpj', 'phone', 'email', 'address', 'status')),
            metadata=operation_metadata,
        )
        settings = BranchSettings.objects.filter(branch=branch).first()
        if settings:
            audit_log(
                actor=self.request.user, action='branch_settings.create',
                obj=settings, company=branch.company, branch=branch,
                after=model_snapshot(settings, (
                    'allow_negative_stock', 'service_fee_rate',
                    'commission_rate', 'fixed_daily_cost', 'uses_tables',
                    'uses_commands', 'uses_counter', 'uses_consumption',
                    'uses_cash_register', 'charges_service_fee',
                )), metadata=operation_metadata,
            )
        for access in UserBranchAccess.objects.filter(branch=branch):
            audit_log(
                actor=self.request.user, action='user_branch_access.create',
                obj=access, company=branch.company, branch=branch,
                after=model_snapshot(access, ('user_id', 'access_profile_id', 'is_active')),
                metadata=operation_metadata,
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
        before = model_snapshot(branch, ('status',))
        branch = activate_branch(branch=branch)
        audit_log(
            actor=request.user, action='branch.activate', obj=branch,
            company=branch.company, branch=branch, before=before,
            after=model_snapshot(branch, ('status',)),
        )
        return Response(self.get_serializer(branch).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        branch = self.get_object()
        before = model_snapshot(branch, ('status',))
        branch.status = Status.INACTIVE
        branch.save(update_fields=['status', 'updated_at'])
        audit_log(
            actor=request.user, action='branch.deactivate', obj=branch,
            company=branch.company, branch=branch, before=before,
            after=model_snapshot(branch, ('status',)),
        )
        return Response(self.get_serializer(branch).data)

    @action(detail=True, methods=['get', 'put', 'patch'], url_path='settings')
    @transaction.atomic
    def branch_settings(self, request, pk=None):
        branch = self.get_object()
        if request.method == 'GET':
            instance = BranchSettings.objects.filter(branch=branch).first() or BranchSettings(branch=branch)
            return Response(BranchSettingsSerializer(instance, context={'request': request}).data)
        branch = Branch.objects.select_for_update().get(pk=branch.pk)
        instance, _ = BranchSettings.objects.select_for_update().get_or_create(branch=branch)
        serializer = BranchSettingsSerializer(instance, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        fields = (
            'allow_negative_stock', 'service_fee_rate', 'commission_rate',
            'fixed_daily_cost', 'uses_tables', 'uses_commands', 'uses_counter',
            'uses_consumption', 'uses_cash_register', 'charges_service_fee',
            'default_table_quantity', 'default_table_seats', 'default_table_prefix',
            'consumption_limit_enabled', 'command_consumption_limit', 'table_consumption_limit',
        )
        before = model_snapshot(instance, fields)
        serializer.save()
        audit_log(
            actor=request.user,
            action='branch_settings.update',
            obj=instance,
            company=branch.company,
            branch=branch,
            before=before,
            after=model_snapshot(instance, fields),
        )
        return Response(BranchSettingsSerializer(instance, context={'request': request}).data)

    @action(detail=True, methods=['get'], url_path='features')
    def branch_features(self, request, pk=None):
        branch = self.get_object()
        return Response(branch_feature_states(branch))


class CanViewPermissionCatalog(BasePermission):
    message = 'Você não possui permissão para visualizar perfis de acesso.'

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        company_id = request.query_params.get('company')
        if company_id:
            return user_has_company_permission(user, company_id, 'access_profiles.view')
        return accessible_companies(user, 'access_profiles.view').exists()


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
    message = 'Você não possui permissão para esta operação.'
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
        return accessible_companies(user, code).exists()

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
        support_session = getattr(self.request, 'support_session', None)
        if support_session:
            queryset = queryset.filter(company_id=support_session.company_id)
        user = self.request.user
        if not user.is_superuser:
            permission_code = AccessProfilePermission.codes.get(
                self.action, 'access_profiles.view'
            )
            queryset = queryset.filter(
                company__in=accessible_companies(user, permission_code)
            )
        company_id = self.request.query_params.get('company')
        profile_status = self.request.query_params.get('status')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        if profile_status:
            queryset = queryset.filter(status=profile_status)
        return queryset

    def perform_create(self, serializer):
        profile = serializer.save()
        after = model_snapshot(profile, ('name', 'description', 'status', 'receives_commission', 'commission_rate'))
        after['permission_codes'] = sorted(profile.permissions.values_list('code', flat=True))
        audit_log(
            actor=self.request.user,
            action='access_profile.create',
            obj=profile,
            company=profile.company,
            after=after,
        )

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('name', 'description', 'status', 'receives_commission', 'commission_rate'))
        before['permission_codes'] = sorted(
            serializer.instance.permissions.values_list('code', flat=True)
        )
        profile = serializer.save()
        after = model_snapshot(profile, ('name', 'description', 'status', 'receives_commission', 'commission_rate'))
        after['permission_codes'] = sorted(profile.permissions.values_list('code', flat=True))
        audit_log(
            actor=self.request.user,
            action='access_profile.update',
            obj=profile,
            company=profile.company,
            before=before,
            after=after,
        )

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        profile = self.get_object()
        before = model_snapshot(profile, ('name', 'status'))
        profile.status = Status.ACTIVE
        profile.save(update_fields=['status', 'updated_at'])
        audit_log(actor=request.user, action='access_profile.activate', obj=profile, company=profile.company, before=before, after=model_snapshot(profile, ('name', 'status')))
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
                {'status': ['Você não pode inativar seu próprio perfil ativo nesta empresa.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile.status = Status.INACTIVE
        profile.save(update_fields=['status', 'updated_at'])
        audit_log(actor=request.user, action='access_profile.deactivate', obj=profile, company=profile.company, before={'name': profile.name, 'status': Status.ACTIVE}, after=model_snapshot(profile, ('name', 'status')))
        return Response(self.get_serializer(profile).data)

    @action(detail=True, methods=['get'])
    def users(self, request, pk=None):
        profile = self.get_object()
        users = User.objects.filter(
            branch_accesses__access_profile=profile,
            branch_accesses__is_active=True,
            is_active=True,
            archived_at__isnull=True,
        ).distinct().order_by('first_name', 'last_name', 'email')
        data = [
            {
                'id': u.id,
                'email': u.email,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'user_type': u.user_type,
                'is_active': u.is_active,
                'can_login': u.can_login,
            }
            for u in users
        ]
        return Response(data)


class UserPermissionBlockPermission(BasePermission):
    message = 'Você não possui permissão para bloqueios individuais.'

    @staticmethod
    def code_for_action(action_name):
        return (
            'user_permission_blocks.view'
            if action_name in ('list', 'retrieve', 'list_filters')
            else 'user_permission_blocks.change'
        )

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if user.is_superuser:
            return True
        code = self.code_for_action(view.action)
        company_id = request.query_params.get('company') or request.data.get('company')
        branch_id = request.query_params.get('branch') or request.data.get('branch')
        if branch_id and not company_id:
            branch = Branch.objects.filter(pk=branch_id).only('company_id').first()
            company_id = branch.company_id if branch else None
        if company_id:
            return user_has_company_permission(user, company_id, code)
        return accessible_companies(user, code).exists()

    def has_object_permission(self, request, view, obj):
        return user_has_company_permission(
            request.user,
            obj.company_id,
            self.code_for_action(view.action),
        )


class UserPermissionBlockViewSet(viewsets.ModelViewSet):
    serializer_class = UserPermissionBlockSerializer
    permission_classes = (UserPermissionBlockPermission,)
    http_method_names = ('get', 'post', 'head', 'options')

    def get_queryset(self):
        queryset = UserPermissionBlock.objects.select_related(
            'company', 'branch', 'user', 'permission', 'created_by', 'revoked_by'
        )
        support_session = getattr(self.request, 'support_session', None)
        if support_session:
            queryset = queryset.filter(company_id=support_session.company_id)
        user = self.request.user
        if not user.is_superuser:
            permission_code = UserPermissionBlockPermission.code_for_action(self.action)
            company_ids = accessible_companies(user, permission_code).values_list('id', flat=True)
            queryset = queryset.filter(company_id__in=company_ids)
        params = self.request.query_params
        for field in ('company', 'branch', 'user'):
            value = params.get(field)
            if not value:
                continue
            try:
                value = int(value)
                if value < 1:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise ValidationError({field: 'Informe um identificador válido.'}) from error
            queryset = queryset.filter(**{f'{field}_id': value})
        search = params.get('search', '').strip()
        for term in search.split():
            queryset = queryset.filter(
                Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__email__icontains=term)
            )
        if params.get('module'):
            queryset = queryset.filter(permission__module=params['module'])
        if params.get('permission'):
            queryset = queryset.filter(permission__code=params['permission'])
        scope = params.get('scope')
        if scope:
            if scope not in ('company', 'branch'):
                raise ValidationError({'scope': 'Informe company ou branch.'})
            if scope == 'company' and params.get('branch'):
                raise ValidationError({
                    'branch': 'Filial nao pode ser usada com escopo company.'
                })
            queryset = queryset.filter(branch__isnull=scope == 'company')
        active = params.get('active')
        if active:
            if active not in ('true', 'false'):
                raise ValidationError({'active': 'Informe true ou false.'})
            queryset = queryset.filter(is_active=active == 'true')
        return queryset.order_by('-created_at', '-id')

    def perform_create(self, serializer):
        block = serializer.save()
        self._audit_create(block, uuid.uuid4())

    def _audit_create(self, block, operation_reference):
        after = model_snapshot(block, ('reason', 'is_active'))
        after.update({
            'user_name': str(block.user),
            'permission_label': block.permission.label,
        })
        audit_log(
            actor=self.request.user,
            action='user_permission_block.create',
            obj=block,
            company=block.company,
            branch=block.branch,
            after=after,
            metadata={'operation_reference': str(operation_reference)},
        )

    def _audit_revoke(self, block, before, operation_reference):
        audit_log(
            actor=self.request.user,
            action='user_permission_block.revoke',
            obj=block,
            company=block.company,
            branch=block.branch,
            before=before,
            after=model_snapshot(block, ('is_active', 'revoked_at', 'revoked_by_id')),
            metadata={'operation_reference': str(operation_reference)},
        )

    @action(detail=False, methods=('get',), url_path='list-filters')
    def list_filters(self, request):
        company_id = request.query_params.get('company')
        try:
            company_id = int(company_id)
            if company_id < 1:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise ValidationError({'company': 'Informe uma empresa válida.'}) from error
        if not Company.objects.filter(pk=company_id).exists():
            raise ValidationError({'company': 'Informe uma empresa válida.'})
        branches = Branch.objects.filter(
            company_id=company_id, status=Status.ACTIVE
        ).order_by('name', 'id')
        permissions = FunctionalPermission.objects.filter(
            status=Status.ACTIVE
        ).order_by('module', 'label', 'code')
        return Response({
            'branches': [
                {'id': branch.pk, 'name': branch.name} for branch in branches
            ],
            'permissions': FunctionalPermissionSerializer(
                permissions, many=True
            ).data,
        })

    @action(detail=False, methods=('get',), url_path='options')
    def block_options(self, request):
        company_id = request.query_params.get('company')
        try:
            company_id = int(company_id)
        except (TypeError, ValueError) as error:
            raise ValidationError({'company': 'Informe uma empresa válida.'}) from error
        company = Company.objects.filter(pk=company_id).first()
        if not company:
            raise ValidationError({'company': 'Informe uma empresa válida.'})

        users = User.objects.filter(
            is_active=True,
            archived_at__isnull=True,
            can_login=True,
            is_superuser=False,
            company_accesses__company=company,
            company_accesses__is_active=True,
            company_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
            branch_accesses__branch__company=company,
            branch_accesses__is_active=True,
            branch_accesses__access_profile__status=Status.ACTIVE,
        ).distinct().order_by('first_name', 'last_name', 'email', 'id')
        branches = Branch.objects.filter(
            company=company, status=Status.ACTIVE
        ).order_by('name', 'id')
        permissions = FunctionalPermission.objects.none()

        target_id = request.query_params.get('user')
        branch_id = request.query_params.get('branch')
        if target_id:
            try:
                target_id = int(target_id)
                branch_id = int(branch_id) if branch_id else None
            except (TypeError, ValueError) as error:
                raise ValidationError({'detail': 'Usuario ou filial invalida.'}) from error
            target = users.filter(pk=target_id).first()
            if not target:
                raise ValidationError({'user': 'Usuario fora das opcoes de bloqueio.'})
            branches = branches.filter(
                user_accesses__user=target,
                user_accesses__is_active=True,
                user_accesses__access_profile__status=Status.ACTIVE,
            ).distinct()
            if branch_id and not branches.filter(pk=branch_id).exists():
                raise ValidationError({'branch': 'Filial fora da empresa selecionada.'})
            codes = blockable_permission_codes(target, company.id, branch_id)
            permissions = FunctionalPermission.objects.filter(
                status=Status.ACTIVE, code__in=codes
            ).order_by('module', 'label', 'code')

        return Response({
            'users': [
                {'id': target.pk, 'name': str(target), 'email': target.email}
                for target in users
            ],
            'branches': [
                {'id': branch.pk, 'name': branch.name}
                for branch in branches
            ],
            'permissions': FunctionalPermissionSerializer(permissions, many=True).data,
        })

    @action(detail=False, methods=('post',), url_path='batch-apply')
    def batch_apply(self, request):
        permission_codes = request.data.get('permission_codes')
        if not isinstance(permission_codes, list) or not permission_codes:
            raise ValidationError({'permission_codes': 'Selecione ao menos uma permissão.'})
        if (
            any(not isinstance(code, str) or not code for code in permission_codes)
            or len(permission_codes) != len(set(permission_codes))
        ):
            raise ValidationError({'permission_codes': 'Informe codigos validos e sem repeticao.'})

        operation_reference = uuid.uuid4()
        with transaction.atomic():
            serializers = []
            for code in permission_codes:
                serializer = self.get_serializer(data={
                    'company': request.data.get('company'),
                    'branch': request.data.get('branch'),
                    'user': request.data.get('user'),
                    'permission_code': code,
                    'reason': request.data.get('reason', ''),
                })
                serializer.is_valid(raise_exception=True)
                serializers.append(serializer)
            blocks = [serializer.save() for serializer in serializers]
            for block in blocks:
                self._audit_create(block, operation_reference)

        return Response({
            'operation_reference': str(operation_reference),
            'count': len(blocks),
            'results': self.get_serializer(blocks, many=True).data,
        }, status=status.HTTP_201_CREATED)

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
        self._audit_revoke(block, before, uuid.uuid4())
        return Response(self.get_serializer(block).data)

    @action(detail=False, methods=('post',), url_path='batch-revoke')
    def batch_revoke(self, request):
        block_ids = request.data.get('block_ids')
        if not isinstance(block_ids, list) or not block_ids:
            raise ValidationError({'block_ids': 'Selecione ao menos um bloqueio.'})
        if (
            any(not isinstance(block_id, int) or isinstance(block_id, bool) or block_id < 1 for block_id in block_ids)
            or len(block_ids) != len(set(block_ids))
        ):
            raise ValidationError({'block_ids': 'Informe bloqueios validos e sem repeticao.'})

        operation_reference = uuid.uuid4()
        with transaction.atomic():
            blocks = list(
                self.get_queryset().select_for_update(of=('self',)).filter(pk__in=block_ids)
            )
            if len(blocks) != len(block_ids):
                raise PermissionDenied('Um ou mais bloqueios estao fora do seu escopo autorizado.')
            if any(not block.is_active for block in blocks):
                raise ValidationError({'block_ids': 'Um ou mais bloqueios ja foram revogados.'})
            revoked_at = timezone.now()
            for block in blocks:
                before = model_snapshot(block, ('is_active', 'revoked_at', 'revoked_by_id'))
                block.is_active = False
                block.revoked_by = request.user
                block.revoked_at = revoked_at
                block.save(update_fields=('is_active', 'revoked_by', 'revoked_at', 'updated_at'))
                self._audit_revoke(block, before, operation_reference)

        return Response({
            'operation_reference': str(operation_reference),
            'count': len(blocks),
            'results': self.get_serializer(blocks, many=True).data,
        })


class CommissionOverridePermission(BasePermission):
    message = 'Você não possui permissão para comissões nesta filial.'

    @staticmethod
    def codes_for_action(view):
        codes = view.permission_codes.get(view.action, ())
        return codes if isinstance(codes, tuple) else (codes,)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.can_login or not user.is_active:
            return False
        if user.is_superuser:
            return True
        codes = self.codes_for_action(view)
        if not codes:
            return False
        branch_id = request.data.get('branch') or request.query_params.get('branch')
        if branch_id:
            return any(user_has_branch_permission(user, branch_id, code) for code in codes)
        return any(accessible_branches(user, code).exists() for code in codes)

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        return any(
            user_has_branch_permission(request.user, obj.branch_id, code)
            for code in self.codes_for_action(view)
        )


class UserCommissionOverrideViewSet(viewsets.ModelViewSet):
    serializer_class = UserCommissionOverrideSerializer
    permission_classes = (CommissionOverridePermission,)
    permission_codes = {
        'list': ('commissions.view', 'commissions.change_user_override'),
        'retrieve': ('commissions.view', 'commissions.change_user_override'),
        'create': 'commissions.change_user_override',
        'update': 'commissions.change_user_override',
        'partial_update': 'commissions.change_user_override',
        'destroy': 'commissions.change_user_override',
    }
    http_method_names = ('get', 'post', 'patch', 'put', 'delete', 'head', 'options')

    def get_queryset(self):
        queryset = UserCommissionOverride.objects.filter(archived_at__isnull=True).select_related('branch', 'branch__company', 'user')
        support_session = getattr(self.request, 'support_session', None)
        if support_session:
            queryset = queryset.filter(branch__company_id=support_session.company_id)
        user = self.request.user
        if not user.is_superuser:
            branch_scope = Branch.objects.none()
            for code in CommissionOverridePermission.codes_for_action(self):
                branch_scope = branch_scope | accessible_branches(user, code)
            queryset = queryset.filter(branch__in=branch_scope)
        params = self.request.query_params
        for field in ('branch', 'user'):
            if params.get(field):
                queryset = queryset.filter(**{f'{field}_id': params[field]})
        return queryset.distinct()

    def perform_create(self, serializer):
        override = serializer.save()
        after = model_snapshot(override, ('receives_commission', 'commission_rate'))
        after['user_name'] = str(override.user)
        audit_log(actor=self.request.user, action='commission_override.create', obj=override, company=override.branch.company, branch=override.branch, after=after)

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('receives_commission', 'commission_rate'))
        before['user_name'] = str(serializer.instance.user)
        override = serializer.save()
        after = model_snapshot(override, ('receives_commission', 'commission_rate'))
        after['user_name'] = str(override.user)
        audit_log(actor=self.request.user, action='commission_override.update', obj=override, company=override.branch.company, branch=override.branch, before=before, after=after)

    @transaction.atomic
    def perform_destroy(self, instance):
        before = model_snapshot(instance, (
            'id', 'branch_id', 'user_id', 'receives_commission', 'commission_rate',
            'updated_by_id', 'created_at', 'updated_at',
        ))
        audit_log(
            actor=self.request.user,
            action='commission_override.delete',
            obj=instance,
            company=instance.branch.company,
            branch=instance.branch,
            before=before,
            metadata={
                'branch_name': instance.branch.name,
                'company_name': instance.branch.company.trade_name,
                'user_name': str(instance.user),
                'user_email': instance.user.email,
            },
        )
        instance.delete()
