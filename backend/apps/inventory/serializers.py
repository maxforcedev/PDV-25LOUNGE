from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from apps.base.constants import MAX_BIGINT
from apps.base.exceptions import DomainValidationError
from apps.companies.selectors import user_has_branch_permission
from apps.saas.permissions import support_permission_decision

from .content import content_breakdown, exact_multiply_quantized
from .models import (
    InventoryCount,
    InventoryCountItem,
    InventoryCountStatus,
    LossReason,
    LossRecord,
    MovementDomainOrigin,
    MovementNature,
    Stock,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    StockTransferReceipt,
    StockTransferReceiptItem,
    TransferDivergence,
    TransferDivergenceStatus,
    TransferDivergenceResolution,
    TransferResolutionType,
)


def _can_view_costs(request, branch_id):
    if not request:
        return False
    support = support_permission_decision(request, branch_id=branch_id)
    if support is not None:
        return support
    return request.user.is_superuser or user_has_branch_permission(
        request.user, branch_id, 'inventory.view_stock_costs'
    )


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
    unit_cost = serializers.SerializerMethodField()
    total_cost = serializers.SerializerMethodField()
    product_status = serializers.CharField(source='product.status', read_only=True)
    inventory_behavior = serializers.CharField(
        source='product.inventory_behavior', read_only=True
    )
    equivalent_quantity = serializers.SerializerMethodField()
    package_content = serializers.SerializerMethodField()
    content_unit = serializers.SerializerMethodField()
    complete_packages = serializers.SerializerMethodField()
    residual_content = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = (
            'id', 'product', 'product_name', 'internal_code', 'branch', 'branch_name',
            'company', 'company_name', 'category', 'category_name', 'unit',
            'unit_cost', 'total_cost', 'product_status', 'inventory_behavior',
            'average_unit_cost', 'last_unit_cost', 'current_quantity',
            'equivalent_quantity', 'current_content', 'package_content',
            'content_unit', 'complete_packages', 'residual_content',
            'minimum_quantity', 'state', 'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_state(self, obj):
        quantity = obj.equivalent_quantity()
        if quantity < 0:
            return 'negative'
        if quantity == 0:
            return 'zero'
        if quantity < obj.minimum_quantity:
            return 'below_minimum'
        return 'normal'

    def get_total_cost(self, obj):
        value = exact_multiply_quantized(
            max(obj.equivalent_quantity(), Decimal('0')),
            self._current_cost(obj),
            Decimal('0.01'),
        )
        return f'{value:.2f}'

    @staticmethod
    def get_equivalent_quantity(obj):
        return format(obj.equivalent_quantity(), 'f')

    @staticmethod
    def _fraction_config(obj):
        try:
            config = obj.product.fraction_config
        except ObjectDoesNotExist:
            return None
        return config if config.tracking_active and obj.current_content is not None else None

    def get_package_content(self, obj):
        config = self._fraction_config(obj)
        return format(config.package_content, 'f') if config else None

    def get_content_unit(self, obj):
        config = self._fraction_config(obj)
        return config.content_unit if config else None

    def get_complete_packages(self, obj):
        config = self._fraction_config(obj)
        if not config:
            return None
        complete, _residual = content_breakdown(obj.current_content, config.package_content)
        return format(complete, 'f')

    def get_residual_content(self, obj):
        config = self._fraction_config(obj)
        if not config:
            return None
        _complete, residual = content_breakdown(obj.current_content, config.package_content)
        return format(residual, 'f')

    @staticmethod
    def _current_cost(obj):
        return obj.average_unit_cost if obj.average_unit_cost is not None else obj.product.cost

    def get_unit_cost(self, obj):
        return f'{self._current_cost(obj):.12f}'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not _can_view_costs(request, instance.branch_id):
            data.pop('unit_cost', None)
            data.pop('total_cost', None)
            data.pop('average_unit_cost', None)
            data.pop('last_unit_cost', None)
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
    domain_origin = serializers.ChoiceField(
        choices=MovementDomainOrigin.values, required=False
    )


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
        source='quantity', max_digits=24, decimal_places=9, read_only=True
    )
    sale_number = serializers.SerializerMethodField()
    sale_operation_type = serializers.SerializerMethodField()
    operation_label = serializers.SerializerMethodField()
    operation_count = serializers.IntegerField(read_only=True)
    operation_kind = serializers.CharField(read_only=True)
    equivalent_quantity = serializers.SerializerMethodField()
    legacy_equivalent_quantity = serializers.SerializerMethodField()
    exact_content_equivalent_quantity = serializers.SerializerMethodField()
    package_content = serializers.SerializerMethodField()
    content_unit = serializers.SerializerMethodField()
    complete_packages = serializers.SerializerMethodField()
    residual_content = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = (
            'id', 'stock', 'product', 'product_name', 'internal_code', 'branch',
            'branch_name', 'company', 'company_name', 'unit', 'movement_type', 'type',
             'previous_quantity', 'quantity', 'movement_quantity', 'final_quantity',
             'user', 'user_name', 'reason', 'sale', 'sale_number', 'sale_operation_type',
              'original_movement', 'nature', 'operation_reference', 'created_at',
              'operation_label', 'operation_count', 'operation_kind',
               'unit_cost_snapshot', 'domain_origin', 'transfer_item',
                'transfer_resolution', 'loss_record', 'inventory_count_item',
               'previous_content', 'content_quantity', 'final_content',
               'equivalent_quantity', 'legacy_equivalent_quantity',
               'exact_content_equivalent_quantity', 'package_content', 'content_unit',
               'complete_packages', 'residual_content',
        )
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.get_full_name().strip() or obj.user.email

    @staticmethod
    def get_equivalent_quantity(obj):
        return format(obj.equivalent_quantity(), 'f')

    @staticmethod
    def get_legacy_equivalent_quantity(obj):
        quantity = obj.legacy_equivalent_quantity()
        return format(quantity, 'f') if quantity is not None else None

    @staticmethod
    def get_exact_content_equivalent_quantity(obj):
        quantity = obj.exact_content_equivalent_quantity()
        return format(quantity, 'f') if quantity is not None else None

    @staticmethod
    def _content_details(obj):
        if obj.content_quantity is None:
            return None
        try:
            config = obj.stock.product.fraction_config
        except ObjectDoesNotExist:
            return None
        if not config.tracking_active:
            return None
        complete, residual = content_breakdown(
            obj.content_quantity, config.package_content
        )
        return config, complete, residual

    def get_package_content(self, obj):
        details = self._content_details(obj)
        return format(details[0].package_content, 'f') if details else None

    def get_content_unit(self, obj):
        details = self._content_details(obj)
        return details[0].content_unit if details else None

    def get_complete_packages(self, obj):
        details = self._content_details(obj)
        return format(details[1], 'f') if details else None

    def get_residual_content(self, obj):
        details = self._content_details(obj)
        return format(details[2], 'f') if details else None

    def get_sale_number(self, obj):
        return obj.sale.sale_number if obj.sale_id else None

    def get_sale_operation_type(self, obj):
        return obj.sale.operation_type if obj.sale_id else None

    def get_operation_label(self, obj):
        if obj.sale_id:
            operation = 'Consumação' if obj.sale.operation_type == 'consumption' else 'Venda'
            return f'{operation} {obj.sale.sale_number}'
        domain_label = {
            MovementDomainOrigin.PURCHASE: 'Recebimento de compra',
            MovementDomainOrigin.TRANSFER_DISPATCH: 'Transferencia - despacho',
            MovementDomainOrigin.TRANSFER_RECEIPT: 'Transferencia - recebimento',
            MovementDomainOrigin.TRANSFER_RETURN: 'Transferencia - retorno a origem',
            MovementDomainOrigin.TRANSFER_CORRECTION: 'Transferencia - correcao autorizada',
            MovementDomainOrigin.LOSS: 'Registro de perda',
            MovementDomainOrigin.INVENTORY_COUNT: 'Confirmacao de inventario',
        }.get(obj.domain_origin)
        if domain_label:
            return domain_label
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not _can_view_costs(request, instance.stock.branch_id):
            data.pop('unit_cost_snapshot', None)
        return data


class MovementRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0.001'), required=False
    )
    content_quantity = serializers.DecimalField(
        max_digits=24, decimal_places=9,
        min_value=Decimal('0.000000001'), required=False,
    )
    reason = serializers.CharField(
        allow_blank=True, required=False, default='', trim_whitespace=True
    )
    nature = serializers.ChoiceField(choices=(
        MovementNature.NORMAL, MovementNature.BONUS, MovementNature.RETURN,
        MovementNature.OPENING_BALANCE, MovementNature.CORRECTION,
        MovementNature.DAMAGE, MovementNature.INTERNAL_USE, MovementNature.OTHER,
    ), required=False)

    def validate(self, attrs):
        quantity = attrs.get('quantity')
        content = attrs.get('content_quantity')
        if (quantity is None) == (content is None):
            raise serializers.ValidationError(
                'Informe somente quantity ou content_quantity.'
            )
        return attrs


class AdjustmentRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    final_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0'), required=False
    )
    final_content = serializers.DecimalField(
        max_digits=24, decimal_places=9, min_value=Decimal('0'), required=False
    )
    reason = serializers.CharField(
        allow_blank=True, required=False, default='', trim_whitespace=True
    )
    nature = serializers.ChoiceField(choices=(
        MovementNature.BALANCE_CORRECTION, MovementNature.CORRECTION,
        MovementNature.OTHER,
    ), required=False)

    def validate(self, attrs):
        quantity = attrs.get('final_quantity')
        content = attrs.get('final_content')
        if (quantity is None) == (content is None):
            raise serializers.ValidationError(
                'Informe somente final_quantity ou final_content.'
            )
        return attrs


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
            raise serializers.ValidationError('Não repita produtos na mesma entrada em grupo.')
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
                message='Não repita saldos na mesma regularização.',
                details={'stock_ids': stock_ids},
            )
        return items


