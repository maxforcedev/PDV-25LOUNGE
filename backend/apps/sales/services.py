from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import IntegerField, Max, Q
from django.db.models.functions import Cast, Substr
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.base.audit import audit_log, model_snapshot
from apps.cash.models import CashSession, CashSessionStatus
from apps.companies.models import (
    Branch, BranchSettings, Company, Status, UserBranchAccess, UserCommissionOverride,
    UserCompanyAccess,
)
from apps.companies.selectors import eligible_branch_users, user_has_branch_permission
from apps.inventory.models import MovementType, Stock, StockMovement
from apps.inventory.services import apply_locked_stock
from apps.products.models import BranchProductPrice, InventoryBehavior, Product, ProductComponent, Unit

from .models import (
    OperationType, Payment, PaymentMethod, PaymentMethodCode, Promotion,
    PromotionDiscountType, PromotionSchedule, Sale, SaleItem, SaleStatus, Weekday,
)


DEFAULT_PAYMENT_METHODS = (
    (PaymentMethodCode.CASH, 'Dinheiro'),
    (PaymentMethodCode.PIX, 'PIX'),
    (PaymentMethodCode.CREDIT_CARD, 'Cartão de crédito'),
    (PaymentMethodCode.DEBIT_CARD, 'Cartão de débito'),
)
MAX_MONEY = Decimal('999999999999.99')
CENT = Decimal('0.01')


def _idempotency_value(value):
    if hasattr(value, 'pk'):
        return value.pk
    if isinstance(value, Decimal):
        if value == 0:
            return '0'
        return str(value.normalize())
    if isinstance(value, dict):
        return {
            str(key): _idempotency_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_idempotency_value(item) for item in value]
    if isinstance(value, (datetime, time)):
        return value.isoformat()
    return str(value) if value is not None and not isinstance(value, (str, int, float, bool)) else value


def _idempotency_decimal(value, *, default=None):
    if value in (None, '') and default is not None:
        value = default
    if value is None:
        return None
    if isinstance(value, (float, bool)):
        raise ValidationError('Valores decimais de idempotência devem ser exatos.')
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Valor decimal de idempotência inválido.')
    if not value.is_finite():
        raise ValidationError('Valor decimal de idempotência deve ser finito.')
    return value


def _authorization_identity(authorization):
    if not authorization:
        return None
    user = authorization.get('user')
    return {
        'user': user.pk if hasattr(user, 'pk') else user,
        'method': authorization.get('method'),
    }


def _sale_idempotency_payload(*, actor, operation_type, cash_session, beneficiary_user,
                              seller_user, discount_authorization, items, discount,
                              charged_amount, payments, service_fee_waived,
                              service_fee_authorization, item_discount_authorization):
    def identity(value):
        return value.pk if hasattr(value, 'pk') else value

    canonical_items = [
        {
            'product': identity(item.get('product')),
            'quantity': _idempotency_decimal(item.get('quantity')),
            'discount': _idempotency_decimal(item.get('discount', '0')),
        }
        for item in (items or [])
    ]
    canonical_payments = []
    for payment in payments or []:
        amount = payment.get('amount')
        if amount in (None, '', 'auto', 'remaining'):
            amount = 'remaining'
        else:
            amount = _idempotency_decimal(amount)
        canonical_payments.append({
            'payment_method': identity(payment.get('payment_method')),
            'amount': amount,
            'received_amount': _idempotency_decimal(payment.get('received_amount')),
        })
    return {
        'actor': identity(actor),
        'operation_type': operation_type,
        'cash_session': identity(cash_session),
        'beneficiary_user': identity(beneficiary_user),
        'seller_user': identity(seller_user),
        'discount_authorization': _authorization_identity(discount_authorization),
        'items': canonical_items,
        'discount': _idempotency_decimal(discount, default='0'),
        'charged_amount': (
            None if charged_amount in (None, '')
            else _idempotency_decimal(charged_amount)
        ),
        'payments': canonical_payments,
        'service_fee_waived': bool(service_fee_waived),
        'service_fee_authorization': _authorization_identity(service_fee_authorization),
        'item_discount_authorization': _authorization_identity(item_discount_authorization),
    }


