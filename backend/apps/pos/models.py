import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.base.models import BaseModel


class POSDeviceQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if {'branch', 'branch_id'}.intersection(kwargs):
            from django.core.exceptions import ValidationError

            raise ValidationError({
                'branch': 'A filial do dispositivo nao pode ser alterada; revogue e pareie novamente.'
            })
        return super().update(**kwargs)


class POSDevice(BaseModel):
    objects = POSDeviceQuerySet.as_manager()

    class DeviceType(models.TextChoices):
        POS = 'POS', 'POS'
        STONE_POS = 'STONE_POS', 'Stone POS'
        TABLET_POS = 'TABLET_POS', 'Tablet POS'
        MOBILE_POS = 'MOBILE_POS', 'Mobile POS'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendente'
        ACTIVE = 'ACTIVE', 'Ativo'
        BLOCKED = 'BLOCKED', 'Bloqueado'
        REVOKED = 'REVOKED', 'Revogado'
        REPLACED = 'REPLACED', 'Substituido'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey('companies.Branch', on_delete=models.PROTECT, related_name='pos_devices')
    name = models.CharField(max_length=150)
    device_type = models.CharField(max_length=20, choices=DeviceType.choices, default=DeviceType.POS)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    credential_hash = models.CharField(max_length=256, blank=True, default='')
    credential_fingerprint = models.CharField(max_length=64, blank=True, default='', db_index=True)
    app_version = models.CharField(max_length=50, blank=True)
    os_version = models.CharField(max_length=100, blank=True)
    device_model = models.CharField(max_length=100, blank=True)
    hardware_identifier_hash = models.CharField(max_length=256, blank=True)
    capabilities = models.JSONField(default=dict, blank=True)
    paired_at = models.DateTimeField(blank=True, null=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    blocked_at = models.DateTimeField(blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    replaced_at = models.DateTimeField(blank=True, null=True)
    replaced_by = models.ForeignKey('self', on_delete=models.PROTECT, blank=True, null=True, related_name='replaces')
    # The physical drawer selected for this device. It is deliberately not an
    # operator, checkout, or payment concern.
    active_cash_session = models.ForeignKey(
        'cash.CashSession', on_delete=models.SET_NULL, blank=True, null=True,
        related_name='active_on_pos_devices',
    )

    class Meta:
        ordering = ('branch__name', 'name')

    @property
    def company_id(self):
        return self.branch.company_id

    def clean(self):
        if self.pk:
            original_branch_id = type(self).objects.filter(pk=self.pk).values_list('branch_id', flat=True).first()
            if original_branch_id and original_branch_id != self.branch_id:
                from django.core.exceptions import ValidationError
                raise ValidationError({'branch': 'A filial do dispositivo nao pode ser alterada; revogue e pareie novamente.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class PairingFlow(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey('companies.Branch', on_delete=models.CASCADE, related_name='pos_pairing_flows')
    expires_at = models.DateTimeField()


class AuthenticationChallenge(BaseModel):
    class Purpose(models.TextChoices):
        POS_DEVICE_PAIRING = 'POS_DEVICE_PAIRING', 'Pareamento POS'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purpose = models.CharField(max_length=40, choices=Purpose.choices, default=Purpose.POS_DEVICE_PAIRING)
    pairing_flow = models.ForeignKey(PairingFlow, on_delete=models.CASCADE, related_name='challenges')
    branch = models.ForeignKey('companies.Branch', on_delete=models.PROTECT, related_name='authentication_challenges')
    channel = models.CharField(max_length=20)
    destination_fingerprint = models.CharField(max_length=64)
    destination_masked = models.CharField(max_length=254)
    code_hash = models.CharField(max_length=256)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    resend_count = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(blank=True, null=True)


class POSPinResetToken(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pos_pin_reset_tokens')
    company = models.ForeignKey('companies.Company', on_delete=models.PROTECT, related_name='pos_pin_reset_tokens')
    token_hash = models.CharField(max_length=256)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name='created_pos_pin_reset_tokens')


class POSOperatorSession(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(POSDevice, on_delete=models.PROTECT, related_name='operator_sessions')
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pos_operator_sessions')
    token_hash = models.CharField(max_length=256)
    token_fingerprint = models.CharField(max_length=64, blank=True, default='', db_index=True)
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=('device', 'operator', 'expires_at'))]


class POSOperatorPinAttempt(BaseModel):
    device = models.ForeignKey(POSDevice, on_delete=models.CASCADE, related_name='pin_attempts')
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pos_pin_attempts')
    failures = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('device', 'operator'), name='pos_pin_attempt_device_operator_unique')]


class POSRequestRateLimit(BaseModel):
    key = models.CharField(max_length=180, unique=True)
    failures = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)


