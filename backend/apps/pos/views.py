from decimal import Decimal, InvalidOperation
from time import perf_counter

from django.db import transaction
from django.db.models import Prefetch, Q
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.base.audit import audit_log, model_snapshot
from apps.base.exceptions import DomainValidationError
from apps.base.pagination import StandardPagination
from apps.cash.models import CashMovement, CashRegister, CashRegisterStatus, CashSession, WithdrawalCategory
from apps.cash.serializers import (
    CashBeneficiarySerializer, CashMovementSerializer, CashSessionSerializer, CloseSessionSerializer,
    ManualEntryRequestSerializer, WithdrawalRequestSerializer,
)
from apps.cash.services import (
    close_session, open_session, record_manual_entry, record_withdrawal,
    cash_beneficiaries, redact_operational_summary, session_cash_state,
    session_operational_summary,
)
from apps.companies.permissions import FunctionalCompanyPermission
from apps.companies.selectors import (
    accessible_branches, customer_search_queryset, inactive_customer_identity_match,
)
from apps.companies.services import (
    CustomerIdentityConflict, customer_identity_payload, set_customer_status,
)
from apps.companies.features import require_branch_feature
from apps.companies.models import Customer, Status
from apps.attendance.models import (
    AttendanceCommand, AttendanceCommandStatus, AttendanceOrderItem, AttendancePayment,
    AttendanceTableGroupMembership, TableAttendance, TableAttendanceStatus, TableOrderItem, TablePayment,
)
from apps.attendance.serializers import (
    AttendanceCancelItemSerializer, AttendanceCommandSerializer, AttendanceConfirmItemSerializer,
    AttendanceFinalizeSerializer, AttendanceItemsSerializer,
    AttendanceOpenCommandSerializer, AttendanceOpenTableSerializer,
    AttendanceOrderItemSerializer, AttendancePaymentInputSerializer,
    AttendancePaymentSerializer, AttendanceReversePaymentSerializer, AttendanceTransferCommandSerializer,
    AttendanceTransferItemsSerializer, AttendanceBillRequestSerializer, AttendanceTableGroupSerializer,
    TableAttendanceOpenSerializer, TableAttendanceSerializer, TableOrderItemSerializer,
    TablePaymentInputSerializer, TablePaymentSerializer,
)
from apps.attendance.services import (
    AttendanceConflict, add_order_items, cancel_order_item, command_summary, confirm_order_item,
    finalize_command as finalize_attendance_command, open_command as open_attendance_command,
    open_table as open_attendance_table, record_payment as record_attendance_payment,
    reverse_payment as reverse_attendance_payment,
    group_tables as group_attendance_tables, separate_table_from_group,
    set_bill_requested,
    transfer_command as transfer_attendance_command,
    transfer_items as transfer_attendance_items,
    open_table_attendance, save_table_order, table_summary, cancel_table_item,
    record_table_payment, reverse_table_payment, set_table_bill_requested, close_table_attendance,
    transfer_table_items,
)
from apps.products.models import (
    ModifierOption, ProductModifierGroup,
)
from apps.products.models import SalesChannel
from apps.products.selectors import sellable_products_for_branch
from apps.production.services import lookup_ticket_for_validation, redeem_ticket, ticket_validation_data
from apps.sales.models import OperationType, Sale
from apps.sales.serializers import (
    CalculationOutputSerializer, SaleCatalogProductSerializer, SaleSerializer,
)
from apps.sales.services import (
    assess_sale_stock_availability, calculate_preview, catalog_product_operational_states,
    catalog_products_with_available_stock, finalize_sale, validate_discount_authorization,
)

from .authentication import POSDeviceAuthentication, require_device, require_operator_session
from .models import POSDevice, POSDeviceSettings
from .serializers import (
    POSAdminDeviceSerializer, POSDeviceSettingsSerializer, POSOpenCashSessionSerializer,
    POSCustomerSerializer, POSDiscountAuthorizationValidationSerializer,
    POSFinalizeSaleSerializer, POSSalePreviewSerializer, POSStockAvailabilitySerializer,
    POSTicketLookupSerializer, POSTicketValidateSerializer,
)
from .services import (
    assert_branch_device_limit, authenticate_operator, cash_state_for_device, confirm_pairing,
    effective_cash_settings, effective_settings, identify_branch, logout_operator, modules_for,
    pos_operator_queryset, request_otp, set_device_status,
    eligible_pos_authorizers,
    request_pos_pin_reset, set_pos_pin, version_gate,
)


def _required(data, field):
    value = data.get(field)
    if value in (None, ''):
        raise DomainValidationError(code='invalid_request', message=f'Informe {field}.', details={field: ['Obrigatorio.']})
    return value


class POSTimedAPIView(APIView):
    def dispatch(self, request, *args, **kwargs):
        started = perf_counter()
        try:
            return super().dispatch(request, *args, **kwargs)
        finally:
            import logging

            logging.getLogger('pos.performance').info(
                'POS view_ms=%s view=%s',
                round((perf_counter() - started) * 1000), type(self).__name__,
            )


def _operator_data(user):
    name = user.get_full_name().strip() or user.email or f'Usuario {user.pk}'
    initials = ''.join(part[0] for part in name.split()[:2]).upper()
    return {'id': user.pk, 'display_name': name, 'initials': initials, 'avatar_url': None}