def _sale_idempotency_fingerprint(payload):
    canonical = json.dumps(
        _idempotency_value(payload),
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


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


def _percentage_amount(base, rate, field):
    amount = (base * rate / Decimal('100')).quantize(CENT, rounding=ROUND_HALF_UP)
    ensure_money_fits(amount, field)
    return amount


def _commission_rate_for_seller(branch, seller_user, branch_default):
    if seller_user is None:
        return Decimal('0.00')
    override = UserCommissionOverride.objects.filter(
        branch=branch, user=seller_user,
    ).first()
    if override:
        if not override.receives_commission:
            return Decimal('0.00')
        if override.commission_rate is not None:
            return override.commission_rate
    access = UserBranchAccess.objects.select_related('access_profile').filter(
        branch=branch, user=seller_user, is_active=True, access_profile__status=Status.ACTIVE,
    ).first()
    if access and not access.access_profile.receives_commission:
        return Decimal('0.00')
    if access and access.access_profile.commission_rate is not None:
        return access.access_profile.commission_rate
    return branch_default


def _financial_snapshots(branch, net_subtotal, *, seller_user=None, service_fee_waived=False, lock=False):
    queryset = BranchSettings.objects
    if lock:
        queryset = queryset.select_for_update()
    settings = queryset.filter(branch=branch).first()
    service_fee_rate = settings.service_fee_rate if settings else Decimal('0.00')
    branch_commission_rate = settings.commission_rate if settings else Decimal('0.00')
    commission_rate = _commission_rate_for_seller(branch, seller_user, branch_commission_rate)
    service_fee_amount = (
        Decimal('0.00') if service_fee_waived else _percentage_amount(
            net_subtotal, service_fee_rate, 'service_fee_amount'
        )
    )
    commission_amount = _percentage_amount(
        net_subtotal, commission_rate, 'commission_amount'
    )
    return service_fee_rate, service_fee_amount, commission_rate, commission_amount


def _eligible_sale_user(branch, user, permission_code, field):
    user_id = _pk(user) if user else None
    candidate = eligible_branch_users(branch, permission_code).filter(pk=user_id).first()
    if not candidate:
        raise ValidationError({field: 'Usuário sem acesso ativo e permissão nesta filial.'})
    return candidate


def _discount_approver(
    branch, operator, discount, authorization, *, permission_code, authorization_field
):
    if not discount:
        return None
    if operator.is_superuser or user_has_branch_permission(
        operator, branch.pk, permission_code
    ):
        return operator
    if not authorization or authorization.get('method') != 'password':
        raise ValidationError({authorization_field: 'Autorização de desconto inválida.'})
    approver = _eligible_sale_user(
        branch, authorization.get('user'), permission_code, authorization_field,
    )
    if not approver.check_password(authorization.get('credential') or ''):
        raise ValidationError({authorization_field: 'Autorização de desconto inválida.'})
    return approver


def _service_fee_waiver(branch, operator, waived, authorization):
    if not waived:
        return None
    if operator.is_superuser or user_has_branch_permission(
        operator, branch.pk, 'sales.waive_service_fee'
    ):
        return operator
    if not authorization or authorization.get('method') != 'password':
        raise ValidationError({'service_fee_authorization': 'Autorização para retirar taxa inválida.'})
    approver = _eligible_sale_user(
        branch, authorization.get('user'), 'sales.waive_service_fee',
        'service_fee_authorization',
    )
    if not approver.check_password(authorization.get('credential') or ''):
        raise ValidationError({'service_fee_authorization': 'Autorização para retirar taxa inválida.'})
    return approver


def strict_decimal(value, *, field, decimal_places, max_digits, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, (float, bool)) or value in ('', None):
        raise ValidationError({field: 'Informe um decimal válido como string ou inteiro.'})
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: 'Informe um decimal válido.'})
    if not result.is_finite():
        raise ValidationError({field: 'O valor deve ser finito.'})
    exponent = result.as_tuple().exponent
    places = max(-exponent, 0)
    integer_digits = max(len(result.as_tuple().digits) + exponent, 0)
    if places > decimal_places or integer_digits + places > max_digits:
        raise ValidationError({field: f'Use no máximo {decimal_places} casas decimais.'})
    return result.quantize(Decimal(1).scaleb(-decimal_places))


def ensure_money_fits(value, field):
    if value < 0 or value > MAX_MONEY:
        raise ValidationError({field: 'O valor excede o limite monetário permitido.'})
    return value


def _branch_price_map(branch, product_ids):
    if not branch or not product_ids:
        return {}
    return {
        price.product_id: price.sale_price
        for price in BranchProductPrice.objects.filter(
            branch=branch, product_id__in=product_ids
        )
    }


def _consolidate_items(raw_items, products, *, price_overrides=None):
    price_overrides = price_overrides or {}
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError({'items': 'Informe ao menos um item.'})
    quantities = {}
    discounts = {}
    ordered_ids = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict) or raw_item.get('product') in ('', None):
            raise ValidationError({'items': f'Item {index + 1}: informe o produto.'})
        product = products.get(str(raw_item['product']))
        if not product:
            raise ValidationError({'items': f'Item {index + 1}: produto indisponível nesta empresa.'})
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
            discounts[product.pk] = Decimal('0.00')
        quantities[product.pk] += quantity
        item_discount = strict_decimal(
            raw_item.get('discount', '0'),
            field=f'items.{index}.discount', decimal_places=2, max_digits=14,
        )
        if item_discount < 0:
            raise ValidationError(
                {'items': f'Item {index + 1}: o desconto não pode ser negativo.'}
            )
        discounts[product.pk] += item_discount
        ensure_money_fits(discounts[product.pk], 'items')
        if quantities[product.pk] > Decimal('99999999999.999'):
            raise ValidationError({'items': 'A quantidade consolidada excede o limite permitido.'})

    provisional = []
    subtotal = Decimal('0.00')
    products_by_id = {product.pk: product for product in products.values()}
    for product_id in ordered_ids:
        product = products_by_id[product_id]
        quantity = quantities[product_id]
        unit_price = price_overrides.get(product_id, product.sale_price)
        item_subtotal = (unit_price * quantity).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
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
            'unit_cost': product.cost,
            'unit_price': unit_price,
            'subtotal': item_subtotal,
            'manual_discount_requested': discounts[product_id],
        })
    return provisional, subtotal


