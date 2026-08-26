from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
import hashlib
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.base.audit import audit_log, model_snapshot
from apps.base.exceptions import DomainValidationError
from apps.companies.models import Branch, Company, Status
from apps.companies.selectors import user_has_branch_permission
from apps.products.models import (
    BranchProductPrice, Category, FractionableProductConfig, InventoryBehavior,
    Product, Unit,
)

from .content import (
    exact_content_equivalent, exact_multiply_quantized, exact_weighted_average,
)

from .models import (
    InventoryCount,
    InventoryCountItem,
    InventoryCountStatus,
    InventoryOperation,
    InventoryOperationKind,
    LossReason,
    LossRecord,
    MovementDomainOrigin,
    MovementNature,
    MovementType,
    Stock,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    StockTransferReceipt,
    StockTransferReceiptItem,
    StockTransferStatus,
    TransferCostSource,
    TransferDivergence,
    TransferDivergenceResolution,
    TransferDivergenceStatus,
    TransferResolutionType,
)


def _decimal(value, field, *, positive=False, nonnegative=False):
    if isinstance(value, (float, bool)):
        raise ValidationError({field: 'Envie valores decimais como texto, nunca float.'})
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: 'Informe um número decimal válido.'})
    if not value.is_finite():
        raise ValidationError({field: 'Informe um numero decimal finito.'})
    if positive and value <= 0:
        raise ValidationError({field: 'A quantidade deve ser maior que zero.'})
    if nonnegative and value < 0:
        raise ValidationError({field: 'A quantidade nao pode ser negativa.'})
    if value.as_tuple().exponent < -3:
        raise ValidationError({field: 'Use no maximo tres casas decimais.'})
    return value


def _content_decimal(value, field, *, positive=False, nonnegative=False):
    if isinstance(value, (float, bool)):
        raise ValidationError({field: 'Envie valores decimais como texto, nunca float.'})
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: 'Informe um conteudo decimal valido.'})
    if not value.is_finite() or value.as_tuple().exponent < -9:
        raise ValidationError({field: 'Use no maximo nove casas decimais.'})
    if positive and value <= 0:
        raise ValidationError({field: 'O conteudo deve ser maior que zero.'})
    if nonnegative and value < 0:
        raise ValidationError({field: 'O conteudo nao pode ser negativo.'})
    return value.quantize(Decimal('0.000000001'))


def _pk(value):
    return value.pk if hasattr(value, 'pk') else value


def _authorized_branch(branch, user, permission_code, *, support_session=None):
    try:
        branch = Branch.objects.select_related('company').get(pk=_pk(branch))
    except (Branch.DoesNotExist, TypeError, ValueError):
        if user.is_superuser:
            raise ValidationError({'branch': 'Filial invalida.'})
        raise PermissionDenied('Filial fora do contexto autorizado.')
    support_authorized = False
    if support_session is not None:
        expected_user_id = support_session.impersonated_user_id or support_session.actor_id
        support_authorized = bool(
            expected_user_id == user.pk
            and support_session.company_id == branch.company_id
            and support_session.mode == 'READ_WRITE'
            and support_session.ended_at is None
            and support_session.expires_at > timezone.now()
        )
    if not support_authorized and not user_has_branch_permission(
        user, branch.pk, permission_code
    ):
        raise PermissionDenied('Filial fora do contexto autorizado.')
    return branch


def _fingerprint(payload):
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _branch_sale_price(product, branch):
    price = BranchProductPrice.objects.filter(
        product=product, branch=branch
    ).values_list('sale_price', flat=True).first()
    return product.sale_price if price is None else price


def _locked_stock(product, branch):
    stock = Stock.objects.select_for_update().filter(product=product, branch=branch).first()
    if stock is None:
        defaults = {}
        config = FractionableProductConfig.objects.filter(
            product=product, tracking_active=True
        ).first()
        if config:
            defaults['current_content'] = Decimal('0.000000000')
        stock = Stock.objects.create(product=product, branch=branch, **defaults)
    return stock


def _active_fraction_config(product):
    try:
        config = product.fraction_config
    except FractionableProductConfig.DoesNotExist:
        return None
    return config if config.tracking_active else None


def _validate_whole_unit_quantity(product, quantity, field):
    if product.unit == Unit.UNIT and quantity != quantity.to_integral_value():
        raise ValidationError({
            field: 'Produtos em UN exigem quantidade inteira de embalagens.'
        })


def _validate_operational_stock(product, branch):
    if branch.company.status != Status.ACTIVE:
        raise DomainValidationError(
            code='inactive_company', message='A empresa deve estar ativa.',
            details={'company_id': branch.company_id},
        )
    if branch.status != Status.ACTIVE:
        raise DomainValidationError(
            code='inactive_branch', message='A filial deve estar ativa.',
            details={'branch_id': branch.pk},
        )
    if product.status != Status.ACTIVE:
        raise DomainValidationError(
            code='inactive_product', message='O produto deve estar ativo.',
            details={'product_id': product.pk},
        )
    if product.company_id != branch.company_id:
        raise ValidationError({'branch': 'A filial deve pertencer a empresa do produto.'})
    if product.inventory_behavior != InventoryBehavior.DIRECT:
        raise ValidationError({'product': 'Somente produtos com estoque próprio podem ser movimentados.'})


def _lock_active_company_branch(branch):
    company = Company.objects.select_for_update().get(pk=branch.company_id)
    branch = Branch.objects.select_for_update().select_related('company').get(
        pk=branch.pk, company=company
    )
    branch.company = company
    if company.status != Status.ACTIVE:
        raise DomainValidationError(
            code='inactive_company', message='A empresa deve estar ativa.',
            details={'company_id': company.pk},
        )
    if branch.status != Status.ACTIVE:
        raise DomainValidationError(
            code='inactive_branch', message='A filial deve estar ativa.',
            details={'branch_id': branch.pk},
        )
    return branch


def _claim_operation(*, branch, key, user, kind, payload):
    operation = InventoryOperation.objects.select_for_update().filter(
        branch=branch, idempotency_key=key
    ).first()
    if operation:
        if (
            operation.created_by_id != user.pk
            or operation.kind != kind
            or operation.payload != payload
        ):
            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='A chave de idempotencia ja foi usada com outros dados.',
                details={'operation_reference': str(key)},
            )
        return True
    InventoryOperation.objects.create(
        branch=branch,
        idempotency_key=key,
        kind=kind,
        payload=payload,
        created_by=user,
    )
    return False