class TransferItemSerializer(serializers.ModelSerializer):
    received_quantity = serializers.SerializerMethodField()
    pending_quantity = serializers.SerializerMethodField()
    movement_ids = serializers.SerializerMethodField()

    class Meta:
        model = StockTransferItem
        fields = (
            'id', 'product', 'product_name_snapshot', 'product_internal_code_snapshot',
            'product_unit_snapshot', 'requested_quantity', 'dispatched_quantity',
            'received_quantity', 'pending_quantity', 'origin_unit_cost_snapshot',
            'origin_cost_source', 'origin_sale_price_snapshot', 'movement_ids',
            'package_content_snapshot', 'content_unit_snapshot',
            'created_at',
        )
        read_only_fields = fields

    @staticmethod
    def get_received_quantity(item):
        received = sum(
            (receipt_item.received_quantity for receipt_item in item.receipt_items.all()),
            Decimal('0.000'),
        )
        try:
            resolutions = item.divergence.resolutions.all()
        except TransferDivergence.DoesNotExist:
            resolutions = ()
        received += sum(
            (resolution.quantity for resolution in resolutions
             if resolution.resolution_type == TransferResolutionType.FOUND_RECEIPT),
            Decimal('0.000'),
        )
        return format(received, 'f')

    def get_pending_quantity(self, item):
        if item.dispatched_quantity is None:
            return None
        try:
            return format(item.divergence.pending_quantity, 'f')
        except TransferDivergence.DoesNotExist:
            pass
        return format(item.dispatched_quantity - Decimal(self.get_received_quantity(item)), 'f')

    @staticmethod
    def get_movement_ids(item):
        return list(item.stock_movements.values_list('pk', flat=True))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        branch_id = (
            getattr(getattr(request, 'branch_context', None), 'pk', None)
            or instance.transfer.origin_branch_id
        )
        if not _can_view_costs(request, branch_id):
            data.pop('origin_unit_cost_snapshot', None)
            data.pop('origin_cost_source', None)
        return data


