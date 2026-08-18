from decimal import Decimal

from rest_framework import serializers

from apps.base.constants import MAX_BIGINT
from apps.base.exceptions import DomainValidationError
from apps.companies.selectors import user_has_branch_permission

from .models import MovementNature, Stock, StockMovement


class StockSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    internal_code = serializers.CharField(source='product.internal_code', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    company = serializers.IntegerField(source='branch.company_id', read_only=True)
    company_name = serializers.CharField(source='branch.company.trade_name', read_only=True)
    unit = serializers.CharField(source='product.unit', read_only=True)
    state = serializers.SerializerMethodField()
    category = serializers.IntegerField(source='product.category_id', read_only=True)
    category_name = serializers.CharField(source='product.category.name', read_only=True)
    unit_cost = serializers.DecimalField(
        source='product.cost', max_digits=12, decimal_places=2, read_only=True
    )
    total_cost = serializers.SerializerMethodField()
    product_status = serializers.CharField(source='product.status', read_only=True)
    inventory_behavior = serializers.CharField(
        source='product.inventory_behavior', read_only=True
    )

    class Meta:
        model = Stock
        fields = (
            'id', 'product', 'product_name', 'internal_code', 'branch', 'branch_name',
            'company', 'company_name', 'category', 'category_name', 'unit',
            'unit_cost', 'total_cost', 'product_status', 'inventory_behavior',
            'current_quantity', 'minimum_quantity', 'state', 'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_state(self, obj):
        if obj.current_quantity < 0:
            return 'negative'
        if obj.current_quantity == 0:
            return 'zero'
        if obj.current_quantity < obj.minimum_quantity:
            return 'below_minimum'
        return 'normal'

    def get_total_cost(self, obj):
        return f'{(max(obj.current_quantity, Decimal("0")) * obj.product.cost):.2f}'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not request or not user_has_branch_permission(
            request.user, instance.branch_id, 'inventory.view_stock_costs'
        ):
            data.pop('unit_cost', None)
            data.pop('total_cost', None)
        return data


class MinimumQuantitySerializer(serializers.Serializer):
    minimum_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0')
    )

    def update(self, instance, validated_data):
        instance.minimum_quantity = validated_data['minimum_quantity']
        instance.save(update_fields=('minimum_quantity', 'updated_at'))
        return instance


class InventoryQuerySerializer(serializers.Serializer):
    company = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)


class StockMovementQuerySerializer(InventoryQuerySerializer):
    operation_reference = serializers.UUIDField(required=False)


class StockMovementSerializer(serializers.ModelSerializer):
    product = serializers.IntegerField(source='stock.product_id', read_only=True)
    product_name = serializers.CharField(source='stock.product.name', read_only=True)
    internal_code = serializers.CharField(source='stock.product.internal_code', read_only=True)
    branch = serializers.IntegerField(source='stock.branch_id', read_only=True)
    branch_name = serializers.CharField(source='stock.branch.name', read_only=True)
    company = serializers.IntegerField(source='stock.branch.company_id', read_only=True)
    company_name = serializers.CharField(
        source='stock.branch.company.trade_name', read_only=True
    )
    unit = serializers.CharField(source='stock.product.unit', read_only=True)
    user_name = serializers.SerializerMethodField()
    type = serializers.CharField(source='movement_type', read_only=True)
    movement_quantity = serializers.DecimalField(
        source='quantity', max_digits=14, decimal_places=3, read_only=True
    )
    sale_number = serializers.SerializerMethodField()
    sale_operation_type = serializers.SerializerMethodField()
    operation_label = serializers.SerializerMethodField()
    operation_count = serializers.IntegerField(read_only=True)
    operation_kind = serializers.CharField(read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            'id', 'stock', 'product', 'product_name', 'internal_code', 'branch',
            'branch_name', 'company', 'company_name', 'unit', 'movement_type', 'type',
             'previous_quantity', 'quantity', 'movement_quantity', 'final_quantity',
             'user', 'user_name', 'reason', 'sale', 'sale_number', 'sale_operation_type',
              'original_movement', 'nature', 'operation_reference', 'created_at',
              'operation_label', 'operation_count', 'operation_kind',
        )
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.get_full_name().strip() or obj.user.email

    def get_sale_number(self, obj):
        return obj.sale.sale_number if obj.sale_id else None

    def get_sale_operation_type(self, obj):
        return obj.sale.operation_type if obj.sale_id else None

    def get_operation_label(self, obj):
        if obj.sale_id:
            operation = 'Consumação' if obj.sale.operation_type == 'consumption' else 'Venda'
            return f'{operation} {obj.sale.sale_number}'
        count = obj.operation_count
        suffix = f'{count} produto' if count == 1 else f'{count} produtos'
        if obj.nature == MovementNature.REGULARIZATION:
            return f'Regularização · {suffix}'
        operation = {
            'entry': 'Entrada',
            'exit': 'Saída',
            'adjustment': 'Ajuste',
        }.get(obj.movement_type, obj.get_movement_type_display())
        if count > 1 or obj.operation_kind == 'group_entry':
            operation = 'Entrada em grupo' if obj.movement_type == 'entry' else operation
            return f'{operation} · {suffix}'
        return operation


class MovementRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0.001')
    )
    reason = serializers.CharField(
        allow_blank=True, required=False, default='', trim_whitespace=True
    )
    nature = serializers.ChoiceField(choices=MovementNature.values, required=False)


class AdjustmentRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    final_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0')
    )
    reason = serializers.CharField(
        allow_blank=True, required=False, default='', trim_whitespace=True
    )
    nature = serializers.ChoiceField(choices=(
        MovementNature.INVENTORY, MovementNature.BALANCE_CORRECTION,
        MovementNature.OTHER,
    ), required=False)


class GroupMovementItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0')
    )


class GroupEntrySerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    nature = serializers.ChoiceField(choices=(
        MovementNature.NORMAL, MovementNature.BONUS, MovementNature.RETURN,
        MovementNature.OPENING_BALANCE, MovementNature.CORRECTION, MovementNature.OTHER,
    ))
    reason = serializers.CharField(allow_blank=True, required=False, default='')
    items = GroupMovementItemSerializer(many=True, allow_empty=False)

    def validate_items(self, items):
        if not any(item['quantity'] > 0 for item in items):
            raise serializers.ValidationError('Informe quantidade para ao menos um produto.')
        product_ids = [item['product'] for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError('Nao repita produtos na mesma entrada em grupo.')
        return items


class RegularizationItemSerializer(serializers.Serializer):
    stock = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    final_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0')
    )


class RegularizeNegativesSerializer(serializers.Serializer):
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    reason = serializers.CharField(min_length=3, max_length=500)
    items = RegularizationItemSerializer(many=True, allow_empty=False)

    def validate_items(self, items):
        stock_ids = [item['stock'] for item in items]
        if len(stock_ids) != len(set(stock_ids)):
            raise DomainValidationError(
                code='duplicate_regularization_stock',
                message='Nao repita saldos na mesma regularizacao.',
                details={'stock_ids': stock_ids},
            )
        return items
