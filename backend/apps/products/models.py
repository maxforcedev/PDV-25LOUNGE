from decimal import Decimal
import unicodedata

from django.conf import settings
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


class SalesChannel(models.TextChoices):
    COUNTER = 'counter', 'Balcao'
    TABLE = 'table', 'Mesa'
    COMMAND = 'command', 'Comanda'


class ContentUnit(models.TextChoices):
    MILLILITER = 'ml', 'ML'
    GRAM = 'g', 'G'


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
    sku = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=5, choices=Unit.choices, default=Unit.UNIT)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sale_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    image = models.URLField(max_length=500, blank=True, null=True)
    is_sellable = models.BooleanField(default=True)
    is_favorite = models.BooleanField(default=False)
    available_counter = models.BooleanField(default=True)
    available_table = models.BooleanField(default=True)
    available_command = models.BooleanField(default=True)
    participates_in_service_fee = models.BooleanField(default=True)
    participates_in_commission = models.BooleanField(default=True)
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
            models.UniqueConstraint(
                'company',
                Lower('sku'),
                condition=Q(sku__isnull=False) & ~Q(sku=''),
                name='products_product_company_sku_ci_unique',
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
        self.sku = (self.sku or '').strip() or None
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
            if self.status != Status.ACTIVE and self.used_as_fraction_component.filter(
                parent_product__is_sellable=True
            ).exists():
                raise ValidationError({
                    'status': 'O produto fracionavel e fonte de uma composicao vendavel.'
                })
            if (
                self.inventory_behavior != InventoryBehavior.DIRECT
                and self.used_as_component.exists()
            ):
                raise ValidationError(
                    {'inventory_behavior': 'Um insumo de outra composição deve manter estoque próprio.'}
                )
            if self.inventory_behavior == InventoryBehavior.COMPONENTS:
                if (
                    self.is_sellable
                    and not self.components.exists()
                    and not self.fraction_components.exists()
                ):
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
                for component in self.fraction_components.select_related(
                    'component_product__fraction_config'
                ):
                    if component.component_product.company_id != self.company_id:
                        raise ValidationError(
                            {'inventory_behavior': 'A composição fracionada possui produto de outra empresa.'}
                        )
                    if self.is_sellable:
                        source = component.component_product
                        try:
                            config = source.fraction_config
                        except FractionableProductConfig.DoesNotExist:
                            config = None
                        if source.status != Status.ACTIVE:
                            raise ValidationError({
                                'is_sellable': 'A composicao fracionada possui fonte inativa.'
                            })
                        if not config or not config.tracking_active:
                            raise ValidationError({
                                'is_sellable': 'Ative o rastreamento de todas as fontes fracionadas.'
                            })
            elif self.components.exists() or self.fraction_components.exists():
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
        if ProductFractionComponent.objects.filter(
            parent_product=self.parent_product,
            component_product=self.component_product,
        ).exists():
            raise ValidationError(
                {'component_product': 'Use apenas um modo de consumo para o componente.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.parent_product} <- {self.component_product}'


class ProtectedProductConfigurationQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Configuracoes de produto em massa exigem o fluxo auditado.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Configuracoes de produto em massa exigem o fluxo auditado.')

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError('Configuracoes de produto em massa exigem o fluxo auditado.')

    def delete(self):
        raise ValidationError('Configuracoes de produto nao podem ser excluidas em massa.')


class ProductBranchConfig(BaseModel):
    objects = ProtectedProductConfigurationQuerySet.as_manager()
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='branch_configs'
    )
    branch = models.ForeignKey(
        'companies.Branch', on_delete=models.CASCADE, related_name='product_configs'
    )
    is_available = models.BooleanField(default=True)
    available_counter = models.BooleanField(blank=True, null=True)
    available_table = models.BooleanField(blank=True, null=True)
    available_command = models.BooleanField(blank=True, null=True)

    class Meta:
        ordering = ('branch__name', 'product__name')
        constraints = [
            models.UniqueConstraint(
                fields=('product', 'branch'),
                name='products_branch_config_product_branch_unique',
            ),
        ]

    def clean(self):
        super().clean()
        if self.product_id and self.branch_id:
            if self.product.company_id != self.branch.company_id:
                raise ValidationError({'branch': 'A filial deve pertencer a empresa do produto.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def effective_channel(self, channel):
        field = f'available_{channel}'
        override = getattr(self, field)
        return getattr(self.product, field) if override is None else override


class FractionableProductConfig(BaseModel):
    objects = ProtectedProductConfigurationQuerySet.as_manager()
    product = models.OneToOneField(
        Product, on_delete=models.PROTECT, related_name='fraction_config'
    )
    package_content = models.DecimalField(max_digits=24, decimal_places=9)
    content_unit = models.CharField(max_length=2, choices=ContentUnit.choices)
    tracking_active = models.BooleanField(default=False, editable=False)
    activated_at = models.DateTimeField(blank=True, null=True, editable=False)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='activated_fraction_configs',
        blank=True,
        null=True,
        editable=False,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(package_content__gt=0),
                name='products_fraction_package_content_positive',
            ),
        ]

    def clean(self):
        super().clean()
        if self.product_id and (
            self.product.inventory_behavior != InventoryBehavior.DIRECT
            or self.product.unit != Unit.UNIT
        ):
            raise ValidationError(
                {'product': 'Somente produto DIRECT em UN pode ser fracionavel.'}
            )
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                'product_id', 'package_content', 'content_unit', 'tracking_active',
                'activated_at', 'activated_by_id',
            ).first()
            if original and original['product_id'] != self.product_id:
                raise ValidationError({'product': 'O produto da configuracao e imutavel.'})
            if original and original['tracking_active']:
                immutable = ('package_content', 'content_unit')
                if any(getattr(self, field) != original[field] for field in immutable):
                    raise ValidationError(
                        'Conteudo e unidade sao imutaveis depois da ativacao do rastreamento.'
                    )
                if not self.tracking_active:
                    raise ValidationError({'tracking_active': 'O rastreamento nao pode ser desativado.'})
                if (
                    self.activated_at != original['activated_at']
                    or self.activated_by_id != original['activated_by_id']
                ):
                    raise ValidationError('Os metadados de ativacao sao imutaveis.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.tracking_active:
            raise ValidationError('A configuracao com rastreamento ativo nao pode ser excluida.')
        if self.product.used_as_fraction_component.exists():
            raise ValidationError(
                'A configuracao e fonte de uma composicao fracionada e nao pode ser excluida.'
            )
        return super().delete(*args, **kwargs)


class ProductFractionComponent(BaseModel):
    objects = ProtectedProductConfigurationQuerySet.as_manager()
    parent_product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='fraction_components'
    )
    component_product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='used_as_fraction_component'
    )
    content_quantity = models.DecimalField(max_digits=24, decimal_places=9)

    class Meta:
        ordering = ('component_product__name',)
        constraints = [
            models.UniqueConstraint(
                fields=('parent_product', 'component_product'),
                name='products_fraction_component_pair_unique',
            ),
            models.CheckConstraint(
                condition=Q(content_quantity__gt=0),
                name='products_fraction_component_content_positive',
            ),
            models.CheckConstraint(
                condition=~Q(parent_product=models.F('component_product')),
                name='products_fraction_component_not_self',
            ),
        ]

    def clean(self):
        super().clean()
        if not self.parent_product_id or not self.component_product_id:
            return
        errors = {}
        if self.parent_product_id == self.component_product_id:
            errors['component_product'] = 'Um produto nao pode compor a si mesmo.'
        if self.parent_product.company_id != self.component_product.company_id:
            errors['component_product'] = 'O componente deve pertencer a mesma empresa.'
        if self.parent_product.inventory_behavior != InventoryBehavior.COMPONENTS:
            errors['parent_product'] = 'O produto deve baixar estoque por componentes.'
        if self.component_product.inventory_behavior != InventoryBehavior.DIRECT:
            errors['component_product'] = 'O componente deve possuir estoque proprio.'
        try:
            fraction_config = self.component_product.fraction_config
        except FractionableProductConfig.DoesNotExist:
            fraction_config = None
        if not fraction_config:
            errors['component_product'] = 'O componente deve possuir configuracao fracionavel.'
        elif self.parent_product.is_sellable and not fraction_config.tracking_active:
            errors['component_product'] = 'Ative o rastreamento antes de vender a composicao.'
        if self.parent_product.is_sellable and self.component_product.status != Status.ACTIVE:
            errors['component_product'] = 'A fonte fracionada deve estar ativa.'
        if ProductComponent.objects.filter(
            parent_product=self.parent_product,
            component_product=self.component_product,
        ).exists():
            errors['component_product'] = 'Use apenas um modo de consumo para o componente.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProductionDestination(BaseModel):
    objects = ProtectedProductConfigurationQuerySet.as_manager()
    branch = models.ForeignKey(
        'companies.Branch', on_delete=models.PROTECT, related_name='production_destinations'
    )
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=50)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('name', 'id')
        constraints = [
            models.UniqueConstraint(
                'branch', Lower('name'), name='products_destination_branch_name_ci_unique'
            ),
            models.UniqueConstraint(
                'branch', Lower('code'), name='products_destination_branch_code_ci_unique'
            ),
        ]

    @property
    def company_id(self):
        return self.branch.company_id

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        self.code = (self.code or '').strip().lower()
        if not self.name:
            raise ValidationError({'name': 'Informe o nome do destino.'})
        if not self.code:
            raise ValidationError({'code': 'Informe o codigo do destino.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProductProductionDestination(BaseModel):
    objects = ProtectedProductConfigurationQuerySet.as_manager()
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='production_destination_links'
    )
    destination = models.ForeignKey(
        ProductionDestination, on_delete=models.PROTECT, related_name='product_links'
    )

    class Meta:
        ordering = ('destination__name', 'product__name')
        constraints = [
            models.UniqueConstraint(
                fields=('product', 'destination'),
                name='products_product_destination_unique',
            ),
        ]

    def clean(self):
        super().clean()
        if self.product_id and self.destination_id:
            if self.product.company_id != self.destination.branch.company_id:
                raise ValidationError({'destination': 'O destino deve pertencer a empresa do produto.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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


class ModifierOptionType(models.TextChoices):
    ADD = 'add', 'Adicionar'
    REMOVE = 'remove', 'Remover'
    OBSERVATION = 'observation', 'Observação'


class ModifierGroup(BaseModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='modifier_groups'
    )
    name = models.CharField(max_length=100)
    is_required = models.BooleanField(default=False)
    min_selections = models.PositiveIntegerField(default=0)
    max_selections = models.PositiveIntegerField(blank=True, null=True)
    allow_option_quantity = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        ordering = ('sort_order', 'id')
        constraints = [
            models.UniqueConstraint(
                Lower('name'),
                condition=Q(company_id__isnull=False),
                name='products_modifier_group_company_name_ci_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        if not self.name:
            raise ValidationError({'name': 'O nome do grupo é obrigatório.'})
        if self.min_selections and self.max_selections is not None and self.min_selections > self.max_selections:
            raise ValidationError({'max_selections': 'O máximo não pode ser menor que o mínimo.'})
        if self.is_required and self.min_selections < 1:
            raise ValidationError({'min_selections': 'Grupo obrigatório exige mínimo de 1.'})
        if self.max_selections == 1 and self.allow_option_quantity:
            raise ValidationError({'allow_option_quantity': 'Seleção única não permite quantidade por opção.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company} — {self.name}'


class ModifierOption(BaseModel):
    modifier_group = models.ForeignKey(
        ModifierGroup, on_delete=models.PROTECT, related_name='options'
    )
    name = models.CharField(max_length=100)
    option_type = models.CharField(
        max_length=12, choices=ModifierOptionType.choices, default=ModifierOptionType.ADD
    )
    additional_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    sort_order = models.IntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        ordering = ('sort_order', 'id')
        constraints = [
            models.CheckConstraint(
                condition=Q(additional_price__gte=0),
                name='products_modifier_option_price_nonnegative',
            ),
            models.UniqueConstraint(
                fields=('modifier_group', 'name'),
                name='products_modifier_option_group_name_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        if not self.name:
            raise ValidationError({'name': 'O nome da opção é obrigatório.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.modifier_group.name} — {self.name}'


class ProductModifierGroup(BaseModel):
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='modifier_groups'
    )
    modifier_group = models.ForeignKey(
        ModifierGroup, on_delete=models.PROTECT, related_name='product_links'
    )
    sort_order = models.IntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        ordering = ('sort_order', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('product', 'modifier_group'),
                name='products_modifier_link_unique',
            ),
        ]

    def clean(self):
        super().clean()
        if self.product_id and self.modifier_group_id and self.product.company_id != self.modifier_group.company_id:
            raise ValidationError({'modifier_group': 'O grupo deve pertencer à mesma empresa do produto.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product.name} — {self.modifier_group.name}'
