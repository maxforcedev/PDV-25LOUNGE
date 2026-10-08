from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from decimal import Decimal
from django.utils.text import slugify
from rest_framework import serializers

from apps.accounts.models import User
from apps.companies.models import Company

from .models import (
    BillingRecord,
    Capability,
    CommercialLead,
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
    CAPABILITY_DEPENDENCIES,
    create_support_session,
    provision_saas_tenant,
    record_manual_payment,
    validate_entitlement_dependencies,
)

BRANDING_ASSET_FIELDS = {
    'logo': 'logo_file',
    'compact_logo': 'compact_logo_file',
    'favicon': 'favicon_file',
    'logo_light': 'logo_light_file',
    'logo_dark': 'logo_dark_file',
    'compact_logo_light': 'compact_logo_light_file',
    'compact_logo_dark': 'compact_logo_dark_file',
}

DEFAULT_BRANDING_ASSETS = {
    'logo': 'core-logo-light.png',
    'compact_logo': 'core-logo-compact-light.png',
    'favicon': 'core-favicon.png',
    'logo_light': 'core-logo-light.png',
    'logo_dark': 'core-logo-dark.png',
    'compact_logo_light': 'core-logo-compact-light.png',
    'compact_logo_dark': 'core-logo-compact-dark.png',
}


def branding_asset_url(instance, slot, request=None):
    asset = getattr(instance, BRANDING_ASSET_FIELDS[slot])
    if not asset:
        return ''
    path = f'/api/v1/public/branding/{slot}/'
    return request.build_absolute_uri(path) if request else path


def resolved_branding_asset_url(instance, slot, request=None):
    candidates = (slot,) if slot == 'favicon' else (
        slot,
        'compact_logo' if slot.startswith('compact_') else 'logo',
    )
    for candidate in candidates:
        url = branding_asset_url(instance, candidate, request)
        if url:
            return url
    return f'{settings.FRONTEND_URL.rstrip("/")}/branding/{DEFAULT_BRANDING_ASSETS[slot]}'


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
    dependencies = serializers.SerializerMethodField()

    class Meta:
        model = Capability
        fields = (
            'id', 'code', 'name', 'value_type', 'is_active', 'dependencies',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'code', 'value_type', 'created_at', 'updated_at')

    def get_dependencies(self, capability):
        return list(CAPABILITY_DEPENDENCIES.get(capability.code, ()))


class PlanEntitlementSerializer(serializers.ModelSerializer):
    capability_code = serializers.CharField(source='capability.code', read_only=True)

    class Meta:
        model = PlanEntitlement
        fields = (
            'id', 'plan_version', 'capability', 'capability_code', 'enabled',
            'unlimited', 'limit_value', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'capability_code', 'created_at', 'updated_at')

    def validate(self, attrs):
        plan_version = attrs.get('plan_version', getattr(self.instance, 'plan_version', None))
        capability = attrs.get('capability', getattr(self.instance, 'capability', None))
        if not plan_version or not capability:
            return attrs

        try:
            versions = {plan_version.pk: plan_version}
            if self.instance:
                versions[self.instance.plan_version_id] = self.instance.plan_version
            for version in versions.values():
                enabled_capabilities = {
                    item.capability.code: item.enabled
                    for item in version.entitlements.select_related('capability')
                }
                if self.instance and version.pk == self.instance.plan_version_id:
                    enabled_capabilities.pop(self.instance.capability.code, None)
                if version.pk == plan_version.pk:
                    enabled_capabilities[capability.code] = attrs.get(
                        'enabled', getattr(self.instance, 'enabled', False)
                    )
                validate_entitlement_dependencies(enabled_capabilities)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        return attrs


