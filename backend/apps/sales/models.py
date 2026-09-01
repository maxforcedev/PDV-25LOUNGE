from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.base.models import BaseModel
from apps.cash.models import CashSession
from apps.companies.models import Branch, Company, Status, UserCompanyAccess
from apps.products.models import Product, SalesChannel, Unit


class OperationType(models.TextChoices):
    SALE = 'sale', 'Venda'
    CONSUMPTION = 'consumption', 'Consumação'


class SaleStatus(models.TextChoices):
    FINALIZED = 'finalized', 'Finalizada'
    CANCELLED = 'cancelled', 'Cancelada'


class PaymentMethodCode(models.TextChoices):
    CASH = 'cash', 'Dinheiro'
    PIX = 'pix', 'PIX'
    CREDIT_CARD = 'credit_card', 'Cartão de crédito'
    DEBIT_CARD = 'debit_card', 'Cartão de débito'


class PromotionDiscountType(models.TextChoices):
    PERCENTAGE = 'percentage', 'Percentual'
    FIXED_AMOUNT = 'fixed_amount', 'Valor fixo'


class Promotion(BaseModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='promotions'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='promotions',
        blank=True, null=True,
    )
    name = models.CharField(max_length=150)
    discount_type = models.CharField(max_length=20, choices=PromotionDiscountType.choices)
    discount_value = models.DecimalField(max_digits=14, decimal_places=2)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    products = models.ManyToManyField(Product, related_name='promotions', blank=True)
    categories = models.ManyToManyField(
        'products.Category', related_name='promotions', blank=True
    )

    class Meta:
        ordering = ('-starts_at', 'name', 'id')
        constraints = [
            models.UniqueConstraint(
                'company', Lower('name'), name='sales_promotion_company_name_ci_unique'
            ),
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True) | Q(starts_at__lt=F('ends_at')),
                name='sales_promotion_period_valid',
            ),
            models.CheckConstraint(
                condition=Q(discount_value__gt=0),
                name='sales_promotion_value_positive',
            ),
            models.CheckConstraint(
                condition=(
                    Q(discount_type=PromotionDiscountType.FIXED_AMOUNT)
                    | Q(
                        discount_type=PromotionDiscountType.PERCENTAGE,
                        discount_value__lte=100,
                    )
                ),
                name='sales_promotion_percentage_lte_100',
            ),
        ]

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        errors = {}
        if not self.name:
            errors['name'] = 'Informe o nome da promoção.'
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            errors['ends_at'] = 'A data final deve ser posterior à data inicial.'
        if self.discount_value is not None and self.discount_value <= 0:
            errors['discount_value'] = 'O desconto deve ser maior que zero.'
        if (
            self.discount_type == PromotionDiscountType.PERCENTAGE
            and self.discount_value is not None
            and self.discount_value > 100
        ):
            errors['discount_value'] = 'O percentual não pode ser maior que 100.'
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            errors['branch'] = 'A filial deve pertencer à empresa da promoção.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company} - {self.name}'


class Weekday(models.IntegerChoices):
    SUNDAY = 0, 'Domingo'
    MONDAY = 1, 'Segunda'
    TUESDAY = 2, 'Terça'
    WEDNESDAY = 3, 'Quarta'
    THURSDAY = 4, 'Quinta'
    FRIDAY = 5, 'Sexta'
    SATURDAY = 6, 'Sábado'


