from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import User
from .models import (
    Command, CommandStatus, Order, OrderItem, OrderItemStatus, OrderStatus,
    Table, TableStatus,
)


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ('id', 'branch', 'name', 'seats', 'status', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_name(self, value):
        return ' '.join((value or '').split())


class OperationalCommandSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    command_number = serializers.CharField()
    identifier = serializers.CharField()
    open_items_count = serializers.IntegerField()
    confirmed_total = serializers.DecimalField(max_digits=14, decimal_places=2)


class OperationalTableSerializer(TableSerializer):
    operational_status = serializers.SerializerMethodField()
    open_commands_count = serializers.IntegerField(read_only=True)
    open_commands_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    open_commands = OperationalCommandSerializer(many=True, read_only=True)

    class Meta(TableSerializer.Meta):
        fields = TableSerializer.Meta.fields + (
            'operational_status', 'open_commands_count', 'open_commands_total', 'open_commands',
        )
        read_only_fields = TableSerializer.Meta.read_only_fields + (
            'operational_status', 'open_commands_count', 'open_commands_total', 'open_commands',
        )

    def get_operational_status(self, table):
        return 'occupied' if table.open_commands_count else 'free'


class BatchTableSerializer(serializers.Serializer):
    branch = serializers.IntegerField(min_value=1)
    prefix = serializers.CharField(max_length=50, required=False, default='')
    start = serializers.IntegerField(min_value=1)
    end = serializers.IntegerField(min_value=1)
    seats = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate(self, attrs):
        if attrs['end'] < attrs['start']:
            raise serializers.ValidationError({'end': 'O número final deve ser maior ou igual ao inicial.'})
        if attrs['end'] - attrs['start'] > 500:
            raise serializers.ValidationError({'end': 'Máximo de 500 mesas por lote.'})
        return attrs


class CommandSerializer(serializers.ModelSerializer):
    table_name = serializers.CharField(source='table.name', read_only=True, default='')
    open_items_count = serializers.SerializerMethodField()

    class Meta:
        model = Command
        fields = (
            'id', 'company', 'branch', 'table', 'table_name', 'command_number', 'identifier',
            'status', 'opened_by', 'closed_at', 'closed_by', 'sale',
            'open_items_count', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company', 'branch', 'table', 'command_number', 'identifier', 'status', 'opened_by',
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
    reason = serializers.CharField(min_length=3, max_length=500)


class FinalizeCommandSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    cash_session = serializers.IntegerField(min_value=1)
    payments = serializers.ListField(child=serializers.DictField(), allow_empty=False)
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
    table = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    identifier = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    def validate_identifier(self, value):
        return ' '.join(value.split())


class CommandCalculationSerializer(serializers.Serializer):
    seller_user = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    discount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, default=Decimal('0.00')
    )
    service_fee_waived = serializers.BooleanField(required=False, default=False)
