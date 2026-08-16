from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import IntegerField, Max
from django.db.models.functions import Cast, Substr
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.cash.models import CashSession, CashSessionStatus
from apps.companies.models import Branch, Company, Status, UserCompanyAccess
from apps.companies.selectors import user_has_branch_permission
from apps.inventory.models import MovementType, Stock, StockMovement
from apps.inventory.services import apply_locked_stock
from apps.products.models import InventoryBehavior, Product, ProductComponent, Unit

from .models import (
    OperationType, Payment, PaymentMethod, PaymentMethodCode, Promotion,
    PromotionDiscountType, Sale, SaleItem, SaleStatus,
)


DEFAULT_PAYMENT_METHODS = (
    (PaymentMethodCode.CASH, 'Dinheiro'),
    (PaymentMethodCode.PIX, 'PIX'),
    (PaymentMethodCode.CREDIT_CARD, 'Cartao de credito'),
    (PaymentMethodCode.DEBIT_CARD, 'Cartao de debito'),
)
MAX_MONEY = Decimal('999999999999.99')
CENT = Decimal('0.01')


def ensure_default_payment_methods(company):
    methods = []
    for code, name in DEFAULT_PAYMENT_METHODS:
        method, _ = PaymentMethod.objects.get_or_create(
            company=company,
            code=code,
            defaults={'name': name, 'status': Status.ACTIVE, 'is_system': True},
        )
        updates = []
        if not method.is_system:
            method.is_system = True
            updates.append('is_system')
        if method.name != name:
            method.name = name
            updates.append('name')
        if updates:
            PaymentMethod.objects.filter(pk=method.pk).update(**{field: getattr(method, field) for field in updates})
        methods.append(method)
    return methods


def strict_decimal(value, *, field, decimal_places, max_digits, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, (float, bool)) or value in ('', None):
        raise ValidationError({field: 'Informe um decimal valido como string ou inteiro.'})
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: 'Informe um decimal valido.'})
    if not result.is_finite():
        raise ValidationError({field: 'O valor deve ser finito.'})
    exponent = result.as_tuple().exponent
    places = max(-exponent, 0)
    integer_digits = max(len(result.as_tuple().digits) + exponent, 0)
    if places > decimal_places or integer_digits + places > max_digits:
        raise ValidationError({field: f'Use no maximo {decimal_places} casas decimais.'})
    return result.quantize(Decimal(1).scaleb(-decimal_places))


def ensure_money_fits(value, field):
    if value < 0 or value > MAX_MONEY:
        raise ValidationError({field: 'O valor excede o limite monetario permitido.'})
    return value


def _consolidate_items(raw_items, products):
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError({'items': 'Informe ao menos um item.'})
    quantities = {}
    ordered_ids = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict) or raw_item.get('product') in ('', None):
            raise ValidationError({'items': f'Item {index + 1}: informe o produto.'})
        product = products.get(str(raw_item['product']))
        if not product:
            raise ValidationError({'items': f'Item {index + 1}: produto indisponivel nesta empresa.'})
        quantity = strict_decimal(
            raw_item.get('quantity'), field='quantity', decimal_places=3, max_digits=14
        )
        if quantity <= 0:
            raise ValidationError({'items': f'Item {index + 1}: a quantidade deve ser positiva.'})
        if product.unit == Unit.UNIT and quantity != quantity.to_integral_value():
            raise ValidationError({'items': f'Item {index + 1}: produto UN exige quantidade inteira.'})
        if product.pk not in quantities:
            ordered_ids.append(product.pk)
            quantities[product.pk] = Decimal('0.000')
        quantities[product.pk] += quantity
        if quantities[product.pk] > Decimal('99999999999.999'):
            raise ValidationError({'items': 'A quantidade consolidada excede o limite permitido.'})

    provisional = []
    subtotal = Decimal('0.00')
    products_by_id = {product.pk: product for product in products.values()}
    for product_id in ordered_ids:
        product = products_by_id[product_id]
        quantity = quantities[product_id]
        item_subtotal = (product.sale_price * quantity).quantize(Decimal('0.01'))
        ensure_money_fits(item_subtotal, 'items')
        subtotal += item_subtotal
        ensure_money_fits(subtotal, 'subtotal')
        provisional.append({
            'product_object': product,
            'product': product_id,
            'quantity': quantity,
            'product_name': product.name,
            'internal_code': product.internal_code,
            'unit': product.unit,
            'unit_price': product.sale_price,
            'subtotal': item_subtotal,
        })
    return provisional, subtotal