def _move(*, product, branch, user, reason, movement_type, nature,
          permission_code, quantity=None, content_quantity=None,
          final_quantity=None, final_content=None,
          operation_reference=None, idempotency_key=None):
    reason = (reason or '').strip()
    with transaction.atomic():
        branch = _authorized_branch(branch, user, permission_code)
        branch = Branch.objects.select_for_update().select_related('company').get(pk=branch.pk)
        product_id = _pk(product)
        if idempotency_key:
            kind = {
                MovementType.ENTRY: InventoryOperationKind.MANUAL_ENTRY,
                MovementType.EXIT: InventoryOperationKind.MANUAL_EXIT,
                MovementType.ADJUSTMENT: InventoryOperationKind.MANUAL_ADJUSTMENT,
            }[movement_type]
            payload = {
                'product': int(product_id),
                'quantity': str(quantity) if quantity is not None else None,
                'content_quantity': (
                    str(content_quantity) if content_quantity is not None else None
                ),
                'final_quantity': str(final_quantity) if final_quantity is not None else None,
                'final_content': str(final_content) if final_content is not None else None,
                'nature': str(nature),
                'reason': reason,
            }
            replayed = _claim_operation(
                branch=branch, key=idempotency_key, user=user, kind=kind,
                payload=payload,
            )
            if replayed:
                existing = list(StockMovement.objects.select_related('stock').filter(
                    stock__branch=branch,
                    operation_reference=idempotency_key,
                )[:2])
                if len(existing) == 1:
                    existing[0]._idempotency_replayed = True
                    return existing[0]
                raise DomainValidationError(
                    code='idempotency_key_conflict',
                    message='A operação idempotente persistida está inconsistente.',
                    details={'operation_reference': str(idempotency_key)},
                )
        try:
            product = Product.objects.select_for_update().get(pk=product_id)
        except Product.DoesNotExist:
            raise ValidationError({'product': 'Produto invalido.'})
        _validate_operational_stock(product, branch)

        # Locking the product serializes both first-stock creation and later movements.
        stock = Stock.objects.select_for_update().filter(
            product=product, branch=branch
        ).first()
        if stock is None:
            stock = _locked_stock(product, branch)
        config = _active_fraction_config(product)
        adjustment_content = None
        if final_content is not None:
            if not config:
                raise ValidationError({
                    'final_content': 'Conteudo exato exige rastreamento fracionado ativo.'
                })
            final_content = _content_decimal(
                final_content, 'final_content', nonnegative=True
            )
            adjustment_content = final_content - stock.current_content
            quantity = Decimal('0')
            if adjustment_content == 0:
                raise ValidationError({'final_content': 'O ajuste deve alterar o saldo atual.'})
        elif final_quantity is not None:
            _validate_whole_unit_quantity(product, final_quantity, 'final_quantity')
            quantity = final_quantity - stock.current_quantity
            if config:
                target_content = (final_quantity * config.package_content).quantize(
                    Decimal('0.000000001'), rounding=ROUND_HALF_UP
                )
                adjustment_content = target_content - stock.current_content
            if quantity == 0 and adjustment_content in (None, Decimal('0')):
                raise ValidationError({'final_quantity': 'O ajuste deve alterar o saldo atual.'})
        elif content_quantity is not None:
            if not config:
                raise ValidationError({
                    'content_quantity': 'Conteudo exato exige rastreamento fracionado ativo.'
                })
            adjustment_content = _content_decimal(
                content_quantity, 'content_quantity'
            )
            quantity = Decimal('0')
        else:
            _validate_whole_unit_quantity(product, abs(quantity), 'quantity')
        if final_quantity is not None or final_content is not None:
            if (
                (stock.current_content < 0 if config else stock.current_quantity < 0)
                and (
                    adjustment_content > 0
                    if adjustment_content is not None else quantity > 0
                )
                and permission_code != 'inventory.regularize'
            ):
                raise DomainValidationError(
                    code='regularization_permission_required',
                    message='Use o fluxo Regularizar negativos para corrigir este saldo.',
                    details={
                        'stock_id': stock.pk,
                        'current_quantity': str(stock.current_quantity),
                    },
                )
        movement = apply_locked_stock(
            stock=stock, quantity=quantity, user=user, reason=reason,
            movement_type=movement_type, nature=nature,
            operation_reference=idempotency_key or operation_reference,
            domain_origin=MovementDomainOrigin.MANUAL,
            content_quantity=adjustment_content,
        )
        after = model_snapshot(movement, (
            'movement_type', 'nature', 'quantity', 'previous_quantity',
            'final_quantity', 'previous_content', 'content_quantity',
            'final_content', 'unit_cost_snapshot', 'reason',
        ))
        after['product_name'] = product.name
        audit_log(
            actor=user,
            action=(
                'inventory.regularize'
                if nature == MovementNature.REGULARIZATION
                else f'inventory.{movement_type}'
            ),
            obj=movement,
            company=branch.company, branch=branch,
            after=after,
            metadata={'operation_reference': str(movement.operation_reference)},
        )
        return movement


