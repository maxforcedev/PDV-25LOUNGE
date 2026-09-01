from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from apps.inventory.content import content_breakdown

from apps.base.constants import MAX_BIGINT
from apps.companies.selectors import user_has_branch_permission
from apps.saas.permissions import support_permission_decision

from .models import (
    PayableInstallment,
    PurchaseOrder,
    PurchaseAttachment,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
)
from .storage import (
    MAX_ATTACHMENT_SIZE,
    purchase_attachment_download_name,
    validate_purchase_attachment,
)


def _can(request, branch_id, code):
    if request:
        support = support_permission_decision(request, branch_id=branch_id)
        if support is not None:
            return support
    return bool(
        request
        and (
            request.user.is_superuser
            or user_has_branch_permission(request.user, branch_id, code)
        )
    )


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    received_quantity = serializers.SerializerMethodField()
    pending_quantity = serializers.SerializerMethodField()
    ordered_stock_quantity = serializers.SerializerMethodField()
    received_stock_quantity = serializers.SerializerMethodField()
    pending_stock_quantity = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderItem
        fields = (
            'id', 'line_number', 'product', 'product_supplier', 'product_supplier_unit',
            'ordered_quantity', 'received_quantity', 'pending_quantity', 'product_name',
            'product_internal_code', 'product_stock_unit', 'supplier_name',
            'supplier_tax_id', 'supplier_product_code', 'presentation_unit_code',
            'presentation_description', 'conversion_factor', 'purchase_unit_price',
            'ordered_stock_quantity', 'received_stock_quantity', 'pending_stock_quantity',
            'gross_subtotal', 'allocated_discount', 'allocated_freight',
            'allocated_other_expenses', 'effective_total',
            'effective_stock_unit_cost', 'created_at',
        )
        read_only_fields = fields

    @staticmethod
    def get_received_quantity(item):
        value = sum(
            (receipt_item.received_quantity for receipt_item in item.receipt_items.all()),
            Decimal('0.000000'),
        )
        return format(value, 'f')

    def get_pending_quantity(self, item):
        received = Decimal(self.get_received_quantity(item))
        return format(max(item.ordered_quantity - received, Decimal('0')), 'f')

    @staticmethod
    def get_ordered_stock_quantity(item):
        return format(item.ordered_stock_quantity, 'f')

    @staticmethod
    def get_received_stock_quantity(item):
        value = sum(
            (receipt_item.stock_quantity for receipt_item in item.receipt_items.all()),
            Decimal('0.000000'),
        )
        return format(value, 'f')

    def get_pending_stock_quantity(self, item):
        received = Decimal(self.get_received_stock_quantity(item))
        return format(max(item.ordered_stock_quantity - received, Decimal('0')), 'f')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not _can(request, instance.purchase_order.branch_id, 'purchases.view_costs'):
            for field in (
                'purchase_unit_price', 'gross_subtotal', 'allocated_discount',
                'allocated_freight', 'allocated_other_expenses', 'effective_total',
                'effective_stock_unit_cost',
            ):
                data.pop(field, None)
        return data


class PayableInstallmentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.trade_name', read_only=True)
    order_number = serializers.CharField(
        source='purchase_order.order_number', read_only=True
    )

    class Meta:
        model = PayableInstallment
        fields = (
            'id', 'purchase_order', 'order_number', 'supplier', 'supplier_name',
            'installment_number', 'amount', 'due_date', 'status', 'paid_at', 'paid_by',
            'paid_amount', 'paid_payment_method',
            'cancelled_at', 'cancelled_by', 'cancellation_reason', 'notes',
            'created_at', 'updated_at',
        )
        read_only_fields = fields


