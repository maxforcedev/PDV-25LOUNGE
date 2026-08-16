from rest_framework.authentication import SessionAuthentication as BaseSessionAuthentication
from rest_framework.exceptions import AuthenticationFailed


class SessionAuthentication(BaseSessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _ = result
            if not user.can_login or not user.is_active:
                raise AuthenticationFailed('Sessao de usuario sem acesso ao sistema.')
        return result

    def authenticate_header(self, request):
        return 'Session'
