from rest_framework import serializers
import ipaddress
import re

from apps.products.models import ProductionDestination

from .models import (
    PrintDocument, PrintDocumentType, PrintJob, PrintJobStatus, PrintRoute,
    PrintRouteOverride, PrinterConnectionType, PrinterDevice, ProductionJob, Ticket,
)


class PrinterDeviceSerializer(serializers.ModelSerializer):
    destination_ids = serializers.PrimaryKeyRelatedField(
        source='destinations', many=True, queryset=ProductionDestination.objects.all(), required=False,
    )
    connection_summary = serializers.SerializerMethodField()

    class Meta:
        model = PrinterDevice
        fields = (
            'id', 'branch', 'name', 'device_type', 'connection_type', 'status',
            'destination_ids', 'technical_configuration', 'connection_summary',
            'operational_status', 'last_seen_at', 'last_test_at',
            'last_operational_error', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'device_type', 'connection_summary', 'operational_status',
            'last_seen_at', 'last_test_at', 'last_operational_error',
            'created_at', 'updated_at',
        )
        extra_kwargs = {'branch': {'required': False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if branch:
            self.fields['branch'].queryset = self.fields['branch'].queryset.filter(pk=branch.pk)
            self.fields['branch'].default = branch
            self.fields['branch'].required = False

    def validate(self, attrs):
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        context_branch = getattr(self.context.get('request'), 'branch_context', None)
        if context_branch and branch and context_branch.pk != branch.pk:
            raise serializers.ValidationError({'branch': 'Selecione a filial ativa.'})
        destinations = attrs.get('destinations')
        if destinations is not None and (
            branch is None or any(destination.branch_id != branch.pk for destination in destinations)
        ):
            raise serializers.ValidationError({'destination_ids': 'Todos os destinos devem pertencer à filial atual.'})
        configuration = attrs.get('technical_configuration', getattr(self.instance, 'technical_configuration', {})) or {}
        connection_type = attrs.get('connection_type', getattr(self.instance, 'connection_type', None))
        if self.instance and not configuration and 'technical_configuration' not in attrs:
            return attrs
        if connection_type == PrinterConnectionType.NETWORK:
            host = str(configuration.get('host', '')).strip()
            try:
                ipaddress.ip_address(host)
            except ValueError:
                if not re.fullmatch(r'(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9][A-Za-z0-9-]{0,61}[A-Za-z0-9]?', host):
                    raise serializers.ValidationError({'technical_configuration': 'Informe IP ou hostname válido.'})
            if not isinstance(configuration.get('port'), int) or not 1 <= configuration['port'] <= 65535:
                raise serializers.ValidationError({'technical_configuration': 'Rede exige porta entre 1 e 65535.'})
            timeout = configuration.get('timeout', 5)
            if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 30:
                raise serializers.ValidationError({'technical_configuration': 'Rede exige timeout entre 1 e 30 segundos.'})
            if configuration.get('paper_width', 80) not in (58, 80):
                raise serializers.ValidationError({'technical_configuration': 'Largura do papel deve ser 58 ou 80 mm.'})
        elif connection_type == PrinterConnectionType.USB:
            if not str(configuration.get('identifier', '')).strip():
                raise serializers.ValidationError({'technical_configuration': 'Informe os dados da impressora USB.'})
        elif connection_type == PrinterConnectionType.BLUETOOTH:
            if not str(configuration.get('identifier', '')).strip():
                raise serializers.ValidationError({'technical_configuration': 'Informe o identificador Bluetooth.'})
        return attrs

    def create(self, validated_data):
        branch = getattr(self.context['request'], 'branch_context', None)
        validated_data['branch'] = branch
        validated_data['device_type'] = 'manual'
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop('branch', None)
        return super().update(instance, validated_data)

    def get_connection_summary(self, device):
        configuration = device.technical_configuration or {}
        if device.connection_type == PrinterConnectionType.NETWORK:
            return f"{configuration.get('host', '')}:{configuration.get('port', '')}".strip(':')
        if device.connection_type == PrinterConnectionType.USB:
            return configuration.get('serial') or 'USB configurada'
        if device.connection_type == PrinterConnectionType.STONE_INTEGRATED:
            return 'Stone integrada'
        return configuration.get('device_name') or configuration.get('identifier') or 'Bluetooth configurada'


class ProductionJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductionJob
        fields = ('id', 'company', 'branch', 'order_item', 'attendance_order_item', 'table_order_item', 'sale_item', 'destination', 'event', 'payload_snapshot', 'original_job', 'created_at')


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ('id', 'company', 'branch', 'number', 'quantity', 'status', 'issued_at', 'used_at', 'cancelled_at', 'reprint_count', 'identification_snapshot', 'source_sale_item', 'source_order_item', 'created_at', 'updated_at')


class PrintJobSerializer(serializers.ModelSerializer):
    production_event = serializers.CharField(source='production_job.event', read_only=True, allow_null=True)
    document_type = serializers.CharField(source='print_document.document_type', read_only=True, allow_null=True)
    document_snapshot = serializers.JSONField(source='print_document.snapshot', read_only=True, allow_null=True)
    printer_name = serializers.CharField(source='printer_device.name', read_only=True)
    connection_type = serializers.CharField(source='printer_device.connection_type', read_only=True)
    error_summary = serializers.SerializerMethodField()
    origin_type = serializers.SerializerMethodField()
    origin_label = serializers.SerializerMethodField()
    reprint_eligible = serializers.SerializerMethodField()

    class Meta:
        model = PrintJob
        fields = (
            'id', 'company', 'branch', 'production_job', 'print_document', 'production_event',
            'document_type', 'document_snapshot',
            'destination', 'printer_device', 'printer_name', 'connection_type',
            'payload_snapshot', 'is_test', 'status', 'attempts', 'last_error',
            'error_summary', 'origin_type', 'origin_label', 'idempotency_key',
            'processing_at', 'printed_at', 'claimed_by', 'lease_until', 'batch_key',
            'physical_dispatch_started_at',
            'reprint_of', 'reprint_number', 'reprint_eligible', 'created_at', 'updated_at',
        )

    def get_error_summary(self, job):
        return (job.last_error or '')[:300]

    def get_origin_type(self, job):
        if job.is_test:
            return 'test'
        if job.print_document_id:
            return 'document'
        production_job = job.production_job
        if production_job and production_job.order_item_id:
            return 'command'
        if production_job and production_job.sale_item_id:
            return 'sale'
        if production_job and production_job.table_order_item_id:
            return 'table'
        return 'system'

    def get_origin_label(self, job):
        if job.is_test:
            return 'Teste de impressão'
        if job.print_document_id:
            return job.print_document.get_document_type_display()
        production_job = job.production_job
        if production_job and production_job.order_item_id:
            command = (job.payload_snapshot or {}).get('command', {})
            number = command.get('number')
            return f'Comanda {number}' if number else f'Pedido #{production_job.order_item_id}'
        if production_job and production_job.sale_item_id:
            return f'Venda #{production_job.sale_item.sale_id}'
        if production_job and production_job.table_order_item_id:
            table = (job.payload_snapshot or {}).get('table', {})
            return f"Mesa {table.get('name') or production_job.table_order_item_id}"
        return f'Impressão #{job.pk}'

    def get_reprint_eligible(self, job):
        if job.is_test:
            return False
        sources = PrintJob.objects.filter(batch_key=job.batch_key) if job.batch_key else [job]
        return all(
            not source.is_test
            and source.status in (PrintJobStatus.PRINTED, PrintJobStatus.UNCERTAIN)
            for source in sources
        )


class ReprintSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class PrintDocumentTypeField(serializers.ChoiceField):
    """Expose the documented enum names while persisting model choice values."""

    def __init__(self, **kwargs):
        super().__init__(choices=tuple(PrintDocumentType.__members__), **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail('invalid_choice', input=data)
        member = PrintDocumentType.__members__.get(data.upper())
        if member is None:
            self.fail('invalid_choice', input=data)
        return member.value

    def to_representation(self, value):
        try:
            return PrintDocumentType(value).name
        except ValueError:
            return value


class _RouteSerializer(serializers.ModelSerializer):
    document_type = PrintDocumentTypeField()
    copies = serializers.IntegerField(min_value=1, max_value=10, required=False)
    printer_device_ids = serializers.PrimaryKeyRelatedField(
        source='printer_devices', many=True, queryset=PrinterDevice.objects.all(), required=False,
    )

    def validate_printer_devices(self, devices):
        branch_id = getattr(self.instance, 'branch_id', None)
        if branch_id is None:
            branch_id = getattr(getattr(self.context.get('request'), 'branch_context', None), 'pk', None)
        if any(device.branch_id != branch_id for device in devices):
            raise serializers.ValidationError('Todas as impressoras devem pertencer à filial atual.')
        return devices


class PrintRouteSerializer(_RouteSerializer):
    class Meta:
        model = PrintRoute
        fields = ('id', 'branch', 'document_type', 'mode', 'printer_device_ids', 'copies', 'document_format', 'created_at', 'updated_at')
        read_only_fields = ('id', 'branch', 'created_at', 'updated_at')


class PrintRouteOverrideSerializer(_RouteSerializer):
    pos_device_name = serializers.CharField(source='pos_device.name', read_only=True)

    class Meta:
        model = PrintRouteOverride
        fields = ('id', 'pos_device', 'pos_device_name', 'document_type', 'inherit_branch', 'mode', 'printer_device_ids', 'copies', 'document_format', 'created_at', 'updated_at')
        read_only_fields = ('id', 'pos_device_name', 'created_at', 'updated_at')

    def validate_pos_device(self, device):
        branch = getattr(self.context.get('request'), 'branch_context', None)
        if branch and device.branch_id != branch.pk:
            raise serializers.ValidationError('O POS deve pertencer à filial atual.')
        return device


class PrintDocumentSerializer(serializers.ModelSerializer):
    document_type = PrintDocumentTypeField(read_only=True)
    print_jobs = PrintJobSerializer(many=True, read_only=True)
    initial_printed = serializers.SerializerMethodField()
    reprint_eligible = serializers.SerializerMethodField()

    class Meta:
        model = PrintDocument
        fields = (
            'id', 'company', 'branch', 'document_type', 'source_type', 'source_id',
            'snapshot', 'snapshot_hash', 'version', 'created_by', 'original_document', 'metadata',
            'initial_printed', 'reprint_eligible', 'print_jobs', 'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_initial_printed(self, document):
        return document.print_jobs.filter(reprint_of__isnull=True, status=PrintJobStatus.PRINTED).exists()

    def get_reprint_eligible(self, document):
        return document.print_jobs.filter(
            reprint_of__isnull=True, status__in=(PrintJobStatus.PRINTED, PrintJobStatus.UNCERTAIN),
        ).exists()


class PrintDocumentResultSerializer(serializers.Serializer):
    """POS action response with the document identity and current queue state."""

    document = serializers.SerializerMethodField()
    jobs = serializers.SerializerMethodField()
    queued = serializers.SerializerMethodField()
    reprint_number = serializers.SerializerMethodField()
    reprint_eligible = serializers.SerializerMethodField()

    def get_document(self, document):
        return PrintDocumentSerializer(document, context=self.context).data

    def get_jobs(self, document):
        return PrintJobSerializer(document.print_jobs.order_by('id'), many=True, context=self.context).data

    def get_queued(self, document):
        return document.print_jobs.filter(
            status__in=(PrintJobStatus.PENDING, PrintJobStatus.PROCESSING),
        ).exists()

    def get_reprint_number(self, document):
        return max(document.print_jobs.values_list('reprint_number', flat=True), default=0)

    def get_reprint_eligible(self, document):
        return document.print_jobs.filter(
            reprint_of__isnull=True, status__in=(PrintJobStatus.PRINTED, PrintJobStatus.UNCERTAIN),
        ).exists()


class PrintDocumentIssueSerializer(serializers.Serializer):
    document_type = PrintDocumentTypeField()
    source_type = serializers.ChoiceField(choices=(
        'table_attendance', 'sale', 'table_payment', 'quick_sale_payment', 'ticket',
    ))
    source_id = serializers.CharField(max_length=64)
