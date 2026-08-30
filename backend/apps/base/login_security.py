from ipaddress import ip_address

from django.conf import settings
from django.http import HttpResponse, JsonResponse


INVALID_LOGIN_MESSAGE = 'E-mail ou senha inválidos.'


def _valid_ip(value):
    try:
        return str(ip_address(value))
    except (TypeError, ValueError):
        return None


def axes_client_ip(request):
    remote_address = _valid_ip(request.META.get('REMOTE_ADDR', ''))
    if not settings.TRUST_PROXY_HEADERS:
        return remote_address

    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    trusted_value = forwarded.rsplit(',', 1)[-1].strip() if forwarded else ''
    return _valid_ip(trusted_value) or remote_address


def axes_username(request, credentials=None):
    credentials = credentials or {}
    value = credentials.get('email')
    if value is None:
        data = getattr(request, 'data', request.POST)
        value = data.get('email') or data.get('username')
    return str(value).strip().lower() if value else None


def axes_lockout_message():
    return (
        'Muitas tentativas. Aguarde '
        f'{settings.AXES_COOLOFF_MINUTES} minutos e tente novamente.'
    )


def axes_lockout_response(request, original_response=None, credentials=None):
    message = axes_lockout_message()
    if request.path.startswith('/api/'):
        return JsonResponse({'detail': message}, status=429)
    return HttpResponse(message, status=429, content_type='text/plain')
