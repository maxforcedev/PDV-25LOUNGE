import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.base.audit import audit_log
from apps.cash.models import CashSession, CashSessionStatus
from apps.companies.models import Customer, Status
from apps.products.models import SalesChannel
from apps.pos.models import (
    QuickSaleCheckout, QuickSaleCheckoutItem, QuickSalePayment,
    QuickSalePaymentAllocation, QuickSaleCheckoutStatus, QuickSalePaymentStatus,
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


@transaction.atomic
def create_quick_checkout(*, branch, device, user, permissions, cash_session_id, raw_items,
                          discount, service_fee_waived, customer_id, idempotency_key,
                          discount_authorization=None, item_discount_authorization=None,
                          service_fee_authorization=None, audit_metadata=None):
    payload = {
        'cash_session': cash_session_id, 'items': raw_items, 'discount': discount,
        'service_fee_waived': service_fee_waived, 'customer': customer_id,
    }
    fingerprint = _fingerprint(payload)
    existing = QuickSaleCheckout.objects.select_for_update().filter(
        pos_device=device, creation_idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.creation_request_fingerprint != fingerprint:
            raise QuickCheckoutConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
        return existing, True
    session = CashSession.objects.select_for_update().filter(
        pk=cash_session_id, branch=branch, status=CashSessionStatus.OPEN,
    ).first()
    if not session:
        raise ValidationError({'cash_session': 'Informe uma sessão de caixa aberta da filial.'})
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
        allow_pos_only=True, pos_device=device, permission_codes=permissions, device_validated=True,
    )
    item_discount_approver = _discount_approver(
        branch, user, preview['item_discount_total'], item_discount_authorization,
        permission_code='sales.apply_item_discount', authorization_field='item_discount_authorization',
        allow_pos_only=True, pos_device=device, permission_codes=permissions, device_validated=True,
    )
    fee_approver = _service_fee_waiver(
        branch, user, bool(service_fee_waived), service_fee_authorization,
        allow_pos_only=True, pos_device=device, permission_codes=permissions, device_validated=True,
    )
    checkout = QuickSaleCheckout.objects.create(
        company=branch.company, branch=branch, pos_device=device, cash_session=session,
        operator=user, customer=customer,
        financial_snapshot=_preview_snapshot(_financial_snapshot(preview)),
        discount_intent=_preview_snapshot(preview['discount_intent']),
        service_fee_waived=bool(service_fee_waived),
        discount_approved_by=discount_approver, item_discount_approved_by=item_discount_approver,
        service_fee_waived_by=fee_approver, creation_idempotency_key=idempotency_key,
        creation_request_fingerprint=fingerprint,
    )
    for index, item in enumerate(raw_items):
        QuickSaleCheckoutItem.objects.create(
            checkout=checkout, client_item_id=item['client_item_id'], product_id=item['product'],
            quantity=item['quantity'], snapshot={'raw': _preview_snapshot(item), 'preview': _preview_snapshot(preview['items'][index])},
        )
    audit_log(actor=user, action='quick_sale_checkout.create', obj=checkout,
              company=branch.company, branch=branch,
              after={'checkout_id': str(checkout.pk), 'total': str(preview['total'])},
              metadata={**(audit_metadata or {}), 'idempotency_key': str(idempotency_key)})
    return checkout, False


def checkout_balance(checkout, *, lock=False):
    payments = QuickSalePayment.objects
    if lock:
        payments = payments.select_for_update()
    paid = payments.filter(
        checkout=checkout, status=QuickSalePaymentStatus.APPLIED, reversal__isnull=True,
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    total = strict_decimal(
        checkout.financial_snapshot['financials']['total'], field='checkout.total',
        decimal_places=2, max_digits=14,
    )
    return paid, total - paid


def _allocation_amount(checkout, allocations):
    if not allocations:
        raise ValidationError({'allocations': 'Pagamento por itens exige ao menos uma alocação.'})
    item_ids = [row.get('item') for row in allocations]
    if len(item_ids) != len(set(item_ids)):
        raise ValidationError({'allocations': 'Informe cada item apenas uma vez por pagamento.'})
    items = {
        item.pk: item for item in QuickSaleCheckoutItem.objects.select_for_update().filter(
            checkout=checkout, pk__in=item_ids,
        )
    }
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
        for row in QuickSalePaymentAllocation.objects.select_for_update().filter(
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
        if amount <= 0:
            raise QuickCheckoutConflict('item_allocation_mismatch', 'A alocação não gera valor a pagar.')
        resolved.append({'item': item, 'allocated_quantity': quantity, 'amount': amount})
        total += amount
    return total, resolved


@transaction.atomic
def record_quick_checkout_payment(*, checkout, user, payment_method_id, mode, amount,
                                  received_amount, allocations, idempotency_key,
                                  audit_metadata=None):
    checkout = QuickSaleCheckout.objects.select_for_update().get(pk=checkout.pk)
    payload = {'payment_method': payment_method_id, 'mode': mode, 'amount': str(amount),
               'received_amount': str(received_amount), 'allocations': allocations or []}
    fingerprint = _fingerprint(payload)
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
    paid, remaining = checkout_balance(checkout, lock=True)
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
    payment = QuickSalePayment.objects.create(
        checkout=checkout, payment_method=method, amount=amount, received_amount=received,
        change_amount=(received - amount) if received is not None else None, operator=user,
        cash_session=checkout.cash_session if method.code == PaymentMethodCode.CASH else None,
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
def reverse_quick_checkout_payment(*, payment, user, reason, idempotency_key, audit_metadata=None):
    payment = QuickSalePayment.objects.select_for_update().select_related('checkout').get(pk=payment.pk)
    if payment.checkout.status != QuickSaleCheckoutStatus.OPEN:
        raise QuickCheckoutConflict('checkout_closed', 'O checkout já foi finalizado.')
    existing = QuickSalePayment.objects.select_for_update().filter(
        checkout=payment.checkout, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.reversal_of_id == payment.pk:
            return existing, True
        raise QuickCheckoutConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
    if payment.status != QuickSalePaymentStatus.APPLIED or hasattr(payment, 'reversal'):
        raise QuickCheckoutConflict('payment_already_reversed', 'O pagamento já foi estornado.')
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
              after={'payment_id': payment.pk, 'reason': reversal.reversal_reason},
              metadata={**(audit_metadata or {}), 'idempotency_key': str(idempotency_key)})
    return reversal, False


@transaction.atomic
def finalize_quick_checkout(*, checkout, user, permissions, idempotency_key, audit_metadata=None):
    checkout = QuickSaleCheckout.objects.select_for_update().select_related(
        'branch', 'pos_device', 'cash_session', 'customer', 'discount_approved_by',
        'item_discount_approved_by', 'service_fee_waived_by', 'sale',
    ).get(pk=checkout.pk)
    if checkout.status == QuickSaleCheckoutStatus.FINALIZED:
        if checkout.sale:
            return checkout.sale, True
        raise QuickCheckoutConflict('checkout_closed', 'O checkout já foi finalizado.')
    if checkout.cash_session.status != CashSessionStatus.OPEN:
        raise QuickCheckoutConflict('cash_session_closed', 'Não é possível finalizar após o fechamento do caixa.')
    paid, remaining = checkout_balance(checkout, lock=True)
    if remaining != Decimal('0.00'):
        raise QuickCheckoutConflict('balance_remaining', f'Ainda falta pagar R$ {remaining:.2f}.')
    payments = [
        {'payment_method': payment.payment_method_id, 'amount': payment.amount,
         **({'received_amount': payment.received_amount} if payment.received_amount is not None else {})}
        for payment in checkout.payments.filter(
            status=QuickSalePaymentStatus.APPLIED, reversal__isnull=True,
        ).select_related('payment_method')
    ]
    sale = finalize_sale(
        branch=checkout.branch, user=user, operation_type=OperationType.SALE,
        cash_session=checkout.cash_session, seller_user=checkout.operator, customer=checkout.customer,
        items=[item.snapshot['raw'] for item in checkout.items.order_by('id')], payments=payments,
        discount=checkout.discount_intent,
        service_fee_waived=checkout.service_fee_waived,
        idempotency_key=idempotency_key, channel=SalesChannel.COUNTER, pos_device=checkout.pos_device,
        allow_pos_only=True, audit_metadata=audit_metadata, pos_permission_codes=permissions,
        pos_device_validated=True, frozen_quick_preview=checkout.financial_snapshot,
        frozen_quick_discount_approved_by=checkout.discount_approved_by,
        frozen_quick_item_discount_approved_by=checkout.item_discount_approved_by,
        frozen_quick_service_fee_waived_by=checkout.service_fee_waived_by,
    )
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