class PurchaseReceiptItemSerializer(serializers.ModelSerializer):
    complete_packages = serializers.SerializerMethodField()
    residual_content = serializers.SerializerMethodField()
    ordered_stock_quantity = serializers.SerializerMethodField()
    previously_received_stock_quantity = serializers.SerializerMethodField()
    accumulated_stock_quantity = serializers.SerializerMethodField()
    pending_stock_quantity = serializers.SerializerMethodField()
    divergence_stock_quantity = serializers.SerializerMethodField()
    ordered_total = serializers.SerializerMethodField()
    received_total = serializers.SerializerMethodField()
    difference_total = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseReceiptItem
        fields = (
            'id', 'purchase_order_item', 'ordered_quantity_snapshot',
            'previously_received_quantity', 'received_quantity',
            'accumulated_quantity', 'pending_quantity', 'divergence_quantity',
            'divergence_reason', 'conversion_factor_snapshot', 'stock_quantity',
            'ordered_stock_quantity', 'previously_received_stock_quantity',
            'accumulated_stock_quantity', 'pending_stock_quantity',
            'divergence_stock_quantity', 'ordered_total', 'received_total',
            'difference_total',
            'stock_content_quantity', 'stock_content_unit',
            'stock_package_content_snapshot', 'complete_packages',
            'residual_content',
            'effective_stock_unit_cost_snapshot', 'product_name_snapshot',
            'supplier_name_snapshot', 'presentation_snapshot', 'created_at',
        )
        read_only_fields = fields

    @staticmethod
    def _content_breakdown(item):
        if (
            item.stock_content_quantity is None
            or item.stock_package_content_snapshot is None
        ):
            return None
        return content_breakdown(
            item.stock_content_quantity, item.stock_package_content_snapshot
        )

    def get_complete_packages(self, item):
        breakdown = self._content_breakdown(item)
        return format(breakdown[0], 'f') if breakdown else None

    def get_residual_content(self, item):
        breakdown = self._content_breakdown(item)
        return format(breakdown[1], 'f') if breakdown else None

    @staticmethod
    def _stock_text(value):
        return format(value.quantize(Decimal('0.000001')), 'f')

    @staticmethod
    def get_ordered_stock_quantity(item):
        return PurchaseReceiptItemSerializer._stock_text(
            item.ordered_quantity_snapshot * item.conversion_factor_snapshot
        )

    @staticmethod
    def _previous_stock_quantity(item):
        cached = getattr(item, '_previous_stock_quantity', None)
        if cached is not None:
            return cached
        value = PurchaseReceiptItem.objects.filter(
            purchase_order_item_id=item.purchase_order_item_id,
            receipt__confirmed_at__lt=item.receipt.confirmed_at,
        ).aggregate(total=Sum('stock_quantity'))['total'] or Decimal('0.000000')
        item._previous_stock_quantity = value
        return value

    def get_previously_received_stock_quantity(self, item):
        return self._stock_text(self._previous_stock_quantity(item))

    def get_accumulated_stock_quantity(self, item):
        return self._stock_text(self._previous_stock_quantity(item) + item.stock_quantity)

    def get_pending_stock_quantity(self, item):
        return self._stock_text(max(
            item.ordered_quantity_snapshot * item.conversion_factor_snapshot
            - self._previous_stock_quantity(item) - item.stock_quantity,
            Decimal('0'),
        ))

    def get_divergence_stock_quantity(self, item):
        pending_before = max(
            item.ordered_quantity_snapshot * item.conversion_factor_snapshot
            - self._previous_stock_quantity(item),
            Decimal('0'),
        )
        return self._stock_text(item.stock_quantity - pending_before)

    def _received_total(self, item):
        ordered_stock = item.ordered_quantity_snapshot * item.conversion_factor_snapshot
        if not ordered_stock:
            return Decimal('0.00')
        return (
            item.purchase_order_item.effective_total
            * (self._previous_stock_quantity(item) + item.stock_quantity)
            / ordered_stock
        ).quantize(Decimal('0.01'))

    @staticmethod
    def get_ordered_total(item):
        return format(item.purchase_order_item.effective_total, 'f')

    def get_received_total(self, item):
        return format(self._received_total(item), 'f')

    def get_difference_total(self, item):
        return format(self._received_total(item) - item.purchase_order_item.effective_total, 'f')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not _can(request, instance.receipt.branch_id, 'purchases.view_costs'):
            for field in (
                'effective_stock_unit_cost_snapshot', 'ordered_total',
                'received_total', 'difference_total',
            ):
                data.pop(field, None)
        return data


