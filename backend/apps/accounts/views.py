from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.companies.selectors import (
    active_operational_branches,
    active_operational_companies,
)

from .models import User
from .serializers import LoginSerializer, UserSerializer


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'csrf_token': get_token(request)})


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].lower()
        password = serializer.validated_data['password']

        try:
            account = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {'detail': 'E-mail ou senha invalidos.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not account.can_login:
            return Response(
                {'detail': 'E-mail ou senha invalidos.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not account.is_active:
            return Response(
                {'detail': 'Seu usuario esta inativo. Procure um administrador.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not account.check_password(password):
            return Response(
                {'detail': 'E-mail ou senha invalidos.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = authenticate(
            request=request,
            email=email,
            password=password,
        )
        if user is None:
            return Response(
                {'detail': 'Nao foi possivel autenticar esta conta.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_superuser:
            active_companies = active_operational_companies(user)
            if not active_companies.exists():
                has_inactive_profile = user.company_accesses.filter(
                    is_active=True,
                    access_profile__status='inactive',
                    company__status='active',
                ).exists()
                has_inactive_company = user.company_accesses.filter(
                    is_active=True,
                    company__status='inactive',
                ).exists()
                message = (
                    'O perfil de acesso vinculado ao seu usuario esta inativo.'
                    if has_inactive_profile
                    else 'A empresa vinculada ao seu usuario esta inativa.'
                    if has_inactive_company
                    else 'Seu usuario nao possui acesso a uma empresa ativa.'
                )
                return Response({'detail': message}, status=status.HTTP_403_FORBIDDEN)

            if not active_operational_branches(user).exists():
                has_inactive_branch = user.branch_accesses.filter(
                    is_active=True,
                    branch__company__in=active_companies,
                    branch__status='inactive',
                ).exists()
                message = (
                    'A filial vinculada ao seu usuario esta inativa.'
                    if has_inactive_branch
                    else 'Seu usuario nao possui acesso a uma filial ativa.'
                )
                return Response({'detail': message}, status=status.HTTP_403_FORBIDDEN)

        login(request, user)
        response = Response(UserSerializer(user, context={'request': request}).data)
        response['X-CSRFToken'] = get_token(request)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user, context={'request': request}).data)

    def patch(self, request):
        serializer = UserSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
