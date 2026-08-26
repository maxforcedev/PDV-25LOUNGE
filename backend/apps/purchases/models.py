from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.base.models import BaseModel
from apps.companies.models import Branch, Company
from apps.products.models import Product
from apps.suppliers.models import ProductSupplier, ProductSupplierUnit, Supplier

from .storage import (
    PrivatePurchaseStorage,
    purchase_attachment_path,
    validate_purchase_attachment,
)


class ProtectedPurchaseQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Alteracoes em massa de compras nao sao permitidas.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Alteracoes em massa de compras nao sao permitidas.')

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError('Criacoes em massa de compras nao sao permitidas.')

    def delete(self):
        raise ValidationError('Registros de compra nao podem ser excluidos fisicamente.')


class ProtectedPurchaseModel(BaseModel):
    objects = ProtectedPurchaseQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValidationError('Registros de compra nao podem ser excluidos fisicamente.')


class PurchaseOrderType(models.TextChoices):
    ORDER = 'ORDER', 'Pedido de compra'
    DIRECT = 'DIRECT', 'Entrada direta'


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Rascunho'
    PLACED = 'PLACED', 'Realizado'
    PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Recebido parcialmente'
    RECEIVED = 'RECEIVED', 'Recebido'
    CANCELLED = 'CANCELLED', 'Cancelado'
    CLOSED_PARTIAL = 'CLOSED_PARTIAL', 'Parcial encerrado'


class PurchaseOrder(ProtectedPurchaseModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='purchase_orders'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='purchase_orders'
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchase_orders'
    )
    order_number = models.CharField(max_length=20)
    order_type = models.CharField(max_length=10, choices=PurchaseOrderType.choices)
    status = models.CharField(
        max_length=24,
        choices=PurchaseOrderStatus.choices,
        default=PurchaseOrderStatus.DRAFT,
    )
    gross_total = models.DecimalField(max_digits=16, decimal_places=2)
    global_discount = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0.00')
    )
    freight_total = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0.00')
    )
    other_expenses_total = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0.00')
    )
    payable_total = models.DecimalField(max_digits=16, decimal_places=2)
    document_number = models.CharField(max_length=100, blank=True)
    document_key = models.CharField(max_length=100, blank=True)
    document_series = models.CharField(max_length=30, blank=True)
    document_date = models.DateField(blank=True, null=True)
    attachment = models.FileField(
        upload_to=purchase_attachment_path,
        storage=PrivatePurchaseStorage(),
        validators=(validate_purchase_attachment,),
        max_length=500,
        blank=True,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_purchase_orders',
    )
    placed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='placed_purchase_orders',
        blank=True,
        null=True,
    )
    placed_at = models.DateTimeField(blank=True, null=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='closed_purchase_orders',
        blank=True,
        null=True,
    )
    closed_at = models.DateTimeField(blank=True, null=True)
    closure_reason = models.TextField(blank=True)

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'order_number'),
                name='purchases_order_company_number_unique',
            ),
            models.CheckConstraint(
                condition=Q(gross_total__gte=0)
                & Q(global_discount__gte=0)
                & Q(global_discount__lte=F('gross_total'))
                & Q(freight_total__gte=0)
                & Q(other_expenses_total__gte=0)
                & Q(payable_total__gte=0),
                name='purchases_order_amounts_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(
                    payable_total=(
                        F('gross_total') - F('global_discount')
                        + F('freight_total') + F('other_expenses_total')
                    )
                ),
                name='purchases_order_payable_total_coherent',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            errors['branch'] = 'A filial deve pertencer a empresa da compra.'
        if self.supplier_id and self.company_id and self.supplier.company_id != self.company_id:
            errors['supplier'] = 'O fornecedor deve pertencer a empresa da compra.'
        expected = (
            self.gross_total - self.global_discount
            + self.freight_total + self.other_expenses_total
        )
        if self.payable_total != expected:
            errors['payable_total'] = 'O total a pagar nao reconcilia com a compra.'
        if self.global_discount > self.gross_total:
            errors['global_discount'] = 'O desconto nao pode exceder o valor bruto.'
        if self.order_type == PurchaseOrderType.DIRECT and self.status not in (
            PurchaseOrderStatus.DRAFT,
            PurchaseOrderStatus.RECEIVED,
            PurchaseOrderStatus.CANCELLED,
        ):
            errors['status'] = 'Entrada direta somente pode estar em rascunho, recebida ou cancelada.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        allow_transition = getattr(self, '_allow_status_transition', False)
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                'status', 'gross_total', 'global_discount', 'freight_total',
                'other_expenses_total', 'payable_total', 'supplier_id', 'branch_id',
            ).first()
            if original:
                if (
                    self.status != original['status']
                    and not allow_transition
                ):
                    raise ValidationError({
                        'status': 'Transicoes de compra devem usar o service auditado.'
                    })
                commercial_changed = any(
                    getattr(self, field) != original[field]
                    for field in (
                        'gross_total', 'global_discount', 'freight_total',
                        'other_expenses_total', 'payable_total', 'supplier_id', 'branch_id',
                    )
                )
                if commercial_changed and original['status'] != PurchaseOrderStatus.DRAFT:
                    raise ValidationError(
                        'Valores comerciais nao podem mudar depois que a compra sai do rascunho.'
                    )
        self.full_clean()
        if allow_transition:
            del self._allow_status_transition
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.order_number} - {self.supplier.trade_name}'


