import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.base.models import BaseModel
from apps.companies.models import Branch, Company, Status


class AttendanceCommandStatus(models.TextChoices):
    OPEN = 'open', 'Aberta'
    CLOSED = 'closed', 'Fechada'


class AttendanceOrderStatus(models.TextChoices):
    DRAFT = 'draft', 'Rascunho'
    CONFIRMED = 'confirmed', 'Confirmado'
    CANCELLED = 'cancelled', 'Cancelado'


class AttendanceOrderItemStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    CONFIRMED = 'confirmed', 'Confirmado'
    CANCELLED = 'cancelled', 'Cancelado'


class AttendancePaymentStatus(models.TextChoices):
    APPLIED = 'applied', 'Aplicado'
    REVERSED = 'reversed', 'Estornado'


class AttendanceOperationType(models.TextChoices):
    OPEN_TABLE = 'open_table', 'Abrir mesa'
    OPEN_COMMAND = 'open_command', 'Abrir comanda'
    ADD_ITEMS = 'add_items', 'Adicionar itens'
    TRANSFER_COMMAND = 'transfer_command', 'Transferir comanda'
    TRANSFER_ITEMS = 'transfer_items', 'Transferir itens'
    CANCEL_ITEM = 'cancel_item', 'Cancelar item'
    REVERSE_PAYMENT = 'reverse_payment', 'Estornar pagamento'
    GROUP_TABLES = 'group_tables', 'Agrupar mesas'
    SEPARATE_TABLE = 'separate_table', 'Separar mesa'
    REQUEST_BILL = 'request_bill', 'Solicitar conta'
    CLEAR_BILL = 'clear_bill', 'Limpar solicitação de conta'
    TABLE_OPEN = 'table_open', 'Abrir atendimento de mesa'
    TABLE_ORDER = 'table_order', 'Salvar pedido de mesa'
    TABLE_PAYMENT = 'table_payment', 'Registrar pagamento de mesa'
    TABLE_REVERSE_PAYMENT = 'table_reverse_payment', 'Estornar pagamento de mesa'
    TABLE_CANCEL_ITEM = 'table_cancel_item', 'Cancelar item de mesa'
    TABLE_TRANSFER_ITEMS = 'table_transfer_items', 'Transferir itens de mesa'
    TABLE_BILL = 'table_bill', 'Solicitar conta de mesa'
    TABLE_CLOSE = 'table_close', 'Fechar atendimento de mesa'


