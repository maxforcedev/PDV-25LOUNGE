import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.base.audit import audit_log
from apps.cash.models import CashSession, CashSessionStatus
from apps.companies.models import Customer, Status
from apps.inventory.reservations import (
    StockReservationConflict, acquire_checkout_reservation,
    consume_checkout_reservation, release_checkout_reservation,
    restore_checkout_reservation_expiry, validate_checkout_reservation,
)
from apps.products.models import SalesChannel
from apps.pos.models import (
    QuickSaleCheckout, QuickSaleCheckoutItem, QuickSalePayment,
    QuickSalePaymentAllocation, QuickSaleCheckoutStatus, QuickSalePaymentSourceType,
    QuickSalePaymentStatus,
)

from .models import OperationType, PaymentMethod, PaymentMethodCode
from .services import (
    CENT, _allocate_money, _discount_approver, _service_fee_waiver,
    calculate_preview, finalize_sale, strict_decimal,
)


class QuickCheckoutConflict(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


_BLOCKING_PAYMENT_INTENT_STATUSES = (
    'created', 'ready', 'processing', 'declined', 'error', 'unknown', 'approved',
)
_QUICK_UNSET = object()


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str,
    ).encode()).hexdigest()


def _preview_snapshot(preview):
    # Serializer-compatible JSON also prevents Decimal values from leaking into JSONField.
    return json.loads(json.dumps(preview, default=str))


def _financial_snapshot(preview):
    return {
        'items': preview['items'],
        'financials': {
            key: preview[key] for key in (
                'subtotal', 'promotion_discount_total', 'item_discount_total', 'discount',
                'service_fee_rate', 'service_fee_amount', 'commission_rate',
                'commission_amount', 'total',
            )
        },
        'discount_intent': preview['discount_intent'],
    }


def _blocking_payment_intent(checkout, *, lock=False, exclude_id=None):
    from apps.payment_integrations.models import PaymentIntent, PaymentIntentOriginType

    intents = PaymentIntent.objects.filter(
        origin_type=PaymentIntentOriginType.QUICK_SALE,
        origin_id=str(checkout.pk),
        status__in=_BLOCKING_PAYMENT_INTENT_STATUSES,
    )
    if exclude_id:
        intents = intents.exclude(pk=exclude_id)
    if lock:
        intents = intents.select_for_update()
    return intents.first()


def _ensure_checkout_without_blocking_intent(checkout, *, exclude_id=None):
    if _blocking_payment_intent(checkout, lock=True, exclude_id=exclude_id):
        raise QuickCheckoutConflict(
            'payment_intent_in_progress',
            'O checkout possui uma cobrança externa pendente ou reutilizável.',
        )


def _frozen_application_context(checkout, *, mode, amount, allocations, remaining):
    if mode == 'value':
        resolved_amount = strict_decimal(amount, field='amount', decimal_places=2, max_digits=14)
        resolved_allocations = []
    elif mode == 'remaining':
        resolved_amount = remaining
        resolved_allocations = []
    elif mode == 'items':
        resolved_amount, resolved_allocations = _allocation_amount(checkout, allocations)
    else:
        raise ValidationError({'mode': 'Modo de pagamento inválido.'})
    if resolved_amount <= 0 or resolved_amount > remaining:
        raise QuickCheckoutConflict('payment_exceeds_remaining', 'O pagamento deve estar dentro do saldo restante.')
    return {
        'mode': mode,
        'amount': f'{resolved_amount:.2f}',
        'allocations': [
            {
                'item': allocation['item'].pk,
                'allocated_quantity': format(allocation['allocated_quantity'], 'f'),
                'amount': f'{allocation["amount"]:.2f}',
            }
            for allocation in sorted(resolved_allocations, key=lambda row: row['item'].pk)
        ],
    }, resolved_amount


def _validate_quick_sale_intent_context(intent, checkout):
    from apps.payment_integrations.models import PaymentIntentOriginType

    context = intent.application_context or {}
    if (
        intent.origin_type != PaymentIntentOriginType.QUICK_SALE
        or intent.origin_id != str(checkout.pk)
        or intent.company_id != checkout.company_id
        or intent.branch_id != checkout.branch_id
        or intent.pos_device_id != checkout.pos_device_id
        or str(context.get('amount')) != f'{intent.amount:.2f}'
    ):
        raise QuickCheckoutConflict('payment_intent_context_invalid', 'O contexto congelado do intent é inválido.')
    return context


def _validated_application_context_allocations(intent, checkout, context):
    mode = context.get('mode')
    allocations = context.get('allocations')
    if mode not in {'value', 'remaining', 'items'} or not isinstance(allocations, list):
        raise QuickCheckoutConflict('payment_intent_context_invalid', 'O modo ou as alocações do intent são inválidos.')
    if mode in {'value', 'remaining'}:
        if allocations:
            raise QuickCheckoutConflict('payment_intent_context_invalid', 'Este modo não aceita alocações por item.')
        return []
    item_ids = [row.get('item') if isinstance(row, dict) else None for row in allocations]
    if not item_ids or len(item_ids) != len(set(item_ids)):
        raise QuickCheckoutConflict('payment_intent_context_invalid', 'As alocações do intent são inválidas.')
    try:
        expected_amount, expected_allocations = _allocation_amount(
            checkout,
            [
                {
                    'item': row['item'],
                    'allocated_quantity': strict_decimal(
                        row.get('allocated_quantity'), field='application_context.allocated_quantity',
                        decimal_places=3, max_digits=14,
                    ),
                }
                for row in allocations
            ],
        )
    except (KeyError, TypeError, ValueError, ValidationError, QuickCheckoutConflict) as error:
        raise QuickCheckoutConflict('payment_intent_context_invalid', 'As alocações congeladas são inválidas.') from error
    if expected_amount != intent.amount:
        raise QuickCheckoutConflict('payment_intent_context_invalid', 'As alocações não correspondem ao valor do intent.')
    by_item = {row['item'].pk: row for row in expected_allocations}
    for row in allocations:
        expected = by_item.get(row['item'])
        if not expected:
            raise QuickCheckoutConflict('payment_intent_context_invalid', 'A alocação não pertence ao checkout.')
        try:
            allocated_quantity = strict_decimal(
                row.get('allocated_quantity'), field='application_context.allocated_quantity',
                decimal_places=3, max_digits=14,
            )
            amount = strict_decimal(
                row.get('amount'), field='application_context.amount', decimal_places=2, max_digits=14,
            )
        except ValidationError as error:
            raise QuickCheckoutConflict('payment_intent_context_invalid', 'A alocação possui valores inválidos.') from error
        if (
            allocated_quantity <= 0 or amount <= 0
            or allocated_quantity != expected['allocated_quantity']
            or amount != expected['amount']
        ):
            raise QuickCheckoutConflict('payment_intent_context_invalid', 'A alocação não corresponde ao contexto congelado.')
    return expected_allocations


