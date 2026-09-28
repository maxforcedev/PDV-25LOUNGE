import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.base.audit import audit_log

from .models import (
    PAYMENT_ATTEMPT_RESULT_FIELDS, PaymentAttempt, PaymentAttemptStatus, PaymentIntent,
    PaymentIntentOriginType, PaymentIntentStatus,
)


class PaymentIntegrationConflict(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


_UNSET = object()

_BLOCKING_QUICK_SALE_INTENT_STATUSES = (
    PaymentIntentStatus.CREATED,
    PaymentIntentStatus.READY,
    PaymentIntentStatus.PROCESSING,
    PaymentIntentStatus.DECLINED,
    PaymentIntentStatus.ERROR,
    PaymentIntentStatus.UNKNOWN,
    PaymentIntentStatus.APPROVED,
)


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str,
    ).encode()).hexdigest()


def _blocking_quick_sale_intent(origin_type, origin_id):
    if origin_type != PaymentIntentOriginType.QUICK_SALE:
        return None
    return PaymentIntent.objects.select_for_update().filter(
        origin_type=PaymentIntentOriginType.QUICK_SALE,
        origin_id=str(origin_id).strip(),
        status__in=_BLOCKING_QUICK_SALE_INTENT_STATUSES,
    ).first()


def _blocking_quick_sale_conflict():
    return PaymentIntegrationConflict(
        'blocking_quick_sale_intent',
        'Já existe um intent bloqueante para esta venda rápida.',
    )


def create_payment_intent(*, company, branch, pos_device, operator, origin_type, origin_id,
                           payment_method, amount, provider_connection, terminal,
                           idempotency_key, application_context=None):
    application_context = {} if application_context is None else application_context
    payload = {
        'branch': branch.pk,
        'pos_device': str(pos_device.pk),
        'operator': operator.pk,
        'origin_type': origin_type,
        'origin_id': str(origin_id),
        'payment_method': payment_method.pk,
        'amount': str(amount),
        'provider_connection': provider_connection.pk,
        'terminal': str(terminal.pk) if terminal else None,
        'application_context': application_context,
    }
    fingerprint = _fingerprint(payload)
    try:
        with transaction.atomic():
            existing = PaymentIntent.objects.select_for_update().filter(
                company=company, idempotency_key=idempotency_key,
            ).first()
            if existing:
                if existing.request_fingerprint != fingerprint:
                    raise PaymentIntegrationConflict(
                        'idempotency_key_conflict',
                        'A chave de idempotência já foi usada com outros dados.',
                    )
                return existing, True
            if _blocking_quick_sale_intent(origin_type, origin_id):
                raise _blocking_quick_sale_conflict()
            intent = PaymentIntent(
                company=company, branch=branch, pos_device=pos_device, operator=operator,
                origin_type=origin_type, origin_id=str(origin_id), payment_method=payment_method,
                amount=amount, provider_connection=provider_connection, terminal=terminal,
                idempotency_key=idempotency_key, request_fingerprint=fingerprint,
                application_context=application_context,
            )
            intent.full_clean()
            intent.save()
    except IntegrityError:
        with transaction.atomic():
            existing = PaymentIntent.objects.select_for_update().filter(
                company=company, idempotency_key=idempotency_key,
            ).first()
            if not existing and _blocking_quick_sale_intent(origin_type, origin_id):
                raise _blocking_quick_sale_conflict()
        if not existing:
            raise
        if existing.request_fingerprint != fingerprint:
            raise PaymentIntegrationConflict(
                'idempotency_key_conflict',
                'A chave de idempotência já foi usada com outros dados.',
            )
        return existing, True
    audit_log(
        actor=operator, action='payment_intent.created', obj=intent,
        company=company, branch=branch,
        after={'intent_id': str(intent.pk), 'status': intent.status, 'amount': str(intent.amount)},
        metadata={'idempotency_key': str(idempotency_key), 'provider_connection_id': provider_connection.pk},
    )
    return intent, False


def _save_intent_status(intent, status):
    intent.status = status
    intent._allow_status_transition = True
    try:
        intent.save(update_fields=(
            'status', 'approved_at', 'applied_at', 'cancelled_at', 'updated_at',
        ))
    finally:
        delattr(intent, '_allow_status_transition')


def _save_attempt_status(attempt, status, result_fields=()):
    attempt.status = status
    attempt._allow_status_transition = True
    attempt._allow_result_update = True
    try:
        attempt.save(update_fields=tuple(dict.fromkeys((
            'status', 'response_metadata', 'started_at', 'completed_at', *result_fields, 'updated_at',
        ))))
    finally:
        delattr(attempt, '_allow_status_transition')
        delattr(attempt, '_allow_result_update')