class PurchaseOrderItem(ProtectedPurchaseModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name='items'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='purchase_order_items'
    )
    product_supplier = models.ForeignKey(
        ProductSupplier, on_delete=models.PROTECT, related_name='purchase_order_items',
        blank=True, null=True,
    )
    product_supplier_unit = models.ForeignKey(
        ProductSupplierUnit, on_delete=models.PROTECT, related_name='purchase_order_items',
        blank=True, null=True,
    )
    line_number = models.PositiveIntegerField()
    ordered_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    product_name = models.CharField(max_length=200)
    product_internal_code = models.CharField(max_length=100)
    product_stock_unit = models.CharField(max_length=5)
    supplier_name = models.CharField(max_length=200)
    supplier_tax_id = models.CharField(max_length=14, blank=True)
    supplier_product_code = models.CharField(max_length=100, blank=True)
    presentation_unit_code = models.CharField(max_length=20)
    presentation_description = models.CharField(max_length=200)
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6)
    purchase_unit_price = models.DecimalField(max_digits=18, decimal_places=6)
    gross_subtotal = models.DecimalField(max_digits=16, decimal_places=2)
    allocated_discount = models.DecimalField(max_digits=16, decimal_places=2)
    allocated_freight = models.DecimalField(max_digits=16, decimal_places=2)
    allocated_other_expenses = models.DecimalField(max_digits=16, decimal_places=2)
    effective_total = models.DecimalField(max_digits=16, decimal_places=2)
    effective_stock_unit_cost = models.DecimalField(max_digits=28, decimal_places=12)

    class Meta:
        ordering = ('line_number', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('purchase_order', 'line_number'),
                name='purchases_order_item_line_unique',
            ),
            models.CheckConstraint(
                condition=Q(ordered_quantity__gt=0)
                & Q(conversion_factor__gt=0)
                & Q(purchase_unit_price__gte=0)
                & Q(gross_subtotal__gte=0)
                & Q(allocated_discount__gte=0)
                & Q(allocated_freight__gte=0)
                & Q(allocated_other_expenses__gte=0)
                & Q(effective_total__gte=0)
                & Q(effective_stock_unit_cost__gte=0),
                name='purchases_order_item_amounts_valid',
            ),
        ]

    @property
    def ordered_stock_quantity(self):
        return self.ordered_quantity * self.conversion_factor

    def clean(self):
        super().clean()
        errors = {}
        if self.purchase_order_id and self.product_id:
            if self.product.company_id != self.purchase_order.company_id:
                errors['product'] = 'O produto deve pertencer a empresa da compra.'
        if self.product_supplier_id:
            if self.product_supplier.product_id != self.product_id:
                errors['product_supplier'] = 'A relacao comercial nao corresponde ao produto.'
            if self.purchase_order_id and self.product_supplier.supplier_id != self.purchase_order.supplier_id:
                errors['product_supplier'] = 'A relacao comercial nao corresponde ao fornecedor da compra.'
        if self.product_supplier_unit_id and self.product_supplier_id and self.product_supplier_unit.product_supplier_id != self.product_supplier_id:
            errors['product_supplier_unit'] = 'A apresentacao nao corresponde a relacao comercial.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            status = type(self).objects.filter(pk=self.pk).values_list(
                'purchase_order__status', flat=True
            ).first()
            if status != PurchaseOrderStatus.DRAFT:
                raise ValidationError(
                    'Itens de compra nao podem mudar depois que o pedido sai do rascunho.'
                )
        self.full_clean()
        return super().save(*args, **kwargs)


