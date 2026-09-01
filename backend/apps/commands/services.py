import hashlib
import json
from dataclasses import dataclass

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from apps.base.audit import audit_log, model_snapshot
from apps.companies.features import require_branch_feature
from apps.companies.models import Branch, Company, Customer, Status
from apps.companies.selectors import eligible_branch_users
from apps.inventory.models import (
    MovementType, MovementNature, MovementDomainOrigin, Stock, StockMovement,
)
from apps.inventory.materialization import materialize_stock
from apps.inventory.services import apply_locked_stock
from apps.products.models import (
    FractionableProductConfig, Product, ProductBranchConfig, ProductComponent, ProductFractionComponent,
    Unit, SalesChannel, InventoryBehavior,
)
from apps.sales.services import (
    apply_modifier_stock_requirements, resolve_modifiers, branch_price_map, branch_cost_map,
    calculate_command_preview, finalize_sale, CENT, strict_decimal,
    _discount_approver, _service_fee_waiver,
)
from apps.cash.models import CashSession, CashSessionStatus
from apps.sales.models import PaymentMethod, PaymentMethodCode

from .models import (
    Command, CommandOperation, CommandOperationType, CommandPayment, CommandPaymentStatus,
    CommandStatus, Order, OrderItem,
    OrderItemStatus, OrderStatus,
    Table, TableStatus,
)


class CommandConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = 'command_conflict'

    def __init__(self, code, message):
        super().__init__({'code': code, 'message': message})


