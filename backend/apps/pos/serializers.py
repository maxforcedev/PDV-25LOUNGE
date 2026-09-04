from rest_framework import serializers

from .models import BranchPOSSettings, POSDevice, POSDeviceSettings
from .services import effective_cash_settings, effective_settings


class POSAdminDeviceSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    company_id = serializers.IntegerField(source='branch.company_id', read_only=True)
    online = serializers.SerializerMethodField()

    class Meta:
        model = POSDevice
        fields = (
            'id', 'company_id', 'branch', 'branch_name', 'name', 'device_type', 'status',
            'app_version', 'os_version', 'device_model', 'capabilities', 'paired_at',
            'last_seen_at', 'blocked_at', 'revoked_at', 'replaced_at', 'replaced_by',
            'online', 'created_at', 'updated_at',
        )
        read_only_fields = tuple(field for field in fields if field != 'name')

    def get_online(self, device):
        from django.utils import timezone
        from datetime import timedelta

        return bool(device.last_seen_at and device.last_seen_at >= timezone.now() - timedelta(minutes=5))


class BranchPOSSettingsSerializer(serializers.ModelSerializer):
    cash_register_options = serializers.SerializerMethodField()

    class Meta:
        model = BranchPOSSettings
        fields = (
            'id', 'branch', 'cash_binding_mode', 'default_cash_register', 'receipt_printer',
            'sale_confirmation_print', 'receipt_print_mode', 'receipt_format', 'paper_width',
            'copies', 'local_report_print_preferences', 'sound_enabled',
            'screen_timeout_seconds', 'peripherals', 'cash_register_options', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'branch', 'cash_register_options', 'created_at', 'updated_at')

    def get_cash_register_options(self, settings):
        from apps.cash.models import CashRegister

        branch = self.context['branch']
        return list(CashRegister.objects.filter(branch=branch, status='active').values('id', 'name'))

    def validate_default_cash_register(self, register):
        branch = self.context['branch']
        if register and register.branch_id != branch.id:
            raise serializers.ValidationError('O caixa padrao deve pertencer a filial.')
        return register


class POSDeviceSettingsSerializer(serializers.ModelSerializer):
    effective_settings = serializers.SerializerMethodField()
    cash_register_options = serializers.SerializerMethodField()

    class Meta:
        model = POSDeviceSettings
        fields = (
            'id', 'device', 'cash_binding_mode', 'default_cash_register', 'receipt_printer',
            'sale_confirmation_print', 'receipt_print_mode', 'receipt_format', 'paper_width',
            'copies', 'local_report_print_preferences', 'sound_enabled',
            'screen_timeout_seconds', 'peripherals', 'effective_settings', 'cash_register_options', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'device', 'effective_settings', 'cash_register_options', 'created_at', 'updated_at')

    def to_internal_value(self, data):
        # The Backoffice submits null for blank override controls; the model stores blank
        # strings/dicts so an empty override continues to inherit the branch default.
        data = data.copy()
        for field in ('cash_binding_mode', 'receipt_printer', 'receipt_print_mode', 'receipt_format'):
            if field in data and data.get(field) is None:
                data[field] = ''
        for field in ('local_report_print_preferences', 'peripherals'):
            if field in data and data.get(field) is None:
                data[field] = {}
        return super().to_internal_value(data)

    def validate_default_cash_register(self, register):
        device = self.context['device']
        if register and register.branch_id != device.branch_id:
            raise serializers.ValidationError('O caixa padrao deve pertencer a filial do dispositivo.')
        return register

    def validate_receipt_printer(self, printer):
        device = self.context['device']
        if printer == 'stone_integrated' and not device.capabilities.get('integrated_printer'):
            raise serializers.ValidationError('Este dispositivo nao possui impressora integrada.')
        return printer

    def get_effective_settings(self, settings):
        cash_binding_mode, cash_register = effective_cash_settings(settings.device)
        return {
            **effective_settings(settings.device),
            'cash_binding_mode': cash_binding_mode,
            'default_cash_register': cash_register.pk if cash_register else None,
        }

    def get_cash_register_options(self, settings):
        from apps.cash.models import CashRegister

        return list(CashRegister.objects.filter(
            branch_id=settings.device.branch_id, status='active'
        ).values('id', 'name'))
