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
    STONE_INTEGRATED = 'stone_integrated', 'Stone integrada'
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
    connection_type = models.CharField(max_length=18, choices=PrinterConnectionType.choices, default=PrinterConnectionType.NETWORK)
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
            timeout = configuration.get('timeout', 5)
            if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 30:
                raise ValidationError({'technical_configuration': 'Rede exige timeout entre 1 e 30 segundos.'})
            width = configuration.get('paper_width', 80)
            if width not in (58, 80):
                raise ValidationError({'technical_configuration': 'Largura do papel deve ser 58 ou 80 mm.'})
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
    attendance_order_item = models.ForeignKey('attendance.AttendanceOrderItem', on_delete=models.PROTECT, related_name='production_jobs', null=True, blank=True)
    table_order_item = models.ForeignKey('attendance.TableOrderItem', on_delete=models.PROTECT, related_name='production_jobs', null=True, blank=True)
    sale_item = models.ForeignKey('sales.SaleItem', on_delete=models.PROTECT, related_name='production_jobs', null=True, blank=True)
    destination = models.ForeignKey('products.ProductionDestination', on_delete=models.PROTECT, related_name='production_jobs')
    event = models.CharField(max_length=10, choices=ProductionEvent.choices)
    payload_snapshot = models.JSONField(default=dict)
    original_job = models.ForeignKey('self', on_delete=models.PROTECT, related_name='cancellation_jobs', null=True, blank=True)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(order_item__isnull=False, sale_item__isnull=True, attendance_order_item__isnull=True, table_order_item__isnull=True)
                    | Q(order_item__isnull=True, sale_item__isnull=False, attendance_order_item__isnull=True, table_order_item__isnull=True)
                    | Q(order_item__isnull=True, sale_item__isnull=True, attendance_order_item__isnull=False, table_order_item__isnull=True)
                    | Q(order_item__isnull=True, sale_item__isnull=True, attendance_order_item__isnull=True, table_order_item__isnull=False)
                ),
                name='production_job_exactly_one_source',
            ),
            models.UniqueConstraint(fields=('order_item', 'destination', 'event'), condition=Q(order_item__isnull=False), name='production_job_order_destination_event_unique'),
            models.UniqueConstraint(fields=('sale_item', 'destination', 'event'), condition=Q(sale_item__isnull=False), name='production_job_sale_destination_event_unique'),
            models.UniqueConstraint(fields=('attendance_order_item', 'destination', 'event'), condition=Q(attendance_order_item__isnull=False), name='production_job_attendance_order_destination_event_unique'),
            models.UniqueConstraint(fields=('table_order_item', 'destination', 'event'), condition=Q(table_order_item__isnull=False), name='production_job_table_order_destination_event_unique'),
        ]


class PrintJobStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    PROCESSING = 'processing', 'Processando'
    PRINTED = 'printed', 'Impresso'
    FAILED = 'failed', 'Falhou'
    UNCERTAIN = 'uncertain', 'Resultado incerto'
    CANCELLED = 'cancelled', 'Cancelado'


class PrintDocumentType(models.TextChoices):
    TABLE_BILL = 'table_bill', 'Conta da mesa'
    TABLE_CONFERENCE = 'table_conference', 'Conferência da mesa'
    TABLE_FINAL_RECEIPT = 'table_final_receipt', 'Recibo final da mesa'
    QUICK_SALE_RECEIPT = 'quick_sale_receipt', 'Recibo de venda rápida'
    PAYMENT_RECEIPT = 'payment_receipt', 'Comprovante de pagamento'
    TICKET = 'ticket', 'Ticket'
    REPORT = 'report', 'Relatório'
    FISCAL_RECEIPT = 'fiscal_receipt', 'Recibo fiscal'
    LABEL = 'label', 'Etiqueta'
    DELIVERY_ORDER = 'delivery_order', 'Pedido de entrega'
    CASH_CLOSING = 'cash_closing', 'Fechamento de caixa'
    CASH_OPENING = 'cash_opening', 'Abertura de caixa'


class PrintRouteMode(models.TextChoices):
    DISABLED = 'disabled', 'Desabilitado'
    MANUAL = 'manual', 'Manual'
    AUTOMATIC = 'automatic', 'Automático'