def _operation_fingerprint(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _start_command_operation(*, branch, operation_type, idempotency_key, payload):
    fingerprint = _operation_fingerprint(payload)
    existing = CommandOperation.objects.select_for_update().filter(
        branch=branch, operation_type=operation_type, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.payload_fingerprint != fingerprint:
            raise CommandConflict(
                'idempotency_key_conflict',
                'A chave de idempotência já foi usada com outros dados.',
            )
        return existing, True
    return CommandOperation.objects.create(
        company=branch.company, branch=branch, operation_type=operation_type,
        idempotency_key=idempotency_key, payload_fingerprint=fingerprint,
    ), False


def _lock_open_commands(source_id, destination_id=None):
    ids = sorted({source_id, destination_id} - {None})
    commands = {
        command.pk: command
        for command in Command.objects.select_for_update().select_related('branch__company')
        .filter(pk__in=ids).order_by('pk')
    }
    source = commands.get(source_id)
    destination = commands.get(destination_id) if destination_id else None
    if not source or (destination_id and not destination):
        raise ValidationError({'command': 'Comanda não encontrada.'})
    if source.status != CommandStatus.OPEN or (destination and destination.status != CommandStatus.OPEN):
        raise CommandConflict('command_closed', 'A operação exige comandas abertas.')
    if destination and (
        source.company_id != destination.company_id or source.branch_id != destination.branch_id
    ):
        raise CommandConflict('command_scope_mismatch', 'As comandas devem ser da mesma empresa e filial.')
    return source, destination


def _locked_applied_payment_total(command):
    amounts = CommandPayment.objects.select_for_update(of=('self',)).filter(
        command=command, status=CommandPaymentStatus.APPLIED, reversal__isnull=True,
    ).values_list('amount', flat=True)
    return sum(amounts, Decimal('0.00'))


@dataclass(frozen=True)
class CommandFinancialState:
    subtotal: Decimal
    promotion_discount: Decimal
    manual_discount: Decimal
    service_fee: Decimal
    total_due: Decimal
    valid_paid_amount: Decimal
    remaining_balance: Decimal
    preview: dict

    @classmethod
    def calculate(cls, *, command, order_items=None, seller_user=None, discount=None,
                  service_fee_waived=None, lock=False):
        if order_items is None:
            items = OrderItem.objects.filter(
                order__command=command, status=OrderItemStatus.CONFIRMED,
            ).select_related('product__category').order_by('id')
            if lock:
                items = items.select_for_update()
            order_items = list(items)
        preview = calculate_command_preview(
            branch=command.branch, order_items=order_items,
            discount=command.checkout_discount if discount is None else discount,
            seller_user=seller_user,
            service_fee_waived=(command.checkout_service_fee_waived if service_fee_waived is None else service_fee_waived),
            lock=lock, include_internal_snapshots=True,
        )
        paid = _locked_applied_payment_total(command) if lock else CommandPayment.objects.filter(
            command=command, status=CommandPaymentStatus.APPLIED, reversal__isnull=True,
        ).aggregate(total=Coalesce(Sum('amount'), Value(Decimal('0.00'), output_field=DecimalField(max_digits=14, decimal_places=2))))['total']
        return cls(
            subtotal=preview['subtotal'], promotion_discount=preview['promotion_discount_total'],
            manual_discount=preview['discount'], service_fee=preview['service_fee_amount'],
            total_due=preview['total'], valid_paid_amount=paid,
            remaining_balance=max(preview['total'] - paid, Decimal('0.00')), preview=preview,
        )


def _assert_paid_not_above_total(command, *, order_items=None):
    state = CommandFinancialState.calculate(command=command, order_items=order_items, lock=True)
    if state.valid_paid_amount > state.total_due:
        raise CommandConflict(
            'command_paid_exceeds_total',
            f'A operação reduziria o total da comanda para R$ {state.total_due:.2f}, abaixo dos R$ {state.valid_paid_amount:.2f} já pagos. Estorne pagamentos antes de alterar a comanda.',
        )
    return state


def _assert_no_applied_payments(*commands):
    """V1 does not redistribute the immutable command-payment ledger."""
    command_ids = [command.pk for command in commands if command]
    if CommandPayment.objects.filter(
        command_id__in=command_ids,
        status=CommandPaymentStatus.APPLIED,
        reversal__isnull=True,
    ).exists():
        raise CommandConflict(
            'command_payments_transfer_unsupported',
            'Transferir, mesclar ou dividir comandas com pagamentos aplicados não é suportado. Estorne os pagamentos antes da operação.',
        )


def command_payment_summary(*, command):
    state = CommandFinancialState.calculate(command=command)
    return {
        'command_id': command.pk,
        'subtotal': f'{state.subtotal:.2f}',
        'promotion_discount': f'{state.promotion_discount:.2f}',
        'manual_discount': f'{state.manual_discount:.2f}',
        'service_fee': f'{state.service_fee:.2f}',
        'total_due': f'{state.total_due:.2f}',
        'valid_paid_amount': f'{state.valid_paid_amount:.2f}',
        'remaining_balance': f'{state.remaining_balance:.2f}',
        # Keep the established response names for existing clients.
        'command_total': f'{state.total_due:.2f}',
        'paid_total': f'{state.valid_paid_amount:.2f}',
        'remaining_total': f'{state.remaining_balance:.2f}',
    }


def _lock_payment_method_and_session(*, command, payment_method, cash_session):
    method = PaymentMethod.objects.select_for_update().filter(pk=payment_method).first()
    if not method or method.company_id != command.company_id or method.status != Status.ACTIVE:
        raise ValidationError({'payment_method': 'Forma de pagamento inválida ou inativa.'})
    session = None
    if method.code == PaymentMethodCode.CASH:
        if not cash_session:
            raise ValidationError({'cash_session': 'Dinheiro exige uma sessão de caixa aberta.'})
        session = CashSession.objects.select_for_update().filter(pk=cash_session).first()
        if not session or session.branch_id != command.branch_id or session.status != CashSessionStatus.OPEN:
            raise ValidationError({'cash_session': 'A sessão deve estar aberta e pertencer à filial da comanda.'})
    elif cash_session:
        raise ValidationError({'cash_session': 'Somente pagamento em dinheiro utiliza sessão de caixa.'})
    return method, session


@transaction.atomic
def record_command_payment(*, command, user, payment_method, amount, received_amount=None,
                            cash_session=None, idempotency_key=None, discount=None,
                            discount_authorization=None, service_fee_waived=None,
                            service_fee_authorization=None, support_session=None):
    amount = strict_decimal(amount, field='amount', decimal_places=2, max_digits=14)
    received = strict_decimal(received_amount, field='received_amount', decimal_places=2, max_digits=14, allow_none=True)
    command = Command.objects.select_related('branch__company').get(pk=command.pk)
    require_branch_feature(command.branch, 'commands')
    # Cash writers lock the drawer before the command, matching close_session.
    method, session = _lock_payment_method_and_session(
        command=command, payment_method=payment_method, cash_session=cash_session,
    )
    command = Command.objects.select_for_update().select_related('branch__company').get(pk=command.pk)
    if command.status != CommandStatus.OPEN:
        raise CommandConflict('command_closed', 'Pagamentos parciais exigem comanda aberta.')
    existing_payments = CommandPayment.objects.select_for_update(of=('self',)).filter(
        command=command, status=CommandPaymentStatus.APPLIED, reversal__isnull=True,
    )
    # Django's exists() query drops the OF target, reintroducing the nullable
    # reverse join lock PostgreSQL rejects.
    has_valid_payment = bool(list(existing_payments))
    requested_discount = strict_decimal(
        discount if discount is not None else command.checkout_discount,
        field='discount', decimal_places=2, max_digits=14,
    )
    requested_waiver = (
        command.checkout_service_fee_waived if service_fee_waived is None else service_fee_waived
    )
    if has_valid_payment and (
        requested_discount != command.checkout_discount
        or requested_waiver != command.checkout_service_fee_waived
    ):
        raise CommandConflict('checkout_context_mismatch', 'Desconto e taxa de serviço já foram definidos pelo primeiro pagamento.')
    existing = CommandPayment.objects.select_for_update().filter(command=command, idempotency_key=idempotency_key).first()
    if existing:
        same = (existing.payment_method_id == payment_method and existing.amount == amount
                and existing.received_amount == received and existing.cash_session_id == (session.pk if session else None))
        if not same:
            raise CommandConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
        return existing
    if not has_valid_payment:
        # Authorize when the settlement context is first frozen, not per tender row.
        _discount_approver(command.branch, user, requested_discount, discount_authorization,
                           permission_code='sales.apply_discount', authorization_field='discount_authorization')
        _service_fee_waiver(command.branch, user, bool(requested_waiver), service_fee_authorization)
        command.checkout_discount = requested_discount
        command.checkout_service_fee_waived = bool(requested_waiver)
        command.save(update_fields=('checkout_discount', 'checkout_service_fee_waived', 'updated_at'))
    if method.code == PaymentMethodCode.CASH:
        if received is None or received < amount:
            raise ValidationError({'received_amount': 'Dinheiro exige valor recebido igual ou maior ao valor aplicado.'})
        change = received - amount
    elif received is not None:
        raise ValidationError({'received_amount': 'Somente dinheiro aceita valor recebido.'})
    else:
        change = None
    state = _assert_paid_not_above_total(command)
    if state.valid_paid_amount + amount > state.total_due:
        raise CommandConflict('command_overpayment', f'O pagamento excede o saldo da comanda de R$ {state.remaining_balance:.2f}.')
    payment = CommandPayment.objects.create(company=command.company, branch=command.branch, command=command,
        payment_method=method, amount=amount, received_amount=received, change_amount=change,
        cash_session=session, operator=user, idempotency_key=idempotency_key)
    audit_log(actor=user, action='command.payment.record', obj=payment, company=command.company, branch=command.branch,
              after={'command_id': command.pk, 'amount': str(amount), 'payment_method_id': method.pk, 'cash_session_id': session.pk if session else None},
              metadata={'idempotency_key': str(idempotency_key), 'support_session': str(support_session.pk) if support_session else None})
    return payment


@transaction.atomic
def reverse_command_payment(*, command, payment_id, user, reason, idempotency_key, support_session=None):
    try:
        payment_id = int(payment_id)
    except (TypeError, ValueError):
        raise ValidationError({'payment': 'Pagamento inválido.'})
    reason = reason.strip()
    original_hint = CommandPayment.objects.select_related('cash_session').filter(
        pk=payment_id, command_id=command.pk, status=CommandPaymentStatus.APPLIED,
    ).first()
    if not original_hint:
        raise ValidationError({'payment': 'Pagamento aplicado não encontrado.'})
    if original_hint.cash_session_id:
        session = CashSession.objects.select_for_update().get(pk=original_hint.cash_session_id)
        if session.status != CashSessionStatus.OPEN:
            audit_log(
                actor=user, action='command.payment.reverse_blocked', obj=original_hint,
                company=original_hint.company, branch=original_hint.branch,
                metadata={
                    'command_id': original_hint.command_id,
                    'cash_session_id': session.pk,
                    'amount': str(original_hint.amount),
                    'reason': 'cash_session_closed',
                    'idempotency_key': str(idempotency_key),
                    'support_session': str(support_session.pk) if support_session else None,
                },
            )
            raise ValidationError({'cash_session': 'Não é possível estornar pagamento de uma sessão fechada.'})
    # Keep the same session-then-command locking order used by recording and close.
    command = Command.objects.select_for_update().select_related('branch__company').get(pk=command.pk)
    if command.status != CommandStatus.OPEN:
        raise CommandConflict('command_closed', 'Estornos exigem comanda aberta.')
    existing = CommandPayment.objects.select_for_update().filter(command=command, idempotency_key=idempotency_key).first()
    if existing:
        if existing.reversal_of_id == payment_id and existing.reversal_reason == reason:
            return existing
        raise CommandConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
    original = CommandPayment.objects.select_for_update().filter(pk=payment_id, command=command, status=CommandPaymentStatus.APPLIED).first()
    if not original:
        raise ValidationError({'payment': 'Pagamento aplicado não encontrado.'})
    if CommandPayment.objects.select_for_update().filter(reversal_of=original).exists():
        raise CommandConflict('payment_already_reversed', 'Este pagamento já foi estornado.')
    reversal = CommandPayment.objects.create(company=command.company, branch=command.branch, command=command,
        payment_method=original.payment_method, amount=original.amount, received_amount=original.received_amount,
        change_amount=original.change_amount, cash_session=original.cash_session, operator=user,
        status=CommandPaymentStatus.REVERSED, idempotency_key=idempotency_key, reversal_of=original, reversal_reason=reason.strip())
    audit_log(actor=user, action='command.payment.reverse', obj=reversal, company=command.company, branch=command.branch,
              after={
                  'command_id': command.pk,
                  'reversal_of_id': original.pk,
                  'reason': reversal.reversal_reason,
                  'amount': str(reversal.amount),
                  'cash_session_id': reversal.cash_session_id,
              },
              metadata={'idempotency_key': str(idempotency_key), 'support_session': str(support_session.pk) if support_session else None})
    return reversal


def _operation_metadata(operation, support_session):
    return {
        'idempotency_key': str(operation.idempotency_key),
        'operation_reference': str(operation.pk),
        'support_session': str(support_session.pk) if support_session else None,
    }


def _new_target_order(command, user, status):
    return Order.objects.create(command=command, created_by=user, status=status)


def _move_items(*, source, destination, item_requests, user, operation, support_session):
    requested = {entry['item']: entry['quantity'] for entry in item_requests}
    items = list(OrderItem.objects.select_for_update().filter(
        pk__in=requested, order__command=source,
    ).select_related('order').order_by('pk'))
    if len(items) != len(requested):
        raise ValidationError({'items': 'Um ou mais itens não pertencem à comanda de origem.'})
    orders = {}
    moved_ids = []
    for item in items:
        quantity = requested[item.pk]
        if quantity > item.quantity:
            raise ValidationError({'items': f'A quantidade do item {item.pk} excede o disponível.'})
        if item.status == OrderItemStatus.CANCELLED:
            raise CommandConflict('item_cancelled', 'Itens cancelados não podem ser transferidos.')
        if quantity < item.quantity and item.status == OrderItemStatus.CONFIRMED:
            raise CommandConflict(
                'confirmed_partial_transfer_unsupported',
                'Transferência parcial de item confirmado não é suportada: ela dividiria movimentos de estoque e estornos vinculados ao item original.',
            )
        target_order = orders.get(item.status)
        if target_order is None:
            target_order = _new_target_order(
                destination, user,
                OrderStatus.CONFIRMED if item.status == OrderItemStatus.CONFIRMED else OrderStatus.DRAFT,
            )
            orders[item.status] = target_order
        before = model_snapshot(item, ('order_id', 'quantity', 'status'))
        if quantity == item.quantity:
            # Retaining this row preserves confirmed stock-movement and sale traceability.
            item.order = target_order
            item.save(update_fields=('order', 'updated_at'))
            moved_ids.append(item.pk)
            after = model_snapshot(item, ('order_id', 'quantity', 'status'))
        else:
            item.quantity -= quantity
            item.save(update_fields=('quantity', 'updated_at'))
            clone = OrderItem.objects.create(
                order=target_order, product=item.product, quantity=quantity,
                product_name=item.product_name, internal_code=item.internal_code, unit=item.unit,
                unit_price=item.unit_price, base_unit_price=item.base_unit_price,
                modifier_unit_total=item.modifier_unit_total, modifier_snapshot=item.modifier_snapshot,
                unit_cost=item.unit_cost, component_cost_snapshot=item.component_cost_snapshot,
                status=OrderItemStatus.PENDING,
            )
            moved_ids.append(clone.pk)
            after = {
                'source': model_snapshot(item, ('order_id', 'quantity', 'status')),
                'transferred_item_id': clone.pk,
                'transferred_quantity': str(quantity),
            }
        audit_log(
            actor=user, action='command.item_transfer', obj=item,
            company=source.company, branch=source.branch, before=before, after=after,
            metadata={**_operation_metadata(operation, support_session), 'destination_command_id': destination.pk},
        )
    return moved_ids


@transaction.atomic
def transfer_command_table(*, command, table_id, user, idempotency_key, support_session=None):
    branch = Branch.objects.select_for_update().select_related('company').get(pk=command.branch_id)
    _validate_branch_active(branch)
    require_branch_feature(branch, 'commands')
    source, _ = _lock_open_commands(command.pk)
    operation, replayed = _start_command_operation(
        branch=branch, operation_type=CommandOperationType.TRANSFER, idempotency_key=idempotency_key,
        payload={'command': source.pk, 'table': table_id},
    )
    if replayed:
        return source, True
    table = None
    if table_id is not None:
        require_branch_feature(branch, 'tables')
        table = Table.objects.select_for_update().filter(pk=table_id).first()
        if not table:
            raise ValidationError({'table': 'Mesa não encontrada.'})
        if table.branch_id != branch.pk or table.status != TableStatus.ACTIVE:
            raise CommandConflict('table_invalid', 'A mesa de destino deve estar ativa na filial atual.')
    before = model_snapshot(source, ('table_id', 'status'))
    source.table = table
    source.save(update_fields=('table', 'updated_at'))
    operation.result = {'command_id': source.pk}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user, action='command.transfer', obj=source, company=source.company, branch=branch,
        before=before, after=model_snapshot(source, ('table_id', 'status')),
        metadata=_operation_metadata(operation, support_session),
    )
    return source, False


@transaction.atomic
def transfer_command_items(*, command, destination_command_id, items, user, idempotency_key, support_session=None):
    branch = Branch.objects.select_for_update().select_related('company').get(pk=command.branch_id)
    _validate_branch_active(branch)
    require_branch_feature(branch, 'commands')
    source, destination = _lock_open_commands(command.pk, destination_command_id)
    if source.pk == destination.pk:
        raise CommandConflict('same_command', 'A comanda de destino deve ser diferente da origem.')
    _assert_no_applied_payments(source, destination)
    operation, replayed = _start_command_operation(
        branch=branch, operation_type=CommandOperationType.TRANSFER_ITEMS, idempotency_key=idempotency_key,
        payload={'command': source.pk, 'destination_command': destination.pk, 'items': items},
    )
    if replayed:
        return destination, operation.result.get('item_ids', []), True
    moved_ids = _move_items(
        source=source, destination=destination, item_requests=items, user=user,
        operation=operation, support_session=support_session,
    )
    _assert_paid_not_above_total(source)
    operation.result = {'command_id': destination.pk, 'item_ids': moved_ids}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user, action='command.transfer_items', obj=source, company=source.company, branch=branch,
        before={'item_ids': [entry['item'] for entry in items]}, after={'destination_command_id': destination.pk, 'item_ids': moved_ids},
        metadata=_operation_metadata(operation, support_session),
    )
    return destination, moved_ids, False


