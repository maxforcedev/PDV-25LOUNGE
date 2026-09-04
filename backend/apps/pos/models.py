import uuid

from django.conf import settings
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