def apply_locked_stock(*, stock, quantity, user, movement_type, reason='', sale=None,
                       original_movement=None, nature=None, operation_reference=None,
                       effective_unit_cost=None, unit_cost_snapshot=None,
                       domain_origin=MovementDomainOrigin.LEGACY, transfer_item=None,
                       transfer_resolution=None, loss_record=None,
                       inventory_count_item=None, content_quantity=None,
                       order_item=None):
    """Apply a delta to a Stock row already locked by the current transaction."""
    config = _active_fraction_config(stock.product)
    previous = stock.current_quantity
    previous_content = None
    final_content = None
    if config:
        previous_content = (
            stock.current_content
            if stock.current_content is not None
            else (stock.current_quantity * config.package_content).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )
        )
        if original_movement is not None and original_movement.content_quantity is not None:
            content_quantity = -original_movement.content_quantity
        elif content_quantity is None:
            content_quantity = (Decimal(quantity) * config.package_content).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )
        else:
            content_quantity = _content_decimal(content_quantity, 'content_quantity')
        final_content = previous_content + content_quantity
        final = (final_content / config.package_content).quantize(
            Decimal('0.000000001'), rounding=ROUND_HALF_UP
        )
        quantity = final - previous
    elif content_quantity is not None:
        raise ValidationError(
            {'content_quantity': 'Conteudo exato exige rastreamento fracionado ativo.'}
        )
    final = (
        final if config else previous + quantity
    )
    if unit_cost_snapshot is None:
        if original_movement is not None:
            unit_cost_snapshot = (
                original_movement.unit_cost_snapshot
                if original_movement.unit_cost_snapshot is not None
                else stock.product.cost
            )
        elif effective_unit_cost is not None:
            unit_cost_snapshot = effective_unit_cost
        else:
            unit_cost_snapshot = (
                stock.average_unit_cost
                if stock.average_unit_cost is not None else stock.product.cost
            )
    try:
        unit_cost_snapshot = Decimal(unit_cost_snapshot).quantize(
            Decimal('0.000000000001'), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError({'unit_cost_snapshot': 'Informe um custo valido.'}) from error
    if not unit_cost_snapshot.is_finite() or unit_cost_snapshot < 0:
        raise ValidationError({
            'unit_cost_snapshot': 'O custo historico deve ser finito e nao negativo.'
        })
    negative_delta = content_quantity < 0 if config else quantity < 0
    negative_final = final_content < 0 if config else final < 0
    if negative_final and negative_delta:
        from apps.companies.models import BranchSettings
        allow_negative = BranchSettings.objects.filter(
            branch_id=stock.branch_id, allow_negative_stock=True
        ).exists()
        if not allow_negative:
            raise DomainValidationError(
                code='negative_stock_not_allowed',
                message='A movimentacao deixaria o estoque negativo.',
                details={'product_id': stock.product_id, 'current_quantity': str(previous), 'requested_quantity': str(quantity)},
            )
    stock.current_quantity = final
    update_fields = ['current_quantity', 'updated_at']
    if config:
        stock.current_content = final_content
        update_fields.append('current_content')
    if effective_unit_cost is not None:
        previous_valuation_quantity = (
            exact_content_equivalent(previous_content, config.package_content)
            if config else previous
        )
        incoming_valuation_quantity = (
            exact_content_equivalent(content_quantity, config.package_content)
            if config else quantity
        )
        if movement_type != MovementType.ENTRY or incoming_valuation_quantity <= 0:
            raise ValidationError({
                'effective_unit_cost': 'Custo de entrada somente pode ser aplicado em entrada positiva.'
            })
        try:
            effective_unit_cost = Decimal(effective_unit_cost)
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValidationError({'effective_unit_cost': 'Informe um custo valido.'}) from error
        if not effective_unit_cost.is_finite() or effective_unit_cost < 0:
            raise ValidationError({'effective_unit_cost': 'O custo deve ser finito e nao negativo.'})
        if previous_valuation_quantity > 0:
            previous_cost = (
                stock.average_unit_cost
                if stock.average_unit_cost is not None
                else stock.product.cost
            )
            average = exact_weighted_average(
                previous_valuation_quantity,
                previous_cost,
                incoming_valuation_quantity,
                effective_unit_cost,
            )
        else:
            average = effective_unit_cost
        stock.average_unit_cost = average.quantize(
            Decimal('0.000000000001'), rounding=ROUND_HALF_UP
        )
        stock.last_unit_cost = effective_unit_cost.quantize(
            Decimal('0.000000000001'), rounding=ROUND_HALF_UP
        )
        update_fields.extend(('average_unit_cost', 'last_unit_cost'))
    stock.save(update_fields=tuple(update_fields))
    return StockMovement.objects.create(
        stock=stock,
        movement_type=movement_type,
        previous_quantity=previous,
        quantity=quantity,
        final_quantity=final,
        previous_content=previous_content,
        content_quantity=content_quantity,
        final_content=final_content,
        unit_cost_snapshot=unit_cost_snapshot,
        user=user,
        reason=(reason or '').strip(),
        nature=nature or {
            MovementType.SALE: MovementNature.SALE,
            MovementType.CONSUMPTION: MovementNature.CONSUMPTION,
            MovementType.SALE_CANCELLATION: MovementNature.CANCELLATION,
            MovementType.CONSUMPTION_CANCELLATION: MovementNature.CANCELLATION,
        }.get(movement_type, MovementNature.NORMAL),
        operation_reference=operation_reference or uuid.uuid4(),
        sale=sale,
        original_movement=original_movement,
        domain_origin=domain_origin,
        transfer_item=transfer_item,
        transfer_resolution=transfer_resolution,
        loss_record=loss_record,
        inventory_count_item=inventory_count_item,
        order_item=order_item,
    )


@transaction.atomic
def activate_fraction_tracking(*, config, user):
    config = FractionableProductConfig.objects.select_for_update().select_related(
        'product__company'
    ).get(pk=_pk(config))
    if config.tracking_active:
        return config
    product = Product.objects.select_for_update().get(pk=config.product_id)
    if InventoryCountItem.objects.select_for_update().filter(
        product=product, is_open=True
    ).exists():
        raise ValidationError({
            'tracking_active': 'Conclua a contagem aberta antes de ativar o rastreamento.'
        })
    if StockTransferItem.objects.select_for_update().filter(
        product=product,
        transfer__status__in=(
            StockTransferStatus.DRAFT,
            StockTransferStatus.IN_TRANSIT,
            StockTransferStatus.PARTIALLY_RECEIVED,
        ),
    ).exists():
        raise ValidationError({
            'tracking_active': 'Conclua ou cancele as transferencias abertas antes da ativacao.'
        })
    stocks = list(
        Stock.objects.select_for_update().filter(product=product).order_by('branch_id')
    )
    before = model_snapshot(config, ('tracking_active', 'activated_at', 'activated_by_id'))
    config.tracking_active = True
    config.activated_at = timezone.now()
    config.activated_by = user
    config.save(update_fields=(
        'tracking_active', 'activated_at', 'activated_by', 'updated_at',
    ))
    for stock in stocks:
        stock.current_content = (stock.current_quantity * config.package_content).quantize(
            Decimal('0.000000001'), rounding=ROUND_HALF_UP
        )
        stock.save(update_fields=('current_content', 'updated_at'))
    audit_log(
        actor=user,
        action='product.fraction_tracking.activate',
        obj=config,
        company=product.company,
        before=before,
        after={
            **model_snapshot(config, ('tracking_active', 'activated_at', 'activated_by_id')),
            'initialized_stocks': [
                {
                    'stock_id': stock.pk,
                    'branch_id': stock.branch_id,
                    'current_quantity': str(stock.current_quantity),
                    'current_content': str(stock.current_content),
                }
                for stock in stocks
            ],
        },
    )
    return config


@transaction.atomic
def purchase_receipt_entry(*, product, branch, quantity, effective_unit_cost, user,
                           operation_reference, reason=''):
    """Apply a confirmed purchase through the same locked stock engine."""
    quantity = _decimal(quantity, 'quantity', positive=True)
    branch = Branch.objects.select_for_update().select_related('company').get(pk=_pk(branch))
    try:
        product = Product.objects.select_for_update().get(pk=_pk(product))
    except Product.DoesNotExist as error:
        raise ValidationError({'product': 'Produto invalido.'}) from error
    _validate_operational_stock(product, branch)
    _validate_whole_unit_quantity(product, quantity, 'quantity')
    stock = Stock.objects.select_for_update().filter(
        product=product, branch=branch
    ).first()
    if stock is None:
        stock = _locked_stock(product, branch)
    return apply_locked_stock(
        stock=stock,
        quantity=quantity,
        user=user,
        movement_type=MovementType.ENTRY,
        nature=MovementNature.PURCHASE,
        reason=reason,
        operation_reference=operation_reference,
        effective_unit_cost=effective_unit_cost,
        unit_cost_snapshot=effective_unit_cost,
        domain_origin=MovementDomainOrigin.PURCHASE,
    )


def entry(product, branch, user, quantity=None, content_quantity=None, reason='',
          nature=MovementNature.NORMAL, operation_reference=None, idempotency_key=None):
    if nature in (MovementNature.TRANSFER, MovementNature.LOSS, MovementNature.INVENTORY):
        raise ValidationError({'nature': 'Esta natureza exige o workflow especifico.'})
    if (quantity is None) == (content_quantity is None):
        raise ValidationError('Informe somente quantity ou content_quantity.')
    quantity = _decimal(quantity, 'quantity', positive=True) if quantity is not None else None
    content_quantity = (
        _content_decimal(content_quantity, 'content_quantity', positive=True)
        if content_quantity is not None else None
    )
    return _move(
        product=product, branch=branch, quantity=quantity,
        content_quantity=content_quantity, user=user,
        reason=reason, movement_type=MovementType.ENTRY, nature=nature,
        permission_code='inventory.entry', operation_reference=operation_reference,
        idempotency_key=idempotency_key,
    )


def exit(product, branch, user, quantity=None, content_quantity=None, reason='',
         nature=MovementNature.OTHER, operation_reference=None, idempotency_key=None):
    if nature in (MovementNature.TRANSFER, MovementNature.LOSS, MovementNature.INVENTORY):
        raise ValidationError({'nature': 'Esta natureza exige o workflow especifico.'})
    if (quantity is None) == (content_quantity is None):
        raise ValidationError('Informe somente quantity ou content_quantity.')
    quantity = _decimal(quantity, 'quantity', positive=True) if quantity is not None else None
    content_quantity = (
        _content_decimal(content_quantity, 'content_quantity', positive=True)
        if content_quantity is not None else None
    )
    return _move(
        product=product, branch=branch,
        quantity=-quantity if quantity is not None else None,
        content_quantity=(
            -content_quantity if content_quantity is not None else None
        ), user=user,
        reason=reason, movement_type=MovementType.EXIT, nature=nature,
        permission_code='inventory.exit', operation_reference=operation_reference,
        idempotency_key=idempotency_key,
    )


def adjustment(product, branch, user, final_quantity=None, final_content=None, reason='',
               nature=MovementNature.BALANCE_CORRECTION, permission_code='inventory.adjust',
               operation_reference=None, idempotency_key=None):
    if nature in (MovementNature.TRANSFER, MovementNature.LOSS, MovementNature.INVENTORY):
        raise ValidationError({'nature': 'Esta natureza exige o workflow especifico.'})
    if (final_quantity is None) == (final_content is None):
        raise ValidationError('Informe somente final_quantity ou final_content.')
    final_quantity = (
        _decimal(final_quantity, 'final_quantity')
        if final_quantity is not None else None
    )
    final_content = (
        _content_decimal(final_content, 'final_content', nonnegative=True)
        if final_content is not None else None
    )
    return _move(
        product=product, branch=branch, final_quantity=final_quantity,
        final_content=final_content, user=user,
        reason=reason, movement_type=MovementType.ADJUSTMENT, nature=nature,
        permission_code=permission_code, operation_reference=operation_reference,
        idempotency_key=idempotency_key,
    )


@transaction.atomic
def group_entry(*, branch, category, items, user, operation_reference,
                nature=MovementNature.NORMAL, reason=''):
    branch = _authorized_branch(branch, user, 'inventory.entry')
    branch = Branch.objects.select_for_update().select_related('company').get(pk=branch.pk)
    reference = operation_reference
    requested = sorted(
        (int(_pk(item.get('product'))), _decimal(item.get('quantity'), 'quantity', nonnegative=True))
        for item in items if _decimal(item.get('quantity'), 'quantity', nonnegative=True) > 0
    )
    payload = {
        'category': int(_pk(category)),
        'items': [
            {'product': product_id, 'quantity': str(quantity)}
            for product_id, quantity in requested
        ],
        'nature': str(nature),
        'reason': (reason or '').strip(),
    }
    replayed = _claim_operation(
        branch=branch, key=reference, user=user,
        kind=InventoryOperationKind.GROUP_ENTRY, payload=payload,
    )
    if replayed:
        existing = list(StockMovement.objects.select_related('stock').filter(
            stock__branch=branch, operation_reference=reference,
        ).order_by('stock__product_id'))
        if len(existing) != len(requested):
            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='A operação idempotente persistida está inconsistente.',
                details={'operation_reference': str(reference)},
            )
        for movement in existing:
            movement._idempotency_replayed = True
        return existing
    product_ids = [product_id for product_id, _quantity in requested]
    if not Category.objects.filter(
        pk=_pk(category), company_id=branch.company_id, status=Status.ACTIVE
    ).exists():
        raise DomainValidationError(
            code='invalid_inventory_entry_category',
            message='A categoria informada nao esta ativa nesta empresa.',
            details={'category_id': _pk(category)},
        )
    valid_ids = set(Product.objects.filter(
        id__in=product_ids,
        company_id=branch.company_id,
        category_id=_pk(category),
        inventory_behavior=InventoryBehavior.DIRECT,
        status=Status.ACTIVE,
    ).values_list('id', flat=True))
    if valid_ids != set(product_ids):
        raise ValidationError({
            'items': 'Todos os produtos devem ser fisicos, ativos e pertencer a categoria informada.'
        })
    movements = []
    for item in items:
        quantity = _decimal(item.get('quantity'), 'quantity', nonnegative=True)
        if quantity == 0:
            continue
        movements.append(entry(
            product=item.get('product'), branch=branch, quantity=quantity, user=user,
            nature=nature, reason=reason, operation_reference=reference,
        ))
    if not movements:
        raise DomainValidationError(
            code='empty_inventory_operation',
            message='Informe quantidade maior que zero para ao menos um produto.',
        )
    return movements


