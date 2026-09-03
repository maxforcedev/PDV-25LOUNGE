import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.base.models import BaseModel
from apps.companies.models import Branch, Company, Status


class TableStatus(models.TextChoices):
    ACTIVE = 'active', 'Ativo'
    INACTIVE = 'inactive', 'Inativo'


class Table(BaseModel):
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='tables'
    )
    name = models.CharField(max_length=100)
    seats = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=TableStatus.choices, default=TableStatus.ACTIVE
    )

    class Meta:
        ordering = ('name', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'name'),
                condition=Q(status='active'),
                name='commands_table_branch_name_active_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        if not self.name:
            raise ValidationError({'name': 'O nome da mesa é obrigatório.'})
        if self.branch_id and self.branch.company.status != Status.ACTIVE:
            raise ValidationError({'branch': 'A empresa deve estar ativa.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.branch.name} — {self.name}'

    @property
    def company(self):
        return self.branch.company


class CommandStatus(models.TextChoices):
    OPEN = 'open', 'Aberta'
    CLOSED = 'closed', 'Fechada'


class CommandOperationType(models.TextChoices):
    TRANSFER = 'transfer'
    TRANSFER_ITEMS = 'transfer_items'
    MERGE = 'merge'
    SPLIT = 'split'


class CommandPaymentStatus(models.TextChoices):
    APPLIED = 'applied', 'Aplicado'
    REVERSED = 'reversed', 'Estornado'


class Command(BaseModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='commands'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='commands'
    )
    table = models.ForeignKey(
        Table, on_delete=models.PROTECT, related_name='commands',
        blank=True, null=True,
    )
    customer = models.ForeignKey(
        'companies.Customer', on_delete=models.PROTECT, related_name='commands',
        blank=True, null=True,
    )
    command_number = models.CharField(max_length=50)
    identifier = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(
        max_length=10, choices=CommandStatus.choices, default=CommandStatus.OPEN
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='opened_commands',
    )
    closed_at = models.DateTimeField(blank=True, null=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='closed_commands', blank=True, null=True,
    )
    sale = models.OneToOneField(
        'sales.Sale', on_delete=models.PROTECT,
        related_name='command', blank=True, null=True,
    )
    checkout_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    checkout_service_fee_waived = models.BooleanField(default=False)
    table_name_snapshot = models.CharField(max_length=100, blank=True, default='')
    customer_name_snapshot = models.CharField(max_length=200, blank=True, default='')
    opened_by_name_snapshot = models.CharField(max_length=200, blank=True, default='')
    closed_by_name_snapshot = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'command_number'),
                condition=Q(status='open'),
                name='commands_open_number_unique',
            ),
            models.CheckConstraint(
                condition=Q(status='open') | Q(closed_at__isnull=False),
                name='commands_closed_requires_timestamp',
            ),
        ]

    def clean(self):
        super().clean()
        self.identifier = ' '.join((self.identifier or '').split())
        if self.table_id and self.table.branch_id != self.branch_id:
            raise ValidationError({'table': 'A mesa deve pertencer à filial da comanda.'})
        if self.branch_id and self.branch.company_id != self.company_id:
            raise ValidationError({'branch': 'A filial deve pertencer à empresa da comanda.'})
        if self.customer_id and (
            self.customer.company_id != self.company_id
            or self.customer.status != Status.ACTIVE
        ):
            raise ValidationError({'customer': 'O cliente deve estar ativo e pertencer à empresa da comanda.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.branch.name} — {self.command_number}'


class CommandOperation(BaseModel):
    """Stores the completed result of an idempotent command operation."""
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='command_operations')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='command_operations')
    operation_type = models.CharField(max_length=20, choices=CommandOperationType.choices)
    idempotency_key = models.UUIDField(editable=False)
    payload_fingerprint = models.CharField(max_length=64, editable=False)
    result = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'operation_type', 'idempotency_key'),
                name='commands_operation_branch_type_idempotency_unique',
            ),
        ]


