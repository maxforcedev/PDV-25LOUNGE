from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .models import (
    AttendanceCommand, AttendanceOrder, AttendanceOrderItem, AttendancePayment,
    TableAttendance, TableOrder, TableOrderItem, TablePayment, TablePaymentAllocation,
)


class AttendanceCommandSerializer(serializers.ModelSerializer):
    table_name = serializers.CharField(source='table_name_snapshot', read_only=True)

    class Meta:
        model = AttendanceCommand
        fields = (
            'id', 'number', 'identifier', 'table', 'table_name', 'customer', 'is_primary',
            'people_count', 'notes', 'status', 'opened_by', 'opened_by_name_snapshot',
            'customer_name_snapshot', 'bill_requested_at', 'bill_requested_by', 'closed_at',
            'closed_by', 'sale', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class AttendanceOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceOrderItem
        fields = (
            'id', 'order', 'product', 'quantity', 'product_name', 'internal_code', 'unit',
            'unit_price', 'base_unit_price', 'modifier_unit_total', 'modifier_snapshot', 'notes',
            'status', 'confirmed_at', 'confirmed_by', 'cancelled_at', 'cancelled_by',
            'cancellation_reason', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class AttendanceOrderSerializer(serializers.ModelSerializer):
    items = AttendanceOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = AttendanceOrder
        fields = ('id', 'command', 'status', 'created_by', 'items', 'created_at', 'updated_at')
        read_only_fields = fields


class AttendancePaymentSerializer(serializers.ModelSerializer):
    payment_method_name = serializers.CharField(source='payment_method.name', read_only=True)
    payment_method_code = serializers.CharField(source='payment_method.code', read_only=True)

    class Meta:
        model = AttendancePayment
        fields = (
            'id', 'command', 'payment_method', 'payment_method_name', 'payment_method_code',
            'amount', 'received_amount', 'change_amount', 'cash_session', 'operator', 'status',
            'idempotency_key', 'reversal_of', 'reversal_reason', 'created_at',
        )
        read_only_fields = fields


class AttendanceOpenTableSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    people_count = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    identifier = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    customer = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class AttendanceOpenCommandSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    identifier = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    customer = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    table = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    people_count = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')


class AttendanceTableGroupSerializer(serializers.Serializer):
    tables = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=2)
    idempotency_key = serializers.UUIDField()

    def validate_tables(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError('Informe mesas diferentes para agrupar.')
        return value


class AttendanceBillRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()


class AttendanceItemsSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)

    def validate_items(self, values):
        normalized = []
        for value in values:
            if set(value) - {'product', 'quantity', 'modifiers', 'notes'}:
                raise serializers.ValidationError('Item contém campos inválidos.')
            try:
                quantity = Decimal(str(value['quantity']))
                product = int(value['product'])
            except (KeyError, TypeError, ValueError, InvalidOperation) as error:
                raise serializers.ValidationError('Produto ou quantidade inválidos.') from error
            if product < 1 or quantity <= 0 or quantity.as_tuple().exponent < -3:
                raise serializers.ValidationError('Produto e quantidade devem ser positivos.')
            normalized.append({
                'product': product, 'quantity': quantity,
                'modifiers': value.get('modifiers', []), 'notes': value.get('notes', ''),
            })
        return normalized


class AttendanceConfirmItemSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()


class AttendanceCancelItemSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')


class AttendanceTransferCommandSerializer(serializers.Serializer):
    table = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    idempotency_key = serializers.UUIDField()


class AttendanceTransferItemsSerializer(serializers.Serializer):
    command = serializers.IntegerField(min_value=1)
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    idempotency_key = serializers.UUIDField()

    def validate_items(self, values):
        seen = set()
        for value in values:
            try:
                item = int(value['item'])
                quantity = Decimal(str(value['quantity']))
            except (KeyError, TypeError, ValueError, InvalidOperation) as error:
                raise serializers.ValidationError('Item ou quantidade inválidos.') from error
            if item < 1 or quantity <= 0 or quantity.as_tuple().exponent < -3 or item in seen:
                raise serializers.ValidationError('Itens devem ser únicos e ter quantidade positiva.')
            value['item'] = item
            value['quantity'] = quantity
            seen.add(item)
        return values


class AttendancePaymentInputSerializer(serializers.Serializer):
    payment_method = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    received_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.00'), required=False, allow_null=True)
    cash_session = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    idempotency_key = serializers.UUIDField()
    discount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    discount_authorization = serializers.DictField(required=False)
    service_fee_waived = serializers.BooleanField(required=False)
    service_fee_authorization = serializers.DictField(required=False)


class AttendanceReversePaymentSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    authorization = serializers.DictField(required=False)


class AttendanceFinalizeSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    cash_session = serializers.IntegerField(min_value=1)
    payments = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    discount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=Decimal('0.00'))
    discount_authorization = serializers.DictField(required=False)
    service_fee_waived = serializers.BooleanField(required=False, default=False)
    service_fee_authorization = serializers.DictField(required=False)