class AttendanceCommand(BaseModel):
    """POS-5 persistent account. The legacy Table is only physical-layout input."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='attendance_commands')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='attendance_commands')
    table = models.ForeignKey(
        'commands.Table', on_delete=models.PROTECT, related_name='attendance_commands',
        blank=True, null=True,
    )
    number = models.CharField(max_length=50)
    identifier = models.CharField(max_length=100, blank=True, default='')
    customer = models.ForeignKey(
        'companies.Customer', on_delete=models.PROTECT, related_name='attendance_commands',
        blank=True, null=True,
    )
    is_primary = models.BooleanField(default=False)
    people_count = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    status = models.CharField(max_length=10, choices=AttendanceCommandStatus.choices, default=AttendanceCommandStatus.OPEN)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='opened_attendance_commands')
    opened_by_name_snapshot = models.CharField(max_length=200, blank=True, default='')
    table_name_snapshot = models.CharField(max_length=100, blank=True, default='')
    customer_name_snapshot = models.CharField(max_length=200, blank=True, default='')
    closed_at = models.DateTimeField(blank=True, null=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='closed_attendance_commands', blank=True, null=True)
    closed_by_name_snapshot = models.CharField(max_length=200, blank=True, default='')
    sale = models.OneToOneField('sales.Sale', on_delete=models.PROTECT, related_name='attendance_command', blank=True, null=True)
    checkout_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    checkout_service_fee_waived = models.BooleanField(default=False)
    equal_split_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    equal_split_people_count = models.PositiveIntegerField(null=True, blank=True)
    bill_requested_at = models.DateTimeField(blank=True, null=True)
    bill_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='requested_attendance_bills', blank=True, null=True,
    )

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'number'), condition=Q(status='open'),
                name='attendance_open_command_number_unique',
            ),
            models.UniqueConstraint(
                fields=('table',), condition=Q(table__isnull=False, is_primary=True, status='open'),
                name='attendance_one_open_primary_per_table',
            ),
            models.CheckConstraint(
                condition=Q(status='open') | Q(closed_at__isnull=False),
                name='attendance_closed_command_requires_timestamp',
            ),
        ]

    def clean(self):
        super().clean()
        self.identifier = ' '.join((self.identifier or '').split())
        self.notes = (self.notes or '').strip()
        errors = {}
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            errors['branch'] = 'A filial deve pertencer à empresa da comanda.'
        if self.table_id and self.table.branch_id != self.branch_id:
            errors['table'] = 'A mesa deve pertencer à filial da comanda.'
        if self.customer_id and (
            self.customer.company_id != self.company_id or self.customer.status != Status.ACTIVE
        ):
            errors['customer'] = 'O cliente deve estar ativo e pertencer à empresa da comanda.'
        if self.is_primary and not self.table_id:
            errors['is_primary'] = 'Somente uma comanda vinculada a mesa pode ser principal.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class AttendanceTableGroup(BaseModel):
    """Temporary physical-table grouping; commands remain attached to each table."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='attendance_table_groups')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='attendance_table_groups')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_attendance_table_groups')
    is_active = models.BooleanField(default=True)
    separated_at = models.DateTimeField(blank=True, null=True)
    separated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='separated_attendance_table_groups', blank=True, null=True,
    )


class AttendanceTableGroupMembership(BaseModel):
    group = models.ForeignKey(AttendanceTableGroup, on_delete=models.PROTECT, related_name='memberships')
    table = models.ForeignKey('commands.Table', on_delete=models.PROTECT, related_name='attendance_group_memberships')
    joined_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='joined_attendance_table_groups')
    left_at = models.DateTimeField(blank=True, null=True)
    left_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='left_attendance_table_groups', blank=True, null=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('table',), condition=Q(left_at__isnull=True),
                name='attendance_one_active_group_per_table',
            ),
        ]


class AttendanceOperation(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='attendance_operations')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='attendance_operations')
    operation_type = models.CharField(max_length=32, choices=AttendanceOperationType.choices)
    idempotency_key = models.UUIDField(editable=False)
    payload_fingerprint = models.CharField(max_length=64, editable=False)
    result = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'operation_type', 'idempotency_key'),
                name='attendance_operation_branch_type_idempotency_unique',
            ),
        ]


