from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.base.models import BaseModel
from apps.companies.models import Company, Status
from apps.products.models import Product

from .validators import normalize_tax_id, validate_tax_id


class ProtectedSupplierQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            'Alterações em massa de fornecedores devem usar o fluxo auditado.'
        )

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            'Alterações em massa de fornecedores devem usar o fluxo auditado.'
        )

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(
            'Criações em massa de fornecedores não são permitidas.'
        )

    def delete(self):
        raise ValidationError(
            'Fornecedores e seus vínculos não podem ser excluídos fisicamente.'
        )


class ProtectedSupplierModel(BaseModel):
    objects = ProtectedSupplierQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValidationError(
            'Fornecedores e seus vínculos não podem ser excluídos fisicamente.'
        )


class Supplier(ProtectedSupplierModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='suppliers'
    )
    legal_name = models.CharField(max_length=200, blank=True)
    trade_name = models.CharField(max_length=200, blank=False)
    tax_id = models.CharField(
        max_length=14, blank=True, null=True, validators=[validate_tax_id]
    )
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    address = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('trade_name', 'legal_name', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'tax_id'),
                condition=Q(tax_id__isnull=False),
                name='suppliers_supplier_company_tax_id_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.legal_name = ' '.join((self.legal_name or '').split())
        self.trade_name = ' '.join((self.trade_name or '').split())
        self.tax_id = normalize_tax_id(self.tax_id)
        validate_tax_id(self.tax_id)
        self.phone = self.phone.strip()
        self.email = self.email.strip().lower()
        self.contact_name = ' '.join(self.contact_name.split())
        errors = {}
        if not self.trade_name:
            errors['trade_name'] = 'Informe o nome fantasia.'
        if not isinstance(self.address, dict):
            errors['address'] = 'Informe o endereço como um objeto.'
        if self.pk:
            original_company_id = type(self).objects.filter(pk=self.pk).values_list(
                'company_id', flat=True
            ).first()
            if original_company_id and self.company_id != original_company_id:
                errors['company'] = 'A empresa do fornecedor não pode ser alterada.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company} - {self.trade_name}'