def _apply_attempt_result_data(attempt, result_data):
    if not result_data:
        return ()
    invalid_fields = set(result_data) - set(PAYMENT_ATTEMPT_RESULT_FIELDS)
    if invalid_fields:
        raise PaymentIntegrationConflict(
            'invalid_attempt_result_data',
            f'Campos de resultado inválidos: {", ".join(sorted(invalid_fields))}.',
        )
    for field, value in result_data.items():
        setattr(attempt, field, value)
    return tuple(result_data)


def create_payment_attempt(*, intent, provider_connection=None, terminal=_UNSET,
                           request_metadata=None):
    with transaction.atomic():
        intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
        if intent.status == PaymentIntentStatus.UNKNOWN:
            raise PaymentIntegrationConflict(
                'intent_unknown',
                'A transação possui estado desconhecido e exige reconciliação antes de nova tentativa.',
            )
        if intent.status in (PaymentIntentStatus.APPLIED, PaymentIntentStatus.REVERSED):
            raise PaymentIntegrationConflict('intent_terminal', 'O intent financeiro não aceita novas tentativas.')
        if intent.status not in {
            PaymentIntentStatus.READY, PaymentIntentStatus.DECLINED,
            PaymentIntentStatus.ERROR,
        }:
            raise PaymentIntegrationConflict(
                'intent_not_ready', 'O intent deve estar pronto, recusado ou com erro para nova tentativa.',
            )
        previous_status = intent.status
        _save_intent_status(intent, PaymentIntentStatus.PROCESSING)
        latest = intent.attempts.order_by('-attempt_number').values_list('attempt_number', flat=True).first()
        attempt = PaymentAttempt(
            intent=intent,
            provider_connection=provider_connection or intent.provider_connection,
            terminal=intent.terminal if terminal is _UNSET else terminal,
            attempt_number=(latest or 0) + 1,
            amount=intent.amount,
            request_metadata=request_metadata or {},
        )
        attempt.save()
    audit_log(
        actor=intent.operator, action='payment_attempt.created', obj=attempt,
        company=intent.company, branch=intent.branch,
        after={'attempt_id': str(attempt.pk), 'attempt_number': attempt.attempt_number, 'status': attempt.status},
        metadata={'intent_id': str(intent.pk), 'provider_connection_id': attempt.provider_connection_id},
    )
    audit_log(actor=intent.operator, action='payment_intent.status_changed', obj=intent,
              company=intent.company, branch=intent.branch,
              before={'status': previous_status}, after={'status': intent.status})
    return attempt


_INTENT_TRANSITIONS = {
    PaymentIntentStatus.CREATED: {PaymentIntentStatus.READY, PaymentIntentStatus.CANCELLED, PaymentIntentStatus.ERROR},
    PaymentIntentStatus.READY: {PaymentIntentStatus.CANCELLED, PaymentIntentStatus.ERROR},
    PaymentIntentStatus.PROCESSING: set(),
    PaymentIntentStatus.DECLINED: {PaymentIntentStatus.CANCELLED},
    PaymentIntentStatus.CANCELLED: set(),
    PaymentIntentStatus.ERROR: {PaymentIntentStatus.CANCELLED},
    PaymentIntentStatus.UNKNOWN: set(),
    PaymentIntentStatus.APPROVED: set(),
    PaymentIntentStatus.APPLIED: set(),
    PaymentIntentStatus.REVERSED: set(),
}

_ATTEMPT_TRANSITIONS = {
    PaymentAttemptStatus.CREATED: {PaymentAttemptStatus.PROCESSING, PaymentAttemptStatus.CANCELLED, PaymentAttemptStatus.ERROR},
    PaymentAttemptStatus.PROCESSING: {
        PaymentAttemptStatus.APPROVED, PaymentAttemptStatus.DECLINED, PaymentAttemptStatus.CANCELLED,
        PaymentAttemptStatus.ERROR, PaymentAttemptStatus.UNKNOWN,
    },
    PaymentAttemptStatus.UNKNOWN: {
        PaymentAttemptStatus.APPROVED, PaymentAttemptStatus.DECLINED,
        PaymentAttemptStatus.CANCELLED, PaymentAttemptStatus.ERROR,
    },
    PaymentAttemptStatus.APPROVED: set(),
    PaymentAttemptStatus.DECLINED: set(),
    PaymentAttemptStatus.CANCELLED: set(),
    PaymentAttemptStatus.ERROR: set(),
}


