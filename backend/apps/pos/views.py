from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.base.audit import audit_log, model_snapshot
from apps.base.exceptions import DomainValidationError
from apps.base.pagination import StandardPagination
from apps.companies.permissions import FunctionalCompanyPermission
from apps.companies.selectors import accessible_branches

from .authentication import POSDeviceAuthentication, require_device, require_operator_session
from .models import POSDevice, POSDeviceSettings
from .serializers import POSAdminDeviceSerializer, POSDeviceSettingsSerializer
from .services import (
    assert_branch_device_limit, authenticate_operator, confirm_pairing, effective_cash_settings,
    effective_settings, identify_branch, logout_operator, modules_for, pos_operator_queryset,
    request_otp, set_device_status, set_pos_pin, validate_device_operational, version_gate,
)


def _required(data, field):
    value = data.get(field)
    if value in (None, ''):
        raise DomainValidationError(code='invalid_request', message=f'Informe {field}.', details={field: ['Obrigatorio.']})
    return value


def _operator_data(user):
    name = user.get_full_name().strip() or user.email or f'Usuario {user.pk}'
    initials = ''.join(part[0] for part in name.split()[:2]).upper()
    return {'id': user.pk, 'display_name': name, 'initials': initials, 'avatar_url': None}


class POSPublicView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class POSDeviceView(APIView):
    authentication_classes = [POSDeviceAuthentication]
    permission_classes = [AllowAny]

    def device(self, request, *, check_version=False):
        return validate_device_operational(require_device(request), check_version=check_version)


class PairingIdentifyView(POSPublicView):
    def post(self, request):
        flow, channels = identify_branch(_required(request.data, 'identifier'), request)
        return Response({
            'pairing_flow_id': flow.id,
            'branch': {'display_name': flow.branch.name},
            'channels': [{key: value for key, value in channel.items() if key != '_destination'} for channel in channels],
            'expires_in_seconds': int((flow.expires_at - timezone.now()).total_seconds()),
        })


class PairingRequestOtpView(POSPublicView):
    def post(self, request):
        challenge = request_otp(_required(request.data, 'pairing_flow_id'), _required(request.data, 'channel_id'), request)
        return Response({
            'challenge_id': challenge.id,
            'destination': challenge.destination_masked,
            'expires_in_seconds': int((challenge.expires_at - timezone.now()).total_seconds()),
            'resend_available_in_seconds': 60,
        })


class PairingConfirmView(POSPublicView):
    def post(self, request):
        device_data = request.data.get('device')
        if not isinstance(device_data, dict):
            raise DomainValidationError(code='invalid_request', message='Informe os dados do dispositivo.')
        _required(device_data, 'name')
        device, credential = confirm_pairing(
            _required(request.data, 'challenge_id'), _required(request.data, 'code'), device_data, request,
        )
        return Response({
            'device': {'id': device.id, 'name': device.name, 'status': device.status},
            'device_credential': credential,
            'bootstrap_required': True,
        }, status=status.HTTP_201_CREATED)


class OperatorsView(POSDeviceView):
    def get(self, request):
        device = self.device(request)
        return Response({'operators': [_operator_data(item.user) for item in pos_operator_queryset(device.branch)]})


class OperatorLoginView(POSDeviceView):
    def post(self, request):
        device = self.device(request, check_version=True)
        session, token = authenticate_operator(device, _required(request.data, 'operator_id'), _required(request.data, 'pin'))
        return Response({
            'operator_session': {'token': token, 'expires_at': session.expires_at},
            'operator': _operator_data(session.operator),
            'bootstrap_required': True,
        })


class OperatorLogoutView(POSDeviceView):
    def post(self, request):
        device = self.device(request, check_version=True)
        logout_operator(require_operator_session(request, device))
        return Response(status=status.HTTP_204_NO_CONTENT)


class BootstrapView(POSDeviceView):
    def get(self, request):
        device = self.device(request, check_version=True)
        session = require_operator_session(request, device)
        permissions, modules = modules_for(session.operator, device)
        cash_mode, cash_register = effective_cash_settings(device)
        return Response({
            'server_time': timezone.now(),
            'release': version_gate(device.app_version),
            'company': {'id': device.branch.company_id, 'trade_name': device.branch.company.trade_name, 'operational': True},
            'branch': {'id': device.branch_id, 'name': device.branch.name, 'operational': True},
            'device': {
                'id': device.id, 'name': device.name, 'type': device.device_type, 'status': device.status,
                'capabilities': device.capabilities,
            },
            'operator': _operator_data(session.operator),
            'permissions': sorted(permissions),
            'modules': modules,
            'cash': {
                'mode': cash_mode,
                'register': ({'id': cash_register.pk, 'name': cash_register.name} if cash_register else None),
                'session': None,
            },
            'settings': {'receipt': effective_settings(device)},
        })


class HeartbeatView(POSDeviceView):
    def post(self, request):
        device = self.device(request)
        app_version = request.data.get('app_version')
        if app_version is not None:
            device.app_version = str(app_version).strip()
        capabilities = request.data.get('capabilities')
        if isinstance(capabilities, dict):
            device.capabilities = capabilities
        device.last_seen_at = timezone.now()
        device.save(update_fields=['app_version', 'capabilities', 'last_seen_at', 'updated_at'])
        return Response({'device': {'id': device.id, 'status': device.status}, 'release': version_gate(device.app_version)})


