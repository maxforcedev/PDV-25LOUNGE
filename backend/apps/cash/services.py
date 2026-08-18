from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.base.audit import audit_log, model_snapshot
from apps.companies.models import Branch, Status, UserCompanyAccess
from apps.companies.selectors import user_has_branch_permission

from .models import (
    CashMovement,
    CashMovementType,
    CashRegister,
    CashRegisterStatus,
    CashSession,
    CashSessionStatus,
    WithdrawalCategory,
)


def parse_money(value, field, *, positive=False, nonnegative=False):
    if isinstance(value, float):
        raise ValidationError({field: 'Envie valores monetários como texto, nunca float.'})
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: 'Informe um valor decimal válido.'})
    if not value.is_finite():
        raise ValidationError({field: 'Informe um valor decimal finito.'})
    if value.as_tuple().exponent < -2:
        raise ValidationError({field: 'Use no máximo duas casas decimais.'})
    if positive and value <= 0:
        raise ValidationError({field: 'O valor deve ser maior que zero.'})
    if nonnegative and value < 0:
        raise ValidationError({field: 'O valor não pode ser negativo.'})
    if value.copy_abs() >= Decimal('1000000000000'):
        raise ValidationError({field: 'O valor excede o limite permitido.'})
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _pk(value):
    return value.pk if hasattr(value, 'pk') else value


def _validate_current_branch(current_branch, object_branch, user, permission_code):
    if current_branch is None:
        if not user.is_superuser:
            raise PermissionDenied('Informe a filial atual em X-Branch-ID.')
        current_branch = object_branch
    try:
        current_branch_id = _pk(current_branch)
    except (TypeError, ValueError):
        raise PermissionDenied('Filial atual inválida.')
    if str(current_branch_id) != str(object_branch.pk):
        raise PermissionDenied('Objeto fora da filial atual.')
    if not user_has_branch_permission(user, object_branch.pk, permission_code):
        raise PermissionDenied('Você não possui permissão nesta filial.')


def _validate_operational(register):
    if register.branch.company.status != Status.ACTIVE:
        raise ValidationError({'company': 'A empresa deve estar ativa.'})
    if register.branch.status != Status.ACTIVE:
        raise ValidationError({'branch': 'A filial deve estar ativa.'})
    if register.status != CashRegisterStatus.ACTIVE:
        raise ValidationError({'cash_register': 'O caixa deve estar ativo.'})


def open_session(cash_register, opening_amount, user, current_branch):
    opening_amount = parse_money(
        opening_amount, 'opening_amount', nonnegative=True
    )
    try:
        with transaction.atomic():
            try:
                register = CashRegister.objects.select_for_update().select_related(
                    'branch', 'branch__company'
                ).get(pk=_pk(cash_register))
            except (CashRegister.DoesNotExist, TypeError, ValueError):
                raise ValidationError({'cash_register': 'Caixa inválido.'})
            _validate_current_branch(
                current_branch, register.branch, user, 'cash_registers.open'
            )
            _validate_operational(register)
            if CashSession.objects.filter(
                cash_register=register, status=CashSessionStatus.OPEN
            ).exists():
                raise ValidationError(
                    {'cash_register': 'Este caixa já possui uma sessão aberta.'}
                )
            session = CashSession.objects.create(
                cash_register=register,
                branch=register.branch,
                opened_by=user,
                opened_at=timezone.now(),
                opening_amount=opening_amount,
            )
            audit_log(actor=user, action='cash_session.open', obj=session, company=register.branch.company, branch=register.branch, after=model_snapshot(session, ('cash_register_id', 'opening_amount', 'status')))
            return session
    except IntegrityError as error:
        constraint = getattr(getattr(error.__cause__, 'diag', None), 'constraint_name', None)
        if constraint == 'cash_session_one_open_per_register':
            raise ValidationError(
                {'cash_register': 'Este caixa já possui uma sessão aberta.'}
            )
        raise


