from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from decimal import Decimal
from rest_framework import serializers

from apps.accounts.models import User
from apps.companies.models import Company

from .models import (
    BillingRecord,
    Capability,
    CycleUsage,
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
from .services import (
    create_support_session,
    provision_saas_tenant,
    record_manual_payment,
)


class PlatformLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class PlatformUserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source='platform_access.role.code', read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'role', 'permissions')

    def get_permissions(self, user):
        return list(user.platform_access.role.permissions.order_by('code').values_list('code', flat=True))


class CapabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Capability
        fields = ('id', 'code', 'name', 'value_type', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'code', 'value_type', 'created_at', 'updated_at')


class PlanEntitlementSerializer(serializers.ModelSerializer):
    capability_code = serializers.CharField(source='capability.code', read_only=True)

    class Meta:
        model = PlanEntitlement
        fields = (
            'id', 'plan_version', 'capability', 'capability_code', 'enabled',
            'unlimited', 'limit_value', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'capability_code', 'created_at', 'updated_at')


class PlanVersionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    entitlements = PlanEntitlementSerializer(many=True, read_only=True)
    is_used = serializers.BooleanField(read_only=True)

    class Meta:
        model = PlanVersion
        fields = (
            'id', 'plan', 'plan_name', 'version', 'price', 'currency',
            'billing_period_months', 'trial_days', 'is_public', 'is_active',
            'is_used', 'entitlements', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'plan_name', 'is_used', 'entitlements', 'created_at', 'updated_at')


class PublicPlanVersionSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source='plan.code', read_only=True)
    name = serializers.CharField(source='plan.name', read_only=True)
    description = serializers.CharField(source='plan.description', read_only=True)
    limits = serializers.SerializerMethodField()

    class Meta:
        model = PlanVersion
        fields = (
            'id', 'code', 'name', 'description', 'version', 'price', 'currency',
            'billing_period_months', 'trial_days', 'limits',
        )
        read_only_fields = fields

    def get_limits(self, version):
        entitlements = {
            item.capability.code: item
            for item in version.entitlements.all()
        }
        return {
            name: {
                'unlimited': entitlements[code].unlimited,
                'value': None if entitlements[code].unlimited else entitlements[code].limit_value,
            }
            for name, code in (('users', 'users.max'), ('branches', 'branches.max'))
        }


class PlanSerializer(serializers.ModelSerializer):
    versions = PlanVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Plan
        fields = ('id', 'code', 'name', 'description', 'is_active', 'versions', 'created_at', 'updated_at')
        read_only_fields = ('id', 'versions', 'created_at', 'updated_at')


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan_version.plan.name', read_only=True)
    plan_version_number = serializers.IntegerField(source='plan_version.version', read_only=True)

    class Meta:
        model = Subscription
        fields = (
            'id', 'company', 'plan_version', 'plan_name', 'plan_version_number',
            'billing_mode', 'status', 'is_current', 'current_period_start',
            'current_period_end', 'trial_started_at', 'trial_ends_at',
            'cancel_at_period_end', 'cancellation_reason', 'cancelled_at',
            'created_at', 'updated_at',
        )
        read_only_fields = fields


class TenantSaaSStateSerializer(serializers.ModelSerializer):
    is_admin_suspended = serializers.BooleanField(read_only=True)

    class Meta:
        model = TenantSaaSState
        fields = (
            'approval_status', 'approval_reason', 'approved_at', 'approved_by',
            'is_admin_suspended', 'admin_suspended_at', 'admin_suspended_by',
            'admin_suspension_reason', 'archived_at', 'archived_by',
            'archive_reason', 'updated_at',
        )
        read_only_fields = fields


class CycleUsageSerializer(serializers.ModelSerializer):
    capability_code = serializers.CharField(source='capability.code', read_only=True)

    class Meta:
        model = CycleUsage
        fields = ('id', 'capability_code', 'period_start', 'period_end', 'quantity', 'updated_at')


class BillingRecordSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = BillingRecord
        fields = (
            'id', 'subscription', 'amount', 'paid_at', 'payment_method', 'note',
            'competency_start', 'competency_end', 'actor', 'actor_email',
            'proof_reference', 'idempotency_key', 'created_at',
        )
        read_only_fields = fields


class ManualPaymentSerializer(serializers.Serializer):
    subscription = serializers.PrimaryKeyRelatedField(queryset=Subscription.objects.filter(is_current=True))
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    paid_at = serializers.DateTimeField()
    payment_method = serializers.CharField(max_length=50)
    note = serializers.CharField(required=False, allow_blank=True)
    proof_reference = serializers.CharField(required=False, allow_blank=True, max_length=500)
    competency_start = serializers.DateTimeField(required=False)
    competency_end = serializers.DateTimeField(required=False)
    idempotency_key = serializers.CharField(max_length=100)

    def validate(self, attrs):
        if ('competency_start' in attrs) != ('competency_end' in attrs):
            raise serializers.ValidationError({
                'competency_start': 'Informe inicio e fim da competencia juntos ou omita ambos.'
            })
        return attrs

    def create(self, validated_data):
        record, _ = record_manual_payment(actor=self.context['request'].user, **validated_data)
        return record


class ProvisioningSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=100)
    plan_version = serializers.PrimaryKeyRelatedField(queryset=PlanVersion.objects.select_related('plan'))
    trade_name = serializers.CharField(max_length=150)
    legal_name = serializers.CharField(max_length=200)
    cnpj = serializers.CharField(max_length=18, required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    owner_email = serializers.EmailField(required=False)
    owner_password = serializers.CharField(required=False, write_only=True, trim_whitespace=False)
    owner_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)
    billing_mode = serializers.ChoiceField(choices=Subscription.BillingMode.choices, required=False)

    def validate(self, attrs):
        source = self.context['source']
        if source == ProvisioningOperation.Source.PUBLIC_SIGNUP:
            if attrs.get('owner_user'):
                raise serializers.ValidationError({'owner_user': 'O autoatendimento nao aceita usuario existente.'})
            if not attrs.get('owner_email') or not attrs.get('owner_password'):
                raise serializers.ValidationError({'owner_email': 'Informe e-mail e senha do Owner.'})
            if 'billing_mode' in attrs:
                raise serializers.ValidationError({'billing_mode': 'O billing mode publico e definido pela plataforma.'})
        elif 'billing_mode' not in attrs:
            raise serializers.ValidationError({'billing_mode': 'Informe PAID, FREE ou INTERNAL.'})
        if not attrs.get('owner_user'):
            if not attrs.get('owner_email') or not attrs.get('owner_password'):
                raise serializers.ValidationError({
                    'owner_user': 'Informe um usuario existente ou as credenciais da nova conta.'
                })
            try:
                validate_password(attrs['owner_password'], user=User(email=attrs['owner_email']))
            except DjangoValidationError as error:
                raise serializers.ValidationError({'owner_password': list(error.messages)}) from error
        return attrs

    def create(self, validated_data):
        company_fields = ('trade_name', 'legal_name', 'cnpj', 'email', 'phone')
        company_data = {
            field: validated_data.pop(field)
            for field in company_fields
            if field in validated_data
        }
        operation, _ = provision_saas_tenant(
            source=self.context['source'],
            company_data=company_data,
            actor=self.context.get('actor'),
            **validated_data,
        )
        return operation


class ProvisioningResultSerializer(serializers.ModelSerializer):
    owner_user_id = serializers.IntegerField(source='user_id', read_only=True)
    approval_status = serializers.CharField(source='company.saas_state.approval_status', read_only=True)

    class Meta:
        model = ProvisioningOperation
        fields = ('id', 'source', 'company', 'subscription', 'owner_user_id', 'approval_status', 'created_at')


class GlobalSaaSSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSaaSSettings
        exclude = ('singleton',)
        read_only_fields = (
            'id', 'enforcement_enabled', 'enforcement_enabled_at',
            'enforcement_enabled_by', 'created_at', 'updated_at',
        )


class PublicBrandingSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSaaSSettings
        fields = (
            'platform_name', 'logo_url', 'compact_logo_url', 'favicon_url',
            'logo_light_url', 'logo_dark_url', 'compact_logo_light_url',
            'compact_logo_dark_url',
            'primary_color', 'support_email', 'support_phone', 'institutional_links',
        )
        read_only_fields = fields


class SupportSessionSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = SupportSession
        fields = (
            'id', 'actor', 'actor_email', 'company', 'impersonated_user', 'mode',
            'reason', 'expires_at', 'ended_at', 'ended_by', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class SupportSessionCreateSerializer(serializers.Serializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    impersonated_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=SupportSession.Mode.choices)
    reason = serializers.CharField()
    current_password = serializers.CharField(required=False, write_only=True, trim_whitespace=False)
    expires_at = serializers.DateTimeField(required=False)

    def create(self, validated_data):
        return create_support_session(actor=self.context['request'].user, **validated_data)


class SubscriptionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionRequest
        fields = (
            'id', 'subscription', 'request_type', 'requested_plan_version', 'reason',
            'status', 'requested_by', 'resolved_by', 'resolved_at', 'created_at',
        )
        read_only_fields = fields


class PlanChangeRequestSerializer(serializers.Serializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    requested_plan_version = serializers.PrimaryKeyRelatedField(
        queryset=PlanVersion.objects.filter(is_active=True, plan__is_active=True)
    )
    reason = serializers.CharField()
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)


class CancellationRequestSerializer(serializers.Serializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    reason = serializers.CharField()
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
