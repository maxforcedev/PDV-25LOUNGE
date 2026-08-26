from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.companies.models import Branch, Company, UserCompanyAccess

from .models import PlatformUserAccess, SupportSession
from .services import resolve_effective_status, user_has_platform_permission


TENANT_EXEMPT_PREFIXES = (
    '/api/v1/platform/',
    '/api/v1/auth/',
    '/api/v1/public/',
    '/api/v1/saas/owner/',
)


def _company_ids_from_object(obj):
    if obj is None:
        return set()
    if isinstance(obj, Company):
        return {obj.pk}
    if isinstance(obj, Branch):
        return {obj.company_id}
    if isinstance(obj, UserCompanyAccess):
        return {obj.company_id}
    company_id = getattr(obj, 'company_id', None)
    if company_id:
        return {company_id}
    branch = getattr(obj, 'branch', None)
    if branch is not None:
        return {branch.company_id}
    stock = getattr(obj, 'stock', None)
    if stock is not None:
        return {stock.branch.company_id}
    cash_session = getattr(obj, 'cash_session', None)
    if cash_session is not None:
        return {cash_session.branch.company_id}
    purchase_order = getattr(obj, 'purchase_order', None)
    if purchase_order is not None:
        return {purchase_order.company_id}
    transfer_item = getattr(obj, 'transfer_item', None)
    if transfer_item is not None:
        return {transfer_item.transfer.company_id}
    if hasattr(obj, 'company_accesses'):
        return set(obj.company_accesses.filter(is_active=True).values_list('company_id', flat=True))
    return set()


def _routed_object(request, view):
    queryset = getattr(view, 'queryset', None)
    model = getattr(queryset, 'model', None)
    if model is None:
        basename = getattr(view, 'basename', None)
        if basename in ('company', 'branch', 'user', 'cash-beneficiary'):
            from apps.accounts.models import User

            model = {
                'company': Company, 'branch': Branch, 'user': User,
                'cash-beneficiary': User,
            }[basename]
        elif basename in ('category', 'product', 'branchprice'):
            from apps.products.models import BranchProductPrice, Category, Product

            model = {
                'category': Category, 'product': Product, 'branchprice': BranchProductPrice,
            }[basename]
        elif basename in (
            'stock', 'stock-movement', 'stock-transfer', 'transfer-divergence',
            'loss-record', 'inventory-count',
        ):
            from apps.inventory.models import (
                InventoryCount, LossRecord, Stock, StockMovement, StockTransfer,
                TransferDivergence,
            )

            model = {
                'stock': Stock,
                'stock-movement': StockMovement,
                'stock-transfer': StockTransfer,
                'transfer-divergence': TransferDivergence,
                'loss-record': LossRecord,
                'inventory-count': InventoryCount,
            }[basename]
        elif basename in ('purchase-order', 'purchase-receipt', 'payable-installment'):
            from apps.purchases.models import (
                PayableInstallment, PurchaseOrder, PurchaseReceipt,
            )

            model = {
                'purchase-order': PurchaseOrder,
                'purchase-receipt': PurchaseReceipt,
                'payable-installment': PayableInstallment,
            }[basename]
        elif basename in ('cash-register', 'cash-session', 'cash-movement'):
            from apps.cash.models import CashMovement, CashRegister, CashSession

            model = {
                'cash-register': CashRegister, 'cash-session': CashSession,
                'cash-movement': CashMovement,
            }[basename]
        elif basename in ('payment-method', 'promotion', 'sale'):
            from apps.sales.models import PaymentMethod, Promotion, Sale

            model = {
                'payment-method': PaymentMethod, 'promotion': Promotion, 'sale': Sale,
            }[basename]
        elif basename in ('table', 'command', 'orderitem'):
            from apps.commands.models import Command, OrderItem, Table

            model = {
                'table': Table, 'command': Command, 'orderitem': OrderItem,
            }[basename]
        elif basename in ('access-profile', 'user-permission-block', 'user-commission-override'):
            from apps.companies.models import AccessProfile, UserCommissionOverride, UserPermissionBlock

            model = {
                'access-profile': AccessProfile,
                'user-permission-block': UserPermissionBlock,
                'user-commission-override': UserCommissionOverride,
            }[basename]
    kwargs = (getattr(request, 'parser_context', None) or {}).get('kwargs', {})
    lookup = kwargs.get(getattr(view, 'lookup_url_kwarg', None) or getattr(view, 'lookup_field', 'pk'))
    if model is None or lookup is None:
        return None
    lookup_field = getattr(view, 'lookup_field', 'pk')
    try:
        return model._default_manager.filter(**{lookup_field: lookup}).first()
    except (TypeError, ValueError):
        return None


