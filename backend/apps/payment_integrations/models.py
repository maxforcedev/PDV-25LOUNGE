import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.base.models import BaseModel
from apps.companies.models import Status


_SENSITIVE_METADATA_KEY = re.compile(
    r'(authorization|credential|password|secret|token|api[_-]?key|private[_-]?key|headers?)',
    re.IGNORECASE,
)


def validate_non_sensitive_metadata(value, field_name):
    """Provider metadata must contain technical correlation data, never credentials."""
    def visit(current, path=''):
        if isinstance(current, dict):
            for key, nested in current.items():
                key_text = str(key)
                if _SENSITIVE_METADATA_KEY.search(key_text):
                    raise ValidationError({field_name: f'O campo sensível {path}{key_text} não pode ser persistido.'})
                visit(nested, f'{path}{key_text}.')
        elif isinstance(current, list):
            for index, nested in enumerate(current):
                visit(nested, f'{path}{index}.')
    visit(value or {})


class PaymentProviderIntegrationType(models.TextChoices):
    LOCAL_DEEP_LINK = 'local_deep_link', 'Local deep link'
    NATIVE_SDK = 'native_sdk', 'Native SDK'
    SERVER_API = 'server_api', 'Server API'
    HYBRID = 'hybrid', 'Hybrid'


class PaymentProvider(BaseModel):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    integration_type = models.CharField(max_length=20, choices=PaymentProviderIntegrationType.choices)
    capabilities = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('name', 'id')

    def clean(self):
        super().clean()
        self.code = (self.code or '').strip().lower()
        self.name = ' '.join((self.name or '').split())
        if not self.code:
            raise ValidationError({'code': 'Informe o código do provedor.'})
        if not self.name:
            raise ValidationError({'name': 'Informe o nome do provedor.'})
        if self.pk:
            original = PaymentProvider.objects.get(pk=self.pk)
            if original.code != self.code:
                raise ValidationError({'code': 'O código do provedor não pode ser alterado.'})
        validate_non_sensitive_metadata(self.capabilities, 'capabilities')


class PaymentProviderConnectionEnvironment(models.TextChoices):
    SANDBOX = 'sandbox', 'Sandbox'
    PRODUCTION = 'production', 'Production'


