from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from apps.accounts.models import User
from .models import (
    Command, CommandPayment, CommandStatus, Order, OrderItem, OrderItemStatus, OrderStatus,
    Table, TableStatus,
)


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ('id', 'branch', 'name', 'seats', 'status', 'created_at', 'updated_at')
        read_only_fields = ('id', 'status', 'created_at', 'updated_at')

    def validate_name(self, value):
        return ' '.join((value or '').split())


class BatchTableSerializer(serializers.Serializer):
    branch = serializers.IntegerField(min_value=1)
    prefix = serializers.CharField(max_length=50, required=False, allow_blank=True)
    start = serializers.IntegerField(min_value=1, required=False)
    end = serializers.IntegerField(min_value=1, required=False)
    seats = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs):
        start = attrs.get('start', 1)
        if attrs.get('end') is not None and attrs['end'] < start:
            raise serializers.ValidationError({'end': 'O número final deve ser maior ou igual ao inicial.'})
        if attrs.get('end') is not None and attrs['end'] - start >= 500:
            raise serializers.ValidationError({'end': 'Máximo de 500 mesas por lote.'})
        return attrs


class CommandSerializer(serializers.ModelSerializer):
    open_items_count = serializers.SerializerMethodField()

    class Meta:
        model = Command
        fields = (
            'id', 'company', 'branch', 'customer', 'command_number', 'identifier',
            'status', 'opened_by', 'closed_at', 'closed_by', 'sale',
            'open_items_count', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company', 'branch', 'customer', 'command_number', 'identifier', 'status', 'opened_by',
            'closed_at', 'closed_by', 'sale', 'open_items_count',
            'created_at', 'updated_at',
        )

    def get_open_items_count(self, obj):
        if hasattr(obj, 'open_items_count'):
            return obj.open_items_count
        return OrderItem.objects.filter(
            order__command=obj,
            status=OrderItemStatus.PENDING,
        ).count()


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            'id', 'order', 'product', 'quantity', 'product_name', 'internal_code',
            'unit', 'unit_price', 'base_unit_price', 'modifier_unit_total',
            'modifier_snapshot', 'unit_cost', 'component_cost_snapshot',
            'status', 'confirmed_at', 'confirmed_by', 'cancelled_at',
            'cancelled_by', 'cancellation_reason', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'product_name', 'internal_code', 'unit', 'unit_price',
            'base_unit_price', 'modifier_unit_total', 'modifier_snapshot',
            'unit_cost', 'component_cost_snapshot', 'status', 'confirmed_at',
            'confirmed_by', 'cancelled_at', 'cancelled_by', 'cancellation_reason',
            'created_at', 'updated_at',
        )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ('id', 'command', 'status', 'created_by', 'items', 'created_at', 'updated_at')
        read_only_fields = ('id', 'status', 'created_by', 'items', 'created_at', 'updated_at')


class CreateOrderItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal('0.001'))
    modifiers = serializers.JSONField(required=False, default=list)


class ConfirmOrderItemSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()


class CancelOrderItemSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    reason = serializers.CharField(
        required=False, allow_blank=True, default='', max_length=500,
        trim_whitespace=True,
    )


class FinalizeCommandSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    cash_session = serializers.IntegerField(min_value=1)
    payments = serializers.ListField(child=serializers.DictField(), allow_empty=True, required=False, default=list)
    seller_user = serializers.IntegerField(required=False)
    discount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, default=Decimal('0.00')
    )
    discount_authorization = serializers.DictField(required=False)
    service_fee_waived = serializers.BooleanField(required=False, default=False)
    service_fee_authorization = serializers.DictField(required=False)

    def _authorization(self, value):
        allowed = {'user', 'method', 'credential'}
        if set(value) - allowed or value.get('method') != 'password':
            raise serializers.ValidationError('Autorização inválida.')
        credential = value.get('credential')
        if not isinstance(credential, str) or not credential:
            raise serializers.ValidationError('Informe a credencial do autorizador.')
        try:
            user = User.objects.get(pk=int(value.get('user')))
        except (TypeError, ValueError, User.DoesNotExist):
            raise serializers.ValidationError('Autorizador inválido.')
        return {'user': user, 'method': 'password', 'credential': credential}

    def validate_discount_authorization(self, value):
        return self._authorization(value)

    def validate_service_fee_authorization(self, value):
        return self._authorization(value)


class OpenCommandSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    customer = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate(self, attrs):
        if 'table' in self.initial_data:
            raise serializers.ValidationError({'table': 'Mesa é operada exclusivamente por atendimento de mesa.'})
        return attrs

    def validate_identifier(self, value):
        return ' '.join(value.split())


class SetCommandCustomerSerializer(serializers.Serializer):
    customer = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class CommandPaymentSerializer(serializers.ModelSerializer):
    payment_method_name = serializers.CharField(source='payment_method.name', read_only=True)
    payment_method_code = serializers.CharField(source='payment_method.code', read_only=True)

    class Meta:
        model = CommandPayment
        fields = ('id', 'command', 'payment_method', 'payment_method_name', 'payment_method_code',
                  'amount', 'received_amount', 'change_amount', 'cash_session', 'operator', 'status',
                  'idempotency_key', 'reversal_of', 'reversal_reason', 'created_at')
        read_only_fields = fields


class RecordCommandPaymentSerializer(serializers.Serializer):
    payment_method = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    received_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.00'), required=False, allow_null=True)
    cash_session = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    idempotency_key = serializers.UUIDField()
    discount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    discount_authorization = serializers.DictField(required=False)
    service_fee_waived = serializers.BooleanField(required=False)
    service_fee_authorization = serializers.DictField(required=False)

    def _authorization(self, value):
        return FinalizeCommandSerializer()._authorization(value)

    def validate_discount_authorization(self, value):
        return self._authorization(value)

    def validate_service_fee_authorization(self, value):
        return self._authorization(value)


class ReverseCommandPaymentSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    reason = serializers.CharField(
        required=False, allow_blank=True, default='', max_length=500,
        trim_whitespace=True,
    )


class CommandCalculationSerializer(serializers.Serializer):
    seller_user = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    discount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, default=Decimal('0.00')
    )
    service_fee_waived = serializers.BooleanField(required=False, default=False)


class TransferItemsSerializer(serializers.Serializer):
    command = serializers.IntegerField(min_value=1)
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    idempotency_key = serializers.UUIDField()

    def validate_items(self, value):
        seen = set()
        for entry in value:
            if set(entry) != {'item', 'quantity'}:
                raise serializers.ValidationError('Cada item deve conter apenas item e quantity.')
            try:
                item_id = int(entry['item'])
                quantity = Decimal(str(entry['quantity']))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                raise serializers.ValidationError('Item ou quantidade inválidos.')
            if item_id < 1 or quantity <= 0 or quantity.as_tuple().exponent < -3:
                raise serializers.ValidationError('Item e quantidade devem ser positivos.')
            if item_id in seen:
                raise serializers.ValidationError('Um item só pode ser informado uma vez.')
            seen.add(item_id)
            entry['item'] = item_id
            entry['quantity'] = quantity
        return value


class MergeCommandSerializer(serializers.Serializer):
    command = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.UUIDField()


class SplitCommandSerializer(TransferItemsSerializer):
    command = None
    identifier = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if 'table' in self.initial_data:
            raise serializers.ValidationError({'table': 'Mesa é operada exclusivamente por atendimento de mesa.'})
        return attrs

    def validate_identifier(self, value):
        return ' '.join(value.split())
