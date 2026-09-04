import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from apps.base.audit import audit_log
from apps.base.exceptions import DomainValidationError
from apps.companies.models import Branch, Status, UserBranchAccess, UserCompanyAccess, UserPermissionBlock
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.saas.services import effective_entitlement, resolve_effective_status

from .models import (
    AuthenticationChallenge, BranchPOSSettings, POSDevice, POSDeviceSettings,
    POSOperatorPinAttempt, POSOperatorSession, POSPinResetToken, POSRequestRateLimit,
    PairingFlow,
)

OTP_TTL = timedelta(minutes=5)
PAIRING_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(minutes=1)
PIN_LOCK_TTL = timedelta(minutes=15)
PIN_FAILURE_LIMIT = 5


def _error(code, message, details=None, status_code=400):
    error = DomainValidationError(code=code, message=message, details=details)
    error.status_code = status_code
    raise error


def _token():
    return secrets.token_urlsafe(48)


def _fingerprint(value):
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def _request_key(request, prefix, supplied=''):
    ip = request.META.get('REMOTE_ADDR', '')
    return _fingerprint(f'{prefix}:{ip}:{supplied}')


def _limited(key, *, limit=5):
    row, _ = POSRequestRateLimit.objects.get_or_create(key=key)
    return bool(row.locked_until and row.locked_until > timezone.now())


@transaction.atomic
def _record_limit_failure(key, *, limit=5):
    row, _ = POSRequestRateLimit.objects.select_for_update().get_or_create(key=key)
    row.failures += 1
    if row.failures >= limit:
        row.locked_until = timezone.now() + PIN_LOCK_TTL
        row.failures = 0
    row.save(update_fields=['failures', 'locked_until', 'updated_at'])


def _clear_limit(key):
    POSRequestRateLimit.objects.filter(key=key).update(failures=0, locked_until=None)


def _version_parts(version):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:[-+].*)?', (version or '').strip())
    return tuple(int(part) for part in match.groups()) if match else None


def version_gate(version):
    parsed = _version_parts(version)
    minimum = _version_parts(settings.POS_MINIMUM_SUPPORTED_VERSION)
    if not parsed or not minimum or parsed < minimum:
        _error('pos_update_required', 'A versao deste POS nao e mais suportada.', status_code=426)
    latest = _version_parts(settings.POS_LATEST_VERSION)
    return {
        'current_version': version,
        'latest_version': settings.POS_LATEST_VERSION,
        'minimum_supported_version': settings.POS_MINIMUM_SUPPORTED_VERSION,
        'update_available': bool(latest and parsed < latest),
        'update_required': False,
    }


def pos_enabled(company):
    status = resolve_effective_status(company)
    if not status['can_operate']:
        _error('tenant_not_operational', 'O tenant nao esta operacional.', status_code=403)
    entitlement = effective_entitlement(company, 'pos.enabled')
    if entitlement is None:
        # Legacy tenants retain the pre-enforcement behavior used by the SaaS domain.
        from apps.saas.services import get_global_settings
        if not get_global_settings().enforcement_enabled:
            return True
        _error('pos_not_entitled', 'O plano nao habilita o POS.', status_code=403)
    if not entitlement.enabled:
        _error('pos_not_entitled', 'O plano nao habilita o POS.', status_code=403)
    return True


def assert_branch_device_limit(branch):
    entitlement = effective_entitlement(branch.company, 'pos.devices.max')
    if entitlement is None:
        from apps.saas.services import get_global_settings
        if not get_global_settings().enforcement_enabled:
            return
        _error('pos_device_limit_unavailable', 'O plano nao define o limite de dispositivos POS.', status_code=403)
    if not entitlement.enabled:
        _error('pos_device_limit_unavailable', 'O plano nao habilita dispositivos POS.', status_code=403)
    if not entitlement.unlimited and POSDevice.objects.filter(branch=branch, status=POSDevice.Status.ACTIVE).count() >= entitlement.limit_value:
        _error('pos_device_limit_reached', 'O limite de dispositivos POS desta filial foi atingido.', status_code=409)