@transaction.atomic
def regularize_negatives(*, branch, items, user, reason=''):
    reference = uuid.uuid4()
    branch = _authorized_branch(branch, user, 'inventory.regularize')
    branch = Branch.objects.select_for_update().select_related('company').get(pk=branch.pk)
    movements = []
    for item in items:
        try:
            stock = Stock.objects.select_for_update().select_related(
                'product', 'branch', 'branch__company'
            ).get(pk=item['stock'], branch=branch)
        except Stock.DoesNotExist as error:
            raise DomainValidationError(
                code='regularization_stock_not_found',
                message='Um saldo informado nao pertence a filial atual.',
                details={'stock_id': item['stock']},
            ) from error
        config = _active_fraction_config(stock.product)
        is_negative = (
            stock.current_content < 0 if config else stock.current_quantity < 0
        )
        if not is_negative:
            raise DomainValidationError(
                code='regularization_stale_stock',
                message='Um saldo ja foi regularizado ou deixou de ser negativo.',
                details={
                    'stock_id': stock.pk,
                    'product_id': stock.product_id,
                    'current_quantity': str(stock.current_quantity),
                },
            )
        movements.append(adjustment(
            product=stock.product, branch=stock.branch,
            final_quantity=item['final_quantity'], user=user,
            reason=reason, nature=MovementNature.REGULARIZATION,
            permission_code='inventory.regularize', operation_reference=reference,
        ))
    return movements


@transaction.atomic
def set_minimum(*, stock, minimum_quantity, user):
    stock = Stock.objects.select_for_update().select_related(
        'product', 'branch', 'branch__company'
    ).get(pk=_pk(stock))
    branch = _authorized_branch(stock.branch, user, 'inventory.change_minimum')
    _validate_operational_stock(stock.product, branch)
    before = model_snapshot(stock, ('minimum_quantity',))
    stock.minimum_quantity = minimum_quantity
    stock.save(update_fields=('minimum_quantity', 'updated_at'))
    audit_log(
        actor=user, action='inventory.minimum.update', obj=stock,
        company=branch.company, branch=branch, before=before,
        after=model_snapshot(stock, ('minimum_quantity',)),
    )
    return stock


@transaction.atomic
def create_stock_transfer(*, origin_branch, destination_branch, items, user,
                          notes='', support_session=None):
    origin = _authorized_branch(
        origin_branch, user, 'inventory.transfer.create', support_session=support_session
    )
    origin = Branch.objects.select_for_update().select_related('company').get(pk=origin.pk)
    try:
        destination = Branch.objects.select_for_update().select_related('company').get(
            pk=_pk(destination_branch)
        )
    except (Branch.DoesNotExist, TypeError, ValueError) as error:
        raise ValidationError({'destination_branch': 'Filial de destino invalida.'}) from error
    if origin.pk == destination.pk:
        raise ValidationError({'destination_branch': 'A filial de destino deve ser diferente da origem.'})
    if origin.company_id != destination.company_id:
        raise ValidationError({'destination_branch': 'Origem e destino devem pertencer a mesma empresa.'})
    if origin.status != Status.ACTIVE or destination.status != Status.ACTIVE:
        raise ValidationError({'destination_branch': 'As duas filiais devem estar ativas.'})
    if origin.company.status != Status.ACTIVE:
        raise ValidationError({'origin_branch': 'A empresa deve estar ativa.'})
    if not isinstance(items, list) or not items:
        raise ValidationError({'items': 'Informe ao menos um produto.'})
    prepared = []
    seen = set()
    for index, raw in enumerate(items):
        product_id = _pk(raw.get('product')) if isinstance(raw, dict) else None
        try:
            product_id = int(product_id)
        except (TypeError, ValueError) as error:
            raise ValidationError({'items': f'Item {index + 1}: produto invalido.'}) from error
        if product_id in seen:
            raise ValidationError({'items': 'Nao repita produtos na mesma transferencia.'})
        seen.add(product_id)
        quantity = _decimal(raw.get('quantity'), f'items.{index}.quantity', positive=True)
        prepared.append((product_id, quantity))
    products = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(
            pk__in=sorted(seen), company=origin.company,
            inventory_behavior=InventoryBehavior.DIRECT, status=Status.ACTIVE,
        ).order_by('pk')
    }
    if set(products) != seen:
        raise ValidationError({'items': 'Todos os produtos devem ser fisicos e ativos nesta empresa.'})
    for index, (product_id, quantity) in enumerate(prepared):
        _validate_whole_unit_quantity(products[product_id], quantity, f'items.{index}.quantity')
    transfer = StockTransfer.objects.create(
        company=origin.company,
        origin_branch=origin,
        destination_branch=destination,
        notes=(notes or '').strip(),
        created_by=user,
    )
    created_items = []
    for product_id, quantity in prepared:
        product = products[product_id]
        created_items.append(StockTransferItem.objects.create(
            transfer=transfer,
            product=product,
            requested_quantity=quantity,
            product_name_snapshot=product.name,
            product_internal_code_snapshot=product.internal_code,
            product_unit_snapshot=product.unit,
            package_content_snapshot=(
                product.fraction_config.package_content
                if _active_fraction_config(product) else None
            ),
            content_unit_snapshot=(
                product.fraction_config.content_unit
                if _active_fraction_config(product) else ''
            ),
        ))
    audit_log(
        actor=user,
        action='inventory.transfer.create',
        obj=transfer,
        company=origin.company,
        branch=origin,
        after={
            'status': transfer.status,
            'origin_branch_id': origin.pk,
            'destination_branch_id': destination.pk,
            'items': [
                {'id': item.pk, 'product_id': item.product_id,
                 'requested_quantity': str(item.requested_quantity)}
                for item in created_items
            ],
        },
        metadata={'summary': f'Transferencia {transfer.pk} criada em rascunho.'},
    )
    return transfer