class PlanVersionEntitlementInputSerializer(serializers.Serializer):
    capability = serializers.PrimaryKeyRelatedField(
        queryset=Capability.objects.filter(is_active=True)
    )
    enabled = serializers.BooleanField(default=False)
    unlimited = serializers.BooleanField(default=False)
    limit_value = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class PlanVersionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    entitlements = PlanVersionEntitlementInputSerializer(many=True, write_only=True)
    is_used = serializers.BooleanField(read_only=True)

    class Meta:
        model = PlanVersion
        fields = (
            'id', 'plan', 'plan_name', 'version', 'price', 'currency',
            'billing_period_months', 'trial_days', 'is_public', 'is_active',
            'is_used', 'entitlements', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'plan_name', 'is_used', 'created_at', 'updated_at')

    def validate(self, attrs):
        entitlements = attrs.get('entitlements')
        if entitlements is None:
            raise serializers.ValidationError({'entitlements': 'Informe todas as capabilities da versao.'})

        available = {
            capability.pk: capability
            for capability in Capability.objects.filter(is_active=True)
        }
        received_ids = [item['capability'].pk for item in entitlements]
        if len(received_ids) != len(set(received_ids)):
            raise serializers.ValidationError({'entitlements': 'Cada capability pode aparecer apenas uma vez.'})

        core = next((item for item in available.values() if item.code == 'core.enabled'), None)
        if core is None:
            raise serializers.ValidationError({'entitlements': 'A capability obrigatoria core.enabled nao esta disponivel.'})

        expected_ids = set(available) - {core.pk}
        if set(received_ids) - {core.pk} != expected_ids:
            raise serializers.ValidationError({'entitlements': 'Informe todas as capabilities ativas da plataforma.'})

        normalized = []
        for item in entitlements:
            capability = item['capability']
            enabled = item.get('enabled', False)
            unlimited = item.get('unlimited', False) if enabled else False
            limit_value = item.get('limit_value') if enabled and not unlimited else None

            if capability.value_type == Capability.ValueType.BOOLEAN:
                unlimited = enabled
                limit_value = None
            elif enabled and not unlimited and limit_value is None:
                raise serializers.ValidationError({
                    'entitlements': f'Informe um limite ou marque ilimitado para {capability.code}.'
                })
            if capability.code in ('users.max', 'branches.max') and (
                not enabled or (not unlimited and (limit_value is None or limit_value < 1))
            ):
                raise serializers.ValidationError({
                    'entitlements': f'{capability.code} exige limite maior que zero ou ilimitado.'
                })
            normalized.append({
                'capability': capability,
                'enabled': enabled,
                'unlimited': unlimited,
                'limit_value': limit_value,
            })

        normalized_by_capability = {item['capability'].pk: item for item in normalized}
        normalized_by_capability[core.pk] = {
            'capability': core,
            'enabled': True,
            'unlimited': True,
            'limit_value': None,
        }
        normalized_by_code = {
            item['capability'].code: item
            for item in normalized_by_capability.values()
        }
        pos = normalized_by_code.get('pos.enabled')
        pos_devices = normalized_by_code.get('pos.devices.max')
        if pos and pos['enabled'] and (
            not pos_devices
            or not pos_devices['enabled']
            or not pos_devices['unlimited'] and (
                pos_devices['limit_value'] is None or pos_devices['limit_value'] < 1
            )
        ):
            raise serializers.ValidationError({
                'entitlements': 'pos.devices.max exige limite maior que zero ou ilimitado quando pos.enabled esta habilitada.'
            })
        try:
            validate_entitlement_dependencies({
                item['capability'].code: item['enabled']
                for item in normalized_by_capability.values()
            })
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        attrs['entitlements'] = list(normalized_by_capability.values())
        return attrs

    @staticmethod
    def _replace_entitlements(version, entitlements):
        PlanEntitlement.objects.filter(plan_version=version).delete()
        PlanEntitlement.objects.bulk_create([
            PlanEntitlement(plan_version=version, **item)
            for item in entitlements
        ])

    @transaction.atomic
    def create(self, validated_data):
        entitlements = validated_data.pop('entitlements')
        version = PlanVersion.objects.create(**validated_data)
        self._replace_entitlements(version, entitlements)
        return version

    @transaction.atomic
    def update(self, instance, validated_data):
        entitlements = validated_data.pop('entitlements')
        version = super().update(instance, validated_data)
        self._replace_entitlements(version, entitlements)
        return version

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['entitlements'] = PlanEntitlementSerializer(
            instance.entitlements.select_related('capability').all(), many=True
        ).data
        return data


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
    code = serializers.SlugField(required=False)

    class Meta:
        model = Plan
        fields = ('id', 'code', 'name', 'description', 'is_active', 'versions', 'created_at', 'updated_at')
        read_only_fields = ('id', 'versions', 'created_at', 'updated_at')

    def validate(self, attrs):
        name = attrs.get('name', getattr(self.instance, 'name', ''))
        if not self.instance:
            attrs['code'] = slugify(attrs.get('code') or name)
            if not attrs['code']:
                raise serializers.ValidationError({'name': 'Informe um nome que gere um codigo tecnico valido.'})
        elif 'code' in attrs:
            attrs['code'] = slugify(attrs['code'])
            if not attrs['code']:
                raise serializers.ValidationError({'code': 'Informe um codigo tecnico valido.'})
            if attrs['code'] != self.instance.code and self.instance.versions.filter(subscriptions__isnull=False).exists():
                raise serializers.ValidationError({'code': 'O codigo de um plano utilizado nao pode ser alterado.'})
        return attrs


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
    billing_mode = serializers.ChoiceField(choices=Subscription.BillingMode.choices, required=False)
    initial_subscription_mode = serializers.ChoiceField(
        choices=(
            (Subscription.Status.ACTIVE, 'Ativa'),
            (Subscription.Status.TRIALING, 'Trial'),
        ),
        required=False,
        default=Subscription.Status.ACTIVE,
    )

    def validate(self, attrs):
        source = self.context['source']
        if 'owner_user' in self.initial_data:
            raise serializers.ValidationError({
                'owner_user': 'Informe o e-mail do Owner; a selecao tecnica de usuario nao e permitida.'
            })
        if source == ProvisioningOperation.Source.PUBLIC_SIGNUP:
            if not attrs.get('owner_email') or not attrs.get('owner_password'):
                raise serializers.ValidationError({'owner_email': 'Informe e-mail e senha do Owner.'})
            if 'billing_mode' in attrs:
                raise serializers.ValidationError({'billing_mode': 'O billing mode publico e definido pela plataforma.'})
            attrs.pop('initial_subscription_mode', None)
        else:
            if 'billing_mode' not in attrs:
                raise serializers.ValidationError({'billing_mode': 'Informe PAID, FREE ou INTERNAL.'})
            if not attrs.get('owner_email'):
                raise serializers.ValidationError({'owner_email': 'Informe o e-mail do Owner.'})
            existing = User.objects.filter(email__iexact=attrs['owner_email']).exists()
            if not existing and not attrs.get('owner_password'):
                raise serializers.ValidationError({'owner_password': 'Informe a senha inicial da nova conta.'})
            if attrs['initial_subscription_mode'] == Subscription.Status.TRIALING and not attrs['plan_version'].trial_days:
                raise serializers.ValidationError({'initial_subscription_mode': 'O plano selecionado nao possui dias de trial.'})
        if source == ProvisioningOperation.Source.PUBLIC_SIGNUP or not User.objects.filter(
            email__iexact=attrs.get('owner_email', '')
        ).exists():
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