class CommandPayment(BaseModel):
    """Immutable tender ledger for an open command; reversals are new rows."""
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='command_payments')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='command_payments')
    command = models.ForeignKey(Command, on_delete=models.PROTECT, related_name='payments')
    payment_method = models.ForeignKey('sales.PaymentMethod', on_delete=models.PROTECT, related_name='command_payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    received_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    change_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cash_session = models.ForeignKey('cash.CashSession', on_delete=models.PROTECT, related_name='command_payments', null=True, blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='command_payments')
    status = models.CharField(max_length=10, choices=CommandPaymentStatus.choices, default=CommandPaymentStatus.APPLIED)
    idempotency_key = models.UUIDField()
    reversal_of = models.OneToOneField('self', on_delete=models.PROTECT, related_name='reversal', null=True, blank=True)
    reversal_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(fields=('command', 'idempotency_key'), name='commands_payment_idempotency_unique'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='commands_payment_amount_positive'),
            models.CheckConstraint(condition=Q(received_amount__isnull=True) | Q(received_amount__gte=F('amount')), name='commands_payment_received_gte_amount'),
            models.CheckConstraint(condition=Q(change_amount__isnull=True) | Q(change_amount__gte=0), name='commands_payment_change_nonnegative'),
            models.CheckConstraint(condition=Q(status='applied', reversal_of__isnull=True, reversal_reason='') | Q(status='reversed', reversal_of__isnull=False), name='commands_payment_status_coherent'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.command_id and (self.command.company_id != self.company_id or self.command.branch_id != self.branch_id):
            errors['command'] = 'A comanda deve pertencer à mesma empresa e filial.'
        if self.payment_method_id and self.payment_method.company_id != self.company_id:
            errors['payment_method'] = 'A forma de pagamento deve pertencer à empresa.'
        if self.cash_session_id and self.cash_session.branch_id != self.branch_id:
            errors['cash_session'] = 'A sessão deve pertencer à filial.'
        if self.payment_method_id and self.payment_method.code == 'cash':
            if self.received_amount is None or self.received_amount < self.amount:
                errors['received_amount'] = 'Dinheiro exige valor recebido igual ou maior ao aplicado.'
            elif self.change_amount != self.received_amount - self.amount:
                errors['change_amount'] = 'O troco deve ser a diferença entre recebido e aplicado.'
            if not self.cash_session_id:
                errors['cash_session'] = 'Dinheiro exige sessão de caixa.'
        elif self.received_amount is not None or self.change_amount is not None or self.cash_session_id:
            errors['payment_method'] = 'Somente dinheiro aceita recebido, troco ou sessão de caixa.'
        if self.status == CommandPaymentStatus.REVERSED and not self.reversal_reason.strip():
            errors['reversal_reason'] = 'Informe o motivo do estorno.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Pagamentos de comanda são imutáveis.')
        if self.payment_method_id and self.payment_method.code == 'cash' and self.received_amount is not None:
            self.change_amount = self.received_amount - self.amount
        self.full_clean()
        return super().save(*args, **kwargs)


class OrderStatus(models.TextChoices):
    DRAFT = 'draft', 'Rascunho'
    CONFIRMED = 'confirmed', 'Confirmado'
    CANCELLED = 'cancelled', 'Cancelado'


class Order(BaseModel):
    command = models.ForeignKey(
        Command, on_delete=models.PROTECT, related_name='orders'
    )
    status = models.CharField(
        max_length=10, choices=OrderStatus.choices, default=OrderStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='created_orders',
    )

    class Meta:
        ordering = ('-created_at', '-id')

    def __str__(self):
        return f'{self.command.command_number} — Order {self.pk}'


class OrderItemStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    CONFIRMED = 'confirmed', 'Confirmado'
    CANCELLED = 'cancelled', 'Cancelado'


class OrderItem(BaseModel):
    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='items'
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.PROTECT, related_name='order_items'
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    product_name = models.CharField(max_length=200)
    internal_code = models.CharField(max_length=100, blank=True)
    category_id_snapshot = models.PositiveBigIntegerField(blank=True, null=True)
    category_name_snapshot = models.CharField(max_length=150, blank=True, default='')
    unit = models.CharField(max_length=5)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    base_unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    modifier_unit_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    modifier_snapshot = models.JSONField(default=list, blank=True)
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    component_cost_snapshot = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=10, choices=OrderItemStatus.choices, default=OrderItemStatus.PENDING
    )
    confirmed_at = models.DateTimeField(blank=True, null=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='confirmed_order_items', blank=True, null=True,
    )
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='cancelled_order_items', blank=True, null=True,
    )
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='commands_order_item_quantity_positive'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='commands_order_item_price_nonnegative'),
            models.CheckConstraint(
                condition=Q(status__in=('confirmed', 'cancelled')) | Q(confirmed_at__isnull=True),
                name='commands_order_item_confirmed_requires_timestamp',
            ),
            models.CheckConstraint(
                condition=Q(status='cancelled') | Q(cancelled_at__isnull=True),
                name='commands_order_item_cancelled_requires_timestamp',
            ),
        ]

    def clean(self):
        super().clean()
        if self.status == OrderItemStatus.CANCELLED and not (self.cancellation_reason or '').strip():
            raise ValidationError({'cancellation_reason': 'Informe o motivo do cancelamento.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product_name} × {self.quantity}'

    @property
    def company(self):
        return self.order.command.company

    @property
    def branch(self):
        return self.order.command.branch