@transaction.atomic
def dispatch_stock_transfer(*, transfer, idempotency_key, user, support_session=None):
    transfer = StockTransfer.objects.select_for_update().select_related(
        'company', 'origin_branch', 'destination_branch'
    ).get(pk=_pk(transfer))
    origin = _authorized_branch(
        transfer.origin_branch, user, 'inventory.transfer.dispatch',
        support_session=support_session,
    )
    try:
        key = uuid.UUID(str(idempotency_key))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError({'idempotency_key': 'Informe um UUID valido.'}) from error
    items = list(transfer.items.select_for_update().select_related('product').order_by('product_id'))
    payload = {
        'transfer': str(transfer.pk),
        'origin_branch': transfer.origin_branch_id,
        'destination_branch': transfer.destination_branch_id,
        'items': [
            {'transfer_item': item.pk, 'product': item.product_id,
             'quantity': format(item.requested_quantity, 'f')}
            for item in items
        ],
    }
    fingerprint = _fingerprint(payload)
    key_owner = StockTransfer.objects.filter(
        origin_branch=origin, dispatch_idempotency_key=key
    ).exclude(pk=transfer.pk).first()
    if key_owner:
        raise DomainValidationError(
            code='idempotency_key_conflict',
            message='A chave de despacho ja foi usada por outra transferencia.',
            details={'transfer_id': str(key_owner.pk)},
        )
    if transfer.dispatch_idempotency_key is not None:
        if (
            transfer.dispatch_idempotency_key != key
            or transfer.dispatch_payload_fingerprint != fingerprint
            or transfer.dispatch_payload != payload
        ):
            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='O despacho ja foi confirmado com outra chave ou payload.',
                details={'transfer_id': str(transfer.pk)},
            )
        transfer._idempotency_replayed = True
        return transfer
    if transfer.status != StockTransferStatus.DRAFT:
        raise ValidationError({'status': 'Somente transferencia em rascunho pode ser despachada.'})
    if (
        transfer.destination_branch.status != Status.ACTIVE
        or transfer.company.status != Status.ACTIVE
    ):
        raise ValidationError({'destination_branch': 'A empresa e o destino devem estar ativos.'})
    if not items:
        raise ValidationError({'items': 'A transferencia deve possuir itens.'})
    movements = []
    now = timezone.now()
    for item in items:
        product = Product.objects.select_for_update().get(pk=item.product_id)
        _validate_operational_stock(product, origin)
        _validate_whole_unit_quantity(product, item.requested_quantity, 'requested_quantity')
        stock = _locked_stock(product, origin)
        fraction_config = _active_fraction_config(product)
        if fraction_config:
            if (
                item.package_content_snapshot != fraction_config.package_content
                or item.content_unit_snapshot != fraction_config.content_unit
            ):
                raise ValidationError({
                    'items': (
                        f'A configuracao fracionada de {product.name} mudou; '
                        'recrie a transferencia.'
                    )
                })
            closed_packages = (
                stock.current_content / fraction_config.package_content
            ).to_integral_value(rounding=ROUND_FLOOR)
            if closed_packages < item.requested_quantity:
                raise ValidationError({
                    'requested_quantity': (
                        f'O produto {product.name} possui somente {closed_packages} '
                        'embalagens fechadas transferiveis.'
                    )
                })
        cost = stock.average_unit_cost
        source = TransferCostSource.BRANCH_AVERAGE
        if cost is None:
            cost = product.cost
            source = TransferCostSource.PRODUCT_FALLBACK
        cost = Decimal(cost).quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
        item.dispatched_quantity = item.requested_quantity
        item.origin_unit_cost_snapshot = cost
        item.origin_cost_source = source
        item.origin_sale_price_snapshot = _branch_sale_price(product, origin)
        item._allow_dispatch_snapshot = True
        item.save(update_fields=(
            'dispatched_quantity', 'origin_unit_cost_snapshot', 'origin_cost_source',
            'origin_sale_price_snapshot', 'updated_at',
        ))
        movements.append(apply_locked_stock(
            stock=stock,
            quantity=-item.dispatched_quantity,
            user=user,
            movement_type=MovementType.EXIT,
            nature=MovementNature.TRANSFER,
            reason=f'Despacho da transferencia {transfer.pk}',
            operation_reference=transfer.pk,
            unit_cost_snapshot=cost,
            domain_origin=MovementDomainOrigin.TRANSFER_DISPATCH,
            transfer_item=item,
        ))
    transfer.status = StockTransferStatus.IN_TRANSIT
    transfer.dispatched_by = user
    transfer.dispatched_at = now
    transfer.dispatch_idempotency_key = key
    transfer.dispatch_payload_fingerprint = fingerprint
    transfer.dispatch_payload = payload
    transfer._allow_status_transition = True
    transfer.save(update_fields=(
        'status', 'dispatched_by', 'dispatched_at', 'dispatch_idempotency_key',
        'dispatch_payload_fingerprint', 'dispatch_payload', 'updated_at',
    ))
    audit_log(
        actor=user,
        action='inventory.transfer.dispatch',
        obj=transfer,
        company=transfer.company,
        branch=origin,
        before={'status': StockTransferStatus.DRAFT},
        after={
            'status': transfer.status,
            'dispatched_by_id': user.pk,
            'dispatched_at': str(now),
            'dispatch_idempotency_key': str(key),
            'items': [
                {'id': item.pk, 'quantity': str(item.dispatched_quantity),
                 'unit_cost_snapshot': str(item.origin_unit_cost_snapshot),
                 'cost_source': item.origin_cost_source,
                 'movement_id': movement.pk}
                for item, movement in zip(items, movements)
            ],
        },
        metadata={
            'summary': f'Transferencia {transfer.pk} despachada.',
            'idempotency_key': str(key),
            'payload_fingerprint': fingerprint,
        },
    )
    return transfer


@transaction.atomic
def cancel_stock_transfer(*, transfer, user, reason, support_session=None):
    transfer = StockTransfer.objects.select_for_update().select_related(
        'company', 'origin_branch'
    ).get(pk=_pk(transfer))
    origin = _authorized_branch(
        transfer.origin_branch, user, 'inventory.transfer.create',
        support_session=support_session,
    )
    reason = (reason or '').strip()
    if transfer.status != StockTransferStatus.DRAFT or transfer.dispatched_at:
        raise ValidationError({'status': 'Somente transferencia ainda nao despachada pode ser cancelada.'})
    if len(reason) < 3:
        raise ValidationError({'reason': 'Informe o motivo do cancelamento.'})
    now = timezone.now()
    transfer.status = StockTransferStatus.CANCELLED
    transfer.cancelled_by = user
    transfer.cancelled_at = now
    transfer.cancellation_reason = reason
    transfer._allow_status_transition = True
    transfer.save(update_fields=(
        'status', 'cancelled_by', 'cancelled_at', 'cancellation_reason', 'updated_at'
    ))
    audit_log(
        actor=user, action='inventory.transfer.cancel', obj=transfer,
        company=transfer.company, branch=origin,
        before={'status': StockTransferStatus.DRAFT},
        after=model_snapshot(transfer, (
            'status', 'cancelled_by_id', 'cancelled_at', 'cancellation_reason',
        )),
        metadata={'summary': f'Transferencia {transfer.pk} cancelada antes do despacho.'},
    )
    return transfer


def _canonical_transfer_receipt(transfer, items, finalize, notes):
    if not isinstance(items, list):
        raise ValidationError({'items': 'Informe uma lista de itens recebidos.'})
    canonical = []
    seen = set()
    for index, raw in enumerate(items):
        try:
            item_id = int(raw.get('transfer_item'))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValidationError({'items': f'Item {index + 1}: item invalido.'}) from error
        if item_id in seen:
            raise ValidationError({'items': 'Nao repita um item no mesmo recebimento.'})
        seen.add(item_id)
        quantity = _decimal(raw.get('quantity'), f'items.{index}.quantity', nonnegative=True)
        canonical.append({'transfer_item': item_id, 'quantity': format(quantity, 'f')})
    canonical.sort(key=lambda value: value['transfer_item'])
    if not finalize and not any(Decimal(item['quantity']) > 0 for item in canonical):
        raise ValidationError({
            'items': 'Recebimento sem quantidade positiva exige finalize=true.'
        })
    return {
        'transfer': str(transfer.pk),
        'items': canonical,
        'finalize': bool(finalize),
        'notes': (notes or '').strip(),
    }


