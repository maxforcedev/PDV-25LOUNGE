from decimal import Decimal

from django.db.models import DecimalField, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.companies.selectors import accessible_branches
from apps.accounts.models import User
from apps.base.datetimes import parse_datetime_range

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
    CloseSessionSerializer,
    ManualEntryRequestSerializer,
    OpenSessionSerializer,
    WithdrawalRequestSerializer,
)
from .services import (
    calculate_expected_amount,
    close_session,
    movement_totals,
    open_session,
    record_manual_entry,
    record_withdrawal,
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
        'create': 'branches.change',
        'update': 'branches.change',
        'partial_update': 'branches.change',
        'activate': 'branches.change',
        'deactivate': 'branches.change',
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

    @action(detail=True, methods=('post',))
    def activate(self, request, pk=None):
        register = set_register_status(self.get_object(), CashRegisterStatus.ACTIVE)
        return Response(self.get_serializer(register).data)

    @action(detail=True, methods=('post',))
    def deactivate(self, request, pk=None):
        register = set_register_status(self.get_object(), CashRegisterStatus.INACTIVE)
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
        'summary': ('cash_registers.view', 'cash_registers.close'),
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
        register = params.get('cash_register') or params.get('register')
        if register:
            queryset = queryset.filter(cash_register_id=register)
        start_datetime, end_datetime = parse_datetime_range(params)
        if start_datetime:
            queryset = queryset.filter(opened_at__gte=start_datetime)
        if end_datetime:
            queryset = queryset.filter(opened_at__lte=end_datetime)
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
        movement = CashMovement.objects.select_related(
            'cash_session', 'cash_session__cash_register', 'cash_session__branch', 'user',
            'beneficiary_user',
        ).get(pk=movement.pk)
        return Response(CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

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

    @action(detail=True, methods=('get',))
    def summary(self, request, pk=None):
        session = self.get_object()
        totals = movement_totals(session)
        expected = (
            calculate_expected_amount(session)
            if session.status == CashSessionStatus.OPEN
            else session.closing_expected_amount
        )
        return Response(
            {
                'opening_amount': f'{session.opening_amount:.2f}',
                'manual_entries': f"{totals['manual_entries']:.2f}",
                'withdrawals': f"{totals['withdrawals']:.2f}",
                'expected_amount': f'{expected:.2f}',
                'status': session.status,
            }
        )


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
        if start_datetime:
            queryset = queryset.filter(created_at__gte=start_datetime)
        if end_datetime:
            queryset = queryset.filter(created_at__lte=end_datetime)
        return queryset


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
            company_accesses__company_id=branch.company_id,
            company_accesses__is_active=True,
        ).distinct().order_by('first_name', 'last_name', 'email', 'pk')
