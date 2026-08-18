import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.db import IntegrityError, transaction
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot
from apps.companies.models import Branch, Company, Status
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


def branch_price_comparison(company_id, *, product=None, category=None, status=None):
    products_queryset = Product.objects.filter(company_id=company_id)
    if product is not None:
        products_queryset = products_queryset.filter(pk=product)
    if category is not None:
        products_queryset = products_queryset.filter(category_id=category)
    if status is not None:
        products_queryset = products_queryset.filter(status=status)
    products = list(products_queryset.order_by('name', 'id'))
    branches = list(
        Branch.objects.filter(company_id=company_id, status=Status.ACTIVE).order_by(
            'name', 'id'
        )
    )
    prices = {
        (price.product_id, price.branch_id): price.sale_price
        for price in BranchProductPrice.objects.filter(
            product__in=products, branch__in=branches
        )
    }
    return {
        'branches': [{'id': branch.pk, 'name': branch.name} for branch in branches],
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
    }


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
        'price_comparison': 'reports.view_prices',
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
        params = self.request.query_params
        category_status = params.get('status')
        if category_status and category_status not in Status.values:
            raise ValidationError({'status': 'Informe um status valido.'})
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        has_products = params.get('has_products')
        if has_products:
            if has_products not in ('true', 'false'):
                raise ValidationError({'has_products': 'Informe true ou false.'})
            queryset = (
                queryset.filter(product_count__gt=0)
                if has_products == 'true'
                else queryset.filter(product_count=0)
            )
        return queryset

    def perform_create(self, serializer):
        category = serializer.save()
        audit_log(
            actor=self.request.user, action='category.create', obj=category,
            company=category.company,
            after=model_snapshot(category, ('name', 'description', 'sort_order', 'status')),
        )

    def perform_update(self, serializer):
        fields = ('name', 'description', 'sort_order', 'status')
        before = model_snapshot(serializer.instance, fields)
        category = serializer.save()
        audit_log(
            actor=self.request.user, action='category.update', obj=category,
            company=category.company, before=before,
            after=model_snapshot(category, fields),
        )

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
            before = dict(Category.objects.filter(company=company).values_list('id', 'sort_order'))
            categories = reorder_categories(company=company, category_ids=category_ids)
        except (Company.DoesNotExist, DjangoValidationError) as error:
            detail = getattr(error, 'message_dict', {'company': ['Empresa inválida.']})
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)
        reference = uuid.uuid4()
        for category in categories:
            if before.get(category.pk) != category.sort_order:
                audit_log(
                    actor=request.user, action='category.reorder', obj=category,
                    company=company,
                    before={'sort_order': before.get(category.pk)},
                    after={'sort_order': category.sort_order},
                    metadata={'operation_reference': str(reference)},
                )
        return Response(
            self.get_serializer(
                self.get_queryset().filter(company=company), many=True
            ).data
        )