@transaction.atomic
def receive_stock_transfer(*, transfer, idempotency_key, items, user,
                           finalize=False, notes='', support_session=None):
    transfer = StockTransfer.objects.select_for_update().select_related(
        'company', 'origin_branch', 'destination_branch'
    ).get(pk=_pk(transfer))
    destination = _authorized_branch(
        transfer.destination_branch, user, 'inventory.transfer.receive',
        support_session=support_session,
    )
    try:
        key = uuid.UUID(str(idempotency_key))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError({'idempotency_key': 'Informe um UUID valido.'}) from error
    payload = _canonical_transfer_receipt(transfer, items, finalize, notes)
    fingerprint = _fingerprint(payload)
    replay = StockTransferReceipt.objects.filter(
        destination_branch=destination, idempotency_key=key
    ).first()
    if replay:
        if replay.payload_fingerprint != fingerprint:
            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='A chave de idempotencia ja foi usada com outros dados.',
                details={'idempotency_key': str(key), 'receipt_id': str(replay.pk)},
            )
        replay._idempotency_replayed = True
        return replay
    if transfer.status not in (
        StockTransferStatus.IN_TRANSIT, StockTransferStatus.PARTIALLY_RECEIVED,
    ):
        raise ValidationError({'status': 'A transferencia nao esta disponivel para recebimento.'})
    transfer_items = {
        item.pk: item
        for item in transfer.items.select_for_update().select_related('product').order_by('product_id')
    }
    supplied_ids = {item['transfer_item'] for item in payload['items']}
    if not supplied_ids.issubset(transfer_items):
        raise ValidationError({'items': 'Um item nao pertence a transferencia informada.'})
    previous = {
        item_id: (
            StockTransferReceiptItem.objects.filter(
                transfer_item_id=item_id
            ).aggregate(total=Sum('received_quantity'))['total'] or Decimal('0.000')
        )
        for item_id in transfer_items
    }
    prepared = []
    supplied = {item['transfer_item']: Decimal(item['quantity']) for item in payload['items']}
    for item_id, quantity in supplied.items():
        item = transfer_items[item_id]
        _validate_whole_unit_quantity(item.product, quantity, 'quantity')
        pending = item.dispatched_quantity - previous[item_id]
        if quantity > pending:
            raise ValidationError({'items': f'O recebimento excede o pendente do item {item_id}.'})
        if quantity > 0:
            prepared.append((item, quantity, previous[item_id], pending - quantity))
    now = timezone.now()
    receipt = StockTransferReceipt.objects.create(
        transfer=transfer,
        company=transfer.company,
        destination_branch=destination,
        idempotency_key=key,
        payload_fingerprint=fingerprint,
        payload=payload,
        finalize=bool(finalize),
        notes=payload['notes'],
        received_by=user,
        received_at=now,
    )
    receipt_items = []
    movement_ids = []
    for item, quantity, received_before, pending_after in prepared:
        product = Product.objects.select_for_update().get(pk=item.product_id)
        _validate_operational_stock(product, destination)
        stock = _locked_stock(product, destination)
        movement = apply_locked_stock(
            stock=stock,
            quantity=quantity,
            user=user,
            movement_type=MovementType.ENTRY,
            nature=MovementNature.TRANSFER,
            reason=f'Recebimento da transferencia {transfer.pk}',
            operation_reference=receipt.pk,
            effective_unit_cost=item.origin_unit_cost_snapshot,
            unit_cost_snapshot=item.origin_unit_cost_snapshot,
            domain_origin=MovementDomainOrigin.TRANSFER_RECEIPT,
            transfer_item=item,
        )
        movement_ids.append(movement.pk)
        receipt_items.append(StockTransferReceiptItem.objects.create(
            receipt=receipt,
            transfer_item=item,
            dispatched_quantity_snapshot=item.dispatched_quantity,
            previously_received_quantity=received_before,
            received_quantity=quantity,
            accumulated_quantity=received_before + quantity,
            pending_quantity=pending_after,
            unit_cost_snapshot=item.origin_unit_cost_snapshot,
            received_content_snapshot=(
                quantity * item.package_content_snapshot
                if item.package_content_snapshot is not None else None
            ),
        ))
    accumulated = {
        item_id: previous[item_id] + supplied.get(item_id, Decimal('0.000'))
        for item_id in transfer_items
    }
    all_received = all(
        accumulated[item_id] == item.dispatched_quantity
        for item_id, item in transfer_items.items()
    )
    divergences = []
    previous_status = transfer.status
    if all_received:
        transfer.status = StockTransferStatus.RECEIVED
    elif finalize:
        transfer.status = StockTransferStatus.RECEIVED_WITH_DIVERGENCE
        for item_id, item in transfer_items.items():
            pending = item.dispatched_quantity - accumulated[item_id]
            if pending > 0:
                divergences.append(TransferDivergence.objects.create(
                    transfer_item=item,
                    dispatched_quantity_snapshot=item.dispatched_quantity,
                    received_quantity_snapshot=accumulated[item_id],
                    initial_quantity=pending,
                    pending_quantity=pending,
                    detected_by=user,
                    detected_at=now,
                ))
    else:
        transfer.status = StockTransferStatus.PARTIALLY_RECEIVED
    transfer._allow_status_transition = True
    transfer.save(update_fields=('status', 'updated_at'))
    audit_log(
        actor=user,
        action='inventory.transfer.receive',
        obj=receipt,
        company=transfer.company,
        branch=destination,
        before={'transfer_status': previous_status},
        after={
            'transfer_status': transfer.status,
            'received_by_id': user.pk,
            'received_at': str(now),
            'finalize': bool(finalize),
            'items': [
                {'transfer_item_id': item.transfer_item_id,
                 'received_quantity': str(item.received_quantity),
                 'pending_quantity': str(item.pending_quantity)}
                for item in receipt_items
            ],
            'movement_ids': movement_ids,
            'divergence_ids': [item.pk for item in divergences],
        },
        metadata={
            'summary': f'Recebimento {receipt.pk} da transferencia {transfer.pk}.',
            'idempotency_key': str(key),
        },
    )
    return receipt


@transaction.atomic
def resolve_transfer_divergence(*, divergence, idempotency_key, resolution_type,
                                quantity, observation, user, support_session=None):
    divergence = TransferDivergence.objects.select_for_update().select_related(
        'transfer_item__product', 'transfer_item__transfer__company',
        'transfer_item__transfer__origin_branch',
        'transfer_item__transfer__destination_branch',
    ).get(pk=_pk(divergence))
    transfer = divergence.transfer_item.transfer
    target_branch = (
        transfer.destination_branch
        if resolution_type == TransferResolutionType.FOUND_RECEIPT
        else transfer.origin_branch
    )
    target_branch = _authorized_branch(
        target_branch, user, 'inventory.transfer.resolve',
        support_session=support_session,
    )
    try:
        key = uuid.UUID(str(idempotency_key))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError({'idempotency_key': 'Informe um UUID valido.'}) from error
    quantity = _decimal(quantity, 'quantity', positive=True)
    observation = (observation or '').strip()
    if len(observation) < 3:
        raise ValidationError({'observation': 'Informe a observacao da resolucao.'})
    if resolution_type not in TransferResolutionType.values:
        raise ValidationError({'resolution_type': 'Tipo de resolucao invalido.'})
    _validate_whole_unit_quantity(divergence.transfer_item.product, quantity, 'quantity')
    payload = {
        'divergence': divergence.pk,
        'resolution_type': resolution_type,
        'quantity': format(quantity, 'f'),
        'observation': observation,
    }
    fingerprint = _fingerprint(payload)
    replay = TransferDivergenceResolution.objects.filter(
        divergence=divergence, idempotency_key=key
    ).first()
    if replay:
        if replay.payload_fingerprint != fingerprint:
            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='A chave de idempotencia ja foi usada com outros dados.',
                details={'resolution_id': str(replay.pk)},
            )
        replay._idempotency_replayed = True
        return replay
    if divergence.status != TransferDivergenceStatus.PENDING:
        raise ValidationError({'status': 'A divergencia ja foi resolvida.'})
    if quantity > divergence.pending_quantity:
        raise ValidationError({'quantity': 'A quantidade excede a divergencia pendente.'})
    now = timezone.now()
    resolution = TransferDivergenceResolution.objects.create(
        divergence=divergence,
        idempotency_key=key,
        payload_fingerprint=fingerprint,
        resolution_type=resolution_type,
        quantity=quantity,
        observation=observation,
        resolved_by=user,
        resolved_at=now,
    )
    movement = None
    item = divergence.transfer_item
    if resolution_type != TransferResolutionType.LOSS_IN_TRANSIT:
        product = Product.objects.select_for_update().get(pk=item.product_id)
        _validate_operational_stock(product, target_branch)
        stock = _locked_stock(product, target_branch)
        domain_origin = {
            TransferResolutionType.FOUND_RECEIPT: MovementDomainOrigin.TRANSFER_RECEIPT,
            TransferResolutionType.RETURN_TO_ORIGIN: MovementDomainOrigin.TRANSFER_RETURN,
            TransferResolutionType.AUTHORIZED_CORRECTION: MovementDomainOrigin.TRANSFER_CORRECTION,
        }[resolution_type]
        nature = (
            MovementNature.CORRECTION
            if resolution_type == TransferResolutionType.AUTHORIZED_CORRECTION
            else MovementNature.TRANSFER
        )
        movement = apply_locked_stock(
            stock=stock,
            quantity=quantity,
            user=user,
            movement_type=MovementType.ENTRY,
            nature=nature,
            reason=f'Resolucao {resolution_type} da transferencia {transfer.pk}',
            operation_reference=resolution.pk,
            effective_unit_cost=item.origin_unit_cost_snapshot,
            unit_cost_snapshot=item.origin_unit_cost_snapshot,
            domain_origin=domain_origin,
            transfer_item=item,
            transfer_resolution=resolution,
        )
    divergence.resolved_quantity += quantity
    divergence.pending_quantity -= quantity
    if divergence.pending_quantity == 0:
        divergence.status = TransferDivergenceStatus.RESOLVED
    divergence._allow_resolution = True
    divergence.save(update_fields=(
        'resolved_quantity', 'pending_quantity', 'status', 'updated_at'
    ))
    audit_log(
        actor=user,
        action='inventory.transfer.divergence.resolve',
        obj=resolution,
        company=transfer.company,
        branch=target_branch,
        before={
            'divergence_status': TransferDivergenceStatus.PENDING,
            'pending_quantity': str(divergence.pending_quantity + quantity),
        },
        after={
            'divergence_status': divergence.status,
            'pending_quantity': str(divergence.pending_quantity),
            'resolution_type': resolution_type,
            'quantity': str(quantity),
            'movement_id': movement.pk if movement else None,
        },
        metadata={
            'summary': f'Divergencia {divergence.pk} resolvida explicitamente.',
            'idempotency_key': str(key),
        },
    )
    return resolution


