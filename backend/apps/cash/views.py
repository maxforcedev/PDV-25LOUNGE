from decimal import Decimal

from django.db.models import DecimalField, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.companies.selectors import accessible_branches, user_has_branch_permission
from apps.accounts.models import User
from apps.base.datetimes import (
    filter_datetime_range,
    inclusive_end_exclusive,
    parse_datetime_range,
)
from apps.base.audit import audit_log, model_snapshot

from .models import (
    CashMovement,
    CashMovementType,
    CashRegister,
    CashRegisterStatus,
    CashSession,
    CashSessionStatus,
)
from .permissions import CashFunctionalPermission
from .serializers import (
    CashMovementSerializer,
    CashBeneficiarySerializer,
    CashRegisterSerializer,
    CashSessionSerializer,
    CancelSessionSerializer,
    CloseSessionSerializer,
    ManualEntryRequestSerializer,
    OpenSessionSerializer,
    WithdrawalRequestSerializer,
)
from .services import (
    calculate_expected_amount,
    close_session,
    cancel_session,
    movement_totals,
    open_session,
    record_manual_entry,
    record_withdrawal,
    redact_operational_summary,
    session_operational_summary,
    set_register_status,
)


class CurrentBranchQuerysetMixin:
    def allowed_branches(self, code):
        codes = code if isinstance(code, tuple) else (code,)
        branch_ids = accessible_branches(
            self.request.user, codes[0]
        ).order_by().values('pk')
        for alternative in codes[1:]:
            branch_ids = branch_ids.union(
                accessible_branches(
                    self.request.user, alternative
                ).order_by().values('pk')
            )
        branches = accessible_branches(self.request.user).filter(pk__in=branch_ids)
        current = getattr(self.request, 'branch_context', None)
        return branches.filter(pk=current.pk) if current else branches


class CashRegisterViewSet(CurrentBranchQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CashRegisterSerializer
    permission_classes = (CashFunctionalPermission,)
    http_method_names = ('get', 'post', 'patch', 'put', 'head', 'options')
    permission_codes = {
        'list': 'cash_registers.view',
        'retrieve': ('cash_registers.view', 'cash_registers.close'),
        'create': 'cash_registers.add',
        'update': 'cash_registers.change',
        'partial_update': 'cash_registers.change',
        'activate': 'cash_registers.change_status',
        'deactivate': 'cash_registers.change_status',
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'cash_registers.view')
        open_sessions = CashSession.objects.filter(
            status=CashSessionStatus.OPEN
        ).select_related('opened_by')
        queryset = CashRegister.objects.select_related(
            'branch', 'branch__company'
        ).prefetch_related(
            Prefetch('sessions', queryset=open_sessions, to_attr='current_open_sessions')
        ).filter(branch__in=self.allowed_branches(code))
        params = self.request.query_params
        if params.get('status'):
            queryset = queryset.filter(status=params['status'])
        if params.get('search'):
            queryset = queryset.filter(name__icontains=params['search'])
        return queryset

    def perform_create(self, serializer):
        register = serializer.save()
        audit_log(
            actor=self.request.user, action='cash_register.create', obj=register,
            company=register.branch.company, branch=register.branch,
            after=model_snapshot(register, ('branch_id', 'name', 'status')),
        )

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('name', 'status'))
        register = serializer.save()
        audit_log(
            actor=self.request.user, action='cash_register.update', obj=register,
            company=register.branch.company, branch=register.branch,
            before=before, after=model_snapshot(register, ('name', 'status')),
        )

    @action(detail=True, methods=('post',))
    def activate(self, request, pk=None):
        register = set_register_status(self.get_object(), CashRegisterStatus.ACTIVE, request.user)
        return Response(self.get_serializer(register).data)

    @action(detail=True, methods=('post',))
    def deactivate(self, request, pk=None):
        register = set_register_status(self.get_object(), CashRegisterStatus.INACTIVE, request.user)
        return Response(self.get_serializer(register).data)