def _record_movement(
    *, cash_session, amount, user, reason, current_branch, movement_type, permission_code,
    operation_reference, withdrawal_category=None, beneficiary_user=None, result_effect=None,
):
    amount = parse_money(amount, 'amount', positive=True)
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo da movimentação.'})
    with transaction.atomic():
        try:
            session = CashSession.objects.select_for_update().select_related(
                'cash_register', 'branch', 'branch__company'
            ).get(pk=_pk(cash_session))
        except (CashSession.DoesNotExist, TypeError, ValueError):
            raise ValidationError({'cash_session': 'Sessão de caixa inválida.'})
        _validate_current_branch(current_branch, session.branch, user, permission_code)
        if session.opened_by_id != user.pk and not user_has_branch_permission(
            user, session.branch_id, 'cash_registers.administer_others'
        ):
            raise PermissionDenied('Você não pode operar uma sessão aberta por outro usuário.')
        effective_result = result_effect or 'neutral'
        beneficiary_id = _pk(beneficiary_user) if beneficiary_user is not None else None
        existing = CashMovement.objects.filter(
            cash_session=session,
            movement_type=movement_type,
            operation_reference=operation_reference,
        ).first()
        if existing:
            coherent = (
                existing.amount == amount
                and existing.reason == reason
                and existing.withdrawal_category == withdrawal_category
                and existing.beneficiary_user_id == beneficiary_id
                and existing.result_effect == effective_result
                and existing.user_id == user.pk
            )
            if not coherent:
                from apps.base.exceptions import DomainValidationError
                raise DomainValidationError(
                    code='idempotency_key_conflict',
                    message='A chave de idempotência já foi usada com outros dados.',
                    details={'operation_reference': str(operation_reference)},
                )
            existing._idempotency_replayed = True
            return existing
        _validate_operational(session.cash_register)
        if session.status != CashSessionStatus.OPEN:
            raise ValidationError({'cash_session': 'A sessão de caixa está fechada.'})
        beneficiary = None
        if beneficiary_user is not None:
            access = UserCompanyAccess.objects.select_related('user').filter(
                user_id=beneficiary_id,
                user__is_active=True,
                company_id=session.branch.company_id,
                is_active=True,
            ).first()
            if not access:
                raise ValidationError(
                    {'beneficiary_user': 'Beneficiário sem acesso ativo a esta empresa.'}
                )
            beneficiary = access.user
        required_types = {
            WithdrawalCategory.DJ: User.UserType.DJ,
            WithdrawalCategory.ARTIST: User.UserType.ARTIST,
            WithdrawalCategory.PROMOTER: User.UserType.PROMOTER,
        }
        if withdrawal_category in required_types:
            if beneficiary is None:
                raise ValidationError(
                    {'beneficiary_user': 'Informe o beneficiário desta sangria.'}
                )
            if beneficiary.user_type != required_types[withdrawal_category]:
                raise ValidationError({
                    'beneficiary_user': 'O tipo do beneficiário não corresponde à categoria.'
                })
        if withdrawal_category == WithdrawalCategory.ADVANCE and beneficiary is None:
            raise ValidationError(
                {'beneficiary_user': 'Informe o beneficiário desta sangria.'}
            )
        movement = CashMovement.objects.create(
            cash_session=session,
            movement_type=movement_type,
            amount=amount,
            user=user,
            reason=reason,
            withdrawal_category=withdrawal_category,
            beneficiary_user=beneficiary,
            result_effect=result_effect or 'neutral',
            operation_reference=operation_reference,
        )
        audit_log(
            actor=user, action=f'cash_movement.{movement_type}', obj=movement,
            company=session.branch.company, branch=session.branch,
            after=model_snapshot(movement, ('movement_type', 'amount', 'reason', 'withdrawal_category', 'beneficiary_user_id', 'result_effect')),
            metadata={'operation_reference': str(operation_reference)},
        )
        return movement


def record_manual_entry(cash_session, amount, user, reason, current_branch, idempotency_key):
    return _record_movement(
        cash_session=cash_session,
        amount=amount,
        user=user,
        reason=reason,
        current_branch=current_branch,
        movement_type=CashMovementType.MANUAL_ENTRY,
        permission_code='cash_registers.manual_entry',
        operation_reference=idempotency_key,
    )


