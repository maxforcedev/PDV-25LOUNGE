import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.base.audit import audit_log, model_snapshot
from apps.companies.features import require_branch_feature
from apps.companies.models import Branch, Customer, Status
from apps.inventory.models import MovementDomainOrigin, MovementNature, MovementType
from apps.inventory.materialization import materialize_stock
from apps.inventory.services import apply_locked_stock
from apps.cash.models import CashSession, CashSessionStatus
from apps.products.models import Product, ProductBranchConfig, SalesChannel, Unit
from apps.sales.models import OperationType, PaymentMethod, PaymentMethodCode
from apps.sales.services import (
    CENT, _discount_approver, _reconcile_modifier_component_costs, _service_fee_waiver,
    branch_cost_map, branch_price_map, calculate_command_preview, finalize_sale,
    resolve_modifiers, stock_requirements_for_product, strict_decimal,
)

from .models import (
    AttendanceCommand, AttendanceCommandStatus, AttendanceOperation,
    AttendanceOperationType, AttendanceOrder, AttendanceOrderItem,
    AttendanceOrderItemStatus, AttendanceOrderStatus, AttendancePayment,
    AttendancePaymentStatus, AttendanceTableGroup, AttendanceTableGroupMembership,
)


class AttendanceConflict(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str,
    ).encode()).hexdigest()


def _operator_name(user):
    return user.get_full_name().strip() or user.email


def _operation(*, branch, operation_type, idempotency_key, payload):
    fingerprint = _fingerprint(payload)
    operation = AttendanceOperation.objects.select_for_update().filter(
        branch=branch, operation_type=operation_type, idempotency_key=idempotency_key,
    ).first()
    if operation:
        if operation.payload_fingerprint != fingerprint:
            raise AttendanceConflict(
                'idempotency_key_conflict',
                'A chave de idempotência já foi usada com outros dados.',
            )
        return operation, True
    return AttendanceOperation.objects.create(
        company=branch.company, branch=branch, operation_type=operation_type,
        idempotency_key=idempotency_key, payload_fingerprint=fingerprint,
    ), False


def _active_branch(branch):
    branch = Branch.objects.select_for_update().select_related('company').get(pk=branch.pk)
    if branch.status != Status.ACTIVE or branch.company.status != Status.ACTIVE:
        raise ValidationError({'branch': 'A empresa e a filial devem estar ativas.'})
    return branch


def _next_number(branch):
    return f'A{AttendanceCommand.objects.filter(branch=branch).count() + 1:06d}'


def _customer(branch, customer_id):
    if customer_id is None:
        return None
    customer = Customer.objects.select_for_update().filter(pk=customer_id).first()
    if not customer or customer.company_id != branch.company_id or customer.status != Status.ACTIVE:
        raise ValidationError({'customer': 'Cliente inválido, inativo ou fora da empresa.'})
    return customer


def _command_reference(command):
    return {
        'id': command.pk,
        'number': command.number,
        'table_id': command.table_id,
        'status': command.status,
    }


def _audit_metadata(metadata=None, **values):
    return {**(metadata or {}), **values}


@transaction.atomic
def open_table(*, branch, table_id, user, idempotency_key, people_count=None, identifier='', notes='', customer_id=None, audit_metadata=None):
    """Open exactly one primary POS-5 command for a physical table."""
    from apps.commands.models import Command, CommandStatus, Table, TableStatus

    branch = _active_branch(branch)
    require_branch_feature(branch, 'tables')
    require_branch_feature(branch, 'commands')
    operation, replayed = _operation(
        branch=branch, operation_type=AttendanceOperationType.OPEN_TABLE,
        idempotency_key=idempotency_key,
        payload={
            'table': table_id, 'people_count': people_count, 'identifier': identifier,
            'notes': notes, 'customer': customer_id,
        },
    )
    if replayed:
        return AttendanceCommand.objects.get(pk=operation.result['command_id']), True
    table = Table.objects.select_for_update().filter(
        pk=table_id, branch=branch, status=TableStatus.ACTIVE,
    ).first()
    if table is None:
        raise AttendanceConflict('table_not_found', 'Mesa não encontrada na filial atual.')
    if Command.objects.select_for_update().filter(table=table, status=CommandStatus.OPEN).exists():
        raise AttendanceConflict(
            'table_in_legacy_use',
            'A mesa possui atendimento aberto no fluxo legado e não pode ser aberta no POS agora.',
        )
    existing = AttendanceCommand.objects.select_for_update().filter(
        table=table, is_primary=True, status=AttendanceCommandStatus.OPEN,
    ).first()
    if existing:
        operation.result = {'command_id': existing.pk}
        operation.save(update_fields=('result', 'updated_at'))
        return existing, True
    customer = _customer(branch, customer_id)
    command = AttendanceCommand.objects.create(
        company=branch.company, branch=branch, table=table, is_primary=True,
        number=_next_number(branch), identifier=identifier, notes=notes,
        people_count=people_count, customer=customer, opened_by=user,
        opened_by_name_snapshot=_operator_name(user), table_name_snapshot=table.name,
        customer_name_snapshot=customer.name if customer else '',
    )
    operation.result = {'command_id': command.pk}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user, action='attendance.table.open', obj=command,
        company=branch.company, branch=branch,
        after=model_snapshot(command, ('table_id', 'number', 'is_primary', 'people_count', 'status')),
        metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)),
    )
    return command, False


@transaction.atomic
def open_command(*, branch, user, idempotency_key, identifier='', customer_id=None, table_id=None,
                 people_count=None, notes='', audit_metadata=None):
    from apps.commands.models import Table, TableStatus

    branch = _active_branch(branch)
    require_branch_feature(branch, 'commands')
    operation, replayed = _operation(
        branch=branch, operation_type=AttendanceOperationType.OPEN_COMMAND,
        idempotency_key=idempotency_key,
        payload={
            'table': table_id, 'people_count': people_count, 'identifier': identifier,
            'notes': notes, 'customer': customer_id,
        },
    )
    if replayed:
        return AttendanceCommand.objects.get(pk=operation.result['command_id']), True
    table = None
    if table_id is not None:
        require_branch_feature(branch, 'tables')
        table = Table.objects.select_for_update().filter(
            pk=table_id, branch=branch, status=TableStatus.ACTIVE,
        ).first()
        if table is None:
            raise AttendanceConflict('table_not_found', 'Mesa não encontrada na filial atual.')
        if not AttendanceCommand.objects.filter(
            table=table, is_primary=True, status=AttendanceCommandStatus.OPEN,
        ).exists():
            raise AttendanceConflict(
                'table_not_open',
                'Abra a mesa antes de criar uma comanda adicional.',
            )
    customer = _customer(branch, customer_id)
    command = AttendanceCommand.objects.create(
        company=branch.company, branch=branch, table=table, number=_next_number(branch),
        identifier=identifier, people_count=people_count, notes=notes, customer=customer,
        opened_by=user, opened_by_name_snapshot=_operator_name(user),
        table_name_snapshot=table.name if table else '',
        customer_name_snapshot=customer.name if customer else '',
    )
    operation.result = {'command_id': command.pk}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user, action='attendance.command.open', obj=command,
        company=branch.company, branch=branch,
        after=model_snapshot(command, ('table_id', 'number', 'identifier', 'is_primary', 'status')),
        metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)),
    )
    return command, False


def financial_state(command, *, lock=False, discount=None, service_fee_waived=None):
    items = AttendanceOrderItem.objects.filter(
        order__command=command, status=AttendanceOrderItemStatus.CONFIRMED,
    ).select_related('product__category').order_by('id')
    if lock:
        items = items.select_for_update()
    preview = calculate_command_preview(
        branch=command.branch, order_items=list(items),
        discount=command.checkout_discount if discount is None else discount,
        service_fee_waived=(
            command.checkout_service_fee_waived
            if service_fee_waived is None else service_fee_waived
        ),
        lock=lock, include_internal_snapshots=True,
    )
    payments = AttendancePayment.objects.filter(
        command=command, status=AttendancePaymentStatus.APPLIED, reversal__isnull=True,
    )
    if lock:
        payments = payments.select_for_update(of=('self',))
    paid = payments.aggregate(total=Coalesce(
        Sum('amount'), Value(Decimal('0.00'), output_field=DecimalField(max_digits=14, decimal_places=2)),
    ))['total']
    return preview, paid, max(preview['total'] - paid, Decimal('0.00'))


