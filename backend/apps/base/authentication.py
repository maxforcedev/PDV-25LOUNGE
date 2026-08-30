from django.http import HttpRequest
from axes.backends import AxesStandaloneBackend as BaseAxesStandaloneBackend
from rest_framework.authentication import SessionAuthentication as BaseSessionAuthentication
from rest_framework.exceptions import AuthenticationFailed


class AxesStandaloneBackend(BaseAxesStandaloneBackend):
    def authenticate(self, request=None, **credentials):
        if request is None:
            # Django's test client and programmatic callers omit a request; retain Axes
            # enforcement by providing the minimal request context it requires.
            request = HttpRequest()
            request.META['REMOTE_ADDR'] = '127.0.0.1'
        return super().authenticate(request, **credentials)


class SessionAuthentication(BaseSessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _ = result
            if not user.can_login or not user.is_active:
                raise AuthenticationFailed('Sessão de usuário sem acesso ao sistema.')
            if not request.headers.get('X-Support-Session-ID'):
                from apps.saas.permissions import enforce_saas_request

                enforce_saas_request(request, user)
        return result

    def authenticate_header(self, request):
        return 'Session'