def validate_device_operational(device, *, check_version=True):
    device = POSDevice.objects.select_related('branch__company').get(pk=device.pk)
    if device.status != POSDevice.Status.ACTIVE:
        _error('device_not_active', 'O dispositivo nao esta ativo.', status_code=403)
    if device.branch.status != Status.ACTIVE:
        _error('branch_not_operational', 'A filial nao esta operacional.', status_code=403)
    pos_enabled(device.branch.company)
    if check_version:
        version_gate(device.app_version)
    return device


def authenticate_device(credential):
    if not credential or len(credential) > 512:
        raise AuthenticationFailed('Credencial de dispositivo invalida.')
    for device in POSDevice.objects.exclude(credential_hash='').only('id', 'credential_hash'):
        if check_password(credential, device.credential_hash):
            try:
                return validate_device_operational(device, check_version=False)
            except DomainValidationError as error:
                raise AuthenticationFailed(error.payload['message']) from error
    raise AuthenticationFailed('Credencial de dispositivo invalida.')


def _mask_email(value):
    local, _, domain = value.partition('@')
    return f'{local[:1]}***@{domain}' if domain else '***'


def pairing_channels(branch):
    # E-mail is the only delivery channel wired in this backend; phone numbers are never exposed.
    emails = []
    for value in (branch.email, branch.company.email):
        value = (value or '').strip().lower()
        if value and value not in emails:
            emails.append(value)
    return [
        {'id': _fingerprint(f'email:{value}')[:32], 'type': 'email', 'masked': _mask_email(value), '_destination': value}
        for value in emails
    ]


def identify_branch(identifier, request):
    cleaned = re.sub(r'\D', '', str(identifier or ''))
    identifier = str(identifier or '').strip()
    key = _request_key(request, 'pairing-identify', identifier)
    if _limited(key):
        _error('pairing_rate_limited', 'Tente novamente mais tarde.', status_code=429)
    branch = None
    if len(cleaned) == 14:
        branch = Branch.objects.select_related('company').filter(cnpj=cleaned).first()
    if branch is None:
        branch = Branch.objects.select_related('company').filter(licensing_code__iexact=identifier).first()
    if not branch:
        _record_limit_failure(key)
        _error('branch_not_found', 'Filial nao encontrada.', status_code=404)
    if branch.status != Status.ACTIVE:
        _error('branch_not_operational', 'A filial nao esta operacional.', status_code=403)
    pos_enabled(branch.company)
    channels = pairing_channels(branch)
    if not channels:
        _error('pairing_contact_unavailable', 'A filial nao possui um contato de pareamento disponivel.', status_code=409)
    flow = PairingFlow.objects.create(branch=branch, expires_at=timezone.now() + PAIRING_TTL)
    return flow, channels


