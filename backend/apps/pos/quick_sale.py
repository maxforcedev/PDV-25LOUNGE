"""Persistent counter checkout ledger and official item-payment allocation rules."""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.base.audit import audit_log, model_snapshot
from apps.cash.models import CashSession, CashSessionStatus
from apps.companies.models import Customer, Status
from apps.sales.models import OperationType, PaymentMethod, PaymentMethodCode
from apps.sales.serializers import CalculationOutputSerializer
from apps.sales.services import (
    _allocate_money, _discount_approver, _service_fee_waiver, calculate_preview,
    finalize_sale,
)
from apps.products.models import SalesChannel

from .models import (
    QuickSaleCheckout, QuickSaleCheckoutItem, QuickSaleCheckoutStatus,
    QuickSalePayment, QuickSalePaymentAllocation, QuickSalePaymentStatus,
)


CENT = Decimal('0.01')


def _audit_metadata(metadata, **extra):
    return {**(metadata or {}), **extra}


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def _active_payments(checkout, *, lock=False):
    queryset = QuickSalePayment.objects.filter(
        checkout=checkout, status=QuickSalePaymentStatus.APPLIED, reversal__isnull=True,
    )
    return queryset.select_for_update() if lock else queryset


def checkout_state(checkout, *, lock=False):
    total = Decimal(str(checkout.financial_snapshot.get('total', '0.00')))
    paid = sum((row.amount for row in _active_payments(checkout, lock=lock)), Decimal('0.00'))
    return total, paid, total - paid


def _set_status(checkout, *, lock=False):
    total, paid, remaining = checkout_state(checkout, lock=lock)
    desired = QuickSaleCheckoutStatus.PAID if total and remaining == Decimal('0.00') else QuickSaleCheckoutStatus.OPEN
    if checkout.status != desired:
        checkout.status = desired
        checkout.save(update_fields=('status', 'updated_at'))
    return total, paid, remaining


def _assert_editable(checkout):
    if checkout.status in {QuickSaleCheckoutStatus.FINALIZED, QuickSaleCheckoutStatus.CANCELLED}:
        raise ValidationError({'status': 'Este checkout não pode mais ser alterado.'})
    if _active_payments(checkout, lock=True).exists():
        raise ValidationError({'status': 'Itens e financeiro ficam bloqueados após o primeiro pagamento aplicado.'})


def _items_for_preview(items):
    return [{
        'client_item_id': item['client_item_id'], 'product': item['product'],
        'quantity': item['quantity'], 'discount': item.get('discount', '0.00'),
        'modifiers': item.get('modifiers', []), 'notes': item.get('notes', ''),
    } for item in items]


def _official_preview(*, checkout, items, discount, service_fee_waived):
    preview = calculate_preview(
        company=checkout.company, operation_type=OperationType.SALE,
        raw_items=_items_for_preview(items), discount=discount, charged_amount=None,
        beneficiary_user=None, branch=checkout.branch, channel=SalesChannel.COUNTER,
        service_fee_waived=service_fee_waived,
    )
    output = CalculationOutputSerializer(preview)
    return output.data, preview