def record_withdrawal(
    cash_session, amount, user, reason, current_branch, category, result_effect,
    idempotency_key, beneficiary_user=None,
):
    return _record_movement(
        cash_session=cash_session,
        amount=amount,
        user=user,
        reason=reason,
        current_branch=current_branch,
        movement_type=CashMovementType.WITHDRAWAL,
        permission_code='cash_registers.withdraw',
        withdrawal_category=category,
        beneficiary_user=beneficiary_user,
        result_effect=result_effect,
        operation_reference=idempotency_key,
    )


def movement_totals(session):
    money = DecimalField(max_digits=20, decimal_places=2)
    return CashMovement.objects.filter(cash_session_id=_pk(session)).aggregate(
        manual_entries=Coalesce(
            Sum('amount', filter=Q(movement_type=CashMovementType.MANUAL_ENTRY)),
            Decimal('0.00'),
            output_field=money,
        ),
        withdrawals=Coalesce(
            Sum('amount', filter=Q(movement_type=CashMovementType.WITHDRAWAL)),
            Decimal('0.00'),
            output_field=money,
        ),
    )


def calculate_expected_amount(session):
    """Calculate drawer cash from original cash events and their reversals."""
    if not isinstance(session, CashSession):
        session = CashSession.objects.get(pk=_pk(session))
    totals = movement_totals(session)
    cash = cash_payment_components(session)
    return (
        session.opening_amount
        + totals['manual_entries']
        - totals['withdrawals']
        + cash['sale_cash']
        + cash['consumption_cash']
        - cash['cash_reversals']
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def cash_payment_components(session):
    # Local import keeps cash independent from sales during Django app loading.
    from apps.sales.models import (
        OperationType, Payment, PaymentMethodCode, SaleStatus,
    )

    money = DecimalField(max_digits=20, decimal_places=2)
    payments = Payment.objects.filter(sale__cash_session_id=_pk(session)).filter(
        Q(payment_method_code=PaymentMethodCode.CASH)
        | Q(payment_method__code=PaymentMethodCode.CASH)
    )
    values = payments.aggregate(
        sale_cash=Coalesce(
            Sum('amount', filter=Q(sale__operation_type=OperationType.SALE)),
            Decimal('0.00'), output_field=money,
        ),
        consumption_cash=Coalesce(
            Sum('amount', filter=Q(sale__operation_type=OperationType.CONSUMPTION)),
            Decimal('0.00'), output_field=money,
        ),
        cash_reversals=Coalesce(
            Sum('amount', filter=Q(sale__status=SaleStatus.CANCELLED)),
            Decimal('0.00'), output_field=money,
        ),
        cash_cancellations=Count(
            'sale_id', filter=Q(sale__status=SaleStatus.CANCELLED), distinct=True,
        ),
    )
    values['cash_payments'] = (
        values['sale_cash'] + values['consumption_cash'] - values['cash_reversals']
    )
    return values


def session_operational_summary(session):
    precomputed = getattr(session, '_report_operational_summary', None)
    if precomputed is not None:
        return precomputed
    if not isinstance(session, CashSession):
        session = CashSession.objects.get(pk=_pk(session))
    from apps.sales.models import Sale

    sales = Sale.objects.filter(cash_session=session).select_related(
        'created_by', 'seller_user'
    ).prefetch_related('items__product__category', 'payments')
    return build_session_operational_summary(session, list(sales))


def build_session_operational_summary(session, session_sales):
    from apps.reports.financials import FinancialAggregator

    aggregator = FinancialAggregator(session_sales)
    sales = aggregator.commercial()
    sales['cancellations'] = aggregator.cancellations()
    consumptions = aggregator.consumption()
    consumptions['cancellations'] = aggregator.cancellations(
        operation_type='consumption'
    )
    receipts = aggregator.receipts(
        sale for sale in session_sales if sale.status == 'cancelled'
    )
    payments = [
        {
            'payment_method_code': row['code'],
            'payment_method_name': row['name'],
            'amount': row['net_received'],
            'gross_received': row['gross_received'],
            'reversals': row['reversals'],
        }
        for row in receipts['payment_methods']
    ]
    if hasattr(session, 'manual_entries') and hasattr(session, 'withdrawals'):
        movement_values = {
            'manual_entries': session.manual_entries,
            'withdrawals': session.withdrawals,
        }
    else:
        movement_values = movement_totals(session)
    expected = getattr(session, 'expected', None)
    if expected is None:
        expected = (
            calculate_expected_amount(session)
            if session.status == CashSessionStatus.OPEN
            else session.closing_expected_amount
        )
    cash_row = next(
        (row for row in receipts['payment_methods'] if row['code'] == 'cash'), None
    )
    cash = {
        'sale_cash': cash_row['commercial_received'] if cash_row else Decimal('0.00'),
        'consumption_cash': cash_row['consumption_received'] if cash_row else Decimal('0.00'),
        'cash_reversals': cash_row['reversals'] if cash_row else Decimal('0.00'),
        'cash_cancellations': sum(
            1 for sale in session_sales
            if sale.status == 'cancelled' and any(
                payment.payment_method_code == 'cash' for payment in sale.payments.all()
            )
        ),
    }
    cash['cash_payments'] = (
        cash['sale_cash'] + cash['consumption_cash'] - cash['cash_reversals']
    )
    return {
        'status': session.status,
        'opening_amount': session.opening_amount,
        'manual_entries': movement_values['manual_entries'],
        'withdrawals': movement_values['withdrawals'],
        **cash,
        'expected_amount': expected,
        'closing_amount_informed': session.closing_amount_informed,
        'closing_difference': session.closing_difference,
        'sales': sales,
        'consumptions': consumptions,
        'payment_totals': payments,
        'receipts': receipts,
        'values_scope': 'complete_session',
    }


def close_session(cash_session, closing_amount_informed, user, current_branch):
    informed = parse_money(
        closing_amount_informed, 'closing_amount_informed', nonnegative=True
    )
    with transaction.atomic():
        try:
            session = CashSession.objects.select_for_update().select_related(
                'cash_register', 'branch', 'branch__company'
            ).get(pk=_pk(cash_session))
        except (CashSession.DoesNotExist, TypeError, ValueError):
            raise ValidationError({'cash_session': 'Sessão de caixa inválida.'})
        _validate_current_branch(
            current_branch, session.branch, user, 'cash_registers.close'
        )
        if session.opened_by_id != user.pk and not user_has_branch_permission(
            user, session.branch_id, 'cash_registers.administer_others'
        ):
            raise PermissionDenied('Você não pode fechar uma sessão aberta por outro usuário.')
        if session.status != CashSessionStatus.OPEN:
            raise ValidationError({'cash_session': 'A sessão de caixa já está fechada.'})

        # Movement writers lock this same session first; row locks also protect history reads.
        list(
            CashMovement.objects.select_for_update()
            .filter(cash_session=session)
            .values_list('pk', flat=True)
        )
        expected = calculate_expected_amount(session)
        session.status = CashSessionStatus.CLOSED
        session.closed_by = user
        session.closed_at = timezone.now()
        session.closing_expected_amount = expected
        session.closing_amount_informed = informed
        session.closing_difference = informed - expected
        before = {'status': CashSessionStatus.OPEN}
        session.save(
            update_fields=(
                'status',
                'closed_by',
                'closed_at',
                'closing_expected_amount',
                'closing_amount_informed',
                'closing_difference',
                'updated_at',
            )
        )
        audit_log(actor=user, action='cash_session.close', obj=session, company=session.branch.company, branch=session.branch, before=before, after=model_snapshot(session, ('status', 'closing_expected_amount', 'closing_amount_informed', 'closing_difference')))
        return session


@transaction.atomic
def set_register_status(register, status, user):
    register = CashRegister.objects.select_for_update().get(pk=_pk(register))
    before = model_snapshot(register, ('status',))
    if (
        status == CashRegisterStatus.INACTIVE
        and CashSession.objects.filter(
            cash_register=register, status=CashSessionStatus.OPEN
        ).exists()
    ):
        raise ValidationError({'status': 'Não é possível inativar um caixa aberto.'})
    register.status = status
    register.save(update_fields=('status', 'updated_at'))
    audit_log(
        actor=user,
        action='cash_register.activate' if status == CashRegisterStatus.ACTIVE else 'cash_register.deactivate',
        obj=register, company=register.branch.company, branch=register.branch,
        before=before, after=model_snapshot(register, ('status',)),
    )
    return register
