import hashlib
import json
import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.base.audit import audit_log

from .models import (
    PAYMENT_ATTEMPT_RESULT_FIELDS, PaymentAttempt, PaymentAttemptStatus, PaymentIntent,
    PaymentIntentOriginType, PaymentIntentStatus, PaymentProviderConnectionEnvironment,
    ProviderReversalOperation,
    ProviderReversalStatus,
)


class PaymentIntegrationConflict(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


_UNSET = object()
logger = logging.getLogger('payment_integrations')

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
                           idempotency_key, application_context=None, _quick_sale_bridge=False):
    if origin_type == PaymentIntentOriginType.QUICK_SALE and not _quick_sale_bridge:
        raise PaymentIntegrationConflict(
            'quick_sale_bridge_required',
            'PaymentIntent de venda rápida deve ser criado pela ponte dedicada.',
        )
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


def _save_intent_status(intent, status, *, validate_terminal_pos_binding=False):
    intent.status = status
    intent._allow_status_transition = True
    intent._validate_terminal_pos_binding = validate_terminal_pos_binding
    try:
        intent.save(update_fields=(
            'status', 'approved_at', 'applied_at', 'cancelled_at', 'updated_at',
        ))
    finally:
        delattr(intent, '_allow_status_transition')
        delattr(intent, '_validate_terminal_pos_binding')


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
    identity_fields = {
        'provider_transaction_id', 'provider_operation_key', 'provider_order_id', 'provider_reference',
        'authorization_code', 'nsu',
    }
    for field in identity_fields & set(result_data):
        current = getattr(attempt, field)
        value = result_data[field]
        if current not in ('', None) and current != value:
            raise PaymentIntegrationConflict(
                'provider_identity_conflict',
                f'O identificador de provedor {field} não pode ser alterado.',
            )
    changed_fields = []
    for field, value in result_data.items():
        if getattr(attempt, field) != value:
            setattr(attempt, field, value)
            changed_fields.append(field)
    return tuple(changed_fields)


def _is_cielo_sandbox(attempt):
    connection = attempt.provider_connection
    return (
        connection.provider.code == 'cielo'
        and connection.environment == PaymentProviderConnectionEnvironment.SANDBOX
    )


