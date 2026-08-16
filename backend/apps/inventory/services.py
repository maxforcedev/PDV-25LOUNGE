from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.companies.models import Branch, Status
from apps.companies.selectors import user_has_branch_permission
from apps.products.models import InventoryBehavior, Product

from .models import MovementType, Stock, StockMovement


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
        raise ValidationError({'company': 'A empresa deve estar ativa.'})
    if branch.status != Status.ACTIVE:
        raise ValidationError({'branch': 'A filial deve estar ativa.'})
    if product.status != Status.ACTIVE:
        raise ValidationError({'product': 'O produto deve estar ativo.'})
    if product.company_id != branch.company_id:
        raise ValidationError({'branch': 'A filial deve pertencer a empresa do produto.'})
    if product.inventory_behavior != InventoryBehavior.DIRECT:
        raise ValidationError({'product': 'Somente produtos com estoque proprio podem ser movimentados.'})


def _move(*, product, branch, quantity, user, reason, movement_type):
    reason = (reason or '').strip()
    with transaction.atomic():
        branch = _authorized_branch(branch, user, 'inventory.move')
        try:
            product = Product.objects.select_for_update().get(pk=_pk(product))
        except Product.DoesNotExist:
            raise ValidationError({'product': 'Produto invalido.'})
        _validate_operational_stock(product, branch)

        # Locking the product serializes both first-stock creation and later movements.
        stock = Stock.objects.select_for_update().filter(
            product=product, branch=branch
        ).first()
        if stock is None:
            stock = Stock.objects.create(product=product, branch=branch)
        return apply_locked_stock(
            stock=stock, quantity=quantity, user=user, reason=reason,
            movement_type=movement_type,
        )


def apply_locked_stock(*, stock, quantity, user, movement_type, reason='', sale=None,
                       original_movement=None):
    """Apply a delta to a Stock row already locked by the current transaction."""
    previous = stock.current_quantity
    final = previous + quantity
    if final < 0:
        raise ValidationError({
            'stock': f'Saldo insuficiente para o produto {stock.product_id}.',
        })
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
        sale=sale,
        original_movement=original_movement,
    )


def entry(product, branch, quantity, user, reason=''):
    quantity = _decimal(quantity, 'quantity', positive=True)
    return _move(
        product=product, branch=branch, quantity=quantity, user=user,
        reason=reason, movement_type=MovementType.ENTRY,
    )


def exit(product, branch, quantity, user, reason=''):
    quantity = _decimal(quantity, 'quantity', positive=True)
    return _move(
        product=product, branch=branch, quantity=-quantity, user=user,
        reason=reason, movement_type=MovementType.EXIT,
    )


def adjustment(product, branch, final_quantity, user, reason=''):
    final_quantity = _decimal(final_quantity, 'final_quantity', nonnegative=True)
    with transaction.atomic():
        locked_branch = _authorized_branch(branch, user, 'inventory.move')
        try:
            locked_product = Product.objects.select_for_update().get(pk=_pk(product))
        except Product.DoesNotExist:
            raise ValidationError({'product': 'Produto invalido.'})
        _validate_operational_stock(locked_product, locked_branch)
        stock = Stock.objects.select_for_update().filter(
            product=locked_product, branch=locked_branch
        ).first()
        current = stock.current_quantity if stock else Decimal('0')
        delta = final_quantity - current
        if delta == 0:
            raise ValidationError({'final_quantity': 'O ajuste deve alterar o saldo atual.'})
        return _move(
            product=locked_product, branch=locked_branch, quantity=delta, user=user,
            reason=reason, movement_type=MovementType.ADJUSTMENT,
        )


@transaction.atomic
def set_minimum(*, stock, minimum_quantity, user):
    stock = Stock.objects.select_for_update().select_related(
        'product', 'branch', 'branch__company'
    ).get(pk=_pk(stock))
    branch = _authorized_branch(stock.branch, user, 'inventory.change_minimum')
    _validate_operational_stock(stock.product, branch)
    stock.minimum_quantity = minimum_quantity
    stock.save(update_fields=('minimum_quantity', 'updated_at'))
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