def _eligible_promotions(company, timestamp, *, branch=None, lock=False):
    queryset = Promotion.objects.filter(
        company=company,
        status=Status.ACTIVE,
        starts_at__lte=timestamp,
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=timestamp)
    ).filter(
        Q(branch__isnull=True) | Q(branch=branch)
    ).order_by('pk')
    if lock:
        queryset = queryset.select_for_update()
    promotions = list(queryset.prefetch_related('products', 'categories', 'schedules'))
    from datetime import datetime, time

    local_ts = timestamp.astimezone(timezone.get_current_timezone())
    weekday = local_ts.weekday()
    # Python weekday(): Monday=0..Sunday=6; our Weekday uses Sunday=0..Saturday=6.
    weekday_map = {0: Weekday.MONDAY, 1: Weekday.TUESDAY, 2: Weekday.WEDNESDAY,
                   3: Weekday.THURSDAY, 4: Weekday.FRIDAY, 5: Weekday.SATURDAY,
                   6: Weekday.SUNDAY}
    today_code = weekday_map[weekday]
    now_time = local_ts.time()
    eligible = []
    for promotion in promotions:
        schedules = list(promotion.schedules.all())
        if not schedules:
            # No weekly schedule: valid all day within the starts_at/ends_at window.
            eligible.append(promotion)
            continue
        active = False
        for schedule in schedules:
            if schedule.weekday != today_code:
                continue
            if schedule.start_time <= schedule.end_time:
                if schedule.start_time <= now_time < schedule.end_time:
                    active = True
                    break
            else:
                # Overnight interval wrapping midnight.
                if now_time >= schedule.start_time or now_time < schedule.end_time:
                    active = True
                    break
        if active:
            eligible.append(promotion)
    return eligible


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
                    # Fixed amount is a per-unit benefit: multiply by the item quantity.
                    benefit = (
                        promotion.discount_value * item['quantity']
                    ).quantize(CENT, rounding=ROUND_HALF_UP)
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
        manual_discount = item['manual_discount_requested']
        if operation_type == OperationType.CONSUMPTION and manual_discount:
            raise ValidationError({'items': 'Consumação não aceita desconto por item.'})
        if manual_discount > item['subtotal'] - benefit:
            raise ValidationError({
                'items': f'O desconto do item {item["product_name"]} excede o saldo após a promoção.'
            })
        item.update({
            'promotion': promotion.pk if promotion else None,
            'promotion_object': promotion,
            'promotion_name': promotion.name if promotion else None,
            'promotion_discount_type': promotion.discount_type if promotion else None,
            'promotion_discount_value': promotion.discount_value if promotion else None,
            'promotion_benefit': benefit,
            'manual_discount': manual_discount,
            'net_subtotal': item['subtotal'] - benefit - manual_discount,
        })
    return (
        sum((item['promotion_benefit'] for item in items), Decimal('0.00')),
        sum((item['manual_discount'] for item in items), Decimal('0.00')),
    )


def calculate_preview(*, company, operation_type, raw_items, discount, charged_amount, beneficiary_user, branch=None, service_fee_waived=False):
    if operation_type not in OperationType.values:
        raise ValidationError({'operation_type': 'Tipo de operação inválido.'})
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
    price_overrides = _branch_price_map(branch, [pid for pid in product_ids if str(pid).isdigit()])
    provisional, subtotal = _consolidate_items(raw_items, products, price_overrides=price_overrides)
    operation_timestamp = timezone.now()
    promotions = (
        _eligible_promotions(company, operation_timestamp, branch=branch)
        if operation_type == OperationType.SALE else []
    )
    promotion_discount_total, item_discount_total = _apply_promotions(
        operation_type, provisional, promotions
    )
    if operation_type == 'consumption':
        if discount not in (None, '', 0, '0', '0.00'):
            raise ValidationError({'discount': 'Consumação não aceita desconto.'})
        if not beneficiary_user or not UserCompanyAccess.objects.filter(
            user=beneficiary_user, user__is_active=True, company=company, is_active=True
        ).exists():
            raise ValidationError({'beneficiary_user': 'Beneficiário sem acesso ativo à empresa.'})
        charged = strict_decimal(
            charged_amount, field='charged_amount', decimal_places=2, max_digits=14
        )
        if charged < 0 or charged > subtotal:
            raise ValidationError({'charged_amount': 'O valor cobrado deve estar entre zero e o subtotal.'})
        discount_value = Decimal('0.00')
        service_fee_rate = Decimal('0.00')
        service_fee_amount = Decimal('0.00')
        commission_rate = Decimal('0.00')
        commission_amount = Decimal('0.00')
        total = charged
    else:
        discount_value = strict_decimal(
            discount if discount not in (None, '') else '0',
            field='discount', decimal_places=2, max_digits=14,
        )
        remaining = subtotal - promotion_discount_total - item_discount_total
        if discount_value < 0 or discount_value > remaining:
            raise ValidationError({'discount': 'O desconto deve estar entre zero e o saldo após promoções.'})
        charged = None
        net_subtotal = remaining - discount_value
        (
            service_fee_rate,
            service_fee_amount,
            commission_rate,
            commission_amount,
        ) = _financial_snapshots(
            branch, net_subtotal, service_fee_waived=bool(service_fee_waived)
        )
        total = net_subtotal + service_fee_amount
        ensure_money_fits(total, 'total')
    for item in provisional:
        item.pop('product_object')
        item.pop('promotion_object')
        item.pop('manual_discount_requested')
    return {
        'operation_type': operation_type,
        'items': provisional,
        'subtotal': subtotal,
        'promotion_discount_total': promotion_discount_total,
        'item_discount_total': item_discount_total,
        'discount': discount_value,
        'service_fee_rate': service_fee_rate,
        'service_fee_amount': service_fee_amount,
        'service_fee_waived': bool(service_fee_waived) if operation_type == OperationType.SALE else False,
        'commission_rate': commission_rate,
        'commission_amount': commission_amount,
        'charged_amount': charged,
        'reference_total': subtotal,
        'total': total,
    }