@transaction.atomic
def record_loss(*, branch, product, idempotency_key, quantity=None, reason,
                observation, user, content_quantity=None, support_session=None):
    branch = _authorized_branch(
        branch, user, 'inventory.loss.record', support_session=support_session
    )
    branch = Branch.objects.select_for_update().select_related('company').get(pk=branch.pk)
    try:
        key = uuid.UUID(str(idempotency_key))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError({'idempotency_key': 'Informe um UUID valido.'}) from error
    observation = (observation or '').strip()
    if reason not in LossReason.values:
        raise ValidationError({'reason': 'Motivo de perda invalido.'})
    if len(observation) < 3:
        raise ValidationError({'observation': 'Informe a observacao da perda.'})
    try:
        product = Product.objects.select_for_update().get(pk=_pk(product))
    except Product.DoesNotExist as error:
        raise ValidationError({'product': 'Produto invalido.'}) from error
    _validate_operational_stock(product, branch)
    config = _active_fraction_config(product)
    if config:
        if content_quantity not in (None, ''):
            exact_content = _content_decimal(
                content_quantity, 'content_quantity', positive=True
            )
            quantity = (exact_content / config.package_content).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )
        else:
            quantity = _decimal(quantity, 'quantity', positive=True)
            _validate_whole_unit_quantity(product, quantity, 'quantity')
            exact_content = (quantity * config.package_content).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )
    else:
        if content_quantity not in (None, ''):
            raise ValidationError({'content_quantity': 'Produto nao possui rastreamento de conteudo.'})
        quantity = _decimal(quantity, 'quantity', positive=True)
        _validate_whole_unit_quantity(product, quantity, 'quantity')
        exact_content = None
    payload = {
        'branch': branch.pk,
        'product': product.pk,
        'quantity': format(quantity, 'f'),
        'content_quantity': format(exact_content, 'f') if exact_content is not None else None,
        'reason': reason,
        'observation': observation,
    }
    fingerprint = _fingerprint(payload)
    replay = LossRecord.objects.filter(branch=branch, idempotency_key=key).first()
    if replay:
        if replay.payload_fingerprint != fingerprint:
            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='A chave de idempotencia ja foi usada com outros dados.',
                details={'loss_id': str(replay.pk)},
            )
        replay._idempotency_replayed = True
        return replay
    stock = _locked_stock(product, branch)
    cost = stock.average_unit_cost if stock.average_unit_cost is not None else product.cost
    cost = Decimal(cost).quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
    sale_price = _branch_sale_price(product, branch)
    loss = LossRecord.objects.create(
        company=branch.company,
        branch=branch,
        product=product,
        idempotency_key=key,
        payload_fingerprint=fingerprint,
        quantity=quantity,
        content_quantity=exact_content,
        content_unit=config.content_unit if config else '',
        package_content_snapshot=config.package_content if config else None,
        reason=reason,
        observation=observation,
        unit_cost_snapshot=cost,
        sale_price_snapshot=sale_price,
        cost_impact=exact_multiply_quantized(
            exact_content_equivalent(exact_content, config.package_content)
            if config else quantity,
            cost,
        ),
        potential_sale_value=exact_multiply_quantized(
            exact_content_equivalent(exact_content, config.package_content)
            if config else quantity,
            sale_price,
        ),
        recorded_by=user,
        recorded_at=timezone.now(),
    )
    movement = apply_locked_stock(
        stock=stock,
        quantity=-quantity,
        user=user,
        movement_type=MovementType.EXIT,
        nature=MovementNature.LOSS,
        reason=f'Perda {loss.get_reason_display()}: {observation}',
        operation_reference=loss.pk,
        unit_cost_snapshot=cost,
        domain_origin=MovementDomainOrigin.LOSS,
        loss_record=loss,
        content_quantity=-exact_content if exact_content is not None else None,
    )
    audit_log(
        actor=user,
        action='inventory.loss.record',
        obj=loss,
        company=branch.company,
        branch=branch,
        after={
            **model_snapshot(loss, (
                'product_id', 'quantity', 'reason', 'observation',
                'unit_cost_snapshot', 'sale_price_snapshot', 'cost_impact',
                'potential_sale_value', 'recorded_by_id', 'recorded_at',
            )),
            'movement_id': movement.pk,
        },
        metadata={'summary': f'Perda {loss.pk} registrada com uma unica baixa.'},
    )
    return loss


