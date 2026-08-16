from django.contrib.auth import logout


class CanLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and (not user.is_active or not user.can_login):
            logout(request)
        return self.get_response(request)