@transaction.atomic
def merge_commands(*, command, source_command_id, user, idempotency_key, support_session=None):
    branch = Branch.objects.select_for_update().select_related('company').get(pk=command.branch_id)
    _validate_branch_active(branch)
    require_branch_feature(branch, 'commands')
    source, destination = _lock_open_commands(source_command_id, command.pk)
    if source.pk == destination.pk:
        raise CommandConflict('same_command', 'A comanda de origem deve ser diferente do destino.')
    if source.customer_id and destination.customer_id and source.customer_id != destination.customer_id:
        raise CommandConflict('customer_conflict', 'Não é possível mesclar comandas com clientes diferentes.')
    _assert_no_applied_payments(source, destination)
    operation, replayed = _start_command_operation(
        branch=branch, operation_type=CommandOperationType.MERGE, idempotency_key=idempotency_key,
        payload={'command': destination.pk, 'source_command': source.pk},
    )
    if replayed:
        return destination, True
    orders = list(Order.objects.select_for_update().filter(command=source).order_by('pk'))
    if not orders:
        raise CommandConflict('source_empty', 'A comanda de origem não possui pedidos para mesclar.')
    before = {
        'source_command_id': source.pk,
        'source_status': source.status,
        'order_ids': [order.pk for order in orders],
    }
    for order in orders:
        order.command = destination
        order.save(update_fields=('command', 'updated_at'))
    if destination.customer_id is None and source.customer_id is not None:
        destination.customer_id = source.customer_id
        destination.save(update_fields=('customer', 'updated_at'))
    _assert_paid_not_above_total(source)
    source.status = CommandStatus.CLOSED
    source.closed_at = timezone.now()
    source.closed_by = user
    source.save(update_fields=('status', 'closed_at', 'closed_by', 'updated_at'))
    operation.result = {'command_id': destination.pk, 'source_command_id': source.pk}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user, action='command.merge', obj=destination, company=destination.company, branch=branch,
        before=before,
        after={
            'order_ids': [order.pk for order in orders],
            'source_status': source.status,
            'source_closed_at': str(source.closed_at),
        },
        metadata=_operation_metadata(operation, support_session),
    )
    return destination, False