def next_sale_number(company):
    for attempt in range(3):
        try:
            with transaction.atomic():
                # Sale numbering remains serialized per company to preserve monotonic uniqueness.
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


def _promotion_effective_products(promotion):
    product_ids = set(promotion.products.values_list('pk', flat=True))
    if promotion.categories.exists():
        from apps.products.models import Product
        category_ids = set(promotion.categories.values_list('pk', flat=True))
        product_ids = product_ids | set(
            Product.objects.filter(category_id__in=category_ids).values_list('pk', flat=True)
        )
    return product_ids


def _branches_overlap(branch_a, branch_b):
    # null branch means "all branches". Overlap when equal, or either is null.
    if branch_a is None or branch_b is None:
        return True
    return branch_a == branch_b


def _date_windows_overlap(start_a, end_a, start_b, end_b):
    # end=None means open-ended (infinite). Windows [start, end) overlap.
    far_future = datetime(9999, 12, 31, 23, 59, tzinfo=timezone.get_default_timezone())
    a_end = end_a if end_a is not None else far_future
    b_end = end_b if end_b is not None else far_future
    return start_a < b_end and start_b < a_end


def _schedules_overlap(schedules_a, schedules_b):
    # If either side has no schedule, it is active all day on every weekday it exists.
    if not schedules_a or not schedules_b:
        return True
    by_day_a = {}
    for s in schedules_a:
        by_day_a.setdefault(s.weekday, []).append((s.start_time, s.end_time))
    by_day_b = {}
    for s in schedules_b:
        by_day_b.setdefault(s.weekday, []).append((s.start_time, s.end_time))
    for weekday, intervals_a in by_day_a.items():
        intervals_b = by_day_b.get(weekday)
        if not intervals_b:
            continue
        for (a_start, a_end) in intervals_a:
            for (b_start, b_end) in intervals_b:
                # Normalize overnight intervals into [start, 24:00) + [00:00, end).
                def span(start, end):
                    if start <= end:
                        return [(start, end)]
                    return [(start, time(23, 59, 59)), (time(0, 0), end)]
                for a_s, a_e in span(a_start, a_end):
                    for b_s, b_e in span(b_start, b_end):
                        if a_s < b_e and b_s < a_e:
                            return True
    return False


def detect_promotion_conflict(promotion):
    """Return a conflict description string if promotion conflicts with another active
    promotion in the same company; otherwise return None."""
    promotion._effective_products = _promotion_effective_products(promotion)
    if not promotion._effective_products:
        return None
    competitors = (
        Promotion.objects.filter(
            company_id=promotion.company_id, status=Status.ACTIVE
        ).exclude(pk=promotion.pk)
        .prefetch_related('products', 'categories', 'schedules')
    )
    for other in competitors:
        if not _branches_overlap(promotion.branch_id, other.branch_id):
            continue
        other_products = _promotion_effective_products(other)
        if not other_products or not (promotion._effective_products & other_products):
            continue
        if not _date_windows_overlap(promotion.starts_at, promotion.ends_at, other.starts_at, other.ends_at):
            continue
        own_schedules = list(promotion.schedules.all())
        other_schedules = list(other.schedules.all())
        if not _schedules_overlap(own_schedules, other_schedules):
            continue
        branch_label = (
            'Todas as filiais' if promotion.branch_id is None
            else promotion.branch.name
        )
        other_branch_label = (
            'Todas as filiais' if other.branch_id is None
            else other.branch.name
        )
        return (
            f'Conflito com a promoção "{other.name}" ({other_branch_label}). '
            f'Esta promoção ({branch_label}) compartilha produtos/categorias, '
            'vigência e horário sobrepostos. Ajuste alvos, filial, vigência ou agenda.'
        )
    return None


def _pk(value):
    return value.pk if hasattr(value, 'pk') else value


