import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

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

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.branch.name} — {self.command_number}'


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
