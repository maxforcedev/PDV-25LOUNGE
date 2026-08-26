from decimal import ROUND_HALF_UP, Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import F, Q

from apps.base.models import BaseModel
from apps.companies.models import Branch, Company
from apps.products.models import InventoryBehavior, Product

from .content import exact_content_equivalent, exact_multiply_quantized
from .storage import PrivateLossStorage, loss_attachment_path, validate_loss_attachment


class Stock(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='stocks')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='stocks')
    current_quantity = models.DecimalField(
        max_digits=24, decimal_places=9, default=Decimal('0')
    )
    current_content = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    minimum_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0')
    )
    average_unit_cost = models.DecimalField(
        max_digits=28, decimal_places=12, blank=True, null=True
    )
    last_unit_cost = models.DecimalField(
        max_digits=28, decimal_places=12, blank=True, null=True
    )

    class Meta:
        ordering = ('product__name', 'branch__name')
        constraints = [
            models.UniqueConstraint(
                fields=('product', 'branch'), name='inventory_stock_product_branch_unique'
            ),
            models.CheckConstraint(
                condition=Q(minimum_quantity__gte=0),
                name='inventory_stock_minimum_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(average_unit_cost__isnull=True) | Q(average_unit_cost__gte=0),
                name='inventory_stock_average_cost_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(last_unit_cost__isnull=True) | Q(last_unit_cost__gte=0),
                name='inventory_stock_last_cost_nonnegative',
            ),
        ]

    def clean(self):
        super().clean()
        if not self.product_id or not self.branch_id:
            return
        if self.product.company_id != self.branch.company_id:
            raise ValidationError({'branch': 'A filial deve pertencer à empresa do produto.'})
        if self.product.inventory_behavior != InventoryBehavior.DIRECT:
            raise ValidationError({'product': 'Somente produtos com estoque próprio possuem saldo.'})
        try:
            config = self.product.fraction_config
        except ObjectDoesNotExist:
            config = None
        if config and config.tracking_active:
            expected_quantity = (
                (self.current_content / config.package_content).quantize(
                    Decimal('0.000000001'), rounding=ROUND_HALF_UP
                )
                if self.current_content is not None else None
            )
            if expected_quantity is None or self.current_quantity != expected_quantity:
                raise ValidationError(
                    {'current_quantity': 'A quantidade equivalente deve reconciliar com o conteudo.'}
                )
        elif self.current_content is not None:
            raise ValidationError(
                {'current_content': 'Conteudo exato exige rastreamento fracionado ativo.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def equivalent_quantity(self):
        try:
            config = self.product.fraction_config
        except ObjectDoesNotExist:
            config = None
        if config and config.tracking_active and self.current_content is not None:
            return exact_content_equivalent(
                self.current_content, config.package_content
            )
        return self.current_quantity

    def __str__(self):
        return f'{self.product} - {self.branch.name}: {self.current_quantity}'


class MovementType(models.TextChoices):
    ENTRY = 'entry', 'Entrada'
    EXIT = 'exit', 'Saída'
    ADJUSTMENT = 'adjustment', 'Ajuste'
    SALE = 'sale', 'Venda'
    SALE_CANCELLATION = 'sale_cancellation', 'Cancelamento de venda'
    CONSUMPTION = 'consumption', 'Consumação'
    CONSUMPTION_CANCELLATION = 'consumption_cancellation', 'Cancelamento de consumação'


class MovementNature(models.TextChoices):
    NORMAL = 'normal', 'Normal'
    BONUS = 'bonus', 'Bonificada'
    RETURN = 'return', 'Devolução'
    OPENING_BALANCE = 'opening_balance', 'Saldo inicial'
    CORRECTION = 'correction', 'Correção'
    TRANSFER = 'transfer', 'Transferência'
    DAMAGE = 'damage', 'Avaria'
    LOSS = 'loss', 'Perda'
    INTERNAL_USE = 'internal_use', 'Uso interno'
    INVENTORY = 'inventory', 'Inventário'
    REGULARIZATION = 'regularization', 'Regularização'
    BALANCE_CORRECTION = 'balance_correction', 'Correção de saldo'
    SALE = 'sale', 'Venda'
    CONSUMPTION = 'consumption', 'Consumação'
    CANCELLATION = 'cancellation', 'Cancelamento/estorno'
    PURCHASE = 'purchase', 'Compra'
    OTHER = 'other', 'Outros'


class InventoryOperationKind(models.TextChoices):
    MANUAL_ENTRY = 'manual_entry', 'Entrada manual'
    MANUAL_EXIT = 'manual_exit', 'Saída manual'
    MANUAL_ADJUSTMENT = 'manual_adjustment', 'Ajuste manual'
    GROUP_ENTRY = 'group_entry', 'Entrada em grupo'


class InventoryOperation(BaseModel):
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='inventory_operations'
    )
    idempotency_key = models.UUIDField(editable=False)
    kind = models.CharField(max_length=32, choices=InventoryOperationKind.choices)
    payload = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='inventory_operations',
    )

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'idempotency_key'),
                name='inventory_operation_branch_idempotency_unique',
            ),
        ]


class ProtectedInventoryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Alteracoes em massa no historico de estoque nao sao permitidas.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Alteracoes em massa no historico de estoque nao sao permitidas.')

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError('Criacoes em massa no historico de estoque nao sao permitidas.')

    def delete(self):
        raise ValidationError('O historico de estoque nao pode ser excluido fisicamente.')


class ProtectedInventoryModel(BaseModel):
    objects = ProtectedInventoryQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValidationError('O historico de estoque nao pode ser excluido fisicamente.')