class ProductViewSet(CatalogViewSet):
    serializer_class = ProductSerializer

    audit_fields = (
        'category_id', 'name', 'description', 'internal_code', 'barcode', 'unit',
        'cost', 'sale_price', 'image', 'status', 'inventory_behavior',
        'is_sellable', 'is_favorite',
    )

    @staticmethod
    def composition_snapshot(product):
        return [
            {
                'component_product': item.component_product_id,
                'component_name': item.component_product.name,
                'component_unit': item.component_product.unit,
                'quantity': format(item.quantity, 'f'),
            }
            for item in product.components.select_related('component_product').order_by(
                'component_product_id'
            )
        ]

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

    @transaction.atomic
    def perform_create(self, serializer):
        product = serializer.save()
        after = model_snapshot(product, self.audit_fields)
        after['components'] = self.composition_snapshot(product)
        audit_log(
            actor=self.request.user, action='product.create', obj=product,
            company=product.company, after=after,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, self.audit_fields)
        before['components'] = self.composition_snapshot(serializer.instance)
        product = serializer.save()
        after = model_snapshot(product, self.audit_fields)
        after['components'] = self.composition_snapshot(product)
        audit_log(
            actor=self.request.user, action='product.update', obj=product,
            company=product.company, before=before,
            after=after,
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
            raise ValidationError({'products': 'O limite por operação é 200 produtos.'})
        normalized = []
        seen_codes = set()
        seen_barcodes = set()
        seen_names = set()
        duplicate_errors = {}
        for row in rows:
            item = dict(row) if isinstance(row, dict) else row
            if isinstance(item, dict):
                for field in ('cost', 'sale_price'):
                    if isinstance(item.get(field), str):
                        item[field] = item[field].replace(',', '.')
                company = str(item.get('company', ''))
                from .models import normalize_product_name
                _display_name, name = normalize_product_name(str(item.get('name') or ''))
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
                name_key = (company, name)
                if name and name_key in seen_names:
                    duplicate_errors.setdefault(str(len(normalized)), {})['name'] = [
                        'Nome repetido dentro deste lote.'
                    ]
                seen_names.add(name_key)
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
    @transaction.atomic
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
        before = self.composition_snapshot(product)
        product = serializer.save()
        product = self.get_queryset().get(pk=product.pk)
        after = self.composition_snapshot(product)
        audit_log(
            actor=request.user, action='product.composition.update', obj=product,
            company=product.company, before={'components': before},
            after={'components': after},
        )
        return Response(ProductComponentSerializer(product.components.all(), many=True).data)

    @action(detail=False, methods=['get'], url_path='price-comparison')
    def price_comparison(self, request):
        filters = {}
        for parameter in ('product', 'category'):
            if request.query_params.get(parameter):
                try:
                    value = int(request.query_params[parameter])
                except (TypeError, ValueError):
                    raise ValidationError({parameter: 'Informe um identificador válido.'})
                if value <= 0:
                    raise ValidationError({parameter: 'Informe um identificador válido.'})
                filters[parameter] = value
        product_status = request.query_params.get('status')
        if product_status:
            if product_status not in Status.values:
                raise ValidationError({'status': 'Informe um status válido.'})
            filters['status'] = product_status
        return Response(branch_price_comparison(
            request.branch_context.company_id, **filters,
        ))


class BranchProductPriceViewSet(viewsets.ModelViewSet):
    serializer_class = BranchProductPriceSerializer
    permission_classes = [ProductFunctionalPermission]
    http_method_names = ('get', 'post', 'patch', 'put', 'delete', 'head', 'options')
    permission_codes = {
        'list': 'products.view', 'retrieve': 'products.view',
        'create': 'branch_prices.change', 'update': 'branch_prices.change',
        'partial_update': 'branch_prices.change', 'destroy': 'branch_prices.change',
        'table': 'branch_prices.change', 'bulk': 'branch_prices.change',
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

    @action(detail=False, methods=['get'])
    def table(self, request):
        branch = getattr(request, 'branch_context', None)
        if branch is None:
            raise ValidationError({'branch': ['Informe a filial ativa no cabecalho.']})
        data = branch_price_comparison(branch.company_id)
        data['branches'] = [
            item for item in data['branches'] if item['id'] == branch.pk
        ]
        for product in data['products']:
            product['prices'] = {
                str(branch.pk): product['prices'].get(str(branch.pk))
            }
        overrides = self.get_queryset().filter(branch=branch).order_by('product__name', 'id')
        data['overrides'] = self.get_serializer(overrides, many=True).data
        return Response(data)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def bulk(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({
                'detail': 'O lote de preços não foi salvo.',
                'non_field_errors': ['Informe um objeto com branch e items.'],
            })

        branch_id = request.data.get('branch')
        if branch_id in (None, ''):
            raise ValidationError({
                'detail': 'O lote de preços não foi salvo.',
                'branch': ['Informe a filial.'],
            })
        try:
            branch = Branch.objects.select_related('company').select_for_update().get(
                pk=branch_id,
                status=Status.ACTIVE,
                company__status=Status.ACTIVE,
            )
        except (Branch.DoesNotExist, TypeError, ValueError):
            raise ValidationError({
                'detail': 'O lote de preços não foi salvo.',
                'branch': ['Filial inválida ou inativa.'],
            })

        context_branch = getattr(request, 'branch_context', None)
        if context_branch and branch.pk != context_branch.pk:
            raise ValidationError({
                'detail': 'O lote de preços não foi salvo.',
                'branch': ['A filial deve ser a mesma informada em X-Branch-ID.'],
            })

        items = request.data.get('items')
        if not isinstance(items, list) or not items:
            raise ValidationError({
                'detail': 'O lote de preços não foi salvo.',
                'items': ['Informe ao menos uma linha de preço.'],
            })
        if len(items) > 200:
            raise ValidationError({
                'detail': 'O lote de preços não foi salvo.',
                'items': ['O limite por operação é 200 preços.'],
            })

        item_errors = {}
        candidate_product_ids = []
        product_indexes = {}
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                item_errors[index] = {
                    'non_field_errors': ['Cada linha deve ser um objeto.']
                }
                continue
            raw_product_id = item.get('product')
            try:
                product_id = int(raw_product_id)
            except (TypeError, ValueError, OverflowError):
                continue
            candidate_product_ids.append(product_id)
            product_indexes.setdefault(product_id, []).append(index)

        for indexes in product_indexes.values():
            if len(indexes) < 2:
                continue
            for index in indexes:
                item_errors.setdefault(index, {}).setdefault('product', []).append(
                    'Produto repetido dentro deste lote.'
                )

        existing_prices = {
            price.product_id: price
            for price in BranchProductPrice.objects.select_for_update().filter(
                branch=branch, product_id__in=candidate_product_ids
            )
        }
        validated_rows = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            try:
                candidate_product_id = int(item.get('product'))
            except (TypeError, ValueError, OverflowError):
                candidate_product_id = None
            serializer = self.get_serializer(
                existing_prices.get(candidate_product_id),
                data={
                    'product': item.get('product'),
                    'branch': branch.pk,
                    'sale_price': item.get('sale_price'),
                },
            )
            if not serializer.is_valid():
                errors = item_errors.setdefault(index, {})
                for field, messages in serializer.errors.items():
                    errors.setdefault(field, []).extend(messages)
                continue
            validated_rows.append((index, serializer))

        if item_errors:
            raise ValidationError({
                'detail': 'Nenhum preço foi salvo. Corrija as linhas indicadas.',
                'items': item_errors,
            })

        operation_reference = uuid.uuid4()
        audit_fields = ('product_id', 'branch_id', 'sale_price')
        prices = []
        created_count = 0
        for index, serializer in validated_rows:
            before = (
                model_snapshot(serializer.instance, audit_fields)
                if serializer.instance else None
            )
            price = serializer.save()
            created = before is None
            created_count += int(created)
            audit_log(
                actor=request.user,
                action=f'branch_price.{"create" if created else "update"}',
                obj=price,
                company=branch.company,
                branch=branch,
                before=before,
                after=model_snapshot(price, audit_fields),
                metadata={
                    'operation_reference': str(operation_reference),
                    'bulk_index': index,
                    'bulk_size': len(validated_rows),
                },
            )
            prices.append(price)

        return Response({
            'operation_reference': str(operation_reference),
            'count': len(prices),
            'created': created_count,
            'updated': len(prices) - created_count,
            'results': self.get_serializer(prices, many=True).data,
        })

    @transaction.atomic
    def perform_destroy(self, instance):
        before = model_snapshot(instance, ('product_id', 'branch_id', 'sale_price'))
        audit_log(
            actor=self.request.user, action='branch_price.delete', obj=instance,
            company=instance.branch.company, branch=instance.branch, before=before,
        )
        instance.delete()