def _eligible_promotions(company, timestamp, *, lock=False):
    queryset = Promotion.objects.filter(
        company=company,
        status=Status.ACTIVE,
        starts_at__lte=timestamp,
        ends_at__gt=timestamp,
    ).order_by('pk')
    if lock:
        queryset = queryset.select_for_update()
    return list(queryset.prefetch_related('products', 'categories'))


def _apply_promotions(operation_type, items, promotions):
    for item in items:
        selected = None
        if operation_type == OperationType.SALE:
            candidates = []
            product = item['product_object']
            for promotion in promotions:
                product_ids = {target.pk for target in promotion.products.all()}
                category_ids = {target.pk for target in promotion.categories.all()}
                direct_target = product.pk in product_ids
                if not direct_target and product.category_id not in category_ids:
                    continue
                if promotion.discount_type == PromotionDiscountType.PERCENTAGE:
                    benefit = (
                        item['subtotal'] * promotion.discount_value / Decimal('100')
                    ).quantize(CENT, rounding=ROUND_HALF_UP)
                else:
                    benefit = promotion.discount_value.quantize(CENT, rounding=ROUND_HALF_UP)
                benefit = min(benefit, item['subtotal'])
                candidates.append((promotion, benefit, direct_target))
            if candidates:
                selected = min(
                    candidates,
                    key=lambda candidate: (
                        -candidate[1], not candidate[2],
                        candidate[0].starts_at, candidate[0].pk,
                    ),
                )

        promotion, benefit, _direct = selected or (None, Decimal('0.00'), False)
        item.update({
            'promotion': promotion.pk if promotion else None,
            'promotion_object': promotion,
            'promotion_name': promotion.name if promotion else None,
            'promotion_discount_type': promotion.discount_type if promotion else None,
            'promotion_discount_value': promotion.discount_value if promotion else None,
            'promotion_benefit': benefit,
            'net_subtotal': item['subtotal'] - benefit,
        })
    return sum((item['promotion_benefit'] for item in items), Decimal('0.00'))


def calculate_preview(*, company, operation_type, raw_items, discount, charged_amount, beneficiary_user):
    if operation_type not in OperationType.values:
        raise ValidationError({'operation_type': 'Tipo de operacao invalido.'})
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError({'items': 'Informe ao menos um item.'})
    product_ids = [item.get('product') for item in raw_items if isinstance(item, dict)]
    if len(product_ids) != len(raw_items) or any(value in ('', None) for value in product_ids):
        raise ValidationError({'items': 'Todos os itens devem informar um produto.'})
    products = {
        str(product.pk): product
        for product in Product.objects.select_related('category').filter(
            pk__in=product_ids, company=company, status=Status.ACTIVE, is_sellable=True
        )
    }
    provisional, subtotal = _consolidate_items(raw_items, products)
    operation_timestamp = timezone.now()
    promotions = (
        _eligible_promotions(company, operation_timestamp)
        if operation_type == OperationType.SALE else []
    )
    promotion_discount_total = _apply_promotions(operation_type, provisional, promotions)
    if operation_type == 'consumption':
        if discount not in (None, '', 0, '0', '0.00'):
            raise ValidationError({'discount': 'Consumacao nao aceita desconto.'})
        if not beneficiary_user or not UserCompanyAccess.objects.filter(
            user=beneficiary_user, user__is_active=True, company=company, is_active=True
        ).exists():
            raise ValidationError({'beneficiary_user': 'Beneficiario sem acesso ativo a empresa.'})
        charged = strict_decimal(
            charged_amount, field='charged_amount', decimal_places=2, max_digits=14
        )
        if charged < 0 or charged > subtotal:
            raise ValidationError({'charged_amount': 'O valor cobrado deve estar entre zero e o subtotal.'})
        discount_value = Decimal('0.00')
        total = charged
    else:
        discount_value = strict_decimal(
            discount if discount not in (None, '') else '0',
            field='discount', decimal_places=2, max_digits=14,
        )
        remaining = subtotal - promotion_discount_total
        if discount_value < 0 or discount_value > remaining:
            raise ValidationError({'discount': 'O desconto deve estar entre zero e o saldo apos promocoes.'})
        charged = None
        total = remaining - discount_value
    for item in provisional:
        item.pop('product_object')
        item.pop('promotion_object')
    return {
        'operation_type': operation_type,
        'items': provisional,
        'subtotal': subtotal,
        'promotion_discount_total': promotion_discount_total,
        'discount': discount_value,
        'charged_amount': charged,
        'reference_total': subtotal,
        'total': total,
    }