class MovementDomainOrigin(models.TextChoices):
    LEGACY = 'LEGACY', 'Legado'
    MANUAL = 'MANUAL', 'Movimentacao manual'
    PURCHASE = 'PURCHASE', 'Recebimento de compra'
    TRANSFER_DISPATCH = 'TRANSFER_DISPATCH', 'Despacho de transferencia'
    TRANSFER_RECEIPT = 'TRANSFER_RECEIPT', 'Recebimento de transferencia'
    TRANSFER_RETURN = 'TRANSFER_RETURN', 'Retorno de transferencia'
    TRANSFER_CORRECTION = 'TRANSFER_CORRECTION', 'Correcao de transferencia'
    LOSS = 'LOSS', 'Registro de perda'
    INVENTORY_COUNT = 'INVENTORY_COUNT', 'Contagem de inventario'
    ORDER = 'ORDER', 'Confirmacao de OrderItem'
    ORDER_CANCELLATION = 'ORDER_CANCELLATION', 'Cancelamento de OrderItem'


class StockMovement(ProtectedInventoryModel):
    stock = models.ForeignKey(
        Stock, on_delete=models.PROTECT, related_name='movements'
    )
    movement_type = models.CharField(max_length=24, choices=MovementType.choices)
    nature = models.CharField(
        max_length=24, choices=MovementNature.choices, default=MovementNature.NORMAL
    )
    operation_reference = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    previous_quantity = models.DecimalField(max_digits=24, decimal_places=9)
    quantity = models.DecimalField(max_digits=24, decimal_places=9)
    final_quantity = models.DecimalField(max_digits=24, decimal_places=9)
    previous_content = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True, editable=False
    )
    content_quantity = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True, editable=False
    )
    final_content = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True, editable=False
    )
    unit_cost_snapshot = models.DecimalField(
        max_digits=28, decimal_places=12, blank=True, null=True, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='stock_movements',
    )
    reason = models.TextField(blank=True, default='')
    sale = models.ForeignKey(
        'sales.Sale',
        on_delete=models.PROTECT,
        related_name='stock_movements',
        blank=True,
        null=True,
    )
    order_item = models.ForeignKey(
        'commands.OrderItem',
        on_delete=models.PROTECT,
        related_name='stock_movements',
        blank=True,
        null=True,
    )
    original_movement = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        related_name='cancellation_movements',
        blank=True,
        null=True,
    )
    domain_origin = models.CharField(
        max_length=32,
        choices=MovementDomainOrigin.choices,
        default=MovementDomainOrigin.LEGACY,
        editable=False,
    )
    transfer_item = models.ForeignKey(
        'StockTransferItem',
        on_delete=models.PROTECT,
        related_name='stock_movements',
        blank=True,
        null=True,
        editable=False,
    )
    transfer_resolution = models.ForeignKey(
        'TransferDivergenceResolution',
        on_delete=models.PROTECT,
        related_name='stock_movements',
        blank=True,
        null=True,
        editable=False,
    )
    loss_record = models.ForeignKey(
        'LossRecord',
        on_delete=models.PROTECT,
        related_name='stock_movements',
        blank=True,
        null=True,
        editable=False,
    )
    inventory_count_item = models.ForeignKey(
        'InventoryCountItem',
        on_delete=models.PROTECT,
        related_name='stock_movements',
        blank=True,
        null=True,
        editable=False,
    )

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~Q(quantity=0)
                    | (Q(content_quantity__isnull=False) & ~Q(content_quantity=0))
                ),
                name='inventory_movement_quantity_nonzero',
            ),
            models.CheckConstraint(
                condition=Q(
                    movement_type__in=(MovementType.ENTRY, MovementType.SALE_CANCELLATION,
                                       MovementType.CONSUMPTION_CANCELLATION),
                    quantity__gt=0,
                )
                | Q(
                    movement_type__in=(MovementType.ENTRY, MovementType.SALE_CANCELLATION,
                                       MovementType.CONSUMPTION_CANCELLATION),
                    quantity=0,
                    content_quantity__gt=0,
                )
                | Q(
                    movement_type__in=(MovementType.EXIT, MovementType.SALE,
                                       MovementType.CONSUMPTION),
                    quantity__lt=0,
                )
                | Q(
                    movement_type__in=(MovementType.EXIT, MovementType.SALE,
                                       MovementType.CONSUMPTION),
                    quantity=0,
                    content_quantity__lt=0,
                )
                | Q(movement_type=MovementType.ADJUSTMENT),
                name='inventory_movement_quantity_sign',
            ),
            models.CheckConstraint(
                condition=(
                    Q(movement_type__in=(MovementType.ENTRY, MovementType.EXIT,
                                        MovementType.ADJUSTMENT), sale__isnull=True,
                      original_movement__isnull=True)
                    | Q(movement_type__in=(MovementType.SALE, MovementType.CONSUMPTION),
                        sale__isnull=False, original_movement__isnull=True)
                    | Q(
                        movement_type=MovementType.SALE,
                        sale__isnull=True,
                        order_item__isnull=False,
                        original_movement__isnull=True,
                        domain_origin=MovementDomainOrigin.ORDER,
                    )
                    | Q(movement_type__in=(MovementType.SALE_CANCELLATION,
                                            MovementType.CONSUMPTION_CANCELLATION),
                        sale__isnull=False, original_movement__isnull=False)
                    | Q(
                        movement_type=MovementType.SALE_CANCELLATION,
                        sale__isnull=True,
                        order_item__isnull=False,
                        original_movement__isnull=False,
                        domain_origin=MovementDomainOrigin.ORDER_CANCELLATION,
                    )
                ),
                name='inventory_movement_sales_links_coherent',
            ),
            models.UniqueConstraint(
                fields=('original_movement',),
                condition=Q(original_movement__isnull=False),
                name='inventory_movement_original_unique',
            ),
            models.UniqueConstraint(
                fields=('order_item', 'stock'),
                condition=Q(
                    order_item__isnull=False,
                    movement_type=MovementType.SALE,
                    domain_origin=MovementDomainOrigin.ORDER,
                    original_movement__isnull=True,
                ),
                name='inventory_order_item_stock_original_unique',
            ),
            models.CheckConstraint(
                condition=Q(unit_cost_snapshot__isnull=True) | Q(unit_cost_snapshot__gte=0),
                name='inventory_movement_cost_snapshot_nonnegative',
            ),
            models.UniqueConstraint(
                fields=('loss_record',),
                condition=Q(loss_record__isnull=False),
                name='inventory_movement_loss_record_unique',
            ),
            models.UniqueConstraint(
                fields=('inventory_count_item',),
                condition=Q(inventory_count_item__isnull=False),
                name='inventory_movement_count_item_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.reason = (self.reason or '').strip()
        exact_positive = self.quantity == 0 and self.content_quantity is not None and self.content_quantity > 0
        exact_negative = self.quantity == 0 and self.content_quantity is not None and self.content_quantity < 0
        if self.movement_type == MovementType.ENTRY and self.quantity <= 0 and not exact_positive:
            raise ValidationError({'quantity': 'Uma entrada deve ter quantidade positiva.'})
        if self.movement_type == MovementType.EXIT and self.quantity >= 0 and not exact_negative:
            raise ValidationError({'quantity': 'Uma saída deve ter quantidade negativa.'})
        negative_types = (MovementType.SALE, MovementType.CONSUMPTION)
        cancellation_types = (
            MovementType.SALE_CANCELLATION,
            MovementType.CONSUMPTION_CANCELLATION,
        )
        manual_types = (MovementType.ENTRY, MovementType.EXIT, MovementType.ADJUSTMENT)
        if self.movement_type in negative_types and self.quantity >= 0 and not exact_negative:
            raise ValidationError({'quantity': 'A baixa deve ter quantidade negativa.'})
        if self.movement_type in cancellation_types and self.quantity <= 0 and not exact_positive:
            raise ValidationError({'quantity': 'O estorno deve ter quantidade positiva.'})
        if self.movement_type in manual_types and (self.sale_id or self.original_movement_id):
            raise ValidationError({'sale': 'Movimentações manuais não podem ser vinculadas à venda.'})
        if self.movement_type in negative_types:
            is_order_confirmation = (
                self.movement_type == MovementType.SALE
                and self.domain_origin == MovementDomainOrigin.ORDER
                and self.order_item_id
                and not self.sale_id
            )
            if not self.sale_id and not is_order_confirmation:
                raise ValidationError({'sale': 'A venda é obrigatória para esta movimentação.'})
            if self.original_movement_id:
                raise ValidationError({'original_movement': 'Uma baixa não pode estornar outro movimento.'})
        if self.movement_type in cancellation_types:
            is_order_cancellation = (
                self.movement_type == MovementType.SALE_CANCELLATION
                and self.domain_origin == MovementDomainOrigin.ORDER_CANCELLATION
                and self.order_item_id
                and not self.sale_id
            )
            if (not self.sale_id and not is_order_cancellation) or not self.original_movement_id:
                raise ValidationError({'original_movement': 'O movimento original é obrigatório.'})
            else:
                original = self.original_movement
                expected_type = {
                    MovementType.SALE_CANCELLATION: MovementType.SALE,
                    MovementType.CONSUMPTION_CANCELLATION: MovementType.CONSUMPTION,
                }[self.movement_type]
                if original.movement_type != expected_type:
                    raise ValidationError({'original_movement': 'O tipo original não corresponde ao estorno.'})
                if original.stock_id != self.stock_id:
                    raise ValidationError({'original_movement': 'O estoque deve ser o mesmo do movimento original.'})
                original_belongs_to_command_sale = bool(
                    original.domain_origin == MovementDomainOrigin.ORDER
                    and original.order_item_id
                    and original.order_item.order.command.sale_id == self.sale_id
                )
                if self.sale_id and original.sale_id != self.sale_id and not original_belongs_to_command_sale:
                    raise ValidationError({'original_movement': 'A venda deve ser a mesma do movimento original.'})
                if is_order_cancellation and (
                    original.sale_id or original.order_item_id != self.order_item_id
                ):
                    raise ValidationError({'original_movement': 'O item original deve ser a confirmação pendente da comanda.'})
                if original.content_quantity is None and self.quantity != -original.quantity:
                    raise ValidationError({'quantity': 'O estorno deve inverter exatamente a quantidade original.'})
        if self.quantity == 0 and not (exact_positive or exact_negative):
            raise ValidationError({'quantity': 'A movimentação não pode ser zero.'})
        if self.final_quantity != self.previous_quantity + self.quantity:
            raise ValidationError({'final_quantity': 'O saldo final não confere.'})
        content_values = (
            self.previous_content, self.content_quantity, self.final_content,
        )
        if any(value is not None for value in content_values):
            if any(value is None for value in content_values):
                raise ValidationError({'content_quantity': 'O snapshot de conteudo deve ser completo.'})
            if self.final_content != self.previous_content + self.content_quantity:
                raise ValidationError({'final_content': 'O saldo final de conteudo nao confere.'})
            if self.original_movement_id and self.original_movement.content_quantity is not None and (
                self.content_quantity != -self.original_movement.content_quantity
            ):
                raise ValidationError(
                    {'content_quantity': 'O estorno deve inverter o conteudo original.'}
                )
        workflow_links = {
            MovementDomainOrigin.TRANSFER_DISPATCH: bool(self.transfer_item_id),
            MovementDomainOrigin.TRANSFER_RECEIPT: bool(self.transfer_item_id),
            MovementDomainOrigin.TRANSFER_RETURN: bool(
                self.transfer_item_id and self.transfer_resolution_id
            ),
            MovementDomainOrigin.TRANSFER_CORRECTION: bool(
                self.transfer_item_id and self.transfer_resolution_id
            ),
            MovementDomainOrigin.LOSS: bool(self.loss_record_id),
            MovementDomainOrigin.INVENTORY_COUNT: bool(self.inventory_count_item_id),
        }
        if self.domain_origin in workflow_links and not workflow_links[self.domain_origin]:
            raise ValidationError({'domain_origin': 'A origem de dominio exige o vinculo tipado correspondente.'})
        if self.domain_origin == MovementDomainOrigin.LOSS and self.nature != MovementNature.LOSS:
            raise ValidationError({'nature': 'Movimento de perda deve usar a natureza de perda.'})
        if (
            self.domain_origin == MovementDomainOrigin.INVENTORY_COUNT
            and self.nature != MovementNature.INVENTORY
        ):
            raise ValidationError({'nature': 'Movimento de contagem deve usar a natureza de inventario.'})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Movimentações de estoque são imutáveis.')
        if self.unit_cost_snapshot is None and self.stock_id:
            if self.original_movement_id:
                self.unit_cost_snapshot = (
                    self.original_movement.unit_cost_snapshot
                    if self.original_movement.unit_cost_snapshot is not None
                    else self.stock.product.cost
                )
            else:
                self.unit_cost_snapshot = (
                    self.stock.average_unit_cost
                    if self.stock.average_unit_cost is not None
                    else self.stock.product.cost
                )
        self.full_clean()
        return super().save(*args, **kwargs)

    def equivalent_quantity(self):
        if self.content_quantity is not None:
            try:
                config = self.stock.product.fraction_config
            except ObjectDoesNotExist:
                config = None
            if config and config.tracking_active:
                return exact_content_equivalent(
                    self.content_quantity, config.package_content
                )
        return self.quantity

    def legacy_equivalent_quantity(self):
        return self.quantity if self.content_quantity is None else None

    def exact_content_equivalent_quantity(self):
        if self.content_quantity is None:
            return None
        try:
            config = self.stock.product.fraction_config
        except ObjectDoesNotExist:
            return None
        if not config.tracking_active:
            return None
        return exact_content_equivalent(
            self.content_quantity, config.package_content
        )

    def delete(self, *args, **kwargs):
        raise ValidationError('Movimentações de estoque são imutáveis.')

    def __str__(self):
        return f'{self.get_movement_type_display()} - {self.stock} ({self.quantity})'


class StockTransferStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Rascunho'
    IN_TRANSIT = 'IN_TRANSIT', 'Em transito'
    PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Recebida parcialmente'
    RECEIVED = 'RECEIVED', 'Recebida'
    RECEIVED_WITH_DIVERGENCE = 'RECEIVED_WITH_DIVERGENCE', 'Recebida com divergencia'
    CANCELLED = 'CANCELLED', 'Cancelada'


class TransferCostSource(models.TextChoices):
    BRANCH_AVERAGE = 'BRANCH_AVERAGE', 'Custo medio da filial'
    PRODUCT_FALLBACK = 'PRODUCT_FALLBACK', 'Fallback do produto'


class StockTransfer(ProtectedInventoryModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='stock_transfers'
    )
    origin_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='outgoing_stock_transfers'
    )
    destination_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='incoming_stock_transfers'
    )
    status = models.CharField(
        max_length=32,
        choices=StockTransferStatus.choices,
        default=StockTransferStatus.DRAFT,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_stock_transfers',
    )
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='dispatched_stock_transfers',
        blank=True,
        null=True,
    )
    dispatched_at = models.DateTimeField(blank=True, null=True)
    dispatch_idempotency_key = models.UUIDField(blank=True, null=True, editable=False)
    dispatch_payload_fingerprint = models.CharField(
        max_length=64, blank=True, editable=False
    )
    dispatch_payload = models.JSONField(default=dict, blank=True, editable=False)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cancelled_stock_transfers',
        blank=True,
        null=True,
    )
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.CheckConstraint(
                condition=~Q(origin_branch=F('destination_branch')),
                name='inventory_transfer_distinct_branches',
            ),
            models.UniqueConstraint(
                fields=('origin_branch', 'dispatch_idempotency_key'),
                condition=Q(dispatch_idempotency_key__isnull=False),
                name='inventory_transfer_dispatch_idempotency_unique',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.origin_branch_id and self.destination_branch_id:
            if self.origin_branch_id == self.destination_branch_id:
                errors['destination_branch'] = 'A filial de destino deve ser diferente da origem.'
            if self.origin_branch.company_id != self.destination_branch.company_id:
                errors['destination_branch'] = 'Origem e destino devem pertencer a mesma empresa.'
            if self.company_id != self.origin_branch.company_id:
                errors['company'] = 'A empresa deve corresponder as filiais da transferencia.'
        dispatched_states = {
            StockTransferStatus.IN_TRANSIT,
            StockTransferStatus.PARTIALLY_RECEIVED,
            StockTransferStatus.RECEIVED,
            StockTransferStatus.RECEIVED_WITH_DIVERGENCE,
        }
        if self.status in dispatched_states and not (self.dispatched_by_id and self.dispatched_at):
            errors['dispatched_at'] = 'Transferencia despachada exige ator e data do despacho.'
        dispatch_metadata = (
            self.dispatch_idempotency_key,
            self.dispatch_payload_fingerprint,
            self.dispatch_payload,
        )
        if self.status in dispatched_states and not all(dispatch_metadata):
            errors['dispatch_idempotency_key'] = 'Despacho exige metadados idempotentes completos.'
        if self.status not in dispatched_states and any(dispatch_metadata):
            errors['dispatch_idempotency_key'] = 'Metadados de despacho so existem apos o despacho.'
        if self.status == StockTransferStatus.CANCELLED:
            if not (self.cancelled_by_id and self.cancelled_at and self.cancellation_reason.strip()):
                errors['cancellation_reason'] = 'Cancelamento exige ator, data e motivo.'
            if self.dispatched_at:
                errors['status'] = 'Transferencia despachada nao pode ser cancelada.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        allow_transition = getattr(self, '_allow_status_transition', False)
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                'status', 'company_id', 'origin_branch_id', 'destination_branch_id',
                'notes', 'created_by_id', 'dispatched_by_id', 'dispatched_at',
                'dispatch_idempotency_key', 'dispatch_payload_fingerprint',
                'dispatch_payload', 'cancelled_by_id', 'cancelled_at',
                'cancellation_reason',
            ).first()
            if previous and previous['status'] != self.status and not allow_transition:
                raise ValidationError({'status': 'Use o service auditado para alterar a transferencia.'})
            if previous and any(
                getattr(self, field) != previous[field]
                for field in (
                    'company_id', 'origin_branch_id', 'destination_branch_id',
                    'notes', 'created_by_id',
                )
            ):
                raise ValidationError('O escopo e o conteudo da transferencia sao imutaveis.')
            if previous and previous['status'] != StockTransferStatus.DRAFT and any(
                getattr(self, field) != previous[field]
                for field in (
                    'dispatched_by_id', 'dispatched_at', 'dispatch_idempotency_key',
                    'dispatch_payload_fingerprint', 'dispatch_payload',
                    'cancelled_by_id', 'cancelled_at', 'cancellation_reason',
                )
            ):
                raise ValidationError('Metadados de transicao da transferencia sao imutaveis.')
        self.full_clean()
        if allow_transition:
            del self._allow_status_transition
        return super().save(*args, **kwargs)


