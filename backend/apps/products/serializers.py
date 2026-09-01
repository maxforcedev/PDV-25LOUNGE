from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.companies.models import Status
from apps.companies.selectors import user_has_branch_permission, user_has_company_permission
from apps.base.exceptions import DomainValidationError

from .models import (
    BranchProductPrice, Category, ContentUnit, FractionableProductConfig,
    InventoryBehavior, ModifierGroup, ModifierOption, ModifierOptionType,
    Product, ProductBranchConfig, ProductComponent, ProductFractionComponent,
    ProductModifierGroup, ProductProductionDestination, ProductionDestination,
    SalesChannel, Unit, normalize_product_name,
)
from .services import (
    create_product, replace_composition, replace_fraction_composition,
    soft_delete_modifier_option,
)


class CompanyBoundSerializer(serializers.ModelSerializer):
    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch and 'company' in fields:
            fields['company'].queryset = branch.company.__class__.objects.filter(
                pk=branch.company_id
            )
        return fields

    def validate(self, attrs):
        company = attrs.get('company', getattr(self.instance, 'company', None))
        if self.instance and 'company' in attrs and company != self.instance.company:
            raise serializers.ValidationError({'company': 'A empresa nao pode ser alterada.'})
        branch = getattr(self.context['request'], 'branch_context', None)
        if not company or branch and branch.company_id != company.pk:
            raise serializers.ValidationError({'company': 'Empresa fora do contexto autorizado.'})
        return attrs