@transaction.atomic
def update_checkout(*, checkout, user, items, discount, service_fee_waived,
                    discount_authorization=None, item_discount_authorization=None,
                    service_fee_authorization=None, customer_id=None, cash_session=None,
                    permission_codes=None, device=None, audit_metadata=None):
    checkout = QuickSaleCheckout.objects.select_for_update().select_related(
        'company', 'branch', 'pos_device',
    ).get(pk=checkout.pk)
    _assert_editable(checkout)
    if customer_id is not None:
        customer = Customer.objects.filter(
            pk=customer_id, company=checkout.company, status=Status.ACTIVE,
        ).first()
        if not customer:
            raise ValidationError({'customer': 'Cliente inválido, inativo ou fora da empresa.'})
        checkout.customer = customer
    if cash_session is not None:
        if cash_session.branch_id != checkout.branch_id or cash_session.status != CashSessionStatus.OPEN:
            raise ValidationError({'cash_session': 'Informe uma sessão de caixa aberta da filial.'})
        checkout.cash_session = cash_session
    output, preview = _official_preview(
        checkout=checkout, items=items, discount=discount,
        service_fee_waived=service_fee_waived,
    )
    checkout.discount_approved_by = _discount_approver(
        checkout.branch, user, preview['discount'], discount_authorization,
        permission_code='sales.apply_discount', authorization_field='discount_authorization',
        allow_pos_only=True, pos_device=device, permission_codes=permission_codes,
        device_validated=True,
    )
    item_discount = preview['item_discount_total']
    checkout.item_discount_approved_by = _discount_approver(
        checkout.branch, user, item_discount, item_discount_authorization,
        permission_code='sales.apply_item_discount', authorization_field='item_discount_authorization',
        allow_pos_only=True, pos_device=device, permission_codes=permission_codes,
        device_validated=True,
    )
    checkout.service_fee_waived_by = _service_fee_waiver(
        checkout.branch, user, bool(service_fee_waived), service_fee_authorization,
        allow_pos_only=True, pos_device=device, permission_codes=permission_codes,
        device_validated=True,
    )
    # Draft lines may be replaced only before any tender exists; paid lines are append-only.
    QuickSaleCheckoutItem.objects.filter(checkout=checkout).delete()
    for source, snapshot in zip(items, output['items']):
        QuickSaleCheckoutItem.objects.create(
            checkout=checkout, client_item_id=source['client_item_id'],
            product_id=snapshot['product'], quantity=snapshot['quantity'],
            snapshot={**snapshot, 'manual_discount_intent': source.get('discount', '0.00')},
        )
    checkout.discount_intent = discount if isinstance(discount, dict) else {'type': 'amount', 'value': str(discount or '0.00')}
    checkout.service_fee_waived = bool(service_fee_waived)
    checkout.financial_snapshot = {key: value for key, value in output.items() if key != 'items'}
    checkout.status = QuickSaleCheckoutStatus.OPEN
    checkout.save()
    audit_log(
        actor=user, action='pos.quick_sale.checkout.update', obj=checkout,
        company=checkout.company, branch=checkout.branch,
        after={'total': output['total'], 'item_count': len(output['items'])},
        metadata=_audit_metadata(audit_metadata),
    )
    return checkout


