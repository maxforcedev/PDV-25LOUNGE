from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.base.exceptions import DomainValidationError

from .authentication import POSDeviceAuthentication, require_device, require_operator_session
from .models import POSDevice
from .services import (
    authenticate_operator, confirm_pairing, effective_cash_settings, effective_settings, identify_branch, logout_operator,
    modules_for, pos_operator_queryset, request_otp, set_pos_pin, validate_device_operational,
    version_gate,
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
