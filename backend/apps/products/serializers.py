from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.companies.selectors import user_has_branch_permission

from .models import (
    BranchProductPrice, Category, InventoryBehavior, Product, ProductComponent, Unit,
    normalize_product_name,
)
from .services import create_product, replace_composition


class CompanyBoundSerializer(serializers.ModelSerializer):
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
    product_count = serializers.IntegerField(read_only=True, default=0)
    related_products = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            'id', 'company', 'company_name', 'name', 'description', 'sort_order',
            'status', 'product_count', 'related_products',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company_name', 'category_name', 'status', 'components',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company_name', 'sort_order', 'status', 'product_count',
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
            for product in obj.products.all()
        ]

    def validate_name(self, value):
        value = ' '.join(value.split())
        company_id = self.initial_data.get('company') or getattr(self.instance, 'company_id', None)
        queryset = Category.objects.filter(company_id=company_id, name__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if company_id and queryset.exists():
            raise serializers.ValidationError('Ja existe uma categoria com este nome nesta empresa.')
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


class ProductSerializer(CompanyBoundSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    components = ProductComponentSerializer(many=True, required=False)
    internal_code = serializers.CharField(
        allow_blank=True, required=False, max_length=100
    )
    suggested_cost = serializers.SerializerMethodField()
    suggested_sale_price = serializers.SerializerMethodField()
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
            'image', 'is_sellable', 'is_favorite', 'inventory_behavior', 'status',
            'components', 'suggested_cost', 'suggested_sale_price',
            'created_at', 'updated_at',
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
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
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        company = attrs.get('company', getattr(self.instance, 'company', None))
        category = attrs.get('category', getattr(self.instance, 'category', None))
        if category and category.company_id != company.id:
            raise serializers.ValidationError({'category': 'A categoria deve pertencer a empresa do produto.'})
        name, normalized_name = normalize_product_name(
            attrs.get('name', getattr(self.instance, 'name', ''))
        )
        attrs['name'] = name
        duplicate_name = Product.objects.filter(
            company=company, normalized_name=normalized_name
        )
        if self.instance:
            duplicate_name = duplicate_name.exclude(pk=self.instance.pk)
        if duplicate_name.exists():
            raise serializers.ValidationError(
                {'name': 'Ja existe um produto com este nome nesta empresa.'}
            )
        code = attrs.get('internal_code', getattr(self.instance, 'internal_code', '')).strip()
        if code:
            same_code = Product.objects.filter(company=company, internal_code__iexact=code)
            if self.instance:
                same_code = same_code.exclude(pk=self.instance.pk)
            if same_code.exists():
                raise serializers.ValidationError({'internal_code': 'Ja existe um produto com este codigo nesta empresa.'})
        barcode = (attrs.get('barcode', getattr(self.instance, 'barcode', '')) or '').strip()
        if barcode:
            same_barcode = Product.objects.filter(company=company, barcode__iexact=barcode)
            if self.instance:
                same_barcode = same_barcode.exclude(pk=self.instance.pk)
            if same_barcode.exists():
                raise serializers.ValidationError({'barcode': 'Ja existe um produto com este codigo de barras nesta empresa.'})
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
        if components is not None:
            request = self.context.get('request')
            branch = getattr(request, 'branch_context', None) if request else None
            if request and not request.user.is_superuser and not (
                branch and user_has_branch_permission(
                    request.user, branch.pk, 'products.configure_composition'
                )
            ):
                raise serializers.ValidationError(
                    {'components': 'Voce nao possui permissao para configurar a composicao.'}
                )
            if behavior != InventoryBehavior.COMPONENTS:
                raise serializers.ValidationError(
                    {'components': 'Somente produtos com baixa por componentes possuem composicao.'}
                )
            self._validate_components(components, company)
        if behavior == InventoryBehavior.COMPONENTS and sellable:
            has_components = bool(components) if components is not None else bool(
                self.instance and self.instance.components.exists()
            )
            if not has_components:
                raise serializers.ValidationError(
                    {'is_sellable': 'Informe a composicao antes de habilitar a venda.'}
                )
        if self.instance and behavior != InventoryBehavior.COMPONENTS:
            if self.instance.components.exists():
                raise serializers.ValidationError(
                    {'inventory_behavior': 'Remova a composicao antes de alterar o comportamento.'}
                )
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch and not request.user.is_superuser:
            current_cost = self.instance.cost if self.instance else Decimal('0.00')
            current_price = self.instance.sale_price if self.instance else Decimal('0.00')
            if 'cost' in attrs and attrs['cost'] != current_cost and not user_has_branch_permission(
                request.user, branch.pk, 'products.change_cost'
            ):
                raise serializers.ValidationError({'cost': 'Voce nao possui permissao para alterar custos.'})
            if 'sale_price' in attrs and attrs['sale_price'] != current_price and not user_has_branch_permission(
                request.user, branch.pk, 'products.change_price'
            ):
                raise serializers.ValidationError({'sale_price': 'Voce nao possui permissao para alterar o preco padrao.'})
        return attrs

    def _validate_components(self, components, company):
        errors = {}
        seen = set()
        for index, item in enumerate(components):
            component = item['component_product']
            item_errors = {}
            if component.pk in seen:
                item_errors['component_product'] = ['Nao repita produtos na composicao.']
            seen.add(component.pk)
            if self.instance and component.pk == self.instance.pk:
                item_errors['component_product'] = ['Um produto nao pode compor a si mesmo.']
            if component.company_id != company.pk:
                item_errors['component_product'] = ['O componente deve pertencer a mesma empresa.']
            if component.inventory_behavior != InventoryBehavior.DIRECT:
                item_errors['component_product'] = [
                    'Somente produtos com estoque proprio podem ser componentes.'
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
        try:
            return create_product(components=components, **validated_data)
        except DjangoValidationError as error:
            detail = getattr(error, 'message_dict', {'non_field_errors': error.messages})
            raise serializers.ValidationError(detail)

    @transaction.atomic
    def update(self, instance, validated_data):
        instance.company.__class__.objects.select_for_update().get(pk=instance.company_id)
        components = validated_data.pop('components', None)
        if not validated_data.get('internal_code', instance.internal_code):
            validated_data.pop('internal_code', None)
        desired_sellable = validated_data.get('is_sellable', instance.is_sellable)
        if components is not None and desired_sellable:
            validated_data['is_sellable'] = False
        try:
            instance = super().update(instance, validated_data)
            if components is not None:
                instance = replace_composition(product=instance, components=components)
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
        value = sum(
            (item.component_product.cost * item.quantity for item in obj.components.all()),
            Decimal('0'),
        ).quantize(Decimal('0.01'))
        return f'{value:.2f}'

    def get_suggested_sale_price(self, obj):
        if obj.inventory_behavior != InventoryBehavior.COMPONENTS:
            return None
        value = sum(
            (
                item.component_product.sale_price * item.quantity
                for item in obj.components.all()
            ),
            Decimal('0'),
        ).quantize(Decimal('0.01'))
        return f'{value:.2f}'

    def validate_barcode(self, value):
        return (value or '').strip()


class CompositionSerializer(serializers.Serializer):
    components = ProductComponentSerializer(many=True)

    def validate_components(self, value):
        product = self.context['product']
        user = self.context['request'].user
        seen = set()
        errors = {}
        for index, item in enumerate(value):
            component = item['component_product']
            item_errors = {}
            if component.pk in seen:
                item_errors['component_product'] = ['Nao repita produtos na composicao.']
            seen.add(component.pk)
            if component.company_id != product.company_id:
                item_errors['component_product'] = ['O componente deve pertencer a mesma empresa.']
            branch = getattr(self.context['request'], 'branch_context', None)
            if branch and branch.company_id != component.company_id:
                item_errors['component_product'] = ['Componente fora do contexto autorizado.']
            if component.inventory_behavior != InventoryBehavior.DIRECT:
                item_errors['component_product'] = ['Somente produtos com estoque proprio podem ser componentes.']
            if component.pk == product.pk:
                item_errors['component_product'] = ['Um produto nao pode compor a si mesmo.']
            if component.unit == Unit.UNIT and item['quantity'] != item['quantity'].to_integral_value():
                item_errors['quantity'] = ['A quantidade de um componente UN deve ser inteira.']
            if item_errors:
                errors[index] = item_errors
        if errors:
            raise serializers.ValidationError(errors)
        if product.is_sellable and not value:
            raise serializers.ValidationError(
                'Um produto composto vendavel deve possuir componentes.'
            )
        return value

    def save(self, **kwargs):
        try:
            return replace_composition(
                product=self.context['product'], components=self.validated_data['components']
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

    def validate(self, attrs):
        product = attrs.get('product', getattr(self.instance, 'product', None))
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        if product and branch and product.company_id != branch.company_id:
            raise serializers.ValidationError({'branch': 'A filial deve pertencer a empresa do produto.'})
        request = self.context.get('request')
        context_branch = getattr(request, 'branch_context', None) if request else None
        if context_branch and product and product.company_id != context_branch.company_id:
            raise serializers.ValidationError({'product': 'Produto fora do contexto autorizado.'})
        if context_branch and branch and branch.pk != context_branch.pk:
            raise serializers.ValidationError({'branch': 'Selecione a filial ativa.'})
        return attrs
