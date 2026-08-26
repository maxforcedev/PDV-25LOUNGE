import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import BooleanField, Count, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.db import IntegrityError, transaction
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot
from apps.companies.models import Branch, Company, Status
from apps.companies.selectors import (
    accessible_companies, user_has_branch_permission, user_has_company_permission,
)
from .models import BranchProductPrice, Category, InventoryBehavior, Product, SalesChannel
from .models import (
    FractionableProductConfig, ModifierGroup, ModifierOption, ProductBranchConfig,
    ProductComponent, ProductFractionComponent, ProductModifierGroup,
    ProductProductionDestination, ProductionDestination,
)
from .permissions import ProductFunctionalPermission
from .serializers import (
    BranchProductPriceSerializer,
    CategorySerializer,
    CompositionSerializer,
    CopyBranchConfigurationSerializer,
    CopyCategoryConfigurationSerializer,
    DuplicateProductSerializer,
    FractionableProductConfigSerializer,
    ModifierGroupSerializer,
    ModifierOptionSerializer,
    ProductBranchConfigSerializer,
    ProductComponentSerializer,
    ProductDestinationsSerializer,
    ProductFractionComponentSerializer,
    ProductModifierGroupSerializer,
    ProductSerializer,
    ProductionDestinationSerializer,
)
from .services import (
    copy_branch_configuration, duplicate_product, reorder_categories,
    reorder_modifier_groups, reorder_modifier_options, reorder_product_modifier_groups,
)


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
    @transaction.atomic
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
    @transaction.atomic
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
        'apply_config_to_products': 'categories.change',
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
            raise ValidationError({'status': 'Informe um status válido.'})
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

    @transaction.atomic
    def perform_create(self, serializer):
        category = serializer.save()
        fields = (
            'name', 'description', 'sort_order', 'available_counter', 'available_table',
            'available_command', 'participates_in_service_fee',
            'participates_in_commission', 'status',
        )
        audit_log(
            actor=self.request.user, action='category.create', obj=category,
            company=category.company,
            after=model_snapshot(category, fields),
        )

    @transaction.atomic
    def perform_update(self, serializer):
        fields = (
            'name', 'description', 'sort_order', 'available_counter', 'available_table',
            'available_command', 'participates_in_service_fee',
            'participates_in_commission', 'status',
        )
        before = model_snapshot(serializer.instance, fields)
        category = serializer.save()
        audit_log(
            actor=self.request.user, action='category.update', obj=category,
            company=category.company, before=before,
            after=model_snapshot(category, fields),
        )

    @action(detail=False, methods=['post'])
    @transaction.atomic
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

    @action(detail=True, methods=['post'], url_path='apply-config')
    @transaction.atomic
    def apply_config_to_products(self, request, pk=None):
        category = self.get_object()
        fields_to_apply = (
            'available_counter', 'available_table', 'available_command',
            'participates_in_service_fee', 'participates_in_commission',
        )
        products = list(category.products.all())
        affected = 0
        reference = uuid.uuid4()
        for product in products:
            changed = {}
            before = {}
            for field in fields_to_apply:
                current = getattr(product, field, None)
                target = getattr(category, field)
                if current is None or current != target:
                    before[field] = current
                    setattr(product, field, target)
                    changed[field] = target
            if changed:
                product.save(update_fields=list(changed.keys()) + ['updated_at'])
                affected += 1
                audit_log(
                    actor=request.user, action='category.apply_config',
                    obj=product, company=category.company,
                    before=before,
                    after=changed,
                    metadata={
                        'category_id': str(category.pk),
                        'operation_reference': str(reference),
                    },
                )
        return Response({
            'category': category.name,
            'affected_count': affected,
            'total_products': len(products),
        })


