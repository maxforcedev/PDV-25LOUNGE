from decimal import Decimal
import unicodedata

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.base.models import BaseModel
from apps.companies.models import Company, Status


def normalize_product_name(value):
    display_name = ' '.join((value or '').split())
    decomposed = unicodedata.normalize('NFKD', display_name)
    normalized_name = ''.join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()
    return display_name, normalized_name


class Category(BaseModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='product_categories'
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('sort_order', 'name', 'id')
        constraints = [
            models.UniqueConstraint(
                'company', Lower('name'), name='products_category_company_name_ci_unique'
            ),
        ]

    def clean(self):
        super().clean()
        self.name = ' '.join(self.name.split())

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company} - {self.name}'


class Unit(models.TextChoices):
    UNIT = 'un', 'UN'
    KILOGRAM = 'kg', 'KG'
    GRAM = 'g', 'G'
    LITER = 'l', 'L'
    MILLILITER = 'ml', 'ML'


class InventoryBehavior(models.TextChoices):
    DIRECT = 'direct', 'Estoque próprio'
    NONE = 'none', 'Sem estoque'
    COMPONENTS = 'components', 'Baixa por componentes'


class Product(BaseModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='products'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
    )
    name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=400, editable=False)
    description = models.TextField(blank=True)
    internal_code = models.CharField(max_length=100)
    barcode = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=5, choices=Unit.choices, default=Unit.UNIT)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sale_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    image = models.URLField(max_length=500, blank=True, null=True)
    is_sellable = models.BooleanField(default=True)
    is_favorite = models.BooleanField(default=False)
    inventory_behavior = models.CharField(
        max_length=20,
        choices=InventoryBehavior.choices,
        default=InventoryBehavior.DIRECT,
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('company__trade_name', 'name')
        constraints = [
            models.UniqueConstraint(
                'company',
                Lower('normalized_name'),
                name='products_product_company_normalized_name_unique',
            ),
            models.UniqueConstraint(
                'company',
                Lower('internal_code'),
                name='products_product_company_internal_code_ci_unique',
            ),
            models.UniqueConstraint(
                'company',
                Lower('barcode'),
                condition=~Q(barcode=''),
                name='products_product_company_barcode_ci_unique',
            ),
            models.CheckConstraint(
                condition=Q(cost__gte=0), name='products_product_cost_nonnegative'
            ),
            models.CheckConstraint(
                condition=Q(sale_price__gte=0),
                name='products_product_sale_price_nonnegative',
            ),
        ]

    def clean(self):
        super().clean()
        self.name, self.normalized_name = normalize_product_name(self.name)
        if not self.name:
            raise ValidationError({'name': 'Informe o nome do produto.'})
        if self.company_id and self.normalized_name:
            duplicate = Product.objects.filter(
                company_id=self.company_id, normalized_name=self.normalized_name
            )
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                raise ValidationError(
                    {'name': 'Já existe um produto com este nome nesta empresa.'}
                )
        self.internal_code = self.internal_code.strip()
        self.barcode = self.barcode.strip()
        if self.category_id and self.company_id:
            if self.category.company_id != self.company_id:
                raise ValidationError({'category': 'A categoria deve pertencer a empresa do produto.'})
        if self.pk:
            original_behavior = Product.objects.filter(pk=self.pk).values_list(
                'inventory_behavior', flat=True
            ).first()
            if original_behavior and self.inventory_behavior != original_behavior:
                raise ValidationError({
                    'inventory_behavior': 'O comportamento de estoque nao pode ser alterado.'
                })
            if (
                self.inventory_behavior != InventoryBehavior.DIRECT
                and self.used_as_component.exists()
            ):
                raise ValidationError(
                    {'inventory_behavior': 'Um insumo de outra composição deve manter estoque próprio.'}
                )
            if self.inventory_behavior == InventoryBehavior.COMPONENTS:
                if self.is_sellable and not self.components.exists():
                    raise ValidationError(
                        {'is_sellable': 'Informe ao menos um componente antes de habilitar a venda.'}
                    )
                for component in self.components.select_related('component_product'):
                    if component.component_product.company_id != self.company_id:
                        raise ValidationError(
                            {'inventory_behavior': 'A composição possui produto de outra empresa.'}
                        )
                    if (
                        component.component_product.inventory_behavior
                        != InventoryBehavior.DIRECT
                    ):
                        raise ValidationError(
                            {'inventory_behavior': 'A composição possui um componente sem estoque próprio.'}
                        )
            elif self.components.exists():
                raise ValidationError(
                    {'inventory_behavior': 'Remova a composição antes de alterar o comportamento.'}
                )
        elif self.inventory_behavior == InventoryBehavior.COMPONENTS and self.is_sellable:
            raise ValidationError(
                {'is_sellable': 'Um produto composto deve ser criado como não vendável.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company} - {self.name}'


class ProductComponent(BaseModel):
    parent_product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='components'
    )
    component_product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='used_as_component'
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        ordering = ('component_product__name',)
        constraints = [
            models.UniqueConstraint(
                fields=('parent_product', 'component_product'),
                name='products_component_pair_unique',
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name='products_component_quantity_positive'
            ),
            models.CheckConstraint(
                condition=~Q(parent_product=models.F('component_product')),
                name='products_component_not_self',
            ),
        ]

    def clean(self):
        super().clean()
        if not self.parent_product_id or not self.component_product_id:
            return
        if self.parent_product_id == self.component_product_id:
            raise ValidationError({'component_product': 'Um produto nao pode compor a si mesmo.'})
        if self.parent_product.company_id != self.component_product.company_id:
            raise ValidationError({'component_product': 'O componente deve pertencer a mesma empresa.'})
        if self.parent_product.inventory_behavior != InventoryBehavior.COMPONENTS:
            raise ValidationError({'parent_product': 'O produto deve baixar estoque por componentes.'})
        if self.component_product.inventory_behavior != InventoryBehavior.DIRECT:
            raise ValidationError({'component_product': 'Somente produtos com estoque próprio podem ser componentes.'})
        if (
            self.component_product.unit == Unit.UNIT
            and self.quantity != self.quantity.to_integral_value()
        ):
            raise ValidationError(
                {'quantity': 'A quantidade de um componente UN deve ser inteira.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.parent_product} <- {self.component_product}'


class BranchProductPrice(BaseModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='branch_prices'
    )
    branch = models.ForeignKey(
        'companies.Branch', on_delete=models.CASCADE, related_name='product_prices'
    )
    sale_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ('branch__name', 'product__name')
        constraints = [
            models.UniqueConstraint(
                fields=('product', 'branch'),
                name='products_branch_price_product_branch_unique',
            ),
            models.CheckConstraint(
                condition=Q(sale_price__gte=0),
                name='products_branch_price_nonnegative',
            ),
        ]

    def clean(self):
        super().clean()
        if self.product_id and self.branch_id and self.product.company_id != self.branch.company_id:
            raise ValidationError({'branch': 'A filial deve pertencer a empresa do produto.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product.name} @ {self.branch.name}: {self.sale_price}'