class PaymentProviderConnection(BaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.PROTECT, related_name='payment_provider_connections')
    branch = models.ForeignKey('companies.Branch', on_delete=models.PROTECT, related_name='payment_provider_connections', null=True, blank=True)
    provider = models.ForeignKey(PaymentProvider, on_delete=models.PROTECT, related_name='connections')
    name = models.CharField(max_length=150)
    environment = models.CharField(max_length=12, choices=PaymentProviderConnectionEnvironment.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    configuration = models.JSONField(default=dict, blank=True)
    capabilities_override = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('company_id', 'name', 'id')

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        errors = {}
        if not self.name:
            errors['name'] = 'Informe o nome da conexão.'
        if self.branch_id and self.branch.company_id != self.company_id:
            errors['branch'] = 'A filial deve pertencer à empresa da conexão.'
        if errors:
            raise ValidationError(errors)
        validate_non_sensitive_metadata(self.configuration, 'configuration')
        validate_non_sensitive_metadata(self.capabilities_override, 'capabilities_override')


class PaymentTerminal(BaseModel):
    connection = models.ForeignKey(PaymentProviderConnection, on_delete=models.PROTECT, related_name='terminals')
    branch = models.ForeignKey('companies.Branch', on_delete=models.PROTECT, related_name='payment_terminals')
    pos_device = models.ForeignKey('pos.POSDevice', on_delete=models.PROTECT, related_name='payment_terminals', null=True, blank=True)
    name = models.CharField(max_length=150)
    external_id = models.CharField(max_length=150, blank=True, default='')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    capabilities = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('branch_id', 'name', 'id')

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        errors = {}
        if not self.name:
            errors['name'] = 'Informe o nome do terminal.'
        if self.branch.company_id != self.connection.company_id:
            errors['branch'] = 'O terminal deve pertencer à empresa da conexão.'
        if self.connection.branch_id and self.connection.branch_id != self.branch_id:
            errors['branch'] = 'O terminal deve pertencer à filial da conexão.'
        if self.pos_device_id and self.pos_device.branch_id != self.branch_id:
            errors['pos_device'] = 'O POS deve pertencer à filial do terminal.'
        if errors:
            raise ValidationError(errors)
        validate_non_sensitive_metadata(self.capabilities, 'capabilities')
        validate_non_sensitive_metadata(self.metadata, 'metadata')


class PaymentIntentOriginType(models.TextChoices):
    QUICK_SALE = 'quick_sale', 'Venda rápida'
    TABLE = 'table', 'Mesa'
    COMMAND = 'command', 'Comanda'


class PaymentIntentStatus(models.TextChoices):
    CREATED = 'created', 'Criado'
    READY = 'ready', 'Pronto'
    PROCESSING = 'processing', 'Processando'
    APPROVED = 'approved', 'Aprovado'
    DECLINED = 'declined', 'Recusado'
    CANCELLED = 'cancelled', 'Cancelado'
    ERROR = 'error', 'Erro'
    UNKNOWN = 'unknown', 'Desconhecido'
    APPLIED = 'applied', 'Aplicado'
    REVERSED = 'reversed', 'Estornado'


class PaymentIntentQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Use os serviços de PaymentIntent para alterar o estado.')

    def delete(self):
        raise ValidationError('PaymentIntent é histórico operacional e não pode ser excluído.')


class PaymentIntent(BaseModel):
    objects = PaymentIntentQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey('companies.Company', on_delete=models.PROTECT, related_name='payment_intents')
    branch = models.ForeignKey('companies.Branch', on_delete=models.PROTECT, related_name='payment_intents')
    pos_device = models.ForeignKey('pos.POSDevice', on_delete=models.PROTECT, related_name='payment_intents')
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payment_intents')
    origin_type = models.CharField(max_length=20, choices=PaymentIntentOriginType.choices)
    origin_id = models.CharField(max_length=80)
    payment_method = models.ForeignKey('sales.PaymentMethod', on_delete=models.PROTECT, related_name='payment_intents')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    provider_connection = models.ForeignKey(PaymentProviderConnection, on_delete=models.PROTECT, related_name='payment_intents')
    terminal = models.ForeignKey(PaymentTerminal, on_delete=models.PROTECT, related_name='payment_intents', null=True, blank=True)
    status = models.CharField(max_length=10, choices=PaymentIntentStatus.choices, default=PaymentIntentStatus.CREATED, db_index=True)
    idempotency_key = models.UUIDField(editable=False)
    request_fingerprint = models.CharField(max_length=64, editable=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='payment_intent_amount_positive'),
            models.UniqueConstraint(fields=('company', 'idempotency_key'), name='payment_intent_company_idempotency_unique'),
        ]
        indexes = [models.Index(fields=('branch', 'status', 'created_at'), name='pay_intent_branch_status_idx')]

    def clean(self):
        super().clean()
        self.origin_id = str(self.origin_id or '').strip()
        errors = {}
        if not self.origin_id:
            errors['origin_id'] = 'Informe a origem do intent.'
        if self.amount is not None and self.amount <= 0:
            errors['amount'] = 'O valor deve ser maior que zero.'
        if self.branch.company_id != self.company_id:
            errors['branch'] = 'A filial deve pertencer à empresa.'
        if self.pos_device.branch_id != self.branch_id:
            errors['pos_device'] = 'O POS deve pertencer à filial.'
        if self.payment_method.company_id != self.company_id:
            errors['payment_method'] = 'A forma de pagamento deve pertencer à empresa.'
        elif self.payment_method.status != Status.ACTIVE:
            errors['payment_method'] = 'A forma de pagamento deve estar ativa.'
        if self.provider_connection.company_id != self.company_id:
            errors['provider_connection'] = 'A conexão deve pertencer à empresa.'
        elif self.provider_connection.status != Status.ACTIVE:
            errors['provider_connection'] = 'A conexão deve estar ativa.'
        elif self.provider_connection.branch_id and self.provider_connection.branch_id != self.branch_id:
            errors['provider_connection'] = 'A conexão não é válida para esta filial.'
        if self.terminal_id:
            if self.terminal.connection_id != self.provider_connection_id:
                errors['terminal'] = 'O terminal deve pertencer à conexão selecionada.'
            elif self.terminal.branch_id != self.branch_id:
                errors['terminal'] = 'O terminal deve pertencer à filial.'
            elif self.terminal.status != Status.ACTIVE:
                errors['terminal'] = 'O terminal deve estar ativo.'
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        raise ValidationError('PaymentIntent é histórico operacional e não pode ser excluído.')