def command_summary(command):
    preview, paid, remaining = financial_state(command)
    return {
        'subtotal': f"{preview['subtotal']:.2f}",
        'promotion_discount': f"{preview['promotion_discount_total']:.2f}",
        'manual_discount': f"{preview['discount']:.2f}",
        'service_fee': f"{preview['service_fee_amount']:.2f}",
        'total_due': f"{preview['total']:.2f}",
        'paid_total': f'{paid:.2f}',
        'remaining_balance': f'{remaining:.2f}',
    }


@transaction.atomic
def add_order_items(*, command, user, items, idempotency_key, audit_metadata=None):
    command = AttendanceCommand.objects.select_for_update().select_related('branch__company').get(pk=command.pk)
    require_branch_feature(command.branch, 'commands')
    if command.status != AttendanceCommandStatus.OPEN:
        raise AttendanceConflict('command_closed', 'A comanda deve estar aberta.')
    operation, replayed = _operation(
        branch=command.branch, operation_type=AttendanceOperationType.ADD_ITEMS,
        idempotency_key=idempotency_key,
        payload={'command': command.pk, 'items': items},
    )
    if replayed:
        return None, list(AttendanceOrderItem.objects.filter(
            pk__in=operation.result['item_ids'],
        ).order_by('id')), True
    order = AttendanceOrder.objects.create(command=command, created_by=user)
    created = []
    for entry in items:
        product = Product.objects.select_for_update().filter(pk=entry['product']).first()
        if not product or product.company_id != command.company_id:
            raise ValidationError({'product': 'Produto não encontrado na empresa da comanda.'})
        config = ProductBranchConfig.objects.filter(branch=command.branch, product=product).first()
        if not (
            product.status == Status.ACTIVE and product.archived_at is None and product.is_sellable
            and product.available_command and config and config.is_available
            and config.available_command is not False
        ):
            raise ValidationError({'product': 'Produto indisponível para Comanda nesta filial.'})
        quantity = strict_decimal(entry['quantity'], field='quantity', decimal_places=3, max_digits=14)
        if quantity <= 0 or (product.unit == Unit.UNIT and quantity != quantity.to_integral_value()):
            raise ValidationError({'quantity': 'Quantidade inválida para o produto.'})
        modifier_total, modifiers = resolve_modifiers(
            product, entry.get('modifiers', []), command.company_id,
            branch=command.branch, item_quantity=quantity,
        )
        base_price = branch_price_map(command.branch, [product.pk]).get(product.pk, product.sale_price)
        unit_cost = branch_cost_map(command.branch, [product.pk]).get(
            product.pk, product.cost,
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        created.append(AttendanceOrderItem.objects.create(
            order=order, product=product, quantity=quantity, product_name=product.name,
            internal_code=product.internal_code or '', category_id_snapshot=product.category_id,
            category_name_snapshot=product.category.name if product.category_id else '', unit=product.unit,
            base_unit_price=base_price, modifier_unit_total=modifier_total,
            unit_price=(base_price + modifier_total).quantize(CENT, rounding=ROUND_HALF_UP),
            modifier_snapshot=modifiers, notes=entry.get('notes', ''), unit_cost=unit_cost,
        ))
    audit_log(actor=user, action='attendance.order.create', obj=order, company=command.company,
              branch=command.branch, after={'command_id': command.pk, 'item_ids': [item.pk for item in created]},
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    operation.result = {'order_id': order.pk, 'item_ids': [item.pk for item in created]}
    operation.save(update_fields=('result', 'updated_at'))
    return order, created, False


@transaction.atomic
def confirm_order_item(*, item, user, idempotency_key, audit_metadata=None):
    item = AttendanceOrderItem.objects.select_for_update().select_related('order__command', 'product').get(pk=item.pk)
    command = item.order.command
    if item.status == AttendanceOrderItemStatus.CONFIRMED:
        return item
    if command.status != AttendanceCommandStatus.OPEN or item.status != AttendanceOrderItemStatus.PENDING:
        raise AttendanceConflict('item_not_confirmable', 'O item não pode ser confirmado.')
    requirements, contents, component_snapshots = stock_requirements_for_product(
        item.product, item.quantity, command.branch, item.modifier_snapshot,
    )
    stocks = {}
    for product_id, quantity in sorted(requirements.items()):
        stock = materialize_stock(product=product_id, branch=command.branch)
        stocks[product_id] = stock
        apply_locked_stock(
            stock=stock, quantity=-quantity, user=user, movement_type=MovementType.SALE,
            nature=MovementNature.SALE, reason=f'Confirmação AttendanceOrderItem {item.pk}',
            operation_reference=idempotency_key, domain_origin=MovementDomainOrigin.ATTENDANCE_ORDER,
            attendance_order_item=item,
            unit_cost_snapshot=stock.average_unit_cost if stock.average_unit_cost is not None else stock.product.cost,
            content_quantity=-contents[product_id] if product_id in contents else None,
        )
    snapshot = {'quantity': item.quantity, 'component_cost_snapshot': component_snapshots, 'modifier_snapshot': item.modifier_snapshot}
    _reconcile_modifier_component_costs([snapshot], stocks)
    item.status = AttendanceOrderItemStatus.CONFIRMED
    item.confirmed_at = timezone.now()
    item.confirmed_by = user
    item.component_cost_snapshot = snapshot['component_cost_snapshot']
    item.save(update_fields=('status', 'confirmed_at', 'confirmed_by', 'component_cost_snapshot', 'updated_at'))
    if not item.order.items.filter(status=AttendanceOrderItemStatus.PENDING).exists():
        item.order.status = AttendanceOrderStatus.CONFIRMED
        item.order.save(update_fields=('status', 'updated_at'))
    from apps.production.services import create_attendance_order_item_ticket, create_attendance_production_jobs
    create_attendance_production_jobs(item=item, command=command, user=user, idempotency_key=idempotency_key)
    create_attendance_order_item_ticket(item=item, command=command, user=user)
    audit_log(actor=user, action='attendance.order_item.confirm', obj=item, company=command.company,
              branch=command.branch, after=model_snapshot(item, ('status', 'confirmed_at', 'confirmed_by_id')),
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return item


@transaction.atomic
def cancel_order_item(*, item, user, reason, idempotency_key, audit_metadata=None):
    item = AttendanceOrderItem.objects.select_for_update().select_related(
        'order__command', 'product',
    ).get(pk=item.pk)
    command = item.order.command
    if item.status == AttendanceOrderItemStatus.CANCELLED:
        return item, True
    if command.status != AttendanceCommandStatus.OPEN:
        raise AttendanceConflict('command_closed', 'O item só pode ser cancelado em comanda aberta.')
    operation, replayed = _operation(
        branch=command.branch, operation_type=AttendanceOperationType.CANCEL_ITEM,
        idempotency_key=idempotency_key, payload={'item': item.pk, 'reason': reason},
    )
    if replayed:
        return item, True
    if AttendancePayment.objects.filter(
        command=command, status=AttendancePaymentStatus.APPLIED, reversal__isnull=True,
    ).exists():
        raise AttendanceConflict(
            'command_payments_cancel_unsupported',
            'Estorne os pagamentos parciais antes de cancelar itens da comanda.',
        )
    before = model_snapshot(item, ('status', 'cancelled_at', 'cancelled_by_id', 'cancellation_reason'))
    if item.status == AttendanceOrderItemStatus.CONFIRMED:
        from apps.inventory.models import StockMovement

        originals = list(StockMovement.objects.select_for_update().filter(
            attendance_order_item=item, movement_type=MovementType.SALE,
            original_movement__isnull=True,
        ).order_by('stock_id', 'pk'))
        # Stock is locked in a stable order before creating immutable reversals.
        from apps.inventory.models import Stock
        stocks = {
            stock.pk: stock for stock in Stock.objects.select_for_update().filter(
                pk__in=[movement.stock_id for movement in originals],
            ).select_related('product').order_by('product_id', 'pk')
        }
        for original in originals:
            apply_locked_stock(
                stock=stocks[original.stock_id], quantity=-original.quantity, user=user,
                movement_type=MovementType.SALE_CANCELLATION,
                reason=f'Cancelamento AttendanceOrderItem {item.pk}: {reason}',
                original_movement=original,
                domain_origin=MovementDomainOrigin.ATTENDANCE_ORDER_CANCELLATION,
                attendance_order_item=item,
                unit_cost_snapshot=(
                    original.unit_cost_snapshot
                    if original.unit_cost_snapshot is not None else original.stock.product.cost
                ),
                content_quantity=(
                    -original.content_quantity
                    if original.content_quantity is not None else None
                ),
            )
        from apps.production.services import (
            cancel_attendance_ticket_for_item, create_attendance_cancellation_jobs,
        )
        create_attendance_cancellation_jobs(
            item=item, command=command, user=user, idempotency_key=idempotency_key,
            reason=reason,
        )
        cancel_attendance_ticket_for_item(item=item, user=user)
    item.status = AttendanceOrderItemStatus.CANCELLED
    item.cancelled_at = timezone.now()
    item.cancelled_by = user
    item.cancellation_reason = (reason or '').strip()
    item.save(update_fields=(
        'status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at',
    ))
    if not item.order.items.exclude(status=AttendanceOrderItemStatus.CANCELLED).exists():
        item.order.status = AttendanceOrderStatus.CANCELLED
        item.order.save(update_fields=('status', 'updated_at'))
    operation.result = {'item_id': item.pk}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(actor=user, action='attendance.order_item.cancel', obj=item, company=command.company,
              branch=command.branch, before=before,
              after=model_snapshot(item, ('status', 'cancelled_at', 'cancelled_by_id', 'cancellation_reason')),
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return item, False


@transaction.atomic
def transfer_command(*, command, table_id, user, idempotency_key, audit_metadata=None):
    from apps.commands.models import Table, TableStatus

    command = AttendanceCommand.objects.select_for_update().select_related('branch__company').get(pk=command.pk)
    if command.status != AttendanceCommandStatus.OPEN:
        raise AttendanceConflict('command_closed', 'A comanda deve estar aberta.')
    operation, replayed = _operation(
        branch=command.branch, operation_type=AttendanceOperationType.TRANSFER_COMMAND,
        idempotency_key=idempotency_key, payload={'command': command.pk, 'table': table_id},
    )
    if replayed:
        return command, True
    table = None
    if table_id is not None:
        table = Table.objects.select_for_update().filter(
            pk=table_id, branch=command.branch, status=TableStatus.ACTIVE,
        ).first()
        if table is None:
            raise AttendanceConflict('table_not_found', 'Mesa de destino não encontrada.')
        if not AttendanceCommand.objects.filter(table=table, is_primary=True, status=AttendanceCommandStatus.OPEN).exists():
            raise AttendanceConflict('destination_table_not_open', 'Abra a mesa de destino antes da transferência.')
    if command.is_primary and AttendanceCommand.objects.filter(
        table_id=command.table_id, status=AttendanceCommandStatus.OPEN,
    ).exclude(pk=command.pk).exists():
        raise AttendanceConflict(
            'primary_command_required',
            'A mesa de origem possui outras comandas abertas e deve manter sua comanda principal.',
        )
    before = model_snapshot(command, ('table_id', 'table_name_snapshot', 'is_primary'))
    command.table = table
    command.table_name_snapshot = table.name if table else ''
    if command.is_primary:
        # Its former table becomes free; the destination already has its own primary command.
        command.is_primary = False
    command.save(update_fields=('table', 'table_name_snapshot', 'is_primary', 'updated_at'))
    operation.result = {'command_id': command.pk, 'table_id': command.table_id}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(actor=user, action='attendance.command.transfer', obj=command, company=command.company,
              branch=command.branch, before=before, after=model_snapshot(command, ('table_id', 'table_name_snapshot', 'is_primary')),
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return command, False


@transaction.atomic
def transfer_items(*, command, destination_id, items, user, idempotency_key, audit_metadata=None):
    ids = sorted({command.pk, destination_id})
    locked = {row.pk: row for row in AttendanceCommand.objects.select_for_update().filter(pk__in=ids)}
    source, destination = locked.get(command.pk), locked.get(destination_id)
    if not source or not destination or source.branch_id != destination.branch_id:
        raise AttendanceConflict('command_scope_mismatch', 'As comandas devem pertencer à mesma filial.')
    if source.status != AttendanceCommandStatus.OPEN or destination.status != AttendanceCommandStatus.OPEN:
        raise AttendanceConflict('command_closed', 'A transferência exige comandas abertas.')
    operation, replayed = _operation(
        branch=source.branch, operation_type=AttendanceOperationType.TRANSFER_ITEMS,
        idempotency_key=idempotency_key, payload={'source': source.pk, 'destination': destination.pk, 'items': items},
    )
    if replayed:
        return destination, operation.result.get('item_ids', []), True
    if AttendancePayment.objects.filter(command__in=(source, destination), status=AttendancePaymentStatus.APPLIED, reversal__isnull=True).exists():
        raise AttendanceConflict(
            'command_payments_transfer_unsupported',
            'Não é possível transferir itens com pagamento parcial ativo: o rateio do pagamento entre consumos não é automático. Estorne os pagamentos antes de transferir itens.',
        )
    requested = {entry['item']: entry['quantity'] for entry in items}
    source_items = list(AttendanceOrderItem.objects.select_for_update().filter(
        pk__in=requested, order__command=source,
    ).select_related('order').order_by('pk'))
    if len(source_items) != len(requested):
        raise ValidationError({'items': 'Um ou mais itens não pertencem à comanda de origem.'})
    target_orders = {}
    moved = []
    for item in source_items:
        quantity = requested[item.pk]
        if quantity > item.quantity or item.status == AttendanceOrderItemStatus.CANCELLED:
            raise AttendanceConflict('item_not_transferable', 'O item não pode ser transferido.')
        if quantity < item.quantity and item.status == AttendanceOrderItemStatus.CONFIRMED:
            raise AttendanceConflict('confirmed_partial_transfer_unsupported', 'Item confirmado só pode ser transferido integralmente.')
        order = target_orders.setdefault(item.status, AttendanceOrder.objects.create(
            command=destination, created_by=user,
            status=AttendanceOrderStatus.CONFIRMED if item.status == AttendanceOrderItemStatus.CONFIRMED else AttendanceOrderStatus.DRAFT,
        ))
        before = model_snapshot(item, ('order_id', 'quantity'))
        if quantity == item.quantity:
            item.order = order
            item.save(update_fields=('order', 'updated_at'))
            moved.append(item.pk)
        else:
            item.quantity -= quantity
            item.save(update_fields=('quantity', 'updated_at'))
            clone = AttendanceOrderItem.objects.create(
                order=order, product=item.product, quantity=quantity, product_name=item.product_name,
                internal_code=item.internal_code, category_id_snapshot=item.category_id_snapshot,
                category_name_snapshot=item.category_name_snapshot, unit=item.unit, unit_price=item.unit_price,
                base_unit_price=item.base_unit_price, modifier_unit_total=item.modifier_unit_total,
                modifier_snapshot=item.modifier_snapshot, notes=item.notes, unit_cost=item.unit_cost,
                component_cost_snapshot=item.component_cost_snapshot,
            )
            moved.append(clone.pk)
        audit_log(actor=user, action='attendance.item.transfer', obj=item, company=source.company,
                  branch=source.branch, before=before, after={'destination_command_id': destination.pk},
                   metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    operation.result = {'command_id': destination.pk, 'item_ids': moved}
    operation.save(update_fields=('result', 'updated_at'))
    return destination, moved, False


@transaction.atomic
def group_tables(*, branch, table_ids, user, idempotency_key, audit_metadata=None):
    from apps.commands.models import Table, TableStatus

    branch = _active_branch(branch)
    normalized_ids = sorted(set(table_ids))
    operation, replayed = _operation(
        branch=branch, operation_type=AttendanceOperationType.GROUP_TABLES,
        idempotency_key=idempotency_key, payload={'tables': normalized_ids},
    )
    if replayed:
        return AttendanceTableGroup.objects.get(pk=operation.result['group_id']), True
    tables = list(Table.objects.select_for_update().filter(
        pk__in=normalized_ids, branch=branch, status=TableStatus.ACTIVE,
    ).order_by('pk'))
    if len(tables) != len(normalized_ids):
        raise AttendanceConflict('table_not_found', 'Uma ou mais mesas não pertencem à filial atual.')
    memberships = list(AttendanceTableGroupMembership.objects.select_for_update().filter(
        table_id__in=normalized_ids, left_at__isnull=True,
    ).select_related('group'))
    existing_groups = {membership.group for membership in memberships if membership.group.is_active}
    if len(existing_groups) > 1:
        raise AttendanceConflict(
            'table_group_merge_unsupported',
            'Separe os grupos existentes antes de agrupar essas mesas.',
        )
    group = next(iter(existing_groups), None)
    if group is None:
        group = AttendanceTableGroup.objects.create(
            company=branch.company, branch=branch, created_by=user,
        )
    current_ids = {membership.table_id for membership in memberships if membership.group_id == group.pk}
    added = [table for table in tables if table.pk not in current_ids]
    for table in added:
        AttendanceTableGroupMembership.objects.create(group=group, table=table, joined_by=user)
    active_ids = list(group.memberships.filter(left_at__isnull=True).values_list('table_id', flat=True))
    operation.result = {'group_id': group.pk, 'table_ids': active_ids}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user, action='attendance.table_group.group', obj=group,
        company=branch.company, branch=branch,
        after={'table_ids': active_ids, 'added_table_ids': [table.pk for table in added]},
        metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)),
    )
    return group, False


@transaction.atomic
def separate_table_from_group(*, branch, table_id, user, idempotency_key, audit_metadata=None):
    branch = _active_branch(branch)
    operation, replayed = _operation(
        branch=branch, operation_type=AttendanceOperationType.SEPARATE_TABLE,
        idempotency_key=idempotency_key, payload={'table': table_id},
    )
    if replayed:
        return operation.result.get('group_id'), True
    membership = AttendanceTableGroupMembership.objects.select_for_update().select_related('group').filter(
        table_id=table_id, table__branch=branch, left_at__isnull=True, group__is_active=True,
    ).first()
    if membership is None:
        raise AttendanceConflict('table_not_grouped', 'A mesa não pertence a um agrupamento ativo.')
    group = AttendanceTableGroup.objects.select_for_update().get(pk=membership.group_id)
    now = timezone.now()
    membership.left_at = now
    membership.left_by = user
    membership.save(update_fields=('left_at', 'left_by', 'updated_at'))
    remaining = list(group.memberships.select_for_update().filter(left_at__isnull=True))
    dissolved_ids = []
    if len(remaining) < 2:
        for row in remaining:
            row.left_at = now
            row.left_by = user
            row.save(update_fields=('left_at', 'left_by', 'updated_at'))
            dissolved_ids.append(row.table_id)
        group.is_active = False
        group.separated_at = now
        group.separated_by = user
        group.save(update_fields=('is_active', 'separated_at', 'separated_by', 'updated_at'))
    operation.result = {'group_id': group.pk, 'table_id': table_id, 'dissolved_table_ids': dissolved_ids}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user, action='attendance.table_group.separate', obj=group,
        company=branch.company, branch=branch,
        after=operation.result,
        metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)),
    )
    return group.pk, False