def next_sale_number(company):
    for attempt in range(3):
        try:
            with transaction.atomic():
                Company.objects.select_for_update().get(pk=company.pk)
                latest = Sale.objects.filter(
                    company=company, sale_number__regex=r'^V[0-9]+$'
                ).annotate(sequence=Cast(Substr('sale_number', 2), IntegerField())).aggregate(
                    value=Max('sequence')
                )['value']
                sequence = latest + 1 if latest else 1
                return f'V{sequence:06d}'
        except IntegrityError:
            if attempt == 2:
                raise


def _pk(value):
    return value.pk if hasattr(value, 'pk') else value


def _active_branch(branch, user, permission_code):
    try:
        branch = Branch.objects.select_related('company').get(
            pk=_pk(branch), status=Status.ACTIVE, company__status=Status.ACTIVE,
        )
    except (Branch.DoesNotExist, TypeError, ValueError):
        raise ValidationError({'branch': 'Filial ou empresa inativa/invalida.'})
    if not user.is_superuser and not user_has_branch_permission(user, branch.pk, permission_code):
        raise PermissionDenied('Voce nao possui permissao para esta operacao nesta filial.')
    return branch


def _lock_cash_session(raw_session, branch, *, required):
    if raw_session in (None, ''):
        if required:
            raise ValidationError({'cash_session': 'Informe uma sessao de caixa aberta.'})
        return None
    try:
        session = CashSession.objects.select_for_update().get(pk=_pk(raw_session))
    except (CashSession.DoesNotExist, TypeError, ValueError):
        raise ValidationError({'cash_session': 'Sessao de caixa invalida.'})
    if session.branch_id != branch.pk:
        raise ValidationError({'cash_session': 'A sessao deve pertencer a filial atual.'})
    if session.status != CashSessionStatus.OPEN:
        raise ValidationError({'cash_session': 'A sessao de caixa deve estar aberta.'})
    return session