class MapSubscriptionSerializer(serializers.Serializer):
    plan_version = serializers.PrimaryKeyRelatedField(queryset=PlanVersion.objects.select_related('plan'))
    billing_mode = serializers.ChoiceField(choices=Subscription.BillingMode.choices)
    initial_subscription_mode = serializers.ChoiceField(
        choices=(
            (Subscription.Status.ACTIVE, 'Ativa'),
            (Subscription.Status.TRIALING, 'Trial'),
        ),
        required=False,
        default=Subscription.Status.ACTIVE,
    )

    def validate(self, attrs):
        if (
            attrs['initial_subscription_mode'] == Subscription.Status.TRIALING
            and not attrs['plan_version'].trial_days
        ):
            raise serializers.ValidationError({
                'initial_subscription_mode': 'O plano selecionado nao possui dias de trial.'
            })
        return attrs


class ProvisioningResultSerializer(serializers.ModelSerializer):
    owner_user_id = serializers.IntegerField(source='user_id', read_only=True)
    approval_status = serializers.CharField(source='company.saas_state.approval_status', read_only=True)

    class Meta:
        model = ProvisioningOperation
        fields = ('id', 'source', 'company', 'subscription', 'owner_user_id', 'approval_status', 'created_at')


class LegalSettingsSerializer(serializers.Serializer):
    legal_name = serializers.CharField(required=False, allow_blank=True, max_length=254)
    trade_name = serializers.CharField(required=False, allow_blank=True, max_length=254)
    cnpj = serializers.CharField(required=False, allow_blank=True, max_length=254)
    address = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    jurisdiction = serializers.CharField(required=False, allow_blank=True, max_length=254)
    commercial_email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    legal_email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    privacy_email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    security_email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    dpo_name = serializers.CharField(required=False, allow_blank=True, max_length=254)
    dpo_email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    website_url = serializers.URLField(required=False, allow_blank=True, max_length=254)
    subprocessors_url = serializers.URLField(required=False, allow_blank=True, max_length=254)
    effective_date = serializers.CharField(required=False, allow_blank=True, max_length=254)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('Informe um objeto de configurações jurídicas.')
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: 'Campo não permitido.' for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate_effective_date(self, value):
        if value:
            from datetime import date
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError
            except ValueError:
                raise serializers.ValidationError('Use uma data válida no formato AAAA-MM-DD.')
        return value

    def validate_cnpj(self, value):
        if value:
            from apps.companies.validators import validate_cnpj
            try:
                validate_cnpj(value)
            except DjangoValidationError as error:
                raise serializers.ValidationError(error.messages)
        return value