@transaction.atomic
def split_command(*, command, items, table_id, identifier, user, idempotency_key, support_session=None):
    branch = Branch.objects.select_for_update().select_related('company').get(pk=command.branch_id)
    _validate_branch_active(branch)
    require_branch_feature(branch, 'commands')
    source, _ = _lock_open_commands(command.pk)
    _assert_no_applied_payments(source)
    operation, replayed = _start_command_operation(
        branch=branch, operation_type=CommandOperationType.SPLIT, idempotency_key=idempotency_key,
        payload={'command': source.pk, 'items': items, 'table': table_id, 'identifier': identifier},
    )
    if replayed:
        return Command.objects.get(pk=operation.result['command_id']), True
    table = None
    if table_id is not None:
        require_branch_feature(branch, 'tables')
        table = Table.objects.select_for_update().filter(pk=table_id).first()
        if not table:
            raise ValidationError({'table': 'Mesa não encontrada.'})
        if table.branch_id != branch.pk or table.status != TableStatus.ACTIVE:
            raise CommandConflict('table_invalid', 'A mesa de destino deve estar ativa na filial atual.')
    destination = Command.objects.create(
        company=branch.company, branch=branch, table=table,
        command_number=f'C{Command.objects.filter(branch=branch).count() + 1:06d}',
        identifier=identifier, customer=source.customer, opened_by=user,
    )
    moved_ids = _move_items(
        source=source, destination=destination, item_requests=items, user=user,
        operation=operation, support_session=support_session,
    )
    _assert_paid_not_above_total(source)
    operation.result = {'command_id': destination.pk, 'item_ids': moved_ids}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user, action='command.split', obj=destination, company=destination.company, branch=branch,
        before={'source_command_id': source.pk, 'item_ids': [entry['item'] for entry in items]},
        after=model_snapshot(destination, ('table_id', 'command_number', 'identifier', 'status')),
        metadata=_operation_metadata(operation, support_session),
    )
    return destination, False