def _prepare_products(company, raw_items):
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError({'items': 'Informe ao menos um item.'})
    parent_ids = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict) or item.get('product') in (None, ''):
            raise ValidationError({'items': f'Item {index + 1}: informe o produto.'})
        parent_ids.append(item['product'])
    try:
        parent_ids = sorted({int(value) for value in parent_ids})
    except (TypeError, ValueError):
        raise ValidationError({'items': 'Produto invalido.'})
    locked_parents = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=parent_ids).order_by('pk')
    }
    parents = {str(pk): locked_parents[pk] for pk in parent_ids if pk in locked_parents}
    if len(parents) != len(parent_ids):
        raise ValidationError({'items': 'Um ou mais produtos sao invalidos.'})

    component_rows = list(
        ProductComponent.objects.filter(parent_product_id__in=parent_ids)
        .order_by('parent_product_id', 'component_product_id')
    )
    component_ids = sorted({row.component_product_id for row in component_rows})
    components = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(
            pk__in=component_ids
        ).order_by('pk')
    }
    rows_by_parent = {}
    for row in component_rows:
        rows_by_parent.setdefault(row.parent_product_id, []).append(row)

    snapshots, subtotal = _consolidate_items(raw_items, parents)
    requirements = {}
    for index, snapshot in enumerate(snapshots):
        product = snapshot['product_object']
        quantity = snapshot['quantity']
        if product.company_id != company.pk:
            raise PermissionDenied('Produto fora da empresa da filial.')
        if product.status != Status.ACTIVE or not product.is_sellable:
            raise ValidationError({'items': f'Item {index + 1}: produto inativo ou indisponivel para venda.'})

        if product.inventory_behavior == InventoryBehavior.NONE:
            continue
        if product.inventory_behavior == InventoryBehavior.DIRECT:
            requirements[product.pk] = requirements.get(product.pk, Decimal('0')) + quantity
            continue
        rows = rows_by_parent.get(product.pk, [])
        if not rows:
            raise ValidationError({'items': f'Item {index + 1}: produto composto sem composicao.'})
        for row in rows:
            component = components.get(row.component_product_id)
            if (
                not component or component.company_id != company.pk
                or component.status != Status.ACTIVE
                or component.inventory_behavior != InventoryBehavior.DIRECT
            ):
                raise ValidationError({'items': f'Item {index + 1}: a composicao possui componente invalido ou inativo.'})
            required = quantity * row.quantity
            rounded_required = required.quantize(Decimal('0.001'))
            if rounded_required != required:
                raise ValidationError({'items': f'Item {index + 1}: a composicao gera quantidade com mais de tres casas.'})
            required = rounded_required
            requirements[component.pk] = requirements.get(component.pk, Decimal('0')) + required
    return snapshots, requirements, subtotal


def _lock_required_stocks(branch, requirements):
    if not requirements:
        return {}
    stocks = {
        stock.product_id: stock
        for stock in Stock.objects.select_for_update().select_related('product')
        .filter(branch=branch, product_id__in=sorted(requirements)).order_by('product_id', 'pk')
    }
    for product_id in sorted(requirements):
        if product_id not in stocks:
            # Product rows are already locked, serializing this defensive materialization.
            stocks[product_id] = Stock.objects.create(product_id=product_id, branch=branch)
        if stocks[product_id].current_quantity < requirements[product_id]:
            raise ValidationError({
                'stock': f'Saldo insuficiente para o produto {stocks[product_id].product.name} '
                         f'({product_id}).',
            })
    return stocks


def _prepare_payments(company, raw_payments, total, *, free_consumption):
    if not isinstance(raw_payments, list):
        raise ValidationError({'payments': 'Informe uma lista de pagamentos.'})
    if free_consumption:
        if raw_payments:
            raise ValidationError({'payments': 'Consumacao gratuita nao aceita pagamento.'})
        return []
    if total <= 0:
        raise ValidationError({'discount': 'Venda normal deve possuir total maior que zero.'})
    if not raw_payments:
        raise ValidationError({'payments': 'Informe ao menos um pagamento.'})
    method_ids = [item.get('payment_method') for item in raw_payments if isinstance(item, dict)]
    if len(method_ids) != len(raw_payments) or any(value in (None, '') for value in method_ids):
        raise ValidationError({'payments': 'Todos os pagamentos devem informar o metodo.'})
    methods = {
        str(method.pk): method
        for method in PaymentMethod.objects.select_for_update().filter(
            pk__in=method_ids
        ).order_by('pk')
    }
    prepared = []
    paid = Decimal('0.00')
    for index, raw_payment in enumerate(raw_payments):
        method = methods.get(str(raw_payment['payment_method']))
        if not method or method.company_id != company.pk or method.status != Status.ACTIVE:
            raise ValidationError({'payments': f'Pagamento {index + 1}: metodo inativo ou invalido para esta empresa.'})
        amount = strict_decimal(raw_payment.get('amount'), field='amount', decimal_places=2, max_digits=14)
        if amount <= 0:
            raise ValidationError({'payments': f'Pagamento {index + 1}: o valor deve ser maior que zero.'})
        received = strict_decimal(
            raw_payment.get('received_amount'), field='received_amount', decimal_places=2,
            max_digits=14, allow_none=True,
        )
        if method.code == PaymentMethodCode.CASH:
            if received is None or received < amount:
                raise ValidationError({'payments': f'Pagamento {index + 1}: dinheiro exige valor recebido igual ou maior.'})
        elif received is not None:
            raise ValidationError({'payments': f'Pagamento {index + 1}: somente dinheiro aceita valor recebido.'})
        paid += amount
        ensure_money_fits(paid, 'payments')
        prepared.append((method, amount, received))
    if paid != total:
        raise ValidationError({'payments': f'A soma dos pagamentos deve ser {total:.2f}.'})
    return prepared