class POSPublicView(POSTimedAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class POSDeviceView(POSTimedAPIView):
    authentication_classes = [POSDeviceAuthentication]
    permission_classes = [AllowAny]

    def device(self, request, *, check_version=False):
        device = require_device(request)
        if check_version:
            version_gate(device.app_version)
        return device


class PairingIdentifyView(POSPublicView):
    def post(self, request):
        flow, channels = identify_branch(_required(request.data, 'identifier'), request)
        return Response({
            'pairing_flow_id': flow.id,
            'branch': {'display_name': flow.branch.name},
            'channels': [{key: value for key, value in channel.items() if key != '_destination'} for channel in channels],
            'expires_in_seconds': int((flow.expires_at - timezone.now()).total_seconds()),
        })


class PairingRequestOtpView(POSPublicView):
    def post(self, request):
        challenge = request_otp(_required(request.data, 'pairing_flow_id'), _required(request.data, 'channel_id'), request)
        return Response({
            'challenge_id': challenge.id,
            'destination': challenge.destination_masked,
            'expires_in_seconds': int((challenge.expires_at - timezone.now()).total_seconds()),
            'resend_available_in_seconds': 60,
        })


class PairingConfirmView(POSPublicView):
    def post(self, request):
        device_data = request.data.get('device')
        if not isinstance(device_data, dict):
            raise DomainValidationError(code='invalid_request', message='Informe os dados do dispositivo.')
        _required(device_data, 'name')
        device, credential = confirm_pairing(
            _required(request.data, 'challenge_id'), _required(request.data, 'code'), device_data, request,
        )
        return Response({
            'device': {'id': device.id, 'name': device.name, 'status': device.status},
            'device_credential': credential,
            'bootstrap_required': True,
        }, status=status.HTTP_201_CREATED)


class OperatorsView(POSDeviceView):
    def get(self, request):
        device = self.device(request)
        return Response({'operators': [_operator_data(item.user) for item in pos_operator_queryset(device.branch)]})


class OperatorLoginView(POSDeviceView):
    def post(self, request):
        device = self.device(request, check_version=True)
        session, token = authenticate_operator(
            device, _required(request.data, 'operator_id'), _required(request.data, 'pin'),
            device_validated=True,
        )
        return Response({
            'operator_session': {'token': token, 'expires_at': session.expires_at},
            'operator': _operator_data(session.operator),
            'bootstrap_required': True,
        })


class OperatorLogoutView(POSDeviceView):
    def post(self, request):
        device = self.device(request, check_version=True)
        logout_operator(require_operator_session(request, device))
        return Response(status=status.HTTP_204_NO_CONTENT)


class OperatorPinResetView(POSDeviceView):
    def post(self, request, operator_id):
        request_pos_pin_reset(
            self.device(request, check_version=True), operator_id,
            device_validated=True,
        )
        return Response({'detail': 'Se o operador estiver elegivel, recebera instrucoes por e-mail.'}, status=status.HTTP_202_ACCEPTED)


class BootstrapView(POSDeviceView):
    def get(self, request):
        started = perf_counter()
        device = self.device(request, check_version=True)
        session = require_operator_session(request, device)
        permissions, modules = modules_for(
            session.operator, device,
            permission_codes=request.pos_permission_codes,
        )
        import logging

        logging.getLogger('pos.performance').info(
            'POS permission_context_ms=%s', round((perf_counter() - started) * 1000),
        )
        return Response({
            'server_time': timezone.now(),
            'release': version_gate(device.app_version),
            'company': {'id': device.branch.company_id, 'trade_name': device.branch.company.trade_name, 'operational': True},
            'branch': {'id': device.branch_id, 'name': device.branch.name, 'operational': True},
            'device': {
                'id': device.id, 'name': device.name, 'type': device.device_type, 'status': device.status,
                'capabilities': device.capabilities,
            },
            'operator': _operator_data(session.operator),
            'permissions': sorted(permissions),
            'modules': modules,
            'cash': cash_state_for_device(device, permissions, session.operator),
            'settings': {'receipt': effective_settings(device)},
        })


class HeartbeatView(POSDeviceView):
    def post(self, request):
        device = self.device(request)
        app_version = request.data.get('app_version')
        if app_version is not None:
            device.app_version = str(app_version).strip()
        capabilities = request.data.get('capabilities')
        if isinstance(capabilities, dict):
            device.capabilities = capabilities
        device.last_seen_at = timezone.now()
        device.save(update_fields=['app_version', 'capabilities', 'last_seen_at', 'updated_at'])
        return Response({'device': {'id': device.id, 'status': device.status}, 'release': version_gate(device.app_version)})


class PinConfirmView(POSPublicView):
    def post(self, request):
        set_pos_pin(_required(request.data, 'token'), _required(request.data, 'pin'))
        return Response({'detail': 'PIN configurado com sucesso.'})


class POSCashView(POSDeviceView):
    def context(self, request):
        started = perf_counter()
        device = self.device(request, check_version=True)
        operator_session = require_operator_session(request, device)
        permissions = request.pos_permission_codes
        import logging

        logging.getLogger('pos.performance').info(
            'POS permission_context_ms=%s', round((perf_counter() - started) * 1000),
        )
        return device, operator_session.operator, permissions, operator_session

    @staticmethod
    def require_read_permission(permissions):
        if not {'cash_registers.view', 'cash_registers.close'} & permissions:
            raise PermissionDenied('Você não possui permissão para visualizar caixas nesta filial.')

    @staticmethod
    def require_operational_permission(permissions):
        if not permissions.intersection({
            'cash_registers.view', 'cash_registers.open',
            'cash_registers.manual_entry', 'cash_registers.withdraw',
            'cash_registers.close', 'cash_registers.administer_others',
        }):
            raise PermissionDenied('Você não possui permissão operacional de caixa nesta filial.')

    @staticmethod
    def audit_metadata(device, operator_session):
        return {
            'source': 'pos',
            'device_id': str(device.pk),
            'device_name': device.name,
            'operator_session_id': str(operator_session.pk),
        }

    @staticmethod
    def session_for_device(session_id, device):
        return get_object_or_404(
            CashSession.objects.select_related(
                'cash_register', 'branch', 'branch__company', 'opened_by', 'closed_by',
            ),
            pk=session_id,
            branch=device.branch,
        )

    @staticmethod
    def mutation_state(device, permissions, session, operator):
        state = cash_state_for_device(device, permissions, operator)
        state['session_cash'] = session_cash_state(session)
        return state


class POSCashOverviewView(POSCashView):
    def get(self, request):
        device, operator, permissions, operator_session = self.context(request)
        self.require_operational_permission(permissions)
        return Response(cash_state_for_device(device, permissions, operator))


def _pos_catalog_queryset(branch, *, search=None, barcode=None):
    return sellable_products_for_branch(
        branch, SalesChannel.COUNTER, search=search, barcode=barcode,
    ).prefetch_related(
        'components__component_product',
        'fraction_components__component_product',
        Prefetch(
            'modifier_groups',
            queryset=ProductModifierGroup.objects.filter(
                status=Status.ACTIVE,
                modifier_group__status=Status.ACTIVE,
                modifier_group__deleted_at__isnull=True,
                modifier_group__branch=branch,
            ).select_related('modifier_group').prefetch_related(
                Prefetch(
                    'modifier_group__options',
                    queryset=ModifierOption.objects.filter(status=Status.ACTIVE),
                    to_attr='operational_options',
                )
            ).order_by('sort_order', 'id'),
            to_attr='operational_modifier_group_links',
        ),
        Prefetch(
            'components__component_product__modifier_groups',
            queryset=ProductModifierGroup.objects.filter(
                status=Status.ACTIVE,
                modifier_group__status=Status.ACTIVE,
                modifier_group__deleted_at__isnull=True,
                modifier_group__branch=branch,
            ).select_related('modifier_group').prefetch_related(
                Prefetch(
                    'modifier_group__options',
                    queryset=ModifierOption.objects.filter(status=Status.ACTIVE),
                    to_attr='operational_options',
                )
            ).order_by('sort_order', 'id'),
            to_attr='operational_modifier_group_links',
        ),
    )


def _visible_pos_catalog(device, queryset):
    products = list(queryset)
    if effective_settings(device).get('show_out_of_stock_products', True):
        return products
    return catalog_products_with_available_stock(device.branch, products)


def _pos_sale_session(device, session_id):
    """Resolve an open session while enforcing the device cash binding."""
    session = get_object_or_404(
        CashSession.objects.select_related('cash_register'),
        pk=session_id,
        branch=device.branch,
        status='open',
    )
    mode, fixed_register = effective_cash_settings(device)
    if mode == 'FIXED':
        if fixed_register is None or fixed_register.status != CashRegisterStatus.ACTIVE:
            raise DomainValidationError(
                code='pos_fixed_cash_unconfigured',
                message='O caixa fixo deste dispositivo não está configurado ou ativo.',
            )
        if session.cash_register_id != fixed_register.pk:
            raise DomainValidationError(
                code='pos_fixed_cash_required',
                message='Este dispositivo só pode vender no caixa fixo configurado.',
            )
    return session


class POSTicketValidatorView(POSCashView):
    def _context(self, request):
        device, operator, permissions, operator_session = self.context(request)
        if 'tickets.validate' not in permissions:
            raise PermissionDenied('Você não possui permissão para validar tickets nesta filial.')
        return device, operator, operator_session


class POSTicketLookupView(POSTicketValidatorView):
    def post(self, request):
        device, _operator, _session = self._context(request)
        serializer = POSTicketLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = lookup_ticket_for_validation(branch=device.branch, **serializer.validated_data)
        return Response({'ticket': ticket_validation_data(ticket)})


class POSTicketValidateView(POSTicketValidatorView):
    def post(self, request):
        device, operator, operator_session = self._context(request)
        serializer = POSTicketValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ticket, redemption, replayed = redeem_ticket(
            branch=device.branch, operator=operator, device=device,
            validation_code=data.get('validation_code'), ticket_number=data.get('ticket_number'),
            quantity=data['quantity'], idempotency_key=data['idempotency_key'],
            input_method=data['input_method'],
        )
        request.branch_context = device.branch
        response = Response({
            'ticket': ticket_validation_data(ticket),
            'redemption': {'quantity': str(redemption.quantity), 'redeemed_at': redemption.redeemed_at},
        })
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSQuickSaleView(POSCashView):
    @staticmethod
    def _catalog_payload(request, products, branch):
        request.branch_context = request._pos_branch
        products = list(products)
        inventory_states = catalog_product_operational_states(branch, products)
        rows = SaleCatalogProductSerializer(
            products, many=True, context={'request': request},
        ).data
        return [
            {
                'id': product['id'],
                'name': product['name'],
                'internal_code': product['internal_code'],
                'barcode': product['barcode'],
                'category': {
                    'id': product_object.effective_category_id,
                    'name': product_object.effective_category_name,
                } if product_object.effective_category_id else None,
                'price': product['sale_price'],
                'unit': product['unit'],
                'image': product['image'],
                'favorite': product['is_favorite'],
                'emits_ticket': product['emits_ticket'],
                'modifier_groups': product['modifier_groups'],
                **inventory_states[product_object.pk],
            }
            for product_object, product in zip(products, rows)
        ]

    @staticmethod
    def _items(items):
        return [
            {
                'client_item_id': item['client_item_id'],
                'product': item['product'],
                'quantity': item['quantity'],
                'discount': item.get('discount', '0.00'),
                'modifiers': item.get('modifiers', []),
                'notes': item.get('notes', ''),
            }
            for item in items
        ]


class POSCatalogView(POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        request._pos_branch = device.branch
        queryset = _pos_catalog_queryset(
            device.branch, search=request.query_params.get('search'),
        )
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(effective_category_id=category)
        if request.query_params.get('favorites') == 'true':
            queryset = queryset.filter(is_favorite=True)
        return Response({
            'products': self._catalog_payload(
                request, _visible_pos_catalog(device, queryset), device.branch,
            ),
        })


class POSCatalogCategoriesView(POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        categories = {
            (product.effective_category_id, product.effective_category_name)
            for product in _visible_pos_catalog(device, _pos_catalog_queryset(device.branch))
            if product.effective_category_id
        }
        return Response({'categories': [
            {'id': category_id, 'name': category_name}
            for category_id, category_name in sorted(
                categories, key=lambda item: (item[1], item[0]),
            )
        ]})


class POSBarcodeProductView(POSQuickSaleView):
    def get(self, request, barcode):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        request._pos_branch = device.branch
        product = get_object_or_404(_pos_catalog_queryset(device.branch, barcode=barcode))
        if not _visible_pos_catalog(device, [product]):
            raise Http404
        return Response(self._catalog_payload(request, [product], device.branch)[0])


class POSCustomersView(POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions or 'customers.view' not in permissions:
            raise PermissionDenied('Você não possui permissão para consultar clientes nesta filial.')
        term = request.query_params.get('q', '').strip()
        customers = customer_search_queryset(
            company=device.branch.company, term=term, active_only=True,
        )
        inactive_match = inactive_customer_identity_match(device.branch.company, term)
        return Response({
            'customers': POSCustomerSerializer(customers.order_by('name', 'id')[:20], many=True).data,
            'inactive_identity': {
                'customer': customer_identity_payload(inactive_match),
                'can_reactivate': 'customers.change' in permissions,
            } if inactive_match else None,
        })

    def post(self, request):
        device, operator, permissions, operator_session = self.context(request)
        if 'sales.create' not in permissions or 'customers.add' not in permissions:
            raise PermissionDenied('Você não possui permissão para cadastrar clientes nesta filial.')
        serializer = POSCustomerSerializer(
            data=request.data, context={'company': device.branch.company},
        )
        serializer.is_valid(raise_exception=True)
        try:
            customer = serializer.save()
        except CustomerIdentityConflict as error:
            if error.code == 'customer_identity_mismatch':
                raise DomainValidationError(
                    code=error.code, message=error.message,
                ) from error
            if 'customers.view' not in permissions:
                raise DomainValidationError(
                    code='customer_identity_conflict',
                    message='Já existe um cliente cadastrado com este telefone ou CPF.',
                ) from error
            details = {**error.details}
            if error.code == 'customer_inactive_identity_conflict':
                details['can_reactivate'] = 'customers.change' in permissions
                if 'customers.change' not in permissions:
                    message = (
                        'Cliente cadastrado, porém inativo. '
                        'Você não possui permissão para reativá-lo.'
                    )
                else:
                    message = error.message
            else:
                message = error.message
            raise DomainValidationError(
                code=error.code, message=message, details=details,
            ) from error
        audit_log(
            actor=operator, action='pos.customer.created', obj=customer,
            company=device.branch.company, branch=device.branch,
        )
        return Response(POSCustomerSerializer(customer).data, status=status.HTTP_201_CREATED)


class POSCustomerActivateView(POSQuickSaleView):
    def post(self, request, customer_id):
        device, operator, permissions, operator_session = self.context(request)
        if 'customers.change' not in permissions:
            raise PermissionDenied('Você não possui permissão para reativar clientes nesta filial.')
        with transaction.atomic():
            customer = get_object_or_404(
                Customer.objects.select_for_update().filter(
                    company_id=device.branch.company_id,
                ),
                pk=customer_id,
            )
            if customer.status == Status.INACTIVE:
                before = model_snapshot(customer, ('status',))
                customer = set_customer_status(customer=customer, status=Status.ACTIVE)
                audit_log(
                    actor=operator, action='pos.customer.activated', obj=customer,
                    company=device.branch.company, branch=device.branch, before=before,
                    after=model_snapshot(customer, ('status',)),
                )
        return Response(POSCustomerSerializer(customer).data)


class POSAttendanceView(POSCashView):
    @staticmethod
    def _require(permissions, code, message):
        if code not in permissions:
            raise PermissionDenied(message)

    @staticmethod
    def _domain(error):
        conflict = DomainValidationError(code=error.code, message=error.message)
        if error.code.endswith(('conflict', 'closed', 'unsupported', 'forbidden')):
            conflict.status_code = status.HTTP_409_CONFLICT
        raise conflict from error

    @staticmethod
    def _command(device, command_id):
        return get_object_or_404(
            AttendanceCommand.objects.select_related('table', 'customer', 'sale'),
            pk=command_id, branch=device.branch,
        )


class POSTablesView(POSAttendanceView):
    def get(self, request):
        from apps.commands.models import Command, CommandStatus, Table, TableStatus

        device, _, permissions, _ = self.context(request)
        self._require(permissions, 'tables.view', 'Você não possui permissão para consultar mesas nesta filial.')
        require_branch_feature(device.branch, 'tables')
        tables = list(Table.objects.filter(branch=device.branch, status=TableStatus.ACTIVE).order_by('name', 'id'))
        attendances = TableAttendance.objects.filter(
            branch=device.branch, status=TableAttendanceStatus.OPEN, table_id__in=[table.pk for table in tables],
        ).select_related('table').order_by('created_at', 'id')
        grouped = {table.pk: None for table in tables}
        for attendance in attendances:
            grouped[attendance.table_id] = attendance
        legacy_ids = set(Command.objects.filter(
            branch=device.branch, status=CommandStatus.OPEN, table_id__in=grouped,
        ).values_list('table_id', flat=True))
        active_memberships = AttendanceTableGroupMembership.objects.filter(
            table_id__in=grouped, left_at__isnull=True, group__is_active=True,
        ).select_related('group', 'table')
        memberships_by_table = {membership.table_id: membership for membership in active_memberships}
        group_members = {}
        for membership in active_memberships:
            group_members.setdefault(membership.group_id, []).append(membership)
        payload = []
        for table in tables:
            attendance = grouped[table.pk]
            summary = table_summary(attendance) if attendance else None
            membership = memberships_by_table.get(table.pk)
            payload.append({
                'id': table.pk, 'name': table.name, 'capacity': table.seats,
                'status': 'occupied' if attendance or table.pk in legacy_ids else 'free',
                'legacy_occupied': table.pk in legacy_ids,
                'attendance': TableAttendanceSerializer(attendance).data if attendance else None,
                'total': summary['total_due'] if summary else '0.00',
                'balance': summary['remaining_balance'] if summary else '0.00',
                'bill_requested': bool(attendance and attendance.bill_requested_at),
                'group': (
                    {
                        'id': membership.group_id,
                        'table_ids': [row.table_id for row in group_members[membership.group_id]],
                        'table_names': [row.table.name for row in group_members[membership.group_id]],
                    }
                    if membership else None
                ),
            })
        return Response({'tables': payload})


class POSTableOpenView(POSAttendanceView):
    def post(self, request, table_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.open', 'Você não possui permissão para abrir mesas nesta filial.')
        serializer = TableAttendanceOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attendance, replayed = open_table_attendance(
                branch=device.branch, table_id=table_id, user=operator,
                audit_metadata=self.audit_metadata(device, operator_session), **serializer.validated_data,
            )
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(TableAttendanceSerializer(attendance).data, status=(status.HTTP_200_OK if replayed else status.HTTP_201_CREATED))
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSTableGroupView(POSAttendanceView):
    def post(self, request):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.merge', 'Você não possui permissão para agrupar mesas.')
        serializer = AttendanceTableGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            group, replayed = group_attendance_tables(
                branch=device.branch, table_ids=serializer.validated_data['tables'], user=operator,
                idempotency_key=serializer.validated_data['idempotency_key'],
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        response = Response({'id': group.pk}, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSTableSeparateView(POSAttendanceView):
    def post(self, request, table_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.merge', 'Você não possui permissão para separar mesas.')
        serializer = AttendanceBillRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            group_id, replayed = separate_table_from_group(
                branch=device.branch, table_id=table_id, user=operator,
                idempotency_key=serializer.validated_data['idempotency_key'],
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        response = Response({'group_id': group_id})
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSAttendanceCommandsView(POSAttendanceView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        self._require(permissions, 'commands.view', 'Você não possui permissão para consultar comandas nesta filial.')
        require_branch_feature(device.branch, 'commands')
        queryset = AttendanceCommand.objects.filter(branch=device.branch).select_related('table', 'customer', 'sale')
        if request.query_params.get('open_only') != 'false':
            queryset = queryset.filter(status=AttendanceCommandStatus.OPEN)
        query = request.query_params.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(number__icontains=query) | Q(identifier__icontains=query)
                | Q(customer_name_snapshot__icontains=query),
            )
        return Response({'commands': AttendanceCommandSerializer(queryset.order_by('-created_at', '-id')[:50], many=True).data})

    def post(self, request):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.open', 'Você não possui permissão para abrir comandas nesta filial.')
        serializer = AttendanceOpenCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            command, replayed = open_attendance_command(
                branch=device.branch, user=operator,
                table_id=data.get('table'), idempotency_key=data['idempotency_key'],
                identifier=data['identifier'], customer_id=data.get('customer'),
                people_count=data.get('people_count'), notes=data['notes'],
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        request.audit_fallback_suppressed = replayed
        response = Response(
            AttendanceCommandSerializer(command).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSAttendanceCatalogView(POSAttendanceView, POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        self._require(permissions, 'commands.add_items', 'Você não possui permissão para adicionar itens.')
        require_branch_feature(device.branch, 'commands')
        request._pos_branch = device.branch
        queryset = _pos_catalog_queryset(
            device.branch, search=request.query_params.get('search'),
        ).filter(available_command=True)
        return Response({'products': self._catalog_payload(
            request, _visible_pos_catalog(device, queryset), device.branch,
        )})


class POSTableCatalogView(POSAttendanceView, POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        self._require(permissions, 'tables.add_items', 'Você não possui permissão para consultar o catálogo de Mesa.')
        require_branch_feature(device.branch, 'tables')
        request._pos_branch = device.branch
        queryset = sellable_products_for_branch(device.branch, SalesChannel.TABLE, search=request.query_params.get('search'))
        return Response({'products': self._catalog_payload(request, _visible_pos_catalog(device, queryset), device.branch)})


class POSAttendanceCheckoutOptionsView(POSAttendanceView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if not permissions.intersection({'commands.payments.record', 'commands.finalize'}):
            raise PermissionDenied('Você não possui permissão para consultar opções de pagamento.')
        from apps.sales.models import PaymentMethod

        mode, fixed_register = effective_cash_settings(device)
        sessions = CashSession.objects.filter(
            branch=device.branch, status='open',
        ).select_related('cash_register', 'opened_by').order_by('id')
        fixed_cash_available = True
        if mode == 'FIXED':
            fixed_cash_available = bool(
                fixed_register and fixed_register.status == CashRegisterStatus.ACTIVE
            )
            sessions = sessions.filter(cash_register=fixed_register) if fixed_cash_available else sessions.none()
        methods = PaymentMethod.objects.filter(
            company_id=device.branch.company_id, status=Status.ACTIVE,
        ).order_by('name', 'id').values('id', 'code', 'name')
        return Response({
            'payment_methods': list(methods),
            'cash_binding_mode': mode,
            'fixed_register': (
                {'id': fixed_register.pk, 'name': fixed_register.name}
                if mode == 'FIXED' and fixed_register else None
            ),
            'cash_required': True,
            'fixed_cash_available': fixed_cash_available,
            'cash_sessions': [
                {
                    'id': session.pk,
                    'register_name': session.cash_register.name,
                    'opened_by_name': session.opened_by.get_full_name().strip() or session.opened_by.email,
                }
                for session in sessions
            ],
        })


class POSAttendanceCommandDetailView(POSAttendanceView):
    def get(self, request, command_id):
        device, _, permissions, _ = self.context(request)
        self._require(permissions, 'commands.view', 'Você não possui permissão para consultar comandas nesta filial.')
        command = self._command(device, command_id)
        data = AttendanceCommandSerializer(command).data
        data['summary'] = command_summary(command)
        data['orders'] = list(AttendanceOrderItem.objects.filter(
            order__command=command,
        ).values('id', 'order_id', 'product_id', 'product_name', 'quantity', 'unit', 'unit_price', 'modifier_snapshot', 'notes', 'status', 'confirmed_at'))
        return Response(data)


class POSAttendanceBillRequestView(POSAttendanceView):
    def post(self, request, command_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.finalize', 'Você não possui permissão para solicitar conta.')
        serializer = AttendanceBillRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            command, replayed = set_bill_requested(
                command=self._command(device, command_id), user=operator,
                idempotency_key=serializer.validated_data['idempotency_key'], requested=True,
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(AttendanceCommandSerializer(command).data)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSAttendanceBillClearView(POSAttendanceView):
    def post(self, request, command_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.finalize', 'Você não possui permissão para resolver a solicitação de conta.')
        serializer = AttendanceBillRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            command, replayed = set_bill_requested(
                command=self._command(device, command_id), user=operator,
                idempotency_key=serializer.validated_data['idempotency_key'], requested=False,
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(AttendanceCommandSerializer(command).data)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSAttendanceCommandItemsView(POSAttendanceView):
    def post(self, request, command_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.add_items', 'Você não possui permissão para adicionar itens.')
        command = self._command(device, command_id)
        serializer = AttendanceItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            _, items, replayed = add_order_items(
                command=command, user=operator, items=serializer.validated_data['items'],
                idempotency_key=serializer.validated_data['idempotency_key'],
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(
            AttendanceOrderItemSerializer(items, many=True).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSAttendanceItemConfirmView(POSAttendanceView):
    def post(self, request, item_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.add_items', 'Você não possui permissão para confirmar itens.')
        item = get_object_or_404(AttendanceOrderItem.objects.select_related('order__command'), pk=item_id, order__command__branch=device.branch)
        serializer = AttendanceConfirmItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = confirm_order_item(
                item=item, user=operator, audit_metadata=self.audit_metadata(device, operator_session),
                **serializer.validated_data,
            )
        except AttendanceConflict as error:
            self._domain(error)
        return Response(AttendanceOrderItemSerializer(item).data)


class POSAttendanceItemCancelView(POSAttendanceView):
    def post(self, request, item_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.cancel_items', 'Você não possui permissão para cancelar itens.')
        item = get_object_or_404(
            AttendanceOrderItem.objects.select_related('order__command'),
            pk=item_id, order__command__branch=device.branch,
        )
        serializer = AttendanceCancelItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item, replayed = cancel_order_item(
                item=item, user=operator, audit_metadata=self.audit_metadata(device, operator_session),
                **serializer.validated_data,
            )
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(AttendanceOrderItemSerializer(item).data)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSAttendanceCommandPaymentView(POSAttendanceView):
    def get(self, request, command_id):
        device, _, permissions, _ = self.context(request)
        self._require(permissions, 'commands.payments.view', 'Você não possui permissão para consultar pagamentos.')
        command = self._command(device, command_id)
        return Response({'summary': command_summary(command), 'payments': AttendancePaymentSerializer(command.payments.select_related('payment_method'), many=True).data})

    def post(self, request, command_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.payments.record', 'Você não possui permissão para registrar pagamentos.')
        command = self._command(device, command_id)
        serializer = AttendancePaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            payment = record_attendance_payment(
                command=command, user=operator, payment_method_id=data['payment_method'],
                amount=data['amount'], received_amount=data.get('received_amount'),
                cash_session_id=data.get('cash_session'), idempotency_key=data['idempotency_key'],
                discount=data.get('discount'), discount_authorization=data.get('discount_authorization'),
                service_fee_waived=data.get('service_fee_waived'), service_fee_authorization=data.get('service_fee_authorization'),
                pos_device=device, pos_permission_codes=permissions,
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        return Response(AttendancePaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class POSAttendancePaymentReverseView(POSAttendanceView):
    def post(self, request, payment_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.payments.reverse', 'Você não possui permissão para estornar pagamentos.')
        payment = get_object_or_404(
            AttendancePayment.objects.select_related('command'), pk=payment_id,
            command__branch=device.branch,
        )
        serializer = AttendanceReversePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reversal, replayed = reverse_attendance_payment(
                payment=payment, user=operator, **serializer.validated_data,
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(AttendancePaymentSerializer(reversal).data, status=status.HTTP_201_CREATED)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSAttendanceCommandFinalizeView(POSAttendanceView):
    def post(self, request, command_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.finalize', 'Você não possui permissão para fechar comandas.')
        command = self._command(device, command_id)
        serializer = AttendanceFinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            command = finalize_attendance_command(
                command=command, user=operator, cash_session_id=data['cash_session'],
                payments=data['payments'], idempotency_key=data['idempotency_key'],
                discount=data['discount'], discount_authorization=data.get('discount_authorization'),
                service_fee_waived=data['service_fee_waived'], service_fee_authorization=data.get('service_fee_authorization'),
                pos_device=device, pos_permission_codes=permissions,
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        return Response(AttendanceCommandSerializer(command).data)


class POSAttendanceCommandTransferView(POSAttendanceView):
    def post(self, request, command_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.transfer', 'Você não possui permissão para transferir comandas.')
        serializer = AttendanceTransferCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            command, replayed = transfer_attendance_command(
                command=self._command(device, command_id), user=operator,
                audit_metadata=self.audit_metadata(device, operator_session), **serializer.validated_data,
            )
        except AttendanceConflict as error:
            self._domain(error)
        return Response({**AttendanceCommandSerializer(command).data, 'idempotency_replayed': replayed})


class POSAttendanceCommandItemsTransferView(POSAttendanceView):
    def post(self, request, command_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'commands.transfer_items', 'Você não possui permissão para transferir itens.')
        serializer = AttendanceTransferItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            destination, item_ids, replayed = transfer_attendance_items(
                command=self._command(device, command_id), destination_id=serializer.validated_data['command'],
                items=serializer.validated_data['items'], user=operator,
                idempotency_key=serializer.validated_data['idempotency_key'],
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        return Response({'command': AttendanceCommandSerializer(destination).data, 'item_ids': item_ids, 'idempotency_replayed': replayed})


class POSTableAttendanceView(POSAttendanceView):
    def _attendance(self, device, attendance_id):
        return get_object_or_404(TableAttendance.objects.select_related('table', 'customer', 'sale'), pk=attendance_id, branch=device.branch)

    def get(self, request, attendance_id):
        device, _, permissions, _ = self.context(request)
        self._require(permissions, 'tables.view', 'Você não possui permissão para consultar mesas.')
        attendance = self._attendance(device, attendance_id)
        data = TableAttendanceSerializer(attendance).data
        data['summary'] = table_summary(attendance)
        data['orders'] = list(TableOrderItem.objects.filter(order__attendance=attendance).values('id', 'order_id', 'product_id', 'product_name', 'quantity', 'unit', 'unit_price', 'modifier_snapshot', 'notes', 'status', 'confirmed_at'))
        return Response(data)


class POSTableAttendanceOrdersView(POSTableAttendanceView):
    def post(self, request, attendance_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.add_items', 'Você não possui permissão para salvar pedidos de mesa.')
        serializer = AttendanceItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            _, items, replayed = save_table_order(attendance=self._attendance(device, attendance_id), user=operator,
                items=serializer.validated_data['items'], idempotency_key=serializer.validated_data['idempotency_key'],
                audit_metadata=self.audit_metadata(device, operator_session))
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(TableOrderItemSerializer(items, many=True).data, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSTableAttendanceItemCancelView(POSAttendanceView):
    def post(self, request, item_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.cancel_items', 'Você não possui permissão para cancelar itens.')
        serializer = AttendanceCancelItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = get_object_or_404(TableOrderItem.objects.select_related('order__attendance'), pk=item_id, order__attendance__branch=device.branch)
        try:
            item, replayed = cancel_table_item(item=item, user=operator, audit_metadata=self.audit_metadata(device, operator_session), **serializer.validated_data)
        except AttendanceConflict as error:
            self._domain(error)
        return Response(TableOrderItemSerializer(item).data, headers={'Idempotency-Replayed': 'true'} if replayed else None)


class POSTableAttendancePaymentsView(POSTableAttendanceView):
    def get(self, request, attendance_id):
        device, _, permissions, _ = self.context(request)
        self._require(permissions, 'tables.payments.view', 'Você não possui permissão para consultar pagamentos.')
        attendance = self._attendance(device, attendance_id)
        return Response({'summary': table_summary(attendance), 'payments': TablePaymentSerializer(attendance.payments.select_related('payment_method', 'cash_session').prefetch_related('allocations'), many=True).data})

    def post(self, request, attendance_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.payments.record', 'Você não possui permissão para registrar pagamentos.')
        serializer = TablePaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        attendance = self._attendance(device, attendance_id)
        amount = data['amount']
        if data['mode'] == 'remaining':
            amount = Decimal(table_summary(attendance)['remaining_balance'])
        elif data['mode'] == 'equal_people':
            if not attendance.people_count:
                raise ValidationError({'people_count': 'Informe a quantidade de pessoas para dividir igualmente.'})
            remaining = Decimal(table_summary(attendance)['remaining_balance'])
            active_people = set(attendance.payments.filter(
                status='applied', reversal__isnull=True,
            ).values_list('allocations__person_number', flat=True)) - {None}
            if attendance.equal_split_total is None:
                attendance.equal_split_total = remaining
                attendance.equal_split_people_count = attendance.people_count
                attendance.save(update_fields=('equal_split_total', 'equal_split_people_count', 'updated_at'))
            elif attendance.equal_split_people_count != attendance.people_count:
                raise ValidationError({'people_count': 'A divisão igual já foi iniciada com outra quantidade de pessoas.'})
            if len(active_people) >= attendance.equal_split_people_count:
                raise ValidationError({'payments': 'Todas as parcelas da divisão igual já foram registradas.'})
            person_number = next(index for index in range(1, attendance.equal_split_people_count + 1) if index not in active_people)
            cents = int(attendance.equal_split_total * 100)
            base, remainder = divmod(cents, attendance.equal_split_people_count)
            amount = Decimal(base + (1 if person_number <= remainder else 0)) / Decimal('100')
            data['allocations'] = [{'person_number': person_number, 'amount': amount}]
        try:
            payment, replayed = record_table_payment(attendance=attendance, user=operator, payment_method_id=data['payment_method'], amount=amount,
                received_amount=data.get('received_amount'), cash_session_id=data.get('cash_session'), allocations=data.get('allocations'),
                idempotency_key=data['idempotency_key'], discount=data.get('discount'), discount_authorization=data.get('discount_authorization'),
                service_fee_waived=data.get('service_fee_waived'), service_fee_authorization=data.get('service_fee_authorization'),
                pos_device=device, pos_permission_codes=permissions, audit_metadata=self.audit_metadata(device, operator_session))
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(TablePaymentSerializer(payment).data, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSTableAttendancePaymentReverseView(POSAttendanceView):
    def post(self, request, payment_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.payments.reverse', 'Você não possui permissão para estornar pagamentos.')
        serializer = AttendanceReversePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = get_object_or_404(TablePayment.objects.select_related('attendance'), pk=payment_id, attendance__branch=device.branch)
        try:
            reversal, replayed = reverse_table_payment(payment=payment, user=operator, audit_metadata=self.audit_metadata(device, operator_session), **serializer.validated_data)
        except AttendanceConflict as error:
            self._domain(error)
        response = Response(TablePaymentSerializer(reversal).data, status=status.HTTP_201_CREATED)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class POSTableAttendanceBillView(POSTableAttendanceView):
    requested = True

    def post(self, request, attendance_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.close', 'Você não possui permissão para solicitar conta.')
        serializer = AttendanceBillRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attendance, replayed = set_table_bill_requested(attendance=self._attendance(device, attendance_id), user=operator, requested=self.requested,
                idempotency_key=serializer.validated_data['idempotency_key'], audit_metadata=self.audit_metadata(device, operator_session))
        except AttendanceConflict as error:
            self._domain(error)
        return Response(TableAttendanceSerializer(attendance).data, headers={'Idempotency-Replayed': 'true'} if replayed else None)


class POSTableAttendanceCloseView(POSTableAttendanceView):
    def post(self, request, attendance_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.close', 'Você não possui permissão para fechar mesas.')
        serializer = AttendanceBillRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attendance, replayed = close_table_attendance(attendance=self._attendance(device, attendance_id), user=operator,
                idempotency_key=serializer.validated_data['idempotency_key'], audit_metadata=self.audit_metadata(device, operator_session))
        except AttendanceConflict as error:
            self._domain(error)
        return Response(TableAttendanceSerializer(attendance).data, headers={'Idempotency-Replayed': 'true'} if replayed else None)


class POSTableAttendanceItemsTransferView(POSTableAttendanceView):
    def post(self, request, attendance_id):
        device, operator, permissions, operator_session = self.context(request)
        self._require(permissions, 'tables.transfer_items', 'Você não possui permissão para transferir itens de mesa.')
        serializer = AttendanceTransferItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            destination, item_ids, replayed = transfer_table_items(
                attendance=self._attendance(device, attendance_id), destination_id=serializer.validated_data['command'],
                items=serializer.validated_data['items'], user=operator,
                idempotency_key=serializer.validated_data['idempotency_key'],
                audit_metadata=self.audit_metadata(device, operator_session),
            )
        except AttendanceConflict as error:
            self._domain(error)
        return Response({'attendance': TableAttendanceSerializer(destination).data, 'item_ids': item_ids, 'idempotency_replayed': replayed})


class POSSalePreviewView(POSQuickSaleView):
    def post(self, request):
        device, operator, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        serializer = POSSalePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        items = self._items(data['items'])
        availability = assess_sale_stock_availability(
            company=device.branch.company,
            raw_items=items,
            branch=device.branch,
            channel=SalesChannel.COUNTER,
        )
        if not availability['available'] and availability['enforced']:
            error = DomainValidationError(
                code='stock_unavailable',
                message='Estoque insuficiente para os itens selecionados.',
                details=availability,
            )
            error.status_code = status.HTTP_409_CONFLICT
            raise error
        result = calculate_preview(
            company=device.branch.company,
            operation_type=OperationType.SALE,
            raw_items=items,
            discount=data['discount'],
            charged_amount=None,
            beneficiary_user=None,
            branch=device.branch,
            channel=SalesChannel.COUNTER,
            service_fee_waived=data['service_fee_waived'],
        )
        output = CalculationOutputSerializer(data=result)
        output.is_valid(raise_exception=True)
        return Response(output.data)


class POSSaleAvailabilityView(POSQuickSaleView):
    def post(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        serializer = POSStockAvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = assess_sale_stock_availability(
            company=device.branch.company,
            raw_items=self._items(serializer.validated_data['items']),
            branch=device.branch,
            channel=SalesChannel.COUNTER,
        )
        return Response(result)


def _authorizer_options(branch, permission_code):
    return [
        {
            'id': user.pk,
            'display_name': user.get_full_name().strip() or user.email,
        }
        for user in eligible_pos_authorizers(branch, permission_code)
    ]


class POSDiscountAuthorizersView(POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        return Response({
            'authorizers': _authorizer_options(device.branch, 'sales.apply_discount'),
        })


class POSItemDiscountAuthorizersView(POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        return Response({
            'authorizers': _authorizer_options(device.branch, 'sales.apply_item_discount'),
        })


class POSServiceFeeAuthorizersView(POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        return Response({
            'authorizers': _authorizer_options(device.branch, 'sales.waive_service_fee'),
        })


class POSDiscountAuthorizationValidationView(POSQuickSaleView):
    def post(self, request):
        device, operator, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        serializer = POSDiscountAuthorizationValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        permission_code = {
            'sale': 'sales.apply_discount',
            'item': 'sales.apply_item_discount',
            'service_fee': 'sales.waive_service_fee',
        }[data['type']]
        try:
            validate_discount_authorization(
                device.branch, data, permission_code=permission_code,
                authorization_field='authorization',
                allow_pos_only=True, pos_device=device, requester=operator,
                device_validated=True,
            )
        except DjangoValidationError as error:
            messages = error.message_dict.get('authorization', error.messages)
            raise DomainValidationError(
                code='discount_authorization_invalid', message=messages[0],
            )
        return Response({'valid': True})


class POSSaleCheckoutOptionsView(POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        from apps.sales.models import PaymentMethod

        mode, fixed_register = effective_cash_settings(device)
        sessions = CashSession.objects.filter(
            branch=device.branch, status='open',
        ).select_related('cash_register', 'opened_by').order_by('id')
        fixed_cash_available = True
        if mode == 'FIXED':
            fixed_cash_available = bool(
                fixed_register and fixed_register.status == CashRegisterStatus.ACTIVE
            )
            sessions = sessions.filter(cash_register=fixed_register) if fixed_cash_available else sessions.none()
        methods = PaymentMethod.objects.filter(
            company_id=device.branch.company_id, status=Status.ACTIVE,
        ).order_by('name', 'id').values('id', 'code', 'name')
        return Response({
            'payment_methods': list(methods),
            'cash_binding_mode': mode,
            'fixed_register': (
                {'id': fixed_register.pk, 'name': fixed_register.name}
                if mode == 'FIXED' and fixed_register else None
            ),
            'cash_required': True,
            'fixed_cash_available': fixed_cash_available,
            'cash_sessions': [
                {
                    'id': session.pk,
                    'register_name': session.cash_register.name,
                    'opened_by_name': session.opened_by.get_full_name().strip() or session.opened_by.email,
                }
                for session in sessions
            ],
        })


class POSFinalizeSaleView(POSQuickSaleView):
    def post(self, request):
        device, operator, permissions, operator_session = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        serializer = POSFinalizeSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        session = _pos_sale_session(device, data['cash_session'])
        customer = None
        if data.get('customer') is not None:
            customer = Customer.objects.filter(
                pk=data['customer'], company_id=device.branch.company_id,
                status=Status.ACTIVE,
            ).first()
            if customer is None:
                raise ValidationError({'customer': 'Cliente inválido, inativo ou fora da empresa.'})
        sale = finalize_sale(
            branch=device.branch,
            user=operator,
            operation_type=OperationType.SALE,
            cash_session=session,
            seller_user=operator,
            customer=customer,
            items=self._items(data['items']),
            payments=data['payments'],
            discount=data['discount'],
            service_fee_waived=data['service_fee_waived'],
            discount_authorization=data.get('discount_authorization'),
            item_discount_authorization=data.get('item_discount_authorization'),
            service_fee_authorization=data.get('service_fee_authorization'),
            idempotency_key=data['idempotency_key'],
            channel=SalesChannel.COUNTER,
            pos_device=device,
            allow_pos_only=True,
            audit_metadata=self.audit_metadata(device, operator_session),
            pos_permission_codes=permissions,
            pos_device_validated=True,
        )
        replayed = bool(getattr(sale, '_idempotency_replayed', False))
        request.branch_context = device.branch
        sale = Sale.objects.select_related(
            'company', 'branch', 'cash_session', 'created_by', 'seller_user', 'pos_device',
        ).prefetch_related('items__product', 'payments__payment_method').get(pk=sale.pk)
        response = Response(
            {
                'sale': SaleSerializer(sale, context={'request': request}).data,
                'cash_state': cash_state_for_device(device, permissions, operator),
                'effects': {
                    'tickets': list(sale.items.filter(
                        product__emits_ticket=True,
                    ).values_list('sale_ticket__number', flat=True)),
                    'production_job_count': sum(
                        item.production_jobs.filter(event='new').count()
                        for item in sale.items.all()
                    ),
                },
            },
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
        if replayed:
            request.audit_fallback_suppressed = True
            response['Idempotency-Replayed'] = 'true'
        return response


class POSCashBeneficiariesView(POSCashView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'cash_registers.withdraw' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar sangrias nesta filial.')
        category = request.query_params.get('category')
        if category not in WithdrawalCategory.values:
            raise ValidationError({'category': 'Informe uma categoria de sangria válida.'})
        beneficiaries = cash_beneficiaries(device.branch, category)
        return Response({'beneficiaries': CashBeneficiarySerializer(beneficiaries, many=True).data})


class POSCashSessionOpenView(POSCashView):
    def post(self, request):
        device, operator, permissions, operator_session = self.context(request)
        require_branch_feature(device.branch, 'cash_register')
        serializer = POSOpenCashSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mode, configured_register = effective_cash_settings(device)
        requested_register = serializer.validated_data.get('register')
        if mode == 'FIXED':
            if requested_register is not None:
                raise DomainValidationError(
                    code='fixed_cash_register',
                    message='Este dispositivo usa o caixa configurado para ele.',
                )
            register = CashRegister.objects.filter(
                pk=getattr(configured_register, 'pk', None), branch=device.branch,
                status=CashRegisterStatus.ACTIVE,
            ).first()
            if not register:
                error = DomainValidationError(
                    code='cash_register_unavailable',
                    message='O caixa configurado para este dispositivo não está ativo.',
                )
                error.status_code = status.HTTP_409_CONFLICT
                raise error
        else:
            if requested_register is None:
                raise DomainValidationError(
                    code='cash_register_required',
                    message='Selecione um caixa para abrir a sessão.',
                    details={'register': ['Este campo é obrigatório.']},
                )
            register = get_object_or_404(
                CashRegister, pk=requested_register, branch=device.branch,
                status=CashRegisterStatus.ACTIVE,
            )
        session = open_session(
            cash_register=register,
            opening_amount=serializer.validated_data['opening_amount'],
            user=operator,
            current_branch=device.branch,
            allow_pos_only=True,
            audit_metadata=self.audit_metadata(device, operator_session),
        )
        data = CashSessionSerializer(session).data
        data['cash_state'] = self.mutation_state(device, permissions, session, operator)
        return Response(data, status=status.HTTP_201_CREATED)


class POSCashSessionSummaryView(POSCashView):
    def get(self, request, session_id):
        device, _, permissions, _ = self.context(request)
        self.require_read_permission(permissions)
        session = self.session_for_device(session_id, device)
        summary = redact_operational_summary(
            session_operational_summary(session),
            include_costs=False,
            include_commission=False,
        )
        return Response(self.serialize(summary))

    @staticmethod
    def serialize(value):
        if isinstance(value, Decimal):
            return f'{value:.2f}'
        if isinstance(value, dict):
            return {key: POSCashSessionSummaryView.serialize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [POSCashSessionSummaryView.serialize(item) for item in value]
        return value


class POSCashSessionMovementView(POSCashView):
    serializer_class = None
    service = None
    is_withdrawal = False

    def post(self, request, session_id):
        device, operator, permissions, operator_session = self.context(request)
        require_branch_feature(device.branch, 'cash_register')
        session = self.session_for_device(session_id, device)
        payload = request.data.copy()
        if self.is_withdrawal:
            if (
                'beneficiary_user' in payload
                or 'beneficiary_supplier' in payload
            ):
                raise ValidationError({
                    'beneficiary': 'Use beneficiary_type e beneficiary_id no POS.'
                })
            beneficiary_type = payload.pop('beneficiary_type', None)
            beneficiary_id = payload.pop('beneficiary_id', None)
            if beneficiary_type is not None:
                if beneficiary_type not in ('user', 'supplier'):
                    raise ValidationError({
                        'beneficiary_type': 'Tipo de beneficiário inválido.'
                    })
                if beneficiary_id is None:
                    raise ValidationError({
                        'beneficiary_id': 'Informe o beneficiário da sangria.'
                    })
                payload[f'beneficiary_{beneficiary_type}'] = beneficiary_id
            elif beneficiary_id is not None:
                raise ValidationError({
                    'beneficiary_type': 'Informe o tipo do beneficiário.'
                })
        serializer = self.serializer_class(data=payload)
        serializer.is_valid(raise_exception=True)
        movement = self.service(
            cash_session=session,
            **serializer.validated_data,
            user=operator,
            current_branch=device.branch,
            allow_pos_only=True,
            audit_metadata=self.audit_metadata(device, operator_session),
        )
        replayed = bool(getattr(movement, '_idempotency_replayed', False))
        request.audit_fallback_suppressed = replayed
        movement = CashMovement.objects.select_related(
            'cash_session', 'cash_session__cash_register', 'cash_session__branch', 'user',
            'beneficiary_user', 'beneficiary_supplier',
        ).get(pk=movement.pk)
        data = CashMovementSerializer(movement).data
        data['cash_state'] = self.mutation_state(
            device, permissions, movement.cash_session, operator
        )
        return Response(
            data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )


class POSCashSessionEntryView(POSCashSessionMovementView):
    serializer_class = ManualEntryRequestSerializer
    service = staticmethod(record_manual_entry)


class POSCashSessionWithdrawalView(POSCashSessionMovementView):
    serializer_class = WithdrawalRequestSerializer
    service = staticmethod(record_withdrawal)
    is_withdrawal = True


class POSCashSessionCloseView(POSCashView):
    def post(self, request, session_id):
        device, operator, permissions, operator_session = self.context(request)
        session = self.session_for_device(session_id, device)
        serializer = CloseSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = close_session(
            cash_session=session,
            **serializer.validated_data,
            user=operator,
            current_branch=device.branch,
            allow_pos_only=True,
            audit_metadata=self.audit_metadata(device, operator_session),
        )
        data = CashSessionSerializer(session).data
        data['cash_state'] = self.mutation_state(device, permissions, session, operator)
        return Response(data)


class POSAdminDeviceViewSet(viewsets.ModelViewSet):
    """Backoffice-only lifecycle and settings for already paired POS devices."""

    serializer_class = POSAdminDeviceSerializer
    permission_classes = [FunctionalCompanyPermission]
    pagination_class = StandardPagination
    http_method_names = ('get', 'patch', 'put', 'post', 'delete', 'head', 'options')
    permission_codes = {
        'list': 'pos_devices.view',
        'retrieve': 'pos_devices.view',
        'update': 'pos_devices.manage',
        'partial_update': 'pos_devices.manage',
        'block': 'pos_devices.manage',
        'unblock': 'pos_devices.manage',
        'revoke': 'pos_devices.manage',
        'replace': 'pos_devices.manage',
        'device_settings': 'pos_devices.manage',
    }
    audit_fields = ('name', 'status', 'app_version', 'os_version', 'device_model', 'last_seen_at')

    def get_queryset(self):
        company_id = self.request.query_params.get('company')
        if not company_id:
            raise ValidationError({'company': 'Selecione uma empresa para consultar dispositivos POS.'})
        permission_code = self.permission_codes.get(self.action, 'pos_devices.view')
        queryset = POSDevice.objects.filter(
            branch__in=accessible_branches(self.request.user, permission_code),
            branch__company_id=company_id,
        ).select_related('branch__company', 'replaced_by')
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)
        return queryset

    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, self.audit_fields)
        device = serializer.save()
        audit_log(
            actor=self.request.user, action='pos.device.update', obj=device,
            company=device.branch.company, branch=device.branch, before=before,
            after=model_snapshot(device, self.audit_fields),
        )

    def _transition(self, request, expected_status, target_status, *, replacement=None):
        device = self.get_object()
        if device.status != expected_status:
            raise DomainValidationError(
                code='device_status_transition_invalid',
                message='Esta transicao nao esta disponivel para o status atual do dispositivo.',
                status_code=409,
            )
        if target_status == POSDevice.Status.ACTIVE:
            assert_branch_device_limit(device.branch)
        return set_device_status(device, target_status, actor=request.user, replacement=replacement)

    @action(detail=True, methods=('post',))
    def block(self, request, pk=None):
        device = self._transition(request, POSDevice.Status.ACTIVE, POSDevice.Status.BLOCKED)
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=('post',))
    def unblock(self, request, pk=None):
        device = self._transition(request, POSDevice.Status.BLOCKED, POSDevice.Status.ACTIVE)
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=('post',))
    def revoke(self, request, pk=None):
        device = self.get_object()
        if device.status not in {POSDevice.Status.ACTIVE, POSDevice.Status.BLOCKED}:
            raise DomainValidationError(
                code='device_status_transition_invalid',
                message='Este dispositivo nao pode ser revogado no status atual.',
                status_code=409,
            )
        device = set_device_status(device, POSDevice.Status.REVOKED, actor=request.user)
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=('post',))
    def replace(self, request, pk=None):
        device = self.get_object()
        replacement_id = request.data.get('replacement_device')
        replacement = self.get_queryset().filter(pk=replacement_id).first()
        if device.status != POSDevice.Status.ACTIVE or not replacement or replacement == device or replacement.status != POSDevice.Status.ACTIVE:
            raise DomainValidationError(
                code='device_replacement_invalid',
                message='Informe outro dispositivo ativo da mesma filial para a substituicao.',
                status_code=409,
            )
        device = set_device_status(device, POSDevice.Status.REPLACED, actor=request.user, replacement=replacement)
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=('get', 'patch', 'delete'), url_path='settings')
    def device_settings(self, request, pk=None):
        device = self.get_object()
        instance = POSDeviceSettings.objects.filter(device=device).first()
        if request.method == 'GET':
            return Response(POSDeviceSettingsSerializer(
                instance or POSDeviceSettings(device=device), context={'device': device}
            ).data)
        if request.method == 'DELETE':
            if instance:
                before = model_snapshot(instance, POSDeviceSettingsSerializer.Meta.fields)
                instance.delete()
                audit_log(
                    actor=request.user, action='pos.device.settings.reset', obj=device,
                    company=device.branch.company, branch=device.branch, before=before,
                )
            return Response(status=status.HTTP_204_NO_CONTENT)
        instance, _ = POSDeviceSettings.objects.get_or_create(device=device)
        fields = tuple(field for field in POSDeviceSettingsSerializer.Meta.fields if field not in {'id', 'device', 'effective_settings', 'cash_register_options', 'created_at', 'updated_at'})
        before = model_snapshot(instance, fields)
        serializer = POSDeviceSettingsSerializer(instance, data=request.data, partial=True, context={'device': device})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        audit_log(
            actor=request.user, action='pos.device.settings.update', obj=instance,
            company=device.branch.company, branch=device.branch, before=before,
            after=model_snapshot(instance, fields),
        )
        return Response(POSDeviceSettingsSerializer(instance, context={'device': device}).data)
