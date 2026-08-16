from decimal import Decimal

from rest_framework import serializers

from apps.companies.selectors import user_has_branch_permission

from .models import Category, InventoryBehavior, Product, ProductComponent, Unit
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
    components = ProductComponentSerializer(many=True, read_only=True)
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
        read_only_fields = (
            'id', 'company_name', 'category_name', 'status', 'components',
            'created_at', 'updated_at',
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        company = attrs.get('company', getattr(self.instance, 'company', None))
        category = attrs.get('category', getattr(self.instance, 'category', None))
        if category and category.company_id != company.id:
            raise serializers.ValidationError({'category': 'A categoria deve pertencer a empresa do produto.'})
        behavior = attrs.get(
            'inventory_behavior',
            getattr(self.instance, 'inventory_behavior', InventoryBehavior.DIRECT),
        )
        if self.instance and behavior != self.instance.inventory_behavior:
            raise serializers.ValidationError({
                'inventory_behavior': 'O comportamento de estoque nao pode ser alterado.'
            })
        sellable = attrs.get('is_sellable', getattr(self.instance, 'is_sellable', True))
        if behavior == InventoryBehavior.COMPONENTS and sellable:
            if not self.instance or not self.instance.components.exists():
                raise serializers.ValidationError(
                    {'is_sellable': 'Informe a composicao antes de habilitar a venda.'}
                )
        if self.instance and behavior != InventoryBehavior.COMPONENTS:
            if self.instance.components.exists():
                raise serializers.ValidationError(
                    {'inventory_behavior': 'Remova a composicao antes de alterar o comportamento.'}
                )
        return attrs

    def validate_internal_code(self, value):
        value = value.strip()
        if self.instance and not value:
            return self.instance.internal_code
        company_id = self.initial_data.get('company') or getattr(self.instance, 'company_id', None)
        queryset = Product.objects.filter(company_id=company_id, internal_code__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if company_id and queryset.exists():
            raise serializers.ValidationError('Ja existe um produto com este codigo nesta empresa.')
        return value

    def create(self, validated_data):
        return create_product(**validated_data)

    def update(self, instance, validated_data):
        if not validated_data.get('internal_code', instance.internal_code):
            validated_data.pop('internal_code', None)
        return super().update(instance, validated_data)

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
        value = (value or '').strip()
        company_id = self.initial_data.get('company') or getattr(self.instance, 'company_id', None)
        queryset = Product.objects.filter(company_id=company_id, barcode__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if value and company_id and queryset.exists():
            raise serializers.ValidationError('Ja existe um produto com este codigo de barras nesta empresa.')
        return value


class CompositionSerializer(serializers.Serializer):
    components = ProductComponentSerializer(many=True)

    def validate_components(self, value):
        product = self.context['product']
        user = self.context['request'].user
        seen = set()
        for item in value:
            component = item['component_product']
            if component.pk in seen:
                raise serializers.ValidationError('Nao repita produtos na composicao.')
            seen.add(component.pk)
            if component.company_id != product.company_id:
                raise serializers.ValidationError('Todos os componentes devem pertencer a mesma empresa.')
            branch = getattr(self.context['request'], 'branch_context', None)
            if branch and branch.company_id != component.company_id:
                raise serializers.ValidationError('Componente fora do contexto autorizado.')
            if component.inventory_behavior != InventoryBehavior.DIRECT:
                raise serializers.ValidationError('Somente produtos com estoque proprio podem ser componentes.')
            if component.pk == product.pk:
                raise serializers.ValidationError('Um produto nao pode compor a si mesmo.')
        return value

    def save(self, **kwargs):
        return replace_composition(
            product=self.context['product'], components=self.validated_data['components']
        )