def _request_company_ids(request, view, user):
    obj = _routed_object(request, view)
    object_ids = _company_ids_from_object(obj)
    supplied_ids = set()
    branch_id = request.headers.get('X-Branch-ID')
    if branch_id:
        branch = Branch.objects.filter(pk=branch_id).only('company_id').first()
        if not branch:
            raise PermissionDenied('Filial de contexto invalida.')
        supplied_ids.add(branch.company_id)
    company_id = request.query_params.get('company')
    data = request.data if isinstance(request.data, dict) else {}
    company_id = company_id or data.get('company')
    payload_branch_id = data.get('branch')
    if payload_branch_id:
        payload_branch = Branch.objects.filter(pk=payload_branch_id).only('company_id').first()
        if not payload_branch:
            raise PermissionDenied('Filial informada invalida.')
        supplied_ids.add(payload_branch.company_id)
    for field in ('origin_branch', 'destination_branch'):
        payload_branch_id = data.get(field)
        if payload_branch_id:
            payload_branch = Branch.objects.filter(pk=payload_branch_id).only('company_id').first()
            if not payload_branch:
                raise PermissionDenied('Filial informada invalida.')
            supplied_ids.add(payload_branch.company_id)
    if company_id:
        try:
            supplied_ids.add(int(company_id))
        except (TypeError, ValueError) as error:
            raise PermissionDenied('Empresa de contexto invalida.') from error
    if object_ids and supplied_ids and object_ids != supplied_ids:
        raise PermissionDenied('O contexto informado nao corresponde ao objeto solicitado.')
    if object_ids:
        return object_ids
    if supplied_ids:
        return supplied_ids
    support_session = getattr(request, 'support_session', None)
    if support_session:
        return {support_session.company_id}
    return set(user.company_accesses.filter(
        is_active=True,
        saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
    ).values_list('company_id', flat=True))


def enforce_saas_request(request, user, view=None):
    if not request.path.startswith('/api/v1/') or request.path.startswith(TENANT_EXEMPT_PREFIXES):
        return
    view = view or (getattr(request, 'parser_context', None) or {}).get('view')
    if view is None:
        return
    company_ids = _request_company_ids(request, view, user)
    support_session = getattr(request, 'support_session', None)
    if support_session:
        if company_ids != {support_session.company_id}:
            raise PermissionDenied('A Support Session esta vinculada a outro tenant.')
        if request.method not in SAFE_METHODS and support_session.mode != SupportSession.Mode.READ_WRITE:
            raise PermissionDenied('A Support Session permite somente leitura.')
    elif not user.is_superuser:
        authorized_ids = set(UserCompanyAccess.objects.filter(
            user=user,
            company_id__in=company_ids,
            is_active=True,
            saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        ).values_list('company_id', flat=True))
        if authorized_ids != company_ids:
            raise PermissionDenied('Tenant fora do contexto autorizado.')
    if not company_ids:
        from .services import get_global_settings

        if get_global_settings().enforcement_enabled:
            raise PermissionDenied('O tenant alvo deve ser resolvido pelo objeto ou payload.')
        return
    for company in Company.objects.filter(pk__in=company_ids):
        effective = resolve_effective_status(company)
        if effective['can_operate']:
            continue
        if (
            support_session
            and request.method in SAFE_METHODS
            and effective['status'] not in ('INVALID_ENTITLEMENTS', 'UNMAPPED', 'INVALID_SUBSCRIPTION')
        ):
            continue
        raise PermissionDenied(f'O tenant esta em estado {effective["status"]}.')


def support_permission_decision(request, *, company_id=None, branch_id=None, obj=None):
    session = getattr(request, 'support_session', None)
    if not session or session.impersonated_user_id:
        return None
    if not user_has_platform_permission(request.support_actor, 'platform.support.manage'):
        return False
    if request.method not in SAFE_METHODS and session.mode != SupportSession.Mode.READ_WRITE:
        return False
    target_ids = _company_ids_from_object(obj)
    if branch_id:
        branch = Branch.objects.filter(pk=branch_id).select_related('company').first()
        if not branch:
            return False
        request.branch_context = branch
        target_ids.add(branch.company_id)
    if company_id:
        target_ids.add(int(company_id))
    return not target_ids or target_ids == {session.company_id}


class HasPlatformPermission(BasePermission):
    message = 'Acesso de plataforma ou permissao insuficiente.'

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.is_active or not user.can_login:
            return False
        try:
            access = PlatformUserAccess.objects.select_related('role').get(
                user=user, is_active=True
            )
        except PlatformUserAccess.DoesNotExist:
            return False
        required = getattr(view, 'required_platform_permission', None)
        if required is None and hasattr(view, 'platform_permission_codes'):
            required = view.platform_permission_codes.get(getattr(view, 'action', None))
        return bool(required) and access.role.permissions.filter(code=required).exists()


class IsCompanyOwner(BasePermission):
    message = 'A area de assinatura e exclusiva do Owner.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.is_active or not request.user.can_login:
            return False
        company_id = request.query_params.get('company') or request.data.get('company')
        if not company_id:
            return False
        return UserCompanyAccess.objects.filter(
            company_id=company_id,
            user=request.user,
            is_owner=True,
            is_active=True,
            saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        ).exists()


class SaaSTenantRuntimePermission(BasePermission):
    """Block unsafe tenant operations from current dates even if cron is delayed."""

    message = 'O estado SaaS atual nao permite operacoes neste tenant.'

    def has_permission(self, request, view):
        enforce_saas_request(request, request.user, view)
        return True