class StockTransferItem(ProtectedInventoryModel):
    transfer = models.ForeignKey(
        StockTransfer, on_delete=models.PROTECT, related_name='items'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='stock_transfer_items'
    )
    requested_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    dispatched_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, blank=True, null=True
    )
    origin_unit_cost_snapshot = models.DecimalField(
        max_digits=28, decimal_places=12, blank=True, null=True
    )
    origin_cost_source = models.CharField(
        max_length=24, choices=TransferCostSource.choices, blank=True
    )
    origin_sale_price_snapshot = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    product_name_snapshot = models.CharField(max_length=200)
    product_internal_code_snapshot = models.CharField(max_length=100)
    product_unit_snapshot = models.CharField(max_length=5)
    package_content_snapshot = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    content_unit_snapshot = models.CharField(max_length=2, blank=True)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(
                fields=('transfer', 'product'), name='inventory_transfer_product_unique'
            ),
            models.CheckConstraint(
                condition=Q(requested_quantity__gt=0)
                & (Q(dispatched_quantity__isnull=True) | Q(dispatched_quantity__gt=0))
                & (Q(origin_unit_cost_snapshot__isnull=True) | Q(origin_unit_cost_snapshot__gte=0))
                & (Q(origin_sale_price_snapshot__isnull=True) | Q(origin_sale_price_snapshot__gte=0)),
                name='inventory_transfer_item_values_valid',
            ),
        ]

    def clean(self):
        super().clean()
        if self.transfer_id and self.product_id:
            if self.product.company_id != self.transfer.company_id:
                raise ValidationError({'product': 'O produto deve pertencer a empresa da transferencia.'})
            if self.product.inventory_behavior != InventoryBehavior.DIRECT:
                raise ValidationError({'product': 'Somente produto com estoque proprio pode ser transferido.'})
        snapshot_values = (
            self.dispatched_quantity,
            self.origin_unit_cost_snapshot,
            self.origin_cost_source,
            self.origin_sale_price_snapshot,
        )
        populated = tuple(value not in (None, '') for value in snapshot_values)
        if any(populated) and not all(populated):
            raise ValidationError('O snapshot de despacho deve ser preenchido integralmente.')
        if self.dispatched_quantity is not None and self.dispatched_quantity != self.requested_quantity:
            raise ValidationError({'dispatched_quantity': 'O despacho deve preservar a quantidade solicitada.'})

    def save(self, *args, **kwargs):
        if self.pk and not getattr(self, '_allow_dispatch_snapshot', False):
            raise ValidationError('Itens de transferencia sao imutaveis fora do despacho.')
        self.full_clean()
        if hasattr(self, '_allow_dispatch_snapshot'):
            del self._allow_dispatch_snapshot
        return super().save(*args, **kwargs)