class PromotionSchedule(BaseModel):
    promotion = models.ForeignKey(
        Promotion, on_delete=models.CASCADE, related_name='schedules'
    )
    weekday = models.SmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ('weekday', 'start_time', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('promotion', 'weekday', 'start_time', 'end_time'),
                name='sales_promotion_schedule_interval_unique',
            ),
            models.CheckConstraint(
                condition=~Q(start_time=F('end_time')),
                name='sales_promotion_schedule_interval_nonempty',
            ),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time:
            # Allow overnight intervals where end_time < start_time (wraps midnight).
            if self.start_time == self.end_time:
                raise ValidationError({'end_time': 'O horário final deve diferir do inicial.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_weekday_display()} {self.start_time}-{self.end_time}'


class PaymentMethod(BaseModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='payment_methods'
    )
    code = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ('name', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'code'), name='sales_payment_method_company_code_unique'
            )
        ]

    def clean(self):
        super().clean()
        self.code = (self.code or '').strip().lower()
        self.name = ' '.join((self.name or '').split())
        if not self.code:
            raise ValidationError({'code': 'Informe o código da forma de pagamento.'})
        if not self.name:
            raise ValidationError({'name': 'Informe o nome da forma de pagamento.'})
        if self.pk:
            original = PaymentMethod.objects.get(pk=self.pk)
            if self.company_id != original.company_id:
                raise ValidationError({'company': 'A empresa não pode ser alterada.'})
            if self.code != original.code:
                raise ValidationError({'code': 'O código não pode ser alterado.'})
            if original.is_system and self.name != original.name:
                raise ValidationError({'name': 'O nome de um método padrão não pode ser alterado.'})
            if self.is_system != original.is_system:
                raise ValidationError({'is_system': 'A origem do método não pode ser alterada.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company} - {self.name}'


class SaleQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if 'channel' in kwargs:
            raise ValidationError('O canal da venda e um snapshot imutavel.')
        return super().update(**kwargs)


class Sale(BaseModel):
    objects = SaleQuerySet.as_manager()
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='sales')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='sales')
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.PROTECT, related_name='sales', blank=True, null=True
    )
    sale_number = models.CharField(max_length=20)
    idempotency_key = models.UUIDField(blank=True, null=True, editable=False)
    idempotency_fingerprint = models.CharField(max_length=64, blank=True, default='', editable=False)
    operation_type = models.CharField(
        max_length=20, choices=OperationType.choices, default=OperationType.SALE
    )
    channel = models.CharField(
        max_length=10, choices=SalesChannel.choices, default=SalesChannel.COUNTER
    )
    status = models.CharField(
        max_length=10, choices=SaleStatus.choices, default=SaleStatus.FINALIZED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_sales'
    )
    seller_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='seller_sales',
        blank=True,
        null=True,
    )
    discount_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='approved_discount_sales',
        blank=True,
        null=True,
    )
    service_fee_waived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='waived_service_fee_sales',
        blank=True,
        null=True,
    )
    beneficiary_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='beneficiary_sales',
        blank=True,
        null=True,
    )
    customer = models.ForeignKey(
        'companies.Customer', on_delete=models.PROTECT, related_name='sales',
        blank=True, null=True,
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    promotion_discount_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    item_discount_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    service_fee_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00')
    )
    service_fee_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    service_fee_waived = models.BooleanField(default=False)
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00')
    )
    commission_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    charged_amount = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True
    )
    total = models.DecimalField(max_digits=14, decimal_places=2)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cancelled_sales',
        blank=True,
        null=True,
    )
    cancellation_reason = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'sale_number'), name='sales_sale_company_number_unique'
            ),
            models.UniqueConstraint(
                fields=('company', 'branch', 'operation_type', 'idempotency_key'),
                condition=Q(idempotency_key__isnull=False),
                name='sales_sale_finalize_idempotency_unique',
            ),
            models.CheckConstraint(condition=Q(subtotal__gte=0), name='sales_sale_subtotal_nonnegative'),
            models.CheckConstraint(condition=Q(discount__gte=0), name='sales_sale_discount_nonnegative'),
            models.CheckConstraint(
                condition=Q(promotion_discount_total__gte=0),
                name='sales_sale_promotion_discount_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(item_discount_total__gte=0),
                name='sales_sale_item_discount_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(promotion_discount_total__lte=F('subtotal')),
                name='sales_sale_promotion_discount_lte_subtotal',
            ),
            models.CheckConstraint(condition=Q(total__gte=0), name='sales_sale_total_nonnegative'),
            models.CheckConstraint(
                condition=Q(service_fee_rate__gte=0, service_fee_rate__lte=100),
                name='sales_sale_service_fee_rate_range',
            ),
            models.CheckConstraint(
                condition=Q(service_fee_amount__gte=0),
                name='sales_sale_service_fee_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(commission_rate__gte=0, commission_rate__lte=100),
                name='sales_sale_commission_rate_range',
            ),
            models.CheckConstraint(
                condition=Q(commission_amount__gte=0),
                name='sales_sale_commission_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(
                    discount__lte=(
                        F('subtotal') - F('promotion_discount_total') - F('item_discount_total')
                    )
                ),
                name='sales_sale_discount_lte_remaining',
            ),
            models.CheckConstraint(
                condition=Q(charged_amount__isnull=True) | Q(charged_amount__gte=0),
                name='sales_sale_charged_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(charged_amount__isnull=True) | Q(charged_amount__lte=F('subtotal')),
                name='sales_sale_charged_lte_subtotal',
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        operation_type=OperationType.SALE,
                        seller_user__isnull=False,
                        total=(F('subtotal') - F('promotion_discount_total')
                               - F('item_discount_total') - F('discount')
                               + F('service_fee_amount')),
                    )
                    | Q(
                        operation_type=OperationType.CONSUMPTION,
                        beneficiary_user__isnull=False,
                        charged_amount__isnull=False,
                        promotion_discount_total=0,
                        item_discount_total=0,
                        discount=0,
                        seller_user__isnull=True,
                        service_fee_rate=0,
                        service_fee_amount=0,
                        commission_rate=0,
                        commission_amount=0,
                        total=F('charged_amount'),
                    )
                ),
                name='sales_sale_operation_amounts_coherent',
            ),
            models.CheckConstraint(
                condition=(
                    Q(discount=0, discount_approved_by__isnull=True)
                    | Q(discount__gt=0)
                ),
                name='sales_sale_discount_approval_coherent',
            ),
            models.CheckConstraint(
                condition=(
                    Q(service_fee_waived=False, service_fee_waived_by__isnull=True)
                    | Q(service_fee_waived=True)
                ),
                name='sales_sale_service_fee_waiver_coherent',
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        operation_type=OperationType.SALE,
                        cash_session__isnull=False,
                        charged_amount__isnull=True,
                    )
                    | Q(
                        operation_type=OperationType.CONSUMPTION,
                        charged_amount=0,
                    )
                    | Q(
                        operation_type=OperationType.CONSUMPTION,
                        charged_amount__gt=0,
                        cash_session__isnull=False,
                    )
                ),
                name='sales_sale_cash_session_coherent',
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=SaleStatus.FINALIZED,
                        cancelled_at__isnull=True,
                        cancelled_by__isnull=True,
                        cancellation_reason__isnull=True,
                    )
                    | Q(
                        status=SaleStatus.CANCELLED,
                        cancelled_at__isnull=False,
                        cancelled_by__isnull=False,
                        cancellation_reason__isnull=False,
                    )
                ),
                name='sales_sale_cancellation_coherent',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.pk:
            original_channel = type(self).objects.filter(pk=self.pk).values_list(
                'channel', flat=True
            ).first()
            if original_channel is not None and self.channel != original_channel:
                errors['channel'] = 'O canal da venda e um snapshot imutavel.'
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            errors['branch'] = 'A filial deve pertencer à empresa da venda.'
        if self.cash_session_id and self.branch_id and self.cash_session.branch_id != self.branch_id:
            errors['cash_session'] = 'A sessão de caixa deve pertencer à filial da venda.'
        if self.beneficiary_user_id and self.company_id and not UserCompanyAccess.objects.filter(
            user_id=self.beneficiary_user_id, company_id=self.company_id, is_active=True
        ).exists():
            errors['beneficiary_user'] = 'O beneficiário deve possuir acesso ativo à empresa.'
        if self.customer_id and (
            self.customer.company_id != self.company_id
            or self.customer.status != Status.ACTIVE
        ):
            errors['customer'] = 'O cliente deve estar ativo e pertencer à empresa da venda.'
        if self.operation_type == OperationType.CONSUMPTION:
            if not self.beneficiary_user_id:
                errors['beneficiary_user'] = 'Informe o beneficiário da consumação.'
            if self.charged_amount is None:
                errors['charged_amount'] = 'Informe o valor cobrado.'
            if self.discount != Decimal('0'):
                errors['discount'] = 'Consumação não aceita desconto.'
            if self.promotion_discount_total != Decimal('0'):
                errors['promotion_discount_total'] = 'Consumação não aceita promoção.'
            if self.item_discount_total != Decimal('0'):
                errors['item_discount_total'] = 'Consumação não aceita desconto por item.'
            if self.seller_user_id:
                errors['seller_user'] = 'Consumação não possui atendente.'
            if any(value != Decimal('0') for value in (
                self.service_fee_rate, self.service_fee_amount,
                self.commission_rate, self.commission_amount,
            )):
                errors['service_fee_amount'] = 'Consumação não possui taxa ou comissão.'
            if self.service_fee_waived or self.service_fee_waived_by_id:
                errors['service_fee_waived'] = 'Consumação não possui retirada de taxa.'
            if self.charged_amount is not None and self.total != self.charged_amount:
                errors['total'] = 'O total deve ser igual ao valor cobrado.'
            if self.charged_amount and not self.cash_session_id:
                errors['cash_session'] = 'Consumação cobrada exige sessão de caixa.'
        else:
            if not self.seller_user_id:
                errors['seller_user'] = 'Informe o atendente da venda.'
            if self.charged_amount is not None:
                errors['charged_amount'] = 'Venda normal não possui valor cobrado.'
            if not self.cash_session_id:
                errors['cash_session'] = 'Venda normal exige sessão de caixa.'
            after_promotion = self.subtotal - self.promotion_discount_total
            remaining = after_promotion - self.item_discount_total
            if self.promotion_discount_total < 0 or after_promotion < 0:
                errors['promotion_discount_total'] = 'O desconto promocional excede o subtotal.'
            if self.item_discount_total < 0 or remaining < 0:
                errors['item_discount_total'] = 'O desconto por item excede o saldo após promoções.'
            if self.discount < 0 or self.discount > remaining:
                errors['discount'] = 'O desconto manual excede o saldo após promoções.'
            net_subtotal = remaining - self.discount
            if self.total != net_subtotal + self.service_fee_amount:
                errors['total'] = 'O total deve considerar descontos e taxa de serviço.'
            if self.service_fee_waived and self.service_fee_amount != Decimal('0'):
                errors['service_fee_amount'] = 'Taxa retirada deve possuir valor zero.'
        if self.discount == 0 and self.discount_approved_by_id:
            errors['discount_approved_by'] = 'Venda sem desconto não possui aprovador.'
        if not self.service_fee_waived and self.service_fee_waived_by_id:
            errors['service_fee_waived_by'] = 'Taxa não retirada não possui autorizador.'
        if self.status == SaleStatus.FINALIZED and any(
            value is not None and value != ''
            for value in (self.cancelled_at, self.cancelled_by_id, self.cancellation_reason)
        ):
            errors['status'] = 'Venda finalizada não pode possuir cancelamento.'
        if self.status == SaleStatus.CANCELLED and not all(
            (self.cancelled_at, self.cancelled_by_id)
        ):
            errors['status'] = 'Os dados de cancelamento são obrigatórios.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ImmutableHistoricalQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError('Registros históricos não podem ser alterados em lote.')

    def delete(self):
        raise ValueError('Registros históricos não podem ser excluídos.')

    def bulk_create(self, objs, *args, **kwargs):
        raise ValueError('Registros historicos devem ser criados pelo fluxo de dominio.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError('Registros historicos nao podem ser alterados em lote.')


class ImmutableHistoricalModel(BaseModel):
    objects = ImmutableHistoricalQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValidationError('Registros históricos não podem ser excluídos.')


class SaleItem(ImmutableHistoricalModel):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='sale_items')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    product_name = models.CharField(max_length=200)
    internal_code = models.CharField(max_length=100)
    unit = models.CharField(max_length=5, choices=Unit.choices)
    category_id_snapshot = models.PositiveBigIntegerField(blank=True, null=True, editable=False)
    category_name_snapshot = models.CharField(max_length=150, blank=True, editable=False)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    base_unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'), editable=False
    )
    modifier_unit_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'), editable=False
    )
    modifier_snapshot = models.JSONField(default=list, blank=True, editable=False)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    promotion = models.ForeignKey(
        Promotion,
        on_delete=models.PROTECT,
        related_name='sale_items',
        blank=True,
        null=True,
    )
    promotion_name = models.CharField(max_length=150, blank=True, null=True)
    promotion_discount_type = models.CharField(
        max_length=20, choices=PromotionDiscountType.choices, blank=True, null=True
    )
    promotion_discount_value = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True
    )
    promotion_benefit = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    manual_discount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    discount_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='approved_sale_item_discounts',
        blank=True,
        null=True,
    )
    component_cost_snapshot = models.JSONField(default=list, blank=True)
    net_subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    participates_in_service_fee = models.BooleanField(default=True, editable=False)
    participates_in_commission = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='sales_item_quantity_positive'),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name='sales_item_cost_nonnegative'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='sales_item_price_nonnegative'),
            models.CheckConstraint(condition=Q(subtotal__gte=0), name='sales_item_subtotal_nonnegative'),
            models.CheckConstraint(
                condition=Q(promotion_benefit__gte=0),
                name='sales_item_promotion_benefit_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(promotion_benefit__lte=F('subtotal')),
                name='sales_item_promotion_benefit_lte_subtotal',
            ),
            models.CheckConstraint(
                condition=Q(manual_discount__gte=0),
                name='sales_item_manual_discount_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(manual_discount__lte=F('subtotal') - F('promotion_benefit')),
                name='sales_item_manual_discount_lte_remaining',
            ),
            models.CheckConstraint(
                condition=Q(
                    net_subtotal=F('subtotal') - F('promotion_benefit') - F('manual_discount')
                ),
                name='sales_item_net_subtotal_coherent',
            ),
            models.CheckConstraint(
                condition=(
                    Q(manual_discount=0, discount_approved_by__isnull=True)
                    | Q(manual_discount__gt=0, discount_approved_by__isnull=False)
                ),
                name='sales_item_discount_approval_coherent',
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        promotion__isnull=True,
                        promotion_name__isnull=True,
                        promotion_discount_type__isnull=True,
                        promotion_discount_value__isnull=True,
                        promotion_benefit=0,
                    )
                    | Q(
                        promotion__isnull=False,
                        promotion_name__isnull=False,
                        promotion_discount_type__isnull=False,
                        promotion_discount_value__isnull=False,
                    )
                ),
                name='sales_item_promotion_snapshot_coherent',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.sale_id and self.product_id and self.sale.company_id != self.product.company_id:
            errors['product'] = 'O produto deve pertencer à empresa da venda.'
        if self.promotion_id and self.sale_id and self.promotion.company_id != self.sale.company_id:
            errors['promotion'] = 'A promoção deve pertencer à empresa da venda.'
        snapshots = (
            self.promotion_name,
            self.promotion_discount_type,
            self.promotion_discount_value,
        )
        if self.promotion_id and any(value is None for value in snapshots):
            errors['promotion'] = 'Os snapshots da promoção são obrigatórios.'
        if not self.promotion_id and (
            any(value is not None for value in snapshots) or self.promotion_benefit != 0
        ):
            errors['promotion'] = 'Item sem promoção não pode possuir benefício promocional.'
        if self.promotion_benefit < 0 or self.promotion_benefit > self.subtotal:
            errors['promotion_benefit'] = 'O benefício deve estar entre zero e o subtotal.'
        remaining = self.subtotal - self.promotion_benefit
        if self.manual_discount < 0 or self.manual_discount > remaining:
            errors['manual_discount'] = 'O desconto manual excede o saldo do item.'
        if self.manual_discount and not self.discount_approved_by_id:
            errors['discount_approved_by'] = 'Informe quem autorizou o desconto do item.'
        if not self.manual_discount and self.discount_approved_by_id:
            errors['discount_approved_by'] = 'Item sem desconto não possui autorizador.'
        if self.net_subtotal != remaining - self.manual_discount:
            errors['net_subtotal'] = 'O subtotal líquido deve descontar promoção e desconto do item.'
        if self.unit == Unit.UNIT and self.quantity != self.quantity.to_integral_value():
            errors['quantity'] = 'A quantidade de produto UN deve ser inteira.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Itens de venda são imutáveis.')
        if isinstance(self.quantity, (float, bool)):
            raise ValidationError({'quantity': 'Informe a quantidade como decimal exato.'})
        try:
            self.quantity = Decimal(self.quantity)
        except (TypeError, ValueError):
            raise ValidationError({'quantity': 'Informe uma quantidade válida.'})
        if self.product_id:
            self.product_name = self.product.name
            self.internal_code = self.product.internal_code
            self.unit = self.product.unit
            if self.unit_cost is None:
                from apps.inventory.models import Stock

                stock = Stock.objects.filter(
                    product=self.product, branch_id=self.sale.branch_id
                ).only('average_unit_cost').first()
                branch_cost = (
                    stock.average_unit_cost
                    if stock and stock.average_unit_cost is not None
                    else self.product.cost
                )
                self.unit_cost = branch_cost.quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
            if self.unit_price is None:
                self.unit_price = self.product.sale_price
            self.subtotal = (self.unit_price * self.quantity).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        self.net_subtotal = self.subtotal - self.promotion_benefit - self.manual_discount
        self.full_clean()
        return super().save(*args, **kwargs)