def _active_branch(branch, user, permission_code):
    try:
        branch = Branch.objects.select_related('company').get(
            pk=_pk(branch), status=Status.ACTIVE, company__status=Status.ACTIVE,
        )
    except (Branch.DoesNotExist, TypeError, ValueError):
        raise ValidationError({'branch': 'Filial ou empresa inativa ou inválida.'})
    if not user.is_superuser and not user_has_branch_permission(user, branch.pk, permission_code):
        raise PermissionDenied('Você não possui permissão para esta operação nesta filial.')
    return branch


def _lock_cash_session(raw_session, branch, *, required):
    if raw_session in (None, ''):
        if required:
            raise ValidationError({'cash_session': 'Informe uma sessão de caixa aberta.'})
        return None
    try:
        session = CashSession.objects.select_for_update().get(pk=_pk(raw_session))
    except (CashSession.DoesNotExist, TypeError, ValueError):
        raise ValidationError({'cash_session': 'Sessão de caixa inválida.'})
    if session.branch_id != branch.pk:
        raise ValidationError({'cash_session': 'A sessão deve pertencer à filial atual.'})
    if session.status != CashSessionStatus.OPEN:
        raise ValidationError({'cash_session': 'A sessão de caixa deve estar aberta.'})
    return session


def _prepare_products(company, raw_items, *, branch=None):
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
        raise ValidationError({'items': 'Produto inválido.'})
    locked_parents = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=parent_ids).order_by('pk')
    }
    parents = {str(pk): locked_parents[pk] for pk in parent_ids if pk in locked_parents}
    if len(parents) != len(parent_ids):
        raise ValidationError({'items': 'Um ou mais produtos são inválidos.'})

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

    price_overrides = _branch_price_map(branch, parent_ids)
    snapshots, subtotal = _consolidate_items(raw_items, parents, price_overrides=price_overrides)
    requirements = {}
    for index, snapshot in enumerate(snapshots):
        product = snapshot['product_object']
        quantity = snapshot['quantity']
        snapshot['component_cost_snapshot'] = []
        if product.company_id != company.pk:
            raise PermissionDenied('Produto fora da empresa da filial.')
        if product.status != Status.ACTIVE or not product.is_sellable:
            raise ValidationError({'items': f'Item {index + 1}: produto inativo ou indisponível para venda.'})

        if product.inventory_behavior == InventoryBehavior.NONE:
            continue
        if product.inventory_behavior == InventoryBehavior.DIRECT:
            requirements[product.pk] = requirements.get(product.pk, Decimal('0')) + quantity
            continue
        rows = rows_by_parent.get(product.pk, [])
        if not rows:
            raise ValidationError({'items': f'Item {index + 1}: produto composto sem composição.'})
        compound_unit_cost = Decimal('0.00')
        component_cost_snapshot = []
        for row in rows:
            component = components.get(row.component_product_id)
            if (
                not component or component.company_id != company.pk
                or component.status != Status.ACTIVE
                or component.inventory_behavior != InventoryBehavior.DIRECT
            ):
                raise ValidationError({'items': f'Item {index + 1}: a composição possui componente inválido ou inativo.'})
            required = quantity * row.quantity
            rounded_required = required.quantize(Decimal('0.001'))
            if rounded_required != required:
                raise ValidationError({'items': f'Item {index + 1}: a composição gera quantidade com mais de três casas.'})
            required = rounded_required
            requirements[component.pk] = requirements.get(component.pk, Decimal('0')) + required
            cost_contribution = component.cost * row.quantity
            compound_unit_cost += cost_contribution
            component_cost_snapshot.append({
                'product': component.pk,
                'product_name': component.name,
                'internal_code': component.internal_code,
                'unit': component.unit,
                'quantity_per_unit': format(row.quantity, 'f'),
                'consumed_quantity': format(required, 'f'),
                'unit_cost': f'{component.cost:.2f}',
                'unit_cost_contribution': (
                    f'{cost_contribution.quantize(CENT, rounding=ROUND_HALF_UP):.2f}'
                ),
            })
        snapshot['unit_cost'] = compound_unit_cost.quantize(CENT, rounding=ROUND_HALF_UP)
        ensure_money_fits(snapshot['unit_cost'], 'unit_cost')
        snapshot['component_cost_snapshot'] = component_cost_snapshot
    return snapshots, requirements, subtotal