class ImmutableInventoryRecord(ProtectedInventoryModel):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Eventos confirmados de estoque sao imutaveis.')
        self.full_clean()
        return super().save(*args, **kwargs)


class StockTransferReceipt(ImmutableInventoryRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transfer = models.ForeignKey(
        StockTransfer, on_delete=models.PROTECT, related_name='receipts'
    )
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='stock_transfer_receipts'
    )
    destination_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='stock_transfer_receipts'
    )
    idempotency_key = models.UUIDField(editable=False)
    payload_fingerprint = models.CharField(max_length=64, editable=False)
    payload = models.JSONField(default=dict, editable=False)
    finalize = models.BooleanField(default=False, editable=False)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='received_stock_transfers',
    )
    received_at = models.DateTimeField()

    class Meta:
        ordering = ('-received_at', '-created_at')
        constraints = [
            models.UniqueConstraint(
                fields=('destination_branch', 'idempotency_key'),
                name='inventory_transfer_receipt_idempotency_unique',
            ),
        ]

    def clean(self):
        super().clean()
        if self.transfer_id:
            if self.company_id != self.transfer.company_id:
                raise ValidationError({'company': 'A empresa nao corresponde a transferencia.'})
            if self.destination_branch_id != self.transfer.destination_branch_id:
                raise ValidationError({'destination_branch': 'A filial nao corresponde ao destino.'})


