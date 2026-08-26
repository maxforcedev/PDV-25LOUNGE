from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.base.audit import audit_log, model_snapshot
from apps.companies.features import require_branch_feature
from apps.companies.models import Branch, Status
from apps.companies.selectors import eligible_branch_users
from apps.inventory.models import (
    MovementType, MovementNature, MovementDomainOrigin, Stock, StockMovement,
)
from apps.inventory.services import apply_locked_stock
from apps.products.models import (
    FractionableProductConfig, Product, ProductBranchConfig, ProductComponent, ProductFractionComponent,
    Unit, SalesChannel, InventoryBehavior,
)
from apps.sales.services import (
    resolve_modifiers, branch_price_map, branch_cost_map,
    finalize_sale, CENT,
)

from .models import (
    Command, CommandStatus, Order, OrderItem, OrderItemStatus, OrderStatus,
    Table, TableStatus,
)


def _resolve_stock_requirements_for_product(product, quantity, branch):
    requirements = {}
    content_requirements = {}
    component_snapshots = []
    if product.inventory_behavior == InventoryBehavior.NONE:
        return requirements, content_requirements, component_snapshots
    if product.inventory_behavior == InventoryBehavior.DIRECT:
        requirements[product.pk] = requirements.get(product.pk, Decimal('0')) + quantity
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
    return requirements, content_requirements, component_snapshots


def _validate_branch_active(branch):
    if branch.company.status != Status.ACTIVE:
        raise ValidationError({'branch': 'A empresa deve estar ativa.'})
    if branch.status != Status.ACTIVE:
        raise ValidationError({'branch': 'A filial deve estar ativa.'})


def _get_locked_stock(product_id, branch):
    stock = Stock.objects.select_for_update().filter(
        product_id=product_id, branch=branch
    ).first()
    if stock is None:
        fraction_tracking = FractionableProductConfig.objects.filter(
            product_id=product_id, tracking_active=True
        ).exists()
        stock = Stock.objects.create(
            product_id=product_id, branch=branch,
            current_quantity=Decimal('0'), average_unit_cost=None,
            **({'current_content': Decimal('0.000000000')} if fraction_tracking else {}),
        )
    return stock


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
def open_command(*, branch, user, table=None, identifier='', support_session=None):
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
    count = Command.objects.filter(branch=branch_obj).count()
    command_number = f'C{count + 1:06d}'
    command = Command.objects.create(
        company=branch_obj.company,
        branch=branch_obj,
        table=table_obj,
        command_number=command_number,
        identifier=identifier,
        opened_by=user,
    )
    audit_log(
        actor=user, action='command.open', obj=command,
        company=branch_obj.company, branch=branch_obj,
        after=model_snapshot(command, (
            'company_id', 'branch_id', 'table_id', 'command_number', 'identifier', 'status', 'opened_by_id'
        )),
        metadata={'support_session': str(support_session.pk) if support_session else None},
    )
    return command


@transaction.atomic
def add_order_item(*, command, user, product_id, quantity, modifiers=None,
                   support_session=None, order=None):
    command = Command.objects.select_for_update().get(pk=command.pk)
    require_branch_feature(command.branch, 'commands')
    if command.status != CommandStatus.OPEN:
        raise ValidationError({'command': 'A comanda deve estar aberta.'})
    product = Product.objects.select_for_update().get(pk=product_id)
    if product.company_id != command.company_id:
        raise ValidationError({'product': 'Produto não pertence à empresa da comanda.'})
    if product.status != Status.ACTIVE:
        raise ValidationError({'product': 'Produto inativo.'})
    if not product.is_sellable:
        raise ValidationError({'product': 'Produto não vendável.'})
    if not product.available_command:
        raise ValidationError({'product': 'Produto não disponível para comanda.'})
    branch_config = ProductBranchConfig.objects.filter(
        branch=command.branch, product=product
    ).first()
    if branch_config and (
        not branch_config.is_available or branch_config.available_command is False
    ):
        raise ValidationError({'product': 'Produto indisponível para Comanda nesta filial.'})
    if product.unit == Unit.UNIT and quantity != quantity.to_integral_value():
        raise ValidationError({'quantity': 'Produto UN exige quantidade inteira.'})

    modifier_total, modifier_snapshot_data = resolve_modifiers(
        product, modifiers or [], product.company_id
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
    item = OrderItem.objects.select_for_update().select_related(
        'order__command', 'product'
    ).get(pk=item.pk)
    command = item.order.command
    require_branch_feature(command.branch, 'commands')
    if command.status != CommandStatus.OPEN:
        raise ValidationError({'command': 'A comanda deve estar aberta.'})
    if item.status == OrderItemStatus.CONFIRMED:
        return item
    if item.status != OrderItemStatus.PENDING:
        raise ValidationError({'item': 'Somente itens pendentes podem ser confirmados.'})

    product = item.product
    requirements, content_requirements, component_snapshots = (
        _resolve_stock_requirements_for_product(product, item.quantity, command.branch)
    )

    operation_ref = str(idempotency_key)
    for product_id, qty in requirements.items():
        stock = _get_locked_stock(product_id, command.branch)
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

    item.status = OrderItemStatus.CONFIRMED
    item.confirmed_at = timezone.now()
    item.confirmed_by = user
    item.component_cost_snapshot = component_snapshots
    item.save(update_fields=(
        'status', 'confirmed_at', 'confirmed_by', 'component_cost_snapshot', 'updated_at',
    ))

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
    if command.status != CommandStatus.OPEN:
        raise ValidationError({'command': 'A comanda deve estar aberta.'})
    if command.sale_id is not None:
        existing_sale = command.sale
        if existing_sale.idempotency_key == idempotency_key:
            return command
        raise ValidationError({'command': 'Esta comanda já foi finalizada.'})

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

    normalized_payments = []
    for payment in payments:
        normalized_payments.append({
            'payment_method': payment.get('payment_method') or payment.get('payment_method_id'),
            'amount': payment.get('amount'),
            'received_amount': payment.get('received_amount'),
        })

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
        confirmed_order_items=confirmed_items,
        internal_permission_code='commands.finalize',
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