class InstitutionalLinksSerializer(serializers.Serializer):
    terms = serializers.URLField(required=False, allow_blank=True, max_length=500)
    privacy = serializers.URLField(required=False, allow_blank=True, max_length=500)
    website = serializers.URLField(required=False, allow_blank=True, max_length=500)
    help = serializers.URLField(required=False, allow_blank=True, max_length=500)
    cookies = serializers.URLField(required=False, allow_blank=True, max_length=500)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('Informe os links institucionais em campos separados.')
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: 'Campo não permitido.' for key in sorted(unknown)})
        return super().to_internal_value(data)


class GlobalSaaSSettingsSerializer(serializers.ModelSerializer):
    legal_settings = LegalSettingsSerializer(required=False)
    institutional_links = InstitutionalLinksSerializer(required=False)
    branding_assets = serializers.SerializerMethodField()

    def update(self, instance, validated_data):
        if 'legal_settings' in validated_data:
            validated_data['legal_settings'] = {
                **(instance.legal_settings or {}), **validated_data['legal_settings'],
            }
        if 'institutional_links' in validated_data:
            validated_data['institutional_links'] = {
                **(instance.institutional_links or {}), **validated_data['institutional_links'],
            }
        return super().update(instance, validated_data)

    def get_branding_assets(self, instance):
        return {
            slot: branding_asset_url(instance, slot, self.context.get('request'))
            for slot in BRANDING_ASSET_FIELDS
        }

    class Meta:
        model = GlobalSaaSSettings
        exclude = ('singleton', *BRANDING_ASSET_FIELDS.values())
        read_only_fields = (
            'id', 'enforcement_enabled', 'enforcement_enabled_at',
            'enforcement_enabled_by', 'created_at', 'updated_at',
            'logo_url', 'compact_logo_url', 'favicon_url', 'logo_light_url',
            'logo_dark_url', 'compact_logo_light_url', 'compact_logo_dark_url',
        )