@transaction.atomic
def set_bill_requested(*, command, user, idempotency_key, requested, audit_metadata=None):
    command = AttendanceCommand.objects.select_for_update().select_related('branch__company').get(pk=command.pk)
    if command.status != AttendanceCommandStatus.OPEN:
        raise AttendanceConflict('command_closed', 'A comanda deve estar aberta.')
    operation_type = AttendanceOperationType.REQUEST_BILL if requested else AttendanceOperationType.CLEAR_BILL
    operation, replayed = _operation(
        branch=command.branch, operation_type=operation_type, idempotency_key=idempotency_key,
        payload={'command': command.pk},
    )
    if replayed:
        return command, True
    before = model_snapshot(command, ('bill_requested_at', 'bill_requested_by_id'))
    command.bill_requested_at = timezone.now() if requested else None
    command.bill_requested_by = user if requested else None
    command.save(update_fields=('bill_requested_at', 'bill_requested_by', 'updated_at'))
    operation.result = {'command_id': command.pk, 'requested': requested}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(
        actor=user,
        action='attendance.bill.request' if requested else 'attendance.bill.clear',
        obj=command, company=command.company, branch=command.branch,
        before=before, after=model_snapshot(command, ('bill_requested_at', 'bill_requested_by_id')),
        metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)),
    )
    return command, False