def _provider_operation_key(attempt, result_data):
    """Keep provider values intact while deriving the database deduplication key."""
    transaction_id = str((result_data or {}).get('provider_transaction_id') or '')
    if not transaction_id:
        return ''
    if not _is_cielo_sandbox(attempt):
        return transaction_id
    order_id = str((result_data or {}).get('provider_order_id') or '')
    reference = str((result_data or {}).get('provider_reference') or '')
    if not order_id or not reference:
        # Missing Cielo correlation remains protected by the strict transaction ID key.
        return transaction_id
    return _fingerprint({
        'provider_connection_id': str(attempt.provider_connection_id),
        'provider_order_id': order_id,
        'provider_reference': reference,
        'provider_transaction_id': transaction_id,
    })


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
        # The intent terminal is historical configuration. The Attempt below
        # validates the terminal actually selected for this retry or fallback.
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
        if status == PaymentIntentStatus.CANCELLED:
            attempts = list(intent.attempts.select_for_update().order_by('-attempt_number'))
            if any(attempt.status in {
                PaymentAttemptStatus.PROCESSING,
                PaymentAttemptStatus.UNKNOWN,
                PaymentAttemptStatus.APPROVED,
            } for attempt in attempts):
                raise PaymentIntegrationConflict(
                    'intent_cancellation_attempt_conflict',
                    'O intent não pode ser cancelado com tentativa em processamento, desconhecida ou aprovada.',
                )
            expected_attempt_status = {
                PaymentIntentStatus.DECLINED: PaymentAttemptStatus.DECLINED,
                PaymentIntentStatus.ERROR: PaymentAttemptStatus.ERROR,
            }.get(intent.status)
            if expected_attempt_status and (
                not attempts or attempts[0].status != expected_attempt_status
            ):
                raise PaymentIntegrationConflict(
                    'intent_cancellation_latest_attempt_conflict',
                    'O último resultado da tentativa deve corresponder ao estado do intent.',
                )
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
    result_data = dict(result_data or {})
    transaction_id = result_data.get('provider_transaction_id')
    if transaction_id:
        result_data['provider_operation_key'] = _provider_operation_key(attempt, result_data)
    identity_conflict = None
    try:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.select_for_update().select_related('intent').get(pk=attempt.pk)
            intent = PaymentIntent.objects.select_for_update().get(pk=attempt.intent_id)
            if attempt.status in {
                PaymentAttemptStatus.APPROVED,
                PaymentAttemptStatus.DECLINED,
                PaymentAttemptStatus.CANCELLED,
                PaymentAttemptStatus.ERROR,
            }:
                if status != attempt.status:
                    raise PaymentIntegrationConflict(
                        'attempt_result_conflict',
                        'A tentativa já possui um resultado final diferente.',
                    )
                result_fields = _apply_attempt_result_data(attempt, result_data)
                if response_metadata is not None and response_metadata != attempt.response_metadata:
                    attempt.response_metadata = response_metadata
                    result_fields = (*result_fields, 'response_metadata')
                if result_fields:
                    attempt._allow_result_update = True
                    try:
                        attempt.save(update_fields=tuple(dict.fromkeys((*result_fields, 'updated_at'))))
                    finally:
                        delattr(attempt, '_allow_result_update')
                return attempt, intent
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
            conflicting_attempt = None
            if transaction_id:
                conflicting_attempt = PaymentAttempt.objects.select_for_update().select_related('intent').filter(
                    provider_connection=attempt.provider_connection,
                    provider_transaction_id=transaction_id,
                ).exclude(pk=attempt.pk).first()
            sandbox_transaction_reuse = False
            if conflicting_attempt:
                from apps.pos.models import QuickSalePayment

                callback_order_id = str((result_data or {}).get('provider_order_id') or '')
                callback_reference = str((result_data or {}).get('provider_reference') or '')
                expected_reference = f'CORE-{attempt.pk}'
                identity_conflict = {
                    'current_attempt_id': str(attempt.pk),
                    'current_intent_id': str(intent.pk),
                    'current_origin_id': intent.origin_id,
                    'current_attempt_number': attempt.attempt_number,
                    'current_status': attempt.status,
                    'current_amount': str(attempt.amount),
                    'current_reference_present': bool(callback_reference),
                    'current_reference_matches': callback_reference == expected_reference,
                    'conflicting_attempt_id': str(conflicting_attempt.pk),
                    'conflicting_intent_id': str(conflicting_attempt.intent_id),
                    'conflicting_origin_id': conflicting_attempt.intent.origin_id,
                    'conflicting_attempt_number': conflicting_attempt.attempt_number,
                    'same_intent': attempt.intent_id == conflicting_attempt.intent_id,
                    'same_origin': (
                        intent.origin_type == conflicting_attempt.intent.origin_type
                        and intent.origin_id == conflicting_attempt.intent.origin_id
                    ),
                    'same_order': bool(callback_order_id) and callback_order_id == conflicting_attempt.provider_order_id,
                    'same_reference': bool(callback_reference) and callback_reference == conflicting_attempt.provider_reference,
                    'same_amount': attempt.amount == conflicting_attempt.amount,
                    'conflicting_attempt_status': conflicting_attempt.status,
                    'conflicting_intent_status': conflicting_attempt.intent.status,
                    'conflicting_payment_exists': QuickSalePayment.objects.filter(
                        source_payment_attempt=conflicting_attempt,
                    ).exists(),
                    'conflicting_intent_applied': (
                        conflicting_attempt.intent.status == PaymentIntentStatus.APPLIED
                    ),
                    'transaction_fingerprint': _fingerprint({'transaction_id': transaction_id})[:12],
                }
                sandbox_transaction_reuse = (
                    _is_cielo_sandbox(attempt)
                    and identity_conflict['current_reference_matches']
                    and not identity_conflict['same_order']
                    and not identity_conflict['same_reference']
                )
            if conflicting_attempt and not sandbox_transaction_reuse:
                # The external evidence belongs to another attempt. Do not persist its
                # identifiers on this attempt or let the operator charge blindly again.
                attempt.provider_transaction_id = ''
                conflict_result = {
                    'provider_status': 'unknown',
                    'provider_message': (
                        'A Cielo retornou a transação, mas o CORE encontrou um conflito com um '
                        'registro anterior. Não realize uma nova cobrança até a verificação ser concluída.'
                    ),
                }
                result_fields = _apply_attempt_result_data(attempt, conflict_result)
                attempt.response_metadata = {
                    **(response_metadata or {}),
                    'provider_callback_identity_conflict': True,
                }
                result_fields = (*result_fields, 'response_metadata')
                attempt.completed_at = timezone.now()
                _save_attempt_status(attempt, PaymentAttemptStatus.UNKNOWN, result_fields)
                _save_intent_status(
                    intent, PaymentIntentStatus.UNKNOWN, validate_terminal_pos_binding=False,
                )
            else:
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
                _save_intent_status(intent, intent_status, validate_terminal_pos_binding=False)
    except IntegrityError as error:
        if transaction_id:
            raise PaymentIntegrationConflict(
                'provider_transaction_conflict',
                'O identificador da transação já pertence a outra tentativa desta conexão.',
            ) from error
        raise
    audit_log(actor=actor or intent.operator, action='payment_attempt.status_changed', obj=attempt,
              company=intent.company, branch=intent.branch,
              before={'status': previous_attempt}, after={'status': attempt.status},
              metadata={'intent_id': str(intent.pk)})
    audit_log(actor=actor or intent.operator, action='payment_intent.status_changed', obj=intent,
              company=intent.company, branch=intent.branch,
              before={'status': previous_intent}, after={'status': intent.status})
    if identity_conflict:
        log = logger.info if sandbox_transaction_reuse else logger.warning
        log(
            '%s current_attempt_id=%s current_intent_id=%s '
            'current_origin_id=%s current_attempt_number=%s current_status=%s current_amount=%s '
            'current_reference_present=%s current_reference_matches=%s '
            'conflicting_attempt_id=%s conflicting_intent_id=%s conflicting_origin_id=%s '
            'conflicting_attempt_number=%s '
            'same_intent=%s same_origin=%s same_order=%s same_reference=%s same_amount=%s '
            'conflicting_attempt_status=%s conflicting_intent_status=%s conflicting_amount=%s '
            'conflicting_payment_exists=%s conflicting_intent_applied=%s '
            'transaction_fingerprint=%s',
            'CIELO_SANDBOX_TRANSACTION_REUSED' if sandbox_transaction_reuse else 'CIELO_TRANSACTION_CONFLICT',
            identity_conflict['current_attempt_id'], identity_conflict['current_intent_id'],
            identity_conflict['current_origin_id'], identity_conflict['current_attempt_number'],
            identity_conflict['current_status'], identity_conflict['current_amount'],
            identity_conflict['current_reference_present'], identity_conflict['current_reference_matches'],
            identity_conflict['conflicting_attempt_id'], identity_conflict['conflicting_intent_id'],
            identity_conflict['conflicting_origin_id'], identity_conflict['conflicting_attempt_number'],
            identity_conflict['same_intent'], identity_conflict['same_origin'],
            identity_conflict['same_order'], identity_conflict['same_reference'],
            identity_conflict['same_amount'], identity_conflict['conflicting_attempt_status'],
            identity_conflict['conflicting_intent_status'], str(conflicting_attempt.amount),
            identity_conflict['conflicting_payment_exists'], identity_conflict['conflicting_intent_applied'],
            identity_conflict['transaction_fingerprint'],
        )
    return attempt, intent


