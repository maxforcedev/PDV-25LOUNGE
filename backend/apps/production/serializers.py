from rest_framework import serializers
import ipaddress
import re
from django.utils.text import slugify

from apps.products.models import ProductionDestination

from .models import PrintJob, PrinterConnectionType, PrinterDevice, ProductionJob, Ticket


class PrinterDeviceSerializer(serializers.ModelSerializer):
    destination_ids = serializers.PrimaryKeyRelatedField(source='destinations', many=True, read_only=True)
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

    def validate_name(self, value):
        value = ' '.join(value.split())
        if self.instance and ProductionDestination.objects.filter(
            branch=self.instance.branch, name__iexact=value,
        ).exclude(printer_devices=self.instance).exists():
            raise serializers.ValidationError('Já existe outro setor com este nome na filial.')
        return value

    def validate(self, attrs):
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        context_branch = getattr(self.context.get('request'), 'branch_context', None)
        if context_branch and branch and context_branch.pk != branch.pk:
            raise serializers.ValidationError({'branch': 'Selecione a filial ativa.'})
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
        device = super().create(validated_data)
        self._sync_destination(device)
        return device

    def update(self, instance, validated_data):
        validated_data.pop('branch', None)
        device = super().update(instance, validated_data)
        self._sync_destination(device)
        return device

    @staticmethod
    def _sync_destination(device):
        destination = device.destinations.order_by('id').first()
        if destination is None:
            destination = ProductionDestination.objects.filter(
                branch=device.branch, name__iexact=device.name,
            ).first()
        if destination is None:
            base = slugify(device.name)[:40] or f'impressora-{device.pk}'
            code = base
            suffix = 1
            while ProductionDestination.objects.filter(branch=device.branch, code=code).exists():
                suffix += 1
                code = f'{base[:44]}-{suffix}'
            destination = ProductionDestination.objects.create(
                branch=device.branch, name=device.name, code=code,
                status=device.status,
            )
        if not device.destinations.filter(pk=destination.pk).exists():
            device.destinations.add(destination)
        if destination.name != device.name or destination.status != device.status:
            destination.name = device.name
            destination.status = device.status
            destination.save(update_fields=('name', 'status', 'updated_at'))

    def get_connection_summary(self, device):
        configuration = device.technical_configuration or {}
        if device.connection_type == PrinterConnectionType.NETWORK:
            return f"{configuration.get('host', '')}:{configuration.get('port', '')}".strip(':')
        if device.connection_type == PrinterConnectionType.USB:
            return configuration.get('serial') or 'USB configurada'
        return configuration.get('device_name') or configuration.get('identifier') or 'Bluetooth configurada'


class ProductionJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductionJob
        fields = ('id', 'company', 'branch', 'order_item', 'sale_item', 'destination', 'event', 'payload_snapshot', 'original_job', 'created_at')


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ('id', 'company', 'branch', 'number', 'quantity', 'status', 'issued_at', 'used_at', 'cancelled_at', 'reprint_count', 'identification_snapshot', 'source_sale_item', 'source_order_item', 'created_at', 'updated_at')


class PrintJobSerializer(serializers.ModelSerializer):
    production_event = serializers.CharField(source='production_job.event', read_only=True, allow_null=True)
    printer_name = serializers.CharField(source='printer_device.name', read_only=True)
    connection_type = serializers.CharField(source='printer_device.connection_type', read_only=True)
    error_summary = serializers.SerializerMethodField()
    origin_type = serializers.SerializerMethodField()
    origin_label = serializers.SerializerMethodField()

    class Meta:
        model = PrintJob
        fields = (
            'id', 'company', 'branch', 'production_job', 'production_event',
            'destination', 'printer_device', 'printer_name', 'connection_type',
            'payload_snapshot', 'is_test', 'status', 'attempts', 'last_error',
            'error_summary', 'origin_type', 'origin_label', 'idempotency_key',
            'processing_at', 'printed_at',
            'reprint_of', 'reprint_number', 'created_at', 'updated_at',
        )

    def get_error_summary(self, job):
        return (job.last_error or '')[:300]

    def get_origin_type(self, job):
        if job.is_test:
            return 'test'
        production_job = job.production_job
        if production_job and production_job.order_item_id:
            return 'command'
        if production_job and production_job.sale_item_id:
            return 'sale'
        return 'system'

    def get_origin_label(self, job):
        if job.is_test:
            return 'Teste de impressão'
        production_job = job.production_job
        if production_job and production_job.order_item_id:
            command = (job.payload_snapshot or {}).get('command', {})
            number = command.get('number')
            return f'Comanda {number}' if number else f'Pedido #{production_job.order_item_id}'
        if production_job and production_job.sale_item_id:
            return f'Venda #{production_job.sale_item.sale_id}'
        return f'Impressão #{job.pk}'


class ReprintSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)