class ProductViewSet(CatalogViewSet):
    serializer_class = ProductSerializer
    permission_codes = {
        **CatalogViewSet.permission_codes,
        'components': 'products.configure_composition',
        'branch_config': 'products.configure_branch',
        'fraction_config': 'products.configure_fraction',
        'activate_fraction_config': 'products.configure_fraction',
        'production_destinations': 'products.configure_destinations',
        'duplicate': 'products.duplicate',
        'copy_branch_config': 'products.configure_branch',
        'copy_category_config': 'products.configure_branch',
    }

    audit_fields = (
        'category_id', 'name', 'description', 'internal_code', 'sku', 'barcode', 'unit',
        'cost', 'sale_price', 'image', 'status', 'inventory_behavior',
        'is_sellable', 'is_favorite', 'available_counter', 'available_table',
        'available_command', 'participates_in_service_fee',
        'participates_in_commission',
    )

    @staticmethod
    def composition_snapshot(product):
        return {
            'ordinary': [
                {
                    'component_product': item.component_product_id,
                    'component_name': item.component_product.name,
                    'component_internal_code': item.component_product.internal_code,
                    'component_unit': item.component_product.unit,
                    'quantity': format(item.quantity, 'f'),
                }
                for item in ProductComponent.objects.filter(
                    parent_product=product
                ).select_related('component_product').order_by('component_product_id')
            ],
            'fractional': [
                {
                    'component_product': item.component_product_id,
                    'component_name': item.component_product.name,
                    'component_internal_code': item.component_product.internal_code,
                    'content_quantity': format(item.content_quantity, 'f'),
                    'content_unit': item.component_product.fraction_config.content_unit,
                    'source_fraction_config': item.component_product.fraction_config.pk,
                    'source_package_content': format(
                        item.component_product.fraction_config.package_content, 'f'
                    ),
                    'source_tracking_active': (
                        item.component_product.fraction_config.tracking_active
                    ),
                }
                for item in ProductFractionComponent.objects.filter(
                    parent_product=product
                ).select_related(
                    'component_product__fraction_config'
                ).order_by('component_product_id')
            ],
        }

    def get_queryset(self):
        queryset = Product.objects.select_related('company', 'category').prefetch_related(
            'components__component_product',
            'fraction_components__component_product__fraction_config',
            'branch_configs', 'branch_prices',
            'production_destination_links__destination',
            'product_suppliers__supplier', 'product_suppliers__units',
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
                | Q(sku__icontains=search)
            )
        if params.get('pos') == 'true':
            channel = params.get('channel', SalesChannel.COUNTER)
            if channel not in SalesChannel.values:
                raise ValidationError({'channel': 'Canal de venda invalido.'})
            if branch:
                config = ProductBranchConfig.objects.filter(
                    branch=branch, product_id=OuterRef('pk')
                )
                queryset = queryset.annotate(
                    effective_branch_available=Coalesce(
                        Subquery(
                            config.values('is_available')[:1],
                            output_field=BooleanField(),
                        ),
                        Value(True),
                    ),
                    effective_branch_channel=Coalesce(
                        Subquery(
                            config.values(f'available_{channel}')[:1],
                            output_field=BooleanField(),
                        ),
                        f'available_{channel}',
                    ),
                ).filter(
                    effective_branch_available=True,
                    effective_branch_channel=True,
                )
            return queryset.filter(status=Status.ACTIVE, is_sellable=True).order_by(
                '-is_favorite', 'category__sort_order', 'name', 'id'
            )
        return queryset.order_by('-is_favorite', 'name', 'id')

    @transaction.atomic
    def perform_create(self, serializer):
        product = serializer.save()
        after = model_snapshot(product, self.audit_fields)
        after['composition'] = self.composition_snapshot(product)
        audit_log(
            actor=self.request.user, action='product.create', obj=product,
            company=product.company, after=after,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, self.audit_fields)
        before['composition'] = self.composition_snapshot(serializer.instance)
        product = serializer.save()
        after = model_snapshot(product, self.audit_fields)
        after['composition'] = self.composition_snapshot(product)
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
        seen_skus = set()
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
                sku = str(item.get('sku') or '').strip().casefold()
                for field, value, seen in (
                    ('internal_code', code, seen_codes), ('barcode', barcode, seen_barcodes),
                    ('sku', sku, seen_skus),
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
                'products': 'Outro cadastro gravou um codigo, codigo de barras ou SKU igual. Revise o lote.'
            })
        for product in products:
            audit_log(
                actor=request.user, action='product.bulk_create', obj=product,
                company=product.company,
                after={
                    **model_snapshot(product, self.audit_fields),
                    'composition': self.composition_snapshot(product),
                },
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
            return Response({
                'components': ProductComponentSerializer(
                    product.components.all(), many=True
                ).data,
                'fraction_components': ProductFractionComponentSerializer(
                    product.fraction_components.all(), many=True
                ).data,
            })

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
            company=product.company, before=before, after=after,
        )
        return Response({
            'components': ProductComponentSerializer(
                product.components.all(), many=True
            ).data,
            'fraction_components': ProductFractionComponentSerializer(
                product.fraction_components.all(), many=True
            ).data,
        })

    @action(detail=True, methods=('get', 'put'), url_path='branch-config')
    @transaction.atomic
    def branch_config(self, request, pk=None):
        product = self.get_object()
        branch = request.branch_context
        config = ProductBranchConfig.objects.filter(
            product=product, branch=branch
        ).first()
        if request.method == 'GET':
            if config is None:
                config = ProductBranchConfig(
                    product=product, branch=branch, is_available=True
                )
            return Response(ProductBranchConfigSerializer(
                config, context={'request': request}
            ).data)
        before = model_snapshot(config, (
            'is_available', 'available_counter', 'available_table',
            'available_command',
        )) if config else {}
        payload = {**request.data, 'product': product.pk, 'branch': branch.pk}
        serializer = ProductBranchConfigSerializer(
            config, data=payload, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        config = serializer.save()
        audit_log(
            actor=request.user, action='product.branch_config.update', obj=config,
            company=product.company, branch=branch, before=before,
            after=model_snapshot(config, (
                'is_available', 'available_counter', 'available_table',
                'available_command',
            )),
        )
        return Response(serializer.data)

    @action(detail=True, methods=('get', 'put'), url_path='fraction-config')
    @transaction.atomic
    def fraction_config(self, request, pk=None):
        product = self.get_object()
        config = FractionableProductConfig.objects.filter(product=product).first()
        if request.method == 'GET':
            return Response(
                FractionableProductConfigSerializer(config).data if config else None
            )
        before = model_snapshot(config, (
            'package_content', 'content_unit', 'tracking_active',
        )) if config else {}
        serializer = FractionableProductConfigSerializer(
            config, data={**request.data, 'product': product.pk}
        )
        serializer.is_valid(raise_exception=True)
        config = serializer.save()
        audit_log(
            actor=request.user, action='product.fraction_config.update', obj=config,
            company=product.company, before=before,
            after=model_snapshot(config, (
                'package_content', 'content_unit', 'tracking_active',
            )),
        )
        return Response(serializer.data)

    @action(
        detail=True, methods=('post',),
        url_path='fraction-config/activate', url_name='fraction-config-activate',
    )
    def activate_fraction_config(self, request, pk=None):
        product = self.get_object()
        try:
            config = product.fraction_config
        except FractionableProductConfig.DoesNotExist:
            raise ValidationError({'fraction_config': 'Configure o produto antes de ativar.'})
        from apps.inventory.services import activate_fraction_tracking

        config = activate_fraction_tracking(config=config, user=request.user)
        return Response(FractionableProductConfigSerializer(config).data)

    @action(detail=True, methods=('get', 'put'), url_path='production-destinations')
    @transaction.atomic
    def production_destinations(self, request, pk=None):
        product = self.get_object()
        branch = request.branch_context
        queryset = ProductionDestination.objects.filter(
            branch=branch, product_links__product=product
        ).order_by('name', 'id')
        if request.method == 'GET':
            return Response(ProductionDestinationSerializer(queryset, many=True).data)
        serializer = ProductDestinationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        destinations = serializer.validated_data['destinations']
        if any(destination.branch_id != branch.pk for destination in destinations):
            raise ValidationError({'destinations': 'Todos os destinos devem pertencer a filial ativa.'})
        before = list(queryset.values_list('pk', flat=True))
        for link in ProductProductionDestination.objects.filter(
            product=product, destination__branch=branch
        ):
            link.delete()
        for destination in destinations:
            ProductProductionDestination.objects.create(
                product=product, destination=destination
            )
        audit_log(
            actor=request.user, action='product.production_destinations.update',
            obj=product, company=product.company, branch=branch,
            before={'destinations': before},
            after={'destinations': [item.pk for item in destinations]},
        )
        return Response(ProductionDestinationSerializer(destinations, many=True).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def duplicate(self, request, pk=None):
        source = self.get_object()
        serializer = DuplicateProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data['suppliers'] and not (
            request.user.is_superuser
            or user_has_company_permission(
                request.user, source.company_id, 'suppliers.change'
            )
        ):
            raise PermissionDenied('Voce nao possui permissao para copiar fornecedores.')
        duplicate = duplicate_product(
            product=source, options=serializer.validated_data
        )
        audit_log(
            actor=request.user, action='product.duplicate', obj=duplicate,
            company=duplicate.company,
            after={
                **model_snapshot(duplicate, self.audit_fields),
                'composition': self.composition_snapshot(duplicate),
                'source_product_id': source.pk,
                'copied_relations': serializer.validated_data,
            },
        )
        return Response(
            self.get_serializer(duplicate).data, status=status.HTTP_201_CREATED
        )

    def _validate_copy_branches(self, request, source, targets):
        for branch_id in [source, *targets]:
            if not request.user.is_superuser and not user_has_branch_permission(
                request.user, branch_id, 'products.configure_branch'
            ):
                raise PermissionDenied('Filial fora do contexto autorizado para copia.')

    @action(detail=True, methods=('post',), url_path='copy-branch-config')
    def copy_branch_config(self, request, pk=None):
        product = self.get_object()
        serializer = CopyBranchConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self._validate_copy_branches(
            request, data['source_branch'], data['target_branches']
        )
        copied = copy_branch_configuration(
            products=[product], **data
        )
        reference = uuid.uuid4()
        for copied_row in copied:
            copied_product = copied_row['product']
            branch = copied_row['target_branch']
            audit_log(
                actor=request.user, action='product.branch_config.copy',
                obj=copied_product, company=copied_product.company, branch=branch,
                before=copied_row['before'],
                after={
                    **copied_row['after'],
                    'source_branch': data['source_branch'],
                    'copied_from': copied_row['source'],
                },
                metadata={'operation_reference': str(reference)},
            )
        return Response({'operation_reference': str(reference), 'count': len(copied)})

    @action(detail=False, methods=('post',), url_path='copy-category-config')
    def copy_category_config(self, request):
        serializer = CopyCategoryConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch = request.branch_context
        try:
            category = Category.objects.get(
                pk=data.pop('category'), company_id=branch.company_id
            )
        except Category.DoesNotExist:
            raise ValidationError({'category': 'Categoria fora da empresa atual.'})
        self._validate_copy_branches(
            request, data['source_branch'], data['target_branches']
        )
        products = list(Product.objects.filter(category=category).order_by('pk'))
        copied = copy_branch_configuration(products=products, **data)
        reference = uuid.uuid4()
        for copied_row in copied:
            product = copied_row['product']
            target = copied_row['target_branch']
            audit_log(
                actor=request.user, action='category.branch_config.copy', obj=product,
                company=product.company, branch=target,
                before=copied_row['before'],
                after={
                    **copied_row['after'],
                    'category_id': category.pk,
                    'source_branch': data['source_branch'],
                    'copied_from': copied_row['source'],
                },
                metadata={'operation_reference': str(reference)},
            )
        return Response({'operation_reference': str(reference), 'count': len(copied)})

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
        'list': 'branch_prices.view', 'retrieve': 'branch_prices.view',
        'create': 'branch_prices.change', 'update': 'branch_prices.change',
        'partial_update': 'branch_prices.change', 'destroy': 'branch_prices.change',
        'table': 'branch_prices.view', 'bulk': 'branch_prices.change',
    }

    def _has_company_permission(self, code):
        branch = self.request.branch_context
        return self.request.user.is_superuser or user_has_company_permission(
            self.request.user, branch.company_id, code
        )

    def _assert_mutation_scope(self, target_branch):
        context_branch = self.request.branch_context
        if target_branch.company_id != context_branch.company_id:
            raise PermissionDenied('Filial fora da empresa atual.')
        if target_branch.pk == context_branch.pk:
            if not self.request.user.is_superuser and not user_has_branch_permission(
                self.request.user, context_branch.pk, 'branch_prices.change'
            ):
                raise PermissionDenied('Você não possui permissão para alterar preços desta filial.')
            return
        if not self._has_company_permission('branch_prices.change_company'):
            raise PermissionDenied('Você não possui permissão para alterar preços de outra filial.')

    def get_queryset(self):
        branch = self.request.branch_context
        queryset = BranchProductPrice.objects.select_related('product', 'branch').filter(
            product__company_id=branch.company_id
        )
        if self.action in {'list', 'retrieve', 'table'}:
            if not self._has_company_permission('branch_prices.view_company'):
                queryset = queryset.filter(branch=branch)
        elif not self._has_company_permission('branch_prices.change_company'):
            queryset = queryset.filter(branch=branch)
        params = self.request.query_params
        if params.get('product'):
            queryset = queryset.filter(product_id=params['product'])
        if params.get('branch'):
            queryset = queryset.filter(branch_id=params['branch'])
        return queryset

    def perform_create(self, serializer):
        self._assert_mutation_scope(serializer.validated_data['branch'])
        price = serializer.save()
        audit_log(
            actor=self.request.user, action='branch_price.create', obj=price,
            company=price.branch.company, branch=price.branch,
            after=model_snapshot(price, ('product_id', 'branch_id', 'sale_price')),
        )

    def perform_update(self, serializer):
        self._assert_mutation_scope(serializer.instance.branch)
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
        if not self._has_company_permission('branch_prices.view_company'):
            data['branches'] = [
                item for item in data['branches'] if item['id'] == branch.pk
            ]
            for product in data['products']:
                product['prices'] = {
                    str(branch.pk): product['prices'].get(str(branch.pk))
                }
        overrides = self.get_queryset().order_by('product__name', 'id')
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
        if context_branch and branch.company_id != context_branch.company_id:
            raise ValidationError({
                'detail': 'O lote de preços não foi salvo.',
                'branch': ['Filial fora da empresa atual.'],
            })
        self._assert_mutation_scope(branch)

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


class ProductionDestinationViewSet(viewsets.ModelViewSet):
    serializer_class = ProductionDestinationSerializer
    permission_classes = (ProductFunctionalPermission,)
    http_method_names = ('get', 'post', 'put', 'patch', 'head', 'options')
    permission_codes = {
        'list': 'products.view',
        'retrieve': 'products.view',
        'create': 'products.configure_destinations',
        'update': 'products.configure_destinations',
        'partial_update': 'products.configure_destinations',
        'activate': 'products.configure_destinations',
        'deactivate': 'products.configure_destinations',
    }

    def get_queryset(self):
        branch = self.request.branch_context
        queryset = ProductionDestination.objects.filter(branch=branch)
        item_status = self.request.query_params.get('status')
        if item_status:
            queryset = queryset.filter(status=item_status)
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return queryset.order_by('name', 'id')

    @transaction.atomic
    def perform_create(self, serializer):
        destination = serializer.save()
        audit_log(
            actor=self.request.user, action='production_destination.create',
            obj=destination, company=destination.branch.company,
            branch=destination.branch,
            after=model_snapshot(destination, ('name', 'code', 'status')),
        )

    @transaction.atomic
    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('name', 'code', 'status'))
        destination = serializer.save()
        audit_log(
            actor=self.request.user, action='production_destination.update',
            obj=destination, company=destination.branch.company,
            branch=destination.branch, before=before,
            after=model_snapshot(destination, ('name', 'code', 'status')),
        )

    def _status(self, request, value):
        destination = self.get_object()
        before = model_snapshot(destination, ('status',))
        destination.status = value
        destination.save(update_fields=('status', 'updated_at'))
        audit_log(
            actor=request.user,
            action=f'production_destination.{"activate" if value == Status.ACTIVE else "deactivate"}',
            obj=destination, company=destination.branch.company,
            branch=destination.branch, before=before,
            after=model_snapshot(destination, ('status',)),
        )
        return Response(self.get_serializer(destination).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def activate(self, request, pk=None):
        return self._status(request, Status.ACTIVE)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def deactivate(self, request, pk=None):
        return self._status(request, Status.INACTIVE)


class ModifierGroupViewSet(viewsets.ModelViewSet):
    serializer_class = ModifierGroupSerializer
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        from apps.companies.selectors import accessible_companies
        queryset = ModifierGroup.objects.select_related('company').prefetch_related('options')
        branch = getattr(self.request, 'branch_context', None)
        if branch:
            queryset = queryset.filter(company_id=branch.company_id)
        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                company__in=accessible_companies(self.request.user, 'modifiers.view')
            )
        company = self.request.query_params.get('company')
        if company:
            queryset = queryset.filter(company_id=company)
        return queryset

    def get_permissions(self):
        if self.action == 'create':
            return [ProductFunctionalPermission()]
        return [ProductFunctionalPermission()]

    @property
    def permission_codes(self):
        return {
            'list': 'modifiers.view',
            'retrieve': 'modifiers.view',
            'create': 'modifiers.change',
            'update': 'modifiers.change',
            'partial_update': 'modifiers.change',
            'activate': 'modifiers.change',
            'deactivate': 'modifiers.change',
            'reorder': 'modifiers.change',
        }

    def perform_create(self, serializer):
        last_order = ModifierGroup.objects.filter(
            company=serializer.validated_data['company']
        ).aggregate(value=Max('sort_order'))['value']
        group = serializer.save(sort_order=(last_order if last_order is not None else -1) + 1)
        audit_log(
            actor=self.request.user, action='modifier_group.create',
            obj=group, company=group.company,
            after=model_snapshot(group, (
                'company_id', 'name', 'is_required', 'min_selections',
                'max_selections', 'allow_option_quantity', 'sort_order', 'status',
            )),
        )

    def perform_update(self, serializer):
        fields = ('company_id', 'name', 'is_required', 'min_selections',
                   'max_selections', 'allow_option_quantity', 'sort_order', 'status')
        before = model_snapshot(serializer.instance, fields)
        group = serializer.save()
        audit_log(
            actor=self.request.user, action='modifier_group.update',
            obj=group, company=group.company, before=before,
            after=model_snapshot(group, fields),
        )

    def _status(self, request, value):
        group = self.get_object()
        before = model_snapshot(group, ('status',))
        group.status = value
        group.save(update_fields=('status', 'updated_at'))
        audit_log(
            actor=request.user,
            action=f'modifier_group.{"activate" if value == Status.ACTIVE else "deactivate"}',
            obj=group, company=group.company, before=before,
            after=model_snapshot(group, ('status',)),
        )
        return Response(self.get_serializer(group).data)

    @action(detail=False, methods=('post',), url_path='reorder')
    @transaction.atomic
    def reorder(self, request):
        branch = request.branch_context
        group_ids = request.data.get('group_ids')
        if not isinstance(group_ids, list):
            raise ValidationError({'group_ids': 'Informe uma lista de grupos.'})
        groups = reorder_modifier_groups(company=branch.company, group_ids=group_ids)
        reference = str(uuid.uuid4())
        for group in groups:
            audit_log(actor=request.user, action='modifier_group.reorder', obj=group,
                      company=branch.company, after={'sort_order': group.sort_order},
                      metadata={'operation_reference': reference})
        return Response(self.get_serializer(groups, many=True).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def activate(self, request, pk=None):
        return self._status(request, Status.ACTIVE)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def deactivate(self, request, pk=None):
        return self._status(request, Status.INACTIVE)


class ProductModifierGroupViewSet(viewsets.ModelViewSet):
    serializer_class = ProductModifierGroupSerializer
    permission_classes = (ProductFunctionalPermission,)
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')

    def get_queryset(self):
        from apps.companies.selectors import accessible_companies
        queryset = ProductModifierGroup.objects.select_related(
            'product', 'modifier_group'
        )
        branch = getattr(self.request, 'branch_context', None)
        if branch:
            queryset = queryset.filter(product__company_id=branch.company_id)
        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                product__company__in=accessible_companies(
                    self.request.user, 'modifiers.view'
                )
            )
        product = self.request.query_params.get('product')
        if product:
            queryset = queryset.filter(product_id=product)
        return queryset

    @property
    def permission_codes(self):
        return {
            'list': 'modifiers.view',
            'retrieve': 'modifiers.view',
            'create': 'modifiers.change',
            'update': 'modifiers.change',
            'partial_update': 'modifiers.change',
            'activate': 'modifiers.change',
            'deactivate': 'modifiers.change',
            'reorder': 'modifiers.change',
        }

    def perform_create(self, serializer):
        last_order = ProductModifierGroup.objects.filter(
            product=serializer.validated_data['product']
        ).aggregate(value=Max('sort_order'))['value']
        link = serializer.save(sort_order=(last_order if last_order is not None else -1) + 1)
        audit_log(
            actor=self.request.user, action='product_modifier_link.create',
            obj=link, company=link.product.company,
            after=model_snapshot(link, ('product_id', 'modifier_group_id', 'sort_order', 'status')),
        )

    def perform_update(self, serializer):
        fields = ('product_id', 'modifier_group_id', 'sort_order', 'status')
        before = model_snapshot(serializer.instance, fields)
        link = serializer.save()
        audit_log(
            actor=self.request.user, action='product_modifier_link.update',
            obj=link, company=link.product.company, before=before,
            after=model_snapshot(link, fields),
        )

    def _status(self, request, value):
        link = self.get_object()
        before = model_snapshot(link, ('status',))
        link.status = value
        link.save(update_fields=('status', 'updated_at'))
        audit_log(
            actor=request.user,
            action=f'product_modifier_link.{"activate" if value == Status.ACTIVE else "deactivate"}',
            obj=link, company=link.product.company, before=before,
            after=model_snapshot(link, ('status',)),
        )
        return Response(self.get_serializer(link).data)

    @action(detail=False, methods=('post',), url_path='reorder')
    @transaction.atomic
    def reorder(self, request):
        product_id = request.data.get('product')
        link_ids = request.data.get('link_ids')
        branch = request.branch_context
        try:
            product = Product.objects.get(pk=product_id, company_id=branch.company_id)
        except Product.DoesNotExist:
            raise ValidationError({'product': 'Produto fora da empresa atual.'})
        if not isinstance(link_ids, list):
            raise ValidationError({'link_ids': 'Informe uma lista de vínculos.'})
        links = reorder_product_modifier_groups(product=product, link_ids=link_ids)
        reference = str(uuid.uuid4())
        for link in links:
            audit_log(actor=request.user, action='product_modifier_link.reorder', obj=link,
                      company=branch.company, after={'sort_order': link.sort_order},
                      metadata={'operation_reference': reference})
        return Response(self.get_serializer(links, many=True).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def activate(self, request, pk=None):
        return self._status(request, Status.ACTIVE)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def deactivate(self, request, pk=None):
        return self._status(request, Status.INACTIVE)


class ModifierOptionViewSet(CatalogViewSet):
    serializer_class = ModifierOptionSerializer
    http_method_names = ('get', 'post', 'patch', 'head', 'options')
    permission_codes = {
        'list': 'modifiers.view', 'retrieve': 'modifiers.view',
        'create': 'modifiers.change', 'update': 'modifiers.change',
        'partial_update': 'modifiers.change',
        'activate': 'modifiers.change', 'deactivate': 'modifiers.change',
        'reorder': 'modifiers.change',
    }

    def get_queryset(self):
        queryset = ModifierOption.objects.select_related('modifier_group__company')
        branch = getattr(self.request, 'branch_context', None)
        if branch:
            queryset = queryset.filter(modifier_group__company_id=branch.company_id)
        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                modifier_group__company__in=accessible_companies(self.request.user, 'modifiers.view')
            )
        group_id = self.request.query_params.get('modifier_group')
        if group_id:
            queryset = queryset.filter(modifier_group_id=group_id)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        last_order = ModifierOption.objects.filter(
            modifier_group=serializer.validated_data['modifier_group']
        ).aggregate(value=Max('sort_order'))['value']
        option = serializer.save(sort_order=(last_order if last_order is not None else -1) + 1)
        audit_log(
            actor=self.request.user, action='modifier_option.create',
            obj=option, company=option.modifier_group.company,
            after=model_snapshot(option, ('name', 'option_type', 'additional_price', 'sort_order', 'status')),
        )

    @transaction.atomic
    def perform_update(self, serializer):
        fields = ('name', 'option_type', 'additional_price', 'sort_order', 'status')
        before = model_snapshot(serializer.instance, fields)
        option = serializer.save()
        audit_log(
            actor=self.request.user, action='modifier_option.update',
            obj=option, company=option.modifier_group.company,
            before=before, after=model_snapshot(option, fields),
        )

    @action(detail=False, methods=('post',), url_path='reorder')
    @transaction.atomic
    def reorder(self, request):
        group_id = request.data.get('modifier_group')
        option_ids = request.data.get('option_ids')
        branch = request.branch_context
        try:
            group = ModifierGroup.objects.get(pk=group_id, company_id=branch.company_id)
        except ModifierGroup.DoesNotExist:
            raise ValidationError({'modifier_group': 'Grupo fora da empresa atual.'})
        if not isinstance(option_ids, list):
            raise ValidationError({'option_ids': 'Informe uma lista de opções.'})
        options = reorder_modifier_options(group=group, option_ids=option_ids)
        reference = str(uuid.uuid4())
        for option in options:
            audit_log(actor=request.user, action='modifier_option.reorder', obj=option,
                      company=branch.company, after={'sort_order': option.sort_order},
                      metadata={'operation_reference': reference})
        return Response(self.get_serializer(options, many=True).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def activate(self, request, pk=None):
        option = self.get_object()
        option.status = Status.ACTIVE
        option.save(update_fields=('status', 'updated_at'))
        audit_log(actor=request.user, action='modifier_option.activate', obj=option, company=option.modifier_group.company)
        return Response(self.get_serializer(option).data)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def deactivate(self, request, pk=None):
        option = self.get_object()
        option.status = Status.INACTIVE
        option.save(update_fields=('status', 'updated_at'))
        audit_log(actor=request.user, action='modifier_option.deactivate', obj=option, company=option.modifier_group.company)
        return Response(self.get_serializer(option).data)