class TransferReceiptItemSerializer(serializers.ModelSerializer):
    movement_ids = serializers.SerializerMethodField()

    class Meta:
        model = StockTransferReceiptItem
        fields = (
            'id', 'transfer_item', 'dispatched_quantity_snapshot',
            'previously_received_quantity', 'received_quantity',
            'accumulated_quantity', 'pending_quantity', 'unit_cost_snapshot',
            'movement_ids', 'created_at',
            'received_content_snapshot',
        )
        read_only_fields = fields

    @staticmethod
    def get_movement_ids(item):
        return list(item.transfer_item.stock_movements.filter(
            operation_reference=item.receipt_id
        ).values_list('pk', flat=True))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not _can_view_costs(request, instance.receipt.destination_branch_id):
            data.pop('unit_cost_snapshot', None)
        return data


class TransferReceiptSerializer(serializers.ModelSerializer):
    items = TransferReceiptItemSerializer(many=True, read_only=True)

    class Meta:
        model = StockTransferReceipt
        fields = (
            'id', 'transfer', 'company', 'destination_branch', 'idempotency_key',
            'finalize', 'notes', 'received_by', 'received_at', 'items', 'created_at',
        )
        read_only_fields = fields


class TransferResolutionSerializer(serializers.ModelSerializer):
    movement_ids = serializers.SerializerMethodField()

    class Meta:
        model = TransferDivergenceResolution
        fields = (
            'id', 'divergence', 'idempotency_key', 'resolution_type', 'quantity',
            'observation', 'resolved_by', 'resolved_at', 'movement_ids', 'created_at',
        )
        read_only_fields = fields

    @staticmethod
    def get_movement_ids(resolution):
        return list(resolution.stock_movements.values_list('pk', flat=True))


class TransferDivergenceSerializer(serializers.ModelSerializer):
    transfer = serializers.UUIDField(source='transfer_item.transfer_id', read_only=True)
    product = serializers.IntegerField(source='transfer_item.product_id', read_only=True)
    product_name = serializers.CharField(
        source='transfer_item.product_name_snapshot', read_only=True
    )
    unit_cost_snapshot = serializers.DecimalField(
        source='transfer_item.origin_unit_cost_snapshot',
        max_digits=28,
        decimal_places=12,
        read_only=True,
    )
    cost_impact = serializers.SerializerMethodField()
    potential_sale_value = serializers.SerializerMethodField()
    resolutions = TransferResolutionSerializer(many=True, read_only=True)

    class Meta:
        model = TransferDivergence
        fields = (
            'id', 'transfer', 'transfer_item', 'product', 'product_name',
            'dispatched_quantity_snapshot', 'received_quantity_snapshot',
            'initial_quantity', 'resolved_quantity', 'pending_quantity', 'status',
            'unit_cost_snapshot', 'cost_impact', 'potential_sale_value',
            'detected_by', 'detected_at', 'resolutions', 'created_at', 'updated_at',
        )
        read_only_fields = fields

    @staticmethod
    def get_cost_impact(obj):
        return format(obj.pending_quantity * obj.transfer_item.origin_unit_cost_snapshot, '.12f')

    @staticmethod
    def get_potential_sale_value(obj):
        return format(obj.pending_quantity * obj.transfer_item.origin_sale_price_snapshot, '.12f')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        branch_id = (
            getattr(getattr(request, 'branch_context', None), 'pk', None)
            or instance.transfer_item.transfer.origin_branch_id
        )
        if not _can_view_costs(request, branch_id):
            data.pop('unit_cost_snapshot', None)
            data.pop('cost_impact', None)
        return data


class StockTransferSerializer(serializers.ModelSerializer):
    origin_branch_name = serializers.CharField(source='origin_branch.name', read_only=True)
    destination_branch_name = serializers.CharField(
        source='destination_branch.name', read_only=True
    )
    items = TransferItemSerializer(many=True, read_only=True)
    receipts = TransferReceiptSerializer(many=True, read_only=True)

    class Meta:
        model = StockTransfer
        fields = (
            'id', 'company', 'origin_branch', 'origin_branch_name',
            'destination_branch', 'destination_branch_name', 'status', 'notes',
            'created_by', 'dispatched_by', 'dispatched_at', 'cancelled_by',
            'dispatch_idempotency_key', 'dispatch_payload_fingerprint',
            'cancelled_at', 'cancellation_reason', 'items', 'receipts',
            'created_at', 'updated_at',
        )
        read_only_fields = fields


class LossRecordSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    movement_ids = serializers.SerializerMethodField()
    complete_packages = serializers.SerializerMethodField()
    residual_content = serializers.SerializerMethodField()

    class Meta:
        model = LossRecord
        fields = (
            'id', 'company', 'branch', 'branch_name', 'product', 'product_name',
            'idempotency_key', 'quantity', 'reason', 'observation',
            'content_quantity', 'content_unit',
            'package_content_snapshot',
            'complete_packages', 'residual_content',
            'unit_cost_snapshot', 'sale_price_snapshot', 'cost_impact',
            'potential_sale_value', 'recorded_by', 'recorded_at', 'movement_ids',
            'created_at',
        )
        read_only_fields = fields

    @staticmethod
    def get_movement_ids(loss):
        return list(loss.stock_movements.values_list('pk', flat=True))

    @staticmethod
    def _content_breakdown(loss):
        if loss.content_quantity is None or loss.package_content_snapshot is None:
            return None
        return content_breakdown(
            loss.content_quantity, loss.package_content_snapshot
        )

    def get_complete_packages(self, loss):
        breakdown = self._content_breakdown(loss)
        return format(breakdown[0], 'f') if breakdown else None

    def get_residual_content(self, loss):
        breakdown = self._content_breakdown(loss)
        return format(breakdown[1], 'f') if breakdown else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not _can_view_costs(request, instance.branch_id):
            data.pop('unit_cost_snapshot', None)
            data.pop('cost_impact', None)
        return data


class InventoryCountItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    movement_ids = serializers.SerializerMethodField()
    difference_complete_packages = serializers.SerializerMethodField()
    difference_residual_content = serializers.SerializerMethodField()

    class Meta:
        model = InventoryCountItem
        fields = (
            'id', 'product', 'product_name', 'theoretical_quantity',
            'counted_quantity', 'difference_quantity', 'counted_at',
            'unit_cost_snapshot', 'sale_price_snapshot', 'cost_impact',
            'potential_sale_value', 'counted_by', 'observation', 'movement_ids',
            'is_open', 'closed_at', 'created_at',
            'theoretical_content', 'counted_complete_packages',
            'counted_residual_content', 'counted_content', 'difference_content',
            'content_unit',
            'package_content_snapshot',
            'difference_complete_packages', 'difference_residual_content',
        )
        read_only_fields = fields

    @staticmethod
    def get_movement_ids(item):
        return list(item.stock_movements.values_list('pk', flat=True))

    @staticmethod
    def _difference_breakdown(item):
        if item.difference_content is None or item.package_content_snapshot is None:
            return None
        return content_breakdown(
            item.difference_content, item.package_content_snapshot
        )

    def get_difference_complete_packages(self, item):
        breakdown = self._difference_breakdown(item)
        return format(breakdown[0], 'f') if breakdown else None

    def get_difference_residual_content(self, item):
        breakdown = self._difference_breakdown(item)
        return format(breakdown[1], 'f') if breakdown else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not _can_view_costs(request, instance.inventory_count.branch_id):
            data.pop('unit_cost_snapshot', None)
            data.pop('cost_impact', None)
        return data


class InventoryCountSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    items = InventoryCountItemSerializer(many=True, read_only=True)

    class Meta:
        model = InventoryCount
        fields = (
            'id', 'company', 'branch', 'branch_name', 'status', 'observation',
            'created_by', 'confirmed_by', 'confirmed_at',
            'confirmation_idempotency_key', 'items', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class TransferCreateItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0.001')
    )