_REVERSAL_RESULT_STATUSES = {
    ProviderReversalStatus.APPROVED,
    ProviderReversalStatus.CANCELLED,
    ProviderReversalStatus.ERROR,
    ProviderReversalStatus.UNKNOWN,
}


def create_provider_reversal(*, company, branch, pos_device, operator, authorized_by,
                             origin_type, origin_id, source_attempt, reason, idempotency_key):
    """Create the external reversal operation before any local ledger mutation."""
    fingerprint = _fingerprint({
        'branch': branch.pk, 'pos_device': str(pos_device.pk), 'operator': operator.pk,
        'authorized_by': authorized_by.pk if authorized_by else None,
        'origin_type': origin_type, 'origin_id': str(origin_id),
        'source_attempt': str(source_attempt.pk), 'reason': (reason or '').strip(),
    })
    with transaction.atomic():
        existing = ProviderReversalOperation.objects.select_for_update().filter(
            company=company, idempotency_key=idempotency_key,
        ).first()
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise PaymentIntegrationConflict(
                    'idempotency_key_conflict',
                    'A chave de idempotência já foi usada com outros dados.',
                )
            return existing, True
        source_attempt = PaymentAttempt.objects.select_for_update().select_related(
            'intent', 'provider_connection__provider',
        ).get(pk=source_attempt.pk)
        if source_attempt.status != PaymentAttemptStatus.APPROVED:
            raise PaymentIntegrationConflict(
                'provider_reversal_source_unapproved',
                'O pagamento original não possui aprovação comprovada no provedor.',
            )
        blocking = ProviderReversalOperation.objects.select_for_update().filter(
            source_attempt=source_attempt,
            status__in=(
                ProviderReversalStatus.CREATED, ProviderReversalStatus.PROCESSING,
                ProviderReversalStatus.UNKNOWN, ProviderReversalStatus.APPROVED,
            ),
        ).first()
        if blocking:
            raise PaymentIntegrationConflict(
                'provider_reversal_in_progress',
                'Já existe uma reversão externa pendente para este pagamento.',
            )
        operation = ProviderReversalOperation(
            company=company, branch=branch, pos_device=pos_device, operator=operator,
            authorized_by=authorized_by, origin_type=origin_type, origin_id=str(origin_id),
            source_attempt=source_attempt, provider_connection=source_attempt.provider_connection,
            terminal=source_attempt.terminal, amount=source_attempt.amount,
            reason=(reason or '').strip(), idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
        )
        operation.save()
        operation.status = ProviderReversalStatus.PROCESSING
        operation.started_at = timezone.now()
        operation._allow_status_transition = True
        operation._allow_result_update = True
        try:
            operation.save(update_fields=('status', 'started_at', 'updated_at'))
        finally:
            delattr(operation, '_allow_status_transition')
            delattr(operation, '_allow_result_update')
    audit_log(
        actor=operator, action='provider_reversal.started', obj=operation,
        company=company, branch=branch,
        after={
            'operation_id': str(operation.pk), 'source_attempt_id': str(source_attempt.pk),
            'status': operation.status,
        },
        metadata={'idempotency_key': str(idempotency_key)},
    )
    return operation, False


