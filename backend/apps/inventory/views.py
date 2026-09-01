from decimal import ROUND_HALF_UP, Decimal

import mimetypes

from django.core.exceptions import ObjectDoesNotExist
from django.http import FileResponse
from django.db.models import (
    Case, CharField, Count, DecimalField, ExpressionWrapper, F, IntegerField,
    OuterRef, Prefetch, Q, Subquery, Value, When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.base.datetimes import (
    filter_datetime_range,
    inclusive_end_exclusive,
    parse_datetime_range,
)
from apps.base.exceptions import DomainValidationError
from apps.base.audit import audit_log
from apps.base.report_exports import render_report_export, report_key_value_rows
from apps.companies.models import Branch, BranchSettings, Status
from apps.companies.selectors import accessible_branches, user_has_branch_permission, user_has_company_permission
from apps.products.models import Category, Product, ProductBranchConfig
from apps.purchases.models import PurchaseReceipt

from .content import content_breakdown, exact_multiply, exact_sum
from .models import (
    InventoryCount,
    InventoryCountItem,
    InventoryCountStatus,
    InventoryOperation,
    LossRecord,
    MovementDomainOrigin,
    Stock,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    StockTransferReceipt,
    StockTransferReceiptItem,
    StockTransferStatus,
    TransferDivergence,
    TransferDivergenceStatus,
    TransferDivergenceResolution,
    TransferResolutionType,
)
from .permissions import InventoryFunctionalPermission
from .selectors import active_transfer_destinations, eligible_inventory_products, eligible_workflow_stocks
from .serializers import (
    AdjustmentRequestSerializer,
    AdvancedInventoryReportQuerySerializer,
    GroupEntrySerializer,
    IdempotencySerializer,
    InventoryCountCreateSerializer,
    InventoryCountSerializer,
    InventoryQuerySerializer,
    LossRecordCreateSerializer,
    LossRecordSerializer,
    MinimumQuantitySerializer,
    MovementRequestSerializer,
    ReasonSerializer,
    RegularizeNegativesSerializer,
    StockTransferCreateSerializer,
    StockTransferReceiptCreateSerializer,
    StockTransferSerializer,
    StockMovementQuerySerializer,
    StockMovementSerializer,
    StockSerializer,
    TransferDivergenceSerializer,
    TransferReceiptSerializer,
    TransferResolutionCreateSerializer,
    TransferResolutionSerializer,
    _can_view_costs,
)
from .storage import loss_attachment_download_name
from .services import adjustment as adjust_stock
from .services import entry as enter_stock
from .services import exit as exit_stock
from .services import set_minimum
from .services import (
    cancel_stock_transfer,
    confirm_inventory_count,
    create_inventory_count,
    create_stock_transfer,
    dispatch_stock_transfer,
    group_entry,
    receive_stock_transfer,
    record_loss,
    regularize_negatives,
    resolve_transfer_divergence,
    write_off_archived_stock,
)


def _with_operation_count(queryset):
    counts = StockMovement.objects.filter(
        operation_reference=OuterRef('operation_reference'),
        stock__branch_id=OuterRef('stock__branch_id'),
    ).order_by().values('operation_reference').annotate(
        total=Count('pk')
    ).values('total')
    kinds = InventoryOperation.objects.filter(
        branch_id=OuterRef('stock__branch_id'),
        idempotency_key=OuterRef('operation_reference'),
    ).values('kind')
    return queryset.annotate(
        operation_count=Subquery(counts[:1], output_field=IntegerField()),
        operation_kind=Subquery(kinds[:1], output_field=CharField()),
    )


def _scoped_inventory_branches(request, code):
    support = getattr(request, 'support_session', None)
    codes = code if isinstance(code, tuple) else (code,)
    branch_scope = Q()
    for permission_code in codes:
        branch_scope |= Q(pk__in=accessible_branches(request.user, permission_code))
    branches = Branch.objects.filter(branch_scope)
    if support:
        branches = Branch.objects.filter(company_id=support.company_id)
    current = getattr(request, 'branch_context', None)
    if current:
        branches = branches.filter(pk=current.pk)
    return branches


def _workflow_stock_options(request, branch, *, exclude_open_counts=False):
    show_costs = _can_view_costs(request, branch.pk)
    results = []
    for stock in eligible_workflow_stocks(
        branch, exclude_open_counts=exclude_open_counts
    ):
        item = {
            'stock': stock.pk,
            'product': stock.product_id,
            'product_name': stock.product.name,
            'internal_code': stock.product.internal_code,
            'unit': stock.product.unit,
            'current_quantity': format(stock.current_quantity, 'f'),
            'equivalent_quantity': format(stock.equivalent_quantity(), 'f'),
        }
        try:
            config = stock.product.fraction_config
        except ObjectDoesNotExist:
            config = None
        if config and config.tracking_active and stock.current_content is not None:
            complete, residual = content_breakdown(
                stock.current_content, config.package_content
            )
            item.update({
                'current_content': format(stock.current_content, 'f'),
                'package_content': format(config.package_content, 'f'),
                'content_unit': config.content_unit,
                'complete_packages': format(complete, 'f'),
                'residual_content': format(residual, 'f'),
            })
        if show_costs:
            item['unit_cost'] = format(
                stock.average_unit_cost
                if stock.average_unit_cost is not None else stock.product.cost,
                '.12f',
            )
        results.append(item)
    return results


class StockViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockSerializer
    permission_classes = (InventoryFunctionalPermission,)
    permission_codes = {
        'list': 'inventory.view',
        'retrieve': 'inventory.view',
        'minimum': 'inventory.change_minimum',
        'summary': 'inventory.view',
        'options': 'inventory.view',
        'write_off_residual': 'inventory.adjust',
        'regularize_negatives': 'inventory.regularize',
    }

    def _filtered_queryset(self, queryset):
        params = self.request.query_params
        query = InventoryQuerySerializer(data=params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        if filters.get('company'):
            queryset = queryset.filter(branch__company_id=filters['company'])
        if filters.get('branch'):
            queryset = queryset.filter(branch_id=filters['branch'])
        if filters.get('category'):
            queryset = queryset.filter(
                product__branch_configs__branch=F('branch_id'),
                product__branch_configs__category_id=filters['category'],
            )
        if params.get('status'):
            queryset = queryset.filter(product__status=params['status'])
        if params.get('inventory_behavior'):
            queryset = queryset.filter(
                product__inventory_behavior=params['inventory_behavior']
            )
        if params.get('search'):
            queryset = queryset.filter(
                Q(product__name__icontains=params['search'])
                | Q(product__internal_code__icontains=params['search'])
            )
        state = params.get('state')
        fraction_threshold = (
            F('minimum_quantity') * F('product__fraction_config__package_content')
        )
        if state == 'negative':
            queryset = queryset.filter(
                Q(current_content__lt=0)
                | Q(current_content__isnull=True, current_quantity__lt=0)
            )
        elif state == 'zero':
            queryset = queryset.filter(
                Q(current_content=0)
                | Q(current_content__isnull=True, current_quantity=0)
            )
        elif state == 'below_minimum':
            queryset = queryset.filter(
                Q(
                    current_content__gt=0,
                    current_content__lt=fraction_threshold,
                )
                | Q(
                    current_content__isnull=True,
                    current_quantity__gt=0,
                    current_quantity__lt=F('minimum_quantity'),
                )
            )
        elif state == 'normal':
            queryset = queryset.filter(
                Q(
                    current_content__gt=0,
                    current_content__gte=fraction_threshold,
                )
                | Q(
                    current_content__isnull=True,
                    current_quantity__gt=0,
                    current_quantity__gte=F('minimum_quantity'),
                )
            )
        return queryset

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'inventory.view')
        branches = _scoped_inventory_branches(self.request, code)
        queryset = Stock.objects.select_related(
            'product', 'product__fraction_config',
            'branch', 'branch__company'
        ).prefetch_related(Prefetch(
            'product__branch_configs',
            queryset=ProductBranchConfig.objects.select_related('category'),
            to_attr='_inventory_branch_configs',
        )).filter(
            branch__in=branches,
            product__inventory_behavior='direct',
            product__branch_configs__branch=F('branch_id'),
            product__branch_configs__is_available=True,
        ).filter(
            Q(product__archived_at__isnull=True, product__status=Status.ACTIVE)
            | Q(product__archived_at__isnull=False) & (
                Q(current_content__isnull=False) & ~Q(current_content=0)
                | Q(current_content__isnull=True) & ~Q(current_quantity=0)
            )
        ).distinct()
        queryset = self._filtered_queryset(queryset)
        ordering = self.request.query_params.get('ordering', 'product')
        descending = ordering.startswith('-')
        ordering = ordering.removeprefix('-')
        fields = {
            'product': 'product__name',
            'category': 'product__branch_configs__category__name',
            'balance': 'current_quantity',
            'average_unit_cost': 'average_unit_cost',
            'last_unit_cost': 'last_unit_cost',
            'total_cost': 'total_cost_sort',
        }
        if ordering not in fields:
            raise ValidationError({
                'ordering': 'Informe product, category, balance, average_unit_cost, last_unit_cost ou total_cost.'
            })
        if ordering == 'total_cost':
            cost_field = DecimalField(max_digits=28, decimal_places=12)
            queryset = queryset.annotate(
                total_cost_sort=Case(
                    When(
                        current_quantity__gt=0,
                        then=ExpressionWrapper(
                            F('current_quantity') * Coalesce(
                                F('average_unit_cost'), F('product__cost')
                            ),
                            output_field=cost_field,
                        ),
                    ),
                    default=Value(0, output_field=cost_field),
                    output_field=cost_field,
                )
            )
        order_field = fields[ordering]
        if ordering in ('average_unit_cost', 'last_unit_cost'):
            ordering_expression = (
                F(order_field).desc(nulls_last=True)
                if descending else F(order_field).asc(nulls_last=True)
            )
            return queryset.order_by(ordering_expression, 'pk')
        return queryset.order_by(f'-{order_field}' if descending else order_field, 'pk')

    @action(detail=False, methods=('get',))
    def summary(self, request):
        queryset = self.get_queryset().filter(
            product__archived_at__isnull=True,
            product__status=Status.ACTIVE,
        )
        branch = getattr(request, 'branch_context', None)
        branch_id = branch.pk if branch else None
        can_view_kpis = request.user.is_superuser or user_has_branch_permission(
            request.user, branch_id, 'inventory.view_stock_kpis'
        )
        can_view_costs = request.user.is_superuser or user_has_branch_permission(
            request.user, branch_id, 'inventory.view_stock_costs'
        )
        can_regularize = request.user.is_superuser or user_has_branch_permission(
            request.user, branch_id, 'inventory.regularize'
        )
        summary_stocks = list(queryset) if (
            can_view_kpis or can_regularize or can_view_costs
        ) else []
        summary_quantities = [
            stock.equivalent_quantity() for stock in summary_stocks
        ]
        result = {'allow_negative_stock': False, 'legacy_negative_state': False}
        if branch:
            result['allow_negative_stock'] = BranchSettings.objects.filter(
                branch=branch, allow_negative_stock=True
            ).exists()
        if can_view_kpis or can_regularize:
            result['negative_count'] = sum(
                quantity < 0 for quantity in summary_quantities
            )
            result['legacy_negative_state'] = bool(
                result['negative_count'] and not result['allow_negative_stock']
            )
        if can_view_kpis:
            result.update({
                'below_minimum_count': sum(
                    quantity > 0 and quantity < stock.minimum_quantity
                    for stock, quantity in zip(summary_stocks, summary_quantities)
                ),
                'zero_count': sum(quantity == 0 for quantity in summary_quantities),
                'physical_products': len(summary_stocks),
            })
        if can_view_costs:
            estimated_value = exact_sum(
                exact_multiply(
                    max(stock.equivalent_quantity(), Decimal('0')),
                    stock.average_unit_cost
                    if stock.average_unit_cost is not None else stock.product.cost,
                )
                for stock in summary_stocks
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            result['estimated_value'] = f'{estimated_value:.2f}'
        return Response(result)

    @action(detail=False, methods=('get',))
    def options(self, request):
        branch = getattr(request, 'branch_context', None)
        if branch is None:
            raise PermissionDenied('Selecione a filial ativa.')
        categories = Category.objects.filter(
            branch=branch, status=Status.ACTIVE, deleted_at__isnull=True,
            branch_product_configs__in=ProductBranchConfig.objects.filter(
                product__in=eligible_inventory_products(branch), branch=branch,
                is_available=True,
            ),
        ).distinct().order_by('sort_order', 'name')
        return Response({'categories': [
            {'id': item.pk, 'name': item.name} for item in categories
        ]})

    @action(detail=True, methods=('post',), url_path='write-off-residual')
    def write_off_residual(self, request, pk=None):
        reason = str(request.data.get('reason') or '').strip()
        movement = write_off_archived_stock(
            stock=self.get_object(), user=request.user, reason=reason,
        )
        movement = _with_operation_count(StockMovement.objects.select_related(
            'stock__product', 'stock__branch', 'stock__branch__company', 'user', 'sale',
        )).get(pk=movement.pk)
        return Response(StockMovementSerializer(movement, context={'request': request}).data)

    @action(detail=False, methods=('post',), url_path='regularize-negatives')
    def regularize_negatives(self, request):
        serializer = RegularizeNegativesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        current = getattr(request, 'branch_context', None)
        if current is None or current.pk != data['branch']:
            raise PermissionDenied('Filial fora do contexto autorizado.')
        movements = regularize_negatives(
            branch=data['branch'], items=data['items'], reason=data['reason'],
            user=request.user,
        )
        queryset = _with_operation_count(StockMovement.objects.select_related(
            'stock__product', 'stock__branch', 'stock__branch__company', 'user', 'sale'
        ).filter(pk__in=[item.pk for item in movements]))
        results = StockMovementSerializer(queryset, many=True).data
        return Response({
            'operation_reference': str(movements[0].operation_reference),
            'count': len(movements),
            'operation_label': results[0]['operation_label'],
            'operation_count': results[0]['operation_count'],
            'results': results,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=('patch',))
    def minimum(self, request, pk=None):
        stock = self.get_object()
        serializer = MinimumQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stock = set_minimum(
            stock=stock,
            minimum_quantity=serializer.validated_data['minimum_quantity'],
            user=request.user,
        )
        return Response(self.get_serializer(stock).data)


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = (InventoryFunctionalPermission,)
    permission_codes = {
        'list': 'inventory.view_history',
        'retrieve': 'inventory.view_history',
        'entry': 'inventory.entry',
        'group_entry': 'inventory.entry',
        'exit': 'inventory.exit',
        'adjustment': 'inventory.adjust',
        'entry_options': 'inventory.entry',
        'exit_options': 'inventory.exit',
        'adjustment_options': 'inventory.adjust',
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'inventory.view_history')
        branches = _scoped_inventory_branches(self.request, code)
        queryset = _with_operation_count(StockMovement.objects.select_related(
            'stock', 'stock__product', 'stock__branch', 'stock__branch__company',
            'user', 'sale', 'order_item__order__command',
            'transfer_item__transfer',
            'transfer_resolution__divergence__transfer_item__transfer',
            'loss_record', 'inventory_count_item__inventory_count',
        ).filter(stock__branch__in=branches))
        purchase_receipt = PurchaseReceipt.objects.filter(
            pk=OuterRef('operation_reference')
        )
        queryset = queryset.annotate(
            purchase_order_id=Subquery(
                purchase_receipt.values('purchase_order_id')[:1],
                output_field=IntegerField(),
            ),
            purchase_order_number=Subquery(
                purchase_receipt.values('purchase_order__order_number')[:1],
                output_field=CharField(),
            ),
        )
        params = self.request.query_params
        query = StockMovementQuerySerializer(data=params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        if filters.get('company'):
            queryset = queryset.filter(stock__branch__company_id=filters['company'])
        if filters.get('branch'):
            queryset = queryset.filter(stock__branch_id=filters['branch'])
        if filters.get('category'):
            queryset = queryset.filter(
                stock__product__branch_configs__branch_id=F('stock__branch_id'),
                stock__product__branch_configs__category_id=filters['category'],
            )
        if filters.get('product'):
            queryset = queryset.filter(stock__product_id=filters['product'])
        movement_type = params.get('movement_type') or params.get('type')
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        if params.get('nature'):
            queryset = queryset.filter(nature=params['nature'])
        if filters.get('operation_reference'):
            queryset = queryset.filter(operation_reference=filters['operation_reference'])
        if filters.get('domain_origin'):
            queryset = queryset.filter(domain_origin=filters['domain_origin'])
        if params.get('search'):
            search = params['search']
            queryset = queryset.filter(
                Q(stock__product__name__icontains=search)
                | Q(stock__product__internal_code__icontains=search)
                | Q(reason__icontains=search)
            )
        start_datetime, end_datetime = parse_datetime_range(params)
        return filter_datetime_range(
            queryset, 'created_at', start_datetime, end_datetime
        )

    def _perform_movement(self, request, service, serializer_class):
        branch_id = request.data.get('branch')
        current = getattr(request, 'branch_context', None)
        if current and str(branch_id) != str(current.pk):
            raise PermissionDenied('Filial fora do contexto autorizado.')
        permission_code = self.permission_codes.get(self.action)
        if not request.user.is_superuser and not user_has_branch_permission(
            request.user, branch_id, permission_code
        ):
            raise PermissionDenied('Filial fora do contexto autorizado.')
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement = service(user=request.user, **serializer.validated_data)
        replayed = bool(getattr(movement, '_idempotency_replayed', False))
        movement = self.get_queryset().get(pk=movement.pk)
        request.audit_fallback_suppressed = replayed
        return Response(
            self.get_serializer(movement).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=('post',))
    def entry(self, request):
        return self._perform_movement(request, enter_stock, MovementRequestSerializer)

    @action(detail=False, methods=('post',))
    def exit(self, request):
        return self._perform_movement(request, exit_stock, MovementRequestSerializer)

    @action(detail=False, methods=('post',))
    def adjustment(self, request):
        return self._perform_movement(
            request, adjust_stock, AdjustmentRequestSerializer
        )

    @action(detail=False, methods=('post',), url_path='group-entry')
    def group_entry(self, request):
        current = getattr(request, 'branch_context', None)
        if current is None or current.status != Status.ACTIVE or current.company.status != Status.ACTIVE:
            raise DomainValidationError(
                code='active_branch_context_required',
                message='Selecione uma filial ativa para registrar a entrada.',
            )
        serializer = GroupEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if current.pk != data['branch']:
            raise PermissionDenied('Filial fora do contexto autorizado.')
        movements = group_entry(
            branch=data['branch'], category=data.get('category'), items=data['items'],
            nature=data['nature'],
            reason=data['reason'], user=request.user,
            operation_reference=data['idempotency_key'],
        )
        queryset = self.get_queryset().filter(pk__in=[item.pk for item in movements])
        results = self.get_serializer(queryset, many=True).data
        replayed = bool(getattr(movements[0], '_idempotency_replayed', False))
        request.audit_fallback_suppressed = replayed
        return Response({
            'operation_reference': str(movements[0].operation_reference),
            'count': len(movements),
            'operation_label': results[0]['operation_label'],
            'operation_count': results[0]['operation_count'],
            'idempotency_replayed': replayed,
            'results': results,
        }, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)

    def _movement_options(self, request):
        branch = getattr(request, 'branch_context', None)
        if (
            branch is None
            or branch.status != Status.ACTIVE
            or branch.company.status != Status.ACTIVE
        ):
            raise DomainValidationError(
                code='active_branch_context_required',
                message='Selecione uma filial ativa para carregar as opcoes de entrada.',
            )
        categories = Category.objects.filter(
            branch=branch, status=Status.ACTIVE, deleted_at__isnull=True,
            branch_product_configs__product__status=Status.ACTIVE,
            branch_product_configs__product__archived_at__isnull=True,
            branch_product_configs__product__inventory_behavior='direct',
            branch_product_configs__is_available=True,
        ).distinct().order_by('sort_order', 'name', 'id')
        category_id = request.query_params.get('category')
        search = (request.query_params.get('search') or '').strip()
        products = Product.objects.none()
        if category_id:
            try:
                category = categories.get(pk=category_id)
            except (Category.DoesNotExist, TypeError, ValueError) as error:
                raise DomainValidationError(
                    code='invalid_inventory_entry_category',
                    message='A categoria nao possui produtos fisicos elegiveis nesta filial.',
                    details={'category_id': category_id},
                ) from error
            products = Product.objects.filter(
                company_id=branch.company_id, branch_configs__branch=branch,
                branch_configs__category=category, branch_configs__is_available=True,
                inventory_behavior='direct', status=Status.ACTIVE, archived_at__isnull=True,
            ).select_related('fraction_config').order_by('name', 'id')
        elif request.query_params.get('all') == 'true':
            products = Product.objects.filter(
                company_id=branch.company_id, branch_configs__branch=branch,
                branch_configs__is_available=True, inventory_behavior='direct', status=Status.ACTIVE,
                archived_at__isnull=True,
            ).select_related('fraction_config').order_by('name', 'id')
        elif search:
            products = Product.objects.filter(
                company_id=branch.company_id, branch_configs__branch=branch,
                branch_configs__is_available=True, inventory_behavior='direct', status=Status.ACTIVE,
                archived_at__isnull=True,
            ).filter(
                Q(name__icontains=search)
                | Q(internal_code__icontains=search)
                | Q(barcode__icontains=search)
                | Q(sku__icontains=search)
            ).select_related('fraction_config').order_by('name', 'id')[:50]
        configs = {
            config.product_id: config
            for config in ProductBranchConfig.objects.filter(
                branch=branch, product__in=products, is_available=True,
            ).select_related('category')
        }
        balances = dict(Stock.objects.filter(
            branch=branch, product__in=products
        ).values_list('product_id', 'current_quantity'))
        return Response({
            'branch': {'id': branch.pk, 'name': branch.name},
            'categories': [{'id': item.pk, 'name': item.name} for item in categories],
            'products': [{
                'id': product.pk,
                'name': product.name,
                'internal_code': product.internal_code,
                'barcode': product.barcode,
                'sku': product.sku,
                'category_id': configs[product.pk].category_id,
                'category_name': configs[product.pk].category.name if configs[product.pk].category_id else '',
                'unit': product.unit,
                'current_quantity': str(balances.get(product.pk, 0)),
                'fraction_config': (
                    {
                        'tracking_active': product.fraction_config.tracking_active,
                        'package_content': str(product.fraction_config.package_content),
                        'content_unit': product.fraction_config.content_unit,
                    }
                    if hasattr(product, 'fraction_config') and product.fraction_config.tracking_active
                    else None
                ),
            } for product in products],
        })

    @action(detail=False, methods=('get',), url_path='entry-options')
    def entry_options(self, request):
        return self._movement_options(request)

    @action(detail=False, methods=('get',), url_path='exit-options')
    def exit_options(self, request):
        return self._movement_options(request)

    @action(detail=False, methods=('get',), url_path='adjustment-options')
    def adjustment_options(self, request):
        return self._movement_options(request)


class StockTransferViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockTransferSerializer
    permission_classes = (InventoryFunctionalPermission,)
    http_method_names = ('get', 'post', 'head', 'options')
    permission_codes = {
        'list': (
            'inventory.transfer.view',
            'inventory.transfer.create',
            'inventory.transfer.dispatch',
            'inventory.transfer.receive',
        ),
        'retrieve': (
            'inventory.transfer.view',
            'inventory.transfer.create',
            'inventory.transfer.dispatch',
            'inventory.transfer.receive',
        ),
        'destroy': 'inventory.transfer.view',
        'create': 'inventory.transfer.create',
        'dispatch_transfer': 'inventory.transfer.dispatch',
        'receive': 'inventory.transfer.receive',
        'cancel': 'inventory.transfer.create',
        'workflow_options': 'inventory.transfer.create',
        'receive_options': 'inventory.transfer.receive',
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'inventory.transfer.view')
        current = getattr(self.request, 'branch_context', None)
        support = getattr(self.request, 'support_session', None)
        if self.action in ('list', 'retrieve') and current and not support:
            scope = Q(pk__in=[])
            user = self.request.user
            if user.is_superuser or user_has_branch_permission(
                user, current.pk, 'inventory.transfer.view'
            ):
                scope |= Q(origin_branch=current) | Q(destination_branch=current)
            if user.is_superuser or user_has_branch_permission(
                user, current.pk, 'inventory.transfer.create'
            ):
                scope |= Q(
                    origin_branch=current,
                    status=StockTransferStatus.DRAFT,
                    created_by=user,
                )
            if user.is_superuser or user_has_branch_permission(
                user, current.pk, 'inventory.transfer.dispatch'
            ):
                scope |= Q(origin_branch=current, status=StockTransferStatus.DRAFT)
            if user.is_superuser or user_has_branch_permission(
                user, current.pk, 'inventory.transfer.receive'
            ):
                scope |= Q(
                    destination_branch=current,
                    status__in=(
                        StockTransferStatus.IN_TRANSIT,
                        StockTransferStatus.PARTIALLY_RECEIVED,
                    ),
                )
        elif self.action == 'cancel':
            branches = _scoped_inventory_branches(self.request, code)
            scope = Q(origin_branch__in=branches)
            if current and not support and not self.request.user.is_superuser:
                can_manage_other_drafts = (
                    user_has_branch_permission(
                        self.request.user, current.pk, 'inventory.transfer.view'
                    )
                    or user_has_branch_permission(
                        self.request.user, current.pk, 'inventory.transfer.dispatch'
                    )
                )
                if not can_manage_other_drafts:
                    scope &= Q(
                        origin_branch=current,
                        status=StockTransferStatus.DRAFT,
                        created_by=self.request.user,
                    )
        elif self.action in ('dispatch_transfer', 'create'):
            branches = _scoped_inventory_branches(self.request, code)
            scope = Q(origin_branch__in=branches)
        elif self.action in ('receive', 'receive_options'):
            branches = _scoped_inventory_branches(self.request, code)
            scope = Q(destination_branch__in=branches)
        else:
            branches = _scoped_inventory_branches(self.request, code)
            scope = Q(origin_branch__in=branches) | Q(destination_branch__in=branches)
        queryset = StockTransfer.objects.select_related(
            'company', 'origin_branch', 'destination_branch', 'created_by',
            'dispatched_by', 'cancelled_by',
        ).prefetch_related(
            'items__product', 'items__receipt_items', 'items__stock_movements',
            'items__divergence__resolutions',
            'receipts__items', 'receipts__received_by',
        ).filter(scope).distinct()
        params = self.request.query_params
        if params.get('status'):
            queryset = queryset.filter(status=params['status'])
        if params.get('product'):
            queryset = queryset.filter(items__product_id=params['product'])
        if params.get('responsible'):
            responsible = params['responsible']
            queryset = queryset.filter(
                Q(created_by_id=responsible) | Q(dispatched_by_id=responsible)
                | Q(receipts__received_by_id=responsible)
            )
        start, end = parse_datetime_range(params)
        return filter_datetime_range(queryset, 'created_at', start, end).distinct()

    def create(self, request, *args, **kwargs):
        serializer = StockTransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = getattr(request, 'branch_context', None)
        if current is None or current.pk != serializer.validated_data['origin_branch']:
            raise PermissionDenied('A filial de contexto deve ser a origem da transferencia.')
        transfer = create_stock_transfer(
            user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(
            self.get_serializer(transfer).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=('get',), url_path='options', url_name='options')
    def workflow_options(self, request):
        origin = getattr(request, 'branch_context', None)
        if (
            origin is None
            or origin.status != Status.ACTIVE
            or origin.company.status != Status.ACTIVE
        ):
            raise PermissionDenied('Selecione uma filial de origem ativa.')
        return Response({
            'origin_branch': {'id': origin.pk, 'name': origin.name},
            'destination_branches': [
                {'id': branch.pk, 'name': branch.name}
                for branch in active_transfer_destinations(origin)
            ],
            'stocks': _workflow_stock_options(request, origin),
        })

    @action(detail=True, methods=('post',), url_path='dispatch', url_name='dispatch')
    def dispatch_transfer(self, request, pk=None):
        serializer = IdempotencySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transfer = dispatch_stock_transfer(
            transfer=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        replayed = bool(getattr(transfer, '_idempotency_replayed', False))
        request.audit_fallback_suppressed = replayed
        data = self.get_serializer(transfer).data
        data['idempotency_replayed'] = replayed
        return Response(data)

    @action(detail=True, methods=('get',), url_path='receive-options')
    def receive_options(self, request, pk=None):
        transfer = self.get_object()
        if (
            transfer.destination_branch.status != Status.ACTIVE
            or transfer.company.status != Status.ACTIVE
        ):
            raise PermissionDenied('A empresa e a filial de destino devem estar ativas.')
        if transfer.status not in (
            StockTransferStatus.IN_TRANSIT, StockTransferStatus.PARTIALLY_RECEIVED,
        ):
            raise DomainValidationError(
                code='transfer_not_receivable',
                message='A transferencia nao esta disponivel para recebimento.',
            )
        items = []
        for item in transfer.items.all():
            received = sum(
                (row.received_quantity for row in item.receipt_items.all()), Decimal('0')
            )
            items.append({
                'transfer_item': item.pk,
                'product': item.product_id,
                'product_name': item.product_name_snapshot,
                'internal_code': item.product_internal_code_snapshot,
                'unit': item.product_unit_snapshot,
                'dispatched_quantity': format(item.dispatched_quantity, 'f'),
                'received_quantity': format(received, 'f'),
                'pending_quantity': format(item.dispatched_quantity - received, 'f'),
            })
        return Response({
            'transfer': str(transfer.pk),
            'origin_branch': transfer.origin_branch_id,
            'destination_branch': transfer.destination_branch_id,
            'items': items,
        })

    @action(detail=True, methods=('post',))
    def receive(self, request, pk=None):
        serializer = StockTransferReceiptCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = receive_stock_transfer(
            transfer=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        replayed = bool(getattr(receipt, '_idempotency_replayed', False))
        request.audit_fallback_suppressed = replayed
        return Response(
            TransferReceiptSerializer(receipt, context={'request': request}).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=('post',))
    def cancel(self, request, pk=None):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transfer = cancel_stock_transfer(
            transfer=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(self.get_serializer(transfer).data)


class TransferDivergenceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TransferDivergenceSerializer
    permission_classes = (InventoryFunctionalPermission,)
    permission_codes = {
        'list': ('inventory.transfer.view', 'inventory.transfer.resolve'),
        'retrieve': ('inventory.transfer.view', 'inventory.transfer.resolve'),
        'destroy': 'inventory.transfer.view',
        'resolve': 'inventory.transfer.resolve',
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'inventory.transfer.view')
        current = getattr(self.request, 'branch_context', None)
        support = getattr(self.request, 'support_session', None)
        if self.action in ('list', 'retrieve') and current and not support:
            scope = Q(pk__in=[])
            user = self.request.user
            if user.is_superuser or user_has_branch_permission(
                user, current.pk, 'inventory.transfer.view'
            ):
                scope |= (
                    Q(transfer_item__transfer__origin_branch=current)
                    | Q(transfer_item__transfer__destination_branch=current)
                )
            if user.is_superuser or user_has_branch_permission(
                user, current.pk, 'inventory.transfer.resolve'
            ):
                scope |= (
                    Q(status=TransferDivergenceStatus.PENDING)
                    & (
                        Q(transfer_item__transfer__origin_branch=current)
                        | Q(transfer_item__transfer__destination_branch=current)
                    )
                )
        else:
            branches = _scoped_inventory_branches(self.request, code)
            scope = (
                Q(transfer_item__transfer__origin_branch__in=branches)
                | Q(transfer_item__transfer__destination_branch__in=branches)
            )
        queryset = TransferDivergence.objects.select_related(
            'detected_by', 'transfer_item__product', 'transfer_item__transfer__company',
            'transfer_item__transfer__origin_branch',
            'transfer_item__transfer__destination_branch',
        ).prefetch_related(
            'resolutions__resolved_by', 'resolutions__stock_movements'
        ).filter(scope)
        params = self.request.query_params
        if params.get('status'):
            queryset = queryset.filter(status=params['status'])
        if params.get('product'):
            queryset = queryset.filter(transfer_item__product_id=params['product'])
        if params.get('transfer'):
            queryset = queryset.filter(transfer_item__transfer_id=params['transfer'])
        if params.get('responsible'):
            responsible = params['responsible']
            queryset = queryset.filter(
                Q(detected_by_id=responsible) | Q(resolutions__resolved_by_id=responsible)
            )
        start, end = parse_datetime_range(params)
        return filter_datetime_range(queryset, 'detected_at', start, end).distinct()

    @action(detail=True, methods=('post',))
    def resolve(self, request, pk=None):
        serializer = TransferResolutionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        divergence = self.get_object()
        transfer = divergence.transfer_item.transfer
        expected_branch = (
            transfer.destination_branch_id
            if serializer.validated_data['resolution_type'] == TransferResolutionType.FOUND_RECEIPT
            else transfer.origin_branch_id
        )
        current = getattr(request, 'branch_context', None)
        if current is None or current.pk != expected_branch:
            raise PermissionDenied('A filial de contexto nao corresponde a resolucao fisica.')
        resolution = resolve_transfer_divergence(
            divergence=divergence, user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        replayed = bool(getattr(resolution, '_idempotency_replayed', False))
        request.audit_fallback_suppressed = replayed
        return Response(
            TransferResolutionSerializer(resolution).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )


class LossRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LossRecordSerializer
    permission_classes = (InventoryFunctionalPermission,)
    http_method_names = ('get', 'post', 'head', 'options')
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    permission_codes = {
        'list': 'inventory.report.view',
        'retrieve': 'inventory.report.view',
        'destroy': 'inventory.report.view',
        'create': 'inventory.loss.record',
        'workflow_options': 'inventory.loss.record',
        'attachment': 'inventory.report.view',
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'inventory.report.view')
        branches = _scoped_inventory_branches(self.request, code)
        queryset = LossRecord.objects.select_related(
            'company', 'branch', 'product', 'recorded_by'
        ).prefetch_related('stock_movements').filter(branch__in=branches)
        params = self.request.query_params
        if params.get('product'):
            queryset = queryset.filter(product_id=params['product'])
        if params.get('reason'):
            queryset = queryset.filter(reason=params['reason'])
        if params.get('responsible'):
            queryset = queryset.filter(recorded_by_id=params['responsible'])
        start, end = parse_datetime_range(params)
        return filter_datetime_range(queryset, 'recorded_at', start, end)

    def create(self, request, *args, **kwargs):
        serializer = LossRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = getattr(request, 'branch_context', None)
        if current is None or current.pk != serializer.validated_data['branch']:
            raise PermissionDenied('A filial de contexto deve ser a filial da perda.')
        loss = record_loss(
            user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        replayed = bool(getattr(loss, '_idempotency_replayed', False))
        request.audit_fallback_suppressed = replayed
        return Response(
            self.get_serializer(loss).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=('get',), url_path='options', url_name='options')
    def workflow_options(self, request):
        branch = getattr(request, 'branch_context', None)
        if (
            branch is None
            or branch.status != Status.ACTIVE
            or branch.company.status != Status.ACTIVE
        ):
            raise PermissionDenied('Selecione uma filial ativa para registrar a perda.')
        return Response({
            'branch': {'id': branch.pk, 'name': branch.name},
            'stocks': _workflow_stock_options(request, branch),
        })

    @action(detail=True, methods=('get',))
    def attachment(self, request, pk=None):
        loss = self.get_object()
        if not loss.attachment or not loss.attachment.storage.exists(loss.attachment.name):
            raise NotFound('Foto nao encontrada.')
        filename = loss_attachment_download_name(loss.attachment)
        return FileResponse(
            loss.attachment.open('rb'),
            as_attachment=True,
            filename=filename,
            content_type=mimetypes.guess_type(filename)[0] or 'application/octet-stream',
        )


class InventoryCountViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InventoryCountSerializer
    permission_classes = (InventoryFunctionalPermission,)
    http_method_names = ('get', 'post', 'head', 'options')
    permission_codes = {
        'list': 'inventory.report.view',
        'retrieve': 'inventory.report.view',
        'destroy': 'inventory.report.view',
        'create': 'inventory.count.perform',
        'confirm': 'inventory.count.perform',
        'workflow_options': 'inventory.count.perform',
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'inventory.report.view')
        branches = _scoped_inventory_branches(self.request, code)
        queryset = InventoryCount.objects.select_related(
            'company', 'branch', 'created_by', 'confirmed_by'
        ).prefetch_related(
            'items__product', 'items__counted_by', 'items__stock_movements'
        ).filter(branch__in=branches)
        params = self.request.query_params
        if params.get('status'):
            queryset = queryset.filter(status=params['status'])
        if params.get('product'):
            queryset = queryset.filter(items__product_id=params['product'])
        if params.get('responsible'):
            responsible = params['responsible']
            queryset = queryset.filter(
                Q(created_by_id=responsible) | Q(confirmed_by_id=responsible)
                | Q(items__counted_by_id=responsible)
            )
        start, end = parse_datetime_range(params)
        return filter_datetime_range(queryset, 'created_at', start, end).distinct()

    def create(self, request, *args, **kwargs):
        serializer = InventoryCountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = getattr(request, 'branch_context', None)
        if current is None or current.pk != serializer.validated_data['branch']:
            raise PermissionDenied('A filial de contexto deve ser a filial do inventario.')
        count = create_inventory_count(
            user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(self.get_serializer(count).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=('get',), url_path='options', url_name='options')
    def workflow_options(self, request):
        branch = getattr(request, 'branch_context', None)
        if (
            branch is None
            or branch.status != Status.ACTIVE
            or branch.company.status != Status.ACTIVE
        ):
            raise PermissionDenied('Selecione uma filial ativa para realizar o inventario.')
        open_product_ids = InventoryCountItem.objects.filter(
            branch=branch, is_open=True
        ).values_list('product_id', flat=True)
        stocks = {
            stock.product_id: stock
            for stock in eligible_workflow_stocks(branch, exclude_open_counts=True)
        }
        products = eligible_inventory_products(branch).exclude(pk__in=open_product_ids)
        configs = {
            config.product_id: config
            for config in ProductBranchConfig.objects.filter(
                branch=branch, product__in=products, is_available=True,
            ).select_related('category')
        }
        options = []
        for product in products:
            stock = stocks.get(product.pk)
            item = {
                'stock': stock.pk if stock else None,
                'product': product.pk,
                'product_name': product.name,
                'internal_code': product.internal_code,
                'unit': product.unit,
                'category': configs[product.pk].category_id,
                'category_name': configs[product.pk].category.name if configs[product.pk].category_id else '',
                'current_quantity': format(stock.current_quantity, 'f') if stock else '0',
                'equivalent_quantity': format(stock.equivalent_quantity(), 'f') if stock else '0',
            }
            try:
                config = product.fraction_config
            except ObjectDoesNotExist:
                config = None
            if config and config.tracking_active:
                current_content = stock.current_content if stock else Decimal('0')
                complete, residual = content_breakdown(current_content, config.package_content)
                item.update({
                    'current_content': format(current_content, 'f'),
                    'package_content': format(config.package_content, 'f'),
                    'content_unit': config.content_unit,
                    'complete_packages': format(complete, 'f'),
                    'residual_content': format(residual, 'f'),
                })
            options.append(item)
        return Response({
            'branch': {'id': branch.pk, 'name': branch.name},
            'stocks': options,
        })

    @action(detail=True, methods=('post',))
    def confirm(self, request, pk=None):
        serializer = IdempotencySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = confirm_inventory_count(
            inventory_count=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        replayed = bool(getattr(count, '_idempotency_replayed', False))
        request.audit_fallback_suppressed = replayed
        return Response(self.get_serializer(count).data)


class AdvancedInventoryReportViewSet(viewsets.ViewSet):
    permission_classes = (InventoryFunctionalPermission,)
    permission_codes = {'list': 'inventory.report.view'}

    def list(self, request):
        query = AdvancedInventoryReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        branch = getattr(request, 'branch_context', None)
        if branch is None:
            raise PermissionDenied('Selecione uma filial para consultar o relatorio.')
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf') and not (
            request.user.is_superuser or user_has_company_permission(
                request.user, branch.company_id, 'reports.export'
            )
        ):
            raise PermissionDenied('Você não possui permissão para exportar relatórios.')
        start = filters.get('start_datetime')
        end = filters.get('end_datetime')
        product = filters.get('product')
        responsible = filters.get('responsible')
        transfer_status = filters.get('transfer_status')
        divergence_status = filters.get('divergence_status')
        inventory_status = filters.get('inventory_status')
        loss_reason = filters.get('loss_reason')
        resolution_type = filters.get('resolution_type')

        transfer_scope = Q(transfer__origin_branch=branch) | Q(
            transfer__destination_branch=branch
        )
        dispatch_items = StockTransferItem.objects.select_related(
            'product', 'transfer'
        ).prefetch_related(
            'receipt_items', 'divergence__resolutions'
        ).filter(transfer_scope, transfer__dispatched_at__isnull=False)
        receipt_items = StockTransferReceiptItem.objects.select_related(
            'receipt', 'transfer_item__product', 'transfer_item__transfer'
        ).filter(
            Q(receipt__destination_branch=branch)
            | Q(transfer_item__transfer__origin_branch=branch)
        )
        receipts = StockTransferReceipt.objects.select_related(
            'transfer', 'received_by'
        ).prefetch_related(
            Prefetch(
                'items',
                queryset=StockTransferReceiptItem.objects.select_related(
                    'transfer_item__product'
                ),
            )
        ).filter(
            Q(destination_branch=branch) | Q(transfer__origin_branch=branch)
        )
        resolutions = TransferDivergenceResolution.objects.select_related(
            'divergence__transfer_item__product',
            'divergence__transfer_item__transfer',
        ).filter(
            Q(divergence__transfer_item__transfer__origin_branch=branch)
            | Q(divergence__transfer_item__transfer__destination_branch=branch)
        )
        divergences = TransferDivergence.objects.select_related(
            'transfer_item__product', 'transfer_item__transfer'
        ).filter(
            Q(transfer_item__transfer__origin_branch=branch)
            | Q(transfer_item__transfer__destination_branch=branch)
        )
        losses = LossRecord.objects.select_related('product').filter(branch=branch)
        counts = InventoryCount.objects.filter(branch=branch)
        has_period = bool(start or end)
        snapshot_as_of = end or timezone.now()
        snapshot_cutoff = (
            inclusive_end_exclusive(end) if end else snapshot_as_of
        )
        snapshot_transfers = StockTransfer.objects.filter(
            Q(origin_branch=branch) | Q(destination_branch=branch),
            dispatched_at__isnull=False,
        )

        if transfer_status and not has_period:
            dispatch_items = dispatch_items.filter(transfer__status=transfer_status)
            receipts = receipts.filter(transfer__status=transfer_status)
            receipt_items = receipt_items.filter(
                transfer_item__transfer__status=transfer_status
            )
            resolutions = resolutions.filter(
                divergence__transfer_item__transfer__status=transfer_status
            )
            divergences = divergences.filter(
                transfer_item__transfer__status=transfer_status
            )
        if divergence_status and not has_period:
            divergences = divergences.filter(status=divergence_status)
            resolutions = resolutions.filter(divergence__status=divergence_status)
        if inventory_status:
            counts = counts.filter(status=inventory_status)
        if loss_reason:
            losses = losses.filter(reason=loss_reason)
        if resolution_type:
            resolutions = resolutions.filter(resolution_type=resolution_type)
        if product:
            dispatch_items = dispatch_items.filter(product_id=product)
            receipts = receipts.filter(transfer__items__product_id=product)
            receipt_items = receipt_items.filter(transfer_item__product_id=product)
            resolutions = resolutions.filter(
                divergence__transfer_item__product_id=product
            )
            divergences = divergences.filter(transfer_item__product_id=product)
            losses = losses.filter(product_id=product)
            counts = counts.filter(items__product_id=product)
            snapshot_transfers = snapshot_transfers.filter(items__product_id=product)
        if responsible:
            dispatch_items = dispatch_items.filter(
                transfer__dispatched_by_id=responsible
            )
            receipts = receipts.filter(received_by_id=responsible)
            receipt_items = receipt_items.filter(receipt__received_by_id=responsible)
            resolutions = resolutions.filter(resolved_by_id=responsible)
            divergences = divergences.filter(detected_by_id=responsible)
            losses = losses.filter(recorded_by_id=responsible)
            counts = counts.filter(
                Q(created_by_id=responsible) | Q(confirmed_by_id=responsible)
                | Q(items__counted_by_id=responsible)
            )

        if has_period:
            snapshot_transfers = snapshot_transfers.filter(
                dispatched_at__lt=snapshot_cutoff
            )

        dispatch_items = filter_datetime_range(
            dispatch_items, 'transfer__dispatched_at', start, end
        )
        receipts = filter_datetime_range(receipts, 'received_at', start, end)
        receipt_items = filter_datetime_range(
            receipt_items, 'receipt__received_at', start, end
        )
        resolutions = filter_datetime_range(
            resolutions, 'resolved_at', start, end
        )
        divergences = filter_datetime_range(
            divergences, 'detected_at', start, end
        )
        losses = filter_datetime_range(losses, 'recorded_at', start, end)
        if start or end:
            event_filter = Q()
            if start:
                event_filter &= (
                    Q(status='OPEN', created_at__gte=start)
                    | Q(status='CONFIRMED', confirmed_at__gte=start)
                )
            if end:
                event_filter &= (
                    Q(status='OPEN', created_at__lt=snapshot_cutoff)
                    | Q(status='CONFIRMED', confirmed_at__lt=snapshot_cutoff)
                )
            counts = counts.filter(event_filter)

        dispatch_items = list(dispatch_items.distinct())
        receipts = list(receipts.distinct())
        receipt_items = list(receipt_items.distinct())
        resolutions = list(resolutions.distinct())
        divergences = list(divergences.distinct())
        losses = list(losses.distinct())
        counts = list(counts.distinct())
        count_items = InventoryCountItem.objects.select_related(
            'inventory_count', 'product'
        ).filter(
            inventory_count__in=counts
        )
        if product:
            count_items = count_items.filter(product_id=product)
        count_items = list(count_items)

        snapshot_transfers = list(snapshot_transfers.select_related(
            'dispatched_by'
        ).prefetch_related(
            'items__product',
            Prefetch(
                'items__receipt_items',
                queryset=StockTransferReceiptItem.objects.select_related('receipt'),
            ),
            Prefetch(
                'items__divergence__resolutions',
                queryset=TransferDivergenceResolution.objects.order_by('resolved_at'),
            ),
        ).distinct())

        def item_state_at(item):
            regular_received = sum((
                receipt_item.received_quantity
                for receipt_item in item.receipt_items.all()
                if not has_period or receipt_item.receipt.received_at < snapshot_cutoff
            ), Decimal('0'))
            try:
                divergence = item.divergence
            except TransferDivergence.DoesNotExist:
                divergence = None
            divergence_active = bool(
                divergence
                and (not has_period or divergence.detected_at < snapshot_cutoff)
            )
            resolved = Decimal('0')
            if divergence_active:
                resolved = sum((
                    resolution.quantity
                    for resolution in divergence.resolutions.all()
                    if not has_period or resolution.resolved_at < snapshot_cutoff
                ), Decimal('0'))
            if divergence_active:
                divergence_pending = max(
                    divergence.initial_quantity - resolved, Decimal('0')
                )
                in_transit = Decimal('0')
            else:
                divergence_pending = Decimal('0')
                in_transit = max(
                    (item.dispatched_quantity or Decimal('0')) - regular_received,
                    Decimal('0'),
                )
            return regular_received, divergence, divergence_active, divergence_pending, in_transit

        transfer_states = {}
        transfer_item_states = {}
        for transfer in snapshot_transfers:
            states = []
            for item in transfer.items.all():
                state = item_state_at(item)
                transfer_item_states[item.pk] = state
                states.append((item, state))
            if any(state[2] for _, state in states):
                derived_status = StockTransferStatus.RECEIVED_WITH_DIVERGENCE
            elif states and all(
                state[0] >= (item.dispatched_quantity or Decimal('0'))
                for item, state in states
            ):
                derived_status = StockTransferStatus.RECEIVED
            elif any(state[0] > 0 for _, state in states):
                derived_status = StockTransferStatus.PARTIALLY_RECEIVED
            else:
                derived_status = StockTransferStatus.IN_TRANSIT
            transfer_states[transfer.pk] = derived_status

        eligible_transfer_ids = {
            transfer.pk
            for transfer in snapshot_transfers
            if not transfer_status or transfer_states[transfer.pk] == transfer_status
        }
        eligible_snapshot_items = [
            item
            for transfer in snapshot_transfers
            if transfer.pk in eligible_transfer_ids
            for item in transfer.items.all()
            if not product or item.product_id == product
        ]
        snapshot_items = [
            item
            for item in eligible_snapshot_items
            if not responsible or item.transfer.dispatched_by_id == responsible
        ]
        divergence_rows = []
        snapshot_divergence_statuses = {}
        for item in eligible_snapshot_items:
            _, divergence, active, pending, _ = transfer_item_states[item.pk]
            if not active:
                continue
            status_at_snapshot = (
                TransferDivergenceStatus.RESOLVED
                if pending == 0 else TransferDivergenceStatus.PENDING
            )
            snapshot_divergence_statuses[divergence.pk] = status_at_snapshot
            if divergence_status and status_at_snapshot != divergence_status:
                continue
            if responsible and divergence.detected_by_id != responsible:
                continue
            divergence_rows.append((divergence, pending))

        if has_period and transfer_status:
            dispatch_items = [
                item for item in dispatch_items
                if item.transfer_id in eligible_transfer_ids
            ]
            receipt_items = [
                item for item in receipt_items
                if item.transfer_item.transfer_id in eligible_transfer_ids
            ]
            receipts = [
                item for item in receipts if item.transfer_id in eligible_transfer_ids
            ]
            resolutions = [
                item for item in resolutions
                if item.divergence.transfer_item.transfer_id in eligible_transfer_ids
            ]
            divergences = [
                item for item in divergences
                if item.transfer_item.transfer_id in eligible_transfer_ids
            ]
        if has_period and divergence_status:
            matching_divergence_ids = {
                divergence_id
                for divergence_id, status_at_snapshot
                in snapshot_divergence_statuses.items()
                if status_at_snapshot == divergence_status
            }
            resolutions = [
                item for item in resolutions
                if item.divergence_id in matching_divergence_ids
            ]
            divergences = [
                item for item in divergences
                if item.pk in matching_divergence_ids
            ]

        quantities = {}
        content_quantities = {}

        def add_quantity(metric, unit, value):
            quantities.setdefault(metric, {})
            quantities[metric][unit] = quantities[metric].get(unit, Decimal('0')) + value

        def add_content(metric, unit, value):
            if value is None or not unit:
                return
            content_quantities.setdefault(metric, {})
            content_quantities[metric][unit] = (
                content_quantities[metric].get(unit, Decimal('0')) + value
            )

        def content_payload(content, package_content, content_unit):
            if content is None or package_content is None:
                return {
                    'content_quantity': None,
                    'package_content': None,
                    'content_unit': None,
                    'complete_packages': None,
                    'residual_content': None,
                }
            complete, residual = content_breakdown(content, package_content)
            return {
                'content_quantity': format(content, 'f'),
                'package_content': format(package_content, 'f'),
                'content_unit': content_unit,
                'complete_packages': format(complete, 'f'),
                'residual_content': format(residual, 'f'),
            }

        for item in dispatch_items:
            add_quantity(
                'transfer_dispatched', item.product.unit,
                item.dispatched_quantity or Decimal('0'),
            )
            add_content(
                'transfer_dispatched', item.content_unit_snapshot,
                exact_multiply(item.dispatched_quantity, item.package_content_snapshot)
                if item.package_content_snapshot is not None else None,
            )
        for item in receipt_items:
            add_quantity(
                'transfer_received', item.transfer_item.product.unit,
                item.received_quantity,
            )
            add_content(
                'transfer_received', item.transfer_item.content_unit_snapshot,
                item.received_content_snapshot,
            )
        for resolution in resolutions:
            item = resolution.divergence.transfer_item
            add_quantity(
                f'resolution_{resolution.resolution_type.lower()}',
                item.product.unit,
                resolution.quantity,
            )
            if resolution.resolution_type == TransferResolutionType.FOUND_RECEIPT:
                add_quantity('transfer_received', item.product.unit, resolution.quantity)
            add_content(
                f'resolution_{resolution.resolution_type.lower()}',
                item.content_unit_snapshot,
                exact_multiply(resolution.quantity, item.package_content_snapshot)
                if item.package_content_snapshot is not None else None,
            )
        for divergence, pending in divergence_rows:
            add_quantity(
                'divergence_pending', divergence.transfer_item.product.unit,
                pending,
            )
            add_content(
                'divergence_pending', divergence.transfer_item.content_unit_snapshot,
                exact_multiply(
                    pending, divergence.transfer_item.package_content_snapshot
                ) if divergence.transfer_item.package_content_snapshot is not None else None,
            )
        for loss in losses:
            add_quantity('loss', loss.product.unit, loss.quantity)
            add_content('loss', loss.content_unit, loss.content_quantity)
        for item in count_items:
            add_quantity('inventory_difference', item.product.unit, item.difference_quantity)
            add_content('inventory_difference', item.content_unit, item.difference_content)

        in_transit_rows = []
        for item in snapshot_items:
            pending = transfer_item_states[item.pk][4]
            if pending > 0:
                add_quantity('transfer_in_transit', item.product.unit, pending)
                add_content(
                    'transfer_in_transit', item.content_unit_snapshot,
                    exact_multiply(pending, item.package_content_snapshot)
                    if item.package_content_snapshot is not None else None,
                )
                in_transit_rows.append((item, pending))

        quantities = {
            metric: {unit: format(value, 'f') for unit, value in sorted(by_unit.items())}
            for metric, by_unit in sorted(quantities.items())
        }
        content_quantities = {
            metric: {unit: format(value, 'f') for unit, value in sorted(by_unit.items())}
            for metric, by_unit in sorted(content_quantities.items())
        }

        receipt_ids = {item.pk for item in receipts}
        resolution_ids = {item.pk for item in resolutions}
        loss_ids = {item.pk for item in losses}
        count_item_ids = {item.pk for item in count_items}
        dispatch_item_ids = {item.pk for item in dispatch_items}
        movement_records = list(StockMovement.objects.filter(
            Q(
                domain_origin=MovementDomainOrigin.TRANSFER_DISPATCH,
                transfer_item_id__in=dispatch_item_ids,
            )
            | Q(operation_reference__in=receipt_ids)
            | Q(transfer_resolution_id__in=resolution_ids)
            | Q(loss_record_id__in=loss_ids)
            | Q(inventory_count_item_id__in=count_item_ids)
        ).order_by('pk').values(
            'pk', 'domain_origin', 'transfer_item_id', 'operation_reference',
            'transfer_resolution_id', 'loss_record_id', 'inventory_count_item_id',
        ))
        movement_ids = [movement['pk'] for movement in movement_records]
        dispatch_movement_ids = {}
        receipt_movement_ids = {}
        resolution_movement_ids = {}
        loss_movement_ids = {}
        count_item_movement_ids = {}
        for movement in movement_records:
            if movement['domain_origin'] == MovementDomainOrigin.TRANSFER_DISPATCH:
                dispatch_movement_ids.setdefault(
                    movement['transfer_item_id'], []
                ).append(movement['pk'])
            receipt_movement_ids.setdefault((
                str(movement['operation_reference']), movement['transfer_item_id'],
            ), []).append(movement['pk'])
            receipt_movement_ids.setdefault(
                str(movement['operation_reference']), []
            ).append(movement['pk'])
            if movement['transfer_resolution_id']:
                resolution_movement_ids.setdefault(
                    movement['transfer_resolution_id'], []
                ).append(movement['pk'])
            if movement['loss_record_id']:
                loss_movement_ids.setdefault(
                    movement['loss_record_id'], []
                ).append(movement['pk'])
            if movement['inventory_count_item_id']:
                count_item_movement_ids.setdefault(
                    movement['inventory_count_item_id'], []
                ).append(movement['pk'])

        dispatch_event_rows = [{
            'transfer': str(item.transfer_id),
            'transfer_item': item.pk,
            'event_at': item.transfer.dispatched_at.isoformat(),
            'product': item.product_id,
            'product_name': item.product.name,
            'unit': item.product.unit,
            'quantity': format(item.dispatched_quantity or Decimal('0'), 'f'),
            **content_payload(
                exact_multiply(item.dispatched_quantity, item.package_content_snapshot)
                if item.package_content_snapshot is not None else None,
                item.package_content_snapshot,
                item.content_unit_snapshot,
            ),
            'movement_ids': dispatch_movement_ids.get(item.pk, []),
        } for item in dispatch_items]
        filtered_receipt_items = {}
        for item in receipt_items:
            filtered_receipt_items.setdefault(item.receipt_id, []).append(item)
        receipt_event_rows = [{
            'receipt': str(receipt.pk),
            'transfer': str(receipt.transfer_id),
            'event_at': receipt.received_at.isoformat(),
            'finalize': receipt.finalize,
            'received_by': receipt.received_by_id,
            'movement_ids': receipt_movement_ids.get(str(receipt.pk), []),
            'items': [{
                'transfer_item': item.transfer_item_id,
                'product': item.transfer_item.product_id,
                'product_name': item.transfer_item.product.name,
                'unit': item.transfer_item.product.unit,
                'quantity': format(item.received_quantity, 'f'),
                **content_payload(
                    item.received_content_snapshot,
                    item.transfer_item.package_content_snapshot,
                    item.transfer_item.content_unit_snapshot,
                ),
                'movement_ids': receipt_movement_ids.get(
                    (str(receipt.pk), item.transfer_item_id), []
                ),
            } for item in filtered_receipt_items.get(receipt.pk, [])],
        } for receipt in receipts]
        resolution_event_rows = [{
            'resolution': str(item.pk),
            'divergence': item.divergence_id,
            'transfer': str(item.divergence.transfer_item.transfer_id),
            'transfer_item': item.divergence.transfer_item_id,
            'event_at': item.resolved_at.isoformat(),
            'resolution_type': item.resolution_type,
            'product': item.divergence.transfer_item.product_id,
            'product_name': item.divergence.transfer_item.product.name,
            'unit': item.divergence.transfer_item.product.unit,
            'quantity': format(item.quantity, 'f'),
            **content_payload(
                exact_multiply(
                    item.quantity,
                    item.divergence.transfer_item.package_content_snapshot,
                ) if item.divergence.transfer_item.package_content_snapshot is not None else None,
                item.divergence.transfer_item.package_content_snapshot,
                item.divergence.transfer_item.content_unit_snapshot,
            ),
            'movement_ids': resolution_movement_ids.get(item.pk, []),
        } for item in resolutions]
        divergence_event_rows = [{
            'divergence': item.pk,
            'transfer': str(item.transfer_item.transfer_id),
            'transfer_item': item.transfer_item_id,
            'event_at': item.detected_at.isoformat(),
            'product': item.transfer_item.product_id,
            'product_name': item.transfer_item.product.name,
            'unit': item.transfer_item.product.unit,
            'initial_quantity': format(item.initial_quantity, 'f'),
        } for item in divergences]
        loss_event_rows = [{
            'loss': str(item.pk),
            'event_at': item.recorded_at.isoformat(),
            'product': item.product_id,
            'product_name': item.product.name,
            'unit': item.product.unit,
            'quantity': format(item.quantity, 'f'),
            **content_payload(
                item.content_quantity,
                item.package_content_snapshot,
                item.content_unit,
            ),
            'reason': item.reason,
            'movement_ids': loss_movement_ids.get(item.pk, []),
        } for item in losses]
        count_event_rows = [{
            'inventory_count': str(item.inventory_count_id),
            'inventory_count_item': item.pk,
            'event_at': (
                item.inventory_count.confirmed_at
                if item.inventory_count.status == InventoryCountStatus.CONFIRMED
                else item.inventory_count.created_at
            ).isoformat(),
            'status': item.inventory_count.status,
            'product': item.product_id,
            'product_name': item.product.name,
            'unit': item.product.unit,
            'difference_quantity': format(item.difference_quantity, 'f'),
            'theoretical_content': (
                format(item.theoretical_content, 'f')
                if item.theoretical_content is not None else None
            ),
            'counted_content': (
                format(item.counted_content, 'f')
                if item.counted_content is not None else None
            ),
            **content_payload(
                item.difference_content,
                item.package_content_snapshot,
                item.content_unit,
            ),
            'movement_ids': count_item_movement_ids.get(item.pk, []),
        } for item in count_items]

        state_transfer_rows = [{
            'transfer': str(transfer.pk),
            'status': transfer_states[transfer.pk],
            'dispatched_at': transfer.dispatched_at.isoformat(),
            'origin_branch': transfer.origin_branch_id,
            'destination_branch': transfer.destination_branch_id,
        } for transfer in snapshot_transfers
            if transfer.pk in eligible_transfer_ids
            and (not responsible or transfer.dispatched_by_id == responsible)]
        state_divergence_rows = [{
            'divergence': divergence.pk,
            'transfer': str(divergence.transfer_item.transfer_id),
            'transfer_item': divergence.transfer_item_id,
            'status': snapshot_divergence_statuses[divergence.pk],
            'product': divergence.transfer_item.product_id,
            'unit': divergence.transfer_item.product.unit,
            'pending_quantity': format(pending, 'f'),
            **content_payload(
                exact_multiply(
                    pending, divergence.transfer_item.package_content_snapshot
                ) if divergence.transfer_item.package_content_snapshot is not None else None,
                divergence.transfer_item.package_content_snapshot,
                divergence.transfer_item.content_unit_snapshot,
            ),
        } for divergence, pending in divergence_rows]
        state_in_transit_rows = [{
            'transfer': str(item.transfer_id),
            'transfer_item': item.pk,
            'product': item.product_id,
            'unit': item.product.unit,
            'pending_quantity': format(pending, 'f'),
            **content_payload(
                exact_multiply(pending, item.package_content_snapshot)
                if item.package_content_snapshot is not None else None,
                item.package_content_snapshot,
                item.content_unit_snapshot,
            ),
        } for item, pending in in_transit_rows]

        financials = {
            'inventory_potential_sale_value': format(sum(
                (item.potential_sale_value for item in count_items), Decimal('0')
            ), '.12f'),
            'loss_potential_sale_value': format(sum(
                (item.potential_sale_value for item in losses), Decimal('0')
            ), '.12f'),
            'pending_divergence_potential_sale_value': format(sum(
                (pending * divergence.transfer_item.origin_sale_price_snapshot
                 for divergence, pending in divergence_rows), Decimal('0')
            ), '.12f'),
            'in_transit_potential_sale_value': format(sum(
                (pending * (item.origin_sale_price_snapshot or Decimal('0'))
                 for item, pending in in_transit_rows), Decimal('0')
            ), '.12f'),
        }
        if _can_view_costs(request, branch.pk):
            financials.update({
                'inventory_cost_impact': format(sum(
                    (item.cost_impact for item in count_items), Decimal('0')
                ), '.12f'),
                'loss_cost_impact': format(sum(
                    (item.cost_impact for item in losses), Decimal('0')
                ), '.12f'),
                'pending_divergence_cost_impact': format(sum(
                    (pending * divergence.transfer_item.origin_unit_cost_snapshot
                     for divergence, pending in divergence_rows), Decimal('0')
                ), '.12f'),
                'in_transit_cost_value': format(sum(
                    (pending * (item.origin_unit_cost_snapshot or Decimal('0'))
                     for item, pending in in_transit_rows), Decimal('0')
                ), '.12f'),
            })

        transfer_ids = {item.transfer_id for item in dispatch_items}
        transfer_status_counts = {
            value: sum(
                1
                for transfer in snapshot_transfers
                if transfer.pk in eligible_transfer_ids
                and (not responsible or transfer.dispatched_by_id == responsible)
                and transfer_states[transfer.pk] == value
            )
            for value in StockTransferStatus.values
        }
        state_basis = 'as_of_period_end' if has_period else 'current_state'
        data = {
            'branch': branch.pk,
            'filters': {
                'start_datetime': start.isoformat() if start else None,
                'end_datetime': end.isoformat() if end else None,
                'product': product,
                'responsible': responsible,
                'transfer_status': transfer_status,
                'divergence_status': divergence_status,
                'inventory_status': inventory_status,
                'loss_reason': loss_reason,
                'resolution_type': resolution_type,
            },
            'events': {
                'transfer_dispatches': len(transfer_ids),
                'transfer_receipts': len(receipt_ids),
                'divergence_resolutions': len(resolutions),
                'divergences': len(divergences),
                'losses': len(losses),
                'inventory_counts': len(counts),
            },
            'transfer_statuses': transfer_status_counts,
            'state_basis': {
                'mode': state_basis,
                'as_of': snapshot_as_of.isoformat(),
                'event_metrics': 'event_time',
            },
            'pending_quantity_basis': state_basis,
            'pending_quantity_as_of': snapshot_as_of.isoformat(),
            'quantities_by_unit': quantities,
            'content_by_unit': content_quantities,
            'financials': financials,
            'drill_down': {
                'inventory_counts': '/api/v1/inventory-counts/',
                'divergences': '/api/v1/transfer-divergences/',
                'losses': '/api/v1/loss-records/',
                'transfers': '/api/v1/stock-transfers/',
                'movements': '/api/v1/stock-movements/',
                'movement_ids': movement_ids,
                'resource_ids': {
                    'transfers': sorted(str(item) for item in transfer_ids),
                    'receipts': sorted(str(item) for item in receipt_ids),
                    'resolutions': sorted(str(item) for item in resolution_ids),
                    'divergences': sorted(str(item.pk) for item in divergences),
                    'losses': sorted(str(item) for item in loss_ids),
                    'inventory_counts': sorted(
                        str(item.pk) for item in counts
                    ),
                    'movements': movement_ids,
                    'state_transfers': [
                        item['transfer'] for item in state_transfer_rows
                    ],
                    'state_divergences': [
                        str(item['divergence']) for item in state_divergence_rows
                    ],
                },
                'links': {
                    'transfers': [
                        f'/api/v1/stock-transfers/{item}/'
                        for item in sorted(str(item) for item in transfer_ids)
                    ],
                    'divergences': [
                        f'/api/v1/transfer-divergences/{item.pk}/'
                        for item in divergences
                    ],
                    'losses': [
                        f'/api/v1/loss-records/{item}/'
                        for item in sorted(str(item) for item in loss_ids)
                    ],
                    'inventory_counts': [
                        f'/api/v1/inventory-counts/{item.pk}/' for item in counts
                    ],
                    'movements': [
                        f'/api/v1/stock-movements/{item}/' for item in movement_ids
                    ],
                    'state_transfers': [
                        f"/api/v1/stock-transfers/{item['transfer']}/"
                        for item in state_transfer_rows
                    ],
                    'state_divergences': [
                        f"/api/v1/transfer-divergences/{item['divergence']}/"
                        for item in state_divergence_rows
                    ],
                },
                'contract': {
                    'event_rows': 'filtered_by_each_domain_event_timestamp',
                    'state_rows': state_basis,
                    'state_as_of': snapshot_as_of.isoformat(),
                },
                'event_rows': {
                    'dispatches': dispatch_event_rows,
                    'receipts': receipt_event_rows,
                    'resolutions': resolution_event_rows,
                    'divergences': divergence_event_rows,
                    'losses': loss_event_rows,
                    'inventory_counts': count_event_rows,
                },
                'state_rows': {
                    'transfers': state_transfer_rows,
                    'divergences': state_divergence_rows,
                    'in_transit': state_in_transit_rows,
                },
            },
        }
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            response = render_report_export(
                request, filename='relatorio-avancado-estoque.csv',
                title='Relatório avançado de estoque',
                headers=('indicator', 'value'), rows=report_key_value_rows(data),
                period=data['filters'],
            )
            audit_log(actor=request.user, action='report.export', company=branch.company, branch=branch,
                      metadata={'report': 'advanced_inventory', 'format': request.query_params['export']})
            return response
        return Response(data)
