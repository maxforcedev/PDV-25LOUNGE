from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from apps.base.cost_visibility import can_view_branch_costs, redact_cost_payload

from .models import (
    AttendanceCommand, AttendanceOrder, AttendanceOrderItem, AttendancePayment,
    TableAttendance, TableOrder, TableOrderItem, TablePayment, TablePaymentAllocation,
)


class AttendanceCommandSerializer(serializers.ModelSerializer):
    seller_user_name = serializers.SerializerMethodField()

    def get_seller_user_name(self, command):
        if command.seller_user_id is None:
            return ''
        return command.seller_user.get_full_name().strip() or command.seller_user.email

    class Meta:
        model = AttendanceCommand
        fields = (
            'id', 'number', 'identifier', 'customer',
            'people_count', 'notes', 'status', 'opened_by', 'opened_by_name_snapshot',
            'seller_user', 'seller_user_name',
            'customer_name_snapshot', 'bill_requested_at', 'bill_requested_by', 'closed_at',
            'closed_by', 'sale', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class AttendanceLegacyServiceFeeRegularizationSerializer(serializers.ModelSerializer):
    payment_count = serializers.IntegerField(read_only=True)
    branch = serializers.IntegerField(source='branch_id', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = AttendanceCommand
        fields = (
            'id', 'number', 'identifier', 'branch', 'branch_name', 'status', 'created_at', 'service_fee_rate_snapshot',
            'payment_count',
        )


class AttendanceServiceFeeRegularizationInputSerializer(serializers.Serializer):
    service_fee_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal('0.00'), max_value=Decimal('100.00'),
    )
    justification = serializers.CharField(min_length=3, max_length=2000, trim_whitespace=True)
    evidence_reference = serializers.CharField(min_length=3, max_length=1000, trim_whitespace=True)
    idempotency_key = serializers.UUIDField()


class AttendanceItemFinancialRegularizationInputSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    justification = serializers.CharField(min_length=3, max_length=2000, trim_whitespace=True)
    evidence_reference = serializers.CharField(min_length=3, max_length=1000, trim_whitespace=True)
    idempotency_key = serializers.UUIDField(required=False)
    preview = serializers.BooleanField(required=False, default=False)

    def validate_items(self, values):
        normalized, seen = [], set()
        for value in values:
            if set(value) != {'item', 'financial_snapshot'}:
                raise serializers.ValidationError('Cada item deve informar somente o item e o snapshot financeiro.')
            try:
                item = int(value['item'])
            except (TypeError, ValueError) as error:
                raise serializers.ValidationError('Item inválido.') from error
            if item < 1 or item in seen or not isinstance(value['financial_snapshot'], dict):
                raise serializers.ValidationError('Itens devem ser únicos e conter um snapshot financeiro.')
            normalized.append({'item': item, 'financial_snapshot': value['financial_snapshot']})
            seen.add(item)
        return normalized

    def validate(self, attrs):
        if not attrs['preview'] and 'idempotency_key' not in attrs:
            raise serializers.ValidationError({'idempotency_key': 'Informe a chave de idempotência.'})
        return attrs


class AttendanceOrderItemSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        data['modifier_snapshot'] = redact_cost_payload(
            data.get('modifier_snapshot', []),
            include_costs=can_view_branch_costs(
                request, getattr(branch, 'pk', None),
                permission_codes=self.context.get('permission_codes'),
            ),
        )
        return data

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


class AttendanceOpenCommandSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    identifier = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    customer = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    people_count = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    seller_user = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate(self, attrs):
        if 'table' in self.initial_data:
            raise serializers.ValidationError({'table': 'Mesa é operada exclusivamente por atendimento de mesa.'})
        return attrs


class AttendanceSetSellerSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    seller_user = serializers.IntegerField(min_value=1)


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
        if 'uncertain' in statuses:
            return 'uncertain'
        if 'processing' in statuses:
            return 'processing'
        return 'pending'

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if not can_view_branch_costs(
            request, getattr(branch, 'pk', None),
            permission_codes=self.context.get('permission_codes'),
        ):
            fields.pop('unit_cost', None)
            fields.pop('component_cost_snapshot', None)
        return fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        include_costs = can_view_branch_costs(
            request, getattr(branch, 'pk', None),
            permission_codes=self.context.get('permission_codes'),
        )
        data['modifier_snapshot'] = redact_cost_payload(
            data.get('modifier_snapshot', []), include_costs=include_costs,
        )
        data['financial_snapshot'] = redact_cost_payload(
            data.get('financial_snapshot', {}), include_costs=include_costs,
        )
        return data

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
    print_document = serializers.SerializerMethodField()

    def get_print_document(self, payment):
        from apps.production.models import PrintDocument, PrintDocumentType
        from apps.production.serializers import PrintDocumentResultSerializer

        document = PrintDocument.objects.filter(
            branch=payment.attendance.branch,
            document_type=PrintDocumentType.PAYMENT_RECEIPT,
            source_type='table_payment', source_id=str(payment.pk),
        ).order_by('-version', '-id').first()
        return PrintDocumentResultSerializer(document).data if document else None

    class Meta:
        model = TablePayment
        fields = (
            'id', 'attendance', 'payment_method', 'payment_method_name', 'payment_method_code', 'amount', 'received_amount',
            'change_amount', 'operator', 'status', 'idempotency_key',
            'reversal_of', 'reversal_reason', 'allocations', 'print_document', 'created_at',
        )
        read_only_fields = fields


class TableAttendanceOpenSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    people_count = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    responsible_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    customer = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')


class TablePaymentInputSerializer(AttendancePaymentInputSerializer):
    cash_session = None
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