def _lock_required_stocks(branch, requirements):
    if not requirements:
        return {}
    allow_negative = False
    from apps.companies.models import BranchSettings
    branch_settings = BranchSettings.objects.filter(branch=branch).first()
    allow_negative = bool(branch_settings and branch_settings.allow_negative_stock)
    stocks = {
        stock.product_id: stock
        for stock in Stock.objects.select_for_update().select_related('product')
        .filter(branch=branch, product_id__in=sorted(requirements)).order_by('product_id', 'pk')
    }
    for product_id in sorted(requirements):
        if product_id not in stocks:
            # Product rows are already locked, serializing this defensive materialization.
            stocks[product_id] = Stock.objects.create(product_id=product_id, branch=branch)
        if not allow_negative and stocks[product_id].current_quantity < requirements[product_id]:
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
            raise ValidationError({'payments': 'Consumação gratuita não aceita pagamento.'})
        return []
    if total <= 0:
        raise ValidationError({'discount': 'Venda normal deve possuir total maior que zero.'})
    if not raw_payments:
        raise ValidationError({'payments': 'Informe ao menos um pagamento.'})
    method_ids = [item.get('payment_method') for item in raw_payments if isinstance(item, dict)]
    if len(method_ids) != len(raw_payments) or any(value in (None, '') for value in method_ids):
        raise ValidationError({'payments': 'Todos os pagamentos devem informar o método.'})
    methods = {
        str(method.pk): method
        for method in PaymentMethod.objects.select_for_update().filter(
            pk__in=method_ids
        ).order_by('pk')
    }
    explicit_rows = []
    remaining_cash_rows = []
    for index, raw_payment in enumerate(raw_payments):
        method = methods.get(str(raw_payment['payment_method']))
        if not method or method.company_id != company.pk or method.status != Status.ACTIVE:
            raise ValidationError({'payments': f'Pagamento {index + 1}: método inativo ou inválido para esta empresa.'})
        raw_amount = raw_payment.get('amount')
        is_remaining_cash = (
            method.code == PaymentMethodCode.CASH
            and (raw_amount in (None, '', 'auto', 'remaining'))
        )
        received = strict_decimal(
            raw_payment.get('received_amount'), field='received_amount', decimal_places=2,
            max_digits=14, allow_none=True,
        )
        if method.code != PaymentMethodCode.CASH and received is not None:
            raise ValidationError({'payments': f'Pagamento {index + 1}: somente dinheiro aceita valor recebido.'})
        if is_remaining_cash:
            if received is None:
                raise ValidationError({'payments': f'Pagamento {index + 1}: informe o valor recebido em dinheiro.'})
            remaining_cash_rows.append((index, method, received))
            continue
        amount = strict_decimal(raw_amount, field='amount', decimal_places=2, max_digits=14)
        if amount <= 0:
            raise ValidationError({'payments': f'Pagamento {index + 1}: o valor deve ser maior que zero.'})
        if method.code == PaymentMethodCode.CASH and (received is None or received < amount):
            raise ValidationError({'payments': f'Pagamento {index + 1}: dinheiro exige valor recebido igual ou maior.'})
        explicit_rows.append((index, method, amount, received))

    explicit_total = sum((row[2] for row in explicit_rows), Decimal('0.00'))
    ensure_money_fits(explicit_total, 'payments')
    if explicit_total > total:
        raise ValidationError({'payments': 'A soma dos pagamentos informados excede o total.'})
    remaining = (total - explicit_total).quantize(CENT)
    if remaining < 0:
        raise ValidationError({'payments': 'A soma dos pagamentos informados excede o total.'})
    if not remaining_cash_rows and remaining != 0:
        raise ValidationError({'payments': f'A soma dos pagamentos deve ser {total:.2f}.'})
    if len(remaining_cash_rows) > 1:
        raise ValidationError({'payments': 'Informe o valor de cada pagamento em dinheiro quando houver mais de um.'})
    prepared = []
    paid = Decimal('0.00')
    for index, method, amount, received in explicit_rows:
        paid += amount
        ensure_money_fits(paid, 'payments')
        prepared.append((method, amount, received))
    for index, method, received in remaining_cash_rows:
        amount = remaining
        if amount <= 0 and total > 0:
            raise ValidationError({'payments': f'Pagamento {index + 1}: o saldo restante em dinheiro deve ser maior que zero.'})
        if received < amount:
            raise ValidationError({'payments': f'Pagamento {index + 1}: dinheiro exige valor recebido igual ou maior.'})
        paid += amount
        ensure_money_fits(paid, 'payments')
        prepared.append((method, amount, received))
    if paid != total:
        raise ValidationError({'payments': f'A soma dos pagamentos deve ser {total:.2f}.'})
    return prepared