class StockTransferReceiptItem(ImmutableInventoryRecord):
    receipt = models.ForeignKey(
        StockTransferReceipt, on_delete=models.PROTECT, related_name='items'
    )
    transfer_item = models.ForeignKey(
        StockTransferItem, on_delete=models.PROTECT, related_name='receipt_items'
    )
    dispatched_quantity_snapshot = models.DecimalField(max_digits=14, decimal_places=3)
    previously_received_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    received_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    accumulated_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    pending_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost_snapshot = models.DecimalField(max_digits=28, decimal_places=12)
    received_content_snapshot = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )

    class Meta:
        ordering = ('transfer_item_id', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('receipt', 'transfer_item'),
                name='inventory_transfer_receipt_item_unique',
            ),
            models.CheckConstraint(
                condition=Q(dispatched_quantity_snapshot__gt=0)
                & Q(previously_received_quantity__gte=0)
                & Q(received_quantity__gt=0)
                & Q(accumulated_quantity__gt=0)
                & Q(pending_quantity__gte=0)
                & Q(unit_cost_snapshot__gte=0),
                name='inventory_transfer_receipt_item_values_valid',
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.receipt_id and self.transfer_item_id
            and self.receipt.transfer_id != self.transfer_item.transfer_id
        ):
            raise ValidationError({'transfer_item': 'O item nao pertence a transferencia recebida.'})
        if self.accumulated_quantity != (
            self.previously_received_quantity + self.received_quantity
        ):
            raise ValidationError({'accumulated_quantity': 'O acumulado do recebimento nao confere.'})
        if self.pending_quantity != (
            self.dispatched_quantity_snapshot - self.accumulated_quantity
        ):
            raise ValidationError({'pending_quantity': 'O pendente do recebimento nao confere.'})


class TransferDivergenceStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pendente'
    RESOLVED = 'RESOLVED', 'Resolvida'


class TransferDivergence(ProtectedInventoryModel):
    transfer_item = models.OneToOneField(
        StockTransferItem, on_delete=models.PROTECT, related_name='divergence'
    )
    dispatched_quantity_snapshot = models.DecimalField(max_digits=14, decimal_places=3)
    received_quantity_snapshot = models.DecimalField(max_digits=14, decimal_places=3)
    initial_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    resolved_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0')
    )
    pending_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    status = models.CharField(
        max_length=10,
        choices=TransferDivergenceStatus.choices,
        default=TransferDivergenceStatus.PENDING,
    )
    detected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='detected_transfer_divergences',
    )
    detected_at = models.DateTimeField()

    class Meta:
        ordering = ('-detected_at', '-id')
        constraints = [
            models.CheckConstraint(
                condition=Q(dispatched_quantity_snapshot__gt=0)
                & Q(received_quantity_snapshot__gte=0)
                & Q(initial_quantity__gt=0)
                & Q(resolved_quantity__gte=0)
                & Q(pending_quantity__gte=0),
                name='inventory_transfer_divergence_values_valid',
            ),
        ]

    def save(self, *args, **kwargs):
        allow_resolution = getattr(self, '_allow_resolution', False)
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                'transfer_item_id', 'dispatched_quantity_snapshot',
                'received_quantity_snapshot', 'initial_quantity', 'resolved_quantity',
                'pending_quantity', 'status', 'detected_by_id', 'detected_at',
            ).first()
            if not allow_resolution:
                raise ValidationError('Divergencias somente podem mudar pelo service de resolucao.')
            if previous and any(
                getattr(self, field) != previous[field]
                for field in (
                    'transfer_item_id', 'dispatched_quantity_snapshot',
                    'received_quantity_snapshot', 'initial_quantity',
                    'detected_by_id', 'detected_at',
                )
            ):
                raise ValidationError('A origem e os snapshots da divergencia sao imutaveis.')
        self.full_clean()
        if hasattr(self, '_allow_resolution'):
            del self._allow_resolution
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.initial_quantity != (
            self.dispatched_quantity_snapshot - self.received_quantity_snapshot
        ):
            raise ValidationError({'initial_quantity': 'A divergencia inicial nao confere.'})
        if self.initial_quantity != self.resolved_quantity + self.pending_quantity:
            raise ValidationError({'pending_quantity': 'A reconciliacao da divergencia nao confere.'})
        expected_status = (
            TransferDivergenceStatus.RESOLVED
            if self.pending_quantity == 0
            else TransferDivergenceStatus.PENDING
        )
        if self.status != expected_status:
            raise ValidationError({'status': 'O status nao corresponde a quantidade pendente.'})


class TransferResolutionType(models.TextChoices):
    FOUND_RECEIPT = 'FOUND_RECEIPT', 'Item localizado e recebido'
    RETURN_TO_ORIGIN = 'RETURN_TO_ORIGIN', 'Retorno confirmado a origem'
    LOSS_IN_TRANSIT = 'LOSS_IN_TRANSIT', 'Perda em transito'
    AUTHORIZED_CORRECTION = 'AUTHORIZED_CORRECTION', 'Correcao autorizada de separacao'