class AttendanceOrder(BaseModel):
    command = models.ForeignKey(AttendanceCommand, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=10, choices=AttendanceOrderStatus.choices, default=AttendanceOrderStatus.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_attendance_orders')

    class Meta:
        ordering = ('-created_at', '-id')


class AttendanceOrderItem(BaseModel):
    order = models.ForeignKey(AttendanceOrder, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='attendance_order_items')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    product_name = models.CharField(max_length=200)
    internal_code = models.CharField(max_length=100, blank=True, default='')
    category_id_snapshot = models.PositiveBigIntegerField(blank=True, null=True)
    category_name_snapshot = models.CharField(max_length=150, blank=True, default='')
    unit = models.CharField(max_length=5)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    base_unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    modifier_unit_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    modifier_snapshot = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default='')
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    component_cost_snapshot = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=AttendanceOrderItemStatus.choices, default=AttendanceOrderItemStatus.PENDING)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='confirmed_attendance_order_items', blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cancelled_attendance_order_items', blank=True, null=True)
    cancellation_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='attendance_order_item_quantity_positive'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='attendance_order_item_price_nonnegative'),
        ]

    def save(self, *args, **kwargs):
        self.notes = (self.notes or '').strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class AttendancePayment(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='attendance_payments')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='attendance_payments')
    command = models.ForeignKey(AttendanceCommand, on_delete=models.PROTECT, related_name='payments')
    payment_method = models.ForeignKey('sales.PaymentMethod', on_delete=models.PROTECT, related_name='attendance_payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    received_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    change_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cash_session = models.ForeignKey('cash.CashSession', on_delete=models.PROTECT, related_name='attendance_payments', null=True, blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='attendance_payments')
    status = models.CharField(max_length=10, choices=AttendancePaymentStatus.choices, default=AttendancePaymentStatus.APPLIED)
    idempotency_key = models.UUIDField(default=uuid.uuid4)
    reversal_of = models.OneToOneField('self', on_delete=models.PROTECT, related_name='reversal', null=True, blank=True)
    reversal_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(fields=('command', 'idempotency_key'), name='attendance_payment_idempotency_unique'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='attendance_payment_amount_positive'),
            models.CheckConstraint(condition=Q(received_amount__isnull=True) | Q(received_amount__gte=F('amount')), name='attendance_payment_received_gte_amount'),
            models.CheckConstraint(condition=Q(change_amount__isnull=True) | Q(change_amount__gte=0), name='attendance_payment_change_nonnegative'),
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
        elif self.received_amount is not None or self.change_amount is not None or self.cash_session_id:
            errors['payment_method'] = 'Somente dinheiro aceita recebido, troco ou sessão de caixa.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Pagamentos de comanda são imutáveis.')
        if self.payment_method_id and self.payment_method.code == 'cash' and self.received_amount is not None:
            self.change_amount = self.received_amount - self.amount
        self.full_clean()
        return super().save(*args, **kwargs)


class TableAttendanceStatus(models.TextChoices):
    OPEN = 'open', 'Aberto'
    CLOSED = 'closed', 'Fechado'