class PinConfirmView(POSPublicView):
    def post(self, request):
        set_pos_pin(_required(request.data, 'token'), _required(request.data, 'pin'))
        return Response({'detail': 'PIN configurado com sucesso.'})


class POSAdminDeviceViewSet(viewsets.ModelViewSet):
    """Backoffice-only lifecycle and settings for already paired POS devices."""

    serializer_class = POSAdminDeviceSerializer
    permission_classes = [FunctionalCompanyPermission]
    pagination_class = StandardPagination
    http_method_names = ('get', 'patch', 'put', 'post', 'delete', 'head', 'options')
    permission_codes = {
        'list': 'pos_devices.view',
        'retrieve': 'pos_devices.view',
        'update': 'pos_devices.manage',
        'partial_update': 'pos_devices.manage',
        'block': 'pos_devices.manage',
        'unblock': 'pos_devices.manage',
        'revoke': 'pos_devices.manage',
        'replace': 'pos_devices.manage',
        'settings': 'pos_devices.manage',
    }
    audit_fields = ('name', 'status', 'app_version', 'os_version', 'device_model', 'last_seen_at')

    def get_queryset(self):
        company_id = self.request.query_params.get('company')
        if not company_id:
            raise ValidationError({'company': 'Selecione uma empresa para consultar dispositivos POS.'})
        permission_code = self.permission_codes.get(self.action, 'pos_devices.view')
        queryset = POSDevice.objects.filter(
            branch__in=accessible_branches(self.request.user, permission_code),
            branch__company_id=company_id,
        ).select_related('branch__company', 'replaced_by')
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)
        return queryset

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, self.audit_fields)
        device = serializer.save()
        audit_log(
            actor=self.request.user, action='pos.device.update', obj=device,
            company=device.branch.company, branch=device.branch, before=before,
            after=model_snapshot(device, self.audit_fields),
        )

    def _transition(self, request, expected_status, target_status, *, replacement=None):
        device = self.get_object()
        if device.status != expected_status:
            raise DomainValidationError(
                code='device_status_transition_invalid',
                message='Esta transicao nao esta disponivel para o status atual do dispositivo.',
                status_code=409,
            )
        if target_status == POSDevice.Status.ACTIVE:
            assert_branch_device_limit(device.branch)
        return set_device_status(device, target_status, actor=request.user, replacement=replacement)

    @action(detail=True, methods=('post',))
    def block(self, request, pk=None):
        device = self._transition(request, POSDevice.Status.ACTIVE, POSDevice.Status.BLOCKED)
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=('post',))
    def unblock(self, request, pk=None):
        device = self._transition(request, POSDevice.Status.BLOCKED, POSDevice.Status.ACTIVE)
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=('post',))
    def revoke(self, request, pk=None):
        device = self.get_object()
        if device.status not in {POSDevice.Status.ACTIVE, POSDevice.Status.BLOCKED}:
            raise DomainValidationError(
                code='device_status_transition_invalid',
                message='Este dispositivo nao pode ser revogado no status atual.',
                status_code=409,
            )
        device = set_device_status(device, POSDevice.Status.REVOKED, actor=request.user)
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=('post',))
    def replace(self, request, pk=None):
        device = self.get_object()
        replacement_id = request.data.get('replacement_device')
        replacement = self.get_queryset().filter(pk=replacement_id).first()
        if device.status != POSDevice.Status.ACTIVE or not replacement or replacement == device or replacement.status != POSDevice.Status.ACTIVE:
            raise DomainValidationError(
                code='device_replacement_invalid',
                message='Informe outro dispositivo ativo da mesma filial para a substituicao.',
                status_code=409,
            )
        device = set_device_status(device, POSDevice.Status.REPLACED, actor=request.user, replacement=replacement)
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=('get', 'patch', 'delete'))
    def settings(self, request, pk=None):
        device = self.get_object()
        instance = POSDeviceSettings.objects.filter(device=device).first()
        if request.method == 'GET':
            return Response(POSDeviceSettingsSerializer(
                instance or POSDeviceSettings(device=device), context={'device': device}
            ).data)
        if request.method == 'DELETE':
            if instance:
                before = model_snapshot(instance, POSDeviceSettingsSerializer.Meta.fields)
                instance.delete()
                audit_log(
                    actor=request.user, action='pos.device.settings.reset', obj=device,
                    company=device.branch.company, branch=device.branch, before=before,
                )
            return Response(status=status.HTTP_204_NO_CONTENT)
        instance, _ = POSDeviceSettings.objects.get_or_create(device=device)
        fields = tuple(field for field in POSDeviceSettingsSerializer.Meta.fields if field not in {'id', 'device', 'effective_settings', 'created_at', 'updated_at'})
        before = model_snapshot(instance, fields)
        serializer = POSDeviceSettingsSerializer(instance, data=request.data, partial=True, context={'device': device})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        audit_log(
            actor=request.user, action='pos.device.settings.update', obj=instance,
            company=device.branch.company, branch=device.branch, before=before,
            after=model_snapshot(instance, fields),
        )
        return Response(POSDeviceSettingsSerializer(instance, context={'device': device}).data)