def allocation_preview(*, checkout, allocations, lock=False):
    """Calculate line tender from the saved official preview, including fee and discounts."""
    items = list(QuickSaleCheckoutItem.objects.select_for_update().filter(checkout=checkout).order_by('id')) if lock else list(checkout.items.all())
    by_id = {str(item.pk): item for item in items}
    if not allocations:
        raise ValidationError({'allocations': 'Informe ao menos um item para alocar o pagamento.'})
    requested_ids = [str(row.get('item')) for row in allocations]
    if len(requested_ids) != len(set(requested_ids)) or any(item_id not in by_id for item_id in requested_ids):
        raise ValidationError({'allocations': 'Cada item deve pertencer uma única vez ao checkout.'})
    existing = {
        str(row['item_id']): (row['quantity'] or Decimal('0.000'), row['amount'] or Decimal('0.00'))
        for row in QuickSalePaymentAllocation.objects.select_for_update().filter(
            item_id__in=[item.pk for item in items], payment__status=QuickSalePaymentStatus.APPLIED,
            payment__reversal__isnull=True,
        ).values('item_id').annotate(
            quantity=__import__('django.db.models', fromlist=['Sum']).Sum('allocated_quantity'),
            amount=__import__('django.db.models', fromlist=['Sum']).Sum('amount'),
        )
    }
    snapshots = [item.snapshot for item in items]
    checkout_discount = _allocate_money(
        Decimal(str(checkout.financial_snapshot['discount'])),
        [(index, Decimal(str(row['net_subtotal']))) for index, row in enumerate(snapshots)],
    )
    revenue = {
        index: Decimal(str(row['net_subtotal'])) - checkout_discount[index]
        for index, row in enumerate(snapshots)
    }
    service = _allocate_money(
        Decimal(str(checkout.financial_snapshot['service_fee_amount'])),
        [(index, amount) for index, amount in revenue.items() if snapshots[index]['participates_in_service_fee']],
    )
    result, total = [], Decimal('0.00')
    for row in allocations:
        item = by_id[str(row['item'])]
        quantity = Decimal(str(row['quantity']))
        if quantity <= 0 or quantity.as_tuple().exponent < -3:
            raise ValidationError({'allocations': 'Quantidade alocada inválida.'})
        allocated_quantity, allocated_amount = existing.get(str(item.pk), (Decimal('0.000'), Decimal('0.00')))
        if allocated_quantity + quantity > item.quantity:
            raise ValidationError({'allocations': 'A quantidade alocada excede o saldo disponível do item.'})
        index = items.index(item)
        final_amount = revenue[index] + service.get(index, Decimal('0.00'))
        cumulative = ((allocated_quantity + quantity) * final_amount / item.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        amount = cumulative - allocated_amount
        if amount <= 0:
            raise ValidationError({'allocations': 'A alocação selecionada não gera valor a pagar.'})
        result.append({'item': item, 'allocated_quantity': quantity, 'amount': amount, 'available_quantity': item.quantity - allocated_quantity})
        total += amount
    return result, total


@transaction.atomic
def apply_payment(*, checkout, user, payment_method_id, mode, amount, received_amount,
                  allocations, idempotency_key, cash_session, audit_metadata=None):
    checkout = QuickSaleCheckout.objects.select_for_update().select_related('company', 'branch', 'cash_session').get(pk=checkout.pk)
    existing = QuickSalePayment.objects.select_for_update().filter(checkout=checkout, idempotency_key=idempotency_key).first()
    request_payload = {'payment_method': payment_method_id, 'mode': mode, 'amount': str(amount) if amount is not None else None,
                       'received_amount': str(received_amount) if received_amount is not None else None,
                       'cash_session': getattr(cash_session, 'pk', None), 'allocations': allocations or []}
    fingerprint = _fingerprint(request_payload)
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise ValidationError({'idempotency_key': 'A chave de idempotência já foi usada com outros dados.'})
        return existing, True
    if checkout.status in {QuickSaleCheckoutStatus.FINALIZED, QuickSaleCheckoutStatus.CANCELLED}:
        raise ValidationError({'status': 'Este checkout não aceita pagamentos.'})
    method = PaymentMethod.objects.select_for_update().filter(
        pk=payment_method_id, company=checkout.company, status=Status.ACTIVE,
    ).first()
    if not method:
        raise ValidationError({'payment_method': 'Forma de pagamento inválida ou inativa.'})
    if cash_session is None or cash_session.branch_id != checkout.branch_id or cash_session.status != CashSessionStatus.OPEN:
        raise ValidationError({'cash_session': 'Informe uma sessão de caixa aberta da filial.'})
    if checkout.cash_session_id and checkout.cash_session_id != cash_session.pk:
        raise ValidationError({'cash_session': 'Todos os pagamentos do checkout devem usar a mesma sessão de caixa.'})
    if method.code != PaymentMethodCode.CASH and received_amount is not None:
        raise ValidationError({'received_amount': 'Somente dinheiro aceita valor recebido e troco.'})
    if mode == 'items':
        calculated_allocations, amount = allocation_preview(checkout=checkout, allocations=allocations, lock=True)
    else:
        if amount is None or amount <= 0:
            raise ValidationError({'amount': 'Informe um valor positivo para o pagamento manual.'})
        calculated_allocations = []
    total, _paid, remaining = checkout_state(checkout, lock=True)
    if amount > remaining:
        raise ValidationError({'amount': f'O pagamento excede o saldo de R$ {remaining:.2f}.'})
    if method.code == PaymentMethodCode.CASH and (received_amount is None or received_amount < amount):
        raise ValidationError({'received_amount': 'Dinheiro exige valor recebido igual ou maior ao aplicado.'})
    if not checkout.cash_session_id:
        checkout.cash_session = cash_session
        checkout.save(update_fields=('cash_session', 'updated_at'))
    payment = QuickSalePayment.objects.create(
        checkout=checkout, payment_method=method, amount=amount, received_amount=received_amount,
        cash_session=cash_session if method.code == PaymentMethodCode.CASH else None,
        operator=user, idempotency_key=idempotency_key, request_fingerprint=fingerprint,
    )
    for row in calculated_allocations:
        QuickSalePaymentAllocation.objects.create(payment=payment, item=row['item'], allocated_quantity=row['allocated_quantity'], amount=row['amount'])
    _set_status(checkout, lock=True)
    audit_log(actor=user, action='pos.quick_sale.payment.apply', obj=payment, company=checkout.company,
              branch=checkout.branch, after={'amount': str(amount), 'source_type': 'manual'},
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return payment, False


@transaction.atomic
def reverse_payment(*, payment, user, reason, idempotency_key, audit_metadata=None):
    payment = QuickSalePayment.objects.select_for_update().select_related('checkout__branch__company', 'cash_session').get(pk=payment.pk)
    checkout = QuickSaleCheckout.objects.select_for_update().get(pk=payment.checkout_id)
    fingerprint = _fingerprint({'payment': str(payment.pk), 'reason': (reason or '').strip()})
    existing = QuickSalePayment.objects.select_for_update().filter(checkout=checkout, idempotency_key=idempotency_key).first()
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise ValidationError({'idempotency_key': 'A chave de idempotência já foi usada com outros dados.'})
        return existing, True
    if checkout.status == QuickSaleCheckoutStatus.FINALIZED:
        raise ValidationError({'status': 'Não é possível estornar checkout finalizado.'})
    if payment.status != QuickSalePaymentStatus.APPLIED or hasattr(payment, 'reversal'):
        raise ValidationError({'payment': 'O pagamento já foi estornado.'})
    if payment.cash_session_id and payment.cash_session.status != CashSessionStatus.OPEN:
        raise ValidationError({'cash_session': 'Não é possível estornar após o fechamento do caixa.'})
    reversal = QuickSalePayment.objects.create(
        checkout=checkout, payment_method=payment.payment_method, amount=payment.amount,
        received_amount=payment.received_amount, cash_session=payment.cash_session, operator=user,
        status=QuickSalePaymentStatus.REVERSED, idempotency_key=idempotency_key,
        request_fingerprint=fingerprint, reversal_of=payment, reversal_reason=(reason or '').strip(),
    )
    _set_status(checkout, lock=True)
    audit_log(actor=user, action='pos.quick_sale.payment.reverse', obj=reversal, company=checkout.company,
              branch=checkout.branch, after={'payment_id': str(payment.pk), 'reason': reversal.reversal_reason},
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return reversal, False


@transaction.atomic
def finalize_checkout(*, checkout, user, idempotency_key, permission_codes, device, audit_metadata=None):
    checkout = QuickSaleCheckout.objects.select_for_update().select_related(
        'branch__company', 'cash_session', 'discount_approved_by', 'item_discount_approved_by',
        'service_fee_waived_by',
    ).get(pk=checkout.pk)
    if checkout.status == QuickSaleCheckoutStatus.FINALIZED:
        if checkout.finalization_idempotency_key == idempotency_key:
            return checkout, True
        raise ValidationError({'status': 'Este checkout já foi finalizado.'})
    total, paid, remaining = checkout_state(checkout, lock=True)
    if remaining != Decimal('0.00'):
        raise ValidationError({'remaining': f'Não é possível finalizar: saldo de R$ {remaining:.2f}.'})
    if not checkout.cash_session_id or checkout.cash_session.status != CashSessionStatus.OPEN:
        raise ValidationError({'cash_session': 'A sessão de caixa do checkout deve permanecer aberta para finalizar.'})
    payments = list(_active_payments(checkout, lock=True).select_related('payment_method').order_by('created_at', 'id'))
    frozen_preview = {
        'financials': checkout.financial_snapshot,
        'discount_intent': checkout.discount_intent,
        'items': [item.snapshot for item in checkout.items.order_by('id')],
    }
    sale = finalize_sale(
        branch=checkout.branch, user=user, operation_type=OperationType.SALE,
        cash_session=checkout.cash_session, seller_user=checkout.operator,
        customer=checkout.customer, items=[{
            'product': item.product_id, 'quantity': str(item.quantity),
            'modifiers': [{'option': row['option_id'], 'quantity': row['selected_quantity']} for row in item.snapshot.get('modifier_snapshot', [])],
            'notes': item.snapshot.get('notes', ''), 'discount': item.snapshot.get('manual_discount_intent', '0.00'),
        } for item in checkout.items.order_by('id')],
        payments=[{'payment_method': row.payment_method_id, 'amount': row.amount, 'received_amount': row.received_amount} for row in payments],
        discount=checkout.discount_intent, service_fee_waived=checkout.service_fee_waived,
        idempotency_key=idempotency_key, channel=SalesChannel.COUNTER, pos_device=device,
        allow_pos_only=True, pos_permission_codes=permission_codes, pos_device_validated=True,
        audit_metadata=_audit_metadata(audit_metadata, quick_sale_checkout_id=str(checkout.pk)),
        frozen_quick_preview=frozen_preview,
        frozen_quick_discount_approved_by=checkout.discount_approved_by,
        frozen_quick_item_discount_approved_by=checkout.item_discount_approved_by,
        frozen_quick_service_fee_waived_by=checkout.service_fee_waived_by,
    )
    checkout.sale = sale
    checkout.status = QuickSaleCheckoutStatus.FINALIZED
    checkout.finalization_idempotency_key = idempotency_key
    checkout.save(update_fields=('sale', 'status', 'finalization_idempotency_key', 'updated_at'))
    audit_log(actor=user, action='pos.quick_sale.checkout.finalize', obj=checkout, company=checkout.company,
              branch=checkout.branch, after={'sale_id': sale.pk, 'total': str(total)},
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return checkout, bool(getattr(sale, '_idempotency_replayed', False))