@transaction.atomic
def finalize_sale(*, branch, user, operation_type, cash_session=None, beneficiary_user=None,
                  seller_user=None, discount_authorization=None, items=None, discount=None,
                  charged_amount=None, payments=None, service_fee_waived=False,
                  service_fee_authorization=None, item_discount_authorization=None,
                  idempotency_key=None):
    operation_timestamp = timezone.now()
    permission = 'sales.create_consumption' if operation_type == OperationType.CONSUMPTION else 'sales.create'
    if operation_type not in OperationType.values:
        raise ValidationError({'operation_type': 'Tipo de operação inválido.'})
    branch = _active_branch(branch, user, permission)
    if not idempotency_key:
        raise ValidationError({'idempotency_key': 'Informe a chave de idempotência.'})
    company = Company.objects.select_for_update().get(pk=branch.company_id)
    fingerprint = _sale_idempotency_fingerprint(_sale_idempotency_payload(
        actor=user,
        operation_type=operation_type,
        cash_session=cash_session,
        beneficiary_user=beneficiary_user,
        seller_user=seller_user,
        discount_authorization=discount_authorization,
        items=items,
        discount=discount,
        charged_amount=charged_amount,
        payments=payments,
        service_fee_waived=service_fee_waived,
        service_fee_authorization=service_fee_authorization,
        item_discount_authorization=item_discount_authorization,
    ))
    replay = Sale.objects.filter(
        company=company,
        branch=branch,
        operation_type=operation_type,
        idempotency_key=idempotency_key,
    ).first()
    if replay:
        if not replay.idempotency_fingerprint:
            from apps.base.exceptions import DomainValidationError

            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='A chave pertence a uma venda sem fingerprint seguro; use uma nova chave.',
                details={
                    'idempotency_key': str(idempotency_key),
                    'requires_new_key': True,
                    'reason': 'missing_safe_fingerprint',
                },
            )
        if replay.idempotency_fingerprint != fingerprint:
            from apps.base.exceptions import DomainValidationError

            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='A chave de idempotência já foi usada com outros dados.',
                details={'idempotency_key': str(idempotency_key)},
            )
        replay._idempotency_replayed = True
        return replay

    if operation_type == OperationType.CONSUMPTION:
        charged = strict_decimal(charged_amount, field='charged_amount', decimal_places=2, max_digits=14)
        if charged < 0:
            raise ValidationError({'charged_amount': 'O valor cobrado não pode ser negativo.'})
        consumption_discount = strict_decimal(
            discount if discount not in (None, '') else '0', field='discount',
            decimal_places=2, max_digits=14,
        )
        if consumption_discount != 0:
            raise ValidationError({'discount': 'Consumação não aceita desconto.'})
        beneficiary_access = UserCompanyAccess.objects.select_related('user').filter(
            user_id=_pk(beneficiary_user), user__is_active=True,
            company=branch.company, is_active=True,
        ).first() if beneficiary_user else None
        if not beneficiary_access:
            raise ValidationError({'beneficiary_user': 'Beneficiário sem acesso ativo à empresa.'})
        beneficiary_user = beneficiary_access.user
        seller_user = None
        session = _lock_cash_session(cash_session, branch, required=charged > 0)
    else:
        if charged_amount not in (None, ''):
            raise ValidationError({'charged_amount': 'Venda normal não aceita valor cobrado.'})
        charged = None
        beneficiary_user = None
        seller_user = _eligible_sale_user(
            branch, seller_user, 'sales.create', 'seller_user'
        )
        session = _lock_cash_session(cash_session, branch, required=True)

    snapshots, requirements, subtotal = _prepare_products(company, items, branch=branch)
    stocks = _lock_required_stocks(branch, requirements)
    promotions = (
        _eligible_promotions(company, operation_timestamp, branch=branch, lock=True)
        if operation_type == OperationType.SALE else []
    )
    promotion_discount_total, item_discount_total = _apply_promotions(
        operation_type, snapshots, promotions
    )

    if operation_type == OperationType.CONSUMPTION:
        if charged > subtotal:
            raise ValidationError({'charged_amount': 'O valor cobrado deve estar entre zero e o subtotal.'})
        discount_value = Decimal('0.00')
        promotion_discount_total = Decimal('0.00')
        item_discount_total = Decimal('0.00')
        discount_approved_by = None
        item_discount_approved_by = None
        service_fee_waived = False
        service_fee_waived_by = None
        service_fee_rate = Decimal('0.00')
        service_fee_amount = Decimal('0.00')
        commission_rate = Decimal('0.00')
        commission_amount = Decimal('0.00')
        total = charged
    else:
        discount_value = strict_decimal(
            discount if discount not in (None, '') else '0', field='discount',
            decimal_places=2, max_digits=14,
        )
        remaining = subtotal - promotion_discount_total - item_discount_total
        if discount_value < 0 or discount_value > remaining:
            raise ValidationError({'discount': 'O desconto deve estar entre zero e o saldo após promoções.'})
        discount_approved_by = _discount_approver(
            branch, user, discount_value, discount_authorization,
            permission_code='sales.apply_discount',
            authorization_field='discount_authorization',
        )
        item_discount_approved_by = _discount_approver(
            branch, user, item_discount_total, item_discount_authorization,
            permission_code='sales.apply_item_discount',
            authorization_field='item_discount_authorization',
        )
        service_fee_waived_by = _service_fee_waiver(
            branch, user, bool(service_fee_waived), service_fee_authorization
        )
        net_subtotal = remaining - discount_value
        (
            service_fee_rate,
            service_fee_amount,
            commission_rate,
            commission_amount,
        ) = _financial_snapshots(
            branch, net_subtotal, seller_user=seller_user,
            service_fee_waived=bool(service_fee_waived), lock=True,
        )
        total = net_subtotal + service_fee_amount
        ensure_money_fits(total, 'total')

    prepared_payments = _prepare_payments(
        company, payments or [], total,
        free_consumption=(operation_type == OperationType.CONSUMPTION and total == 0),
    )
    sale = Sale.objects.create(
        company=company, branch=branch, cash_session=session,
        sale_number=next_sale_number(company), operation_type=operation_type,
        idempotency_key=idempotency_key, idempotency_fingerprint=fingerprint,
        status=SaleStatus.FINALIZED, created_by=user, seller_user=seller_user,
        discount_approved_by=discount_approved_by, beneficiary_user=beneficiary_user,
        subtotal=subtotal, promotion_discount_total=promotion_discount_total,
        item_discount_total=item_discount_total,
        discount=discount_value, service_fee_rate=service_fee_rate,
        service_fee_amount=service_fee_amount, commission_rate=commission_rate,
        commission_amount=commission_amount, charged_amount=charged, total=total,
        service_fee_waived=bool(service_fee_waived), service_fee_waived_by=service_fee_waived_by,
    )
    for snapshot in snapshots:
        promotion = snapshot['promotion_object']
        SaleItem.objects.create(
            sale=sale,
            product=snapshot['product_object'],
            quantity=snapshot['quantity'],
            unit_cost=snapshot.get('unit_cost'),
            unit_price=snapshot.get('unit_price'),
            promotion=promotion,
            promotion_name=snapshot['promotion_name'],
            promotion_discount_type=snapshot['promotion_discount_type'],
            promotion_discount_value=snapshot['promotion_discount_value'],
            promotion_benefit=snapshot['promotion_benefit'],
            manual_discount=snapshot['manual_discount'],
            discount_approved_by=(
                item_discount_approved_by if snapshot['manual_discount'] else None
            ),
            component_cost_snapshot=snapshot['component_cost_snapshot'],
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
    item_snapshots = [
        {
            'product': snapshot['product'],
            'product_name': snapshot['product_name'],
            'quantity': format(snapshot['quantity'], 'f'),
            'unit_cost': f'{snapshot["unit_cost"]:.2f}',
            'unit_price': f'{snapshot["unit_price"]:.2f}',
            'promotion_discount': f'{snapshot["promotion_benefit"]:.2f}',
            'manual_item_discount': f'{snapshot["manual_discount"]:.2f}',
            'item_discount_approved_by': (
                item_discount_approved_by.pk
                if snapshot['manual_discount'] and item_discount_approved_by else None
            ),
            'component_cost_snapshot': snapshot['component_cost_snapshot'],
        }
        for snapshot in snapshots
    ]
    audit_log(
        actor=user,
        action='sale.finalize' if operation_type == OperationType.SALE else 'consumption.finalize',
        obj=sale,
        company=company,
        branch=branch,
        after=model_snapshot(
            sale,
            ('sale_number', 'operation_type', 'idempotency_key', 'subtotal',
             'promotion_discount_total', 'item_discount_total', 'discount',
             'service_fee_rate', 'service_fee_amount', 'service_fee_waived', 'commission_rate',
             'commission_amount', 'total', 'seller_user_id', 'discount_approved_by_id',
             'service_fee_waived_by_id', 'beneficiary_user_id', 'charged_amount',
             'cash_session_id'),
        ),
        metadata={
            'items': item_snapshots,
            'payments': [
                {
                    'payment_method': method.pk,
                    'payment_method_name': method.name,
                    'amount': f'{amount:.2f}',
                    'received_amount': f'{received:.2f}' if received is not None else None,
                }
                for method, amount, received in prepared_payments
            ],
            'discount_authorization': {
                'method': (discount_authorization or {}).get('method'),
                'approved_by': discount_approved_by.pk if discount_approved_by else None,
            } if discount_value else None,
            'item_discount_authorization': {
                'method': (item_discount_authorization or {}).get('method'),
                'approved_by': item_discount_approved_by.pk if item_discount_approved_by else None,
            } if item_discount_total else None,
            'service_fee_authorization': {
                'method': (service_fee_authorization or {}).get('method'),
                'approved_by': service_fee_waived_by.pk if service_fee_waived_by else None,
            } if service_fee_waived else None,
        },
    )
    return sale


@transaction.atomic
def cancel_sale(*, sale, branch, user, reason=''):
    try:
        sale = Sale.objects.select_for_update().get(pk=_pk(sale))
    except (Sale.DoesNotExist, TypeError, ValueError):
        raise ValidationError({'sale': 'Venda inválida.'})
    permission = (
        'sales.cancel_consumption'
        if sale.operation_type == OperationType.CONSUMPTION else 'sales.cancel'
    )
    branch = _active_branch(branch, user, permission)
    if sale.branch_id != branch.pk:
        raise PermissionDenied('Venda fora da filial atual.')
    if sale.status == SaleStatus.CANCELLED:
        raise ValidationError({'status': 'Esta venda já foi cancelada.'})
    if sale.cash_session_id:
        session = CashSession.objects.select_for_update().get(pk=sale.cash_session_id)
        if session.status != CashSessionStatus.OPEN:
            raise ValidationError(
                {'cash_session': 'Não é possível cancelar uma operação após o fechamento da sessão de caixa.'}
            )

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
    audit_log(
        actor=user,
        action='sale.cancel' if sale.operation_type == OperationType.SALE else 'consumption.cancel',
        obj=sale,
        company=sale.company,
        branch=branch,
        before={'status': SaleStatus.FINALIZED},
        after=model_snapshot(sale, ('status', 'cancelled_at', 'cancelled_by_id', 'cancellation_reason')),
    )
    return sale
