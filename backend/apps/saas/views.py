import hashlib
import logging
import mimetypes
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.http import FileResponse, Http404
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.base.audit import audit_log
from apps.base.login_security import INVALID_LOGIN_MESSAGE, axes_lockout_message
from apps.companies.models import Company
from apps.companies.services import transfer_company_owner

from .models import (
    BillingRecord,
    Capability,
    CommercialLead,
    GlobalSaaSSettings,
    Plan,
    PlanEntitlement,
    PlanVersion,
    ProvisioningOperation,
    Subscription,
    SubscriptionRequest,
    SupportSession,
    TenantSaaSState,
)
from .permissions import HasPlatformPermission, IsCompanyOwner
from .serializers import (
    BillingRecordSerializer,
    BRANDING_ASSET_FIELDS,
    CancellationRequestSerializer,
    CapabilitySerializer,
    CommercialLeadSerializer,
    CommercialLeadStatusSerializer,
    CycleUsageSerializer,
    GlobalSaaSSettingsSerializer,
    ManualPaymentSerializer,
    MapSubscriptionSerializer,
    PlanChangeRequestSerializer,
    PlanEntitlementSerializer,
    PlanSerializer,
    PlanVersionSerializer,
    PlatformLoginSerializer,
    PlatformCommercialLeadSerializer,
    PlatformUserSerializer,
    PublicPlanVersionSerializer,
    ProvisioningResultSerializer,
    ProvisioningSerializer,
    PublicBrandingSerializer,
    SubscriptionRequestSerializer,
    SubscriptionSerializer,
    SupportSessionCreateSerializer,
    SupportSessionSerializer,
    TenantSaaSStateSerializer,
)


logger = logging.getLogger(__name__)
from .services import (
    approve_tenant,
    archive_tenant,
    current_subscription,
    end_subscription_trial,
    enable_saas_enforcement,
    end_support_session,
    extend_subscription_trial,
    get_global_settings,
    map_existing_company,
    OwnerEmailAlreadyExists,
    process_subscription_lifecycle,
    request_cancellation,
    request_plan_change,
    resource_usage,
    resolve_subscription_request,
    reject_tenant,
    resolve_effective_status,
    set_financial_suspension,
    set_admin_suspension,
    set_subscription_billing_mode,
    sync_cycle_usage,
    user_has_platform_permission,
)


def _critical_action(request):
    reason = str(request.data.get('reason', '')).strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo da acao critica.'})
    if not request.user.check_password(request.data.get('current_password', '')):
        raise ValidationError({'current_password': 'Senha atual invalida.'})
    return reason


def _without_critical_fields(data):
    payload = data.copy()
    payload.pop('reason', None)
    payload.pop('current_password', None)
    return payload


class PublicPlanVersionListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        versions = PlanVersion.objects.filter(
            is_public=True,
            is_active=True,
            plan__is_active=True,
            entitlements__capability__code='core.enabled',
            entitlements__capability__is_active=True,
            entitlements__enabled=True,
        ).filter(
            Q(entitlements__capability__code='users.max')
            & Q(entitlements__capability__is_active=True)
            & Q(entitlements__enabled=True)
            & (Q(entitlements__unlimited=True) | Q(entitlements__limit_value__gte=1))
        ).filter(
            Q(entitlements__capability__code='branches.max')
            & Q(entitlements__capability__is_active=True)
            & Q(entitlements__enabled=True)
            & (Q(entitlements__unlimited=True) | Q(entitlements__limit_value__gte=1))
        ).filter(
            entitlements__capability__code='pos.enabled',
            entitlements__capability__is_active=True,
        ).filter(
            entitlements__capability__code='pos.devices.max',
            entitlements__capability__is_active=True,
        ).select_related('plan').prefetch_related(
            'entitlements__capability'
        ).distinct().order_by('plan__name', '-version')
        return Response(PublicPlanVersionSerializer(versions, many=True).data)


class PublicSettingsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        instance = GlobalSaaSSettings.objects.first() or GlobalSaaSSettings()
        return Response(PublicBrandingSerializer(instance, context={'request': request}).data)


