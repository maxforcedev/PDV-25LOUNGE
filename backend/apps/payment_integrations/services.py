import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.base.audit import audit_log

from .models import (
    PaymentAttempt, PaymentAttemptStatus, PaymentIntent, PaymentIntentStatus,
)


class PaymentIntegrationConflict(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str,
    ).encode()).hexdigest()


def create_payment_intent(*, company, branch, pos_device, operator, origin_type, origin_id,
                          payment_method, amount, provider_connection, terminal,
                          idempotency_key):
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
            intent = PaymentIntent(
                company=company, branch=branch, pos_device=pos_device, operator=operator,
                origin_type=origin_type, origin_id=str(origin_id), payment_method=payment_method,
                amount=amount, provider_connection=provider_connection, terminal=terminal,
                idempotency_key=idempotency_key, request_fingerprint=fingerprint,
            )
            intent.full_clean()
            intent.save()
    except IntegrityError:
        with transaction.atomic():
            existing = PaymentIntent.objects.select_for_update().get(
                company=company, idempotency_key=idempotency_key,
            )
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


def create_payment_attempt(*, intent, provider_connection=None, terminal=None, amount=None,
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
            PaymentIntentStatus.CANCELLED, PaymentIntentStatus.ERROR,
        }:
            raise PaymentIntegrationConflict(
                'intent_not_ready', 'O intent deve estar pronto ou concluído sem sucesso para nova tentativa.',
            )
        previous_status = intent.status
        intent.status = PaymentIntentStatus.PROCESSING
        intent.save(update_fields=('status', 'updated_at'))
        latest = intent.attempts.order_by('-attempt_number').values_list('attempt_number', flat=True).first()
        attempt = PaymentAttempt(
            intent=intent,
            provider_connection=provider_connection or intent.provider_connection,
            terminal=terminal if terminal is not None else intent.terminal,
            attempt_number=(latest or 0) + 1,
            amount=amount if amount is not None else intent.amount,
            request_metadata=request_metadata or {},
        )
        attempt.full_clean()
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
    PaymentIntentStatus.PROCESSING: {
        PaymentIntentStatus.APPROVED, PaymentIntentStatus.DECLINED, PaymentIntentStatus.CANCELLED,
        PaymentIntentStatus.ERROR, PaymentIntentStatus.UNKNOWN,
    },
    PaymentIntentStatus.DECLINED: set(),
    PaymentIntentStatus.CANCELLED: set(),
    PaymentIntentStatus.ERROR: set(),
    PaymentIntentStatus.UNKNOWN: {
        PaymentIntentStatus.APPROVED, PaymentIntentStatus.DECLINED,
        PaymentIntentStatus.CANCELLED, PaymentIntentStatus.ERROR,
    },
    PaymentIntentStatus.APPROVED: {PaymentIntentStatus.APPLIED},
    PaymentIntentStatus.APPLIED: {PaymentIntentStatus.REVERSED},
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
        intent.status = status
        now = timezone.now()
        if status == PaymentIntentStatus.APPROVED:
            intent.approved_at = now
        elif status == PaymentIntentStatus.APPLIED:
            intent.applied_at = now
        elif status == PaymentIntentStatus.CANCELLED:
            intent.cancelled_at = now
        intent.save(update_fields=('status', 'approved_at', 'applied_at', 'cancelled_at', 'updated_at'))
    audit_log(actor=actor or intent.operator, action='payment_intent.status_changed', obj=intent,
              company=intent.company, branch=intent.branch,
              before={'status': previous}, after={'status': status})
    return intent


def transition_payment_attempt(*, attempt, status, actor=None, response_metadata=None):
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().select_related('intent').get(pk=attempt.pk)
        if status not in _ATTEMPT_TRANSITIONS[attempt.status]:
            raise PaymentIntegrationConflict(
                'invalid_attempt_transition', f'Transição inválida: {attempt.status} para {status}.',
            )
        if response_metadata is not None:
            attempt.response_metadata = response_metadata
        attempt.full_clean()
        previous = attempt.status
        attempt.status = status
        if status == PaymentAttemptStatus.PROCESSING and not attempt.started_at:
            attempt.started_at = timezone.now()
        if status in {
            PaymentAttemptStatus.APPROVED, PaymentAttemptStatus.DECLINED, PaymentAttemptStatus.CANCELLED,
            PaymentAttemptStatus.ERROR, PaymentAttemptStatus.UNKNOWN,
        }:
            attempt.completed_at = timezone.now()
        attempt.save(update_fields=('status', 'response_metadata', 'started_at', 'completed_at', 'updated_at'))
    audit_log(actor=actor or attempt.intent.operator, action='payment_attempt.status_changed', obj=attempt,
              company=attempt.intent.company, branch=attempt.intent.branch,
              before={'status': previous}, after={'status': status}, metadata={'intent_id': str(attempt.intent_id)})
    return attempt