class StockTransferCreateSerializer(serializers.Serializer):
    origin_branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    destination_branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    items = TransferCreateItemSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        if attrs['origin_branch'] == attrs['destination_branch']:
            raise serializers.ValidationError({
                'destination_branch': 'A filial de destino deve ser diferente da origem.'
            })
        product_ids = [item['product'] for item in attrs['items']]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError({'items': 'Nao repita produtos.'})
        return attrs


class TransferReceiptInputItemSerializer(serializers.Serializer):
    transfer_item = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0')
    )


class StockTransferReceiptCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    finalize = serializers.BooleanField(default=False)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    items = TransferReceiptInputItemSerializer(many=True, allow_empty=True)

    def validate(self, attrs):
        if not attrs['finalize'] and not any(
            item['quantity'] > 0 for item in attrs['items']
        ):
            raise serializers.ValidationError({
                'items': 'Recebimento sem quantidade positiva exige finalize=true.'
            })
        item_ids = [item['transfer_item'] for item in attrs['items']]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError({'items': 'Nao repita itens.'})
        return attrs


class TransferResolutionCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    resolution_type = serializers.ChoiceField(choices=TransferResolutionType.values)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0.001')
    )
    observation = serializers.CharField(min_length=3, max_length=2000)


class LossRecordCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0.001'), required=False
    )
    content_quantity = serializers.DecimalField(
        max_digits=24, decimal_places=9,
        min_value=Decimal('0.000000001'), required=False,
    )
    reason = serializers.ChoiceField(choices=LossReason.values)
    observation = serializers.CharField(min_length=3, max_length=2000)

    def validate(self, attrs):
        if attrs.get('quantity') is None and attrs.get('content_quantity') is None:
            raise serializers.ValidationError(
                'Informe quantity ou content_quantity.'
            )
        if attrs.get('quantity') is not None and attrs.get('content_quantity') is not None:
            raise serializers.ValidationError(
                'Informe somente quantity ou content_quantity.'
            )
        return attrs


class InventoryCountInputItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    counted_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0'), required=False
    )
    counted_complete_packages = serializers.IntegerField(min_value=0, required=False)
    counted_residual_content = serializers.DecimalField(
        max_digits=24, decimal_places=9, min_value=Decimal('0'), required=False
    )
    counted_at = serializers.DateTimeField(required=False)
    observation = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        standard = attrs.get('counted_quantity') is not None
        fractional = attrs.get('counted_complete_packages') is not None
        if standard == fractional:
            raise serializers.ValidationError(
                'Informe counted_quantity ou a contagem por embalagens e residual.'
            )
        if not fractional and 'counted_residual_content' in attrs:
            raise serializers.ValidationError({
                'counted_residual_content': 'Residual exige embalagens completas.'
            })
        return attrs


class InventoryCountCreateSerializer(serializers.Serializer):
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    observation = serializers.CharField(min_length=3, max_length=2000)
    items = InventoryCountInputItemSerializer(many=True, allow_empty=False)


class IdempotencySerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=2000)


class AdvancedInventoryReportQuerySerializer(serializers.Serializer):
    product = serializers.IntegerField(
        min_value=1, max_value=MAX_BIGINT, required=False
    )
    responsible = serializers.IntegerField(
        min_value=1, max_value=MAX_BIGINT, required=False
    )
    transfer_status = serializers.ChoiceField(
        choices=StockTransfer._meta.get_field('status').choices, required=False
    )
    divergence_status = serializers.ChoiceField(
        choices=TransferDivergenceStatus.values, required=False
    )
    inventory_status = serializers.ChoiceField(
        choices=InventoryCountStatus.values, required=False
    )
    loss_reason = serializers.ChoiceField(choices=LossReason.values, required=False)
    resolution_type = serializers.ChoiceField(
        choices=TransferResolutionType.values, required=False
    )
    start_datetime = serializers.DateTimeField(required=False)
    end_datetime = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        start = attrs.get('start_datetime')
        end = attrs.get('end_datetime')
        if start and end and start > end:
            raise serializers.ValidationError({
                'end_datetime': 'A data final deve ser posterior ou igual a inicial.'
            })
        return attrs