class PrintRoute(BaseModel):
    """Branch-level document policy. Routes deliberately know devices, not transport."""

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='print_routes')
    document_type = models.CharField(max_length=32, choices=PrintDocumentType.choices)
    mode = models.CharField(max_length=12, choices=PrintRouteMode.choices, default=PrintRouteMode.DISABLED)
    printer_devices = models.ManyToManyField(PrinterDevice, related_name='print_routes', blank=True)
    copies = models.PositiveSmallIntegerField(default=1)
    document_format = models.CharField(max_length=30, blank=True, default='')

    class Meta:
        ordering = ('document_type', 'id')
        constraints = [
            models.UniqueConstraint(fields=('branch', 'document_type'), name='print_route_branch_document_type_unique'),
            models.CheckConstraint(condition=Q(copies__gte=1), name='print_route_copies_positive'),
        ]


class PrintRouteOverride(BaseModel):
    """An optional POS-only replacement of one branch document policy."""

    pos_device = models.ForeignKey('pos.POSDevice', on_delete=models.PROTECT, related_name='print_route_overrides')
    document_type = models.CharField(max_length=32, choices=PrintDocumentType.choices)
    inherit_branch = models.BooleanField(default=True)
    mode = models.CharField(max_length=12, choices=PrintRouteMode.choices, default=PrintRouteMode.DISABLED)
    printer_devices = models.ManyToManyField(PrinterDevice, related_name='print_route_overrides', blank=True)
    copies = models.PositiveSmallIntegerField(default=1)
    document_format = models.CharField(max_length=30, blank=True, default='')

    class Meta:
        ordering = ('document_type', 'id')
        constraints = [
            models.UniqueConstraint(fields=('pos_device', 'document_type'), name='print_route_override_device_document_type_unique'),
            models.CheckConstraint(condition=Q(copies__gte=1), name='print_route_override_copies_positive'),
        ]