def request_otp(flow_id, channel_id, request):
    flow = PairingFlow.objects.select_related('branch__company').filter(pk=flow_id).first()
    if not flow or flow.expires_at <= timezone.now():
        _error('pairing_flow_expired', 'O fluxo de pareamento expirou.', status_code=400)
    validate_device_branch_for_pairing(flow.branch)
    channel = next((item for item in pairing_channels(flow.branch) if secrets.compare_digest(item['id'], str(channel_id))), None)
    if not channel:
        _error('pairing_channel_invalid', 'Canal de pareamento invalido.', status_code=400)
    key = _request_key(request, 'pairing-otp', f'{flow.id}:{channel_id}')
    if _limited(key):
        _error('pairing_rate_limited', 'Tente novamente mais tarde.', status_code=429)
    previous = AuthenticationChallenge.objects.filter(pairing_flow=flow, consumed_at__isnull=True).order_by('-created_at').first()
    if previous and previous.created_at + RESEND_COOLDOWN > timezone.now():
        seconds = int((previous.created_at + RESEND_COOLDOWN - timezone.now()).total_seconds()) + 1
        _error('otp_resend_cooldown', 'Aguarde antes de solicitar outro codigo.', {'resend_available_in_seconds': seconds}, 429)
    AuthenticationChallenge.objects.filter(pairing_flow=flow, consumed_at__isnull=True).update(consumed_at=timezone.now())
    code = f'{secrets.randbelow(1_000_000):06d}'
    challenge = AuthenticationChallenge.objects.create(
        pairing_flow=flow, branch=flow.branch, channel=channel['type'],
        destination_fingerprint=_fingerprint(channel['_destination']), destination_masked=channel['masked'],
        code_hash=make_password(code), expires_at=timezone.now() + OTP_TTL,
        resend_count=(previous.resend_count + 1) if previous else 0,
    )
    send_mail('Codigo de pareamento CORE POS', f'Seu codigo de pareamento e: {code}', settings.DEFAULT_FROM_EMAIL, [channel['_destination']], fail_silently=False)
    return challenge


def validate_device_branch_for_pairing(branch):
    if branch.status != Status.ACTIVE:
        _error('branch_not_operational', 'A filial nao esta operacional.', status_code=403)
    pos_enabled(branch.company)


def confirm_pairing(challenge_id, code, device_data, request):
    key = _request_key(
        request,
        'pairing-confirm',
        f'{challenge_id}:{device_data.get("hardware_identifier", "")}',
    )
    with transaction.atomic():
        challenge = AuthenticationChallenge.objects.select_for_update().select_related('branch__company').filter(pk=challenge_id).first()
        if not challenge or challenge.purpose != AuthenticationChallenge.Purpose.POS_DEVICE_PAIRING:
            _error('otp_invalid', 'Codigo de verificacao invalido.', status_code=400)
        if challenge.consumed_at or challenge.expires_at <= timezone.now():
            _error('otp_expired_or_consumed', 'Codigo de verificacao expirado ou ja utilizado.', status_code=400)
        if _limited(key):
            _error('otp_rate_limited', 'Tente novamente mais tarde.', status_code=429)
        invalid_otp = challenge.attempts >= challenge.max_attempts or not check_password(str(code), challenge.code_hash)
        if invalid_otp:
            challenge.attempts += 1
            if challenge.attempts >= challenge.max_attempts:
                challenge.consumed_at = timezone.now()
            challenge.save(update_fields=['attempts', 'consumed_at', 'updated_at'])
        else:
            validate_device_branch_for_pairing(challenge.branch)
            branch = Branch.objects.select_for_update().get(pk=challenge.branch_id)
            active_devices = POSDevice.objects.filter(branch=branch, status=POSDevice.Status.ACTIVE).count()
            assert_branch_device_limit(branch)
            credential = _token()
            now = timezone.now()
            device = POSDevice.objects.create(
                branch=branch, name=str(device_data['name']).strip(), device_type=device_data.get('device_type', POSDevice.DeviceType.POS),
                status=POSDevice.Status.ACTIVE, credential_hash=make_password(credential), app_version=str(device_data.get('app_version', '')).strip(),
                os_version=str(device_data.get('os_version', '')).strip(), device_model=str(device_data.get('device_model', '')).strip(),
                hardware_identifier_hash=_fingerprint(str(device_data.get('hardware_identifier', ''))) if device_data.get('hardware_identifier') else '',
                capabilities=device_data.get('capabilities') if isinstance(device_data.get('capabilities'), dict) else {}, paired_at=now,
            )
            challenge.consumed_at = now
            challenge.save(update_fields=['consumed_at', 'updated_at'])
            _clear_limit(key)
            audit_log(action='pos.device.paired', obj=device, company=branch.company, branch=branch, after={'status': device.status}, metadata={'challenge_id': str(challenge.id), 'active_devices_before': active_devices})
    if invalid_otp:
        _record_limit_failure(key)
        _error('otp_invalid', 'Codigo de verificacao invalido.', status_code=400)
    return device, credential