class PaymentAttemptStatus(models.TextChoices):
    CREATED = 'created', 'Criada'
    PROCESSING = 'processing', 'Processando'
    APPROVED = 'approved', 'Aprovada'
    DECLINED = 'declined', 'Recusada'
    CANCELLED = 'cancelled', 'Cancelada'
    ERROR = 'error', 'Erro'
    UNKNOWN = 'unknown', 'Desconhecido'


class PaymentAttemptQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Use os serviços de PaymentAttempt para alterar o estado.')

    def delete(self):
        raise ValidationError('PaymentAttempt é histórico operacional e não pode ser excluído.')


class PaymentAttempt(BaseModel):
    objects = PaymentAttemptQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intent = models.ForeignKey(PaymentIntent, on_delete=models.PROTECT, related_name='attempts')
    provider_connection = models.ForeignKey(PaymentProviderConnection, on_delete=models.PROTECT, related_name='payment_attempts')
    terminal = models.ForeignKey(PaymentTerminal, on_delete=models.PROTECT, related_name='payment_attempts', null=True, blank=True)
    attempt_number = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=PaymentAttemptStatus.choices, default=PaymentAttemptStatus.CREATED, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    provider_transaction_id = models.CharField(max_length=150, blank=True, default='')
    provider_order_id = models.CharField(max_length=150, blank=True, default='')
    provider_reference = models.CharField(max_length=150, blank=True, default='')
    terminal_external_id = models.CharField(max_length=150, blank=True, default='')
    authorization_code = models.CharField(max_length=100, blank=True, default='')
    nsu = models.CharField(max_length=100, blank=True, default='')
    card_brand = models.CharField(max_length=50, blank=True, default='')
    card_mask = models.CharField(max_length=32, blank=True, default='')
    installments = models.PositiveSmallIntegerField(null=True, blank=True)
    payment_product = models.CharField(max_length=50, blank=True, default='')
    payment_product_detail = models.CharField(max_length=100, blank=True, default='')
    provider_status = models.CharField(max_length=100, blank=True, default='')
    provider_status_code = models.CharField(max_length=100, blank=True, default='')
    provider_message = models.CharField(max_length=500, blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    request_metadata = models.JSONField(default=dict, blank=True)
    response_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('intent_id', 'attempt_number')
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='payment_attempt_amount_positive'),
            models.UniqueConstraint(fields=('intent', 'attempt_number'), name='payment_attempt_intent_number_unique'),
        ]
        indexes = [models.Index(fields=('intent', 'status', 'attempt_number'), name='pay_attempt_intent_status_idx')]

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors['amount'] = 'O valor deve ser maior que zero.'
        if self.provider_connection.company_id != self.intent.company_id:
            errors['provider_connection'] = 'A conexão deve pertencer à empresa do intent.'
        elif self.provider_connection.branch_id and self.provider_connection.branch_id != self.intent.branch_id:
            errors['provider_connection'] = 'A conexão não é válida para a filial do intent.'
        if self.terminal_id:
            if self.terminal.connection_id != self.provider_connection_id:
                errors['terminal'] = 'O terminal deve pertencer à conexão da tentativa.'
            elif self.terminal.branch_id != self.intent.branch_id:
                errors['terminal'] = 'O terminal deve pertencer à filial do intent.'
        if errors:
            raise ValidationError(errors)
        validate_non_sensitive_metadata(self.request_metadata, 'request_metadata')
        validate_non_sensitive_metadata(self.response_metadata, 'response_metadata')

    def delete(self, *args, **kwargs):
        raise ValidationError('PaymentAttempt é histórico operacional e não pode ser excluído.')