class TransferDivergenceResolution(ImmutableInventoryRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    divergence = models.ForeignKey(
        TransferDivergence, on_delete=models.PROTECT, related_name='resolutions'
    )
    idempotency_key = models.UUIDField(editable=False)
    payload_fingerprint = models.CharField(max_length=64, editable=False)
    resolution_type = models.CharField(max_length=32, choices=TransferResolutionType.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    observation = models.TextField()
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='transfer_divergence_resolutions',
    )
    resolved_at = models.DateTimeField()

    class Meta:
        ordering = ('resolved_at', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('divergence', 'idempotency_key'),
                name='inventory_transfer_resolution_idempotency_unique',
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name='inventory_transfer_resolution_quantity_positive'
            ),
        ]

    def clean(self):
        super().clean()
        self.observation = (self.observation or '').strip()
        if len(self.observation) < 3:
            raise ValidationError({'observation': 'Informe a observacao da resolucao.'})


class LossReason(models.TextChoices):
    BREAKAGE = 'BREAKAGE', 'Quebra'
    EXPIRATION = 'EXPIRATION', 'Vencimento'
    DAMAGE = 'DAMAGE', 'Avaria'
    INTERNAL_USE = 'INTERNAL_USE', 'Consumo interno'
    MISPLACEMENT = 'MISPLACEMENT', 'Extravio'
    OPERATIONAL_ERROR = 'OPERATIONAL_ERROR', 'Erro operacional'
    OTHER = 'OTHER', 'Outro'


class LossRecord(ImmutableInventoryRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='inventory_losses'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='inventory_losses'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='inventory_losses'
    )
    idempotency_key = models.UUIDField(editable=False)
    payload_fingerprint = models.CharField(max_length=64, editable=False)
    quantity = models.DecimalField(max_digits=24, decimal_places=9)
    content_quantity = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    content_unit = models.CharField(max_length=2, blank=True)
    package_content_snapshot = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    reason = models.CharField(max_length=24, choices=LossReason.choices)
    observation = models.TextField(blank=True, default='')
    attachment = models.FileField(
        upload_to=loss_attachment_path,
        storage=PrivateLossStorage(),
        validators=(validate_loss_attachment,),
        max_length=500,
        blank=True,
    )
    unit_cost_snapshot = models.DecimalField(max_digits=28, decimal_places=12)
    sale_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    cost_impact = models.DecimalField(max_digits=30, decimal_places=12)
    potential_sale_value = models.DecimalField(max_digits=30, decimal_places=12)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_inventory_losses',
    )
    recorded_at = models.DateTimeField()

    class Meta:
        ordering = ('-recorded_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'idempotency_key'),
                name='inventory_loss_idempotency_unique',
            ),
            models.CheckConstraint(
                condition=(Q(quantity__gt=0) | Q(quantity=0, content_quantity__gt=0))
                & Q(unit_cost_snapshot__gte=0)
                & Q(sale_price_snapshot__gte=0)
                & Q(cost_impact__gte=0)
                & Q(potential_sale_value__gte=0),
                name='inventory_loss_values_valid',
            ),
        ]

    def clean(self):
        super().clean()
        self.observation = (self.observation or '').strip()
        if self.reason == LossReason.OTHER and len(self.observation) < 3:
            raise ValidationError({'observation': 'Descreva a perda quando o motivo for Outro.'})
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            raise ValidationError({'branch': 'A filial deve pertencer a empresa da perda.'})
        if self.product_id and self.company_id and self.product.company_id != self.company_id:
            raise ValidationError({'product': 'O produto deve pertencer a empresa da perda.'})
        valuation_quantity = (
            exact_content_equivalent(
                self.content_quantity, self.package_content_snapshot
            )
            if self.content_quantity is not None and self.package_content_snapshot is not None
            else self.quantity
        )
        if self.content_quantity is not None and self.package_content_snapshot is None:
            raise ValidationError({'package_content_snapshot': 'Informe o conteudo da embalagem.'})
        if self.cost_impact != exact_multiply_quantized(
            valuation_quantity, self.unit_cost_snapshot
        ):
            raise ValidationError({'cost_impact': 'O impacto de custo nao confere.'})
        if self.potential_sale_value != exact_multiply_quantized(
            valuation_quantity, self.sale_price_snapshot
        ):
            raise ValidationError({'potential_sale_value': 'O valor potencial nao confere.'})


class InventoryCountStatus(models.TextChoices):
    OPEN = 'OPEN', 'Aberto'
    CONFIRMED = 'CONFIRMED', 'Confirmado'


class InventoryCountMode(models.TextChoices):
    FULL = 'FULL', 'Contagem completa'
    PARTIAL = 'PARTIAL', 'Contagem parcial'


class InventoryCount(ProtectedInventoryModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='inventory_counts'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='inventory_counts'
    )
    status = models.CharField(
        max_length=12, choices=InventoryCountStatus.choices, default=InventoryCountStatus.OPEN
    )
    mode = models.CharField(
        max_length=10, choices=InventoryCountMode.choices,
        default=InventoryCountMode.PARTIAL,
    )
    observation = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_inventory_counts',
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='confirmed_inventory_counts',
        blank=True,
        null=True,
    )
    confirmed_at = models.DateTimeField(blank=True, null=True)
    confirmation_idempotency_key = models.UUIDField(blank=True, null=True, editable=False)

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'confirmation_idempotency_key'),
                condition=Q(confirmation_idempotency_key__isnull=False),
                name='inventory_count_confirmation_idempotency_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.observation = (self.observation or '').strip()
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            raise ValidationError({'branch': 'A filial deve pertencer a empresa do inventario.'})
        if self.status == InventoryCountStatus.CONFIRMED and not (
            self.confirmed_by_id and self.confirmed_at and self.confirmation_idempotency_key
        ):
            raise ValidationError({'confirmed_at': 'Inventario confirmado exige ator, data e chave.'})

    def save(self, *args, **kwargs):
        allow_confirmation = getattr(self, '_allow_confirmation', False)
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                'status', 'company_id', 'branch_id', 'mode', 'observation', 'created_by_id',
                'confirmed_by_id', 'confirmed_at', 'confirmation_idempotency_key',
            ).first()
            if previous and previous['status'] != self.status and not allow_confirmation:
                raise ValidationError({'status': 'Use o service auditado para confirmar o inventario.'})
            if previous and any(
                getattr(self, field) != previous[field]
                for field in ('company_id', 'branch_id', 'mode', 'observation', 'created_by_id')
            ):
                raise ValidationError('O escopo e o conteudo do inventario sao imutaveis.')
            if previous and previous['status'] == InventoryCountStatus.CONFIRMED and any(
                getattr(self, field) != previous[field]
                for field in (
                    'confirmed_by_id', 'confirmed_at', 'confirmation_idempotency_key',
                )
            ):
                raise ValidationError('Metadados de confirmacao do inventario sao imutaveis.')
        self.full_clean()
        if allow_confirmation:
            del self._allow_confirmation
        return super().save(*args, **kwargs)