def pos_operator_queryset(branch):
    candidates = UserBranchAccess.objects.filter(
        branch=branch, is_active=True, access_profile__status=Status.ACTIVE,
        user__is_active=True, user__archived_at__isnull=True, user__can_access_pos=True,
        user__pos_pin_hash__gt='', user__company_accesses__company_id=branch.company_id,
        user__company_accesses__is_active=True, user__company_accesses__archived_at__isnull=True,
        user__company_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        access_profile__permissions__status=Status.ACTIVE,
        access_profile__permissions__code__in=OPERATING_PERMISSION_CODES,
    ).select_related('user', 'access_profile').prefetch_related('access_profile__permissions').distinct()
    blocked = {}
    for user_id, code in UserPermissionBlock.objects.filter(
        company_id=branch.company_id, is_active=True,
    ).filter(Q(branch_id=branch.pk) | Q(branch__isnull=True)).values_list('user_id', 'permission__code'):
        blocked.setdefault(user_id, set()).add(code)
    eligible_ids = [
        access.user_id for access in candidates
        if operator_permission_codes(access.user, branch, access.access_profile, blocked.get(access.user_id, set()))
    ]
    return candidates.filter(user_id__in=eligible_ids).order_by('user__first_name', 'user__last_name', 'user__id')


def operator_permission_codes(operator, branch, profile=None, blocked_codes=None):
    profile = profile or UserBranchAccess.objects.filter(user=operator, branch=branch, is_active=True).select_related('access_profile').first().access_profile
    blocked_codes = blocked_codes if blocked_codes is not None else set(
        UserPermissionBlock.objects.filter(company_id=branch.company_id, user=operator, is_active=True).filter(
            Q(branch=branch) | Q(branch__isnull=True)
        ).values_list('permission__code', flat=True)
    )
    return set(profile.permissions.filter(status=Status.ACTIVE).values_list('code', flat=True)) - set(blocked_codes)


def eligible_operator(branch, operator_id):
    access = pos_operator_queryset(branch).filter(user_id=operator_id).first()
    return access.user if access else None


def authenticate_operator(device, operator_id, pin):
    device = validate_device_operational(device)
    operator = eligible_operator(device.branch, operator_id)
    if not operator:
        _error('operator_not_eligible', 'Operador indisponivel para este dispositivo.', status_code=403)
    with transaction.atomic():
        attempt, _ = POSOperatorPinAttempt.objects.select_for_update().get_or_create(device=device, operator=operator)
        now = timezone.now()
        rate_limited = bool(attempt.locked_until and attempt.locked_until > now)
        pin_invalid = not rate_limited and (
            not re.fullmatch(r'\d{6}', str(pin or '')) or not check_password(str(pin), operator.pos_pin_hash)
        )
        if pin_invalid:
            attempt.failures += 1
            if attempt.failures >= PIN_FAILURE_LIMIT:
                attempt.failures = 0
                attempt.locked_until = now + PIN_LOCK_TTL
            attempt.save(update_fields=['failures', 'locked_until', 'updated_at'])
        elif not rate_limited:
            attempt.failures = 0
            attempt.locked_until = None
            attempt.save(update_fields=['failures', 'locked_until', 'updated_at'])
            token = _token()
            session = POSOperatorSession.objects.create(device=device, operator=operator, token_hash=make_password(token), expires_at=now + timedelta(minutes=settings.POS_OPERATOR_SESSION_MINUTES))
            audit_log(actor=operator, action='pos.operator.login', obj=session, company=device.branch.company, branch=device.branch, metadata={'device_id': str(device.id)})
    if rate_limited:
        _error('pin_rate_limited', 'PIN temporariamente bloqueado.', status_code=429)
    if pin_invalid:
        _error('pin_invalid', 'PIN invalido.', status_code=401)
    return session, token