@transaction.atomic
def finalize_sale(*, branch, user, operation_type, cash_session=None, beneficiary_user=None,
                  items=None, discount=None, charged_amount=None, payments=None):
    operation_timestamp = timezone.now()
    permission = 'sales.create_consumption' if operation_type == OperationType.CONSUMPTION else 'sales.create'
    if operation_type not in OperationType.values:
        raise ValidationError({'operation_type': 'Tipo de operacao invalido.'})
    branch = _active_branch(branch, user, permission)

    if operation_type == OperationType.CONSUMPTION:
        charged = strict_decimal(charged_amount, field='charged_amount', decimal_places=2, max_digits=14)
        if charged < 0:
            raise ValidationError({'charged_amount': 'O valor cobrado nao pode ser negativo.'})
        consumption_discount = strict_decimal(
            discount if discount not in (None, '') else '0', field='discount',
            decimal_places=2, max_digits=14,
        )
        if consumption_discount != 0:
            raise ValidationError({'discount': 'Consumacao nao aceita desconto.'})
        beneficiary_access = UserCompanyAccess.objects.select_related('user').filter(
            user_id=_pk(beneficiary_user), user__is_active=True,
            company=branch.company, is_active=True,
        ).first() if beneficiary_user else None
        if not beneficiary_access:
            raise ValidationError({'beneficiary_user': 'Beneficiario sem acesso ativo a empresa.'})
        beneficiary_user = beneficiary_access.user
        session = _lock_cash_session(cash_session, branch, required=charged > 0)
    else:
        if charged_amount not in (None, ''):
            raise ValidationError({'charged_amount': 'Venda normal nao aceita valor cobrado.'})
        charged = None
        beneficiary_user = None
        session = _lock_cash_session(cash_session, branch, required=True)

    company = Company.objects.select_for_update().get(pk=branch.company_id)
    snapshots, requirements, subtotal = _prepare_products(company, items)
    stocks = _lock_required_stocks(branch, requirements)
    promotions = (
        _eligible_promotions(company, operation_timestamp, lock=True)
        if operation_type == OperationType.SALE else []
    )
    promotion_discount_total = _apply_promotions(operation_type, snapshots, promotions)

    if operation_type == OperationType.CONSUMPTION:
        if charged > subtotal:
            raise ValidationError({'charged_amount': 'O valor cobrado deve estar entre zero e o subtotal.'})
        discount_value = Decimal('0.00')
        promotion_discount_total = Decimal('0.00')
        total = charged
    else:
        discount_value = strict_decimal(
            discount if discount not in (None, '') else '0', field='discount',
            decimal_places=2, max_digits=14,
        )
        remaining = subtotal - promotion_discount_total
        if discount_value < 0 or discount_value > remaining:
            raise ValidationError({'discount': 'O desconto deve estar entre zero e o saldo apos promocoes.'})
        if discount_value and not user.is_superuser and not user_has_branch_permission(
            user, branch.pk, 'sales.apply_discount',
        ):
            raise PermissionDenied('Voce nao possui permissao para aplicar desconto.')
        total = remaining - discount_value

    prepared_payments = _prepare_payments(
        company, payments or [], total,
        free_consumption=(operation_type == OperationType.CONSUMPTION and total == 0),
    )
    sale = Sale.objects.create(
        company=company, branch=branch, cash_session=session,
        sale_number=next_sale_number(company), operation_type=operation_type,
        status=SaleStatus.FINALIZED, created_by=user, beneficiary_user=beneficiary_user,
        subtotal=subtotal, promotion_discount_total=promotion_discount_total,
        discount=discount_value, charged_amount=charged, total=total,
    )
    for snapshot in snapshots:
        promotion = snapshot['promotion_object']
        SaleItem.objects.create(
            sale=sale,
            product=snapshot['product_object'],
            quantity=snapshot['quantity'],
            promotion=promotion,
            promotion_name=snapshot['promotion_name'],
            promotion_discount_type=snapshot['promotion_discount_type'],
            promotion_discount_value=snapshot['promotion_discount_value'],
            promotion_benefit=snapshot['promotion_benefit'],
        )
    for method, amount, received in prepared_payments:
        Payment.objects.create(
            sale=sale, payment_method=method, amount=amount, received_amount=received,
        )
    movement_type = (
        MovementType.CONSUMPTION
        if operation_type == OperationType.CONSUMPTION else MovementType.SALE
    )
    for product_id in sorted(requirements):
        apply_locked_stock(
            stock=stocks[product_id], quantity=-requirements[product_id], user=user,
            movement_type=movement_type, sale=sale,
        )
    return sale