def _resolve_stock_requirements_for_product(product, quantity, branch, modifier_snapshot=None):
    requirements = {}
    content_requirements = {}
    component_snapshots = []
    if product.inventory_behavior == InventoryBehavior.NONE:
        apply_modifier_stock_requirements(
            requirements, product=product, quantity=quantity,
            modifier_snapshot=modifier_snapshot,
        )
        return requirements, content_requirements, component_snapshots
    if product.inventory_behavior == InventoryBehavior.DIRECT:
        requirements[product.pk] = requirements.get(product.pk, Decimal('0')) + quantity
        apply_modifier_stock_requirements(
            requirements, product=product, quantity=quantity,
            modifier_snapshot=modifier_snapshot,
        )
        return requirements, content_requirements, component_snapshots
    normal_rows = ProductComponent.objects.filter(
        parent_product=product
    ).select_related('component_product').order_by('component_product_id')
    fraction_rows = ProductFractionComponent.objects.filter(
        parent_product=product
    ).select_related('component_product').order_by('component_product_id')
    cost_map = branch_cost_map(branch, set(
        [row.component_product_id for row in list(normal_rows) + list(fraction_rows)]
    ))
    for row in normal_rows:
        comp = row.component_product
        req_qty = row.quantity * quantity
        requirements[comp.pk] = requirements.get(comp.pk, Decimal('0')) + req_qty
        comp_cost = cost_map.get(comp.pk, comp.cost)
        component_snapshots.append({
            'product': comp.pk, 'product_name': comp.name,
            'internal_code': comp.internal_code, 'unit': comp.unit,
            'quantity_per_unit': str(row.quantity),
            'consumed_quantity': str(req_qty),
            'unit_cost': str(comp_cost), 'unit_cost_contribution': str(comp_cost * req_qty),
        })
    for row in fraction_rows:
        comp = row.component_product
        try:
            config = comp.fraction_config
        except Exception:
            config = None
        if not config or not config.tracking_active:
            raise ValidationError({
                'product': f'O componente fracionado {comp.name} não possui rastreamento ativo.'
            })
        content_qty = row.content_quantity * quantity
        content_requirements[comp.pk] = content_requirements.get(comp.pk, Decimal('0')) + content_qty
        req_qty = (content_qty / config.package_content).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )
        requirements[comp.pk] = requirements.get(comp.pk, Decimal('0')) + req_qty
        comp_cost = cost_map.get(comp.pk, comp.cost)
        component_snapshots.append({
            'product': comp.pk, 'product_name': comp.name,
            'internal_code': comp.internal_code, 'unit': comp.unit,
            'quantity_per_unit': str(req_qty),
            'consumed_quantity': str(content_qty),
            'unit_cost': str(comp_cost), 'unit_cost_contribution': str(comp_cost * req_qty),
        })
    apply_modifier_stock_requirements(
        requirements, product=product, quantity=quantity,
        modifier_snapshot=modifier_snapshot,
    )
    return requirements, content_requirements, component_snapshots


def _validate_branch_active(branch):
    if branch.company.status != Status.ACTIVE:
        raise ValidationError({'branch': 'A empresa deve estar ativa.'})
    if branch.status != Status.ACTIVE:
        raise ValidationError({'branch': 'A filial deve estar ativa.'})


def _get_locked_stock(product_id, branch):
    return materialize_stock(product=product_id, branch=branch)


@transaction.atomic
def create_table(*, branch, name, seats=0, user):
    branch = Branch.objects.select_for_update().select_related('company').get(pk=branch.pk)
    _validate_branch_active(branch)
    require_branch_feature(branch, 'tables')
    table = Table.objects.create(branch=branch, name=name, seats=seats)
    audit_log(
        actor=user, action='table.create', obj=table,
        company=branch.company, branch=branch,
        after=model_snapshot(table, ('branch_id', 'name', 'seats', 'status')),
    )
    return table


@transaction.atomic
def batch_create_tables(*, branch, prefix, start, end, seats=0, user):
    branch = Branch.objects.select_for_update().select_related('company').get(pk=branch.pk)
    _validate_branch_active(branch)
    require_branch_feature(branch, 'tables')
    created = []
    operation_ref = str(__import__('uuid').uuid4())
    for number in range(start, end + 1):
        name = f'{prefix}{number}' if prefix else str(number)
        table, created_flag = Table.objects.get_or_create(
            branch=branch, name=name,
            defaults={'seats': seats, 'status': TableStatus.ACTIVE},
        )
        if created_flag:
            created.append(table)
            audit_log(
                actor=user, action='table.create', obj=table,
                company=branch.company, branch=branch,
                after=model_snapshot(table, ('branch_id', 'name', 'seats', 'status')),
                metadata={'batch': True, 'operation_reference': operation_ref},
            )
    return created


@transaction.atomic
def open_command(*, branch, user, table=None, identifier='', customer_id=None, support_session=None):
    branch_obj = Branch.objects.select_for_update().select_related('company').get(pk=branch.pk)
    _validate_branch_active(branch_obj)
    require_branch_feature(branch_obj, 'commands')
    table_obj = None
    if table is not None:
        require_branch_feature(branch_obj, 'tables')
        table_obj = Table.objects.select_for_update().get(pk=table.pk)
        if table_obj.branch_id != branch_obj.pk:
            raise ValidationError({'table': 'A mesa deve pertencer à filial.'})
        if table_obj.status != TableStatus.ACTIVE:
            raise ValidationError({'table': 'A mesa deve estar ativa.'})
    customer = None
    if customer_id is not None:
        customer = Customer.objects.select_for_update().filter(pk=customer_id).first()
        if not customer or customer.company_id != branch_obj.company_id or customer.status != Status.ACTIVE:
            raise ValidationError({'customer': 'Cliente inválido, inativo ou fora da empresa.'})
    count = Command.objects.filter(branch=branch_obj).count()
    command_number = f'C{count + 1:06d}'
    command = Command.objects.create(
        company=branch_obj.company,
        branch=branch_obj,
        table=table_obj,
        customer=customer,
        command_number=command_number,
        identifier=identifier,
        opened_by=user,
    )
    audit_log(
        actor=user, action='command.open', obj=command,
        company=branch_obj.company, branch=branch_obj,
        after=model_snapshot(command, (
            'company_id', 'branch_id', 'table_id', 'customer_id', 'command_number', 'identifier', 'status', 'opened_by_id'
        )),
        metadata={'support_session': str(support_session.pk) if support_session else None},
    )
    return command