class TableAttendanceSerializer(serializers.ModelSerializer):
    table_name = serializers.CharField(source='table.name', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default='')

    class Meta:
        model = TableAttendance
        fields = (
            'id', 'table', 'table_name', 'customer', 'customer_name', 'people_count', 'responsible_name', 'notes', 'status',
            'opened_by', 'bill_requested_at', 'bill_requested_by', 'closed_at', 'closed_by',
            'sale', 'checkout_discount', 'checkout_discount_type', 'checkout_service_fee_waived', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class TableOrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.SerializerMethodField()
    print_status = serializers.SerializerMethodField()

    def get_line_total(self, item):
        return item.unit_price * item.quantity

    def get_print_status(self, item):
        jobs = [job for job in item.production_jobs.all() if job.event == 'new']
        print_jobs = [
            print_job
            for job in jobs
            for print_job in job.print_jobs.all()
            if print_job.reprint_of_id is None
        ]
        if not print_jobs:
            return None
        statuses = {job.status for job in print_jobs}
        if statuses == {'printed'}:
            return 'printed'
        if 'failed' in statuses:
            return 'failed'
        if 'processing' in statuses:
            return 'processing'
        return 'pending'

    class Meta:
        model = TableOrderItem
        fields = (
            'id', 'order', 'product', 'quantity', 'product_name', 'internal_code', 'line_total',
            'category_id_snapshot', 'category_name_snapshot', 'unit', 'unit_price',
            'base_unit_price', 'modifier_unit_total', 'modifier_snapshot', 'notes',
            'unit_cost', 'component_cost_snapshot', 'financial_snapshot', 'print_status', 'status', 'confirmed_at',
            'confirmed_by', 'cancelled_at', 'cancelled_by', 'cancellation_reason',
            'created_at', 'updated_at',
        )
        read_only_fields = fields


class TableOrderSerializer(serializers.ModelSerializer):
    items = TableOrderItemSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()

    def get_created_by_name(self, order):
        return order.created_by.get_full_name().strip() or order.created_by.email

    class Meta:
        model = TableOrder
        fields = ('id', 'attendance', 'status', 'created_by', 'created_by_name', 'items', 'created_at', 'updated_at')
        read_only_fields = fields


class TablePaymentAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TablePaymentAllocation
        fields = ('id', 'item', 'person_number', 'amount', 'allocated_quantity', 'equal_split_cycle')
        read_only_fields = fields


class TablePaymentSerializer(serializers.ModelSerializer):
    allocations = TablePaymentAllocationSerializer(many=True, read_only=True)
    payment_method_name = serializers.CharField(source='payment_method.name', read_only=True)
    payment_method_code = serializers.CharField(source='payment_method.code', read_only=True)

    class Meta:
        model = TablePayment
        fields = (
            'id', 'attendance', 'payment_method', 'payment_method_name', 'payment_method_code', 'amount', 'received_amount',
            'change_amount', 'cash_session', 'operator', 'status', 'idempotency_key',
            'reversal_of', 'reversal_reason', 'allocations', 'created_at',
        )
        read_only_fields = fields


class TableAttendanceOpenSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    people_count = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    responsible_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    customer = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')


class TablePaymentInputSerializer(AttendancePaymentInputSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'), required=False)
    mode = serializers.ChoiceField(choices=('value', 'remaining', 'equal_people', 'items'), required=False, default='value')
    allocations = serializers.ListField(child=serializers.DictField(), required=False, default=list)

    def validate(self, attrs):
        mode = attrs['mode']
        if mode == 'value' and attrs.get('amount') is None:
            raise serializers.ValidationError({'amount': 'Informe o valor do pagamento.'})
        if mode == 'items' and not attrs.get('allocations'):
            raise serializers.ValidationError({'allocations': 'Informe os itens a pagar.'})
        if mode != 'items' and attrs.get('allocations'):
            raise serializers.ValidationError({'allocations': 'Alocações são exclusivas do pagamento por itens.'})
        return attrs


class TablePaymentPreviewSerializer(serializers.Serializer):
    allocations = serializers.ListField(child=serializers.DictField(), allow_empty=False)

    def validate_allocations(self, values):
        seen = set()
        for value in values:
            try:
                item = int(value['item'])
                quantity = Decimal(str(value['allocated_quantity']))
            except (KeyError, TypeError, ValueError, InvalidOperation) as error:
                raise serializers.ValidationError('Item ou quantidade inválidos.') from error
            if item < 1 or quantity <= 0 or quantity.as_tuple().exponent < -3 or item in seen:
                raise serializers.ValidationError('Itens devem ser únicos e ter quantidade positiva.')
            value['item'], value['allocated_quantity'] = item, quantity
            seen.add(item)
        return values


class TableTransferItemsSerializer(serializers.Serializer):
    destination_attendance = serializers.IntegerField(min_value=1)
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    idempotency_key = serializers.UUIDField()

    def validate_items(self, values):
        seen = set()
        for value in values:
            try:
                item = int(value['item'])
                quantity = Decimal(str(value['quantity']))
            except (KeyError, TypeError, ValueError, InvalidOperation) as error:
                raise serializers.ValidationError('Item ou quantidade inválidos.') from error
            if item < 1 or quantity <= 0 or quantity.as_tuple().exponent < -3 or item in seen:
                raise serializers.ValidationError('Itens devem ser únicos e ter quantidade positiva.')
            value['item'], value['quantity'] = item, quantity
            seen.add(item)
        return values


class TableAttendanceCustomerSerializer(serializers.Serializer):
    customer = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    idempotency_key = serializers.UUIDField()


class TableCancelOrderItemSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    reason = serializers.CharField(max_length=1000, allow_blank=False, trim_whitespace=True)


class TableItemDiscountSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    discount = serializers.JSONField()
    authorization = serializers.DictField(required=False)


class TableCheckoutContextSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    discount = serializers.JSONField(required=False, default='0.00')
    discount_authorization = serializers.DictField(required=False)
    service_fee_waived = serializers.BooleanField(required=False, default=False)
    service_fee_authorization = serializers.DictField(required=False)


class TableCloseSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    cash_session = serializers.IntegerField(min_value=1, required=False, allow_null=True)