def resolve_provider_reversal(*, operation, status, actor=None, response_metadata=None,
                              result_data=None):
    if status not in _REVERSAL_RESULT_STATUSES:
        raise PaymentIntegrationConflict('invalid_reversal_result', 'Informe um resultado final válido da reversão.')
    result_data = result_data or {}
    allowed_fields = {'provider_status', 'provider_status_code', 'provider_message'}
    if set(result_data) - allowed_fields:
        raise PaymentIntegrationConflict('invalid_reversal_result_data', 'Resultado da reversão possui campos inválidos.')
    with transaction.atomic():
        operation = ProviderReversalOperation.objects.select_for_update().get(pk=operation.pk)
        if operation.status in _REVERSAL_RESULT_STATUSES | {ProviderReversalStatus.APPLIED}:
            if status != operation.status and not (
                operation.status == ProviderReversalStatus.APPLIED and status == ProviderReversalStatus.APPROVED
            ):
                raise PaymentIntegrationConflict(
                    'reversal_result_conflict',
                    'A reversão já possui um resultado final diferente.',
                )
            return operation, True
        if operation.status not in {ProviderReversalStatus.PROCESSING, ProviderReversalStatus.UNKNOWN}:
            raise PaymentIntegrationConflict('reversal_not_processing', 'A reversão não está pronta para receber resultado.')
        previous = operation.status
        operation.status = status
        operation.provider_status = str(result_data.get('provider_status') or '')[:100]
        operation.provider_status_code = str(result_data.get('provider_status_code') or '')[:100]
        operation.provider_message = str(result_data.get('provider_message') or '')[:500]
        operation.response_metadata = response_metadata or {}
        operation.completed_at = timezone.now()
        operation._allow_status_transition = True
        operation._allow_result_update = True
        try:
            operation.save(update_fields=(
                'status', 'provider_status', 'provider_status_code', 'provider_message',
                'response_metadata', 'completed_at', 'updated_at',
            ))
        finally:
            delattr(operation, '_allow_status_transition')
            delattr(operation, '_allow_result_update')
    audit_log(
        actor=actor or operation.operator, action='provider_reversal.resolved', obj=operation,
        company=operation.company, branch=operation.branch,
        before={'status': previous}, after={'status': status},
    )
    return operation, False


def mark_provider_reversal_applied(*, operation, actor=None):
    with transaction.atomic():
        operation = ProviderReversalOperation.objects.select_for_update().get(pk=operation.pk)
        if operation.status == ProviderReversalStatus.APPLIED:
            return operation, True
        if operation.status != ProviderReversalStatus.APPROVED:
            raise PaymentIntegrationConflict(
                'reversal_not_approved',
                'A reversão externa deve estar aprovada antes de aplicação local.',
            )
        operation.status = ProviderReversalStatus.APPLIED
        operation._allow_status_transition = True
        try:
            operation.save(update_fields=('status', 'updated_at'))
        finally:
            delattr(operation, '_allow_status_transition')
    audit_log(
        actor=actor or operation.operator, action='provider_reversal.applied', obj=operation,
        company=operation.company, branch=operation.branch,
        before={'status': ProviderReversalStatus.APPROVED}, after={'status': operation.status},
    )
    return operation, False