@transaction.atomic
def set_command_customer(*, command, customer_id, user, support_session=None):
    command = Command.objects.select_for_update().select_related('branch__company').get(pk=command.pk)
    if command.status != CommandStatus.OPEN:
        raise ValidationError({'command': 'A comanda deve estar aberta.'})
    customer = None
    if customer_id is not None:
        customer = Customer.objects.select_for_update().filter(pk=customer_id).first()
        if not customer or customer.company_id != command.company_id or customer.status != Status.ACTIVE:
            raise ValidationError({'customer': 'Cliente inválido, inativo ou fora da empresa.'})
    before = model_snapshot(command, ('customer_id',))
    command.customer = customer
    command.save(update_fields=('customer', 'updated_at'))
    audit_log(actor=user, action='command.set_customer', obj=command, company=command.company,
              branch=command.branch, before=before, after=model_snapshot(command, ('customer_id',)),
              metadata={'support_session': str(support_session.pk) if support_session else None})
    return command


@transaction.atomic
def add_order_item(*, command, user, product_id, quantity, modifiers=None,
                   support_session=None, order=None):
    command = Command.objects.select_for_update().get(pk=command.pk)
    require_branch_feature(command.branch, 'commands')
    if command.status != CommandStatus.OPEN:
        raise ValidationError({'command': 'A comanda deve estar aberta.'})
    try:
        product = Product.objects.select_for_update().get(pk=product_id)
    except Product.DoesNotExist as error:
        raise ValidationError({'product': 'Produto não encontrado.'}) from error
    if product.company_id != command.company_id:
        raise ValidationError({'product': 'Produto não pertence à empresa da comanda.'})
    if product.status != Status.ACTIVE:
        raise ValidationError({'product': 'Produto inativo.'})
    if product.archived_at is not None:
        raise ValidationError({'product': 'Produto arquivado.'})
    if not product.is_sellable:
        raise ValidationError({'product': 'Produto não vendável.'})
    if not product.available_command:
        raise ValidationError({'product': 'Produto não disponível para comanda.'})
    branch_config = ProductBranchConfig.objects.filter(
        branch=command.branch, product=product
    ).first()
    if branch_config is None or not branch_config.is_available or branch_config.available_command is False:
        raise ValidationError({'product': 'Produto indisponível para Comanda nesta filial.'})
    if product.unit == Unit.UNIT and quantity != quantity.to_integral_value():
        raise ValidationError({'quantity': 'Produto UN exige quantidade inteira.'})

    modifier_total, modifier_snapshot_data = resolve_modifiers(
        product, modifiers or [], product.company_id,
        branch=command.branch, item_quantity=quantity,
    )

    price_overrides = branch_price_map(command.branch, [product.pk])
    base_price = price_overrides.get(product.pk, product.sale_price)
    unit_price = (base_price + modifier_total).quantize(CENT, rounding=ROUND_HALF_UP)

    cost_map = branch_cost_map(command.branch, [product.pk])
    unit_cost = cost_map.get(product.pk, product.cost).quantize(CENT, rounding=ROUND_HALF_UP)

    if order is None:
        order = Order.objects.create(command=command, created_by=user)

    item = OrderItem.objects.create(
        order=order, product=product, quantity=quantity,
        product_name=product.name, internal_code=product.internal_code or '',
        unit=product.unit, unit_price=unit_price,
        base_unit_price=base_price, modifier_unit_total=modifier_total,
        modifier_snapshot=modifier_snapshot_data, unit_cost=unit_cost,
        status=OrderItemStatus.PENDING,
    )
    audit_log(
        actor=user, action='order_item.create', obj=item,
        company=command.company, branch=command.branch,
        after=model_snapshot(item, ('product_id', 'quantity', 'unit_price', 'status')),
        metadata={
            'command_id': str(command.pk),
            'order_id': str(order.pk),
            'support_session': str(support_session.pk) if support_session else None,
        },
    )
    return item


@transaction.atomic
def confirm_order_item(*, item, user, idempotency_key, support_session=None):
    item = OrderItem.objects.select_for_update(of=('self',)).select_related(
        'order__command', 'product'
    ).get(pk=item.pk)
    command = item.order.command
    command.company = Company.objects.select_for_update().get(pk=command.company_id)
    command.branch = Branch.objects.select_for_update(of=('self',)).get(
        pk=command.branch_id, company=command.company,
    )
    command.branch.company = command.company
    require_branch_feature(command.branch, 'commands')
    if command.status != CommandStatus.OPEN:
        raise ValidationError({'command': 'A comanda deve estar aberta.'})
    if item.status == OrderItemStatus.CONFIRMED:
        return item
    if item.status != OrderItemStatus.PENDING:
        raise ValidationError({'item': 'Somente itens pendentes podem ser confirmados.'})

    _assert_consumption_limit(command, item)

    product = Product.objects.select_for_update().get(pk=item.product_id)
    item.product = product
    if product.archived_at is not None:
        raise ValidationError({'product': 'Produto arquivado.'})
    requirements, content_requirements, component_snapshots = (
        _resolve_stock_requirements_for_product(
            product, item.quantity, command.branch, item.modifier_snapshot,
        )
    )

    operation_ref = str(idempotency_key)
    locked_stocks = {}
    for product_id in sorted(requirements):
        qty = requirements[product_id]
        stock = _get_locked_stock(product_id, command.branch)
        locked_stocks[product_id] = stock
        allow_negative = _branch_allows_negative(command.branch)
        new_quantity = stock.current_quantity - qty
        if new_quantity < 0 and not allow_negative:
            raise ValidationError({
                'item': f'Estoque insuficiente para {product.name if product_id == product.pk else Product.objects.get(pk=product_id).name}.'
            })
        unit_cost_snapshot = stock.average_unit_cost if stock.average_unit_cost is not None else stock.product.cost
        content_qty = content_requirements.get(product_id)
        apply_locked_stock(
            stock=stock, quantity=-qty, user=user,
            movement_type=MovementType.SALE,
            nature=MovementNature.SALE,
            reason=f'Confirmação OrderItem {item.pk}',
            operation_reference=operation_ref,
            domain_origin=MovementDomainOrigin.ORDER,
            order_item=item,
            unit_cost_snapshot=unit_cost_snapshot,
            content_quantity=-content_qty if content_qty is not None else None,
        )

    from apps.sales.services import _reconcile_modifier_component_costs

    reconciled_snapshot = {
        'quantity': item.quantity,
        'component_cost_snapshot': component_snapshots,
        'modifier_snapshot': item.modifier_snapshot,
    }
    _reconcile_modifier_component_costs([reconciled_snapshot], locked_stocks)
    component_snapshots = reconciled_snapshot['component_cost_snapshot']

    item.status = OrderItemStatus.CONFIRMED
    item.confirmed_at = timezone.now()
    item.confirmed_by = user
    item.component_cost_snapshot = component_snapshots
    item.save(update_fields=(
        'status', 'confirmed_at', 'confirmed_by', 'component_cost_snapshot', 'updated_at',
    ))
    from apps.production.services import create_production_jobs
    create_production_jobs(
        item=item, command=command, user=user, idempotency_key=idempotency_key,
    )
    from apps.production.services import create_order_item_ticket
    create_order_item_ticket(item=item, command=command, user=user)

    order = item.order
    if order.status == OrderStatus.DRAFT:
        pending = order.items.filter(status=OrderItemStatus.PENDING).exists()
        if not pending:
            order.status = OrderStatus.CONFIRMED
            order.save(update_fields=('status', 'updated_at'))

    audit_log(
        actor=user, action='order_item.confirm', obj=item,
        company=command.company, branch=command.branch,
        after=model_snapshot(item, ('status', 'confirmed_at', 'confirmed_by_id')),
        metadata={
            'idempotency_key': str(idempotency_key),
            'operation_reference': operation_ref,
            'support_session': str(support_session.pk) if support_session else None,
        },
    )
    return item