class PurchaseReceiptSerializer(serializers.ModelSerializer):
    items = PurchaseReceiptItemSerializer(many=True, read_only=True)
    order_number = serializers.CharField(
        source='purchase_order.order_number', read_only=True
    )
    supplier = serializers.IntegerField(
        source='purchase_order.supplier_id', read_only=True
    )

    class Meta:
        model = PurchaseReceipt
        fields = (
            'id', 'purchase_order', 'order_number', 'company', 'branch', 'supplier',
            'idempotency_key', 'notes', 'divergence_reason', 'confirmed_by',
            'confirmed_at', 'items', 'created_at',
        )
        read_only_fields = fields


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    installments = PayableInstallmentSerializer(many=True, read_only=True)
    receipts = PurchaseReceiptSerializer(many=True, read_only=True)
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.trade_name', read_only=True)
    attachment = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = (
            'id', 'company', 'company_name', 'branch', 'branch_name', 'supplier',
            'supplier_name', 'order_number', 'order_type', 'status', 'gross_total',
            'global_discount', 'freight_total', 'other_expenses_total', 'payable_total',
             'document_number', 'document_key', 'document_series', 'document_date',
               'attachment', 'attachments', 'notes', 'exclusive_supplier_override',
               'created_by', 'placed_by', 'placed_at',
            'closed_by', 'closed_at', 'closure_reason', 'items', 'installments',
            'receipts', 'created_at', 'updated_at',
        )
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not _can(request, instance.branch_id, 'purchases.view_costs'):
            for field in (
                'gross_total', 'global_discount', 'freight_total',
                'other_expenses_total', 'payable_total',
            ):
                data.pop(field, None)
        if not _can(request, instance.branch_id, 'purchases.manage_payables'):
            data.pop('installments', None)
        return data

    def get_attachment(self, order):
        if not order.attachment:
            return None
        return {
            'name': purchase_attachment_download_name(order.attachment),
            'download_url': f'/api/v1/purchase-orders/{order.pk}/attachment/',
        }

    def get_attachments(self, order):
        return [
            {
                'id': attachment.pk,
                'name': purchase_attachment_download_name(attachment.attachment),
                'download_url': f'/api/v1/purchase-orders/{order.pk}/attachments/{attachment.pk}/download/',
                'status': attachment.status,
            }
            for attachment in order.attachments.filter(status='active')
        ]


class PurchaseItemInputSerializer(serializers.Serializer):
    product = serializers.IntegerField(
        min_value=1, max_value=MAX_BIGINT, required=False
    )
    product_supplier_unit = serializers.IntegerField(
        min_value=1, max_value=MAX_BIGINT, required=False, allow_null=True
    )
    purchase_presentation = serializers.IntegerField(
        min_value=1, max_value=MAX_BIGINT, required=False, allow_null=True
    )
    ordered_quantity = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal('0.000001')
    )
    purchase_unit_price = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal('0')
    )


class InstallmentInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0.01')
    )
    due_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class PurchaseOrderCreateSerializer(serializers.Serializer):
    branch = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    supplier = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    order_type = serializers.ChoiceField(choices=('ORDER', 'DIRECT'))
    items = PurchaseItemInputSerializer(many=True, allow_empty=False)
    global_discount = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0'), default=Decimal('0')
    )
    freight_total = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0'), default=Decimal('0')
    )
    other_expenses_total = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0'), default=Decimal('0')
    )
    document_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    document_key = serializers.CharField(max_length=100, required=False, allow_blank=True)
    document_series = serializers.CharField(max_length=30, required=False, allow_blank=True)
    document_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    installments = InstallmentInputSerializer(many=True, required=False)
    installment_count = serializers.IntegerField(min_value=1, max_value=120, required=False)
    first_due_date = serializers.DateField(required=False)
    exclusive_supplier_override = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if 'attachment_reference' in self.initial_data:
            raise serializers.ValidationError({
                'attachment_reference': 'Envie anexos pelo endpoint protegido da compra.'
            })
        if attrs.get('installments') and attrs.get('installment_count'):
            raise serializers.ValidationError({'installments': 'Informe parcelas manuais ou o número de parcelas, não ambos.'})
        if attrs.get('installment_count') and not attrs.get('first_due_date'):
            raise serializers.ValidationError({'first_due_date': 'Informe o primeiro vencimento para gerar as parcelas.'})
        return attrs


class PurchaseOrderUpdateSerializer(serializers.Serializer):
    global_discount = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0'), required=False
    )
    freight_total = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0'), required=False
    )
    other_expenses_total = serializers.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0'), required=False
    )
    document_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    document_key = serializers.CharField(max_length=100, required=False, allow_blank=True)
    document_series = serializers.CharField(max_length=30, required=False, allow_blank=True)
    document_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    installments = InstallmentInputSerializer(many=True, required=False)
    installment_count = serializers.IntegerField(min_value=1, max_value=120, required=False)
    first_due_date = serializers.DateField(required=False)

    def validate(self, attrs):
        if 'attachment_reference' in self.initial_data:
            raise serializers.ValidationError({
                'attachment_reference': 'Envie anexos pelo endpoint protegido da compra.'
            })
        if attrs.get('installments') and attrs.get('installment_count'):
            raise serializers.ValidationError({'installments': 'Informe parcelas manuais ou o número de parcelas, não ambos.'})
        if attrs.get('installment_count') and not attrs.get('first_due_date'):
            raise serializers.ValidationError({'first_due_date': 'Informe o primeiro vencimento para gerar as parcelas.'})
        return attrs


class PlacePurchaseOrderSerializer(serializers.Serializer):
    exclusive_supplier_override = serializers.BooleanField(required=False, default=False)


class ReceiptItemInputSerializer(serializers.Serializer):
    purchase_order_item = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    received_quantity = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal('0'), required=False
    )
    received_stock_quantity = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal('0'), required=False
    )
    divergence_reason = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        presentation = attrs.get('received_quantity')
        stock = attrs.get('received_stock_quantity')
        if presentation is None and stock is None:
            raise serializers.ValidationError(
                'Informe a quantidade recebida na apresentação ou na unidade de estoque.'
            )
        if presentation is not None and stock is not None:
            raise serializers.ValidationError(
                'Informe somente uma quantidade recebida.'
            )
        return attrs


class PurchaseReceiptCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    items = ReceiptItemInputSerializer(many=True, allow_empty=False)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    divergence_reason = serializers.CharField(required=False, allow_blank=True, default='')


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=2000)


class PayInstallmentSerializer(serializers.Serializer):
    payment_method = serializers.CharField(min_length=1, max_length=50)
    paid_amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.01'), required=False)
    paid_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class SetInstallmentsSerializer(serializers.Serializer):
    installments = InstallmentInputSerializer(many=True, allow_empty=False)


class PurchaseAttachmentSerializer(serializers.Serializer):
    attachment = serializers.FileField(max_length=120, allow_empty_file=False)

    def validate_attachment(self, value):
        if value.size > MAX_ATTACHMENT_SIZE:
            raise serializers.ValidationError('O anexo deve ter no maximo 10 MB.')
        try:
            validate_purchase_attachment(value)
        except Exception as error:
            messages = getattr(error, 'messages', None)
            raise serializers.ValidationError(messages or str(error)) from error
        return value