class BranchPOSSettings(BaseModel):
    branch = models.OneToOneField('companies.Branch', on_delete=models.CASCADE, related_name='pos_settings')
    cash_binding_mode = models.CharField(max_length=10, choices=(('FIXED', 'Fixo'), ('FLEXIBLE', 'Flexivel')), default='FLEXIBLE')
    default_cash_register = models.ForeignKey('cash.CashRegister', on_delete=models.SET_NULL, blank=True, null=True, related_name='+')
    # Legacy UI preferences. PrintRoute is the authoritative document-routing source.
    receipt_printer = models.CharField(max_length=80, default='none')
    sale_confirmation_print = models.BooleanField(default=False)
    receipt_print_mode = models.CharField(max_length=10, choices=(('automatic', 'Automatico'), ('manual', 'Manual')), default='manual')
    receipt_format = models.CharField(max_length=12, choices=(('detailed', 'Detalhado'), ('simplified', 'Simplificado')), default='detailed')
    paper_width = models.PositiveSmallIntegerField(default=80, validators=[MinValueValidator(40), MaxValueValidator(120)])
    copies = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(10)])
    local_report_print_preferences = models.JSONField(default=dict, blank=True)
    sound_enabled = models.BooleanField(default=True)
    screen_timeout_seconds = models.PositiveIntegerField(blank=True, null=True)
    peripherals = models.JSONField(default=dict, blank=True)
    show_out_of_stock_products = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        if self.default_cash_register_id and self.default_cash_register.branch_id != self.branch_id:
            from django.core.exceptions import ValidationError

            raise ValidationError({'default_cash_register': 'O caixa padrao deve pertencer a filial.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class POSDeviceSettings(BaseModel):
    device = models.OneToOneField(POSDevice, on_delete=models.CASCADE, related_name='settings')
    cash_binding_mode = models.CharField(max_length=10, choices=(('FIXED', 'Fixo'), ('FLEXIBLE', 'Flexivel')), blank=True)
    default_cash_register = models.ForeignKey('cash.CashRegister', on_delete=models.SET_NULL, blank=True, null=True, related_name='+')
    # Retained only for pre-PrintRoute clients; new document dispatch uses PrintRouteOverride.
    receipt_printer = models.CharField(max_length=80, blank=True)
    sale_confirmation_print = models.BooleanField(blank=True, null=True)
    receipt_print_mode = models.CharField(max_length=10, blank=True)
    receipt_format = models.CharField(max_length=12, blank=True)
    paper_width = models.PositiveSmallIntegerField(blank=True, null=True, validators=[MinValueValidator(40), MaxValueValidator(120)])
    copies = models.PositiveSmallIntegerField(blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(10)])
    local_report_print_preferences = models.JSONField(default=dict, blank=True)
    sound_enabled = models.BooleanField(blank=True, null=True)
    screen_timeout_seconds = models.PositiveIntegerField(blank=True, null=True)
    peripherals = models.JSONField(default=dict, blank=True)
    show_out_of_stock_products = models.BooleanField(blank=True, null=True)

    def clean(self):
        super().clean()
        if (
            self.default_cash_register_id
            and self.default_cash_register.branch_id != self.device.branch_id
        ):
            from django.core.exceptions import ValidationError

            raise ValidationError({'default_cash_register': 'O caixa padrao deve pertencer a filial do dispositivo.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class QuickSaleCheckoutStatus(models.TextChoices):
    OPEN = 'open', 'Em edição'
    PAID = 'paid', 'Pago'
    FINALIZED = 'finalized', 'Finalizado'
    CANCELLED = 'cancelled', 'Cancelado'


class QuickSalePaymentStatus(models.TextChoices):
    APPLIED = 'applied', 'Manual aplicado'
    REVERSED = 'reversed', 'Estorno'


class QuickSaleCheckout(BaseModel):
    """Persistent POS counter checkout. Monetary data is the official preview snapshot."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey('companies.Company', on_delete=models.PROTECT, related_name='quick_sale_checkouts')
    branch = models.ForeignKey('companies.Branch', on_delete=models.PROTECT, related_name='quick_sale_checkouts')
    pos_device = models.ForeignKey(POSDevice, on_delete=models.PROTECT, related_name='quick_sale_checkouts')
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='quick_sale_checkouts')
    customer = models.ForeignKey('companies.Customer', on_delete=models.PROTECT, related_name='quick_sale_checkouts', blank=True, null=True)
    cash_session = models.ForeignKey('cash.CashSession', on_delete=models.PROTECT, related_name='quick_sale_checkouts', blank=True, null=True)
    sale = models.OneToOneField('sales.Sale', on_delete=models.PROTECT, related_name='quick_sale_checkout', blank=True, null=True)
    status = models.CharField(max_length=10, choices=QuickSaleCheckoutStatus.choices, default=QuickSaleCheckoutStatus.OPEN, db_index=True)
    discount_intent = models.JSONField(default=dict, blank=True)
    service_fee_waived = models.BooleanField(default=False)
    discount_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='approved_quick_sale_discounts', blank=True, null=True)
    item_discount_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='approved_quick_sale_item_discounts', blank=True, null=True)
    service_fee_waived_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='approved_quick_sale_service_fee_waivers', blank=True, null=True)
    financial_snapshot = models.JSONField(default=dict, blank=True)
    creation_idempotency_key = models.UUIDField(blank=True, null=True, editable=False)
    creation_request_fingerprint = models.CharField(max_length=64, blank=True, default='', editable=False)
    finalization_idempotency_key = models.UUIDField(blank=True, null=True, editable=False)

    class Meta:
        ordering = ('-updated_at', '-created_at')
        indexes = [models.Index(fields=('branch', 'operator', 'status'))]
        constraints = [
            models.UniqueConstraint(
                fields=('pos_device', 'operator', 'creation_idempotency_key'),
                name='pos_quick_sale_checkout_creation_idempotency_unique',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            errors['branch'] = 'A filial deve pertencer à empresa do checkout.'
        if self.pos_device_id and self.branch_id and self.pos_device.branch_id != self.branch_id:
            errors['pos_device'] = 'O dispositivo deve pertencer à filial do checkout.'
        if self.customer_id and (
            self.customer.company_id != self.company_id or self.customer.status != 'active'
        ):
            errors['customer'] = 'O cliente deve estar ativo e pertencer à empresa.'
        if self.cash_session_id and self.cash_session.branch_id != self.branch_id:
            errors['cash_session'] = 'A sessão de caixa deve pertencer à filial.'
        if self.status == QuickSaleCheckoutStatus.FINALIZED and not self.sale_id:
            errors['sale'] = 'Checkout finalizado exige venda.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class QuickSaleCheckoutItem(BaseModel):
    checkout = models.ForeignKey(QuickSaleCheckout, on_delete=models.PROTECT, related_name='items')
    client_item_id = models.UUIDField()
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='quick_sale_checkout_items')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    snapshot = models.JSONField(default=dict)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(fields=('checkout', 'client_item_id'), name='pos_quick_sale_checkout_item_client_unique'),
            models.CheckConstraint(condition=Q(quantity__gt=0), name='pos_quick_sale_checkout_item_quantity_positive'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Itens de checkout são imutáveis.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Itens de checkout não podem ser excluídos.')


class QuickSalePayment(BaseModel):
    """Manual tender ledger. Reversals are new rows and never delete the original."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    checkout = models.ForeignKey(QuickSaleCheckout, on_delete=models.PROTECT, related_name='payments')
    payment_method = models.ForeignKey('sales.PaymentMethod', on_delete=models.PROTECT, related_name='quick_sale_payments')
    payment_method_name = models.CharField(max_length=100)
    payment_method_code = models.CharField(max_length=50)
    source_type = models.CharField(max_length=20, default='manual', editable=False)
    status = models.CharField(max_length=10, choices=QuickSalePaymentStatus.choices, default=QuickSalePaymentStatus.APPLIED)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    received_amount = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    change_amount = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    cash_session = models.ForeignKey('cash.CashSession', on_delete=models.PROTECT, related_name='quick_sale_payments', blank=True, null=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='quick_sale_payments')
    idempotency_key = models.UUIDField(editable=False)
    request_fingerprint = models.CharField(max_length=64, editable=False)
    reversal_of = models.OneToOneField('self', on_delete=models.PROTECT, related_name='reversal', blank=True, null=True)
    reversal_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('created_at', 'id')
        constraints = [
            models.UniqueConstraint(fields=('checkout', 'idempotency_key'), name='pos_quick_sale_payment_idempotency_unique'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='pos_quick_sale_payment_amount_positive'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.checkout_id and self.payment_method_id and self.payment_method.company_id != self.checkout.company_id:
            errors['payment_method'] = 'A forma de pagamento deve pertencer à empresa do checkout.'
        if self.cash_session_id and self.cash_session.branch_id != self.checkout.branch_id:
            errors['cash_session'] = 'A sessão de caixa deve pertencer à filial do checkout.'
        if self.reversal_of_id is None and self.cash_session_id is None:
            errors['cash_session'] = 'Pagamento de checkout exige sessão de caixa.'
        if self.payment_method_id and self.payment_method.code == 'cash':
            if self.received_amount is None or self.received_amount < self.amount:
                errors['received_amount'] = 'Dinheiro exige valor recebido igual ou maior ao aplicado.'
        elif self.received_amount is not None or self.change_amount is not None:
            errors['payment_method'] = 'Somente dinheiro aceita recebido ou troco.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # UUID primary keys are assigned before the first save, so truthiness alone
        # cannot distinguish a new immutable ledger row from an update.
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Pagamentos de checkout são imutáveis.')
        if self.payment_method_id:
            self.payment_method_name = self.payment_method.name
            self.payment_method_code = self.payment_method.code
            if self.payment_method.code == 'cash' and self.received_amount is not None:
                self.change_amount = self.received_amount - self.amount
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Pagamentos de checkout não podem ser excluídos.')


class QuickSalePaymentAllocation(BaseModel):
    payment = models.ForeignKey(QuickSalePayment, on_delete=models.PROTECT, related_name='allocations')
    item = models.ForeignKey(QuickSaleCheckoutItem, on_delete=models.PROTECT, related_name='payment_allocations')
    allocated_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(allocated_quantity__gt=0), name='pos_quick_sale_allocation_quantity_positive'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='pos_quick_sale_allocation_amount_positive'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Alocações de pagamento são imutáveis.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Alocações de pagamento não podem ser excluídas.')