@transaction.atomic
def create_quick_checkout(*, branch, pos_device, user, permissions, raw_items,
                          discount, service_fee_waived, customer_id, idempotency_key,
                          discount_authorization=None, item_discount_authorization=None,
                          service_fee_authorization=None, audit_metadata=None):
    payload = {
        'items': raw_items, 'discount': discount,
        'service_fee_waived': service_fee_waived, 'customer': customer_id,
    }
    fingerprint = _fingerprint(payload)
    existing = QuickSaleCheckout.objects.select_for_update().filter(
        pos_device=pos_device, operator=user, creation_idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.creation_request_fingerprint != fingerprint:
            raise QuickCheckoutConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
        return existing, True
    if pos_device.branch_id != branch.pk:
        raise ValidationError({'pos_device': 'O dispositivo deve pertencer à filial da venda.'})
    # Import locally because POS views import this checkout domain service.
    from apps.pos.services import current_pos_cash_session

    session = current_pos_cash_session(pos_device, for_update=True)
    customer = None
    if customer_id is not None:
        customer = Customer.objects.select_for_update().filter(
            pk=customer_id, company=branch.company, status=Status.ACTIVE,
        ).first()
        if not customer:
            raise ValidationError({'customer': 'Cliente inválido, inativo ou fora da empresa.'})
    preview = calculate_preview(
        company=branch.company, operation_type=OperationType.SALE, raw_items=raw_items,
        discount=discount, charged_amount=None, beneficiary_user=None, branch=branch,
        channel=SalesChannel.COUNTER, service_fee_waived=service_fee_waived,
    )
    discount_approver = _discount_approver(
        branch, user, preview['discount'], discount_authorization,
        permission_code='sales.apply_discount', authorization_field='discount_authorization',
        allow_pos_only=True, pos_device=pos_device, permission_codes=permissions, device_validated=True,
    )
    item_discount_approver = _discount_approver(
        branch, user, preview['item_discount_total'], item_discount_authorization,
        permission_code='sales.apply_item_discount', authorization_field='item_discount_authorization',
        allow_pos_only=True, pos_device=pos_device, permission_codes=permissions, device_validated=True,
    )
    fee_approver = _service_fee_waiver(
        branch, user, bool(service_fee_waived), service_fee_authorization,
        allow_pos_only=True, pos_device=pos_device, permission_codes=permissions, device_validated=True,
    )
    try:
        with transaction.atomic():
            checkout = QuickSaleCheckout.objects.create(
                company=branch.company, branch=branch, pos_device=pos_device, cash_session=session,
                operator=user, customer=customer,
                financial_snapshot=_preview_snapshot(_financial_snapshot(preview)),
                discount_intent=_preview_snapshot(preview['discount_intent']),
                service_fee_waived=bool(service_fee_waived),
                discount_approved_by=discount_approver, item_discount_approved_by=item_discount_approver,
                service_fee_waived_by=fee_approver, creation_idempotency_key=idempotency_key,
                creation_request_fingerprint=fingerprint,
            )
    except IntegrityError:
        existing = QuickSaleCheckout.objects.select_for_update().get(
            pos_device=pos_device, operator=user, creation_idempotency_key=idempotency_key,
        )
        if existing.creation_request_fingerprint != fingerprint:
            raise QuickCheckoutConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
        return existing, True
    for index, item in enumerate(raw_items):
        QuickSaleCheckoutItem.objects.create(
            checkout=checkout, client_item_id=item['client_item_id'], product_id=item['product'],
            quantity=item['quantity'], snapshot={'raw': _preview_snapshot(item), 'preview': _preview_snapshot(preview['items'][index])},
        )
    try:
        acquire_checkout_reservation(checkout)
    except StockReservationConflict as error:
        raise QuickCheckoutConflict('stock_unavailable', error.message) from error
    audit_log(actor=user, action='quick_sale_checkout.create', obj=checkout,
              company=branch.company, branch=branch,
              after={'checkout_id': str(checkout.pk), 'total': str(preview['total'])},
              metadata={**(audit_metadata or {}), 'idempotency_key': str(idempotency_key)})
    return checkout, False


@transaction.atomic
def update_quick_checkout(*, checkout, pos_device, user, permissions, raw_items, discount,
                           service_fee_waived, customer_id,
                          discount_authorization=None, item_discount_authorization=None,
                          service_fee_authorization=None, audit_metadata=None):
    _current_session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    _ensure_checkout_without_blocking_intent(checkout)
    paid, _remaining = checkout_balance(checkout, lock=True)
    if checkout.status != QuickSaleCheckoutStatus.OPEN or paid:
        raise QuickCheckoutConflict('checkout_not_editable', 'Itens não podem mudar após o primeiro pagamento.')
    if checkout.pos_device_id != pos_device.pk or pos_device.branch_id != checkout.branch_id:
        raise ValidationError({'pos_device': 'O dispositivo deve pertencer ao checkout.'})
    # Import locally because POS views import this checkout domain service.
    from apps.pos.services import current_pos_cash_session

    session = current_pos_cash_session(pos_device, for_update=True)
    customer = None
    if customer_id is not None:
        customer = Customer.objects.select_for_update().filter(
            pk=customer_id, company=checkout.company, status=Status.ACTIVE,
        ).first()
        if not customer:
            raise ValidationError({'customer': 'Cliente inválido, inativo ou fora da empresa.'})
    preview = calculate_preview(
        company=checkout.company, operation_type=OperationType.SALE, raw_items=raw_items,
        discount=discount, charged_amount=None, beneficiary_user=None, branch=checkout.branch,
        channel=SalesChannel.COUNTER, service_fee_waived=service_fee_waived,
    )
    unchanged_items = _fingerprint(raw_items) == _fingerprint([
        item.snapshot['raw'] for item in checkout.items.order_by('id')
    ])
    if not unchanged_items and QuickSalePayment.objects.filter(checkout=checkout).exists():
        raise QuickCheckoutConflict(
            'checkout_requires_new_instance',
            'Um checkout com histórico de pagamentos não pode receber outros itens.',
        )
    if checkout.discount_intent != preview['discount_intent'] or not checkout.discount_approved_by_id:
        checkout.discount_approved_by = _discount_approver(
            checkout.branch, user, preview['discount'], discount_authorization,
            permission_code='sales.apply_discount', authorization_field='discount_authorization',
            allow_pos_only=True, pos_device=pos_device, permission_codes=permissions,
            device_validated=True,
        )
    if not unchanged_items or not checkout.item_discount_approved_by_id:
        checkout.item_discount_approved_by = _discount_approver(
            checkout.branch, user, preview['item_discount_total'], item_discount_authorization,
            permission_code='sales.apply_item_discount', authorization_field='item_discount_authorization',
            allow_pos_only=True, pos_device=pos_device, permission_codes=permissions,
            device_validated=True,
        )
    if checkout.service_fee_waived != bool(service_fee_waived) or not checkout.service_fee_waived_by_id:
        checkout.service_fee_waived_by = _service_fee_waiver(
            checkout.branch, user, bool(service_fee_waived), service_fee_authorization,
            allow_pos_only=True, pos_device=pos_device, permission_codes=permissions,
            device_validated=True,
        )
    if not unchanged_items:
        QuickSaleCheckoutItem.objects.filter(checkout=checkout).delete()
        for index, item in enumerate(raw_items):
            QuickSaleCheckoutItem.objects.create(
                checkout=checkout, client_item_id=item['client_item_id'], product_id=item['product'],
                quantity=item['quantity'], snapshot={
                    'raw': _preview_snapshot(item), 'preview': _preview_snapshot(preview['items'][index]),
                },
            )
    checkout.customer = customer
    checkout.cash_session = session
    checkout.financial_snapshot = _preview_snapshot(_financial_snapshot(preview))
    checkout.discount_intent = _preview_snapshot(preview['discount_intent'])
    checkout.service_fee_waived = bool(service_fee_waived)
    checkout.save()
    try:
        acquire_checkout_reservation(checkout)
    except StockReservationConflict as error:
        raise QuickCheckoutConflict('stock_unavailable', error.message) from error
    audit_log(actor=user, action='quick_sale_checkout.update', obj=checkout,
              company=checkout.company, branch=checkout.branch,
              after={'checkout_id': str(checkout.pk), 'total': str(preview['total'])},
              metadata=audit_metadata or {})
    return checkout


def checkout_balance(checkout, *, lock=False):
    if lock:
        list(QuickSalePayment.objects.select_for_update().filter(
            checkout=checkout,
        ).order_by('pk').values_list('pk', flat=True))
    paid = QuickSalePayment.objects.filter(
        checkout=checkout, status=QuickSalePaymentStatus.APPLIED, reversal__isnull=True,
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    total = strict_decimal(
        checkout.financial_snapshot['financials']['total'], field='checkout.total',
        decimal_places=2, max_digits=14,
    )
    return paid, total - paid


def checkout_available_quantities(checkout):
    """Return quantities still eligible for item-based payment from the payment ledger."""
    allocated = {
        row['item_id']: row['quantity'] or Decimal('0.000')
        for row in QuickSalePaymentAllocation.objects.filter(
            payment__checkout=checkout,
            payment__status=QuickSalePaymentStatus.APPLIED,
            payment__reversal__isnull=True,
        ).values('item_id').annotate(quantity=Sum('allocated_quantity'))
    }
    return {
        item.pk: item.quantity - allocated.get(item.pk, Decimal('0.000'))
        for item in checkout.items.order_by('id')
    }


def _lock_checkout_session(checkout_id, *, user=None):
    """Lock the drawer before its checkout so closing and tender writes serialize."""
    checkouts = QuickSaleCheckout.objects.filter(pk=checkout_id)
    if user is not None:
        checkouts = checkouts.filter(operator=user)
    session_id = checkouts.values_list(
        'cash_session_id', flat=True,
    ).first()
    if session_id is None:
        if checkouts.exists():
            raise QuickCheckoutConflict('cash_session_missing', 'O checkout não possui sessão de caixa.')
        raise QuickCheckoutConflict('checkout_not_found', 'Checkout não encontrado.')
    sessions = {
        session.pk: session
        for session in CashSession.objects.select_for_update().filter(
            pk=session_id,
        ).order_by('pk')
    }
    if session_id not in sessions:
        raise QuickCheckoutConflict('cash_session_missing', 'A sessão de caixa do checkout não existe.')
    checkout = checkouts.select_for_update(of=('self',)).select_related(
        'branch', 'pos_device', 'company', 'cash_session', 'customer',
        'discount_approved_by', 'item_discount_approved_by',
        'service_fee_waived_by', 'sale',
    ).get(pk=checkout_id)
    if checkout.cash_session_id != session_id:
        raise QuickCheckoutConflict(
            'cash_session_changed', 'A sessão de caixa do checkout foi alterada.',
        )
    return sessions[session_id], checkout, sessions


def _allocation_amount(checkout, allocations, *, lock_items=True, allow_zero_amount=False):
    if not allocations:
        raise ValidationError({'allocations': 'Pagamento por itens exige ao menos uma alocação.'})
    item_ids = [row.get('item') for row in allocations]
    if len(item_ids) != len(set(item_ids)):
        raise ValidationError({'allocations': 'Informe cada item apenas uma vez por pagamento.'})
    items_queryset = QuickSaleCheckoutItem.objects.filter(
        checkout=checkout, pk__in=item_ids,
    )
    if lock_items:
        items_queryset = items_queryset.select_for_update()
    items = {item.pk: item for item in items_queryset}
    if len(items) != len(item_ids):
        raise ValidationError({'allocations': 'Itens devem pertencer ao checkout.'})
    snapshots = checkout.financial_snapshot['items']
    discount_shares = _allocate_money(
        strict_decimal(checkout.financial_snapshot['financials']['discount'], field='checkout.discount', decimal_places=2, max_digits=14),
        [(index, strict_decimal(row['net_subtotal'], field='checkout.items.net_subtotal', decimal_places=2, max_digits=14)) for index, row in enumerate(snapshots)],
    )
    fee_shares = _allocate_money(
        strict_decimal(checkout.financial_snapshot['financials']['service_fee_amount'], field='checkout.service_fee_amount', decimal_places=2, max_digits=14),
        [(index, strict_decimal(row['net_subtotal'], field='checkout.items.net_subtotal', decimal_places=2, max_digits=14) - discount_shares[index]) for index, row in enumerate(snapshots) if row['participates_in_service_fee']],
    )
    ordered_items = list(checkout.items.order_by('id'))
    item_indexes = {item.pk: index for index, item in enumerate(ordered_items)}
    final_amounts = {
        item.pk: strict_decimal(item.snapshot['preview']['net_subtotal'], field='checkout.items.net_subtotal', decimal_places=2, max_digits=14)
        - discount_shares[item_indexes[item.pk]] + fee_shares.get(item_indexes[item.pk], Decimal('0.00'))
        for item in items.values()
    }
    prior = {
        row['item_id']: (row['quantity'] or Decimal('0.000'), row['amount'] or Decimal('0.00'))
        for row in QuickSalePaymentAllocation.objects.filter(
            item_id__in=item_ids, payment__checkout=checkout,
            payment__status=QuickSalePaymentStatus.APPLIED,
            payment__reversal__isnull=True,
        ).values('item_id').annotate(quantity=Sum('allocated_quantity'), amount=Sum('amount'))
    }
    total = Decimal('0.00')
    resolved = []
    for row in allocations:
        item = items[row['item']]
        quantity = strict_decimal(row.get('allocated_quantity'), field='allocated_quantity', decimal_places=3, max_digits=14)
        allocated_quantity, allocated_amount = prior.get(item.pk, (Decimal('0.000'), Decimal('0.00')))
        if allocated_quantity + quantity > item.quantity:
            raise QuickCheckoutConflict('item_overallocated', 'A quantidade alocada excede a quantidade disponível do item.')
        cumulative = ((allocated_quantity + quantity) * final_amounts[item.pk] / item.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        amount = cumulative - allocated_amount
        if amount <= 0 and not allow_zero_amount:
            raise QuickCheckoutConflict('item_allocation_mismatch', 'A alocação não gera valor a pagar.')
        resolved.append({'item': item, 'allocated_quantity': quantity, 'amount': amount})
        total += amount
    return total, resolved


def checkout_can_pay_by_items(checkout, remaining):
    """Return whether an official item allocation can fit in the current balance."""
    if remaining <= Decimal('0.00'):
        return False
    available_quantities = checkout_available_quantities(checkout)
    for item in QuickSaleCheckoutItem.objects.select_related('product').filter(
        checkout=checkout,
    ).order_by('id'):
        available = available_quantities.get(item.pk, Decimal('0.000'))
        step = 1000 if item.product.unit.lower() == 'un' else 1
        maximum_units = int(available * 1000) // step
        if maximum_units < 1:
            continue
        low, high = 1, maximum_units
        first_positive = None
        while low <= high:
            units = (low + high) // 2
            amount, _resolved = _allocation_amount(
                checkout,
                [{'item': item.pk, 'allocated_quantity': Decimal(units * step) / 1000}],
                lock_items=False, allow_zero_amount=True,
            )
            if amount > Decimal('0.00'):
                first_positive = amount
                high = units - 1
            else:
                low = units + 1
        if first_positive is not None and first_positive <= remaining:
            return True
    return False


@transaction.atomic
def preview_quick_checkout_payment(*, checkout, allocations):
    """Use the ledger allocation primitive without creating a payment."""
    checkout = QuickSaleCheckout.objects.select_for_update().get(pk=checkout.pk)
    if checkout.status != QuickSaleCheckoutStatus.OPEN:
        raise QuickCheckoutConflict('checkout_closed', 'O checkout já foi finalizado.')
    total, _resolved = _allocation_amount(checkout, allocations)
    return {
        'total': str(total),
        'available_quantities': {
            str(item_id): str(quantity)
            for item_id, quantity in checkout_available_quantities(checkout).items()
        },
    }


@transaction.atomic
def create_quick_sale_payment_intent(*, checkout, user, payment_method_id, mode, amount,
                                     allocations, provider_connection, terminal, idempotency_key,
                                     audit_metadata=None):
    from apps.payment_integrations.models import PaymentIntentStatus
    from apps.payment_integrations.services import (
        PaymentIntegrationConflict, create_payment_intent, transition_payment_intent,
    )

    session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    if session.status != CashSessionStatus.OPEN:
        raise QuickCheckoutConflict('cash_session_closed', 'Não é possível iniciar cobrança após o fechamento do caixa.')
    if checkout.status != QuickSaleCheckoutStatus.OPEN:
        raise QuickCheckoutConflict('checkout_closed', 'O checkout já foi finalizado.')
    paid, remaining = checkout_balance(checkout, lock=True)
    method = PaymentMethod.objects.select_for_update().filter(
        pk=payment_method_id, company=checkout.company, status=Status.ACTIVE,
    ).first()
    if not method:
        raise ValidationError({'payment_method': 'Forma de pagamento inválida ou inativa.'})
    if method.code == PaymentMethodCode.CASH:
        raise ValidationError({'payment_method': 'Dinheiro não pode usar integração de provedor.'})
    context, resolved_amount = _frozen_application_context(
        checkout, mode=mode, amount=amount, allocations=allocations or [], remaining=remaining,
    )
    try:
        intent, replayed = create_payment_intent(
            company=checkout.company, branch=checkout.branch, pos_device=checkout.pos_device,
            operator=user, origin_type='quick_sale', origin_id=checkout.pk,
            payment_method=method, amount=resolved_amount,
            provider_connection=provider_connection, terminal=terminal,
            application_context=context, idempotency_key=idempotency_key,
            _quick_sale_bridge=True,
        )
    except PaymentIntegrationConflict as error:
        raise QuickCheckoutConflict(error.code, error.message) from error
    if not replayed:
        intent = transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY, actor=user)
        audit_log(
            actor=user, action='quick_sale_payment_intent.created', obj=intent,
            company=checkout.company, branch=checkout.branch,
            after={'checkout_id': str(checkout.pk), 'intent_id': str(intent.pk), 'amount': str(intent.amount)},
            metadata=audit_metadata or {},
        )
    return intent, replayed


@transaction.atomic
def start_quick_sale_payment_attempt(*, checkout, intent, user, provider_connection=None,
                                     terminal=_QUICK_UNSET, request_metadata=None,
                                     audit_metadata=None):
    from apps.payment_integrations.models import PaymentIntent, PaymentIntentStatus
    from apps.payment_integrations.services import (
        PaymentIntegrationConflict, create_payment_attempt, transition_payment_attempt,
    )

    # Match POS tender writes: device -> active session -> checkout -> ledger.
    from apps.pos.services import current_pos_cash_session

    active_session = current_pos_cash_session(intent.pos_device, for_update=True)
    session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
    _validate_quick_sale_intent_context(intent, checkout)
    if session.status != CashSessionStatus.OPEN or checkout.status != QuickSaleCheckoutStatus.OPEN:
        raise QuickCheckoutConflict('checkout_not_payable', 'O checkout ou a sessão de caixa não permite cobrança.')
    if intent.status not in (PaymentIntentStatus.READY, PaymentIntentStatus.DECLINED, PaymentIntentStatus.ERROR):
        raise QuickCheckoutConflict('payment_intent_not_ready', 'O intent não aceita uma nova tentativa.')
    if active_session.pk != checkout.cash_session_id:
        raise QuickCheckoutConflict(
            'cash_context_changed',
            'O checkout pertence a outro contexto de caixa deste POS.',
        )
    paid, _remaining = checkout_balance(checkout, lock=True)
    try:
        validate_checkout_reservation(checkout, paid=True, renew_if_unpaid=paid == Decimal('0.00'))
        kwargs = {
            'intent': intent,
            'provider_connection': provider_connection,
            'request_metadata': request_metadata,
        }
        if terminal is not _QUICK_UNSET:
            kwargs['terminal'] = terminal
        attempt = create_payment_attempt(**kwargs)
        attempt = transition_payment_attempt(attempt=attempt, status='processing', actor=user)
    except StockReservationConflict as error:
        raise QuickCheckoutConflict('stock_unavailable', error.message) from error
    except PaymentIntegrationConflict as error:
        raise QuickCheckoutConflict(error.code, error.message) from error
    audit_log(
        actor=user, action='quick_sale_payment_attempt.started', obj=attempt,
        company=checkout.company, branch=checkout.branch,
        after={'checkout_id': str(checkout.pk), 'intent_id': str(intent.pk), 'attempt_id': str(attempt.pk)},
        metadata=audit_metadata or {},
    )
    return attempt


@transaction.atomic
def resolve_quick_sale_payment_attempt(*, checkout, attempt, status, user, response_metadata=None,
                                       result_data=None, audit_metadata=None):
    from apps.payment_integrations.models import PaymentAttempt, PaymentAttemptStatus, PaymentIntent
    from apps.payment_integrations.services import PaymentIntegrationConflict, resolve_payment_attempt

    _session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    attempt = PaymentAttempt.objects.select_for_update().select_related('intent').get(pk=attempt.pk)
    intent = PaymentIntent.objects.select_for_update().get(pk=attempt.intent_id)
    _validate_quick_sale_intent_context(intent, checkout)
    try:
        resolved_attempt, resolved_intent = resolve_payment_attempt(
            attempt=attempt, status=status, actor=user, response_metadata=response_metadata,
            result_data=result_data,
        )
    except PaymentIntegrationConflict as error:
        raise QuickCheckoutConflict(error.code, error.message) from error
    if status in {
        PaymentAttemptStatus.DECLINED, PaymentAttemptStatus.ERROR, PaymentAttemptStatus.CANCELLED,
    }:
        paid, _remaining = checkout_balance(checkout, lock=True)
        if paid == Decimal('0.00'):
            restore_checkout_reservation_expiry(checkout)
    audit_log(
        actor=user, action='quick_sale_payment_attempt.resolved', obj=resolved_attempt,
        company=checkout.company, branch=checkout.branch,
        after={'checkout_id': str(checkout.pk), 'intent_id': str(resolved_intent.pk), 'status': status},
        metadata=audit_metadata or {},
    )
    return resolved_attempt, resolved_intent


@transaction.atomic
def cancel_quick_sale_payment_intent(*, checkout, intent, user, audit_metadata=None):
    from apps.payment_integrations.models import PaymentIntent, PaymentIntentStatus
    from apps.payment_integrations.services import PaymentIntegrationConflict, transition_payment_intent

    _session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
    _validate_quick_sale_intent_context(intent, checkout)
    if intent.status not in {
        PaymentIntentStatus.CREATED, PaymentIntentStatus.READY,
        PaymentIntentStatus.DECLINED, PaymentIntentStatus.ERROR,
    }:
        raise QuickCheckoutConflict('payment_intent_not_cancellable', 'O intent não pode ser cancelado neste estado.')
    try:
        intent = transition_payment_intent(intent=intent, status=PaymentIntentStatus.CANCELLED, actor=user)
    except PaymentIntegrationConflict as error:
        raise QuickCheckoutConflict(error.code, error.message) from error
    paid, _remaining = checkout_balance(checkout, lock=True)
    if paid == Decimal('0.00'):
        restore_checkout_reservation_expiry(checkout)
    audit_log(
        actor=user, action='quick_sale_payment_intent.cancelled', obj=intent,
        company=checkout.company, branch=checkout.branch,
        after={'checkout_id': str(checkout.pk), 'intent_id': str(intent.pk)}, metadata=audit_metadata or {},
    )
    return intent


@transaction.atomic
def apply_approved_quick_sale_payment_intent(*, checkout, intent, user, audit_metadata=None):
    from apps.payment_integrations.models import PaymentAttempt, PaymentAttemptStatus, PaymentIntent, PaymentIntentStatus

    session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
    context = _validate_quick_sale_intent_context(intent, checkout)
    attempt = PaymentAttempt.objects.select_for_update().filter(
        intent=intent, status=PaymentAttemptStatus.APPROVED,
    ).order_by('-attempt_number').first()
    if attempt:
        existing = QuickSalePayment.objects.select_for_update().filter(source_payment_attempt=attempt).first()
        if existing:
            if (
                existing.checkout_id != checkout.pk
                or existing.payment_method_id != intent.payment_method_id
                or existing.amount != intent.amount
                or existing.source_payment_attempt_id != attempt.pk
                or attempt.intent_id != intent.pk
            ):
                raise QuickCheckoutConflict('payment_intent_apply_conflict', 'A tentativa possui pagamento aplicado inconsistente.')
            if intent.status == PaymentIntentStatus.APPLIED:
                return existing, True
            raise QuickCheckoutConflict(
                'payment_intent_apply_inconsistency',
                'Existe pagamento de provedor sem intent aplicado correspondente.',
            )
    if intent.status != PaymentIntentStatus.APPROVED:
        raise QuickCheckoutConflict('payment_intent_not_approved', 'O intent deve estar aprovado para aplicação.')
    if session.status != CashSessionStatus.OPEN or checkout.status != QuickSaleCheckoutStatus.OPEN:
        raise QuickCheckoutConflict('checkout_not_payable', 'O checkout ou a sessão de caixa não permite aplicação.')
    if not attempt:
        raise QuickCheckoutConflict('approved_attempt_missing', 'O intent aprovado não possui tentativa aprovada.')
    paid, remaining = checkout_balance(checkout, lock=True)
    if intent.amount > remaining:
        raise QuickCheckoutConflict('payment_exceeds_remaining', 'O intent aprovado excede o saldo atual do checkout.')
    allocations = _validated_application_context_allocations(intent, checkout, context)
    payment = QuickSalePayment(
        checkout=checkout, payment_method=intent.payment_method, amount=intent.amount,
        operator=intent.operator, cash_session=checkout.cash_session,
        source_type=QuickSalePaymentSourceType.PROVIDER, source_payment_attempt=attempt,
        idempotency_key=intent.pk,
        request_fingerprint=_fingerprint({'intent': str(intent.pk), 'attempt': str(attempt.pk), 'context': context}),
    )
    payment._allow_provider_creation = True
    try:
        payment.save()
    finally:
        delattr(payment, '_allow_provider_creation')
    for row in allocations:
        QuickSalePaymentAllocation.objects.create(
            payment=payment, item=row['item'],
            allocated_quantity=row['allocated_quantity'], amount=row['amount'],
        )
    intent.status = PaymentIntentStatus.APPLIED
    intent.applied_at = timezone.now()
    intent._allow_status_transition = True
    try:
        intent.save(update_fields=('status', 'applied_at', 'updated_at'))
    finally:
        delattr(intent, '_allow_status_transition')
    audit_log(
        actor=user, action='quick_sale_provider_payment.applied', obj=payment,
        company=checkout.company, branch=checkout.branch,
        after={'checkout_id': str(checkout.pk), 'intent_id': str(intent.pk), 'attempt_id': str(attempt.pk)},
        metadata=audit_metadata or {},
    )
    return payment, False


@transaction.atomic
def record_quick_checkout_payment(*, checkout, user, payment_method_id, mode, amount,
                                    received_amount, allocations, idempotency_key,
                                    pos_device,
                                    audit_metadata=None):
    if pos_device.branch_id != checkout.branch_id:
        raise ValidationError({'pos_device': 'O dispositivo deve pertencer ao checkout.'})
    # Resolve and lock the persisted POS context before touching the checkout ledger.
    from apps.pos.services import current_pos_cash_session

    active_session = current_pos_cash_session(pos_device, for_update=True)
    session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    _ensure_checkout_without_blocking_intent(checkout)
    if session.status != CashSessionStatus.OPEN:
        raise QuickCheckoutConflict('cash_session_closed', 'Não é possível registrar pagamento após o fechamento do caixa.')
    if session.pk != active_session.pk:
        raise QuickCheckoutConflict(
            'cash_context_changed',
            'O checkout pertence a outro contexto de caixa deste POS.',
        )
    payload = {'payment_method': payment_method_id, 'mode': mode, 'amount': str(amount),
               'received_amount': str(received_amount), 'allocations': allocations or []}
    fingerprint = _fingerprint(payload)
    paid, remaining = checkout_balance(checkout, lock=True)
    existing = QuickSalePayment.objects.select_for_update().filter(
        checkout=checkout, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise QuickCheckoutConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
        return existing, True
    if checkout.status != QuickSaleCheckoutStatus.OPEN:
        raise QuickCheckoutConflict('checkout_closed', 'O checkout já foi finalizado.')
    method = PaymentMethod.objects.select_for_update().filter(
        pk=payment_method_id, company=checkout.company, status=Status.ACTIVE,
    ).first()
    if not method:
        raise ValidationError({'payment_method': 'Forma de pagamento inválida ou inativa.'})
    if mode == 'value':
        amount = strict_decimal(amount, field='amount', decimal_places=2, max_digits=14)
        resolved_allocations = []
    elif mode == 'remaining':
        amount, resolved_allocations = remaining, []
    elif mode == 'items':
        amount, resolved_allocations = _allocation_amount(checkout, allocations)
    else:
        raise ValidationError({'mode': 'Modo de pagamento inválido.'})
    if amount <= 0 or amount > remaining:
        raise QuickCheckoutConflict('payment_exceeds_remaining', 'O pagamento deve estar dentro do saldo restante.')
    received = strict_decimal(received_amount, field='received_amount', decimal_places=2, max_digits=14, allow_none=True)
    if method.code == PaymentMethodCode.CASH:
        if received is None or received < amount:
            raise ValidationError({'received_amount': 'Dinheiro exige valor recebido igual ou maior ao aplicado.'})
    elif received is not None:
        raise ValidationError({'received_amount': 'Somente dinheiro aceita valor recebido.'})
    try:
        validate_checkout_reservation(
            checkout, paid=True, renew_if_unpaid=paid == Decimal('0.00'),
        )
    except StockReservationConflict as error:
        raise QuickCheckoutConflict('stock_unavailable', error.message) from error
    payment = QuickSalePayment.objects.create(
        checkout=checkout, payment_method=method, amount=amount, received_amount=received,
        change_amount=(received - amount) if received is not None else None, operator=user,
        cash_session=checkout.cash_session,
        idempotency_key=idempotency_key, request_fingerprint=fingerprint,
    )
    for allocation in resolved_allocations:
        QuickSalePaymentAllocation.objects.create(payment=payment, **allocation)
    audit_log(actor=user, action='quick_sale_checkout.payment.record', obj=payment,
              company=checkout.company, branch=checkout.branch,
              after={'checkout_id': str(checkout.pk), 'amount': str(amount)},
              metadata={**(audit_metadata or {}), 'idempotency_key': str(idempotency_key)})
    return payment, False


@transaction.atomic
def reverse_quick_checkout_payment(*, payment, user, reason, idempotency_key, authorized_by=None, audit_metadata=None):
    payment_hint = QuickSalePayment.objects.filter(pk=payment.pk).values_list(
        'checkout_id', flat=True,
    ).first()
    if payment_hint is None:
        raise QuickCheckoutConflict('payment_not_found', 'Pagamento não encontrado.')
    session, checkout, _sessions = _lock_checkout_session(payment_hint, user=user)
    _ensure_checkout_without_blocking_intent(checkout)
    checkout_balance(checkout, lock=True)
    payment = QuickSalePayment.objects.select_for_update(of=('self',)).select_related(
        'checkout', 'payment_method', 'cash_session',
    ).get(pk=payment.pk, checkout=checkout)
    if checkout.status != QuickSaleCheckoutStatus.OPEN:
        raise QuickCheckoutConflict('checkout_closed', 'O checkout já foi finalizado.')
    if session.status != CashSessionStatus.OPEN:
        raise QuickCheckoutConflict('cash_session_closed', 'Não é possível estornar após o fechamento do caixa.')
    existing = QuickSalePayment.objects.select_for_update().filter(
        checkout=checkout, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.reversal_of_id == payment.pk:
            return existing, True
        raise QuickCheckoutConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
    if payment.status != QuickSalePaymentStatus.APPLIED or hasattr(payment, 'reversal'):
        raise QuickCheckoutConflict('payment_already_reversed', 'O pagamento já foi estornado.')
    if payment.source_type == QuickSalePaymentSourceType.PROVIDER:
        raise QuickCheckoutConflict(
            'provider_reversal_required',
            'Pagamento de provedor exige reversão no provedor externo.',
        )
    reversal = QuickSalePayment.objects.create(
        checkout=payment.checkout, payment_method=payment.payment_method, amount=payment.amount,
        received_amount=payment.received_amount, change_amount=payment.change_amount, operator=user,
        cash_session=payment.cash_session,
        status=QuickSalePaymentStatus.REVERSED, idempotency_key=idempotency_key,
        request_fingerprint=_fingerprint({'payment': payment.pk, 'reason': reason}),
        reversal_of=payment, reversal_reason=(reason or '').strip(),
    )
    audit_log(actor=user, action='quick_sale_checkout.payment.reverse', obj=reversal,
               company=payment.checkout.company, branch=payment.checkout.branch,
                after={'payment_id': str(payment.pk), 'reason': reversal.reversal_reason},
                metadata={
                    **(audit_metadata or {}),
                    'idempotency_key': str(idempotency_key),
                    **({'authorizer_user_id': authorized_by.pk}
                       if authorized_by is not None and authorized_by.pk != user.pk else {}),
                })
    paid, _remaining = checkout_balance(checkout)
    if paid == Decimal('0.00'):
        restore_checkout_reservation_expiry(checkout)
    return reversal, False


@transaction.atomic
def cancel_quick_checkout(*, checkout, user, audit_metadata=None):
    _session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    _ensure_checkout_without_blocking_intent(checkout)
    if checkout.status == QuickSaleCheckoutStatus.CANCELLED:
        return checkout, True
    if checkout.status != QuickSaleCheckoutStatus.OPEN:
        raise QuickCheckoutConflict('checkout_closed', 'O checkout já foi finalizado.')
    paid, _remaining = checkout_balance(checkout, lock=True)
    if paid:
        raise QuickCheckoutConflict('checkout_paid', 'Estorne todos os pagamentos antes de cancelar.')
    release_checkout_reservation(checkout)
    checkout.status = QuickSaleCheckoutStatus.CANCELLED
    checkout.save(update_fields=('status', 'updated_at'))
    audit_log(actor=user, action='quick_sale_checkout.cancel', obj=checkout,
              company=checkout.company, branch=checkout.branch,
              after={'checkout_id': str(checkout.pk)}, metadata=audit_metadata or {})
    return checkout, False


@transaction.atomic
def finalize_quick_checkout(*, checkout, user, permissions, idempotency_key, audit_metadata=None):
    session, checkout, _sessions = _lock_checkout_session(checkout.pk, user=user)
    _ensure_checkout_without_blocking_intent(checkout)
    if checkout.status == QuickSaleCheckoutStatus.FINALIZED:
        if checkout.sale:
            return checkout.sale, True
        raise QuickCheckoutConflict('checkout_closed', 'O checkout já foi finalizado.')
    if session.status not in (CashSessionStatus.OPEN, CashSessionStatus.CLOSED):
        raise QuickCheckoutConflict('cash_session_closed', 'Não é possível finalizar após o fechamento do caixa.')
    paid, remaining = checkout_balance(checkout, lock=True)
    if remaining != Decimal('0.00'):
        raise QuickCheckoutConflict('balance_remaining', f'Ainda falta pagar R$ {remaining:.2f}.')
    try:
        reservation = validate_checkout_reservation(
            checkout, paid=True, renew_if_unpaid=paid == Decimal('0.00'),
        )
    except StockReservationConflict as error:
        raise QuickCheckoutConflict('stock_unavailable', error.message) from error
    quick_sale_payments = list(checkout.payments.filter(
        status=QuickSalePaymentStatus.APPLIED, reversal__isnull=True,
    ).select_related('payment_method'))
    payments = [
        {'payment_method': payment.payment_method_id, 'amount': payment.amount,
         **({'received_amount': payment.received_amount} if payment.received_amount is not None else {})}
        for payment in quick_sale_payments
    ]
    sale = finalize_sale(
        branch=checkout.branch, user=user, operation_type=OperationType.SALE,
        cash_session=session, seller_user=checkout.operator, customer=checkout.customer,
        items=[item.snapshot['raw'] for item in checkout.items.order_by('id')], payments=payments,
        discount=checkout.discount_intent,
        service_fee_waived=checkout.service_fee_waived,
        idempotency_key=idempotency_key, channel=SalesChannel.COUNTER, pos_device=checkout.pos_device,
        allow_pos_only=True, audit_metadata=audit_metadata, pos_permission_codes=permissions,
        pos_device_validated=True, frozen_quick_preview=checkout.financial_snapshot,
        frozen_quick_discount_approved_by=checkout.discount_approved_by,
        frozen_quick_item_discount_approved_by=checkout.item_discount_approved_by,
        frozen_quick_service_fee_waived_by=checkout.service_fee_waived_by,
        quick_sale_payment_sources=quick_sale_payments,
        quick_sale_checkout=checkout,
        allow_closed_cash_session=session.status == CashSessionStatus.CLOSED,
        stock_reservation=reservation,
    )
    consume_checkout_reservation(reservation)
    checkout.sale = sale
    checkout.status = QuickSaleCheckoutStatus.FINALIZED
    checkout.finalization_idempotency_key = idempotency_key
    checkout.save(update_fields=(
        'sale', 'status', 'finalization_idempotency_key', 'updated_at',
    ))
    audit_log(actor=user, action='quick_sale_checkout.finalize', obj=checkout,
              company=checkout.company, branch=checkout.branch,
              after={'sale_id': sale.pk, 'paid': str(paid)},
              metadata={**(audit_metadata or {}), 'idempotency_key': str(idempotency_key)})
    return sale, False