class PrintDocument(BaseModel):
    """Immutable commercial document snapshot; it is not a ProductionJob."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='print_documents')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='print_documents')
    document_type = models.CharField(max_length=32, choices=PrintDocumentType.choices)
    source_type = models.CharField(max_length=40)
    source_id = models.CharField(max_length=64)
    snapshot = models.JSONField(default=dict)
    snapshot_hash = models.CharField(max_length=64, editable=False)
    version = models.PositiveIntegerField(default=1, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_print_documents', null=True, blank=True)
    original_document = models.ForeignKey('self', on_delete=models.PROTECT, related_name='derived_documents', null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'document_type', 'source_type', 'source_id', 'snapshot_hash'),
                name='print_document_source_snapshot_unique',
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name='print_document_version_positive'),
        ]


class PrintDocumentRequest(BaseModel):
    """Durable business-action idempotency, separate from physical PrintJob keys."""

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='print_document_requests')
    document = models.ForeignKey(PrintDocument, on_delete=models.PROTECT, related_name='requests')
    action = models.CharField(max_length=12, choices=(('issue', 'Emissão'), ('reprint', 'Reimpressão')))
    idempotency_key = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'action', 'idempotency_key'),
                name='print_document_request_idempotency_unique',
            ),
        ]


class PrintJob(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='print_jobs')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='print_jobs')
    production_job = models.ForeignKey(ProductionJob, on_delete=models.PROTECT, related_name='print_jobs', null=True, blank=True)
    print_document = models.ForeignKey(PrintDocument, on_delete=models.PROTECT, related_name='print_jobs', null=True, blank=True)
    is_test = models.BooleanField(default=False)
    destination = models.ForeignKey('products.ProductionDestination', on_delete=models.PROTECT, related_name='print_jobs', null=True, blank=True)
    printer_device = models.ForeignKey(PrinterDevice, on_delete=models.PROTECT, related_name='print_jobs')
    payload_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=PrintJobStatus.choices, default=PrintJobStatus.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default='')
    idempotency_key = models.UUIDField(default=uuid.uuid4, editable=False)
    processing_at = models.DateTimeField(blank=True, null=True)
    printed_at = models.DateTimeField(blank=True, null=True)
    claimed_by = models.ForeignKey(
        'pos.POSDevice', on_delete=models.PROTECT, related_name='claimed_print_jobs',
        blank=True, null=True,
    )
    lease_until = models.DateTimeField(blank=True, null=True)
    # Jobs emitted by one business operation can be sent as one physical ticket.
    batch_key = models.UUIDField(blank=True, null=True, db_index=True)
    # Once persisted, a physical ticket may have reached the printer and can
    # never be automatically claimed by another POS.
    physical_dispatch_started_at = models.DateTimeField(blank=True, null=True)
    executor_metadata = models.JSONField(default=dict, blank=True)
    reprint_of = models.ForeignKey('self', on_delete=models.PROTECT, related_name='reprints', null=True, blank=True)
    reprint_number = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(fields=('production_job', 'printer_device', 'idempotency_key'), name='production_print_job_idempotency_unique'),
            models.UniqueConstraint(fields=('reprint_of', 'reprint_number'), condition=Q(reprint_of__isnull=False), name='production_print_job_reprint_number_unique'),
            models.CheckConstraint(
                condition=(
                    Q(production_job__isnull=False, print_document__isnull=True, is_test=False, destination__isnull=False)
                    | Q(production_job__isnull=True, print_document__isnull=False, is_test=False, destination__isnull=True)
                    | Q(production_job__isnull=True, print_document__isnull=True, is_test=True)
                ),
                name='print_job_exactly_one_valid_origin',
            ),
        ]


class TicketStatus(models.TextChoices):
    ISSUED = 'issued', 'Emitido'
    PARTIALLY_USED = 'partially_used', 'Parcialmente utilizado'
    USED = 'used', 'Utilizado'
    CANCELLED = 'cancelled', 'Cancelado'


class Ticket(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='tickets')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='tickets')
    source_sale_item = models.OneToOneField('sales.SaleItem', on_delete=models.PROTECT, related_name='sale_ticket', null=True, blank=True)
    source_order_item = models.OneToOneField('commands.OrderItem', on_delete=models.PROTECT, related_name='order_ticket', null=True, blank=True)
    source_attendance_order_item = models.OneToOneField('attendance.AttendanceOrderItem', on_delete=models.PROTECT, related_name='order_ticket', null=True, blank=True)
    source_table_order_item = models.OneToOneField('attendance.TableOrderItem', on_delete=models.PROTECT, related_name='order_ticket', null=True, blank=True)
    number = models.PositiveIntegerField()
    validation_code = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    status = models.CharField(max_length=14, choices=TicketStatus.choices, default=TicketStatus.ISSUED)
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
                condition=(
                    Q(source_sale_item__isnull=False, source_order_item__isnull=True, source_attendance_order_item__isnull=True, source_table_order_item__isnull=True)
                    | Q(source_sale_item__isnull=True, source_order_item__isnull=False, source_attendance_order_item__isnull=True, source_table_order_item__isnull=True)
                    | Q(source_sale_item__isnull=True, source_order_item__isnull=True, source_attendance_order_item__isnull=False, source_table_order_item__isnull=True)
                    | Q(source_sale_item__isnull=True, source_order_item__isnull=True, source_attendance_order_item__isnull=True, source_table_order_item__isnull=False)
                ),
                name='production_ticket_exactly_one_source',
            ),
        ]


class TicketRedemptionInputMethod(models.TextChoices):
    SCAN = 'scan', 'Scanner'
    MANUAL = 'manual', 'Manual'


class TicketRedemption(BaseModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name='redemptions')
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ticket_redemptions')
    device = models.ForeignKey('pos.POSDevice', on_delete=models.PROTECT, related_name='ticket_redemptions')
    redeemed_at = models.DateTimeField()
    idempotency_key = models.UUIDField()
    request_fingerprint = models.CharField(max_length=64)
    input_method = models.CharField(max_length=10, choices=TicketRedemptionInputMethod.choices)

    class Meta:
        ordering = ('redeemed_at', 'id')
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='production_ticket_redemption_quantity_positive'),
            models.UniqueConstraint(fields=('ticket', 'idempotency_key'), name='production_ticket_redemption_idempotency_unique'),
        ]