@transaction.atomic
def create_inventory_count(*, branch, items, observation, user, support_session=None):
    branch = _authorized_branch(
        branch, user, 'inventory.count.perform', support_session=support_session
    )
    branch = _lock_active_company_branch(branch)
    observation = (observation or '').strip()
    if len(observation) < 3:
        raise ValidationError({'observation': 'Informe a observacao do inventario.'})
    if not isinstance(items, list) or not items:
        raise ValidationError({'items': 'Informe ao menos um item contado.'})
    prepared = []
    seen = set()
    now = timezone.now()
    for index, raw in enumerate(items):
        try:
            product_id = int(_pk(raw.get('product')))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValidationError({'items': f'Item {index + 1}: produto invalido.'}) from error
        if product_id in seen:
            raise ValidationError({'items': 'Nao repita produtos no mesmo inventario.'})
        seen.add(product_id)
        counted_at = raw.get('counted_at') or now
        if counted_at > now:
            raise ValidationError({'items': f'Item {index + 1}: contado_em nao pode estar no futuro.'})
        prepared.append((product_id, raw, counted_at, (raw.get('observation') or '').strip()))
    products = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(
            pk__in=sorted(seen), company=branch.company,
            inventory_behavior=InventoryBehavior.DIRECT,
        ).order_by('pk')
    }
    if set(products) != seen:
        raise ValidationError({'items': 'Todos os produtos devem possuir estoque proprio nesta empresa.'})
    for product in products.values():
        _validate_operational_stock(product, branch)
    overlapping = InventoryCountItem.objects.select_for_update().filter(
        branch=branch, product_id__in=seen, is_open=True
    ).values_list('product_id', flat=True)
    overlapping_ids = sorted(set(overlapping))
    if overlapping_ids:
        raise DomainValidationError(
            code='inventory_count_overlap',
            message='Ja existe contagem aberta para um ou mais produtos nesta filial.',
            details={'product_ids': overlapping_ids},
        )
    count = InventoryCount.objects.create(
        company=branch.company,
        branch=branch,
        observation=observation,
        created_by=user,
    )
    created = []
    for product_id, raw, counted_at, item_observation in prepared:
        product = products[product_id]
        stock = _locked_stock(product, branch)
        config = _active_fraction_config(product)
        theoretical_content = None
        complete_packages = None
        residual_content = None
        counted_content = None
        difference_content = None
        if config:
            if raw.get('counted_complete_packages') in (None, ''):
                raise ValidationError({
                    'items': f'Produto {product.name}: informe as embalagens completas.'
                })
            complete_packages = _content_decimal(
                raw.get('counted_complete_packages'),
                'counted_complete_packages', nonnegative=True,
            )
            if complete_packages != complete_packages.to_integral_value():
                raise ValidationError({'counted_complete_packages': 'Use um numero inteiro.'})
            residual_content = _content_decimal(
                raw.get('counted_residual_content', '0'),
                'counted_residual_content', nonnegative=True,
            )
            if residual_content >= config.package_content:
                raise ValidationError({
                    'counted_residual_content': 'O residual deve ser menor que uma embalagem.'
                })
            counted_content = (
                complete_packages * config.package_content + residual_content
            ).quantize(Decimal('0.000000001'), rounding=ROUND_HALF_UP)
            counted = (counted_content / config.package_content).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )
            net_content_after = StockMovement.objects.filter(
                stock=stock, created_at__gt=counted_at
            ).aggregate(total=Sum('content_quantity'))['total'] or Decimal('0.000000000')
            theoretical_content = stock.current_content - net_content_after
            theoretical = (theoretical_content / config.package_content).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )
            difference_content = counted_content - theoretical_content
            difference = counted - theoretical
        else:
            counted = _decimal(
                raw.get('counted_quantity'), 'counted_quantity', nonnegative=True
            )
            _validate_whole_unit_quantity(product, counted, 'counted_quantity')
            net_after = StockMovement.objects.filter(
                stock=stock, created_at__gt=counted_at
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0.000')
            theoretical = stock.current_quantity - net_after
            difference = counted - theoretical
        cost = stock.average_unit_cost if stock.average_unit_cost is not None else product.cost
        cost = Decimal(cost).quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
        sale_price = _branch_sale_price(product, branch)
        created.append(InventoryCountItem.objects.create(
            inventory_count=count,
            branch=branch,
            product=product,
            theoretical_quantity=theoretical,
            counted_quantity=counted,
            difference_quantity=difference,
            theoretical_content=theoretical_content,
            counted_complete_packages=complete_packages,
            counted_residual_content=residual_content,
            counted_content=counted_content,
            difference_content=difference_content,
            content_unit=config.content_unit if config else '',
            package_content_snapshot=config.package_content if config else None,
            counted_at=counted_at,
            unit_cost_snapshot=cost,
            sale_price_snapshot=sale_price,
            cost_impact=exact_multiply_quantized(
                exact_content_equivalent(difference_content, config.package_content)
                if config else difference,
                cost,
            ),
            potential_sale_value=exact_multiply_quantized(
                exact_content_equivalent(difference_content, config.package_content)
                if config else difference,
                sale_price,
            ),
            counted_by=user,
            observation=item_observation,
        ))
    audit_log(
        actor=user,
        action='inventory.count.create',
        obj=count,
        company=branch.company,
        branch=branch,
        after={
            'status': count.status,
            'observation': observation,
            'items': [
                {'id': item.pk, 'product_id': item.product_id,
                 'theoretical_quantity': str(item.theoretical_quantity),
                 'counted_quantity': str(item.counted_quantity),
                 'difference_quantity': str(item.difference_quantity),
                 'counted_at': str(item.counted_at),
                 'unit_cost_snapshot': str(item.unit_cost_snapshot),
                 'sale_price_snapshot': str(item.sale_price_snapshot)}
                for item in created
            ],
        },
        metadata={'summary': f'Inventario {count.pk} capturado sem bloquear a filial.'},
    )
    return count


@transaction.atomic
def confirm_inventory_count(*, inventory_count, idempotency_key, user,
                            support_session=None):
    count_reference = InventoryCount.objects.only('branch_id').get(pk=_pk(inventory_count))
    branch = _authorized_branch(
        count_reference.branch_id, user, 'inventory.count.perform',
        support_session=support_session,
    )
    branch = _lock_active_company_branch(branch)
    count = InventoryCount.objects.select_for_update().select_related(
        'company', 'branch'
    ).get(pk=count_reference.pk, branch=branch)
    if count.company_id != branch.company_id:
        raise ValidationError({'company': 'O inventario nao pertence a empresa da filial.'})
    try:
        key = uuid.UUID(str(idempotency_key))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError({'idempotency_key': 'Informe um UUID valido.'}) from error
    if count.status == InventoryCountStatus.CONFIRMED:
        if count.confirmation_idempotency_key != key:
            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='O inventario ja foi confirmado com outra chave.',
                details={'inventory_count_id': str(count.pk)},
            )
        count._idempotency_replayed = True
        return count


    items = list(count.items.select_for_update().select_related('product').order_by('product_id'))
    if any(item.branch_id != branch.pk for item in items):
        raise ValidationError({'items': 'Os itens nao pertencem a filial do inventario.'})
    if any(not item.is_open for item in items):
        raise DomainValidationError(
            code='inventory_count_item_closed',
            message='Um item desta contagem ja foi reconciliado.',
            details={'inventory_count_id': str(count.pk)},
        )
    products = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(
            pk__in=[item.product_id for item in items]
        ).order_by('pk')
    }
    if len(products) != len(items):
        raise ValidationError({'items': 'Um ou mais produtos da contagem nao existem.'})
    for item in items:
        product = products[item.product_id]
        _validate_operational_stock(product, branch)
        if product.company_id != count.company_id:
            raise ValidationError({'product': 'O produto nao pertence a empresa do inventario.'})

    movements = []
    reconciliation = []
    for item in items:
        product = products[item.product_id]
        stock = _locked_stock(product, branch)
        config = _active_fraction_config(product)
        if config:
            net_content_after = StockMovement.objects.filter(
                stock=stock, created_at__gt=item.counted_at
            ).aggregate(total=Sum('content_quantity'))['total'] or Decimal('0.000000000')
            target_content = item.counted_content + net_content_after
            adjustment_content = target_content - stock.current_content
            target = (target_content / config.package_content).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )
            adjustment_quantity = target - stock.current_quantity
        else:
            net_after_count = StockMovement.objects.filter(
                stock=stock, created_at__gt=item.counted_at
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0.000')
            target = item.counted_quantity + net_after_count
            adjustment_quantity = target - stock.current_quantity
            adjustment_content = None
            net_content_after = None
        movement = None
        if (adjustment_content if config else adjustment_quantity) != 0:
            movement = apply_locked_stock(
                stock=stock,
                quantity=adjustment_quantity,
                user=user,
                movement_type=MovementType.ADJUSTMENT,
                nature=MovementNature.INVENTORY,
                reason=f'Confirmacao do inventario {count.pk}',
                operation_reference=count.pk,
                unit_cost_snapshot=item.unit_cost_snapshot,
                domain_origin=MovementDomainOrigin.INVENTORY_COUNT,
                inventory_count_item=item,
                content_quantity=adjustment_content,
            )
            movements.append(movement)
        reconciliation.append({
            'item_id': item.pk,
            'stock_id': stock.pk,
            'current_quantity_before': str(stock.current_quantity - adjustment_quantity),
            'counted_quantity': str(item.counted_quantity),
            'net_movements_after_counted_at': (
                str(net_content_after) if config else str(net_after_count)
            ),
            'target_quantity': str(target),
            'adjustment_quantity': str(adjustment_quantity),
            'movement_id': movement.pk if movement else None,
        })
    now = timezone.now()
    for item in items:
        item.is_open = False
        item.closed_at = now
        item._allow_close = True
        item.save(update_fields=('is_open', 'closed_at', 'updated_at'))
    count.status = InventoryCountStatus.CONFIRMED
    count.confirmed_by = user
    count.confirmed_at = now
    count.confirmation_idempotency_key = key
    count._allow_confirmation = True
    count.save(update_fields=(
        'status', 'confirmed_by', 'confirmed_at', 'confirmation_idempotency_key',
        'updated_at',
    ))
    audit_log(
        actor=user,
        action='inventory.count.confirm',
        obj=count,
        company=count.company,
        branch=branch,
        before={'status': InventoryCountStatus.OPEN},
        after={
            'status': count.status,
            'confirmed_by_id': user.pk,
            'confirmed_at': str(now),
            'reconciliation': reconciliation,
        },
        metadata={
            'summary': f'Inventario {count.pk} confirmado com movimentos posteriores preservados.',
            'idempotency_key': str(key),
            'movement_ids': [movement.pk for movement in movements],
        },
    )
    return count


get_or_create_locked_stock = _locked_stock