class ImmutableReceiptModel(ProtectedPurchaseModel):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Recebimentos confirmados sao imutaveis.')
        self.full_clean()
        return super().save(*args, **kwargs)


class PurchaseReceipt(ImmutableReceiptModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name='receipts'
    )
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='purchase_receipts'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='purchase_receipts'
    )
    idempotency_key = models.UUIDField(editable=False)
    payload_fingerprint = models.CharField(max_length=64, editable=False)
    payload = models.JSONField(default=dict, editable=False)
    notes = models.TextField(blank=True)
    divergence_reason = models.TextField(blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='confirmed_purchase_receipts',
    )
    confirmed_at = models.DateTimeField()

    class Meta:
        ordering = ('-confirmed_at', '-created_at')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'idempotency_key'),
                name='purchases_receipt_branch_idempotency_unique',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.purchase_order_id:
            if self.company_id != self.purchase_order.company_id:
                errors['company'] = 'A empresa nao corresponde a compra.'
            if self.branch_id != self.purchase_order.branch_id:
                errors['branch'] = 'A filial nao corresponde a compra.'
        if errors:
            raise ValidationError(errors)


class PurchaseReceiptItem(ImmutableReceiptModel):
    receipt = models.ForeignKey(
        PurchaseReceipt, on_delete=models.PROTECT, related_name='items'
    )
    purchase_order_item = models.ForeignKey(
        PurchaseOrderItem, on_delete=models.PROTECT, related_name='receipt_items'
    )
    ordered_quantity_snapshot = models.DecimalField(max_digits=18, decimal_places=6)
    previously_received_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    received_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    accumulated_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    pending_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    divergence_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    divergence_reason = models.TextField(blank=True)
    conversion_factor_snapshot = models.DecimalField(max_digits=18, decimal_places=6)
    stock_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    stock_content_quantity = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    stock_content_unit = models.CharField(max_length=2, blank=True)
    stock_package_content_snapshot = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    effective_stock_unit_cost_snapshot = models.DecimalField(
        max_digits=28, decimal_places=12
    )
    product_name_snapshot = models.CharField(max_length=200)
    supplier_name_snapshot = models.CharField(max_length=200)
    presentation_snapshot = models.CharField(max_length=200)

    class Meta:
        ordering = ('purchase_order_item__line_number', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('receipt', 'purchase_order_item'),
                name='purchases_receipt_item_unique',
            ),
            models.CheckConstraint(
                condition=Q(ordered_quantity_snapshot__gt=0)
                & Q(previously_received_quantity__gte=0)
                & Q(received_quantity__gte=0)
                & Q(accumulated_quantity__gte=0)
                & Q(pending_quantity__gte=0)
                & Q(conversion_factor_snapshot__gt=0)
                & Q(stock_quantity__gte=0)
                & Q(effective_stock_unit_cost_snapshot__gte=0),
                name='purchases_receipt_item_quantities_valid',
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.receipt_id and self.purchase_order_item_id
            and self.receipt.purchase_order_id != self.purchase_order_item.purchase_order_id
        ):
            raise ValidationError({
                'purchase_order_item': 'O item nao pertence a compra recebida.'
            })
        content_values = (
            self.stock_content_quantity,
            self.stock_package_content_snapshot,
            self.stock_content_unit or None,
        )
        if any(value is not None for value in content_values):
            if any(value is None for value in content_values):
                raise ValidationError({
                    'stock_content_quantity': 'O snapshot de conteudo deve ser completo.'
                })
            expected_content = (
                self.stock_quantity * self.stock_package_content_snapshot
            ).quantize(Decimal('0.000000001'))
            if self.stock_content_quantity != expected_content:
                raise ValidationError({
                    'stock_content_quantity': 'O conteudo recebido nao reconcilia com as embalagens.'
                })


class PayableInstallmentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pendente'
    PAID = 'PAID', 'Paga'
    CANCELLED = 'CANCELLED', 'Cancelada'


class PayableInstallment(ProtectedPurchaseModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name='installments'
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchase_installments'
    )
    installment_number = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=PayableInstallmentStatus.choices,
        default=PayableInstallmentStatus.PENDING,
    )
    paid_at = models.DateTimeField(blank=True, null=True)
    paid_amount = models.DecimalField(
        max_digits=16, decimal_places=2, blank=True, null=True
    )
    paid_payment_method = models.CharField(max_length=50, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='paid_purchase_installments',
        blank=True,
        null=True,
    )
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cancelled_purchase_installments',
        blank=True,
        null=True,
    )
    cancellation_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('due_date', 'installment_number', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('purchase_order', 'installment_number'),
                name='purchases_installment_number_unique',
            ),
            models.UniqueConstraint(
                fields=('purchase_order', 'due_date'),
                name='purchases_installment_due_date_unique',
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='purchases_installment_amount_positive',
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=PayableInstallmentStatus.PENDING,
                        paid_at__isnull=True,
                        paid_amount__isnull=True,
                        paid_payment_method='',
                        paid_by__isnull=True,
                        cancelled_at__isnull=True,
                        cancelled_by__isnull=True,
                        cancellation_reason='',
                    )
                    | Q(
                        status=PayableInstallmentStatus.PAID,
                        paid_at__isnull=False,
                        paid_amount__isnull=False,
                        paid_payment_method__gt='',
                        paid_by__isnull=False,
                        cancelled_at__isnull=True,
                        cancelled_by__isnull=True,
                        cancellation_reason='',
                    )
                    | Q(
                        status=PayableInstallmentStatus.CANCELLED,
                        paid_at__isnull=True,
                        paid_amount__isnull=True,
                        paid_payment_method='',
                        paid_by__isnull=True,
                        cancelled_at__isnull=False,
                        cancelled_by__isnull=False,
                    )
                ),
                name='purchases_installment_status_coherent',
            ),
        ]

    def clean(self):
        super().clean()
        if self.purchase_order_id and self.supplier_id != self.purchase_order.supplier_id:
            raise ValidationError({'supplier': 'O fornecedor deve ser o mesmo da compra.'})

    def save(self, *args, **kwargs):
        allow_transition = getattr(self, '_allow_status_transition', False)
        if self.pk:
            previous_status = type(self).objects.filter(pk=self.pk).values_list(
                'status', flat=True
            ).first()
            if (
                previous_status != self.status
                and not allow_transition
            ):
                raise ValidationError({
                    'status': 'Pagamento e cancelamento devem usar o service auditado.'
                })
        self.full_clean()
        if allow_transition:
            del self._allow_status_transition
        return super().save(*args, **kwargs)
