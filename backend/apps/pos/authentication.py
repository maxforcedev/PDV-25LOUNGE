from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .services import authenticate_device, authenticate_operator_session


class POSDeviceAuthentication(BaseAuthentication):
    keyword = 'HTTP_X_POS_DEVICE_CREDENTIAL'

    def authenticate(self, request):
        credential = request.META.get(self.keyword)
        if not credential:
            return None
        device = authenticate_device(credential)
        request.pos_device = device
        return None


def require_device(request):
    device = getattr(request, 'pos_device', None)
    if not device:
        raise AuthenticationFailed('Credencial de dispositivo ausente ou invalida.')
    return device


def require_operator_session(request, device):
    token = request.META.get('HTTP_X_POS_OPERATOR_SESSION')
    if not token:
        raise AuthenticationFailed('Sessao do operador ausente ou invalida.')
    session = authenticate_operator_session(device, token)
    request.pos_operator_session = session
    return session