def authenticate_operator_session(device, token):
    now = timezone.now()
    for session in POSOperatorSession.objects.filter(device=device, ended_at__isnull=True, expires_at__gt=now).select_related('operator'):
        if check_password(token, session.token_hash):
            if not eligible_operator(device.branch, session.operator_id):
                raise AuthenticationFailed('Operador nao esta mais elegivel.')
            return session
    raise AuthenticationFailed('Sessao do operador ausente ou invalida.')


@transaction.atomic
def logout_operator(session):
    session = POSOperatorSession.objects.select_for_update().get(pk=session.pk)
    if not session.ended_at:
        session.ended_at = timezone.now()
        session.save(update_fields=['ended_at', 'updated_at'])
        audit_log(actor=session.operator, action='pos.operator.logout', obj=session, company=session.device.branch.company, branch=session.device.branch, metadata={'device_id': str(session.device_id)})


def create_pin_reset_token(user, company, actor=None):
    token = _token()
    row = POSPinResetToken.objects.create(
        user=user,
        company=company,
        created_by=actor,
        token_hash=make_password(token),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    audit_log(
        actor=actor,
        action='pos.operator.pin_reset_requested',
        obj=row,
        company=company,
        metadata={'user_id': user.pk},
    )
    return row, token


def send_pos_pin_setup(user, company, actor=None):
    if not user.can_access_pos:
        _error('pos_access_required', 'O operador precisa ter acesso ao POS habilitado.', status_code=409)
    if not user.email:
        _error('pos_pin_email_unavailable', 'O operador precisa de e-mail para receber o link de PIN.', status_code=409)
    _, token = create_pin_reset_token(user, company, actor)
    from urllib.parse import urlencode

    url = f'{settings.FRONTEND_URL.rstrip("/")}/pos/pin?{urlencode({"token": token})}'
    send_mail('Configure seu PIN do CORE POS', f'Use este link de uso unico para configurar seu PIN: {url}', settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


@transaction.atomic
def rotate_device_credential(device, actor=None):
    device = POSDevice.objects.select_for_update().select_related('branch__company').get(pk=device.pk)
    if device.status != POSDevice.Status.ACTIVE:
        _error('device_not_active', 'A credencial so pode ser rotacionada para dispositivo ativo.', status_code=409)
    credential = _token()
    device.credential_hash = make_password(credential)
    device.save(update_fields=['credential_hash', 'updated_at'])
    POSOperatorSession.objects.filter(device=device, ended_at__isnull=True).update(ended_at=timezone.now())
    audit_log(actor=actor, action='pos.device.credential_rotated', obj=device, company=device.branch.company, branch=device.branch)
    return credential


@transaction.atomic
def set_device_status(device, status, actor=None, replacement=None):
    device = POSDevice.objects.select_for_update().select_related('branch__company').get(pk=device.pk)
    if status not in {POSDevice.Status.BLOCKED, POSDevice.Status.REVOKED, POSDevice.Status.ACTIVE, POSDevice.Status.REPLACED}:
        _error('device_status_invalid', 'Status de dispositivo invalido.')
    now = timezone.now()
    device.status = status
    if status == POSDevice.Status.BLOCKED:
        device.blocked_at = now
    elif status == POSDevice.Status.REVOKED:
        device.revoked_at = now
        device.credential_hash = ''
    elif status == POSDevice.Status.REPLACED:
        if not replacement or replacement.branch_id != device.branch_id:
            _error('device_replacement_invalid', 'A substituicao deve pertencer a mesma filial.')
        device.replaced_at = now
        device.replaced_by = replacement
        device.credential_hash = ''
    device.save()
    if status in {POSDevice.Status.REVOKED, POSDevice.Status.REPLACED}:
        POSOperatorSession.objects.filter(device=device, ended_at__isnull=True).update(ended_at=now)
    audit_log(actor=actor, action=f'pos.device.{status.lower()}', obj=device, company=device.branch.company, branch=device.branch, after={'status': status})
    return device


@transaction.atomic
def rotate_licensing_code(branch, actor=None):
    branch = Branch.objects.select_for_update().get(pk=branch.pk)
    before = branch.licensing_code
    branch.licensing_code = Branch.generate_licensing_code()
    branch.save(update_fields=['licensing_code', 'updated_at'])
    audit_log(actor=actor, action='pos.branch.licensing_code_rotated', obj=branch, company=branch.company, branch=branch, before={'licensing_code': before}, after={'licensing_code': branch.licensing_code})
    return branch


@transaction.atomic
def set_pos_pin(token, pin):
    if not re.fullmatch(r'\d{6}', str(pin or '')):
        _error('pin_invalid_format', 'O PIN deve ter exatamente 6 digitos numericos.')
    row = next((item for item in POSPinResetToken.objects.select_for_update().select_related('user').filter(consumed_at__isnull=True, expires_at__gt=timezone.now()) if check_password(token, item.token_hash)), None)
    if not row:
        _error('pin_reset_token_invalid', 'Link de PIN invalido ou expirado.', status_code=400)
    row.user.pos_pin_hash = make_password(pin)
    row.user.save(update_fields=['pos_pin_hash', 'updated_at'])
    now = timezone.now()
    row.consumed_at = now
    row.save(update_fields=['consumed_at', 'updated_at'])
    POSPinResetToken.objects.filter(
        user=row.user,
        consumed_at__isnull=True,
    ).exclude(pk=row.pk).update(consumed_at=now)
    POSOperatorSession.objects.filter(operator=row.user, ended_at__isnull=True).update(ended_at=now)
    audit_log(actor=row.user, action='pos.operator.pin_set', obj=row.user, company=row.company)


def effective_settings(device):
    defaults = BranchPOSSettings.objects.filter(branch=device.branch).first()
    override = POSDeviceSettings.objects.filter(device=device).first()
    fields = ('receipt_printer', 'sale_confirmation_print', 'receipt_print_mode', 'receipt_format', 'paper_width', 'copies', 'local_report_print_preferences', 'sound_enabled', 'screen_timeout_seconds', 'peripherals')
    result = {field: getattr(defaults, field) if defaults else None for field in fields}
    if override:
        for field in fields:
            value = getattr(override, field)
            if value not in (None, ''):
                result[field] = value
    if result['receipt_printer'] == 'stone_integrated' and not device.capabilities.get('integrated_printer'):
        result['receipt_printer'] = 'none'
    return result


def effective_cash_settings(device):
    defaults = BranchPOSSettings.objects.filter(branch=device.branch).select_related('default_cash_register').first()
    override = POSDeviceSettings.objects.filter(device=device).select_related('default_cash_register').first()
    mode = (override.cash_binding_mode if override and override.cash_binding_mode else None) or getattr(defaults, 'cash_binding_mode', 'FLEXIBLE')
    register = (override.default_cash_register if override and override.default_cash_register_id else None) or getattr(defaults, 'default_cash_register', None)
    return mode, register


def modules_for(operator, device):
    permissions = operator_permission_codes(operator, device.branch)
    settings_obj = getattr(device.branch, 'settings', None)
    enabled = pos_enabled(device.branch.company)
    operational = enabled and device.branch.status == Status.ACTIVE
    return permissions, {
        'quick_sale': {'enabled': bool(operational and settings_obj and settings_obj.uses_counter and 'sales.create' in permissions)},
        'commands': {'enabled': bool(operational and settings_obj and settings_obj.uses_commands and permissions.intersection({'commands.view', 'commands.open', 'commands.add_items'}))},
        'ticket_validator': {'enabled': False, 'reason': 'not_implemented'},
        'inventory': {'enabled': False, 'reason': 'not_implemented'},
        'reports': {'enabled': False, 'reason': 'not_implemented'},
    }