class ProductSupplier(ProtectedSupplierModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='product_suppliers'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='product_suppliers'
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='product_suppliers'
    )
    supplier_code = models.CharField(max_length=100, blank=True)
    is_preferred = models.BooleanField(default=False)
    is_exclusive = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('product__name', '-is_exclusive', '-is_preferred', 'supplier__trade_name')
        constraints = [
            models.UniqueConstraint(
                fields=('product', 'supplier'),
                name='suppliers_product_supplier_pair_unique',
            ),
            models.UniqueConstraint(
                fields=('product',),
                condition=Q(status=Status.ACTIVE, is_preferred=True),
                name='suppliers_product_one_active_preferred',
            ),
            models.UniqueConstraint(
                fields=('product',),
                condition=Q(status=Status.ACTIVE, is_exclusive=True),
                name='suppliers_product_one_active_exclusive',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=Status.INACTIVE)
                    | Q(is_exclusive=False)
                    | Q(is_preferred=True)
                ),
                name='suppliers_active_exclusive_is_preferred',
            ),
        ]

    def clean(self):
        super().clean()
        self.supplier_code = self.supplier_code.strip()
        errors = {}
        if self.product_id and self.company_id and self.product.company_id != self.company_id:
            errors['product'] = 'O produto deve pertencer à empresa da relação.'
        if self.supplier_id and self.company_id and self.supplier.company_id != self.company_id:
            errors['supplier'] = 'O fornecedor deve pertencer à empresa da relação.'
        if self.status == Status.ACTIVE and self.is_exclusive and not self.is_preferred:
            errors['is_preferred'] = 'Um fornecedor exclusivo ativo deve ser preferencial.'
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                'company_id', 'product_id', 'supplier_id'
            ).first()
            if original:
                for field in ('company', 'product', 'supplier'):
                    if getattr(self, f'{field}_id') != original[f'{field}_id']:
                        errors[field] = 'A identidade da relação não pode ser alterada.'
        if errors:
            raise ValidationError(errors)

        if self.status == Status.ACTIVE and self.product_id:
            siblings = type(self).objects.filter(
                product_id=self.product_id, status=Status.ACTIVE
            )
            if self.pk:
                siblings = siblings.exclude(pk=self.pk)
            if self.is_preferred and siblings.filter(is_preferred=True).exists():
                raise ValidationError({
                    'is_preferred': 'O produto já possui um fornecedor preferencial ativo.'
                })
            if self.is_exclusive and siblings.filter(is_exclusive=True).exists():
                raise ValidationError({
                    'is_exclusive': 'O produto já possui um fornecedor exclusivo ativo.'
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product} - {self.supplier.trade_name}'


class PresentationType(models.TextChoices):
    UNIT = 'UN', 'Unidade'
    BOX = 'CX', 'Caixa'
    BALE = 'FD', 'Fardo'
    PACK = 'PK', 'Pack'
    PACKAGE = 'PCT', 'Pacote'
    CRATE = 'ENG', 'Engradado'
    DISPLAY = 'DSP', 'Display'
    TRAY = 'BDJ', 'Bandeja'
    BAG = 'SC', 'Saco'
    KIT = 'KIT', 'Kit'
    OTHER = 'OTHER', 'Outro'


class PresentationPreset(ProtectedSupplierModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='presentation_presets'
    )
    presentation_type = models.CharField(max_length=5, choices=PresentationType.choices)
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6)
    code = models.CharField(max_length=20)
    description = models.CharField(max_length=200)
    custom_code = models.CharField(max_length=20, blank=True)
    custom_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('code', 'description', 'id')
        constraints = [
            models.CheckConstraint(
                condition=Q(conversion_factor__gt=0),
                name='suppliers_preset_conversion_factor_positive',
            ),
            models.UniqueConstraint(
                fields=(
                    'company', 'presentation_type', 'conversion_factor',
                    'custom_code', 'custom_name',
                ),
                name='suppliers_preset_company_semantic_unique',
            ),
        ]

    @staticmethod
    def _quantity_text(value):
        return format(value.normalize(), 'f').rstrip('0').rstrip('.') if value % 1 else str(int(value))

    def _populate_generated_fields(self):
        if self.conversion_factor is None:
            return
        self.conversion_factor = self._meta.get_field('conversion_factor').to_python(
            self.conversion_factor
        )
        quantity = self._quantity_text(self.conversion_factor)
        prefix = self.custom_code if self.presentation_type == PresentationType.OTHER else self.presentation_type
        name = self.custom_name if self.presentation_type == PresentationType.OTHER else self.get_presentation_type_display()
        self.code = f'{prefix}{quantity}'
        self.description = f'{name} com {quantity} unidades'

    def clean(self):
        super().clean()
        self.custom_code = self.custom_code.strip().upper()
        self.custom_name = ' '.join(self.custom_name.split())
        errors = {}
        if self.conversion_factor is None or self.conversion_factor <= 0:
            errors['conversion_factor'] = 'A quantidade por apresentação deve ser maior que zero.'
        if self.presentation_type == PresentationType.OTHER:
            if not self.custom_code or not self.custom_code.replace('_', '').isalnum():
                errors['custom_code'] = 'Informe uma sigla personalizada com letras, números ou _.'
            if not self.custom_name:
                errors['custom_name'] = 'Informe o nome personalizado.'
        elif self.custom_code or self.custom_name:
            errors['presentation_type'] = 'Campos personalizados são exclusivos do tipo Outro.'
        if errors:
            raise ValidationError(errors)
        self._populate_generated_fields()
        if len(self.code) > 20:
            raise ValidationError({'custom_code': 'A sigla e a quantidade excedem o limite do código.'})
        if self.pk:
            original_company_id = type(self).objects.filter(pk=self.pk).values_list(
                'company_id', flat=True
            ).first()
            if original_company_id and self.company_id != original_company_id:
                raise ValidationError({'company': 'A empresa do padrão não pode ser alterada.'})

    def save(self, *args, **kwargs):
        self.custom_code = self.custom_code.strip().upper()
        self.custom_name = ' '.join(self.custom_name.split())
        self._populate_generated_fields()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company} - {self.code}'