class PublicBrandingAssetView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slot):
        field = BRANDING_ASSET_FIELDS.get(slot)
        instance = GlobalSaaSSettings.objects.first()
        if not field or not instance:
            raise Http404
        asset = getattr(instance, field)
        if not asset or not asset.storage.exists(asset.name):
            raise Http404
        content_type = mimetypes.guess_type(asset.name)[0] or 'application/octet-stream'
        return FileResponse(asset.open('rb'), content_type=content_type)


def _notify_commercial_lead(lead):
    if not settings.SALES_LEAD_EMAIL:
        return
    fields = (
        ('Nome', lead.name), ('Empresa', lead.company_name), ('WhatsApp', lead.whatsapp),
        ('E-mail', lead.email), ('Segmento', lead.segment), ('Mensagem', lead.message or '-'),
        ('Página de origem', lead.source_path or '-'), ('Plano de interesse', lead.plan_interest or '-'),
        ('UTM source', lead.utm_source or '-'), ('UTM medium', lead.utm_medium or '-'),
        ('UTM campaign', lead.utm_campaign or '-'), ('Recebido em', lead.created_at.isoformat()),
    )
    send_mail(
        subject=f'Novo lead comercial CORE: {lead.name}',
        message='\n'.join(f'{label}: {value}' for label, value in fields),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.SALES_LEAD_EMAIL],
        fail_silently=False,
    )


