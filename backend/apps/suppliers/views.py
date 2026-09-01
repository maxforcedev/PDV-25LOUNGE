from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot
from apps.companies.models import Branch, Status
from apps.companies.permissions import FunctionalCompanyPermission
from apps.companies.selectors import accessible_companies

from .models import (
    PresentationPreset, ProductPurchasePresentation, ProductSupplier,
    ProductSupplierUnit, Supplier,
)
from .serializers import (
    ProductPurchasePresentationSerializer,
    ProductSupplierSerializer,
    ProductSupplierUnitSerializer,
    PresentationPresetSerializer,
    SupplierSerializer,
)
from .services import (
    _lock_instance,
    _set_product_purchase_presentation_status,
    _set_product_supplier_status,
    _set_product_supplier_unit_status,
    _set_presentation_preset_status,
    _set_supplier_status,
    soft_delete_supplier,
    restore_supplier,
)


class SupplierDomainViewSet(viewsets.ModelViewSet):
    permission_classes = (FunctionalCompanyPermission,)
    http_method_names = ('get', 'post', 'put', 'patch', 'head', 'options')
    permission_codes = {
        'list': 'suppliers.view',
        'retrieve': 'suppliers.view',
        'create': 'suppliers.change',
        'update': 'suppliers.change',
        'partial_update': 'suppliers.change',
        'destroy': 'suppliers.change',
        'activate': 'suppliers.change',
        'deactivate': 'suppliers.change',
        'restore': 'suppliers.change',
    }
    audit_name = None
    audit_fields = ()
    status_service = None

    def scope_company(self, queryset):
        support_session = getattr(self.request, 'support_session', None)
        if support_session:
            queryset = queryset.filter(company_id=support_session.company_id)
        elif not self.request.user.is_superuser:
            code = self.permission_codes[self.action]
            queryset = queryset.filter(
                company__in=accessible_companies(self.request.user, code)
            )
        company = self.request.query_params.get('company')
        if company:
            queryset = queryset.filter(company_id=company)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save()
        audit_log(
            actor=self.request.user,
            action=f'{self.audit_name}.create',
            obj=instance,
            company=instance.company,
            after=model_snapshot(instance, self.audit_fields),
        )

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.instance = _lock_instance(serializer.instance)
        before = model_snapshot(serializer.instance, self.audit_fields)
        instance = serializer.save()
        audit_log(
            actor=self.request.user,
            action=f'{self.audit_name}.update',
            obj=instance,
            company=instance.company,
            before=before,
            after=model_snapshot(instance, self.audit_fields),
        )

    def _set_status(self, request, status, action_name):
        instance = self.get_object()
        instance = _lock_instance(instance)
        before = model_snapshot(instance, self.audit_fields)
        instance = self.status_service(instance=instance, status=status)
        audit_log(
            actor=request.user,
            action=f'{self.audit_name}.{action_name}',
            obj=instance,
            company=instance.company,
            before=before,
            after=model_snapshot(instance, self.audit_fields),
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def activate(self, request, pk=None):
        return self._set_status(request, Status.ACTIVE, 'activate')

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def deactivate(self, request, pk=None):
        return self._set_status(request, Status.INACTIVE, 'deactivate')


class SupplierViewSet(SupplierDomainViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    audit_name = 'supplier'
    audit_fields = (
        'company_id', 'legal_name', 'trade_name', 'tax_id', 'phone', 'email',
        'contact_name', 'address', 'notes', 'status',
    )
    status_service = staticmethod(_set_supplier_status)
    http_method_names = (*SupplierDomainViewSet.http_method_names, 'delete')

    def _branch_context(self):
        branch = getattr(self.request, 'branch_context', None)
        if branch is not None:
            return branch
        branch_id = self.request.headers.get('X-Branch-ID')
        if not branch_id:
            return None
        try:
            branch = Branch.objects.select_related('company').get(
                pk=branch_id, status=Status.ACTIVE, company__status=Status.ACTIVE,
            )
        except (Branch.DoesNotExist, TypeError, ValueError):
            raise PermissionDenied('Selecione uma filial ativa e autorizada.')
        support = getattr(self.request, 'support_session', None)
        support_allowed = bool(support and support.company_id == branch.company_id)
        allowed_companies = accessible_companies(
            self.request.user, self.permission_codes[self.action]
        )
        if (
            not self.request.user.is_superuser
            and not support_allowed
            and not allowed_companies.filter(pk=branch.company_id).exists()
        ):
            raise PermissionDenied('Filial fora do contexto autorizado.')
        self.request.branch_context = branch
        return branch

    def get_serializer_context(self):
        self._branch_context()
        return super().get_serializer_context()

    def get_queryset(self):
        queryset = self.scope_company(Supplier.objects.select_related('company', 'branch')).filter(
            deleted_at__isnull=True,
        )
        branch = self._branch_context()
        if branch:
            queryset = queryset.filter(branch=branch)
        params = self.request.query_params
        supplier_status = params.get('status')
        if supplier_status:
            if supplier_status not in Status.values:
                raise ValidationError({'status': 'Informe um status válido.'})
            queryset = queryset.filter(status=supplier_status)
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(legal_name__icontains=search)
                | Q(trade_name__icontains=search)
                | Q(tax_id__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(contact_name__icontains=search)
            )
        return queryset.order_by('trade_name', 'legal_name', 'id')

    @transaction.atomic
    def perform_create(self, serializer):
        branch = self._branch_context()
        if branch is None:
            raise PermissionDenied('Selecione a filial ativa.')
        supplier = serializer.save(branch=branch)
        audit_log(
            actor=self.request.user, action='supplier.create', obj=supplier,
            company=supplier.company, branch=branch,
            after=model_snapshot(supplier, self.audit_fields),
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        before = model_snapshot(instance, ('status', 'deleted_at', 'deleted_by_id'))
        supplier = soft_delete_supplier(supplier=instance, user=self.request.user)
        audit_log(
            actor=self.request.user, action='supplier.delete', obj=supplier,
            company=supplier.company, branch=supplier.branch, before=before,
            after=model_snapshot(supplier, ('status', 'deleted_at', 'deleted_by_id')),
        )

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def restore(self, request, pk=None):
        branch = self._branch_context()
        supplier = self.scope_company(Supplier.objects.select_related(
            'company', 'branch'
        )).filter(
            pk=pk, branch=branch, deleted_at__isnull=False,
        ).first()
        if supplier is None:
            raise NotFound('Fornecedor excluído não encontrado nesta filial.')
        before = model_snapshot(supplier, ('status', 'deleted_at', 'deleted_by_id'))
        try:
            supplier = restore_supplier(supplier=supplier)
        except DjangoValidationError as error:
            raise ValidationError(
                getattr(error, 'message_dict', {'supplier': error.messages})
            ) from error
        audit_log(
            actor=request.user, action='supplier.restore', obj=supplier,
            company=supplier.company, branch=supplier.branch, before=before,
            after=model_snapshot(supplier, ('status', 'deleted_at', 'deleted_by_id')),
        )
        return Response(self.get_serializer(supplier).data)


class ProductSupplierViewSet(SupplierDomainViewSet):
    queryset = ProductSupplier.objects.all()
    serializer_class = ProductSupplierSerializer
    audit_name = 'product_supplier'
    audit_fields = (
        'company_id', 'product_id', 'supplier_id', 'supplier_code', 'is_preferred',
        'is_exclusive', 'status',
    )
    status_service = staticmethod(_set_product_supplier_status)

    def get_queryset(self):
        queryset = self.scope_company(ProductSupplier.objects.select_related(
            'company', 'product', 'supplier'
        ))
        branch = getattr(self.request, 'branch_context', None)
        if branch:
            queryset = queryset.filter(
                product__branch_configs__branch=branch,
                product__branch_configs__is_available=True,
                supplier__branch=branch,
                supplier__deleted_at__isnull=True,
            )
        params = self.request.query_params
        for field in ('product', 'supplier'):
            if params.get(field):
                queryset = queryset.filter(**{f'{field}_id': params[field]})
        relation_status = params.get('status')
        if relation_status:
            if relation_status not in Status.values:
                raise ValidationError({'status': 'Informe um status válido.'})
            queryset = queryset.filter(status=relation_status)
        for field in ('is_preferred', 'is_exclusive'):
            value = params.get(field)
            if value:
                if value not in ('true', 'false'):
                    raise ValidationError({field: 'Informe true ou false.'})
                queryset = queryset.filter(**{field: value == 'true'})
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(product__name__icontains=search)
                | Q(supplier__trade_name__icontains=search)
                | Q(supplier__legal_name__icontains=search)
                | Q(supplier_code__icontains=search)
            )
        return queryset.order_by(
            'product__name', '-is_exclusive', '-is_preferred', 'supplier__trade_name', 'id'
        )


class ProductPurchasePresentationViewSet(SupplierDomainViewSet):
    queryset = ProductPurchasePresentation.objects.all()
    serializer_class = ProductPurchasePresentationSerializer
    permission_codes = {
        'list': 'products.view',
        'retrieve': 'products.view',
        'create': 'products.change',
        'update': 'products.change',
        'partial_update': 'products.change',
        'destroy': 'products.change',
        'activate': 'products.change',
        'deactivate': 'products.change',
    }
    audit_name = 'product_purchase_presentation'
    audit_fields = (
        'company_id', 'product_id', 'unit_code', 'description', 'conversion_factor',
        'status',
    )
    status_service = staticmethod(_set_product_purchase_presentation_status)

    def get_queryset(self):
        queryset = self.scope_company(ProductPurchasePresentation.objects.select_related(
            'company', 'product'
        ))
        params = self.request.query_params
        if params.get('product'):
            queryset = queryset.filter(product_id=params['product'])
        presentation_status = params.get('status')
        if presentation_status:
            if presentation_status not in Status.values:
                raise ValidationError({'status': 'Informe um status válido.'})
            queryset = queryset.filter(status=presentation_status)
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(unit_code__icontains=search)
                | Q(description__icontains=search)
                | Q(product__name__icontains=search)
            )
        return queryset.order_by('product__name', 'unit_code', 'id')


class ProductSupplierUnitViewSet(SupplierDomainViewSet):
    queryset = ProductSupplierUnit.objects.all()
    serializer_class = ProductSupplierUnitSerializer
    audit_name = 'product_supplier_unit'
    audit_fields = (
        'company_id', 'product_supplier_id', 'purchase_presentation_id',
        'unit_code', 'description',
        'conversion_factor', 'presentation_preset_id', 'barcode', 'is_default', 'status',
    )
    status_service = staticmethod(_set_product_supplier_unit_status)

    def get_queryset(self):
        queryset = self.scope_company(ProductSupplierUnit.objects.select_related(
            'company', 'product_supplier__product', 'product_supplier__supplier',
            'purchase_presentation',
        ))
        branch = getattr(self.request, 'branch_context', None)
        if branch:
            queryset = queryset.filter(
                product_supplier__product__branch_configs__branch=branch,
                product_supplier__product__branch_configs__is_available=True,
                product_supplier__supplier__branch=branch,
                product_supplier__supplier__deleted_at__isnull=True,
            )
        params = self.request.query_params
        for parameter, lookup in (
            ('product_supplier', 'product_supplier_id'),
            ('product', 'product_supplier__product_id'),
            ('supplier', 'product_supplier__supplier_id'),
        ):
            if params.get(parameter):
                queryset = queryset.filter(**{lookup: params[parameter]})
        unit_status = params.get('status')
        if unit_status:
            if unit_status not in Status.values:
                raise ValidationError({'status': 'Informe um status válido.'})
            queryset = queryset.filter(status=unit_status)
        is_default = params.get('is_default')
        if is_default:
            if is_default not in ('true', 'false'):
                raise ValidationError({'is_default': 'Informe true ou false.'})
            queryset = queryset.filter(is_default=is_default == 'true')
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(unit_code__icontains=search)
                | Q(description__icontains=search)
                | Q(barcode__icontains=search)
                | Q(product_supplier__product__name__icontains=search)
                | Q(product_supplier__supplier__trade_name__icontains=search)
            )
        return queryset.order_by(
            'product_supplier__product__name', '-is_default', 'unit_code', 'id'
        )


class PresentationPresetViewSet(SupplierDomainViewSet):
    queryset = PresentationPreset.objects.all()
    serializer_class = PresentationPresetSerializer
    audit_name = 'presentation_preset'
    audit_fields = (
        'company_id', 'presentation_type', 'conversion_factor', 'code', 'description',
        'custom_code', 'custom_name', 'status',
    )
    status_service = staticmethod(_set_presentation_preset_status)

    def get_queryset(self):
        queryset = self.scope_company(PresentationPreset.objects.select_related('company'))
        status = self.request.query_params.get('status')
        if status:
            if status not in Status.values:
                raise ValidationError({'status': 'Informe um status válido.'})
            queryset = queryset.filter(status=status)
        return queryset.order_by('code', 'description', 'id')
