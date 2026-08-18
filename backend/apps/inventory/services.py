from decimal import Decimal, InvalidOperation
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.base.audit import audit_log, model_snapshot
from apps.base.exceptions import DomainValidationError
from apps.companies.models import Branch, Status
from apps.companies.selectors import user_has_branch_permission
from apps.products.models import Category, InventoryBehavior, Product

from .models import (
    InventoryOperation,
    InventoryOperationKind,
    MovementNature,
    MovementType,
    Stock,
    StockMovement,
)


def _decimal(value, field, *, positive=False, nonnegative=False):
    if isinstance(value, float):
        raise ValidationError({field: 'Envie valores decimais como texto, nunca float.'})
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: 'Informe um numero decimal valido.'})
    if not value.is_finite():
        raise ValidationError({field: 'Informe um numero decimal finito.'})
    if positive and value <= 0:
        raise ValidationError({field: 'A quantidade deve ser maior que zero.'})
    if nonnegative and value < 0:
        raise ValidationError({field: 'A quantidade nao pode ser negativa.'})
    if value.as_tuple().exponent < -3:
        raise ValidationError({field: 'Use no maximo tres casas decimais.'})
    return value


def _pk(value):
    return value.pk if hasattr(value, 'pk') else value


def _authorized_branch(branch, user, permission_code):
    try:
        branch = Branch.objects.select_related('company').get(pk=_pk(branch))
    except (Branch.DoesNotExist, TypeError, ValueError):
        if user.is_superuser:
            raise ValidationError({'branch': 'Filial invalida.'})
        raise PermissionDenied('Filial fora do contexto autorizado.')
    if not user_has_branch_permission(user, branch.pk, permission_code):
        raise PermissionDenied('Filial fora do contexto autorizado.')
    return branch


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
        raise ValidationError({'product': 'Somente produtos com estoque proprio podem ser movimentados.'})


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
          permission_code, quantity=None, final_quantity=None,
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
                'quantity': str(quantity) if final_quantity is None else None,
                'final_quantity': str(final_quantity) if final_quantity is not None else None,
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
                    message='A operacao idempotente persistida esta inconsistente.',
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
            stock = Stock.objects.create(product=product, branch=branch)
        if final_quantity is not None:
            quantity = final_quantity - stock.current_quantity
            if quantity == 0:
                raise ValidationError({'final_quantity': 'O ajuste deve alterar o saldo atual.'})
            if (
                stock.current_quantity < 0
                and quantity > 0
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
        )
        audit_log(
            actor=user,
            action=(
                'inventory.regularize'
                if nature == MovementNature.REGULARIZATION
                else f'inventory.{movement_type}'
            ),
            obj=movement,
            company=branch.company, branch=branch,
            after=model_snapshot(movement, ('movement_type', 'nature', 'quantity', 'previous_quantity', 'final_quantity', 'reason')),
            metadata={'operation_reference': str(movement.operation_reference)},
        )
        return movement


def apply_locked_stock(*, stock, quantity, user, movement_type, reason='', sale=None,
                       original_movement=None, nature=None, operation_reference=None):
    """Apply a delta to a Stock row already locked by the current transaction."""
    previous = stock.current_quantity
    final = previous + quantity
    if final < 0 and quantity < 0:
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
    stock.save(update_fields=('current_quantity', 'updated_at'))
    return StockMovement.objects.create(
        stock=stock,
        movement_type=movement_type,
        previous_quantity=previous,
        quantity=quantity,
        final_quantity=final,
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
    )


def entry(product, branch, quantity, user, reason='', nature=MovementNature.NORMAL,
          operation_reference=None, idempotency_key=None):
    quantity = _decimal(quantity, 'quantity', positive=True)
    return _move(
        product=product, branch=branch, quantity=quantity, user=user,
        reason=reason, movement_type=MovementType.ENTRY, nature=nature,
        permission_code='inventory.entry', operation_reference=operation_reference,
        idempotency_key=idempotency_key,
    )


def exit(product, branch, quantity, user, reason='', nature=MovementNature.OTHER,
         operation_reference=None, idempotency_key=None):
    quantity = _decimal(quantity, 'quantity', positive=True)
    return _move(
        product=product, branch=branch, quantity=-quantity, user=user,
        reason=reason, movement_type=MovementType.EXIT, nature=nature,
        permission_code='inventory.exit', operation_reference=operation_reference,
        idempotency_key=idempotency_key,
    )


def adjustment(product, branch, final_quantity, user, reason='',
               nature=MovementNature.INVENTORY, permission_code='inventory.adjust',
               operation_reference=None, idempotency_key=None):
    final_quantity = _decimal(final_quantity, 'final_quantity')
    return _move(
        product=product, branch=branch, final_quantity=final_quantity, user=user,
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
                message='A operacao idempotente persistida esta inconsistente.',
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
        if stock.current_quantity >= 0:
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


def resolve_stock_requirements(items):
    requirements = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError('Cada item deve ser um dicionario.')
        quantity = _decimal(item.get('quantity'), 'quantity', positive=True)
        product_value = item.get('product', item.get('product_id'))
        try:
            product = (
                product_value if isinstance(product_value, Product)
                else Product.objects.get(pk=product_value)
            )
        except Product.DoesNotExist:
            raise ValidationError({'product': 'Produto invalido.'})
        if product.inventory_behavior == InventoryBehavior.NONE:
            continue
        if product.inventory_behavior == InventoryBehavior.DIRECT:
            requirements[product.pk] = requirements.get(product.pk, Decimal('0')) + quantity
            continue
        components = list(product.components.select_related('component_product'))
        if not components:
            raise ValidationError({'product': 'Produto composto sem composicao cadastrada.'})
        for component in components:
            required = quantity * component.quantity
            component_id = component.component_product_id
            requirements[component_id] = requirements.get(component_id, Decimal('0')) + required
    return requirements