@method_decorator(csrf_protect, name='dispatch')
class PublicCommercialLeadView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'commercial_lead'

    def post(self, request):
        serializer = CommercialLeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save()
        try:
            _notify_commercial_lead(lead)
        except Exception:
            logger.exception('Commercial lead notification failed for lead_id=%s.', lead.pk)
        return Response(
            {'id': lead.pk, 'detail': 'Recebemos seu contato. Nossa equipe falará com você.'},
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name='dispatch')
class PlatformLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = PlatformLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].lower()
        password = serializer.validated_data['password']
        authenticated = authenticate(request=request, email=email, password=password)
        if authenticated is None:
            if getattr(request, 'axes_locked_out', False):
                return Response(
                    {'detail': axes_lockout_message()},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            return Response(
                {'detail': INVALID_LOGIN_MESSAGE},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if (
            not authenticated.can_login
            or not hasattr(authenticated, 'platform_access')
            or not authenticated.platform_access.is_active
            or not user_has_platform_permission(authenticated, 'platform.access')
        ):
            return Response(
                {'detail': INVALID_LOGIN_MESSAGE},
                status=status.HTTP_403_FORBIDDEN,
            )
        login(request, authenticated)
        audit_log(
            actor=authenticated,
            action='platform.auth.login',
            obj=authenticated,
        )
        response = Response(PlatformUserSerializer(authenticated).data)
        response['X-CSRFToken'] = get_token(request)
        return response


class PlatformMeView(APIView):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.access'

    def get(self, request):
        return Response(PlatformUserSerializer(request.user).data)


class PlatformOwnerLookupView(APIView):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.tenants.manage'

    def get(self, request):
        email = (request.query_params.get('email') or '').strip().lower()
        if not email:
            raise ValidationError({'email': 'Informe o e-mail do Owner.'})
        user = User.objects.filter(email__iexact=email).only(
            'id', 'email', 'is_active', 'can_login'
        ).first()
        return Response({
            'email': email,
            'exists': user is not None,
            'eligible': bool(user and user.is_active and user.can_login),
        })


class PlatformLogoutView(APIView):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.access'

    def post(self, request):
        user = request.user
        logout(request)
        audit_log(actor=user, action='platform.auth.logout', obj=user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name='dispatch')
class PublicSignupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'signup'

    def post(self, request):
        settings_instance = GlobalSaaSSettings.objects.first()
        if not settings_instance or not settings_instance.public_signup_enabled:
            return Response(
                {
                    'code': 'public_signup_disabled',
                    'detail': 'O cadastro público está indisponível. Solicite uma demonstração comercial.',
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ProvisioningSerializer(
            data=request.data,
            context={'source': ProvisioningOperation.Source.PUBLIC_SIGNUP},
        )
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except OwnerEmailAlreadyExists:
            pass
        reference = hashlib.sha256(
            f"public-signup:{serializer.validated_data['idempotency_key']}".encode()
        ).hexdigest()[:12]
        return Response(
            {
                'id': reference,
                'detail': 'Cadastro recebido. Use suas credenciais para acessar quando disponível.',
            },
            status=status.HTTP_201_CREATED,
        )


class PlatformDashboardView(APIView):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.dashboard.view'

    def get(self, request):
        companies = Company.objects.all()
        subscriptions = Subscription.objects.filter(is_current=True).select_related('company', 'plan_version')
        effective_statuses = [resolve_effective_status(company)['status'] for company in companies]
        paid = subscriptions.filter(billing_mode=Subscription.BillingMode.PAID)
        mrr_subscriptions = paid.filter(status__in=(
            Subscription.Status.ACTIVE,
            Subscription.Status.TRIALING,
            Subscription.Status.PAST_DUE,
            Subscription.Status.RESTRICTED,
        ))
        mrr = sum(
            (item.plan_version.price / item.plan_version.billing_period_months for item in mrr_subscriptions),
            Decimal('0'),
        )
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return Response({
            'total_tenants': len(effective_statuses),
            'active_tenants': sum(status_value in (Subscription.Status.ACTIVE, Subscription.Status.TRIALING) for status_value in effective_statuses),
            'paying_customers': paid.count(),
            'free': subscriptions.filter(billing_mode=Subscription.BillingMode.FREE).count(),
            'internal': subscriptions.filter(billing_mode=Subscription.BillingMode.INTERNAL).count(),
            'active_trials': effective_statuses.count(Subscription.Status.TRIALING),
            'expired_trials': effective_statuses.count(Subscription.Status.TRIAL_EXPIRED),
            'past_due': sum(value in (Subscription.Status.PAST_DUE, Subscription.Status.RESTRICTED, Subscription.Status.SUSPENDED_FINANCIAL) for value in effective_statuses),
            'suspended_tenants': sum(value in ('SUSPENDED_ADMIN', Subscription.Status.SUSPENDED_FINANCIAL) for value in effective_statuses),
            'contracted_mrr': str(mrr),
            'new_tenants': companies.filter(created_at__gte=month_start).count(),
            'scheduled_cancellations': subscriptions.filter(cancel_at_period_end=True).count(),
        })


class PlatformTenantViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Company.objects.all().prefetch_related('branches', 'user_accesses__user')
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.tenants.manage'

    def get_permissions(self):
        self.required_platform_permission = (
            'platform.billing.manage'
            if self.action in ('financial_suspend', 'process_lifecycle', 'map_subscription')
            else 'platform.tenants.manage'
        )
        return super().get_permissions()

    def list(self, request):
        queryset = self.get_queryset()
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(trade_name__icontains=search) | Q(legal_name__icontains=search) | Q(cnpj__icontains=search)
            )
        data = [self._summary(company) for company in queryset.order_by('trade_name', 'pk')]
        return Response(data)

    def retrieve(self, request, pk=None):
        company = self.get_object()
        subscription = current_subscription(company)
        owner = company.user_accesses.filter(is_owner=True).select_related('user').first()
        state = TenantSaaSState.objects.filter(company=company).first()
        data = {
            **self._summary(company),
            'legal_name': company.legal_name,
            'cnpj': company.cnpj,
            'email': company.email,
            'phone': company.phone,
            'owner': ({'user_id': owner.user_id, 'email': owner.user.email} if owner else None),
            'saas_state': TenantSaaSStateSerializer(state).data if state else None,
            'branches': list(company.branches.values('id', 'name', 'status', 'is_matrix')),
            'users': list(company.user_accesses.values('user_id', 'user__email', 'is_active', 'is_owner', 'saas_status')),
        }
        if user_has_platform_permission(request.user, 'platform.billing.manage'):
            data['subscription'] = SubscriptionSerializer(subscription).data if subscription else None
            data['payments'] = BillingRecordSerializer(
                BillingRecord.objects.filter(subscription=subscription), many=True
            ).data if subscription else []
        if user_has_platform_permission(request.user, 'platform.support.manage'):
            data['support_sessions'] = SupportSessionSerializer(
                company.support_sessions.all(), many=True
            ).data
        return Response(data)

    def create(self, request):
        _critical_action(request)
        serializer = ProvisioningSerializer(
            data=_without_critical_fields(request.data),
            context={
                'source': ProvisioningOperation.Source.PLATFORM_MANUAL,
                'actor': request.user,
            },
        )
        serializer.is_valid(raise_exception=True)
        operation = serializer.save()
        return Response(ProvisioningResultSerializer(operation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        reason = _critical_action(request)
        state, _ = approve_tenant(self.get_object(), request.user, reason)
        return Response(TenantSaaSStateSerializer(state).data)

    @action(detail=True, methods=['post'], url_path='admin-suspend')
    def admin_suspend(self, request, pk=None):
        reason = _critical_action(request)
        state = set_admin_suspension(
            self.get_object(), request.user, reason, True
        )
        return Response(TenantSaaSStateSerializer(state).data)

    @action(detail=True, methods=['post'], url_path='admin-resume')
    def admin_resume(self, request, pk=None):
        reason = _critical_action(request)
        state = set_admin_suspension(
            self.get_object(), request.user, reason, False
        )
        return Response(TenantSaaSStateSerializer(state).data)

    @action(detail=True, methods=['post'], url_path='financial-suspend')
    def financial_suspend(self, request, pk=None):
        reason = _critical_action(request)
        subscription = current_subscription(self.get_object())
        if not subscription:
            raise ValidationError({'subscription': 'Empresa sem assinatura corrente.'})
        subscription = set_financial_suspension(subscription, request.user, reason, True)
        return Response(SubscriptionSerializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='process-lifecycle')
    def process_lifecycle(self, request, pk=None):
        _critical_action(request)
        subscription = current_subscription(self.get_object())
        if not subscription:
            raise ValidationError({'subscription': 'Empresa sem assinatura corrente.'})
        subscription, _ = process_subscription_lifecycle(subscription)
        return Response(SubscriptionSerializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='map-subscription')
    def map_subscription(self, request, pk=None):
        reason = _critical_action(request)
        serializer = MapSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription, _ = map_existing_company(
            company=self.get_object(),
            plan_version=serializer.validated_data['plan_version'],
            billing_mode=serializer.validated_data['billing_mode'],
            actor=request.user,
            initial_subscription_mode=serializer.validated_data['initial_subscription_mode'],
        )
        audit_log(
            actor=request.user, action='saas.company.map.authorize', obj=subscription,
            company=subscription.company, metadata={'reason': reason},
        )
        return Response(SubscriptionSerializer(subscription).data)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        reason = _critical_action(request)
        state, _ = archive_tenant(self.get_object(), request.user, reason)
        return Response(TenantSaaSStateSerializer(state).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        reason = _critical_action(request)
        state = reject_tenant(self.get_object(), request.user, reason)
        return Response(TenantSaaSStateSerializer(state).data)

    @action(detail=True, methods=['post'], url_path='transfer-owner')
    def transfer_owner(self, request, pk=None):
        reason = _critical_action(request)
        transfer_company_owner(
            company=self.get_object(), actor=request.user,
            target_user_id=request.data.get('target_user_id'),
            current_password=request.data.get('current_password'),
            reason=reason, platform_authorized=True,
        )
        return self.retrieve(request, pk=pk)

    @staticmethod
    def _summary(company):
        effective = resolve_effective_status(company)
        return {
            'id': company.pk,
            'trade_name': company.trade_name,
            'operational_status': company.status,
            'effective_status': effective['status'],
            'can_operate': effective['can_operate'],
        }


class PlatformCommercialLeadViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CommercialLead.objects.all()
    serializer_class = PlatformCommercialLeadSerializer
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.leads.manage'

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search', '').strip()
        status_value = self.request.query_params.get('status', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(company_name__icontains=search)
                | Q(email__icontains=search)
                | Q(whatsapp__icontains=search)
            )
        if status_value:
            if status_value not in CommercialLead.Status.values:
                raise ValidationError({'status': 'Informe um status de lead valido.'})
            queryset = queryset.filter(status=status_value)
        return queryset

    @action(detail=True, methods=['post'])
    def status(self, request, pk=None):
        lead = self.get_object()
        serializer = CommercialLeadStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_status = lead.status
        lead.status = serializer.validated_data['status']
        if lead.status == previous_status:
            return Response(self.get_serializer(lead).data)
        lead.save(update_fields=('status', 'updated_at'))
        audit_log(
            actor=request.user,
            action='saas.commercial_lead.status_change',
            obj=lead,
            before={'status': previous_status},
            after={'status': lead.status},
        )
        return Response(self.get_serializer(lead).data)


class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.prefetch_related('versions__entitlements__capability')
    serializer_class = PlanSerializer
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.plans.manage'
    http_method_names = ('get', 'post', 'put', 'patch', 'head', 'options')

    def create(self, request):
        reason = _critical_action(request)
        serializer = self.get_serializer(data=_without_critical_fields(request.data))
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        audit_log(actor=request.user, action='saas.plan.create', obj=plan, metadata={'reason': reason})
        return Response(self.get_serializer(plan).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        reason = _critical_action(request)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=_without_critical_fields(request.data),
            partial=kwargs.get('partial', False),
        )
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        audit_log(actor=request.user, action='saas.plan.update', obj=plan, metadata={'reason': reason})
        return Response(self.get_serializer(plan).data)


class PlanVersionViewSet(viewsets.ModelViewSet):
    queryset = PlanVersion.objects.select_related('plan').prefetch_related('entitlements__capability')
    serializer_class = PlanVersionSerializer
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.plans.manage'
    http_method_names = ('get', 'post', 'put', 'patch', 'head', 'options')

    def create(self, request):
        reason = _critical_action(request)
        serializer = self.get_serializer(data=_without_critical_fields(request.data))
        serializer.is_valid(raise_exception=True)
        version = serializer.save()
        audit_log(actor=request.user, action='saas.plan_version.create', obj=version, metadata={'reason': reason})
        return Response(self.get_serializer(version).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        reason = _critical_action(request)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=_without_critical_fields(request.data),
            partial=kwargs.get('partial', False),
        )
        serializer.is_valid(raise_exception=True)
        version = serializer.save()
        audit_log(actor=request.user, action='saas.plan_version.update', obj=version, metadata={'reason': reason})
        return Response(self.get_serializer(version).data)


class CapabilityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Capability.objects.filter(is_active=True)
    serializer_class = CapabilitySerializer
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.plans.manage'


class PlanEntitlementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PlanEntitlement.objects.select_related('plan_version', 'capability')
    serializer_class = PlanEntitlementSerializer
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.plans.manage'


class PlatformPaymentViewSet(viewsets.GenericViewSet):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.billing.manage'
    queryset = BillingRecord.objects.select_related('subscription__company', 'actor')

    def list(self, request):
        queryset = self.get_queryset()
        company_id = request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(subscription__company_id=company_id)
        return Response(BillingRecordSerializer(queryset, many=True).data)

    def create(self, request):
        reason = _critical_action(request)
        serializer = ManualPaymentSerializer(
            data=_without_critical_fields(request.data), context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        record = serializer.save()
        audit_log(
            actor=request.user, action='saas.payment.authorize', obj=record,
            company=record.subscription.company, metadata={'reason': reason},
        )
        return Response(BillingRecordSerializer(record).data, status=status.HTTP_201_CREATED)


class PlatformSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.billing.manage'
    serializer_class = SubscriptionSerializer
    queryset = Subscription.objects.select_related('company', 'plan_version__plan')

    def get_queryset(self):
        queryset = super().get_queryset()
        company_id = self.request.query_params.get('company')
        return queryset.filter(company_id=company_id) if company_id else queryset

    @action(detail=True, methods=['post'], url_path='billing-mode')
    def billing_mode(self, request, pk=None):
        reason = _critical_action(request)
        subscription = set_subscription_billing_mode(
            self.get_object(), request.user, request.data.get('billing_mode'), reason
        )
        return Response(self.get_serializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='financial-suspend')
    def financial_suspend(self, request, pk=None):
        reason = _critical_action(request)
        subscription = set_financial_suspension(self.get_object(), request.user, reason, True)
        return Response(self.get_serializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='financial-resume')
    def financial_resume(self, request, pk=None):
        reason = _critical_action(request)
        subscription = set_financial_suspension(self.get_object(), request.user, reason, False)
        return Response(self.get_serializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='extend-trial')
    def extend_trial(self, request, pk=None):
        reason = _critical_action(request)
        try:
            days = int(request.data.get('days'))
        except (TypeError, ValueError) as error:
            raise ValidationError({'days': 'Informe uma quantidade valida.'}) from error
        subscription = extend_subscription_trial(
            self.get_object(), request.user, days, reason
        )
        return Response(self.get_serializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='end-trial')
    def end_trial(self, request, pk=None):
        reason = _critical_action(request)
        subscription = end_subscription_trial(self.get_object(), request.user, reason)
        return Response(self.get_serializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='process-lifecycle')
    def process_lifecycle(self, request, pk=None):
        _critical_action(request)
        subscription, _ = process_subscription_lifecycle(self.get_object())
        return Response(self.get_serializer(subscription).data)


class PlatformSettingsView(APIView):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.settings.manage'

    def get(self, request):
        return Response(GlobalSaaSSettingsSerializer(
            get_global_settings(), context={'request': request}
        ).data)

    def patch(self, request):
        reason = _critical_action(request)
        instance = get_global_settings()
        serializer = GlobalSaaSSettingsSerializer(
            instance, data=_without_critical_fields(request.data), partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit_log(
            actor=request.user, action='saas.settings.update', obj=instance,
            metadata={'reason': reason},
        )
        return Response(GlobalSaaSSettingsSerializer(
            instance, context={'request': request}
        ).data)

    def post(self, request):
        reason = _critical_action(request)
        instance, _ = enable_saas_enforcement(request.user, reason=reason)
        return Response(GlobalSaaSSettingsSerializer(
            instance, context={'request': request}
        ).data)


class PlatformBrandingAssetView(APIView):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.settings.manage'

    @transaction.atomic
    def post(self, request, slot):
        field = BRANDING_ASSET_FIELDS.get(slot)
        if not field:
            raise Http404
        reason = _critical_action(request)
        upload = request.FILES.get('asset')
        if upload is None:
            raise ValidationError({'asset': 'Selecione um arquivo para enviar.'})
        instance = get_global_settings()
        previous = getattr(instance, field)
        previous_name = previous.name if previous else ''
        previous_storage = previous.storage if previous_name else None
        setattr(instance, field, upload)
        instance.save(update_fields=(field, 'updated_at'))
        if previous_name and previous_name != getattr(instance, field).name:
            transaction.on_commit(lambda: previous_storage.delete(previous_name))
        audit_log(
            actor=request.user, action='saas.branding_asset.upload', obj=instance,
            before={slot: bool(previous_name)}, after={slot: True},
            metadata={'reason': reason},
        )
        return Response(GlobalSaaSSettingsSerializer(instance, context={'request': request}).data)

    @transaction.atomic
    def delete(self, request, slot):
        field = BRANDING_ASSET_FIELDS.get(slot)
        if not field:
            raise Http404
        reason = _critical_action(request)
        instance = get_global_settings()
        asset = getattr(instance, field)
        if not asset:
            return Response(status=status.HTTP_204_NO_CONTENT)
        name = asset.name
        storage = asset.storage
        setattr(instance, field, None)
        instance.save(update_fields=(field, 'updated_at'))
        transaction.on_commit(lambda: storage.delete(name))
        audit_log(
            actor=request.user, action='saas.branding_asset.remove', obj=instance,
            before={slot: True}, after={slot: False}, metadata={'reason': reason},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlatformSupportSessionViewSet(viewsets.GenericViewSet):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.support.manage'
    queryset = SupportSession.objects.select_related('actor', 'company', 'impersonated_user')

    def list(self, request):
        queryset = self.get_queryset()
        company_id = request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        return Response(SupportSessionSerializer(queryset, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(SupportSessionSerializer(self.get_object()).data)

    def create(self, request):
        serializer = SupportSessionCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        return Response(SupportSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        session = self.get_object()
        if session.actor_id != request.user.pk:
            raise ValidationError({'session': 'Somente o ator pode encerrar esta sessao.'})
        session, _ = end_support_session(session, request.user)
        return Response(SupportSessionSerializer(session).data)


class PlatformSubscriptionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasPlatformPermission]
    required_platform_permission = 'platform.billing.manage'
    serializer_class = SubscriptionRequestSerializer
    queryset = SubscriptionRequest.objects.select_related(
        'subscription__company', 'requested_plan_version', 'requested_by', 'resolved_by'
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        company_id = self.request.query_params.get('company')
        return queryset.filter(subscription__company_id=company_id) if company_id else queryset

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        reason = _critical_action(request)
        row, _ = resolve_subscription_request(
            self.get_object(), request.user, True, reason=reason
        )
        return Response(self.get_serializer(row).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        reason = _critical_action(request)
        row, _ = resolve_subscription_request(
            self.get_object(), request.user, False, reason=reason
        )
        return Response(self.get_serializer(row).data)


def _owner_subscription(company):
    subscription = current_subscription(company)
    if not subscription:
        raise ValidationError({'subscription': 'Empresa sem assinatura corrente.'})
    return subscription


class OwnerSubscriptionView(APIView):
    permission_classes = [IsCompanyOwner]

    def get(self, request):
        company = Company.objects.get(pk=request.query_params['company'])
        subscription = _owner_subscription(company)
        usage = [
            {
                'capability_code': code,
                'period_start': subscription.current_period_start,
                'period_end': subscription.current_period_end,
                'quantity': resource_usage(company, code),
            }
            for code in ('users.max', 'branches.max')
        ]
        return Response({
            'subscription': SubscriptionSerializer(subscription).data,
            'effective_status': resolve_effective_status(company)['status'],
            'entitlements': PlanEntitlementSerializer(
                subscription.plan_version.entitlements.select_related('capability'), many=True
            ).data,
            'usage': usage,
        })


class OwnerPaymentHistoryView(APIView):
    permission_classes = [IsCompanyOwner]

    def get(self, request):
        company = Company.objects.get(pk=request.query_params['company'])
        records = BillingRecord.objects.filter(subscription__company=company).select_related('actor')
        return Response(BillingRecordSerializer(records, many=True).data)


class OwnerChangeRequestView(APIView):
    permission_classes = [IsCompanyOwner]

    def get(self, request):
        company = Company.objects.get(pk=request.query_params['company'])
        rows = SubscriptionRequest.objects.filter(subscription__company=company)
        return Response(SubscriptionRequestSerializer(rows, many=True).data)

    def post(self, request):
        serializer = PlanChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data['current_password']):
            raise ValidationError({'current_password': 'Senha atual invalida.'})
        company = serializer.validated_data['company']
        row = request_plan_change(
            _owner_subscription(company), request.user,
            serializer.validated_data['requested_plan_version'],
            serializer.validated_data['reason'],
        )
        return Response(SubscriptionRequestSerializer(row).data, status=status.HTTP_201_CREATED)


class OwnerCancellationView(APIView):
    permission_classes = [IsCompanyOwner]

    def post(self, request):
        serializer = CancellationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data['current_password']):
            raise ValidationError({'current_password': 'Senha atual invalida.'})
        company = serializer.validated_data['company']
        row = request_cancellation(
            _owner_subscription(company), request.user, serializer.validated_data['reason']
        )
        return Response(SubscriptionRequestSerializer(row).data, status=status.HTTP_201_CREATED)


class OwnerSupportHistoryView(APIView):
    permission_classes = [IsCompanyOwner]

    def get(self, request):
        company = Company.objects.get(pk=request.query_params['company'])
        return Response(SupportSessionSerializer(company.support_sessions.all(), many=True).data)