@transaction.atomic
def record_payment(*, command, user, payment_method_id, amount, idempotency_key,
                    cash_session_id=None, received_amount=None, discount=None,
                    discount_authorization=None, service_fee_waived=None,
                    service_fee_authorization=None, pos_device=None,
                    pos_permission_codes=None, audit_metadata=None):
    amount = strict_decimal(amount, field='amount', decimal_places=2, max_digits=14)
    received_amount = strict_decimal(
        received_amount, field='received_amount', decimal_places=2,
        max_digits=14, allow_none=True,
    )
    command = AttendanceCommand.objects.select_for_update().select_related('branch__company').get(pk=command.pk)
    if command.status != AttendanceCommandStatus.OPEN:
        raise AttendanceConflict('command_closed', 'Pagamentos parciais exigem comanda aberta.')
    method = PaymentMethod.objects.select_for_update().filter(
        pk=payment_method_id, company=command.company, status=Status.ACTIVE,
    ).first()
    if method is None:
        raise ValidationError({'payment_method': 'Forma de pagamento inválida ou inativa.'})
    session = None
    if method.code == PaymentMethodCode.CASH:
        session = CashSession.objects.select_for_update().filter(
            pk=cash_session_id, branch=command.branch, status=CashSessionStatus.OPEN,
        ).first()
        if session is None:
            raise ValidationError({'cash_session': 'Dinheiro exige sessão de caixa aberta na filial.'})
        if received_amount is None or received_amount < amount:
            raise ValidationError({'received_amount': 'Dinheiro exige valor recebido igual ou maior ao aplicado.'})
    elif cash_session_id is not None or received_amount is not None:
        raise ValidationError({'payment_method': 'Somente dinheiro aceita sessão, recebido e troco.'})
    existing = AttendancePayment.objects.select_for_update().filter(
        command=command, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if (
            existing.payment_method_id == method.pk and existing.amount == amount
            and existing.received_amount == received_amount and existing.cash_session_id == (session.pk if session else None)
        ):
            return existing
        raise AttendanceConflict('idempotency_key_conflict', 'A chave de idempotência já foi usada com outros dados.')
    paid_rows = AttendancePayment.objects.select_for_update(of=('self',)).filter(
        command=command, status=AttendancePaymentStatus.APPLIED, reversal__isnull=True,
    )
    has_payment = bool(list(paid_rows))
    requested_discount = strict_decimal(
        discount if discount is not None else command.checkout_discount,
        field='discount', decimal_places=2, max_digits=14,
    )
    requested_waiver = command.checkout_service_fee_waived if service_fee_waived is None else bool(service_fee_waived)
    if has_payment and (
        requested_discount != command.checkout_discount
        or requested_waiver != command.checkout_service_fee_waived
    ):
        raise AttendanceConflict('checkout_context_mismatch', 'Desconto e taxa foram definidos pelo primeiro pagamento.')
    if not has_payment:
        _discount_approver(command.branch, user, requested_discount, discount_authorization,
                            permission_code='sales.apply_discount', authorization_field='discount_authorization',
                            allow_pos_only=pos_device is not None, pos_device=pos_device,
                            permission_codes=pos_permission_codes,
                            device_validated=pos_device is not None)
        _service_fee_waiver(
            command.branch, user, requested_waiver, service_fee_authorization,
            allow_pos_only=pos_device is not None, pos_device=pos_device,
            permission_codes=pos_permission_codes, device_validated=pos_device is not None,
        )
        command.checkout_discount = requested_discount
        command.checkout_service_fee_waived = requested_waiver
        command.save(update_fields=('checkout_discount', 'checkout_service_fee_waived', 'updated_at'))
    _, paid, remaining = financial_state(command, lock=True)
    if amount > remaining:
        raise AttendanceConflict('command_overpayment', f'O pagamento excede o saldo de R$ {remaining:.2f}.')
    payment = AttendancePayment.objects.create(
        company=command.company, branch=command.branch, command=command,
        payment_method=method, amount=amount, received_amount=received_amount,
        cash_session=session, operator=user, idempotency_key=idempotency_key,
    )
    audit_log(actor=user, action='attendance.payment.record', obj=payment, company=command.company,
              branch=command.branch, after={'command_id': command.pk, 'amount': str(amount), 'payment_method_id': method.pk},
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return payment


@transaction.atomic
def reverse_payment(*, payment, user, reason, idempotency_key, audit_metadata=None):
    payment = AttendancePayment.objects.select_for_update().select_related(
        'command__branch__company', 'payment_method', 'cash_session',
    ).get(pk=payment.pk)
    command = payment.command
    if command.status != AttendanceCommandStatus.OPEN:
        raise AttendanceConflict('command_closed', 'Só é possível estornar pagamentos de comanda aberta.')
    operation, replayed = _operation(
        branch=command.branch, operation_type=AttendanceOperationType.REVERSE_PAYMENT,
        idempotency_key=idempotency_key, payload={'payment': payment.pk, 'reason': reason},
    )
    if replayed:
        return AttendancePayment.objects.get(pk=operation.result['reversal_id']), True
    if payment.status != AttendancePaymentStatus.APPLIED or hasattr(payment, 'reversal'):
        raise AttendanceConflict('payment_already_reversed', 'O pagamento já foi estornado.')
    if payment.cash_session_id:
        session = CashSession.objects.select_for_update().get(pk=payment.cash_session_id)
        if session.status != CashSessionStatus.OPEN:
            raise AttendanceConflict('cash_session_closed', 'Não é possível estornar após o fechamento do caixa.')
    reversal = AttendancePayment.objects.create(
        company=command.company, branch=command.branch, command=command,
        payment_method=payment.payment_method, amount=payment.amount,
        received_amount=payment.received_amount, cash_session=payment.cash_session,
        operator=user, status=AttendancePaymentStatus.REVERSED,
        idempotency_key=idempotency_key, reversal_of=payment,
        reversal_reason=(reason or '').strip(),
    )
    operation.result = {'reversal_id': reversal.pk, 'payment_id': payment.pk}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(actor=user, action='attendance.payment.reverse', obj=reversal, company=command.company,
              branch=command.branch, after={'payment_id': payment.pk, 'reason': reversal.reversal_reason},
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return reversal, False


@transaction.atomic
def finalize_command(*, command, user, cash_session_id, payments, idempotency_key,
                     discount=Decimal('0.00'), discount_authorization=None,
                      service_fee_waived=False, service_fee_authorization=None,
                      pos_device=None, pos_permission_codes=None, audit_metadata=None):
    command = AttendanceCommand.objects.select_for_update().select_related('branch__company').get(pk=command.pk)
    if command.sale_id:
        if command.sale.idempotency_key == idempotency_key:
            return command
        raise AttendanceConflict('command_closed', 'Esta comanda já foi finalizada.')
    if command.status != AttendanceCommandStatus.OPEN:
        raise AttendanceConflict('command_closed', 'A comanda deve estar aberta.')
    if AttendanceOrderItem.objects.filter(order__command=command, status=AttendanceOrderItemStatus.PENDING).exists():
        raise ValidationError({'items': 'Confirme ou cancele todos os itens pendentes antes de fechar a comanda.'})
    confirmed = list(AttendanceOrderItem.objects.filter(
        order__command=command, status=AttendanceOrderItemStatus.CONFIRMED,
    ).select_related('product').order_by('id'))
    if not confirmed:
        raise ValidationError({'items': 'A comanda não possui itens confirmados.'})
    ledger = list(AttendancePayment.objects.select_for_update(of=('self',)).select_related('payment_method').filter(
        command=command, status=AttendancePaymentStatus.APPLIED, reversal__isnull=True,
    ).order_by('pk'))
    if ledger and (
        strict_decimal(discount, field='discount', decimal_places=2, max_digits=14) != command.checkout_discount
        or bool(service_fee_waived) != command.checkout_service_fee_waived
    ):
        raise AttendanceConflict('checkout_context_mismatch', 'A finalização deve usar desconto e taxa do primeiro pagamento.')
    cash_session = CashSession.objects.select_for_update().filter(
        pk=cash_session_id, branch=command.branch, status=CashSessionStatus.OPEN,
    ).first()
    if cash_session is None:
        raise ValidationError({'cash_session': 'Informe uma sessão aberta da filial.'})
    preview, paid, remaining = financial_state(
        command, lock=True, discount=discount, service_fee_waived=service_fee_waived,
    )
    if paid > preview['total']:
        raise AttendanceConflict('command_paid_exceeds_final_total', 'Os pagamentos parciais excedem o total final.')
    if any(
        row.payment_method.code == PaymentMethodCode.CASH and row.cash_session_id != cash_session.pk
        for row in ledger
    ):
        raise AttendanceConflict(
            'partial_payment_cash_session_mismatch',
            'Finalize a comanda no mesmo caixa usado para os pagamentos parciais em dinheiro.',
        )
    normalized = [
        {'payment_method': row.payment_method_id, 'amount': row.amount, 'received_amount': row.received_amount}
        for row in ledger
    ] + list(payments)
    sale_items = [
        {
            'product': item.product_id, 'quantity': str(item.quantity),
            'modifiers': [
                {'option': modifier['option_id'], 'quantity': modifier['selected_quantity']}
                for modifier in item.modifier_snapshot or []
            ],
            'notes': item.notes, 'discount': '0.00',
        }
        for item in confirmed
    ]
    sale = finalize_sale(
        branch=command.branch, user=user, operation_type=OperationType.SALE,
        cash_session=cash_session, items=sale_items, payments=normalized, discount=discount,
        discount_authorization=discount_authorization, service_fee_waived=service_fee_waived,
        service_fee_authorization=service_fee_authorization, idempotency_key=idempotency_key,
        channel=SalesChannel.COMMAND, seller_user=user, customer=command.customer,
        confirmed_order_items=confirmed, internal_permission_code='commands.finalize',
        precomputed_financials=preview, attendance_payment_sources=[*ledger, *([None] * len(payments))],
        pos_device=pos_device, allow_pos_only=pos_device is not None,
        pos_permission_codes=pos_permission_codes, pos_device_validated=pos_device is not None,
        audit_metadata=audit_metadata,
    )
    command.status = AttendanceCommandStatus.CLOSED
    command.sale = sale
    command.closed_at = timezone.now()
    command.closed_by = user
    command.closed_by_name_snapshot = _operator_name(user)
    command.bill_requested_at = None
    command.bill_requested_by = None
    command.save(update_fields=(
        'status', 'sale', 'closed_at', 'closed_by', 'closed_by_name_snapshot',
        'bill_requested_at', 'bill_requested_by', 'updated_at',
    ))
    audit_log(actor=user, action='attendance.command.finalize', obj=command, company=command.company,
              branch=command.branch, after={'sale_id': sale.pk, 'total': str(sale.total)},
               metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return command


def _table_reference(attendance):
    return {'id': attendance.pk, 'table_id': attendance.table_id, 'status': attendance.status}


def table_financial_state(attendance, *, lock=False, discount=None, service_fee_waived=None):
    from .models import TableOrderItem, TablePayment

    items = TableOrderItem.objects.filter(
        order__attendance=attendance, status=AttendanceOrderItemStatus.CONFIRMED,
    ).select_related('product__category').order_by('id')
    if lock:
        items = items.select_for_update()
    preview = calculate_command_preview(
        branch=attendance.branch, order_items=list(items),
        discount=attendance.checkout_discount if discount is None else discount,
        service_fee_waived=(
            attendance.checkout_service_fee_waived
            if service_fee_waived is None else service_fee_waived
        ),
        lock=lock, include_internal_snapshots=True,
    )
    payments = TablePayment.objects.filter(
        attendance=attendance, status=AttendancePaymentStatus.APPLIED, reversal__isnull=True,
    )
    if lock:
        payments = payments.select_for_update(of=('self',))
    paid = payments.aggregate(total=Coalesce(
        Sum('amount'), Value(Decimal('0.00'), output_field=DecimalField(max_digits=14, decimal_places=2)),
    ))['total']
    service_fee_base = sum(
        (row['subtotal'] for row in preview['_snapshots'] if row['participates_in_service_fee']),
        Decimal('0.00'),
    )
    return preview, paid, max(preview['total'] - paid, Decimal('0.00')), service_fee_base


def table_summary(attendance):
    preview, paid, remaining, service_fee_base = table_financial_state(attendance)
    return {
        'subtotal': f"{preview['subtotal']:.2f}",
        'discount_total': f"{(preview['promotion_discount_total'] + preview['discount']):.2f}",
        'service_fee_base': f'{service_fee_base:.2f}',
        'service_fee_total': f"{preview['service_fee_amount']:.2f}",
        'total_due': f"{preview['total']:.2f}",
        'paid_total': f'{paid:.2f}',
        'remaining_balance': f'{remaining:.2f}',
    }


@transaction.atomic
def open_table_attendance(*, branch, table_id, user, idempotency_key, people_count=None,
                          responsible_name='', notes='', customer_id=None, audit_metadata=None):
    from apps.commands.models import Command, CommandStatus, Table, TableStatus
    from .models import TableAttendance, TableAttendanceStatus

    branch = _active_branch(branch)
    require_branch_feature(branch, 'tables')
    operation, replayed = _operation(
        branch=branch, operation_type=AttendanceOperationType.TABLE_OPEN,
        idempotency_key=idempotency_key,
        payload={'table': table_id, 'people_count': people_count, 'responsible_name': responsible_name,
                 'notes': notes, 'customer': customer_id},
    )
    if replayed:
        return TableAttendance.objects.get(pk=operation.result['attendance_id']), True
    table = Table.objects.select_for_update().filter(pk=table_id, branch=branch, status=TableStatus.ACTIVE).first()
    if not table:
        raise AttendanceConflict('table_not_found', 'Mesa não encontrada na filial atual.')
    if Command.objects.select_for_update().filter(table=table, status=CommandStatus.OPEN).exists():
        raise AttendanceConflict('table_in_legacy_use', 'A mesa possui atendimento aberto no fluxo legado.')
    existing = TableAttendance.objects.select_for_update().filter(table=table, status=TableAttendanceStatus.OPEN).first()
    if existing:
        operation.result = {'attendance_id': existing.pk}
        operation.save(update_fields=('result', 'updated_at'))
        return existing, True
    attendance = TableAttendance.objects.create(
        company=branch.company, branch=branch, table=table, people_count=people_count,
        responsible_name=responsible_name, notes=notes, customer=_customer(branch, customer_id), opened_by=user,
    )
    operation.result = {'attendance_id': attendance.pk}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(actor=user, action='table_attendance.open', obj=attendance, company=branch.company,
              branch=branch, after=_table_reference(attendance),
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return attendance, False


@transaction.atomic
def save_table_order(*, attendance, user, items, idempotency_key, audit_metadata=None):
    from .models import TableAttendance, TableAttendanceStatus, TableOrder, TableOrderItem

    attendance = TableAttendance.objects.select_for_update().select_related('branch__company').get(pk=attendance.pk)
    if attendance.status != TableAttendanceStatus.OPEN:
        raise AttendanceConflict('table_closed', 'A mesa deve estar aberta.')
    operation, replayed = _operation(
        branch=attendance.branch, operation_type=AttendanceOperationType.TABLE_ORDER,
        idempotency_key=idempotency_key, payload={'attendance': attendance.pk, 'items': items},
    )
    if replayed:
        return None, list(TableOrderItem.objects.filter(pk__in=operation.result['item_ids']).order_by('id')), True
    order = TableOrder.objects.create(attendance=attendance, created_by=user)
    created = []
    for entry in items:
        product = Product.objects.select_for_update().filter(pk=entry['product'], company=attendance.company).first()
        config = ProductBranchConfig.objects.filter(branch=attendance.branch, product=product).first() if product else None
        if not product or not (product.status == Status.ACTIVE and product.archived_at is None and product.is_sellable and product.available_command and config and config.is_available and config.available_command is not False):
            raise ValidationError({'product': 'Produto indisponível para Mesa nesta filial.'})
        quantity = strict_decimal(entry['quantity'], field='quantity', decimal_places=3, max_digits=14)
        if quantity <= 0 or (product.unit == Unit.UNIT and quantity != quantity.to_integral_value()):
            raise ValidationError({'quantity': 'Quantidade inválida para o produto.'})
        modifier_total, modifiers = resolve_modifiers(product, entry.get('modifiers', []), attendance.company_id, branch=attendance.branch, item_quantity=quantity)
        base_price = branch_price_map(attendance.branch, [product.pk]).get(product.pk, product.sale_price)
        unit_cost = branch_cost_map(attendance.branch, [product.pk]).get(product.pk, product.cost).quantize(CENT, rounding=ROUND_HALF_UP)
        item = TableOrderItem.objects.create(order=order, product=product, quantity=quantity, product_name=product.name,
            internal_code=product.internal_code or '', category_id_snapshot=product.category_id,
            category_name_snapshot=product.category.name if product.category_id else '', unit=product.unit,
            base_unit_price=base_price, modifier_unit_total=modifier_total,
            unit_price=(base_price + modifier_total).quantize(CENT, rounding=ROUND_HALF_UP),
            modifier_snapshot=modifiers, notes=entry.get('notes', ''), unit_cost=unit_cost)
        _confirm_table_item(item=item, attendance=attendance, user=user, idempotency_key=idempotency_key)
        created.append(item)
    order.status = AttendanceOrderStatus.CONFIRMED
    order.save(update_fields=('status', 'updated_at'))
    operation.result = {'order_id': order.pk, 'item_ids': [item.pk for item in created]}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(actor=user, action='table_order.create', obj=order, company=attendance.company, branch=attendance.branch,
              after={'attendance_id': attendance.pk, 'item_ids': operation.result['item_ids']},
              metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return order, created, False


def _confirm_table_item(*, item, attendance, user, idempotency_key):
    from apps.production.services import create_table_order_item_ticket, create_table_production_jobs
    requirements, contents, component_snapshots = stock_requirements_for_product(item.product, item.quantity, attendance.branch, item.modifier_snapshot)
    stocks = {}
    for product_id, quantity in sorted(requirements.items()):
        stock = materialize_stock(product=product_id, branch=attendance.branch)
        stocks[product_id] = stock
        apply_locked_stock(stock=stock, quantity=-quantity, user=user, movement_type=MovementType.SALE,
            nature=MovementNature.SALE, reason=f'Confirmação TableOrderItem {item.pk}', operation_reference=idempotency_key,
            domain_origin=MovementDomainOrigin.TABLE_ORDER, table_order_item=item,
            unit_cost_snapshot=stock.average_unit_cost if stock.average_unit_cost is not None else stock.product.cost,
            content_quantity=-contents[product_id] if product_id in contents else None)
    snapshot = {'quantity': item.quantity, 'component_cost_snapshot': component_snapshots, 'modifier_snapshot': item.modifier_snapshot}
    _reconcile_modifier_component_costs([snapshot], stocks)
    item.status = AttendanceOrderItemStatus.CONFIRMED
    item.confirmed_at = timezone.now()
    item.confirmed_by = user
    item.component_cost_snapshot = snapshot['component_cost_snapshot']
    item.save(update_fields=('status', 'confirmed_at', 'confirmed_by', 'component_cost_snapshot', 'updated_at'))
    create_table_production_jobs(item=item, attendance=attendance, user=user, idempotency_key=idempotency_key)
    create_table_order_item_ticket(item=item, attendance=attendance, user=user)


@transaction.atomic
def cancel_table_item(*, item, user, reason, idempotency_key, audit_metadata=None):
    from apps.inventory.models import Stock, StockMovement
    from apps.production.services import cancel_table_ticket_for_item, create_table_cancellation_jobs
    from .models import TableAttendanceStatus, TablePayment
    item = item.__class__.objects.select_for_update().select_related('order__attendance', 'product').get(pk=item.pk)
    attendance = item.order.attendance
    if attendance.status != TableAttendanceStatus.OPEN:
        raise AttendanceConflict('table_closed', 'O item só pode ser cancelado em mesa aberta.')
    operation, replayed = _operation(branch=attendance.branch, operation_type=AttendanceOperationType.TABLE_CANCEL_ITEM,
        idempotency_key=idempotency_key, payload={'item': item.pk, 'reason': reason})
    if replayed or item.status == AttendanceOrderItemStatus.CANCELLED:
        return item, True
    if TablePayment.objects.filter(attendance=attendance, status=AttendancePaymentStatus.APPLIED, reversal__isnull=True).exists():
        raise AttendanceConflict('table_payments_cancel_unsupported', 'Estorne os pagamentos antes de cancelar itens da mesa.')
    originals = list(StockMovement.objects.select_for_update().filter(table_order_item=item, movement_type=MovementType.SALE, original_movement__isnull=True).order_by('stock_id', 'pk'))
    stocks = {row.pk: row for row in Stock.objects.select_for_update().filter(pk__in=[movement.stock_id for movement in originals]).select_related('product')}
    for original in originals:
        apply_locked_stock(stock=stocks[original.stock_id], quantity=-original.quantity, user=user, movement_type=MovementType.SALE_CANCELLATION,
            reason=f'Cancelamento TableOrderItem {item.pk}: {reason}', original_movement=original,
            domain_origin=MovementDomainOrigin.TABLE_ORDER_CANCELLATION, table_order_item=item,
            unit_cost_snapshot=original.unit_cost_snapshot or original.stock.product.cost,
            content_quantity=-original.content_quantity if original.content_quantity is not None else None)
    create_table_cancellation_jobs(item=item, attendance=attendance, user=user, idempotency_key=idempotency_key, reason=reason)
    cancel_table_ticket_for_item(item=item, user=user)
    item.status = AttendanceOrderItemStatus.CANCELLED
    item.cancelled_at, item.cancelled_by, item.cancellation_reason = timezone.now(), user, (reason or '').strip()
    item.save(update_fields=('status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at'))
    operation.result = {'item_id': item.pk}
    operation.save(update_fields=('result', 'updated_at'))
    return item, False


@transaction.atomic
def record_table_payment(*, attendance, user, payment_method_id, amount, idempotency_key,
                         cash_session_id=None, received_amount=None, allocations=None,
                         discount=None, discount_authorization=None, service_fee_waived=None,
                         service_fee_authorization=None, pos_device=None, pos_permission_codes=None,
                         audit_metadata=None):
    from .models import TableAttendance, TableAttendanceStatus, TablePayment, TablePaymentAllocation
    amount = strict_decimal(amount, field='amount', decimal_places=2, max_digits=14)
    received_amount = strict_decimal(received_amount, field='received_amount', decimal_places=2, max_digits=14, allow_none=True)
    attendance = TableAttendance.objects.select_for_update().select_related('branch__company').get(pk=attendance.pk)
    if attendance.status != TableAttendanceStatus.OPEN:
        raise AttendanceConflict('table_closed', 'Pagamentos exigem mesa aberta.')
    method = PaymentMethod.objects.select_for_update().filter(pk=payment_method_id, company=attendance.company, status=Status.ACTIVE).first()
    if not method:
        raise ValidationError({'payment_method': 'Forma de pagamento inválida ou inativa.'})
    session = None
    if method.code == PaymentMethodCode.CASH:
        session = CashSession.objects.select_for_update().filter(pk=cash_session_id, branch=attendance.branch, status=CashSessionStatus.OPEN).first()
        if not session:
            raise ValidationError({'cash_session': 'Dinheiro exige sessão de caixa aberta na filial.'})
        if received_amount is None or received_amount < amount:
            raise ValidationError({'received_amount': 'Dinheiro exige valor recebido igual ou maior ao aplicado.'})
    elif cash_session_id is not None or received_amount is not None:
        raise ValidationError({'payment_method': 'Somente dinheiro aceita sessão, recebido e troco.'})
    operation, replayed = _operation(branch=attendance.branch, operation_type=AttendanceOperationType.TABLE_PAYMENT,
        idempotency_key=idempotency_key, payload={'attendance': attendance.pk, 'payment_method': payment_method_id,
        'amount': str(amount), 'cash_session': cash_session_id, 'received_amount': str(received_amount) if received_amount is not None else None, 'allocations': allocations or []})
    if replayed:
        return TablePayment.objects.get(pk=operation.result['payment_id']), True
    requested_discount = strict_decimal(discount if discount is not None else attendance.checkout_discount, field='discount', decimal_places=2, max_digits=14)
    requested_waiver = attendance.checkout_service_fee_waived if service_fee_waived is None else bool(service_fee_waived)
    has_payment = TablePayment.objects.select_for_update().filter(attendance=attendance, status=AttendancePaymentStatus.APPLIED, reversal__isnull=True).exists()
    if has_payment and (requested_discount != attendance.checkout_discount or requested_waiver != attendance.checkout_service_fee_waived):
        raise AttendanceConflict('checkout_context_mismatch', 'Desconto e taxa foram definidos pelo primeiro pagamento.')
    if not has_payment:
        _discount_approver(attendance.branch, user, requested_discount, discount_authorization, permission_code='sales.apply_discount', authorization_field='discount_authorization', allow_pos_only=pos_device is not None, pos_device=pos_device, permission_codes=pos_permission_codes, device_validated=pos_device is not None)
        _service_fee_waiver(attendance.branch, user, requested_waiver, service_fee_authorization, allow_pos_only=pos_device is not None, pos_device=pos_device, permission_codes=pos_permission_codes, device_validated=pos_device is not None)
        attendance.checkout_discount, attendance.checkout_service_fee_waived = requested_discount, requested_waiver
        attendance.save(update_fields=('checkout_discount', 'checkout_service_fee_waived', 'updated_at'))
    preview, _paid, remaining, _base = table_financial_state(attendance, lock=True)
    if allocations:
        amount = _table_allocation_amount(attendance, allocations, preview)
    if amount > remaining:
        raise AttendanceConflict('table_overpayment', f'O pagamento excede o saldo de R$ {remaining:.2f}.')
    payment = TablePayment.objects.create(attendance=attendance, payment_method=method, amount=amount, received_amount=received_amount, cash_session=session, operator=user, idempotency_key=idempotency_key)
    for allocation in allocations or []:
        TablePaymentAllocation.objects.create(payment=payment, item_id=allocation.get('item'), person_number=allocation.get('person_number'), amount=allocation['amount'], allocated_quantity=allocation.get('allocated_quantity'))
    operation.result = {'payment_id': payment.pk}
    operation.save(update_fields=('result', 'updated_at'))
    audit_log(actor=user, action='table_payment.record', obj=payment, company=attendance.company, branch=attendance.branch,
              after={'attendance_id': attendance.pk, 'amount': str(amount)}, metadata=_audit_metadata(audit_metadata, idempotency_key=str(idempotency_key)))
    return payment, False


def _table_allocation_amount(attendance, allocations, preview):
    from .models import TableOrderItem, TablePaymentAllocation
    item_ids = [row.get('item') for row in allocations if row.get('item')]
    items = {item.pk: item for item in TableOrderItem.objects.select_for_update().filter(pk__in=item_ids, order__attendance=attendance, status=AttendanceOrderItemStatus.CONFIRMED)}
    if len(items) != len(set(item_ids)):
        raise ValidationError({'allocations': 'Itens devem pertencer ao atendimento aberto da mesa.'})
    allocated = dict(TablePaymentAllocation.objects.select_for_update().filter(item_id__in=item_ids).values('item_id').annotate(total=Sum('allocated_quantity')).values_list('item_id', 'total'))
    total = Decimal('0.00')
    fee_rate = preview['service_fee_rate'] / Decimal('100')
    for row in allocations:
        item_id, quantity = row.get('item'), row.get('allocated_quantity')
        if not item_id or quantity is None:
            raise ValidationError({'allocations': 'Pagamento por itens exige item e quantidade.'})
        quantity = strict_decimal(quantity, field='allocated_quantity', decimal_places=3, max_digits=14)
        item = items[item_id]
        if (allocated.get(item_id) or Decimal('0')) + quantity > item.quantity:
            raise AttendanceConflict('table_item_overallocated', 'A quantidade alocada excede a quantidade disponível do item.')
        value = (item.unit_price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        config = ProductBranchConfig.objects.filter(branch=attendance.branch, product=item.product).first()
        participates_in_service_fee = (
            config.effective_participation('participates_in_service_fee')
            if config else item.product.participates_in_service_fee
        )
        if participates_in_service_fee and not attendance.checkout_service_fee_waived:
            value += (value * fee_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        row['allocated_quantity'], row['amount'] = quantity, value
        total += value
    return total


@transaction.atomic
def reverse_table_payment(*, payment, user, reason, idempotency_key, audit_metadata=None):
    from .models import TablePayment, TableAttendanceStatus
    payment = TablePayment.objects.select_for_update().select_related('attendance__branch__company', 'cash_session').get(pk=payment.pk)
    if payment.attendance.status != TableAttendanceStatus.OPEN:
        raise AttendanceConflict('table_closed', 'Só é possível estornar pagamento de mesa aberta.')
    operation, replayed = _operation(branch=payment.attendance.branch, operation_type=AttendanceOperationType.TABLE_REVERSE_PAYMENT,
        idempotency_key=idempotency_key, payload={'payment': payment.pk, 'reason': reason})
    if replayed:
        return TablePayment.objects.get(pk=operation.result['reversal_id']), True
    if payment.status != AttendancePaymentStatus.APPLIED or hasattr(payment, 'reversal'):
        raise AttendanceConflict('payment_already_reversed', 'O pagamento já foi estornado.')
    if payment.cash_session_id and payment.cash_session.status != CashSessionStatus.OPEN:
        raise AttendanceConflict('cash_session_closed', 'Não é possível estornar após o fechamento do caixa.')
    reversal = TablePayment.objects.create(attendance=payment.attendance, payment_method=payment.payment_method,
        amount=payment.amount, received_amount=payment.received_amount, cash_session=payment.cash_session,
        operator=user, status=AttendancePaymentStatus.REVERSED, idempotency_key=idempotency_key,
        reversal_of=payment, reversal_reason=(reason or '').strip())
    operation.result = {'payment_id': payment.pk, 'reversal_id': reversal.pk}
    operation.save(update_fields=('result', 'updated_at'))
    return reversal, False


@transaction.atomic
def set_table_bill_requested(*, attendance, user, requested, idempotency_key, audit_metadata=None):
    from .models import TableAttendance, TableAttendanceStatus
    attendance = TableAttendance.objects.select_for_update().get(pk=attendance.pk)
    if attendance.status != TableAttendanceStatus.OPEN:
        raise AttendanceConflict('table_closed', 'A mesa deve estar aberta.')
    operation, replayed = _operation(branch=attendance.branch, operation_type=AttendanceOperationType.TABLE_BILL,
        idempotency_key=idempotency_key, payload={'attendance': attendance.pk, 'requested': requested})
    if replayed:
        return attendance, True
    attendance.bill_requested_at = timezone.now() if requested else None
    attendance.bill_requested_by = user if requested else None
    attendance.save(update_fields=('bill_requested_at', 'bill_requested_by', 'updated_at'))
    operation.result = {'attendance_id': attendance.pk, 'requested': requested}
    operation.save(update_fields=('result', 'updated_at'))
    return attendance, False


@transaction.atomic
def close_table_attendance(*, attendance, user, idempotency_key, audit_metadata=None):
    from .models import TableAttendance, TableAttendanceStatus
    attendance = TableAttendance.objects.select_for_update().get(pk=attendance.pk)
    operation, replayed = _operation(branch=attendance.branch, operation_type=AttendanceOperationType.TABLE_CLOSE,
        idempotency_key=idempotency_key, payload={'attendance': attendance.pk})
    if replayed:
        return attendance, True
    if attendance.status != TableAttendanceStatus.OPEN:
        raise AttendanceConflict('table_closed', 'A mesa já está fechada.')
    _preview, _paid, remaining, _base = table_financial_state(attendance, lock=True)
    if remaining != Decimal('0.00'):
        raise AttendanceConflict('table_balance_remaining', f'Não é possível fechar: saldo de R$ {remaining:.2f}.')
    attendance.status, attendance.closed_at, attendance.closed_by = TableAttendanceStatus.CLOSED, timezone.now(), user
    attendance.bill_requested_at, attendance.bill_requested_by = None, None
    attendance.save(update_fields=('status', 'closed_at', 'closed_by', 'bill_requested_at', 'bill_requested_by', 'updated_at'))
    operation.result = {'attendance_id': attendance.pk}
    operation.save(update_fields=('result', 'updated_at'))
    return attendance, False


@transaction.atomic
def transfer_table_items(*, attendance, destination_id, items, user, idempotency_key, audit_metadata=None):
    from .models import TableAttendance, TableAttendanceStatus, TableOrder, TableOrderItem, TablePaymentAllocation
    locked = {row.pk: row for row in TableAttendance.objects.select_for_update().filter(pk__in=sorted({attendance.pk, destination_id}))}
    source, destination = locked.get(attendance.pk), locked.get(destination_id)
    if not source or not destination or source.branch_id != destination.branch_id:
        raise AttendanceConflict('table_scope_mismatch', 'Os atendimentos devem pertencer à mesma filial.')
    if source.status != TableAttendanceStatus.OPEN or destination.status != TableAttendanceStatus.OPEN:
        raise AttendanceConflict('table_closed', 'A transferência exige mesas abertas.')
    operation, replayed = _operation(branch=source.branch, operation_type=AttendanceOperationType.TABLE_TRANSFER_ITEMS,
        idempotency_key=idempotency_key, payload={'source': source.pk, 'destination': destination.pk, 'items': items})
    if replayed:
        return destination, operation.result['item_ids'], True
    requested = {row['item']: row['quantity'] for row in items}
    source_items = list(TableOrderItem.objects.select_for_update().filter(pk__in=requested, order__attendance=source).select_related('order').order_by('pk'))
    if len(source_items) != len(requested):
        raise ValidationError({'items': 'Um ou mais itens não pertencem à mesa de origem.'})
    if TablePaymentAllocation.objects.filter(item__in=source_items).exists():
        raise AttendanceConflict('table_item_allocated_transfer_unsupported', 'Itens com pagamento alocado não podem ser transferidos automaticamente.')
    moved, orders = [], {}
    for item in source_items:
        quantity = requested[item.pk]
        if quantity > item.quantity or item.status == AttendanceOrderItemStatus.CANCELLED:
            raise AttendanceConflict('item_not_transferable', 'O item não pode ser transferido.')
        if quantity < item.quantity and item.status == AttendanceOrderItemStatus.CONFIRMED:
            raise AttendanceConflict('confirmed_partial_transfer_unsupported', 'Item confirmado só pode ser transferido integralmente.')
        order = orders.setdefault(item.status, TableOrder.objects.create(attendance=destination, created_by=user,
            status=AttendanceOrderStatus.CONFIRMED if item.status == AttendanceOrderItemStatus.CONFIRMED else AttendanceOrderStatus.DRAFT))
        item.order = order
        item.save(update_fields=('order', 'updated_at'))
        moved.append(item.pk)
    operation.result = {'attendance_id': destination.pk, 'item_ids': moved}
    operation.save(update_fields=('result', 'updated_at'))
    return destination, moved, False
