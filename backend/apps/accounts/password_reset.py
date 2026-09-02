from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.base.audit import audit_log


def send_password_reset(*, user, actor=None, source):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f'{settings.FRONTEND_URL.rstrip("/")}/redefinir-senha?uid={uid}&token={token}'
    send_mail(
        subject='Redefinição da sua senha CORE',
        message=(
            'Recebemos uma solicitação para redefinir sua senha global do CORE.\n\n'
            f'Acesse o link para escolher uma nova senha: {reset_url}\n\n'
            'Se você não solicitou esta alteração, ignore esta mensagem.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        # A delivery failure must not disclose whether the address has an account.
        fail_silently=True,
    )
    audit_log(
        actor=actor,
        action='auth.password_reset_requested',
        obj=user,
        metadata={'source': source},
    )
