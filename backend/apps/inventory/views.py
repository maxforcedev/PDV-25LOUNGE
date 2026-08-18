from django.db.models import (
    Case, CharField, Count, DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Q,
    Subquery, Sum, Value, When,
)
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.base.datetimes import filter_datetime_range, parse_datetime_range
from apps.base.exceptions import DomainValidationError
from apps.companies.models import BranchSettings, Status
from apps.companies.selectors import accessible_branches, user_has_branch_permission
from apps.products.models import Category, Product

from .models import InventoryOperation, Stock, StockMovement
from .permissions import InventoryFunctionalPermission
from .serializers import (
    AdjustmentRequestSerializer,
    GroupEntrySerializer,
    InventoryQuerySerializer,
    MinimumQuantitySerializer,
    MovementRequestSerializer,
    RegularizeNegativesSerializer,
    StockMovementQuerySerializer,
    StockMovementSerializer,
    StockSerializer,
)
from .services import adjustment as adjust_stock
from .services import entry as enter_stock
from .services import exit as exit_stock
from .services import set_minimum
from .services import group_entry, regularize_negatives


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


class StockViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockSerializer
    permission_classes = (InventoryFunctionalPermission,)
    permission_codes = {
        'list': 'inventory.view',
        'retrieve': 'inventory.view',
        'minimum': 'inventory.change_minimum',
        'summary': 'inventory.view',
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
            queryset = queryset.filter(product__category_id=filters['category'])
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
        if state == 'negative':
            queryset = queryset.filter(current_quantity__lt=0)
        elif state == 'zero':
            queryset = queryset.filter(current_quantity=0)
        elif state == 'below_minimum':
            queryset = queryset.filter(
                current_quantity__gt=0, current_quantity__lt=F('minimum_quantity')
            )
        elif state == 'normal':
            queryset = queryset.filter(
                current_quantity__gt=0, current_quantity__gte=F('minimum_quantity')
            )
        return queryset

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'inventory.view')
        branches = accessible_branches(self.request.user, code)
        current = getattr(self.request, 'branch_context', None)
        if current:
            branches = branches.filter(pk=current.pk)
        queryset = Stock.objects.select_related(
            'product', 'product__category', 'branch', 'branch__company'
        ).filter(
            branch__in=branches,
            product__inventory_behavior='direct',
        )
        return self._filtered_queryset(queryset)

    @action(detail=False, methods=('get',))
    def summary(self, request):
        queryset = self.get_queryset()
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
        result = {'allow_negative_stock': False, 'legacy_negative_state': False}
        if branch:
            result['allow_negative_stock'] = BranchSettings.objects.filter(
                branch=branch, allow_negative_stock=True
            ).exists()
        if can_view_kpis or can_regularize:
            result['negative_count'] = queryset.filter(current_quantity__lt=0).count()
            result['legacy_negative_state'] = bool(
                result['negative_count'] and not result['allow_negative_stock']
            )
        if can_view_kpis:
            result.update(queryset.aggregate(
                below_minimum_count=Count(
                'id',
                filter=Q(
                    current_quantity__gt=0,
                    current_quantity__lt=F('minimum_quantity'),
                ),
            ),
            zero_count=Count('id', filter=Q(current_quantity=0)),
            physical_products=Count('id'),
            ))
        if can_view_costs:
            value_expression = ExpressionWrapper(
                Case(
                    When(current_quantity__gt=0, then=F('current_quantity')),
                    default=Value(0),
                    output_field=DecimalField(max_digits=14, decimal_places=3),
                ) * F('product__cost'),
                output_field=DecimalField(max_digits=26, decimal_places=5),
            )
            cost_result = queryset.aggregate(estimated_value=Coalesce(
                Sum(value_expression),
                0,
                output_field=DecimalField(max_digits=26, decimal_places=2),
            ))
            result['estimated_value'] = f"{cost_result['estimated_value']:.2f}"
        return Response(result)

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
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'inventory.view_history')
        branches = accessible_branches(self.request.user, code)
        current = getattr(self.request, 'branch_context', None)
        if current:
            branches = branches.filter(pk=current.pk)
        queryset = _with_operation_count(StockMovement.objects.select_related(
            'stock', 'stock__product', 'stock__branch', 'stock__branch__company',
            'user', 'sale',
        ).filter(stock__branch__in=branches))
        params = self.request.query_params
        query = StockMovementQuerySerializer(data=params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        if filters.get('company'):
            queryset = queryset.filter(stock__branch__company_id=filters['company'])
        if filters.get('branch'):
            queryset = queryset.filter(stock__branch_id=filters['branch'])
        if filters.get('category'):
            queryset = queryset.filter(stock__product__category_id=filters['category'])
        if filters.get('product'):
            queryset = queryset.filter(stock__product_id=filters['product'])
        movement_type = params.get('movement_type') or params.get('type')
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        if params.get('nature'):
            queryset = queryset.filter(nature=params['nature'])
        if filters.get('operation_reference'):
            queryset = queryset.filter(operation_reference=filters['operation_reference'])
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
            branch=data['branch'], category=data['category'], items=data['items'],
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

    @action(detail=False, methods=('get',), url_path='entry-options')
    def entry_options(self, request):
        branch = getattr(request, 'branch_context', None)
        if branch is None or branch.status != Status.ACTIVE or branch.company.status != Status.ACTIVE:
            raise DomainValidationError(
                code='active_branch_context_required',
                message='Selecione uma filial ativa para carregar as opcoes de entrada.',
            )
        categories = Category.objects.filter(
            company_id=branch.company_id, status=Status.ACTIVE,
            products__status=Status.ACTIVE,
            products__inventory_behavior='direct',
        ).distinct().order_by('sort_order', 'name', 'id')
        category_id = request.query_params.get('category')
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
                company_id=branch.company_id, category=category,
                inventory_behavior='direct', status=Status.ACTIVE,
            ).order_by('name', 'id')
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
                'unit': product.unit,
                'current_quantity': str(balances.get(product.pk, 0)),
            } for product in products],
        })