def transition_payment_intent(*, intent, status, actor=None):
    with transaction.atomic():
        intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
        if status not in _INTENT_TRANSITIONS[intent.status]:
            raise PaymentIntegrationConflict(
                'invalid_intent_transition', f'Transição inválida: {intent.status} para {status}.',
            )
        previous = intent.status
        now = timezone.now()
        if status == PaymentIntentStatus.APPROVED:
            intent.approved_at = now
        elif status == PaymentIntentStatus.CANCELLED:
            intent.cancelled_at = now
        _save_intent_status(intent, status)
    audit_log(actor=actor or intent.operator, action='payment_intent.status_changed', obj=intent,
              company=intent.company, branch=intent.branch,
              before={'status': previous}, after={'status': status})
    return intent


def transition_payment_attempt(*, attempt, status, actor=None, response_metadata=None, result_data=None):
    if status != PaymentAttemptStatus.PROCESSING:
        raise PaymentIntegrationConflict(
            'attempt_result_requires_resolution',
            'Resultados de tentativa devem ser registrados por resolve_payment_attempt.',
        )
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().select_related('intent').get(pk=attempt.pk)
        if status not in _ATTEMPT_TRANSITIONS[attempt.status]:
            raise PaymentIntegrationConflict(
                'invalid_attempt_transition', f'Transição inválida: {attempt.status} para {status}.',
            )
        previous = attempt.status
        result_fields = _apply_attempt_result_data(attempt, result_data)
        if response_metadata is not None:
            attempt.response_metadata = response_metadata
            result_fields = (*result_fields, 'response_metadata')
        if not attempt.started_at:
            attempt.started_at = timezone.now()
        attempt._require_active_resources = True
        try:
            _save_attempt_status(attempt, status, result_fields)
        finally:
            delattr(attempt, '_require_active_resources')
    audit_log(actor=actor or attempt.intent.operator, action='payment_attempt.status_changed', obj=attempt,
              company=attempt.intent.company, branch=attempt.intent.branch,
              before={'status': previous}, after={'status': status}, metadata={'intent_id': str(attempt.intent_id)})
    return attempt


_RESULT_INTENT_STATUS = {
    PaymentAttemptStatus.APPROVED: PaymentIntentStatus.APPROVED,
    PaymentAttemptStatus.DECLINED: PaymentIntentStatus.DECLINED,
    PaymentAttemptStatus.CANCELLED: PaymentIntentStatus.CANCELLED,
    PaymentAttemptStatus.ERROR: PaymentIntentStatus.ERROR,
    PaymentAttemptStatus.UNKNOWN: PaymentIntentStatus.UNKNOWN,
}


def resolve_payment_attempt(*, attempt, status, actor=None, response_metadata=None, result_data=None):
    if status not in _RESULT_INTENT_STATUS:
        raise PaymentIntegrationConflict('invalid_attempt_result', 'Informe um resultado final válido da tentativa.')
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().select_related('intent').get(pk=attempt.pk)
        intent = PaymentIntent.objects.select_for_update().get(pk=attempt.intent_id)
        if attempt.status not in {PaymentAttemptStatus.PROCESSING, PaymentAttemptStatus.UNKNOWN}:
            raise PaymentIntegrationConflict(
                'attempt_not_processing', 'A tentativa deve estar processando ou desconhecida para ser resolvida.',
            )
        if status not in _ATTEMPT_TRANSITIONS[attempt.status]:
            raise PaymentIntegrationConflict(
                'invalid_attempt_transition', f'Transição inválida: {attempt.status} para {status}.',
            )
        expected_intent_status = (
            PaymentIntentStatus.UNKNOWN
            if attempt.status == PaymentAttemptStatus.UNKNOWN
            else PaymentIntentStatus.PROCESSING
        )
        if intent.status != expected_intent_status:
            raise PaymentIntegrationConflict(
                'intent_attempt_state_conflict', 'O intent não está no estado compatível com a tentativa.',
            )
        previous_attempt = attempt.status
        previous_intent = intent.status
        result_fields = _apply_attempt_result_data(attempt, result_data)
        if response_metadata is not None:
            attempt.response_metadata = response_metadata
            result_fields = (*result_fields, 'response_metadata')
        attempt.completed_at = timezone.now()
        _save_attempt_status(attempt, status, result_fields)
        intent_status = _RESULT_INTENT_STATUS[status]
        if intent_status == PaymentIntentStatus.APPROVED:
            intent.approved_at = timezone.now()
        elif intent_status == PaymentIntentStatus.CANCELLED:
            intent.cancelled_at = timezone.now()
        _save_intent_status(intent, intent_status)
    audit_log(actor=actor or intent.operator, action='payment_attempt.status_changed', obj=attempt,
              company=intent.company, branch=intent.branch,
              before={'status': previous_attempt}, after={'status': status},
              metadata={'intent_id': str(intent.pk)})
    audit_log(actor=actor or intent.operator, action='payment_intent.status_changed', obj=intent,
              company=intent.company, branch=intent.branch,
              before={'status': previous_intent}, after={'status': intent.status})
    return attempt, intent