class CategorySerializer(CompanyBoundSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    product_count = serializers.IntegerField(read_only=True, default=0)
    related_products = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            'id', 'company', 'company_name', 'branch', 'branch_name', 'name', 'description', 'sort_order',
            'available_counter', 'available_table', 'available_command',
            'participates_in_service_fee', 'participates_in_commission',
            'status', 'deleted_at', 'product_count', 'related_products',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company_name', 'branch', 'branch_name', 'sort_order', 'status', 'deleted_at', 'product_count',
            'related_products', 'created_at', 'updated_at',
        )

    def get_related_products(self, obj):
        if getattr(self.context.get('view'), 'action', None) != 'retrieve':
            return []
        return [
            {
                'id': product.id,
                'name': product.name,
                'internal_code': product.internal_code,
                'sale_price': f'{product.sale_price:.2f}',
                'status': product.status,
            }
            for config in obj.branch_product_configs.select_related('product').filter(
                is_available=True,
                product__status=Status.ACTIVE,
                product__archived_at__isnull=True,
            )
            for product in [config.product]
        ]

    def validate_name(self, value):
        value = ' '.join(value.split())
        company_id = self.initial_data.get('company') or getattr(self.instance, 'company_id', None)
        branch = getattr(self.context.get('request'), 'branch_context', None)
        queryset = Category.objects.filter(
            branch=branch, name__iexact=value, deleted_at__isnull=True,
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if company_id and queryset.exists():
            raise serializers.ValidationError('Já existe uma categoria com este nome nesta empresa.')
        if not self.instance and branch:
            archived = Category.objects.filter(
                branch=branch, name__iexact=value, deleted_at__isnull=False,
            ).order_by('-deleted_at', '-id').first()
            if archived:
                raise DomainValidationError(
                    code='archived_category_exists',
                    message='Já existiu uma categoria com este nome nesta filial.',
                    details={
                        'category_id': archived.pk,
                        'name': archived.name,
                        'archived_at': archived.deleted_at.isoformat(),
                    },
                )
        return value


class ProductComponentSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component_product.name', read_only=True)
    component_internal_code = serializers.CharField(
        source='component_product.internal_code', read_only=True
    )
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal('0.001')
    )
    component_unit = serializers.CharField(
        source='component_product.unit', read_only=True
    )
    quantity_display = serializers.SerializerMethodField()

    class Meta:
        model = ProductComponent
        fields = (
            'component_product', 'component_name', 'component_internal_code',
            'component_unit', 'quantity', 'quantity_display',
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['component_product'].queryset = Product.objects.filter(
                company_id=branch.company_id
            )
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        component = attrs.get('component_product')
        quantity = attrs.get('quantity')
        if (
            component
            and component.unit == Unit.UNIT
            and quantity != quantity.to_integral_value()
        ):
            raise serializers.ValidationError(
                {'quantity': 'A quantidade de um componente UN deve ser inteira.'}
            )
        return attrs

    def get_quantity_display(self, obj):
        quantity = format(obj.quantity, 'f').rstrip('0').rstrip('.')
        return f'{quantity} {obj.component_product.unit.upper()}'


class ProductFractionComponentSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component_product.name', read_only=True)
    component_internal_code = serializers.CharField(
        source='component_product.internal_code', read_only=True
    )
    content_unit = serializers.CharField(
        source='component_product.fraction_config.content_unit', read_only=True
    )
    source_fraction_config = serializers.IntegerField(
        source='component_product.fraction_config.pk', read_only=True
    )
    source_package_content = serializers.DecimalField(
        source='component_product.fraction_config.package_content',
        max_digits=24, decimal_places=9, read_only=True,
    )
    source_tracking_active = serializers.BooleanField(
        source='component_product.fraction_config.tracking_active', read_only=True
    )
    content_quantity = serializers.DecimalField(
        max_digits=24, decimal_places=9, min_value=Decimal('0.000000001')
    )

    class Meta:
        model = ProductFractionComponent
        fields = (
            'component_product', 'component_name', 'component_internal_code',
            'content_quantity', 'content_unit', 'source_fraction_config',
            'source_package_content', 'source_tracking_active',
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['component_product'].queryset = Product.objects.filter(
                company_id=branch.company_id
            )
        return fields


class FractionableProductConfigSerializer(serializers.ModelSerializer):
    package_content = serializers.DecimalField(
        max_digits=24, decimal_places=9, min_value=Decimal('0.000000001'),
        required=True, allow_null=True,
    )

    class Meta:
        model = FractionableProductConfig
        fields = (
            'id', 'product', 'package_content', 'content_unit', 'tracking_active',
            'activated_at', 'activated_by', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'tracking_active', 'activated_at', 'activated_by',
            'created_at', 'updated_at',
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['product'].queryset = Product.objects.filter(
                company_id=branch.company_id
            )
        return fields

    def validate(self, attrs):
        if attrs.get('package_content') is None:
            raise serializers.ValidationError({
                'package_content': 'Informe o conteúdo da embalagem para este produto.'
            })
        product = attrs.get('product', getattr(self.instance, 'product', None))
        if product and (
            product.inventory_behavior != InventoryBehavior.DIRECT
            or product.unit != Unit.UNIT
        ):
            raise serializers.ValidationError({
                'product': 'Somente produto DIRECT em UN pode ser fracionavel.'
            })
        return attrs


class ProductBranchConfigSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    effective_channels = serializers.SerializerMethodField()
    effective_sale_price = serializers.SerializerMethodField()
    effective_participation = serializers.SerializerMethodField()

    class Meta:
        model = ProductBranchConfig
        fields = (
            'id', 'product', 'product_name', 'branch', 'branch_name', 'category', 'is_available',
            'available_counter', 'available_table', 'available_command',
            'participates_in_service_fee', 'participates_in_commission',
            'effective_channels', 'effective_participation', 'effective_sale_price',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'product_name', 'branch_name', 'effective_channels',
            'effective_participation', 'effective_sale_price', 'created_at', 'updated_at',
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['product'].queryset = Product.objects.filter(
                company_id=branch.company_id
            )
            fields['branch'].queryset = fields['branch'].queryset.filter(pk=branch.pk)
            fields['category'].queryset = Category.objects.filter(
                branch=branch, deleted_at__isnull=True,
            )
        return fields

    def get_effective_channels(self, config):
        return {
            channel: config.effective_channel(channel)
            for channel in SalesChannel.values
        }

    def get_effective_sale_price(self, config):
        price = BranchProductPrice.objects.filter(
            product=config.product, branch=config.branch
        ).values_list('sale_price', flat=True).first()
        return f'{(config.product.sale_price if price is None else price):.2f}'

    def get_effective_participation(self, config):
        return {
            field: config.effective_participation(field)
            for field in ('participates_in_service_fee', 'participates_in_commission')
        }

    def validate(self, attrs):
        product = attrs.get('product', getattr(self.instance, 'product', None))
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        context_branch = getattr(self.context.get('request'), 'branch_context', None)
        if product and branch and product.company_id != branch.company_id:
            raise serializers.ValidationError({'branch': 'Filial fora da empresa do produto.'})
        if context_branch and branch and context_branch.pk != branch.pk:
            raise serializers.ValidationError({'branch': 'Selecione a filial ativa.'})
        category = attrs.get('category', getattr(self.instance, 'category', None))
        if not self.instance and category is None:
            raise serializers.ValidationError({'category': 'Informe a categoria operacional da filial.'})
        if category and branch and category.branch_id != branch.pk:
            raise serializers.ValidationError({'category': 'A categoria deve pertencer a filial ativa.'})
        return attrs


class ProductionDestinationSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = ProductionDestination
        fields = (
            'id', 'branch', 'branch_name', 'name', 'code', 'status',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'branch_name', 'status', 'created_at', 'updated_at')

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['branch'].queryset = fields['branch'].queryset.filter(pk=branch.pk)
        return fields

    def validate(self, attrs):
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        context_branch = getattr(self.context.get('request'), 'branch_context', None)
        if context_branch and branch and context_branch.pk != branch.pk:
            raise serializers.ValidationError({'branch': 'Selecione a filial ativa.'})
        return attrs


class ProductSerializer(CompanyBoundSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    components = ProductComponentSerializer(many=True, required=False)
    fraction_components = ProductFractionComponentSerializer(many=True, required=False)
    internal_code = serializers.CharField(
        allow_blank=True, required=False, max_length=100
    )
    suggested_cost = serializers.SerializerMethodField()
    suggested_sale_price = serializers.SerializerMethodField()
    branch_configuration = serializers.SerializerMethodField()
    branch_stock = serializers.SerializerMethodField()
    fraction_config = serializers.SerializerMethodField()
    production_destinations = serializers.SerializerMethodField()
    purchase_presentations = serializers.SerializerMethodField()
    suppliers = serializers.SerializerMethodField()
    cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.00')
    )
    sale_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.00')
    )
    class Meta:
        model = Product
        fields = (
            'id', 'company', 'company_name', 'category', 'category_name', 'name',
            'description', 'internal_code', 'barcode', 'unit', 'cost', 'sale_price',
            'sku',
            'image', 'is_sellable', 'is_favorite', 'inventory_behavior', 'status',
            'archived_at', 'archived_by',
            'available_counter', 'available_table', 'available_command',
            'participates_in_service_fee', 'participates_in_commission',
            'emits_ticket',
            'components', 'fraction_components', 'suggested_cost', 'suggested_sale_price',
            'branch_configuration', 'branch_stock', 'fraction_config',
            'production_destinations', 'purchase_presentations', 'suppliers',
            'created_at', 'updated_at',
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch and 'category' in fields:
            fields['category'].queryset = Category.objects.filter(branch=branch)
        can_view_costs = bool(
            request and (
                request.user.is_superuser
                or branch and user_has_branch_permission(
                    request.user, branch.pk, 'inventory.view_stock_costs'
                )
            )
        )
        if not can_view_costs:
            fields.pop('cost', None)
            fields.pop('suggested_cost', None)
        if getattr(self.context.get('view'), 'action', None) != 'retrieve':
            for field in (
                'branch_configuration', 'fraction_config',
                'production_destinations', 'suppliers',
            ):
                fields.pop(field, None)
        elif not (
            request and (
                request.user.is_superuser
                or user_has_company_permission(request.user, obj_company_id(self.instance), 'suppliers.view')
            )
        ):
            fields.pop('suppliers', None)
        return fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        branch = getattr(self.context.get('request'), 'branch_context', None)
        if branch:
            configs = getattr(instance, '_prefetched_objects_cache', {}).get('branch_configs', ())
            config = next((item for item in configs if item.branch_id == branch.pk), None)
            if config is None:
                config = ProductBranchConfig.objects.filter(
                    product=instance, branch=branch
                ).select_related('category').first()
            if config and config.category_id:
                data['category'] = config.category_id
                data['category_name'] = config.category.name
            if config:
                for channel in SalesChannel.values:
                    data[f'available_{channel}'] = config.effective_channel(channel)
                for field in (
                    'participates_in_service_fee', 'participates_in_commission',
                ):
                    data[field] = config.effective_participation(field)
        return data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        company = attrs.get('company', getattr(self.instance, 'company', None))
        category = attrs.get('category', getattr(self.instance, 'category', None))
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if category and (
            category.company_id != company.id
            or branch and category.branch_id != branch.pk
            or category.deleted_at is not None
        ):
            raise serializers.ValidationError({'category': 'A categoria deve pertencer a filial ativa.'})
        name, normalized_name = normalize_product_name(
            attrs.get('name', getattr(self.instance, 'name', ''))
        )
        attrs['name'] = name
        duplicate_name = Product.objects.filter(
            company=company, normalized_name=normalized_name, archived_at__isnull=True,
        )
        if self.instance:
            duplicate_name = duplicate_name.exclude(pk=self.instance.pk)
        if duplicate_name.exists():
            raise serializers.ValidationError(
                {'name': 'Já existe um produto com este nome nesta empresa.'}
            )
        if not self.instance:
            archived = Product.objects.filter(
                company=company,
                normalized_name=normalized_name,
                archived_at__isnull=False,
            ).order_by('-archived_at', '-id').first()
            if archived:
                raise DomainValidationError(
                    code='archived_product_exists',
                    message='Já existiu um produto com este nome.',
                    details={
                        'product_id': archived.pk,
                        'name': archived.name,
                        'archived_at': archived.archived_at.isoformat(),
                    },
                )
        code = attrs.get('internal_code', getattr(self.instance, 'internal_code', '')).strip()
        if code:
            same_code = Product.objects.filter(
                company=company, internal_code__iexact=code, archived_at__isnull=True,
            )
            if self.instance:
                same_code = same_code.exclude(pk=self.instance.pk)
            if same_code.exists():
                raise serializers.ValidationError({'internal_code': 'Já existe um produto com este código nesta empresa.'})
        barcode = (attrs.get('barcode', getattr(self.instance, 'barcode', '')) or '').strip()
        if barcode:
            same_barcode = Product.objects.filter(
                company=company, barcode__iexact=barcode, archived_at__isnull=True,
            )
            if self.instance:
                same_barcode = same_barcode.exclude(pk=self.instance.pk)
            if same_barcode.exists():
                raise serializers.ValidationError({'barcode': 'Já existe um produto com este código de barras nesta empresa.'})
        sku = (attrs.get('sku', getattr(self.instance, 'sku', '')) or '').strip()
        if sku:
            same_sku = Product.objects.filter(
                company=company, sku__iexact=sku, archived_at__isnull=True,
            )
            if self.instance:
                same_sku = same_sku.exclude(pk=self.instance.pk)
            if same_sku.exists():
                raise serializers.ValidationError({'sku': 'Ja existe um produto com este SKU nesta empresa.'})
        attrs['sku'] = sku or None
        behavior = attrs.get(
            'inventory_behavior',
            getattr(self.instance, 'inventory_behavior', InventoryBehavior.DIRECT),
        )
        if self.instance and behavior != self.instance.inventory_behavior:
            raise serializers.ValidationError({
                'inventory_behavior': 'O comportamento de estoque nao pode ser alterado.'
            })
        sellable = attrs.get('is_sellable', getattr(self.instance, 'is_sellable', True))
        components = attrs.get('components')
        fraction_components = attrs.get('fraction_components')
        if components is not None:
            request = self.context.get('request')
            branch = getattr(request, 'branch_context', None) if request else None
            if request and not request.user.is_superuser and not (
                branch and user_has_branch_permission(
                    request.user, branch.pk, 'products.configure_composition'
                )
            ):
                raise serializers.ValidationError(
                    {'components': 'Você não possui permissão para configurar a composição.'}
                )
            if behavior != InventoryBehavior.COMPONENTS:
                raise serializers.ValidationError(
                    {'components': 'Somente produtos com baixa por componentes possuem composição.'}
                )
            self._validate_components(components, company)
        if fraction_components is not None:
            request = self.context.get('request')
            branch = getattr(request, 'branch_context', None) if request else None
            if request and not request.user.is_superuser and not (
                branch and user_has_branch_permission(
                    request.user, branch.pk, 'products.configure_composition'
                )
            ):
                raise serializers.ValidationError({
                    'fraction_components': 'Voce nao possui permissao para configurar a composicao.'
                })
            if behavior != InventoryBehavior.COMPONENTS:
                raise serializers.ValidationError({
                    'fraction_components': 'Somente produtos compostos possuem consumo fracionado.'
                })
            self._validate_fraction_components(
                fraction_components, company, require_active=sellable
            )
        if components is not None and fraction_components is not None:
            repeated = (
                {item['component_product'].pk for item in components}
                & {item['component_product'].pk for item in fraction_components}
            )
            if repeated:
                raise serializers.ValidationError({
                    'fraction_components': 'Use apenas um modo de consumo para cada componente.'
                })
        if behavior == InventoryBehavior.COMPONENTS and sellable:
            has_components = (
                bool(components) if components is not None
                else bool(self.instance and self.instance.components.exists())
            ) or (
                bool(fraction_components) if fraction_components is not None
                else bool(self.instance and self.instance.fraction_components.exists())
            )
            if not has_components:
                raise serializers.ValidationError(
                    {'is_sellable': 'Informe a composição antes de habilitar a venda.'}
                )
        if self.instance and behavior != InventoryBehavior.COMPONENTS:
            if self.instance.components.exists():
                raise serializers.ValidationError(
                    {'inventory_behavior': 'Remova a composição antes de alterar o comportamento.'}
                )
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch and not request.user.is_superuser:
            current_cost = self.instance.cost if self.instance else Decimal('0.00')
            current_price = self.instance.sale_price if self.instance else Decimal('0.00')
            if 'cost' in attrs and attrs['cost'] != current_cost and not user_has_branch_permission(
                request.user, branch.pk, 'products.change_cost'
            ):
                raise serializers.ValidationError({'cost': 'Você não possui permissão para alterar custos.'})
            if 'sale_price' in attrs and attrs['sale_price'] != current_price and not user_has_branch_permission(
                request.user, branch.pk, 'products.change_price'
            ):
                raise serializers.ValidationError({'sale_price': 'Você não possui permissão para alterar o preço padrão.'})
        return attrs

    def _validate_fraction_components(self, components, company, *, require_active):
        seen = set()
        errors = {}
        for index, item in enumerate(components):
            component = item['component_product']
            item_errors = {}
            if component.pk in seen:
                item_errors['component_product'] = ['Nao repita produtos.']
            seen.add(component.pk)
            if component.company_id != company.pk:
                item_errors['component_product'] = ['O componente deve pertencer a empresa.']
            if component.inventory_behavior != InventoryBehavior.DIRECT:
                item_errors['component_product'] = ['O componente deve possuir estoque proprio.']
            try:
                config = component.fraction_config
            except FractionableProductConfig.DoesNotExist:
                config = None
                item_errors['component_product'] = ['O componente deve ser fracionavel.']
            if require_active and component.status != Status.ACTIVE:
                item_errors['component_product'] = ['A fonte fracionada deve estar ativa.']
            if require_active and config and not config.tracking_active:
                item_errors['component_product'] = [
                    'Ative o rastreamento da fonte fracionada antes da venda.'
                ]
            if item_errors:
                errors[index] = item_errors
        if errors:
            raise serializers.ValidationError({'fraction_components': errors})

    def _validate_components(self, components, company):
        errors = {}
        seen = set()
        for index, item in enumerate(components):
            component = item['component_product']
            item_errors = {}
            if component.pk in seen:
                item_errors['component_product'] = ['Não repita produtos na composição.']
            seen.add(component.pk)
            if self.instance and component.pk == self.instance.pk:
                item_errors['component_product'] = ['Um produto nao pode compor a si mesmo.']
            if component.company_id != company.pk:
                item_errors['component_product'] = ['O componente deve pertencer a mesma empresa.']
            if component.inventory_behavior != InventoryBehavior.DIRECT:
                item_errors['component_product'] = [
                    'Somente produtos com estoque próprio podem ser componentes.'
                ]
            if component.unit == Unit.UNIT and item['quantity'] != item['quantity'].to_integral_value():
                item_errors['quantity'] = ['A quantidade de um componente UN deve ser inteira.']
            if item_errors:
                errors[index] = item_errors
        if errors:
            raise serializers.ValidationError({'components': errors})

    def validate_internal_code(self, value):
        value = value.strip()
        if self.instance and not value:
            return self.instance.internal_code
        return value

    def create(self, validated_data):
        components = validated_data.pop('components', None)
        fraction_components = validated_data.pop('fraction_components', None)
        try:
            return create_product(
                branch=getattr(self.context.get('request'), 'branch_context', None),
                components=components,
                fraction_components=fraction_components,
                **validated_data,
            )
        except DjangoValidationError as error:
            detail = getattr(error, 'message_dict', {'non_field_errors': error.messages})
            raise serializers.ValidationError(detail)

    @transaction.atomic
    def update(self, instance, validated_data):
        instance.company.__class__.objects.select_for_update().get(pk=instance.company_id)
        components = validated_data.pop('components', None)
        fraction_components = validated_data.pop('fraction_components', None)
        category = validated_data.pop('category', None)
        branch_fields = (
            'available_counter', 'available_table', 'available_command',
            'participates_in_service_fee', 'participates_in_commission',
        )
        branch = getattr(self.context.get('request'), 'branch_context', None)
        branch_values = {}
        if branch:
            branch_values = {
                field: validated_data.pop(field)
                for field in branch_fields if field in validated_data
            }
        if not validated_data.get('internal_code', instance.internal_code):
            validated_data.pop('internal_code', None)
        desired_sellable = validated_data.get('is_sellable', instance.is_sellable)
        if (components is not None or fraction_components is not None) and desired_sellable:
            validated_data['is_sellable'] = False
        try:
            instance = super().update(instance, validated_data)
            if category is not None or branch_values:
                config = ProductBranchConfig.objects.select_for_update().get(
                    product=instance, branch=branch
                )
                update_fields = list(branch_values)
                for field, value in branch_values.items():
                    setattr(config, field, value)
                if category is not None:
                    config.category = category
                    update_fields.append('category')
                config.save(update_fields=(*update_fields, 'updated_at'))
            if components is not None and fraction_components is not None:
                for row in ProductFractionComponent.objects.filter(parent_product=instance):
                    row.delete()
            if components is not None:
                instance = replace_composition(product=instance, components=components)
            if fraction_components is not None:
                instance = replace_fraction_composition(
                    product=instance, components=fraction_components
                )
            if components is not None or fraction_components is not None:
                if desired_sellable:
                    instance.is_sellable = True
                    instance.save(update_fields=('is_sellable', 'updated_at'))
            return instance
        except DjangoValidationError as error:
            detail = getattr(error, 'message_dict', {'non_field_errors': error.messages})
            raise serializers.ValidationError(detail)

    def get_suggested_cost(self, obj):
        if obj.inventory_behavior != InventoryBehavior.COMPONENTS:
            return None
        from apps.inventory.content import (
            exact_content_equivalent, exact_multiply, exact_sum,
        )

        contributions = [
            exact_multiply(item.component_product.cost, item.quantity)
            for item in obj.components.all()
        ]
        for item in obj.fraction_components.select_related(
            'component_product__fraction_config'
        ):
            config = self._valid_fraction_config(item.component_product)
            if config:
                contributions.append(exact_multiply(
                    item.component_product.cost,
                    exact_content_equivalent(item.content_quantity, config.package_content),
                ))
        value = exact_sum(contributions)
        value = value.quantize(Decimal('0.01'))
        return f'{value:.2f}'

    def get_suggested_sale_price(self, obj):
        if obj.inventory_behavior != InventoryBehavior.COMPONENTS:
            return None
        from apps.inventory.content import (
            exact_content_equivalent, exact_multiply, exact_sum,
        )

        contributions = [
            exact_multiply(item.component_product.sale_price, item.quantity)
            for item in obj.components.all()
        ]
        for item in obj.fraction_components.select_related(
            'component_product__fraction_config'
        ):
            config = self._valid_fraction_config(item.component_product)
            if config:
                contributions.append(exact_multiply(
                    item.component_product.sale_price,
                    exact_content_equivalent(item.content_quantity, config.package_content),
                ))
        value = exact_sum(contributions)
        value = value.quantize(Decimal('0.01'))
        return f'{value:.2f}'

    def validate_barcode(self, value):
        return (value or '').strip()

    def get_branch_configuration(self, product):
        branch = getattr(self.context.get('request'), 'branch_context', None)
        if not branch or branch.status != Status.ACTIVE:
            return None
        config = ProductBranchConfig.objects.filter(product=product, branch=branch).first()
        branch_price = BranchProductPrice.objects.filter(
            product=product, branch=branch
        ).values_list('sale_price', flat=True).first()
        return {
            'branch': branch.pk,
            'is_available': config.is_available if config else False,
            'channels': {
                channel: (
                    config.effective_channel(channel) if config
                    else getattr(product, f'available_{channel}')
                )
                for channel in SalesChannel.values
            },
            'sale_price': f'{(product.sale_price if branch_price is None else branch_price):.2f}',
            'participation': {
                field: (
                    config.effective_participation(field) if config
                    else getattr(product, field)
                )
                for field in (
                    'participates_in_service_fee', 'participates_in_commission',
                )
            },
        }

    @staticmethod
    def _valid_fraction_config(product):
        try:
            config = product.fraction_config
        except FractionableProductConfig.DoesNotExist:
            return None
        if config.package_content is None or config.package_content <= 0:
            return None
        return config

    def get_branch_stock(self, product):
        from apps.inventory.content import (
            content_breakdown, exact_content_equivalent, exact_multiply,
        )
        from apps.inventory.materialization import expected_fractional_content

        branch = getattr(self.context.get('request'), 'branch_context', None)
        if not branch or branch.status != Status.ACTIVE:
            return None
        if product.inventory_behavior == InventoryBehavior.NONE:
            return {'applicable': False, 'semantic': 'not_applicable'}
        from apps.inventory.models import Stock

        if product.inventory_behavior == InventoryBehavior.DIRECT:
            stock = Stock.objects.filter(product=product, branch=branch).first()
            result = {
                'applicable': True,
                'semantic': 'actual',
                'stock_id': stock.pk if stock else None,
                'current_quantity': format(stock.current_quantity if stock else Decimal('0'), 'f'),
                'minimum_quantity': format(stock.minimum_quantity if stock else Decimal('0'), 'f'),
                'unit': product.unit,
            }
            config = self._valid_fraction_config(product)
            if config and config.tracking_active:
                current_content = (
                    stock.current_content
                    if stock and stock.current_content is not None
                    else expected_fractional_content(
                        product, stock.current_quantity if stock else Decimal('0')
                    )
                )
                complete, residual = content_breakdown(
                    current_content,
                    config.package_content,
                )
                result.update({
                    'current_content': format(current_content, 'f'),
                    'content_unit': config.content_unit,
                    'package_content': format(config.package_content, 'f'),
                    'equivalent_quantity': format(
                        exact_content_equivalent(current_content, config.package_content), 'f'
                    ),
                    'complete_packages': format(complete, 'f'),
                    'residual_content': format(residual, 'f'),
                })
            if self._can_view_costs(branch):
                cost = (
                    stock.average_unit_cost
                    if stock and stock.average_unit_cost is not None else product.cost
                )
                result['unit_cost'] = f'{cost:.12f}'
            return result
        capacities = []
        cost_contributions = []
        for component in product.components.select_related('component_product'):
            stock = Stock.objects.filter(
                product=component.component_product, branch=branch
            ).first()
            available = stock.current_quantity if stock else Decimal('0')
            capacities.append(available / component.quantity)
            if self._can_view_costs(branch):
                unit_cost = (
                    stock.average_unit_cost
                    if stock and stock.average_unit_cost is not None
                    else component.component_product.cost
                )
                cost_contributions.append(exact_multiply(
                    unit_cost, component.quantity
                ))
        for component in product.fraction_components.select_related(
            'component_product__fraction_config'
        ):
            config = self._valid_fraction_config(component.component_product)
            if not config:
                continue
            stock = Stock.objects.filter(
                product=component.component_product, branch=branch
            ).first()
            available = stock.current_content if stock and stock.current_content else Decimal('0')
            capacities.append(available / component.content_quantity)
            if self._can_view_costs(branch):
                unit_cost = (
                    stock.average_unit_cost
                    if stock and stock.average_unit_cost is not None
                    else component.component_product.cost
                )
                cost_contributions.append(exact_multiply(
                    unit_cost,
                    exact_content_equivalent(
                        component.content_quantity, config.package_content
                    ),
                ))
        result = {
            'applicable': True,
            'semantic': 'components',
            'current_quantity': format(min(capacities) if capacities else Decimal('0'), 'f'),
            'unit': product.unit,
        }
        if self._can_view_costs(branch):
            from apps.inventory.content import exact_sum

            result['unit_cost'] = f'{exact_sum(cost_contributions):.12f}'
        return result

    def _can_view_costs(self, branch):
        request = self.context.get('request')
        return bool(request and (
            request.user.is_superuser
            or user_has_branch_permission(request.user, branch.pk, 'inventory.view_stock_costs')
        ))

    def get_fraction_config(self, product):
        try:
            return FractionableProductConfigSerializer(product.fraction_config).data
        except FractionableProductConfig.DoesNotExist:
            return None

    def get_production_destinations(self, product):
        branch = getattr(self.context.get('request'), 'branch_context', None)
        if not branch:
            return []
        destinations = ProductionDestination.objects.filter(
            branch=branch, product_links__product=product
        ).order_by('name', 'id')
        return ProductionDestinationSerializer(destinations, many=True).data

    def get_purchase_presentations(self, product):
        return [
            {
                'id': presentation.pk,
                'company': presentation.company_id,
                'product': presentation.product_id,
                'unit_code': presentation.unit_code,
                'description': presentation.description,
                'conversion_factor': format(presentation.conversion_factor, 'f'),
                'status': presentation.status,
                'created_at': presentation.created_at,
                'updated_at': presentation.updated_at,
            }
            for presentation in product.purchase_presentations.all()
        ]

    def get_suppliers(self, product):
        return [
            {
                'id': relation.pk,
                'supplier': relation.supplier_id,
                'supplier_name': relation.supplier.trade_name,
                'supplier_code': relation.supplier_code,
                'is_preferred': relation.is_preferred,
                'is_exclusive': relation.is_exclusive,
                'status': relation.status,
                'units': [
                    {
                        'id': unit.pk,
                        'purchase_presentation': unit.purchase_presentation_id,
                        'unit_code': unit.unit_code,
                        'description': unit.description,
                        'conversion_factor': format(unit.conversion_factor, 'f'),
                        'barcode': unit.barcode,
                        'is_default': unit.is_default,
                        'status': unit.status,
                        'presentation_preset': unit.presentation_preset_id,
                        'presentation_preset_code': (
                            unit.presentation_preset.code if unit.presentation_preset_id else ''
                        ),
                        'presentation_preset_name': (
                            unit.presentation_preset.description if unit.presentation_preset_id else ''
                        ),
                        'presentation_type': (
                            unit.presentation_preset.presentation_type
                            if unit.presentation_preset_id else None
                        ),
                    }
                    for unit in relation.units.all()
                ],
            }
            for relation in product.product_suppliers.select_related('supplier').prefetch_related('units')
        ]


def obj_company_id(instance):
    return getattr(instance, 'company_id', None)


class CompositionSerializer(serializers.Serializer):
    components = ProductComponentSerializer(many=True, required=False, default=list)
    fraction_components = ProductFractionComponentSerializer(
        many=True, required=False, default=list
    )

    def validate_components(self, value):
        product = self.context['product']
        user = self.context['request'].user
        seen = set()
        errors = {}
        for index, item in enumerate(value):
            component = item['component_product']
            item_errors = {}
            if component.pk in seen:
                item_errors['component_product'] = ['Não repita produtos na composição.']
            seen.add(component.pk)
            if component.company_id != product.company_id:
                item_errors['component_product'] = ['O componente deve pertencer a mesma empresa.']
            branch = getattr(self.context['request'], 'branch_context', None)
            if branch and branch.company_id != component.company_id:
                item_errors['component_product'] = ['Componente fora do contexto autorizado.']
            if component.inventory_behavior != InventoryBehavior.DIRECT:
                item_errors['component_product'] = ['Somente produtos com estoque próprio podem ser componentes.']
            if component.pk == product.pk:
                item_errors['component_product'] = ['Um produto nao pode compor a si mesmo.']
            if component.unit == Unit.UNIT and item['quantity'] != item['quantity'].to_integral_value():
                item_errors['quantity'] = ['A quantidade de um componente UN deve ser inteira.']
            if item_errors:
                errors[index] = item_errors
        if errors:
            raise serializers.ValidationError(errors)
        if product.is_sellable and not value and not self.initial_data.get('fraction_components'):
            raise serializers.ValidationError(
                'Um produto composto vendável deve possuir componentes.'
            )
        return value

    def validate_fraction_components(self, value):
        product = self.context['product']
        seen = set()
        for item in value:
            component = item['component_product']
            if component.pk in seen:
                raise serializers.ValidationError('Nao repita produtos na composicao.')
            seen.add(component.pk)
            if component.company_id != product.company_id:
                raise serializers.ValidationError('O componente deve pertencer a mesma empresa.')
            if component.inventory_behavior != InventoryBehavior.DIRECT:
                raise serializers.ValidationError('O componente deve possuir estoque proprio.')
            try:
                config = component.fraction_config
            except FractionableProductConfig.DoesNotExist:
                raise serializers.ValidationError('O componente deve ser fracionavel.')
            if product.is_sellable and component.status != Status.ACTIVE:
                raise serializers.ValidationError('A fonte fracionada deve estar ativa.')
            if product.is_sellable and not config.tracking_active:
                raise serializers.ValidationError(
                    'Ative o rastreamento da fonte fracionada antes da venda.'
                )
        return value

    def validate(self, attrs):
        normal = {item['component_product'].pk for item in attrs['components']}
        fractional = {item['component_product'].pk for item in attrs['fraction_components']}
        if normal & fractional:
            raise serializers.ValidationError(
                'Use apenas um modo de consumo para cada componente.'
            )
        if self.context['product'].is_sellable and not normal and not fractional:
            raise serializers.ValidationError('Um produto composto vendavel deve possuir componentes.')
        return attrs

    def save(self, **kwargs):
        try:
            for row in ProductFractionComponent.objects.filter(
                parent_product=self.context['product']
            ):
                row.delete()
            product = replace_composition(
                product=self.context['product'], components=self.validated_data['components']
            )
            return replace_fraction_composition(
                product=product,
                components=self.validated_data['fraction_components'],
            )
        except DjangoValidationError as error:
            detail = getattr(error, 'message_dict', {'non_field_errors': error.messages})
            raise serializers.ValidationError(detail)


class BranchProductPriceSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    internal_code = serializers.CharField(source='product.internal_code', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    default_price = serializers.DecimalField(
        source='product.sale_price', max_digits=12, decimal_places=2, read_only=True,
        coerce_to_string=True,
    )
    sale_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.00'), coerce_to_string=True
    )

    class Meta:
        model = BranchProductPrice
        fields = (
            'id', 'product', 'product_name', 'internal_code', 'branch', 'branch_name',
            'default_price', 'sale_price', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'product_name', 'internal_code', 'branch_name', 'default_price', 'created_at', 'updated_at')

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['product'].queryset = Product.objects.filter(
                company_id=branch.company_id
            )
            fields['branch'].queryset = fields['branch'].queryset.filter(
                company_id=branch.company_id
            )
        return fields

    def validate(self, attrs):
        product = attrs.get('product', getattr(self.instance, 'product', None))
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        request = self.context.get('request')
        context_branch = getattr(request, 'branch_context', None) if request else None
        if context_branch and product and product.company_id != context_branch.company_id:
            raise serializers.ValidationError({'product': 'Produto fora do contexto autorizado.'})
        if context_branch and branch:
            if branch.company_id != context_branch.company_id:
                raise serializers.ValidationError({'branch': 'Filial fora da empresa atual.'})
            if (
                branch.pk != context_branch.pk
                and not request.user.is_superuser
                and not user_has_company_permission(
                    request.user, context_branch.company_id, 'branch_prices.change_company'
                )
            ):
                raise serializers.ValidationError({
                    'branch': 'Você não possui permissão para alterar preços de outra filial.'
                })
        if product and branch and product.company_id != branch.company_id:
            raise serializers.ValidationError({'branch': 'A filial deve pertencer a empresa do produto.'})
        if product and (
            product.status != Status.ACTIVE or product.archived_at is not None
        ):
            raise serializers.ValidationError({'product': 'O produto não está ativo para precificação.'})
        if product and branch and not ProductBranchConfig.objects.filter(
            product=product, branch=branch, is_available=True,
        ).exists():
            raise serializers.ValidationError({
                'product': 'O produto não está disponível nesta filial.'
            })
        return attrs


class DuplicateProductSerializer(serializers.Serializer):
    composition = serializers.BooleanField(default=False)
    fraction = serializers.BooleanField(default=False)
    branch_config = serializers.BooleanField(default=False)
    destinations = serializers.BooleanField(default=False)
    suppliers = serializers.BooleanField(default=False)


class CopyBranchConfigurationSerializer(serializers.Serializer):
    source_branch = serializers.IntegerField(min_value=1)
    target_branches = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=100
    )

    def validate_target_branches(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError('Nao repita filiais de destino.')
        return value


class CopyCategoryConfigurationSerializer(CopyBranchConfigurationSerializer):
    category = serializers.IntegerField(min_value=1)


class ProductDestinationsSerializer(serializers.Serializer):
    destinations = serializers.PrimaryKeyRelatedField(
        queryset=ProductionDestination.objects.all(), many=True
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['destinations'].child_relation.queryset = (
                ProductionDestination.objects.filter(branch=branch)
            )
        return fields


class ProductPrintersSerializer(serializers.Serializer):
    printers = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True,
    )

    def validate_printers(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError('Não repita impressoras.')
        return value


class ModifierOptionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, min_value=1)
    stock_product_name = serializers.CharField(source='stock_product.name', read_only=True)
    class Meta:
        model = ModifierOption
        fields = (
            'id', 'modifier_group', 'name', 'option_type', 'additional_price',
            'stock_product', 'stock_product_name',
            'sort_order', 'status', 'created_at', 'updated_at',
        )
        read_only_fields = ('status', 'created_at', 'updated_at')

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['modifier_group'].queryset = ModifierGroup.objects.filter(
                branch=branch
            )
            fields['stock_product'].queryset = Product.objects.filter(
                company_id=branch.company_id, branch_configs__branch=branch
            )
        return fields

    def validate_name(self, value):
        return ' '.join((value or '').split())

    def validate(self, attrs):
        if 'id' in attrs and not isinstance(self.parent, serializers.ListSerializer):
            raise serializers.ValidationError({'id': 'ID aceito apenas na edição do grupo.'})
        if not self.instance and attrs.get('option_type') == ModifierOptionType.TEXT:
            raise serializers.ValidationError({
                'option_type': 'Use Adicionar sem estoque para novas opções sem produto.'
            })
        request = self.context.get('request')
        group = attrs.get('modifier_group', getattr(self.instance, 'modifier_group', None))
        if request and group and not request.user.is_superuser:
            branch = getattr(request, 'branch_context', None)
            if not branch or group.branch_id != branch.pk:
                raise serializers.ValidationError({
                    'modifier_group': 'O grupo modificador deve pertencer à filial atual.'
                })
        return attrs


class ModifierGroupSerializer(serializers.ModelSerializer):
    options = ModifierOptionSerializer(many=True, required=False)

    class Meta:
        model = ModifierGroup
        fields = (
            'id', 'company', 'name', 'is_required', 'min_selections',
            'max_selections', 'allow_option_quantity', 'min_total_quantity',
            'max_total_quantity', 'branch', 'substitution_component',
            'inherit_component_quantity', 'sort_order',
            'status', 'options', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'branch', 'status', 'created_at', 'updated_at')

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['company'].queryset = branch.company.__class__.objects.filter(
                pk=branch.company_id
            )
            fields['substitution_component'].queryset = Product.objects.filter(
                company_id=branch.company_id, branch_configs__branch=branch
            )
        return fields

    def validate_name(self, value):
        return ' '.join((value or '').split())

    def validate(self, attrs):
        request = self.context.get('request')
        company = attrs.get('company', getattr(self.instance, 'company', None))
        if self.instance and 'company' in attrs and company != self.instance.company:
            raise serializers.ValidationError({'company': 'A empresa não pode ser alterada.'})
        if request and not request.user.is_superuser:
            branch_context = getattr(request, 'branch_context', None)
            if branch_context and company and company.pk != branch_context.company_id:
                raise serializers.ValidationError({'company': 'A empresa deve corresponder à filial atual.'})
            from apps.companies.selectors import user_has_company_permission
            if company and not user_has_company_permission(request.user, company.pk, 'modifiers.change'):
                raise serializers.ValidationError({'company': 'Você não possui permissão nesta empresa.'})
        min_sel = attrs.get('min_selections', getattr(self.instance, 'min_selections', 0))
        max_sel = attrs.get('max_selections', getattr(self.instance, 'max_selections', None))
        is_req = attrs.get('is_required', getattr(self.instance, 'is_required', False))
        allow_qty = attrs.get('allow_option_quantity', getattr(self.instance, 'allow_option_quantity', False))
        min_total = attrs.get(
            'min_total_quantity', getattr(self.instance, 'min_total_quantity', Decimal('0'))
        )
        max_total = attrs.get(
            'max_total_quantity', getattr(self.instance, 'max_total_quantity', None)
        )
        if max_sel is not None and min_sel and min_sel > max_sel:
            raise serializers.ValidationError({'max_selections': 'O máximo não pode ser menor que o mínimo.'})
        if is_req and min_sel < 1:
            raise serializers.ValidationError({'min_selections': 'Grupo obrigatório exige mínimo de 1.'})
        if max_total is not None and min_total and min_total > max_total:
            raise serializers.ValidationError({
                'max_total_quantity': 'O máximo total não pode ser menor que o mínimo total.'
            })
        if not allow_qty and (min_total or max_total is not None):
            raise serializers.ValidationError({
                'allow_option_quantity': (
                    'Limites de quantidade total exigem quantidade por opção habilitada.'
                )
            })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        options = validated_data.pop('options', None)
        group = ModifierGroup.objects.create(**validated_data)
        if options:
            for option_data in options:
                ModifierOption.objects.create(modifier_group=group, **option_data)
        return group

    @transaction.atomic
    def update(self, instance, validated_data):
        options = validated_data.pop('options', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if options is not None:
            requested_ids = {
                option_data['id'] for option_data in options if option_data.get('id')
            }
            existing_options = {
                option.pk: option for option in instance.options.select_for_update()
            }
            if not requested_ids.issubset(existing_options):
                raise serializers.ValidationError({
                    'options': 'Uma opção não pertence a este grupo ou foi excluída.'
                })
            request = self.context.get('request')
            user = request.user if request else None
            for option_id in set(existing_options) - requested_ids:
                soft_delete_modifier_option(
                    option=existing_options[option_id], user=user,
                )
            for option_data in options:
                option_id = option_data.pop('id', None)
                if option_id:
                    option = existing_options[option_id]
                    for key, value in option_data.items():
                        if key != 'modifier_group':
                            setattr(option, key, value)
                    option.save()
                else:
                    option_data.pop('modifier_group', None)
                    ModifierOption.objects.create(modifier_group=instance, **option_data)
        return instance


class ProductModifierGroupSerializer(serializers.ModelSerializer):
    modifier_group_name = serializers.CharField(source='modifier_group.name', read_only=True)

    class Meta:
        model = ProductModifierGroup
        fields = (
            'id', 'product', 'modifier_group', 'modifier_group_name',
            'sort_order', 'status', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'status', 'created_at', 'updated_at')

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            fields['product'].queryset = Product.objects.filter(
                company_id=branch.company_id, branch_configs__branch=branch
            )
            fields['modifier_group'].queryset = ModifierGroup.objects.filter(
                branch=branch
            )
        return fields

    def validate(self, attrs):
        request = self.context.get('request')
        product = attrs.get('product', getattr(self.instance, 'product', None))
        modifier_group = attrs.get('modifier_group', getattr(self.instance, 'modifier_group', None))
        if request and not request.user.is_superuser:
            branch_context = getattr(request, 'branch_context', None)
            company_id = branch_context.company_id if branch_context else None
            if product and company_id and product.company_id != company_id:
                raise serializers.ValidationError({'product': 'O produto deve pertencer à empresa da filial atual.'})
            if modifier_group and company_id and modifier_group.company_id != company_id:
                raise serializers.ValidationError({'modifier_group': 'O grupo modificador deve pertencer à empresa da filial atual.'})
            if modifier_group and branch_context and modifier_group.branch_id != branch_context.pk:
                raise serializers.ValidationError({'modifier_group': 'O grupo deve pertencer à filial atual.'})
            if product and modifier_group and product.company_id != modifier_group.company_id:
                raise serializers.ValidationError({'modifier_group': 'Produto e grupo modificador devem pertencer à mesma empresa.'})
        return attrs
