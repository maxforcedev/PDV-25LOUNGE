from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from apps.base.authentication import SessionAuthentication
from apps.base.audit import set_support_audit_context

from .models import SupportSession
from .permissions import enforce_saas_request
from .services import user_has_platform_permission


class SupportSessionAuthentication(SessionAuthentication):
    """Resolve a temporary support context without creating tenant membership."""

    def authenticate(self, request):
        session_id = request.headers.get('X-Support-Session-ID')
        if not session_id:
            return None
        result = super().authenticate(request)
        if result is None:
            return None
        actor, auth = result
        try:
            support_session = SupportSession.objects.select_related(
                'company', 'impersonated_user'
            ).get(pk=session_id, actor=actor)
        except (SupportSession.DoesNotExist, ValueError) as error:
            raise AuthenticationFailed('Sessao de suporte invalida.') from error
        if support_session.ended_at or support_session.expires_at <= timezone.now():
            raise AuthenticationFailed('Sessao de suporte expirada ou encerrada.')
        if not user_has_platform_permission(actor, 'platform.support.manage'):
            raise AuthenticationFailed('Permissao de suporte inativa.')

        effective_user = support_session.impersonated_user or actor
        if not effective_user or not effective_user.is_active or not effective_user.can_login:
            raise AuthenticationFailed('Nao existe usuario valido para o contexto de suporte.')
        request.support_session = support_session
        request.support_actor = actor
        request.support_effective_user = effective_user
        support_branch_ids = tuple(
            support_session.company.branches.filter(
                status='active', company__status='active'
            ).order_by('pk').values_list('pk', flat=True)
        ) if not support_session.impersonated_user_id else ()
        request.support_branch_ids = support_branch_ids
        raw_request = getattr(request, '_request', request)
        raw_request.support_session = support_session
        raw_request.support_actor = actor
        raw_request.support_effective_user = effective_user
        raw_request.support_branch_ids = support_branch_ids
        set_support_audit_context(actor, support_session)
        enforce_saas_request(request, effective_user)
        return effective_user, auth