class TableAttendance(BaseModel):
    """The operational account for one physical table, independent from Command."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='table_attendances')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='table_attendances')
    table = models.ForeignKey('commands.Table', on_delete=models.PROTECT, related_name='table_attendances')
    people_count = models.PositiveIntegerField(null=True, blank=True)
    responsible_name = models.CharField(max_length=200, blank=True, default='')
    customer = models.ForeignKey(
        'companies.Customer', on_delete=models.PROTECT, related_name='table_attendances',
        blank=True, null=True,
    )
    notes = models.TextField(blank=True, default='')
    status = models.CharField(max_length=10, choices=TableAttendanceStatus.choices, default=TableAttendanceStatus.OPEN)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='opened_table_attendances')
    closed_at = models.DateTimeField(blank=True, null=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='closed_table_attendances', blank=True, null=True)
    sale = models.OneToOneField('sales.Sale', on_delete=models.PROTECT, related_name='table_attendance', blank=True, null=True)
    checkout_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    checkout_service_fee_waived = models.BooleanField(default=False)
    bill_requested_at = models.DateTimeField(blank=True, null=True)
    bill_requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_table_bills', blank=True, null=True)

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(fields=('table',), condition=Q(status='open'), name='table_attendance_one_open_per_table'),
            models.CheckConstraint(condition=Q(status='open') | Q(closed_at__isnull=False), name='table_attendance_closed_requires_timestamp'),
        ]

    def clean(self):
        super().clean()
        self.notes = (self.notes or '').strip()
        self.responsible_name = ' '.join((self.responsible_name or '').split())
        errors = {}
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            errors['branch'] = 'A filial deve pertencer à empresa do atendimento.'
        if self.table_id and self.table.branch_id != self.branch_id:
            errors['table'] = 'A mesa deve pertencer à filial do atendimento.'
        if self.customer_id and (self.customer.company_id != self.company_id or self.customer.status != Status.ACTIVE):
            errors['customer'] = 'O cliente deve estar ativo e pertencer à empresa.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TableOrder(BaseModel):
    attendance = models.ForeignKey(TableAttendance, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=10, choices=AttendanceOrderStatus.choices, default=AttendanceOrderStatus.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_table_orders')

    class Meta:
        ordering = ('-created_at', '-id')


class TableOrderItem(BaseModel):
    order = models.ForeignKey(TableOrder, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='table_order_items')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    product_name = models.CharField(max_length=200)
    internal_code = models.CharField(max_length=100, blank=True, default='')
    category_id_snapshot = models.PositiveBigIntegerField(blank=True, null=True)
    category_name_snapshot = models.CharField(max_length=150, blank=True, default='')
    unit = models.CharField(max_length=5)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    base_unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    modifier_unit_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    modifier_snapshot = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default='')
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    component_cost_snapshot = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=AttendanceOrderItemStatus.choices, default=AttendanceOrderItemStatus.PENDING)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='confirmed_table_order_items', blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cancelled_table_order_items', blank=True, null=True)
    cancellation_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='table_order_item_quantity_positive'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='table_order_item_price_nonnegative'),
        ]


class TablePayment(BaseModel):
    attendance = models.ForeignKey(TableAttendance, on_delete=models.PROTECT, related_name='payments')
    payment_method = models.ForeignKey('sales.PaymentMethod', on_delete=models.PROTECT, related_name='table_payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    received_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    change_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cash_session = models.ForeignKey('cash.CashSession', on_delete=models.PROTECT, related_name='table_payments', null=True, blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='table_payments')
    status = models.CharField(max_length=10, choices=AttendancePaymentStatus.choices, default=AttendancePaymentStatus.APPLIED)
    idempotency_key = models.UUIDField(default=uuid.uuid4)
    reversal_of = models.OneToOneField('self', on_delete=models.PROTECT, related_name='reversal', null=True, blank=True)
    reversal_reason = models.TextField(blank=True, default='')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('attendance', 'idempotency_key'), name='table_payment_idempotency_unique'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='table_payment_amount_positive'),
            models.CheckConstraint(condition=Q(received_amount__isnull=True) | Q(received_amount__gte=F('amount')), name='table_payment_received_gte_amount'),
            models.CheckConstraint(condition=Q(change_amount__isnull=True) | Q(change_amount__gte=0), name='table_payment_change_nonnegative'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.attendance_id and self.payment_method_id and self.payment_method.company_id != self.attendance.company_id:
            errors['payment_method'] = 'A forma de pagamento deve pertencer à empresa.'
        if self.attendance_id and self.cash_session_id and self.cash_session.branch_id != self.attendance.branch_id:
            errors['cash_session'] = 'A sessão deve pertencer à filial.'
        if self.payment_method_id and self.payment_method.code == 'cash':
            if self.received_amount is None or self.received_amount < self.amount:
                errors['received_amount'] = 'Dinheiro exige valor recebido igual ou maior ao aplicado.'
        elif self.received_amount is not None or self.change_amount is not None or self.cash_session_id:
            errors['payment_method'] = 'Somente dinheiro aceita recebido, troco ou sessão de caixa.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Pagamentos de mesa são imutáveis.')
        if self.payment_method_id and self.payment_method.code == 'cash' and self.received_amount is not None:
            self.change_amount = self.received_amount - self.amount
        self.full_clean()
        return super().save(*args, **kwargs)


class TablePaymentAllocation(BaseModel):
    payment = models.ForeignKey(TablePayment, on_delete=models.PROTECT, related_name='allocations')
    item = models.ForeignKey(TableOrderItem, on_delete=models.PROTECT, related_name='payment_allocations', blank=True, null=True)
    person_number = models.PositiveIntegerField(blank=True, null=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    allocated_quantity = models.DecimalField(max_digits=14, decimal_places=3, blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='table_payment_allocation_amount_positive'),
            models.CheckConstraint(condition=Q(item__isnull=False) | Q(person_number__isnull=False), name='table_payment_allocation_target_required'),
            models.CheckConstraint(condition=Q(allocated_quantity__isnull=True) | Q(allocated_quantity__gt=0), name='table_payment_allocation_quantity_positive'),
            models.CheckConstraint(condition=Q(allocated_quantity__isnull=True) | Q(item__isnull=False), name='table_payment_allocation_quantity_requires_item'),
        ]