class InventoryCountItem(ImmutableInventoryRecord):
    inventory_count = models.ForeignKey(
        InventoryCount, on_delete=models.PROTECT, related_name='items'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='inventory_count_items'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='inventory_count_items'
    )
    theoretical_quantity = models.DecimalField(max_digits=24, decimal_places=9)
    counted_quantity = models.DecimalField(max_digits=24, decimal_places=9)
    difference_quantity = models.DecimalField(max_digits=24, decimal_places=9)
    theoretical_content = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    counted_complete_packages = models.DecimalField(
        max_digits=18, decimal_places=0, blank=True, null=True
    )
    counted_residual_content = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    counted_content = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    difference_content = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    content_unit = models.CharField(max_length=2, blank=True)
    package_content_snapshot = models.DecimalField(
        max_digits=24, decimal_places=9, blank=True, null=True
    )
    counted_at = models.DateTimeField()
    unit_cost_snapshot = models.DecimalField(max_digits=28, decimal_places=12)
    sale_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    cost_impact = models.DecimalField(max_digits=30, decimal_places=12)
    potential_sale_value = models.DecimalField(max_digits=30, decimal_places=12)
    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='inventory_count_items',
    )
    observation = models.TextField(blank=True)
    is_open = models.BooleanField(default=True, editable=False)
    closed_at = models.DateTimeField(blank=True, null=True, editable=False)

    class Meta:
        ordering = ('product__name', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('inventory_count', 'product'),
                name='inventory_count_product_unique',
            ),
            models.UniqueConstraint(
                fields=('branch', 'product'),
                condition=Q(is_open=True),
                name='inventory_open_count_branch_product_unique',
            ),
            models.CheckConstraint(
                condition=Q(counted_quantity__gte=0)
                & Q(unit_cost_snapshot__gte=0)
                & Q(sale_price_snapshot__gte=0),
                name='inventory_count_item_values_valid',
            ),
        ]

    def clean(self):
        super().clean()
        if self.inventory_count_id and self.product_id:
            if self.branch_id != self.inventory_count.branch_id:
                raise ValidationError({'branch': 'A filial deve corresponder ao inventario.'})
            if self.product.company_id != self.inventory_count.company_id:
                raise ValidationError({'product': 'O produto deve pertencer a empresa do inventario.'})
            if self.product.inventory_behavior != InventoryBehavior.DIRECT:
                raise ValidationError({'product': 'Somente produto com estoque proprio pode ser contado.'})
        if self.difference_quantity != self.counted_quantity - self.theoretical_quantity:
            raise ValidationError({'difference_quantity': 'A diferenca da contagem nao confere.'})
        content_values = (
            self.theoretical_content, self.counted_complete_packages,
            self.counted_residual_content, self.counted_content,
            self.difference_content,
        )
        if any(value is not None for value in content_values):
            if (
                any(value is None for value in content_values)
                or not self.content_unit
                or self.package_content_snapshot is None
            ):
                raise ValidationError({'counted_content': 'A contagem de conteudo deve ser completa.'})
            if self.difference_content != self.counted_content - self.theoretical_content:
                raise ValidationError({'difference_content': 'A diferenca de conteudo nao confere.'})
        valuation_difference = (
            exact_content_equivalent(
                self.difference_content, self.package_content_snapshot
            )
            if self.difference_content is not None else self.difference_quantity
        )
        if self.cost_impact != exact_multiply_quantized(
            valuation_difference, self.unit_cost_snapshot
        ):
            raise ValidationError({'cost_impact': 'O impacto de custo da contagem nao confere.'})
        if self.potential_sale_value != exact_multiply_quantized(
            valuation_difference, self.sale_price_snapshot
        ):
            raise ValidationError({'potential_sale_value': 'O valor potencial da contagem nao confere.'})
        if self.is_open and self.closed_at is not None:
            raise ValidationError({'closed_at': 'Item aberto nao pode possuir data de fechamento.'})
        if not self.is_open and self.closed_at is None:
            raise ValidationError({'closed_at': 'Item fechado exige data de fechamento.'})

    def save(self, *args, **kwargs):
        allow_close = getattr(self, '_allow_close', False)
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            previous = type(self).objects.filter(pk=self.pk).values().get()
            mutable = {'is_open', 'closed_at', 'updated_at'}
            changed = {
                field.attname
                for field in self._meta.concrete_fields
                if field.attname not in mutable
                and getattr(self, field.attname) != previous[field.attname]
            }
            if not allow_close or changed or not previous['is_open'] or self.is_open:
                raise ValidationError('Item de inventario somente pode ser fechado pelo service auditado.')
            self.full_clean()
            if hasattr(self, '_allow_close'):
                del self._allow_close
            return BaseModel.save(self, *args, **kwargs)
        return super().save(*args, **kwargs)
