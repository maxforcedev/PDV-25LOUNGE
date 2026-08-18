from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.db import IntegrityError, transaction
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot
from apps.companies.models import Company, Status
from .models import BranchProductPrice, Category, InventoryBehavior, Product
from .permissions import ProductFunctionalPermission
from .serializers import (
    BranchProductPriceSerializer,
    CategorySerializer,
    CompositionSerializer,
    ProductComponentSerializer,
    ProductSerializer,
)
from .services import reorder_categories


class CatalogViewSet(viewsets.ModelViewSet):
    permission_classes = [ProductFunctionalPermission]
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')
    permission_codes = {
        'list': 'products.view',
        'retrieve': 'products.view',
        'create': 'products.add',
        'update': 'products.change',
        'partial_update': 'products.change',
        'activate': 'products.change_status',
        'deactivate': 'products.change_status',
        'reorder': 'products.change',
        'price_comparison': 'products.view',
    }

    def filter_common(self, queryset):
        company_id = self.request.query_params.get('company')
        item_status = self.request.query_params.get('status')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        if item_status:
            queryset = queryset.filter(status=item_status)
        return queryset

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        item = self.get_object()
        before = model_snapshot(item, ('status',))
        item.full_clean()
        item.status = Status.ACTIVE
        item.save(update_fields=['status', 'updated_at'])
        audit_log(
            actor=request.user, action=f'{item.__class__.__name__.lower()}.activate',
            obj=item, company=item.company, before=before,
            after=model_snapshot(item, ('status',)),
        )
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        item = self.get_object()
        before = model_snapshot(item, ('status',))
        item.status = Status.INACTIVE
        item.save(update_fields=['status', 'updated_at'])
        audit_log(
            actor=request.user, action=f'{item.__class__.__name__.lower()}.deactivate',
            obj=item, company=item.company, before=before,
            after=model_snapshot(item, ('status',)),
        )
        return Response(self.get_serializer(item).data)


