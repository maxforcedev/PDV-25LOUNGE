import mimetypes

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.base.audit import audit_log, model_snapshot
from apps.base.login_security import INVALID_LOGIN_MESSAGE, axes_lockout_message
from apps.companies.selectors import (
    active_operational_branches,
    active_operational_companies,
)

from .models import User
from .password_reset import send_password_reset
from .serializers import LoginSerializer, SelfProfileSerializer, UserSerializer


def _audit_scope(request, user):
    if user.is_superuser:
        return None, None, {'is_superuser': True}

    companies = list(active_operational_companies(user).order_by('pk'))
    branches = list(
        active_operational_branches(user).select_related('company').order_by('pk')
    )
    requested_branch_id = request.headers.get('X-Branch-ID')
    branch = next(
        (item for item in branches if str(item.pk) == str(requested_branch_id)),
        None,
    )
    if branch is None and not requested_branch_id and len(branches) == 1:
        branch = branches[0]
    company = branch.company if branch else (companies[0] if len(companies) == 1 else None)
    return company, branch, {
        'available_company_ids': [item.pk for item in companies],
        'available_branch_ids': [item.pk for item in branches],
    }


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

        user = authenticate(
            request=request,
            email=email,
            password=password,
        )
        if user is None:
            if getattr(request, 'axes_locked_out', False):
                return Response(
                    {'detail': axes_lockout_message()},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            return Response(
                {'detail': INVALID_LOGIN_MESSAGE},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.can_login:
            return Response(
                {'detail': INVALID_LOGIN_MESSAGE},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_superuser:
            active_companies = active_operational_companies(user)
            if not active_companies.exists():
                return Response(
                    {'detail': INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if not active_operational_branches(user).exists():
                return Response(
                    {'detail': INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_403_FORBIDDEN,
                )

        login(request, user)
        company, branch, metadata = _audit_scope(request, user)
        audit_log(
            actor=user,
            action='auth.login',
            obj=user,
            company=company,
            branch=branch,
            before={'authenticated': False},
            after={'authenticated': True},
            metadata=metadata,
        )
        response = Response(UserSerializer(user, context={'request': request}).data)
        response['X-CSRFToken'] = get_token(request)
        return response


@method_decorator(csrf_protect, name='dispatch')
class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        user = User.objects.filter(
            email__iexact=email,
            can_login=True,
            is_active=True,
            archived_at__isnull=True,
        ).first() if email else None
        if user and user.has_usable_password():
            send_password_reset(user=user, source='self_service')
        return Response({
            'detail': 'Se existir uma conta vinculada a este e-mail, enviaremos as instruções para redefinição.'
        })


@method_decorator(csrf_protect, name='dispatch')
class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset_confirm'

    def post(self, request):
        uid = str(request.data.get('uid', ''))
        token = str(request.data.get('token', ''))
        new_password = request.data.get('new_password', '')
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(
                pk=user_id,
                can_login=True,
                is_active=True,
                archived_at__isnull=True,
            )
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, token):
            raise ValidationError({'token': 'Este link é inválido ou expirou.'})
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as error:
            raise ValidationError({'new_password': list(error.messages)}) from error
        user.set_password(new_password)
        user.save(update_fields=['password', 'updated_at'])
        audit_log(
            actor=user,
            action='auth.password_reset_completed',
            obj=user,
            metadata={'source': 'self_service'},
        )
        return Response({'detail': 'Senha redefinida com sucesso.'})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = getattr(request, 'support_actor', request.user)
        support_session = getattr(request, 'support_session', None)
        if support_session:
            from apps.saas.services import end_support_session

            end_support_session(support_session, user)
        company, branch, metadata = _audit_scope(request, user)
        logout(request)
        audit_log(
            actor=user,
            action='auth.logout',
            obj=user,
            company=company,
            branch=branch,
            before={'authenticated': True},
            after={'authenticated': False},
            metadata=metadata,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _response_data(request, user):
        data = UserSerializer(user, context={'request': request}).data
        support_session = getattr(request, 'support_session', None)
        data['support_session'] = (
            {
                'id': support_session.pk,
                'actor': request.support_actor.pk,
                'actor_email': request.support_actor.email,
                'company': support_session.company_id,
                'company_name': support_session.company.trade_name,
                'impersonated_user': support_session.impersonated_user_id,
                'impersonated_user_name': (
                    str(support_session.impersonated_user)
                    if support_session.impersonated_user_id else None
                ),
                'mode': support_session.mode,
                'reason': support_session.reason,
                'expires_at': support_session.expires_at,
                'ended_at': support_session.ended_at,
                'created_at': support_session.created_at,
            }
            if support_session else None
        )
        return data

    def get(self, request):
        data = self._response_data(request, request.user)
        return Response(data)

    def patch(self, request):
        serializer = SelfProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        fields = tuple(serializer.validated_data)
        before = model_snapshot(request.user, fields)
        company, branch, metadata = _audit_scope(request, request.user)
        user = serializer.save()
        audit_log(
            actor=user,
            action='user.update_self',
            obj=user,
            company=company,
            branch=branch,
            before=before,
            after=model_snapshot(user, fields),
            metadata=metadata,
        )
        return Response(self._response_data(request, user))


class ProfilePhotoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        photo = request.user.profile_photo
        if not photo:
            raise Http404
        content_type = mimetypes.guess_type(photo.name)[0] or 'application/octet-stream'
        return FileResponse(photo.open('rb'), content_type=content_type)

    def delete(self, request):
        user = request.user
        photo = user.profile_photo
        if not photo:
            return Response(status=status.HTTP_204_NO_CONTENT)
        name = photo.name
        user.profile_photo = None
        user.save(update_fields=['profile_photo', 'updated_at'])
        photo.storage.delete(name)
        company, branch, metadata = _audit_scope(request, user)
        audit_log(
            actor=user, action='user.profile_photo_remove', obj=user,
            company=company, branch=branch,
            before={'profile_photo': name}, after={'profile_photo': None},
            metadata=metadata,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name='dispatch')
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')
        if not current_password or not new_password:
            raise ValidationError({'detail': 'Informe a senha atual e a nova senha.'})
        user = request.user
        if not user.check_password(current_password):
            raise ValidationError({'current_password': 'Senha atual incorreta.'})
        try:
            validate_password(new_password, user=user)
        except Exception as error:
            raise ValidationError({'new_password': list(error.messages)}) from error
        user.set_password(new_password)
        user.save(update_fields=['password', 'updated_at'])
        audit_log(
            actor=user, action='auth.password_change', obj=user,
            metadata={'source': 'self'},
        )
        return Response({'detail': 'Senha alterada com sucesso.'})
