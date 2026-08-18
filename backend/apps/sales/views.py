from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import DecimalField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.models import User
from apps.base.datetimes import parse_datetime_range
from apps.base.exceptions import InternalContractError
from apps.cash.models import CashSession, CashSessionStatus
from apps.companies.selectors import eligible_branch_users
from apps.companies.models import Status
from apps.products.models import BranchProductPrice, Category, Product

from .models import PaymentMethod, Promotion, Sale
from .permissions import SalesFunctionalPermission
from .serializers import (
    CalculationOutputSerializer, CalculationSerializer, CancelSaleSerializer,
    FinalizeSaleSerializer,
    PaymentMethodSerializer, PromotionSerializer, SaleBeneficiarySerializer, SaleCatalogProductSerializer,
    SaleUserOptionSerializer,
    SaleSerializer, SalesQuerySerializer,
)
from .services import calculate_preview, cancel_sale, finalize_sale, detect_promotion_conflict


class PromotionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PromotionSerializer
    permission_classes = (SalesFunctionalPermission,)
    http_method_names = ('get', 'post', 'put', 'patch', 'head', 'options')
    permission_codes = {
        'list': ('promotions.view', 'promotions.change'),
        'retrieve': ('promotions.view', 'promotions.change'),
        'create': 'promotions.change',
        'update': 'promotions.change',
        'partial_update': 'promotions.change',
        'activate': 'promotions.change',
        'deactivate': 'promotions.change',
        'target_options': ('promotions.view', 'promotions.change'),
    }

    def get_queryset(self):
        queryset = Promotion.objects.filter(
            company_id=self.request.branch_context.company_id
        ).prefetch_related('products', 'categories', 'schedules')
        if self.action != 'list':
            return queryset
        params = self.request.query_params
        item_status = params.get('status')
        if item_status:
            if item_status not in Status.values:
                raise ValidationError({'status': 'Status invalido.'})
            queryset = queryset.filter(status=item_status)
        active_at = params.get('active_at')
        if active_at:
            value = parse_datetime(active_at)
            if value is None:
                raise ValidationError({'active_at': 'Informe uma data e hora ISO valida.'})
            current_timezone = timezone.get_default_timezone()
            value = (
                timezone.make_aware(value, current_timezone)
                if timezone.is_naive(value) else value.astimezone(current_timezone)
            )
            queryset = queryset.filter(
                status=Status.ACTIVE, starts_at__lte=value
            ).filter(
                Q(ends_at__isnull=True) | Q(ends_at__gt=value)
            )
        if params.get('search'):
            search = params['search']
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(products__name__icontains=search)
                | Q(categories__name__icontains=search)
            )
        for parameter, lookup in (
            ('product', 'products__id'), ('category', 'categories__id')
        ):
            if params.get(parameter):
                try:
                    value = int(params[parameter])
                except (TypeError, ValueError):
                    raise ValidationError({parameter: 'Informe um identificador valido.'})
                if value <= 0:
                    raise ValidationError({parameter: 'Informe um identificador valido.'})
                queryset = queryset.filter(**{lookup: value})
        return queryset.distinct()

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def activate(self, request, pk=None):
        promotion = self.get_queryset().select_for_update().get(pk=pk)
        promotion.status = Status.ACTIVE
        promotion.save(update_fields=('status', 'updated_at'))
        conflict = detect_promotion_conflict(promotion)
        if conflict:
            promotion.status = Status.INACTIVE
            promotion.save(update_fields=('status', 'updated_at'))
            raise ValidationError({'targets': conflict})
        return Response(self.get_serializer(promotion).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def deactivate(self, request, pk=None):
        promotion = self.get_queryset().select_for_update().get(pk=pk)
        promotion.status = Status.INACTIVE
        promotion.save(update_fields=('status', 'updated_at'))
        return Response(self.get_serializer(promotion).data)

    @action(detail=False, methods=('get',), url_path='target-options')
    def target_options(self, request):
        company_id = request.branch_context.company_id
        products = Product.objects.filter(company_id=company_id).order_by('name', 'id')
        categories = Category.objects.filter(company_id=company_id).order_by(
            'sort_order', 'name', 'id'
        )
        return Response({
            'products': [
                {
                    'id': product.pk,
                    'name': product.name,
                    'internal_code': product.internal_code,
                    'status': product.status,
                }
                for product in products
            ],
            'categories': [
                {'id': category.pk, 'name': category.name, 'status': category.status}
                for category in categories
            ],
        })


class PaymentMethodViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PaymentMethodSerializer
    permission_classes = (SalesFunctionalPermission,)
    http_method_names = ('get', 'post', 'put', 'patch', 'head', 'options')
    permission_codes = {
        'list': 'payment_methods.view',
        'retrieve': 'payment_methods.view',
        'update': 'payment_methods.change',
        'partial_update': 'payment_methods.change',
        'activate': 'payment_methods.change',
        'deactivate': 'payment_methods.change',
    }

    def get_queryset(self):
        queryset = PaymentMethod.objects.select_related('company').filter(
            company_id=self.request.branch_context.company_id
        )
        if self.action == 'list':
            item_status = self.request.query_params.get('status')
            if item_status != 'all':
                queryset = queryset.filter(status=item_status or 'active')
        return queryset

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def activate(self, request, pk=None):
        method = self.get_queryset().select_for_update().get(pk=pk)
        method.status = 'active'
        method.save(update_fields=('status', 'updated_at'))
        return Response(self.get_serializer(method).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def deactivate(self, request, pk=None):
        method = self.get_queryset().select_for_update().get(pk=pk)
        method.status = 'inactive'
        method.save(update_fields=('status', 'updated_at'))
        return Response(self.get_serializer(method).data)


class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = (SalesFunctionalPermission,)
    permission_codes = {
        'list': 'sales.view', 'retrieve': 'sales.view', 'calculate': 'sales.create',
        'finalize': 'sales.create', 'cancel': 'sales.cancel',
        'beneficiaries': 'sales.create_consumption', 'catalog': 'sales.create',
        'checkout_options': 'sales.create', 'categories': 'sales.create',
        'sellers': 'sales.create', 'discount_authorizers': 'sales.create',
    }

    def get_queryset(self):
        queryset = Sale.objects.select_related(
            'company', 'branch', 'cash_session', 'created_by', 'seller_user',
            'discount_approved_by', 'service_fee_waived_by', 'beneficiary_user', 'cancelled_by'
        ).prefetch_related('items__product', 'payments__payment_method')
        queryset = queryset.filter(branch=self.request.branch_context)
        if self.action == 'list':
            params = self.request.query_params
            query = SalesQuerySerializer(data=params)
            query.is_valid(raise_exception=True)
            operation_type = query.validated_data['operation_type']
            queryset = queryset.filter(operation_type=operation_type)
            if params.get('status'):
                queryset = queryset.filter(status=params['status'])
            if params.get('number'):
                queryset = queryset.filter(sale_number__icontains=params['number'])
            if query.validated_data.get('beneficiary'):
                queryset = queryset.filter(
                    beneficiary_user_id=query.validated_data['beneficiary']
                )
            if params.get('search'):
                search = params['search']
                queryset = queryset.filter(
                    Q(sale_number__icontains=search)
                    | Q(items__product_name__icontains=search)
                    | Q(items__internal_code__icontains=search)
                    | Q(beneficiary_user__first_name__icontains=search)
                    | Q(beneficiary_user__last_name__icontains=search)
                    | Q(beneficiary_user__email__icontains=search)
                ).distinct()
            start_datetime, end_datetime = parse_datetime_range(params)
            if start_datetime:
                queryset = queryset.filter(created_at__gte=start_datetime)
            if end_datetime:
                queryset = queryset.filter(created_at__lte=end_datetime)
        return queryset

    def _paginated_response(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        serializer = serializer_class(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=('get',))
    def beneficiaries(self, request):
        queryset = User.objects.filter(
            is_active=True,
            company_accesses__company_id=request.branch_context.company_id,
            company_accesses__is_active=True,
        ).distinct().order_by('first_name', 'last_name', 'email', 'id')
        return self._paginated_response(queryset, SaleBeneficiarySerializer)

    @action(detail=False, methods=('get',))
    def sellers(self, request):
        return self._paginated_response(
            eligible_branch_users(request.branch_context, 'sales.create'),
            SaleUserOptionSerializer,
        )

    @action(detail=False, methods=('get',), url_path='discount-authorizers')
    def discount_authorizers(self, request):
        return self._paginated_response(
            eligible_branch_users(request.branch_context, 'sales.apply_discount'),
            SaleUserOptionSerializer,
        )

    @action(detail=False, methods=('get',))
    def catalog(self, request):
        query = SalesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        branch_price = BranchProductPrice.objects.filter(
            branch=request.branch_context, product_id=OuterRef('pk')
        ).values('sale_price')[:1]
        queryset = Product.objects.select_related(
            'company', 'category'
        ).prefetch_related('components__component_product').annotate(
            effective_sale_price=Coalesce(
                Subquery(branch_price), 'sale_price', output_field=DecimalField()
            )
        ).filter(
            company_id=request.branch_context.company_id,
            status=Status.ACTIVE,
            is_sellable=True,
        )
        if query.validated_data.get('category'):
            queryset = queryset.filter(category_id=query.validated_data['category'])
        if request.query_params.get('favorites') == 'true':
            queryset = queryset.filter(is_favorite=True)
        if request.query_params.get('search'):
            search = request.query_params['search']
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(internal_code__icontains=search)
                | Q(barcode__icontains=search)
            )
        queryset = queryset.order_by('-is_favorite', 'category__sort_order', 'name', 'id')
        return self._paginated_response(queryset, SaleCatalogProductSerializer)

    @action(detail=False, methods=('get',), url_path='checkout-options')
    def checkout_options(self, request):
        query = SalesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        company_id = request.branch_context.company_id
        methods = PaymentMethod.objects.filter(
            company_id=company_id, status=Status.ACTIVE
        ).order_by('name', 'id').values('id', 'code', 'name', 'status', 'is_system')
        sessions = CashSession.objects.filter(
            branch=request.branch_context, status=CashSessionStatus.OPEN
        ).select_related('cash_register', 'opened_by').order_by('id')
        return Response({
            'payment_methods': list(methods),
            'cash_sessions': [
                {
                    'id': session.pk,
                    'register_name': session.cash_register.name,
                    'opened_by_name': session.opened_by.get_full_name().strip()
                    or session.opened_by.email,
                }
                for session in sessions
            ],
        })

    @action(detail=False, methods=('get',))
    def categories(self, request):
        query = SalesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        rows = Category.objects.filter(
            company_id=request.branch_context.company_id, status=Status.ACTIVE
        ).order_by('sort_order', 'name', 'id').values('id', 'name')
        return Response(list(rows))

    @action(detail=False, methods=('post',), url_path='finalize')
    def finalize(self, request):
        serializer = FinalizeSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = finalize_sale(
            branch=request.branch_context, user=request.user, **serializer.validated_data,
        )
        sale = Sale.objects.select_related(
            'company', 'branch', 'cash_session', 'created_by', 'seller_user',
            'discount_approved_by', 'service_fee_waived_by', 'beneficiary_user', 'cancelled_by'
        ).prefetch_related('items__product', 'payments__payment_method').get(pk=sale.pk)
        return Response(self.get_serializer(sale).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=('post',), url_path='cancel')
    def cancel(self, request, pk=None):
        sale = self.get_object()
        serializer = CancelSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = cancel_sale(
            sale=sale, branch=request.branch_context, user=request.user,
            reason=serializer.validated_data['reason'],
        )
        sale = self.get_queryset().get(pk=sale.pk)
        return Response(self.get_serializer(sale).data)

    @action(detail=False, methods=('post',))
    def calculate(self, request):
        serializer = CalculationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        product_ids = [item.get('product') for item in data['items']]
        if Product.objects.filter(pk__in=product_ids).exclude(
            company=request.branch_context.company
        ).exists():
            raise PermissionDenied('Produto fora da empresa da filial.')
        beneficiary = data.get('beneficiary_user')
        if beneficiary and not beneficiary.company_accesses.filter(
            company=request.branch_context.company, is_active=True
        ).exists():
            raise PermissionDenied('Beneficiario fora da empresa da filial.')
        try:
            result = calculate_preview(
                company=request.branch_context.company,
                operation_type=data['operation_type'],
                raw_items=data['items'],
                discount=data.get('discount'),
                charged_amount=data.get('charged_amount'),
                beneficiary_user=beneficiary,
                branch=request.branch_context,
                service_fee_waived=data.get('service_fee_waived', False),
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages}
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)
        output = CalculationOutputSerializer(data=result)
        if not output.is_valid():
            raise InternalContractError()
        return Response(output.data)