class CashSessionViewSet(CurrentBranchQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CashSessionSerializer
    permission_classes = (CashFunctionalPermission,)
    permission_codes = {
        'list': 'cash_registers.view',
        'retrieve': ('cash_registers.view', 'cash_registers.close'),
        'open': 'cash_registers.open',
        'entry': 'cash_registers.manual_entry',
        'withdrawal': 'cash_registers.withdraw',
        'close': 'cash_registers.close',
        'cancel': 'cash_registers.close',
        'summary': ('cash_registers.view', 'cash_registers.close'),
        'timeline': ('cash_registers.view', 'cash_registers.close'),
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'cash_registers.view')
        money = DecimalField(max_digits=20, decimal_places=2)
        queryset = CashSession.objects.select_related(
            'cash_register', 'branch', 'branch__company', 'opened_by', 'closed_by'
        ).annotate(
            manual_entries_total=Coalesce(
                Sum(
                    'movements__amount',
                    filter=Q(movements__movement_type=CashMovementType.MANUAL_ENTRY),
                ),
                Decimal('0.00'),
                output_field=money,
            ),
            withdrawals_total=Coalesce(
                Sum(
                    'movements__amount',
                    filter=Q(movements__movement_type=CashMovementType.WITHDRAWAL),
                ),
                Decimal('0.00'),
                output_field=money,
            ),
        ).filter(branch__in=self.allowed_branches(code))
        params = self.request.query_params
        if params.get('status'):
            queryset = queryset.filter(status=params['status'])
        elif self.action == 'list':
            queryset = queryset.exclude(status=CashSessionStatus.CANCELLED)
        register = params.get('cash_register') or params.get('register')
        if register:
            queryset = queryset.filter(cash_register_id=register)
        start_datetime, end_datetime = parse_datetime_range(params)
        if start_datetime:
            queryset = queryset.filter(
                Q(closed_at__isnull=True) | Q(closed_at__gte=start_datetime)
            )
        if end_datetime:
            queryset = queryset.filter(
                opened_at__lt=inclusive_end_exclusive(end_datetime)
            )
        return queryset

    def _serialize_session(self, session, response_status=status.HTTP_200_OK):
        session = CashSession.objects.select_related(
            'cash_register', 'branch', 'branch__company', 'opened_by', 'closed_by'
        ).get(pk=session.pk)
        return Response(self.get_serializer(session).data, status=response_status)

    @action(detail=False, methods=('post',))
    def open(self, request):
        serializer = OpenSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = open_session(
            **serializer.validated_data,
            user=request.user,
            current_branch=getattr(request, 'branch_context', None),
        )
        return self._serialize_session(session, status.HTTP_201_CREATED)

    def _movement(self, request, service, serializer_class):
        session = self.get_object()
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement = service(
            cash_session=session,
            **serializer.validated_data,
            user=request.user,
            current_branch=getattr(request, 'branch_context', None),
        )
        replayed = bool(getattr(movement, '_idempotency_replayed', False))
        movement = CashMovement.objects.select_related(
            'cash_session', 'cash_session__cash_register', 'cash_session__branch', 'user',
            'beneficiary_user',
        ).get(pk=movement.pk)
        request.audit_fallback_suppressed = replayed
        return Response(
            CashMovementSerializer(movement).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=('post',))
    def entry(self, request, pk=None):
        return self._movement(
            request, record_manual_entry, ManualEntryRequestSerializer
        )

    @action(detail=True, methods=('post',))
    def withdrawal(self, request, pk=None):
        return self._movement(
            request, record_withdrawal, WithdrawalRequestSerializer
        )

    @action(detail=True, methods=('post',))
    def close(self, request, pk=None):
        session = self.get_object()
        serializer = CloseSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = close_session(
            cash_session=session,
            **serializer.validated_data,
            user=request.user,
            current_branch=getattr(request, 'branch_context', None),
        )
        return self._serialize_session(session)

    @action(detail=True, methods=('post',))
    def cancel(self, request, pk=None):
        serializer = CancelSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = cancel_session(
            self.get_object(), serializer.validated_data['reason'], request.user,
            getattr(request, 'branch_context', None),
        )
        return self._serialize_session(session)

    @action(detail=True, methods=('get',))
    def summary(self, request, pk=None):
        session = self.get_object()
        summary = session_operational_summary(session)
        include_commission = (
            request.user.is_superuser
            or user_has_branch_permission(
                request.user, session.branch_id, 'commissions.view'
            )
        )
        include_costs = (
            request.user.is_superuser
            or user_has_branch_permission(
                request.user, session.branch_id, 'inventory.view_stock_costs'
            )
        )
        summary = redact_operational_summary(
            summary, include_costs=include_costs,
            include_commission=include_commission,
        )

        def serialize(value):
            if isinstance(value, Decimal):
                return f'{value:.2f}'
            if isinstance(value, dict):
                return {key: serialize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [serialize(item) for item in value]
            return value

        return Response(serialize(summary))

    @action(detail=True, methods=('get',))
    def timeline(self, request, pk=None):
        from apps.sales.models import (
            OperationType, PaymentMethodCode, Sale, SaleStatus,
        )

        session = self.get_object()
        events = []
        events.append({
            'id': f'open-{session.pk}',
            'timestamp': session.opened_at.isoformat(),
            'kind': 'open',
            'label': 'Abertura de caixa',
            'amount': f'{session.opening_amount:.2f}',
            'sale': None,
            'details': f'Aberta por {session.opened_by.get_full_name().strip() or session.opened_by.email}',
        })
        for movement in CashMovement.objects.filter(cash_session=session).select_related(
            'user', 'beneficiary_user'
        ).order_by('created_at', 'pk'):
            is_entry = movement.movement_type == CashMovementType.MANUAL_ENTRY
            events.append({
                'id': f'movement-{movement.pk}',
                'timestamp': movement.created_at.isoformat(),
                'kind': 'manual_entry' if is_entry else 'withdrawal',
                'label': 'Entrada manual' if is_entry else f"Sangria · {movement.get_withdrawal_category_display() or 'Sangria'}",
                'amount': f'{movement.amount:.2f}',
                'sale': None,
                'details': movement.reason,
                'reason': movement.reason,
                'beneficiary_name': (
                    movement.beneficiary_user.get_full_name().strip() or movement.beneficiary_user.email
                    if movement.beneficiary_user_id else None
                ),
                'registered_by_name': movement.user.get_full_name().strip() or movement.user.email,
                'category_label': movement.get_withdrawal_category_display() if not is_entry else None,
            })
        sales = list(
            Sale.objects.filter(cash_session=session).select_related(
                'created_by', 'beneficiary_user', 'cancelled_by'
            ).prefetch_related('payments').order_by('created_at', 'pk')
        )
        cash_code = PaymentMethodCode.CASH
        for sale in sales:
            cash_amount = sale.payments.filter(
                Q(payment_method_code=cash_code) | Q(payment_method__code=cash_code)
            ).aggregate(
                value=Coalesce(Sum('amount'), Decimal('0.00'), output_field=DecimalField(max_digits=20, decimal_places=2))
            )['value']
            has_cash = cash_amount > 0
            is_cancelled = sale.status == SaleStatus.CANCELLED
            if not has_cash:
                continue
            is_consumption = sale.operation_type == OperationType.CONSUMPTION
            events.append({
                'id': f'sale-{sale.pk}-cash',
                'timestamp': sale.created_at.isoformat(),
                'kind': 'charged_consumption' if is_consumption else 'cash_sale',
                'label': (
                    f'Consumação em dinheiro {sale.sale_number}'
                    if is_consumption else f'Venda em dinheiro {sale.sale_number}'
                ),
                'amount': f'{cash_amount:.2f}',
                'sale': {'id': sale.pk, 'number': sale.sale_number, 'operation_type': sale.operation_type, 'status': sale.status},
                'details': f"Operador {sale.created_by.get_full_name().strip() or sale.created_by.email}",
                'reason': None,
                'beneficiary_name': (
                    sale.beneficiary_user.get_full_name().strip() or sale.beneficiary_user.email
                    if sale.beneficiary_user_id else None
                ),
                'registered_by_name': sale.created_by.get_full_name().strip() or sale.created_by.email,
                'category_label': None,
            })
            if is_cancelled:
                cancelled_by = (
                    sale.cancelled_by.get_full_name().strip() or sale.cancelled_by.email
                    if sale.cancelled_by_id else None
                )
                events.append({
                    'id': f'sale-{sale.pk}-reversal',
                    'timestamp': (sale.cancelled_at or sale.created_at).isoformat(),
                    'kind': 'cancellation',
                    'label': f"Reversão em dinheiro · {'Consumação' if is_consumption else 'Venda'} {sale.sale_number}",
                    'amount': f'{-cash_amount:.2f}',
                    'sale': {'id': sale.pk, 'number': sale.sale_number, 'operation_type': sale.operation_type, 'status': sale.status},
                    'details': f'Cancelado por {cancelled_by}' if cancelled_by else 'Operação cancelada',
                    'reason': sale.cancellation_reason,
                    'beneficiary_name': (
                        sale.beneficiary_user.get_full_name().strip() or sale.beneficiary_user.email
                        if sale.beneficiary_user_id else None
                    ),
                    'registered_by_name': cancelled_by,
                    'category_label': None,
                })
        from apps.commands.models import CommandPayment, CommandPaymentStatus
        for payment in CommandPayment.objects.filter(
            cash_session=session, payment_method__code=cash_code, command__sale__isnull=True,
        ).select_related('command', 'operator').order_by('created_at', 'pk'):
            reversed_payment = payment.status == CommandPaymentStatus.REVERSED
            events.append({
                'id': f'command-payment-{payment.pk}',
                'timestamp': payment.created_at.isoformat(),
                'kind': 'command_cash_reversal' if reversed_payment else 'command_cash_applied',
                'label': 'Estorno de pagamento de comanda em dinheiro' if reversed_payment else 'Pagamento de comanda em dinheiro',
                'amount': f'{-payment.amount if reversed_payment else payment.amount:.2f}',
                'sale': None,
                'details': f'Comanda {payment.command.command_number}',
                'reason': payment.reversal_reason or None,
                'beneficiary_name': None,
                'registered_by_name': payment.operator.get_full_name().strip() or payment.operator.email,
                'category_label': None,
            })
        if session.status == CashSessionStatus.CLOSED and session.closed_at:
            events.append({
                'id': f'close-{session.pk}',
                'timestamp': session.closed_at.isoformat(),
                'kind': 'close',
                'label': 'Fechamento de caixa',
                'amount': f'{session.closing_amount_informed or Decimal("0.00"):.2f}',
                'sale': None,
                'details': (
                    f"Esperado {session.closing_expected_amount or Decimal('0.00'):.2f} · "
                    f"diferença {session.closing_difference or Decimal('0.00'):.2f} · "
                    f"por {session.closed_by.get_full_name().strip() if session.closed_by_id else ''}"
                ),
            })
        events.sort(key=lambda item: item['timestamp'])
        return Response({'count': len(events), 'results': events})


class CashMovementViewSet(CurrentBranchQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CashMovementSerializer
    permission_classes = (CashFunctionalPermission,)
    permission_codes = {
        'list': 'cash_registers.view',
        'retrieve': 'cash_registers.view',
    }

    def get_queryset(self):
        queryset = CashMovement.objects.select_related(
            'cash_session', 'cash_session__cash_register', 'cash_session__branch',
            'cash_session__branch__company', 'user',
            'beneficiary_user',
        ).filter(
            cash_session__branch__in=self.allowed_branches('cash_registers.view')
        )
        params = self.request.query_params
        session = params.get('cash_session') or params.get('session')
        movement_type = params.get('movement_type') or params.get('type')
        if session:
            queryset = queryset.filter(cash_session_id=session)
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        if params.get('search'):
            queryset = queryset.filter(reason__icontains=params['search'])
        start_datetime, end_datetime = parse_datetime_range(params)
        return filter_datetime_range(
            queryset, 'created_at', start_datetime, end_datetime
        )


class CashBeneficiaryViewSet(
    CurrentBranchQuerysetMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = CashBeneficiarySerializer
    permission_classes = (CashFunctionalPermission,)
    permission_codes = {'list': 'cash_registers.withdraw'}

    def get_queryset(self):
        branch = self.request.branch_context
        return User.objects.filter(
            is_active=True,
            archived_at__isnull=True,
            company_accesses__company_id=branch.company_id,
            company_accesses__is_active=True,
        ).distinct().order_by('first_name', 'last_name', 'email', 'pk')
