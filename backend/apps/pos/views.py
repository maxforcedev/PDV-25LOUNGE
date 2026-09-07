from decimal import Decimal, InvalidOperation
from time import perf_counter

from django.db.models import CharField, DecimalField, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
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
from apps.companies.selectors import accessible_branches
from apps.companies.features import require_branch_feature
from apps.companies.models import Customer, Status
from apps.products.models import (
    BranchProductPrice, ModifierOption, Product, ProductBranchConfig,
    ProductModifierGroup,
)
from apps.products.models import SalesChannel
from apps.sales.models import OperationType, Sale
from apps.sales.serializers import (
    CalculationOutputSerializer, SaleCatalogProductSerializer, SaleSerializer,
)
from apps.sales.services import (
    catalog_products_with_available_stock, calculate_preview, discount_intent_is_nonzero,
    finalize_sale,
)

from .authentication import POSDeviceAuthentication, require_device, require_operator_session
from .models import POSDevice, POSDeviceSettings
from .serializers import (
    POSAdminDeviceSerializer, POSDeviceSettingsSerializer, POSOpenCashSessionSerializer,
    POSCustomerSerializer, POSFinalizeSaleSerializer, POSSalePreviewSerializer,
)
from .services import (
    assert_branch_device_limit, authenticate_operator, cash_state_for_device, confirm_pairing,
    effective_cash_settings, effective_settings, identify_branch, logout_operator, modules_for,
    operator_permission_codes, pos_operator_queryset, request_otp, set_device_status,
    request_pos_pin_reset, set_pos_pin, validate_device_operational, version_gate,
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
        return validate_device_operational(require_device(request), check_version=check_version)


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
        session, token = authenticate_operator(device, _required(request.data, 'operator_id'), _required(request.data, 'pin'))
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
        request_pos_pin_reset(self.device(request, check_version=True), operator_id)
        return Response({'detail': 'Se o operador estiver elegivel, recebera instrucoes por e-mail.'}, status=status.HTTP_202_ACCEPTED)


class BootstrapView(POSDeviceView):
    def get(self, request):
        started = perf_counter()
        device = self.device(request, check_version=True)
        session = require_operator_session(request, device)
        permissions, modules = modules_for(session.operator, device)
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
            'cash': cash_state_for_device(device, permissions),
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
        permissions = operator_permission_codes(operator_session.operator, device.branch)
        import logging

        logging.getLogger('pos.performance').info(
            'POS permission_context_ms=%s', round((perf_counter() - started) * 1000),
        )
        return device, operator_session.operator, permissions, operator_session

    @staticmethod
    def require_read_permission(permissions):
        if 'cash_registers.view' not in permissions:
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
    def mutation_state(device, permissions, session):
        state = cash_state_for_device(device, permissions)
        state['session_cash'] = session_cash_state(session)
        return state


class POSCashOverviewView(POSCashView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        self.require_operational_permission(permissions)
        return Response(cash_state_for_device(device, permissions))


def _pos_catalog_queryset(branch, *, search=None, barcode=None):
    branch_price = BranchProductPrice.objects.filter(
        branch=branch, product_id=OuterRef('pk')
    ).values('sale_price')[:1]
    branch_config = ProductBranchConfig.objects.filter(
        branch=branch, product_id=OuterRef('pk')
    )
    queryset = Product.objects.select_related('company', 'category').prefetch_related(
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
    ).annotate(
        effective_sale_price=Coalesce(
            Subquery(branch_price), 'sale_price', output_field=DecimalField()
        ),
        branch_available=Subquery(branch_config.values('is_available')[:1]),
        branch_counter=Coalesce(
            Subquery(branch_config.values('available_counter')[:1]), 'available_counter',
        ),
        effective_category_id=Coalesce(
            Subquery(branch_config.values('category_id')[:1]), 'category_id',
            output_field=Product._meta.get_field('category').target_field,
        ),
        effective_category_name=Coalesce(
            Subquery(branch_config.values('category__name')[:1]), 'category__name',
            output_field=CharField(),
        ),
    ).filter(
        company_id=branch.company_id,
        status=Status.ACTIVE,
        archived_at__isnull=True,
        is_sellable=True,
        branch_available=True,
        branch_counter=True,
    )
    if barcode is not None:
        queryset = queryset.filter(barcode=barcode)
    elif search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(internal_code__icontains=search)
            | Q(barcode__icontains=search)
        )
    return queryset.order_by('-is_favorite', 'name', 'id')


def _visible_pos_catalog(device, queryset):
    products = list(queryset)
    if effective_settings(device).get('show_out_of_stock_products', True):
        return products
    return catalog_products_with_available_stock(device.branch, products)


def _has_item_discount(items):
    for item in items:
        try:
            if discount_intent_is_nonzero(item.get('discount', '0.00')):
                return True
        except (DjangoValidationError, TypeError, ValueError):
            # Let the canonical calculator report an invalid monetary input.
            return True
    return False


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


class POSQuickSaleView(POSCashView):
    @staticmethod
    def _catalog_payload(request, products):
        request.branch_context = request._pos_branch
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
                'image': product['image'],
                'favorite': product['is_favorite'],
                'emits_ticket': product['emits_ticket'],
                'modifier_groups': product['modifier_groups'],
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
                request, _visible_pos_catalog(device, queryset),
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
        return Response(self._catalog_payload(request, [product])[0])


class POSCustomersView(POSQuickSaleView):
    def get(self, request):
        device, _, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        term = request.query_params.get('q', '').strip()
        customers = Customer.objects.filter(
            company_id=device.branch.company_id, status=Status.ACTIVE,
        )
        if term:
            customers = customers.filter(
                Q(name__icontains=term) | Q(phone__icontains=term)
                | Q(email__icontains=term) | Q(document__icontains=term)
            )
        return Response({'customers': POSCustomerSerializer(
            customers.order_by('name', 'id')[:20], many=True,
        ).data})

    def post(self, request):
        device, operator, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        serializer = POSCustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save(company=device.branch.company)
        audit_log(
            actor=operator, action='pos.customer.created', obj=customer,
            company=device.branch.company, branch=device.branch,
        )
        return Response(POSCustomerSerializer(customer).data, status=status.HTTP_201_CREATED)


class POSSalePreviewView(POSQuickSaleView):
    def post(self, request):
        device, operator, permissions, _ = self.context(request)
        if 'sales.create' not in permissions:
            raise PermissionDenied('Você não possui permissão para realizar vendas nesta filial.')
        serializer = POSSalePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if discount_intent_is_nonzero(data['discount']) and 'sales.apply_discount' not in permissions:
            raise PermissionDenied('Você não possui permissão para aplicar desconto.')
        if _has_item_discount(data['items']) and 'sales.apply_item_discount' not in permissions:
            raise PermissionDenied('Você não possui permissão para aplicar desconto por item.')
        if data['service_fee_waived'] and 'sales.waive_service_fee' not in permissions:
            raise PermissionDenied('Você não possui permissão para isentar taxa de serviço.')
        result = calculate_preview(
            company=device.branch.company,
            operation_type=OperationType.SALE,
            raw_items=self._items(data['items']),
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
        if _has_item_discount(data['items']) and 'sales.apply_item_discount' not in permissions:
            raise PermissionDenied('Você não possui permissão para aplicar desconto por item.')
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
        )
        replayed = bool(getattr(sale, '_idempotency_replayed', False))
        request.branch_context = device.branch
        sale = Sale.objects.select_related(
            'company', 'branch', 'cash_session', 'created_by', 'seller_user', 'pos_device',
        ).prefetch_related('items__product', 'payments__payment_method').get(pk=sale.pk)
        response = Response(
            {
                'sale': SaleSerializer(sale, context={'request': request}).data,
                'cash_state': cash_state_for_device(device, permissions),
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
        data['cash_state'] = self.mutation_state(device, permissions, session)
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
            device, permissions, movement.cash_session
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
        data['cash_state'] = self.mutation_state(device, permissions, session)
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