@transaction.atomic
def cancel_sale(*, sale, branch, user, reason=''):
    try:
        sale = Sale.objects.select_for_update().get(pk=_pk(sale))
    except (Sale.DoesNotExist, TypeError, ValueError):
        raise ValidationError({'sale': 'Venda invalida.'})
    permission = (
        'sales.cancel_consumption'
        if sale.operation_type == OperationType.CONSUMPTION else 'sales.cancel'
    )
    branch = _active_branch(branch, user, permission)
    if sale.branch_id != branch.pk:
        raise PermissionDenied('Venda fora da filial atual.')
    if sale.status == SaleStatus.CANCELLED:
        raise ValidationError({'status': 'Esta venda ja foi cancelada.'})
    if sale.cash_session_id:
        CashSession.objects.select_for_update().get(pk=sale.cash_session_id)

    original_type = (
        MovementType.CONSUMPTION
        if sale.operation_type == OperationType.CONSUMPTION else MovementType.SALE
    )
    originals = list(
        StockMovement.objects.select_for_update().filter(
            sale=sale, movement_type=original_type, original_movement__isnull=True,
        ).order_by('stock_id', 'pk')
    )
    stock_ids = sorted({movement.stock_id for movement in originals})
    stocks = {
        stock.pk: stock
        for stock in Stock.objects.select_for_update().filter(pk__in=stock_ids)
        .select_related('product').order_by('product_id', 'pk')
    }
    cancellation_type = (
        MovementType.CONSUMPTION_CANCELLATION
        if sale.operation_type == OperationType.CONSUMPTION
        else MovementType.SALE_CANCELLATION
    )
    for original in originals:
        apply_locked_stock(
            stock=stocks[original.stock_id], quantity=-original.quantity, user=user,
            movement_type=cancellation_type, sale=sale,
            original_movement=original, reason=reason,
        )
    sale.status = SaleStatus.CANCELLED
    sale.cancelled_at = timezone.now()
    sale.cancelled_by = user
    sale.cancellation_reason = (reason or '').strip()
    sale.save(update_fields=(
        'status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at',
    ))
    return sale
