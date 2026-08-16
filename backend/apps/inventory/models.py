from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.base.models import BaseModel
from apps.companies.models import Branch
from apps.products.models import InventoryBehavior, Product


class Stock(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='stocks')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='stocks')
    current_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0')
    )
    minimum_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0')
    )

    class Meta:
        ordering = ('product__name', 'branch__name')
        constraints = [
            models.UniqueConstraint(
                fields=('product', 'branch'), name='inventory_stock_product_branch_unique'
            ),
            models.CheckConstraint(
                condition=Q(current_quantity__gte=0),
                name='inventory_stock_current_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(minimum_quantity__gte=0),
                name='inventory_stock_minimum_nonnegative',
            ),
        ]

    def clean(self):
        super().clean()
        if not self.product_id or not self.branch_id:
            return
        if self.product.company_id != self.branch.company_id:
            raise ValidationError({'branch': 'A filial deve pertencer a empresa do produto.'})
        if self.product.inventory_behavior != InventoryBehavior.DIRECT:
            raise ValidationError({'product': 'Somente produtos com estoque proprio possuem saldo.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product} - {self.branch.name}: {self.current_quantity}'


class MovementType(models.TextChoices):
    ENTRY = 'entry', 'Entrada'
    EXIT = 'exit', 'Saida'
    ADJUSTMENT = 'adjustment', 'Ajuste'
    SALE = 'sale', 'Venda'
    SALE_CANCELLATION = 'sale_cancellation', 'Cancelamento de venda'
    CONSUMPTION = 'consumption', 'Consumacao'
    CONSUMPTION_CANCELLATION = 'consumption_cancellation', 'Cancelamento de consumacao'


class StockMovement(BaseModel):
    stock = models.ForeignKey(
        Stock, on_delete=models.PROTECT, related_name='movements'
    )
    movement_type = models.CharField(max_length=24, choices=MovementType.choices)
    previous_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    final_quantity = models.DecimalField(max_digits=14, decimal_places=3)
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
    original_movement = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        related_name='cancellation_movements',
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=Q(previous_quantity__gte=0),
                name='inventory_movement_previous_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(final_quantity__gte=0),
                name='inventory_movement_final_nonnegative',
            ),
            models.CheckConstraint(
                condition=~Q(quantity=0), name='inventory_movement_quantity_nonzero'
            ),
            models.CheckConstraint(
                condition=Q(
                    movement_type__in=(MovementType.ENTRY, MovementType.SALE_CANCELLATION,
                                      MovementType.CONSUMPTION_CANCELLATION),
                    quantity__gt=0,
                )
                | Q(
                    movement_type__in=(MovementType.EXIT, MovementType.SALE,
                                      MovementType.CONSUMPTION),
                    quantity__lt=0,
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
                    | Q(movement_type__in=(MovementType.SALE_CANCELLATION,
                                           MovementType.CONSUMPTION_CANCELLATION),
                        sale__isnull=False, original_movement__isnull=False)
                ),
                name='inventory_movement_sales_links_coherent',
            ),
            models.UniqueConstraint(
                fields=('original_movement',),
                condition=Q(original_movement__isnull=False),
                name='inventory_movement_original_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.reason = (self.reason or '').strip()
        if self.movement_type == MovementType.ENTRY and self.quantity <= 0:
            raise ValidationError({'quantity': 'Uma entrada deve ter quantidade positiva.'})
        if self.movement_type == MovementType.EXIT and self.quantity >= 0:
            raise ValidationError({'quantity': 'Uma saida deve ter quantidade negativa.'})
        negative_types = (MovementType.SALE, MovementType.CONSUMPTION)
        cancellation_types = (
            MovementType.SALE_CANCELLATION,
            MovementType.CONSUMPTION_CANCELLATION,
        )
        manual_types = (MovementType.ENTRY, MovementType.EXIT, MovementType.ADJUSTMENT)
        if self.movement_type in negative_types and self.quantity >= 0:
            raise ValidationError({'quantity': 'A baixa deve ter quantidade negativa.'})
        if self.movement_type in cancellation_types and self.quantity <= 0:
            raise ValidationError({'quantity': 'O estorno deve ter quantidade positiva.'})
        if self.movement_type in manual_types and (self.sale_id or self.original_movement_id):
            raise ValidationError({'sale': 'Movimentacoes manuais nao podem ser vinculadas a venda.'})
        if self.movement_type in negative_types:
            if not self.sale_id:
                raise ValidationError({'sale': 'A venda e obrigatoria para esta movimentacao.'})
            if self.original_movement_id:
                raise ValidationError({'original_movement': 'Uma baixa nao pode estornar outro movimento.'})
        if self.movement_type in cancellation_types:
            if not self.sale_id or not self.original_movement_id:
                raise ValidationError({'original_movement': 'O movimento original e obrigatorio.'})
            else:
                original = self.original_movement
                expected_type = {
                    MovementType.SALE_CANCELLATION: MovementType.SALE,
                    MovementType.CONSUMPTION_CANCELLATION: MovementType.CONSUMPTION,
                }[self.movement_type]
                if original.movement_type != expected_type:
                    raise ValidationError({'original_movement': 'O tipo original nao corresponde ao estorno.'})
                if original.stock_id != self.stock_id or original.sale_id != self.sale_id:
                    raise ValidationError({'original_movement': 'Estoque e venda devem ser os mesmos do movimento original.'})
                if self.quantity != -original.quantity:
                    raise ValidationError({'quantity': 'O estorno deve inverter exatamente a quantidade original.'})
        if self.quantity == 0:
            raise ValidationError({'quantity': 'A movimentacao nao pode ser zero.'})
        if self.final_quantity != self.previous_quantity + self.quantity:
            raise ValidationError({'final_quantity': 'O saldo final nao confere.'})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Movimentacoes de estoque sao imutaveis.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Movimentacoes de estoque sao imutaveis.')

    def __str__(self):
        return f'{self.get_movement_type_display()} - {self.stock} ({self.quantity})'