def _branch_allows_negative(branch):
    from apps.companies.models import BranchSettings
    settings = BranchSettings.objects.filter(branch=branch).first()
    return bool(settings and settings.allow_negative_stock)


def _confirmed_consumption(command, *, table=None):
    money_field = DecimalField(max_digits=14, decimal_places=2)
    filters = Q(order__command=command)
    if table is not None:
        filters = Q(order__command__table=table, order__command__status=CommandStatus.OPEN)
    return OrderItem.objects.filter(filters, status=OrderItemStatus.CONFIRMED).aggregate(
        total=Coalesce(
            Sum(F('unit_price') * F('quantity'), output_field=money_field),
            Value(Decimal('0.00'), output_field=money_field),
        )
    )['total']


def _assert_consumption_limit(command, item):
    from apps.companies.models import BranchSettings

    settings = BranchSettings.objects.select_for_update().filter(branch=command.branch).first()
    if not settings or not settings.consumption_limit_enabled:
        return
    attempt = (item.unit_price * item.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    checks = [('comanda', settings.command_consumption_limit, None)]
    if command.table_id:
        table = Table.objects.select_for_update().get(pk=command.table_id)
        checks.append(('mesa', settings.table_consumption_limit, table))
    for label, limit, table in checks:
        if limit is None:
            continue
        current = _confirmed_consumption(command, table=table)
        total = current + attempt
        if total > limit:
            raise ValidationError({'consumption_limit': (
                f'Limite de consumo da {label}: R$ {limit:.2f}. Consumo atual: '
                f'R$ {current:.2f}. Tentativa: R$ {attempt:.2f}. Excedente: R$ {total - limit:.2f}.'
            )})


@transaction.atomic
def cancel_order_item(*, item, user, idempotency_key, reason, support_session=None):
    item = OrderItem.objects.select_for_update().select_related(
        'order__command', 'product'
    ).get(pk=item.pk)
    command = item.order.command
    require_branch_feature(command.branch, 'commands')
    if command.status != CommandStatus.OPEN:
        raise ValidationError({'command': 'A comanda deve estar aberta.'})
    if item.status == OrderItemStatus.CANCELLED:
        return item
    if item.status == OrderItemStatus.PENDING:
        item.status = OrderItemStatus.CANCELLED
        item.cancelled_at = timezone.now()
        item.cancelled_by = user
        item.cancellation_reason = reason
        item.save(update_fields=(
            'status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at',
        ))
        audit_log(
            actor=user, action='order_item.cancel', obj=item,
            company=command.company, branch=command.branch,
            after=model_snapshot(item, ('status', 'cancelled_at', 'cancelled_by_id')),
            metadata={
                'idempotency_key': str(idempotency_key),
                'support_session': str(support_session.pk) if support_session else None,
            },
        )
        return item
    if item.status != OrderItemStatus.CONFIRMED:
        raise ValidationError({
            'item': 'Somente itens confirmados ou pendentes podem ser cancelados.'
        })

    remaining_items = list(OrderItem.objects.filter(
        order__command=command, status=OrderItemStatus.CONFIRMED,
    ).exclude(pk=item.pk).select_related('product__category').order_by('id'))
    _assert_paid_not_above_total(command, order_items=remaining_items)

    original_movements = StockMovement.objects.filter(
        order_item=item,
        movement_type__in=(MovementType.SALE, MovementType.EXIT),
        original_movement__isnull=True,
    ).select_for_update()
    for original in original_movements:
        already_reversed = StockMovement.objects.select_for_update().filter(
            original_movement=original
        ).exists()
        if already_reversed:
            raise ValidationError({'item': 'Este item já foi estornado.'})
        stock = Stock.objects.select_for_update().get(pk=original.stock_id)
        apply_locked_stock(
            stock=stock, quantity=-original.quantity, user=user,
            movement_type=MovementType.SALE_CANCELLATION,
            nature=MovementNature.CANCELLATION,
            reason=f'Cancelamento OrderItem {item.pk}',
            operation_reference=str(idempotency_key),
            original_movement=original,
            domain_origin=MovementDomainOrigin.ORDER_CANCELLATION,
            order_item=item,
        )

    item.status = OrderItemStatus.CANCELLED
    item.cancelled_at = timezone.now()
    item.cancelled_by = user
    item.cancellation_reason = reason
    item.save(update_fields=(
        'status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at',
    ))
    from apps.production.services import create_cancellation_jobs
    create_cancellation_jobs(
        item=item, command=command, user=user, idempotency_key=idempotency_key, reason=reason,
    )
    from apps.production.services import cancel_ticket_for_source
    cancel_ticket_for_source(source_field='source_order_item', item=item, user=user)
    audit_log(
        actor=user, action='order_item.cancel', obj=item,
        company=command.company, branch=command.branch,
        after=model_snapshot(item, ('status', 'cancelled_at', 'cancelled_by_id')),
        metadata={
            'idempotency_key': str(idempotency_key),
            'support_session': str(support_session.pk) if support_session else None,
        },
    )
    return item


@transaction.atomic
def finalize_command(*, command, user, idempotency_key, cash_session, payments, seller_user=None,
                     discount=Decimal('0.00'), discount_authorization=None,
                     service_fee_waived=False, service_fee_authorization=None,
                     support_session=None):
    from apps.sales.models import SaleStatus, OperationType

    command = Command.objects.select_for_update().get(pk=command.pk)
    require_branch_feature(command.branch, 'commands')
    if command.sale_id is not None:
        existing_sale = command.sale
        if existing_sale.idempotency_key == idempotency_key:
            return command
        raise ValidationError({'command': 'Esta comanda já foi finalizada.'})
    if command.status != CommandStatus.OPEN:
        raise ValidationError({'command': 'A comanda deve estar aberta.'})

    if OrderItem.objects.filter(
        order__command=command, status=OrderItemStatus.PENDING
    ).exists():
        raise ValidationError({
            'items': 'Confirme ou cancele todos os itens pendentes antes de fechar a comanda.'
        })

    confirmed_items = list(
        OrderItem.objects.filter(
            order__command=command, status=OrderItemStatus.CONFIRMED
        ).select_related('product').order_by('id')
    )
    if not confirmed_items:
        raise ValidationError({'items': 'A comanda não possui itens confirmados.'})

    branch = command.branch
    _validate_branch_active(branch)

    seller_user_obj = eligible_branch_users(branch, 'sales.create').filter(pk=user.pk).first()
    if seller_user is not None:
        seller_user_obj = eligible_branch_users(branch, 'sales.create').filter(
            pk=seller_user
        ).first()
    if not seller_user_obj:
        raise ValidationError({
            'seller_user': 'Selecione um atendente com acesso ativo para venda nesta filial.'
        })

    sale_items = []
    for item in confirmed_items:
        sale_items.append({
            'product': item.product_id,
            'quantity': str(item.quantity),
            'modifiers': [
                {
                    'option': modifier['option_id'],
                    'quantity': modifier['selected_quantity'],
                }
                for modifier in item.modifier_snapshot or []
            ],
            'discount': '0.00',
        })

    # `reversal__isnull` uses a nullable reverse join; only the immutable ledger
    # rows need locking, otherwise PostgreSQL rejects FOR UPDATE on that join.
    ledger_payments = list(CommandPayment.objects.select_for_update(of=('self',)).select_related('payment_method').filter(
        command=command, status=CommandPaymentStatus.APPLIED, reversal__isnull=True,
    ).order_by('pk'))
    ledger_cash_sessions = {
        payment.cash_session_id for payment in ledger_payments
        if payment.payment_method.code == PaymentMethodCode.CASH
    }
    final_cash_session_id = cash_session.pk if hasattr(cash_session, 'pk') else cash_session
    if ledger_cash_sessions and ledger_cash_sessions != {final_cash_session_id}:
        raise CommandConflict(
            'cash_session_mismatch',
            'Pagamentos parciais em dinheiro devem ser finalizados na mesma sessão de caixa em que foram registrados.',
        )
    ledger_total = sum((payment.amount for payment in ledger_payments), Decimal('0.00'))
    if ledger_payments and (
        strict_decimal(discount, field='discount', decimal_places=2, max_digits=14)
        != command.checkout_discount
        or bool(service_fee_waived) != command.checkout_service_fee_waived
    ):
        raise CommandConflict(
            'checkout_context_mismatch',
            'A finalização deve usar o desconto e a taxa de serviço definidos no primeiro pagamento.',
        )
    normalized_payments = []
    for payment in ledger_payments:
        normalized_payments.append({
            'payment_method': payment.payment_method_id,
            'amount': payment.amount,
            'received_amount': payment.received_amount,
        })
    for payment in payments:
        normalized_payments.append({
            'payment_method': payment.get('payment_method') or payment.get('payment_method_id'),
            'amount': payment.get('amount'),
            'received_amount': payment.get('received_amount'),
        })

    financial_state = CommandFinancialState.calculate(
        command=command, order_items=confirmed_items, seller_user=seller_user_obj,
        discount=discount, service_fee_waived=service_fee_waived, lock=True,
    )
    if ledger_total > financial_state.total_due:
        raise CommandConflict(
            'command_paid_exceeds_final_total',
            f'O total final de R$ {financial_state.total_due:.2f} é menor que os R$ {ledger_total:.2f} já pagos. Estorne pagamentos ou ajuste a finalização.',
        )
    sale = finalize_sale(
        branch=branch,
        user=user,
        operation_type=OperationType.SALE,
        cash_session=cash_session,
        items=sale_items,
        payments=normalized_payments,
        discount=discount,
        discount_authorization=discount_authorization,
        service_fee_waived=service_fee_waived,
        service_fee_authorization=service_fee_authorization,
        idempotency_key=idempotency_key,
        channel=SalesChannel.COMMAND,
        seller_user=seller_user_obj,
        customer=command.customer,
        confirmed_order_items=confirmed_items,
        internal_permission_code='commands.finalize',
        precomputed_financials=financial_state.preview,
        payment_sources=[*ledger_payments, *([None] * len(payments))],
    )

    command.status = CommandStatus.CLOSED
    command.closed_at = timezone.now()
    command.closed_by = user
    command.sale = sale
    command.save(update_fields=('status', 'closed_at', 'closed_by', 'sale', 'updated_at'))

    audit_log(
        actor=user, action='command.finalize', obj=command,
        company=command.company, branch=branch,
        after={
            **model_snapshot(command, ('status', 'closed_at', 'closed_by_id', 'sale_id')),
            'sale_id': sale.pk, 'sale_number': sale.sale_number,
            'total': str(sale.total), 'item_count': len(confirmed_items),
        },
        metadata={
            'idempotency_key': str(idempotency_key),
            'support_session': str(support_session.pk) if support_session else None,
        },
    )
    return command