class Payment(ImmutableHistoricalModel):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='payments')
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, related_name='payments'
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    received_amount = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    change_amount = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    payment_method_name = models.CharField(max_length=100)
    payment_method_code = models.CharField(max_length=50)
    source_command_payment = models.OneToOneField(
        'commands.CommandPayment', on_delete=models.PROTECT,
        related_name='final_payment', blank=True, null=True,
    )
    # Command tender is recorded before the sale exists; retain its business timestamp.
    occurred_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='sales_payment_amount_positive'),
            models.CheckConstraint(
                condition=Q(received_amount__isnull=True) | Q(received_amount__gte=0),
                name='sales_payment_received_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(change_amount__isnull=True) | Q(change_amount__gte=0),
                name='sales_payment_change_nonnegative',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors['amount'] = 'O valor deve ser maior que zero.'
        if self.sale_id and self.payment_method_id and self.sale.company_id != self.payment_method.company_id:
            errors['payment_method'] = 'A forma de pagamento deve pertencer à empresa da venda.'
        if self.payment_method_id and self.payment_method.status != Status.ACTIVE:
            errors['payment_method'] = 'A forma de pagamento está inativa.'
        if self.payment_method_id and self.payment_method.code == PaymentMethodCode.CASH:
            if self.received_amount is not None and self.received_amount < self.amount:
                errors['received_amount'] = 'O valor recebido não pode ser menor que o pagamento.'
            expected_change = (
                self.received_amount - self.amount if self.received_amount is not None else None
            )
            if self.change_amount != expected_change:
                errors['change_amount'] = 'O troco deve ser calculado a partir do valor recebido.'
        elif self.received_amount is not None or self.change_amount is not None:
            errors['received_amount'] = 'Somente pagamento em dinheiro aceita valor recebido e troco.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Pagamentos são imutáveis.')
        for field in ('amount', 'received_amount'):
            value = getattr(self, field)
            if value is None:
                continue
            if isinstance(value, (float, bool)):
                raise ValidationError({field: 'Informe o valor como decimal exato.'})
            try:
                setattr(self, field, Decimal(value))
            except (TypeError, ValueError):
                raise ValidationError({field: 'Informe um valor válido.'})
        if self.payment_method_id:
            self.payment_method_name = self.payment_method.name
            self.payment_method_code = self.payment_method.code
            if self.payment_method.code == PaymentMethodCode.CASH and self.received_amount is not None:
                self.change_amount = self.received_amount - self.amount
        self.full_clean()
        return super().save(*args, **kwargs)