class CategoryViewSet(CatalogViewSet):
    serializer_class = CategorySerializer
    permission_codes = {
        'list': 'categories.view', 'retrieve': 'categories.view',
        'create': 'categories.add', 'update': 'categories.change',
        'partial_update': 'categories.change',
        'activate': 'categories.change_status', 'deactivate': 'categories.change_status',
        'reorder': 'categories.change',
    }

    def get_queryset(self):
        queryset = Category.objects.select_related('company').annotate(
            product_count=Count('products')
        ).prefetch_related('products').order_by('sort_order', 'name', 'id')
        branch = getattr(self.request, 'branch_context', None)
        if branch:
            queryset = queryset.filter(company_id=branch.company_id)
        queryset = self.filter_common(queryset)
        search = self.request.query_params.get('search')
        return queryset.filter(name__icontains=search) if search else queryset

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        company_id = request.data.get('company')
        branch = getattr(request, 'branch_context', None)
        if branch and str(branch.company_id) != str(company_id):
            return Response(
                {'company': ['Empresa fora do contexto da filial.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        category_ids = request.data.get('category_ids')
        if not isinstance(category_ids, list):
            return Response(
                {'category_ids': ['Informe uma lista de categorias.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            company = Company.objects.get(pk=company_id)
            if branch and company.pk != branch.company_id:
                raise Company.DoesNotExist
            reorder_categories(company=company, category_ids=category_ids)
        except (Company.DoesNotExist, DjangoValidationError) as error:
            detail = getattr(error, 'message_dict', {'company': ['Empresa invalida.']})
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            self.get_serializer(
                self.get_queryset().filter(company=company), many=True
            ).data
        )


class ProductViewSet(CatalogViewSet):
    serializer_class = ProductSerializer

    audit_fields = (
        'name', 'internal_code', 'cost', 'sale_price', 'status',
        'inventory_behavior', 'is_sellable', 'is_favorite',
    )

    def get_queryset(self):
        queryset = Product.objects.select_related('company', 'category').prefetch_related(
            'components__component_product'
        )
        branch = getattr(self.request, 'branch_context', None)
        if branch:
            queryset = queryset.filter(company_id=branch.company_id)
        queryset = self.filter_common(queryset)
        params = self.request.query_params
        category = params.get('category')
        behavior = params.get('inventory_behavior')
        sellable = params.get('is_sellable')
        favorite = params.get('is_favorite')
        search = params.get('search')
        if category:
            queryset = queryset.filter(category_id=category)
        if behavior:
            queryset = queryset.filter(inventory_behavior=behavior)
        if sellable in ('true', 'false'):
            queryset = queryset.filter(is_sellable=sellable == 'true')
        if favorite in ('true', 'false'):
            queryset = queryset.filter(is_favorite=favorite == 'true')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(internal_code__icontains=search)
                | Q(barcode__icontains=search)
            )
        if params.get('pos') == 'true':
            return queryset.filter(status=Status.ACTIVE, is_sellable=True).order_by(
                '-is_favorite', 'category__sort_order', 'name', 'id'
            )
        return queryset.order_by('-is_favorite', 'name', 'id')

    def perform_create(self, serializer):
        product = serializer.save()
        audit_log(
            actor=self.request.user, action='product.create', obj=product,
            company=product.company, after=model_snapshot(product, self.audit_fields),
        )

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, self.audit_fields)
        product = serializer.save()
        audit_log(
            actor=self.request.user, action='product.update', obj=product,
            company=product.company, before=before,
            after=model_snapshot(product, self.audit_fields),
        )

    @action(detail=False, methods=('post',), url_path='bulk-create')
    @transaction.atomic
    def bulk_create(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied('Cadastro em lote e exclusivo do superusuario da plataforma.')
        rows = request.data.get('products') if isinstance(request.data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise ValidationError({'products': 'Informe ao menos uma linha de produto.'})
        if len(rows) > 200:
            raise ValidationError({'products': 'O limite por operacao e 200 produtos.'})
        normalized = []
        seen_codes = set()
        seen_barcodes = set()
        duplicate_errors = {}
        for row in rows:
            item = dict(row) if isinstance(row, dict) else row
            if isinstance(item, dict):
                for field in ('cost', 'sale_price'):
                    if isinstance(item.get(field), str):
                        item[field] = item[field].replace(',', '.')
                company = str(item.get('company', ''))
                code = str(item.get('internal_code') or '').strip().casefold()
                barcode = str(item.get('barcode') or '').strip().casefold()
                for field, value, seen in (
                    ('internal_code', code, seen_codes), ('barcode', barcode, seen_barcodes)
                ):
                    if not value:
                        continue
                    key = (company, value)
                    if key in seen:
                        duplicate_errors.setdefault(str(len(normalized)), {})[field] = [
                            'Valor repetido dentro deste lote.'
                        ]
                    seen.add(key)
            normalized.append(item)
        if duplicate_errors:
            raise ValidationError({'products': duplicate_errors})
        serializer = self.get_serializer(data=normalized, many=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                products = serializer.save()
        except IntegrityError:
            raise ValidationError({
                'products': 'Outro cadastro gravou um código ou código de barras igual. Revise o lote.'
            })
        for product in products:
            audit_log(
                actor=request.user, action='product.bulk_create', obj=product,
                company=product.company,
                after=model_snapshot(product, self.audit_fields),
            )
        return Response(
            {'count': len(products), 'results': self.get_serializer(products, many=True).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get', 'put'], url_path='components')
    def components(self, request, pk=None):
        product = self.get_object()
        if request.method == 'GET':
            return Response(ProductComponentSerializer(product.components.all(), many=True).data)

        data = request.data
        if isinstance(data, list):
            data = {'components': data}
        serializer = CompositionSerializer(
            data=data,
            context={'request': request, 'product': product},
        )
        serializer.is_valid(raise_exception=True)
        before = list(product.components.values('component_product_id', 'quantity'))
        product = serializer.save()
        product = self.get_queryset().get(pk=product.pk)
        audit_log(
            actor=request.user, action='product.composition.update', obj=product,
            company=product.company, before={'components': before},
            after={'components': list(product.components.values('component_product_id', 'quantity'))},
        )
        return Response(ProductComponentSerializer(product.components.all(), many=True).data)

    @action(detail=False, methods=['get'], url_path='price-comparison')
    def price_comparison(self, request):
        company_id = request.branch_context.company_id
        products = list(
            Product.objects.filter(company_id=company_id).order_by('name', 'id')
        )
        from apps.companies.models import Branch
        branches = list(
            Branch.objects.filter(company_id=company_id, status=Status.ACTIVE).order_by('name', 'id')
        )
        prices = {}
        for price in BranchProductPrice.objects.filter(
            product__in=products, branch__in=branches
        ):
            prices[(price.product_id, price.branch_id)] = price.sale_price
        return Response({
            'branches': [{'id': b.pk, 'name': b.name} for b in branches],
            'products': [
                {
                    'id': product.pk,
                    'name': product.name,
                    'internal_code': product.internal_code,
                    'default_price': f'{product.sale_price:.2f}',
                    'prices': {
                        str(branch.pk): (
                            f'{prices[(product.pk, branch.pk)]:.2f}'
                            if (product.pk, branch.pk) in prices else None
                        )
                        for branch in branches
                    },
                }
                for product in products
            ],
        })


class BranchProductPriceViewSet(viewsets.ModelViewSet):
    serializer_class = BranchProductPriceSerializer
    permission_classes = [ProductFunctionalPermission]
    http_method_names = ('get', 'post', 'patch', 'put', 'delete', 'head', 'options')
    permission_codes = {
        'list': 'products.view', 'retrieve': 'products.view',
        'create': 'branch_prices.change', 'update': 'branch_prices.change',
        'partial_update': 'branch_prices.change', 'destroy': 'branch_prices.change',
    }

    def get_queryset(self):
        branch = self.request.branch_context
        queryset = BranchProductPrice.objects.select_related('product', 'branch').filter(
            product__company_id=branch.company_id
        )
        params = self.request.query_params
        if params.get('product'):
            queryset = queryset.filter(product_id=params['product'])
        if params.get('branch'):
            queryset = queryset.filter(branch_id=params['branch'])
        return queryset

    def perform_create(self, serializer):
        price = serializer.save()
        audit_log(
            actor=self.request.user, action='branch_price.create', obj=price,
            company=price.branch.company, branch=price.branch,
            after=model_snapshot(price, ('product_id', 'branch_id', 'sale_price')),
        )

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('sale_price',))
        price = serializer.save()
        audit_log(
            actor=self.request.user, action='branch_price.update', obj=price,
            company=price.branch.company, branch=price.branch,
            before=before, after=model_snapshot(price, ('sale_price',)),
        )