class ProductPurchasePresentation(ProtectedSupplierModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='product_purchase_presentations')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='purchase_presentations')
    unit_code = models.CharField(max_length=20)
    description = models.CharField(max_length=200)
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('product_id', 'unit_code', 'id')
        constraints = [
            models.CheckConstraint(condition=Q(conversion_factor__gt=0), name='suppliers_product_presentation_factor_positive'),
            models.UniqueConstraint(fields=('product', 'unit_code', 'conversion_factor'), name='suppliers_product_presentation_unique'),
        ]

    def clean(self):
        super().clean()
        self.unit_code = self.unit_code.strip().upper()
        self.description = ' '.join(self.description.split())
        if self.product_id and self.company_id and self.product.company_id != self.company_id:
            raise ValidationError({'product': 'O produto deve pertencer à empresa da apresentação.'})
        if self.conversion_factor is None or self.conversion_factor <= 0:
            raise ValidationError({'conversion_factor': 'O fator de conversão deve ser maior que zero.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProductSupplierUnit(ProtectedSupplierModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='product_supplier_units'
    )
    product_supplier = models.ForeignKey(
        ProductSupplier, on_delete=models.PROTECT, related_name='units'
    )
    purchase_presentation = models.ForeignKey(
        ProductPurchasePresentation, on_delete=models.PROTECT, related_name='supplier_links',
        blank=True, null=True,
    )
    presentation_preset = models.ForeignKey(
        PresentationPreset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='product_supplier_units'
    )
    unit_code = models.CharField(max_length=20)
    description = models.CharField(max_length=200, blank=False)
    conversion_factor = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal('1.000000')
    )
    barcode = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('product_supplier_id', '-is_default', 'unit_code', 'id')
        constraints = [
            models.CheckConstraint(
                condition=Q(conversion_factor__gt=0),
                name='suppliers_unit_conversion_factor_positive',
            ),
            models.UniqueConstraint(
                fields=('product_supplier',),
                condition=Q(status=Status.ACTIVE, is_default=True),
                name='suppliers_product_supplier_one_active_default',
            ),
        ]

    def clean(self):
        super().clean()
        self.unit_code = self.unit_code.strip().upper()
        self.description = ' '.join((self.description or '').split())
        self.barcode = self.barcode.strip()
        errors = {}
        if not self.description:
            errors['description'] = 'Informe a descrição da apresentação.'
        if self.conversion_factor is not None and self.conversion_factor <= 0:
            errors['conversion_factor'] = 'O fator de conversão deve ser maior que zero.'
        if (
            self.product_supplier_id
            and self.company_id
            and self.product_supplier.company_id != self.company_id
        ):
            errors['product_supplier'] = 'A relação deve pertencer à empresa da apresentação.'
        if self.purchase_presentation_id and (
            self.purchase_presentation.company_id != self.company_id
            or self.purchase_presentation.product_id != self.product_supplier.product_id
        ):
            errors['purchase_presentation'] = 'A apresentação deve pertencer ao produto deste fornecedor.'
        if (
            self.presentation_preset_id and self.company_id
            and self.presentation_preset.company_id != self.company_id
        ):
            errors['presentation_preset'] = 'O padrão deve pertencer à empresa da apresentação.'
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                'company_id', 'product_supplier_id'
            ).first()
            if original:
                for field in ('company', 'product_supplier'):
                    if getattr(self, f'{field}_id') != original[f'{field}_id']:
                        errors[field] = 'A identidade da relação não pode ser alterada.'
        if errors:
            raise ValidationError(errors)

        if self.status == Status.ACTIVE and self.is_default and self.product_supplier_id:
            siblings = type(self).objects.filter(
                product_supplier_id=self.product_supplier_id,
                status=Status.ACTIVE,
                is_default=True,
            )
            if self.pk:
                siblings = siblings.exclude(pk=self.pk)
            if siblings.exists():
                raise ValidationError({
                    'is_default': 'A relação já possui uma apresentação padrão ativa.'
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product_supplier} - {self.unit_code}'
