import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.base.models import BaseModel
from apps.companies.models import Branch, Company, Status


class PrinterDeviceType(models.TextChoices):
    MANUAL = 'manual', 'Manual'
    DEVELOPMENT = 'development', 'Development'


class PrinterConnectionType(models.TextChoices):
    NETWORK = 'network', 'Network'
    USB = 'usb', 'USB'
    BLUETOOTH = 'bluetooth', 'Bluetooth'


class PrinterOperationalStatus(models.TextChoices):
    NOT_TESTED = 'not_tested', 'Não testada'
    ONLINE = 'online', 'Online'
    OFFLINE = 'offline', 'Offline'
    BRIDGE_UNAVAILABLE = 'bridge_unavailable', 'Bridge indisponível'
    FAILED = 'failed', 'Falha'


class PrinterDevice(BaseModel):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='printer_devices')
    name = models.CharField(max_length=100)
    device_type = models.CharField(max_length=20, choices=PrinterDeviceType.choices, default=PrinterDeviceType.MANUAL)
    connection_type = models.CharField(max_length=12, choices=PrinterConnectionType.choices, default=PrinterConnectionType.NETWORK)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    destinations = models.ManyToManyField('products.ProductionDestination', related_name='printer_devices', blank=True)
    technical_configuration = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    last_test_at = models.DateTimeField(blank=True, null=True)
    operational_status = models.CharField(
        max_length=24, choices=PrinterOperationalStatus.choices,
        default=PrinterOperationalStatus.NOT_TESTED,
    )
    last_operational_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ('name', 'id')
        constraints = [models.UniqueConstraint(fields=('branch', 'name'), name='production_printer_branch_name_unique')]

    @property
    def company_id(self):
        return self.branch.company_id

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        if not self.name:
            raise ValidationError({'name': 'Informe o nome da impressora.'})
        if self.pk and self.destinations.exclude(branch_id=self.branch_id).exists():
            raise ValidationError({'destinations': 'Os destinos devem pertencer à filial da impressora.'})
        configuration = self.technical_configuration or {}
        # Preserve historical manual devices until an operator configures a transport.
        if self.device_type == PrinterDeviceType.MANUAL and not configuration:
            return
        if self.connection_type == PrinterConnectionType.NETWORK:
            if not configuration.get('host'):
                raise ValidationError({'technical_configuration': 'Rede exige host ou IP.'})
            port = configuration.get('port')
            if not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValidationError({'technical_configuration': 'Rede exige porta entre 1 e 65535.'})
        elif self.connection_type == PrinterConnectionType.USB:
            if not configuration.get('identifier'):
                raise ValidationError({'technical_configuration': 'USB exige identificador persistente do dispositivo.'})
        elif self.connection_type == PrinterConnectionType.BLUETOOTH:
            if not configuration.get('identifier'):
                raise ValidationError({'technical_configuration': 'Bluetooth exige identificador do dispositivo.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProductionEvent(models.TextChoices):
    NEW = 'new', 'Novo'
    CANCEL = 'cancel', 'Cancelamento'


class ProductionJob(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='production_jobs')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='production_jobs')
    order_item = models.ForeignKey('commands.OrderItem', on_delete=models.PROTECT, related_name='production_jobs', null=True, blank=True)
    sale_item = models.ForeignKey('sales.SaleItem', on_delete=models.PROTECT, related_name='production_jobs', null=True, blank=True)
    destination = models.ForeignKey('products.ProductionDestination', on_delete=models.PROTECT, related_name='production_jobs')
    event = models.CharField(max_length=10, choices=ProductionEvent.choices)
    payload_snapshot = models.JSONField(default=dict)
    original_job = models.ForeignKey('self', on_delete=models.PROTECT, related_name='cancellation_jobs', null=True, blank=True)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(
                condition=(Q(order_item__isnull=False, sale_item__isnull=True) | Q(order_item__isnull=True, sale_item__isnull=False)),
                name='production_job_exactly_one_source',
            ),
            models.UniqueConstraint(fields=('order_item', 'destination', 'event'), condition=Q(order_item__isnull=False), name='production_job_order_destination_event_unique'),
            models.UniqueConstraint(fields=('sale_item', 'destination', 'event'), condition=Q(sale_item__isnull=False), name='production_job_sale_destination_event_unique'),
        ]


class PrintJobStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    PROCESSING = 'processing', 'Processando'
    PRINTED = 'printed', 'Impresso'
    FAILED = 'failed', 'Falhou'
    CANCELLED = 'cancelled', 'Cancelado'


class PrintJob(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='print_jobs')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='print_jobs')
    production_job = models.ForeignKey(ProductionJob, on_delete=models.PROTECT, related_name='print_jobs', null=True, blank=True)
    is_test = models.BooleanField(default=False)
    destination = models.ForeignKey('products.ProductionDestination', on_delete=models.PROTECT, related_name='print_jobs')
    printer_device = models.ForeignKey(PrinterDevice, on_delete=models.PROTECT, related_name='print_jobs')
    payload_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=PrintJobStatus.choices, default=PrintJobStatus.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default='')
    idempotency_key = models.UUIDField(default=uuid.uuid4, editable=False)
    processing_at = models.DateTimeField(blank=True, null=True)
    printed_at = models.DateTimeField(blank=True, null=True)
    reprint_of = models.ForeignKey('self', on_delete=models.PROTECT, related_name='reprints', null=True, blank=True)
    reprint_number = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(fields=('production_job', 'printer_device', 'idempotency_key'), name='production_print_job_idempotency_unique'),
            models.UniqueConstraint(fields=('reprint_of', 'reprint_number'), condition=Q(reprint_of__isnull=False), name='production_print_job_reprint_number_unique'),
        ]


class TicketStatus(models.TextChoices):
    ISSUED = 'issued', 'Emitido'
    USED = 'used', 'Utilizado'
    CANCELLED = 'cancelled', 'Cancelado'


class Ticket(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='tickets')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='tickets')
    source_sale_item = models.OneToOneField('sales.SaleItem', on_delete=models.PROTECT, related_name='sale_ticket', null=True, blank=True)
    source_order_item = models.OneToOneField('commands.OrderItem', on_delete=models.PROTECT, related_name='order_ticket', null=True, blank=True)
    number = models.PositiveIntegerField()
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    status = models.CharField(max_length=10, choices=TicketStatus.choices, default=TicketStatus.ISSUED)
    issued_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    reprint_count = models.PositiveIntegerField(default=0)
    identification_snapshot = models.JSONField(default=dict)

    class Meta:
        ordering = ('-issued_at', '-id')
        constraints = [
            models.UniqueConstraint(fields=('company', 'branch', 'number'), name='production_ticket_branch_number_unique'),
            models.CheckConstraint(condition=Q(quantity__gt=0), name='production_ticket_quantity_positive'),
            models.CheckConstraint(
                condition=(Q(source_sale_item__isnull=False, source_order_item__isnull=True) | Q(source_sale_item__isnull=True, source_order_item__isnull=False)),
                name='production_ticket_exactly_one_source',
            ),
        ]