class CommercialLeadSerializer(serializers.ModelSerializer):
    honeypot = serializers.CharField(required=False, allow_blank=True, write_only=True, trim_whitespace=False)

    class Meta:
        model = CommercialLead
        fields = (
            'name', 'company_name', 'whatsapp', 'email', 'segment', 'message',
            'source_path', 'plan_interest', 'utm_source', 'utm_medium', 'utm_campaign', 'honeypot',
        )
        extra_kwargs = {
            'message': {'required': False, 'allow_blank': True},
            'source_path': {'required': False, 'allow_blank': True},
            'plan_interest': {'required': False, 'allow_blank': True},
            'utm_source': {'required': False, 'allow_blank': True},
            'utm_medium': {'required': False, 'allow_blank': True},
            'utm_campaign': {'required': False, 'allow_blank': True},
        }

    def validate_whatsapp(self, value):
        digits = ''.join(char for char in value if char.isdigit())
        if not 10 <= len(digits) <= 15:
            raise serializers.ValidationError('Informe um WhatsApp válido com DDD.')
        return value

    def validate_source_path(self, value):
        if value and not value.startswith('/'):
            raise serializers.ValidationError('A origem deve ser um caminho interno.')
        return value

    def validate(self, attrs):
        if attrs.pop('honeypot', ''):
            raise serializers.ValidationError('Não foi possível enviar o contato.')
        return attrs


class PlatformCommercialLeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommercialLead
        fields = (
            'id', 'name', 'company_name', 'whatsapp', 'email', 'segment', 'message',
            'source_path', 'plan_interest', 'utm_source', 'utm_medium', 'utm_campaign',
            'status', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class CommercialLeadStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CommercialLead.Status.choices)


class PublicBrandingSerializer(serializers.ModelSerializer):
    legal_settings = LegalSettingsSerializer(read_only=True)
    institutional_links = InstitutionalLinksSerializer(read_only=True)
    logo_url = serializers.SerializerMethodField()
    compact_logo_url = serializers.SerializerMethodField()
    favicon_url = serializers.SerializerMethodField()
    logo_light_url = serializers.SerializerMethodField()
    logo_dark_url = serializers.SerializerMethodField()
    compact_logo_light_url = serializers.SerializerMethodField()
    compact_logo_dark_url = serializers.SerializerMethodField()

    def _asset_url(self, instance, slot):
        return resolved_branding_asset_url(instance, slot, self.context.get('request'))

    def get_logo_url(self, instance):
        return self._asset_url(instance, 'logo')

    def get_compact_logo_url(self, instance):
        return self._asset_url(instance, 'compact_logo')

    def get_favicon_url(self, instance):
        return self._asset_url(instance, 'favicon')

    def get_logo_light_url(self, instance):
        return self._asset_url(instance, 'logo_light')

    def get_logo_dark_url(self, instance):
        return self._asset_url(instance, 'logo_dark')

    def get_compact_logo_light_url(self, instance):
        return self._asset_url(instance, 'compact_logo_light')

    def get_compact_logo_dark_url(self, instance):
        return self._asset_url(instance, 'compact_logo_dark')

    class Meta:
        model = GlobalSaaSSettings
        fields = (
            'platform_name', 'logo_url', 'compact_logo_url', 'favicon_url',
            'logo_light_url', 'logo_dark_url', 'compact_logo_light_url',
            'compact_logo_dark_url',
            'primary_color', 'support_email', 'support_phone', 'institutional_links', 'legal_settings',
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
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
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
