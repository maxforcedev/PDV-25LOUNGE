import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q

from apps.base.models import BaseModel
from apps.companies.models import Company, UserCompanyAccess


class ProtectedQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError('Registros historicos deste dominio nao podem ser excluidos.')


class AppendOnlyQuerySet(ProtectedQuerySet):
    def update(self, **kwargs):
        raise ValidationError('Registros append-only nao podem ser alterados.')


class PlatformPermission(BaseModel):
    code = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=120)

    class Meta:
        ordering = ('code',)

    def __str__(self):
        return self.label


class PlatformRole(BaseModel):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(PlatformPermission, blank=True, related_name='roles')

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class PlatformUserAccess(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='platform_access'
    )
    role = models.ForeignKey(PlatformRole, on_delete=models.PROTECT, related_name='user_accesses')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.user} - {self.role}'


class Plan(BaseModel):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('name',)

    def delete(self, *args, **kwargs):
        if Subscription.objects.filter(plan_version__plan=self).exists():
            raise ValidationError('Planos utilizados nao podem ser excluidos.')
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.name


class PlanVersionQuerySet(models.QuerySet):
    IMMUTABLE_FIELDS = {
        'plan', 'plan_id', 'version', 'price', 'currency',
        'billing_period_months', 'trial_days', 'is_public', 'is_active',
    }

    def update(self, **kwargs):
        if not self.IMMUTABLE_FIELDS.intersection(kwargs):
            return super().update(**kwargs)
        with transaction.atomic(using=self.db):
            locked = self.select_for_update()
            if locked.filter(subscriptions__isnull=False).exists():
                raise ValidationError('Versoes de plano utilizadas sao imutaveis.')
            return super(PlanVersionQuerySet, locked).update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if self.IMMUTABLE_FIELDS.intersection(fields):
            with transaction.atomic(using=self.db):
                ids = [item.pk for item in objs]
                self.model.objects.select_for_update().filter(pk__in=ids).count()
                if Subscription.objects.filter(plan_version_id__in=ids).exists():
                    raise ValidationError('Versoes de plano utilizadas sao imutaveis.')
                return super().bulk_update(objs, fields, batch_size=batch_size)
        return super().bulk_update(objs, fields, batch_size=batch_size)


class PlanVersion(BaseModel):
    objects = PlanVersionQuerySet.as_manager()

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='versions')
    version = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='BRL')
    billing_period_months = models.PositiveSmallIntegerField(default=1)
    trial_days = models.PositiveSmallIntegerField(default=0)
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    IMMUTABLE_FIELDS = (
        'plan_id', 'version', 'price', 'currency', 'billing_period_months',
        'trial_days', 'is_public', 'is_active',
    )

    class Meta:
        ordering = ('plan__name', '-version')
        constraints = [
            models.UniqueConstraint(fields=('plan', 'version'), name='saas_plan_version_unique'),
            models.CheckConstraint(condition=Q(price__gte=0), name='saas_plan_version_price_nonnegative'),
            models.CheckConstraint(
                condition=Q(billing_period_months__gte=1),
                name='saas_plan_version_period_positive',
            ),
        ]

    @property
    def is_used(self):
        return self.subscriptions.exists()

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.pk:
                previous = type(self).objects.select_for_update().get(pk=self.pk)
                if previous.subscriptions.exists():
                    changed = [
                        field for field in self.IMMUTABLE_FIELDS
                        if getattr(previous, field) != getattr(self, field)
                    ]
                    if changed:
                        raise ValidationError({field: 'Uma versao utilizada e imutavel.' for field in changed})
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            type(self).objects.select_for_update().get(pk=self.pk)
            if self.is_used:
                raise ValidationError('Versoes de plano utilizadas nao podem ser excluidas.')
            return super().delete(*args, **kwargs)

    def __str__(self):
        return f'{self.plan.name} v{self.version}'


class Capability(BaseModel):
    class ValueType(models.TextChoices):
        BOOLEAN = 'BOOLEAN', 'Habilitado/desabilitado'
        INTEGER = 'INTEGER', 'Limite numerico'

    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    value_type = models.CharField(max_length=10, choices=ValueType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('code',)

    def __str__(self):
        return self.name


class PlanEntitlementQuerySet(models.QuerySet):
    def update(self, **kwargs):
        with transaction.atomic(using=self.db):
            version_ids = set(self.values_list('plan_version_id', flat=True).distinct())
            target = kwargs.get('plan_version_id') or getattr(kwargs.get('plan_version'), 'pk', None)
            if target:
                version_ids.add(target)
            PlanVersion.objects.select_for_update().filter(pk__in=version_ids).count()
            if Subscription.objects.filter(plan_version_id__in=version_ids).exists():
                raise ValidationError('Entitlements de uma versao utilizada sao imutaveis.')
            return super().update(**kwargs)

    def delete(self):
        with transaction.atomic(using=self.db):
            version_ids = list(self.values_list('plan_version_id', flat=True).distinct())
            PlanVersion.objects.select_for_update().filter(pk__in=version_ids).count()
            if Subscription.objects.filter(plan_version_id__in=version_ids).exists():
                raise ValidationError('Entitlements de uma versao utilizada sao imutaveis.')
            return super().delete()

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False, update_fields=None, unique_fields=None):
        version_ids = {item.plan_version_id for item in objs}
        with transaction.atomic(using=self.db):
            PlanVersion.objects.select_for_update().filter(pk__in=version_ids).count()
            if Subscription.objects.filter(plan_version_id__in=version_ids).exists():
                raise ValidationError('Entitlements de uma versao utilizada sao imutaveis.')
            return super().bulk_create(
                objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts, update_fields=update_fields,
                unique_fields=unique_fields,
            )

    def bulk_update(self, objs, fields, batch_size=None):
        version_ids = {item.plan_version_id for item in objs}
        version_ids.update(self.filter(pk__in=[item.pk for item in objs]).values_list('plan_version_id', flat=True))
        with transaction.atomic(using=self.db):
            PlanVersion.objects.select_for_update().filter(pk__in=version_ids).count()
            if Subscription.objects.filter(plan_version_id__in=version_ids).exists():
                raise ValidationError('Entitlements de uma versao utilizada sao imutaveis.')
            return super().bulk_update(objs, fields, batch_size=batch_size)


class PlanEntitlement(BaseModel):
    objects = PlanEntitlementQuerySet.as_manager()

    plan_version = models.ForeignKey(PlanVersion, on_delete=models.CASCADE, related_name='entitlements')
    capability = models.ForeignKey(Capability, on_delete=models.PROTECT, related_name='entitlements')
    enabled = models.BooleanField(default=True)
    unlimited = models.BooleanField(default=False)
    limit_value = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        ordering = ('capability__code',)
        constraints = [
            models.UniqueConstraint(
                fields=('plan_version', 'capability'), name='saas_plan_entitlement_unique'
            ),
            models.CheckConstraint(
                condition=(
                    Q(enabled=False, unlimited=False, limit_value__isnull=True)
                    | Q(enabled=True, unlimited=True, limit_value__isnull=True)
                    | Q(enabled=True, unlimited=False, limit_value__isnull=False)
                ),
                name='saas_plan_entitlement_value_coherent',
            ),
        ]

    def clean(self):
        if self.plan_version_id and Subscription.objects.filter(plan_version_id=self.plan_version_id).exists():
            if not self.pk:
                raise ValidationError('Entitlements de uma versao utilizada sao imutaveis.')
            previous = type(self).objects.get(pk=self.pk)
            fields = ('capability_id', 'enabled', 'unlimited', 'limit_value')
            if any(getattr(previous, field) != getattr(self, field) for field in fields):
                raise ValidationError('Entitlements de uma versao utilizada sao imutaveis.')
        if self.capability_id:
            if self.capability.value_type == Capability.ValueType.BOOLEAN and self.limit_value is not None:
                raise ValidationError({'limit_value': 'Capacidades booleanas nao possuem limite.'})
            if self.capability.value_type == Capability.ValueType.INTEGER and self.enabled and not self.unlimited and self.limit_value is None:
                raise ValidationError({'limit_value': 'Informe o limite numerico.'})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous_version_id = None
            if self.pk:
                previous_version_id = type(self).objects.filter(pk=self.pk).values_list(
                    'plan_version_id', flat=True
                ).first()
            version_ids = {item for item in (previous_version_id, self.plan_version_id) if item}
            PlanVersion.objects.select_for_update().filter(pk__in=version_ids).count()
            if previous_version_id and Subscription.objects.filter(
                plan_version_id__in=version_ids
            ).exists():
                previous = type(self).objects.get(pk=self.pk)
                fields = ('plan_version_id', 'capability_id', 'enabled', 'unlimited', 'limit_value')
                if any(getattr(previous, field) != getattr(self, field) for field in fields):
                    raise ValidationError('Entitlements de uma versao utilizada sao imutaveis.')
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            PlanVersion.objects.select_for_update().get(pk=self.plan_version_id)
            if Subscription.objects.filter(plan_version_id=self.plan_version_id).exists():
                raise ValidationError('Entitlements de uma versao utilizada sao imutaveis.')
            return super().delete(*args, **kwargs)


class SubscriptionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if {'company', 'company_id', 'plan_version', 'plan_version_id'}.intersection(kwargs):
            raise ValidationError('Company e PlanVersion da assinatura sao imutaveis.')
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if {'company', 'company_id', 'plan_version', 'plan_version_id'}.intersection(fields):
            raise ValidationError('Company e PlanVersion da assinatura sao imutaveis.')
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, *args, **kwargs):
        version_ids = {item.plan_version_id for item in objs}
        with transaction.atomic(using=self.db):
            versions = {
                item.pk: item
                for item in PlanVersion.objects.select_for_update().filter(pk__in=version_ids)
            }
            from .services import validate_plan_version_complete

            for version in versions.values():
                validate_plan_version_complete(version, lock=True)
            return super().bulk_create(objs, *args, **kwargs)

    def delete(self):
        raise ValidationError('Assinaturas nao podem ser excluidas.')


class Subscription(BaseModel):
    class BillingMode(models.TextChoices):
        PAID = 'PAID', 'Pago'
        FREE = 'FREE', 'Gratuito'
        INTERNAL = 'INTERNAL', 'Interno'

    class Status(models.TextChoices):
        TRIALING = 'TRIALING', 'Em trial'
        ACTIVE = 'ACTIVE', 'Ativa'
        PAST_DUE = 'PAST_DUE', 'Inadimplente'
        RESTRICTED = 'RESTRICTED', 'Restrita'
        SUSPENDED_FINANCIAL = 'SUSPENDED_FINANCIAL', 'Suspensa financeiramente'
        TRIAL_EXPIRED = 'TRIAL_EXPIRED', 'Trial expirado'
        CANCELLED = 'CANCELLED', 'Cancelada'
        SUPERSEDED = 'SUPERSEDED', 'Substituida por mudanca de plano'

    objects = SubscriptionQuerySet.as_manager()

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='subscriptions')
    plan_version = models.ForeignKey(PlanVersion, on_delete=models.PROTECT, related_name='subscriptions')
    billing_mode = models.CharField(max_length=10, choices=BillingMode.choices)
    status = models.CharField(max_length=25, choices=Status.choices)
    is_current = models.BooleanField(default=True)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    trial_started_at = models.DateTimeField(blank=True, null=True)
    trial_ends_at = models.DateTimeField(blank=True, null=True)
    cancel_at_period_end = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('company',), condition=Q(is_current=True),
                name='saas_subscription_one_current_per_company',
            ),
            models.CheckConstraint(
                condition=Q(current_period_start__lt=F('current_period_end')),
                name='saas_subscription_period_valid',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status='TRIALING', trial_started_at__isnull=False, trial_ends_at__isnull=False)
                    | ~Q(status='TRIALING')
                ),
                name='saas_subscription_trial_dates_present',
            ),
        ]

    def clean(self):
        if self.current_period_start and self.current_period_end and self.current_period_start >= self.current_period_end:
            raise ValidationError({'current_period_end': 'O fim do periodo deve ser posterior ao inicio.'})
        if self.status == self.Status.TRIALING and (not self.trial_started_at or not self.trial_ends_at):
            raise ValidationError({'trial_ends_at': 'Uma assinatura em trial exige datas de trial.'})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            PlanVersion.objects.select_for_update().get(pk=self.plan_version_id)
            if self.pk:
                previous = type(self).objects.select_for_update().get(pk=self.pk)
                if (
                    previous.company_id != self.company_id
                    or previous.plan_version_id != self.plan_version_id
                ):
                    raise ValidationError('Company e PlanVersion da assinatura sao imutaveis.')
            else:
                from .services import validate_plan_version_complete

                validate_plan_version_complete(self.plan_version, lock=True)
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Assinaturas nao podem ser excluidas.')


class TenantSaaSState(BaseModel):
    class ApprovalStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pendente'
        APPROVED = 'APPROVED', 'Aprovado'
        REJECTED = 'REJECTED', 'Rejeitado'

    company = models.OneToOneField(Company, on_delete=models.PROTECT, related_name='saas_state')
    approval_status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.APPROVED
    )
    approval_reason = models.TextField(blank=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True,
        related_name='approved_saas_tenants',
    )
    admin_suspended_at = models.DateTimeField(blank=True, null=True)
    admin_suspended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True,
        related_name='admin_suspended_saas_tenants',
    )
    admin_suspension_reason = models.TextField(blank=True)
    archived_at = models.DateTimeField(blank=True, null=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True,
        related_name='archived_saas_tenants',
    )
    archive_reason = models.TextField(blank=True)

    @property
    def is_admin_suspended(self):
        return self.admin_suspended_at is not None


class GlobalSaaSSettings(BaseModel):
    singleton = models.BooleanField(default=True, unique=True, editable=False)
    auto_approve_signups = models.BooleanField(default=True)
    past_due_days = models.PositiveSmallIntegerField(default=3)
    restricted_after_days = models.PositiveSmallIntegerField(default=10)
    support_session_minutes = models.PositiveSmallIntegerField(default=60)
    public_signup_billing_mode = models.CharField(
        max_length=10,
        choices=(('PAID', 'Pago'), ('FREE', 'Gratuito')),
        default='PAID',
    )
    enforcement_enabled = models.BooleanField(default=False, editable=False)
    enforcement_enabled_at = models.DateTimeField(blank=True, null=True, editable=False)
    enforcement_enabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True,
        related_name='enabled_saas_enforcement', editable=False,
    )
    platform_name = models.CharField(max_length=100, default='CORE PDV')
    logo_url = models.URLField(blank=True)
    compact_logo_url = models.URLField(blank=True)
    favicon_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=20, default='#111827')
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=30, blank=True)
    support_whatsapp = models.CharField(max_length=30, blank=True)
    institutional_links = models.JSONField(default=dict, blank=True)

    def clean(self):
        if self.past_due_days > self.restricted_after_days:
            raise ValidationError({'restricted_after_days': 'Deve ser maior ou igual ao prazo de inadimplencia.'})
        if not 1 <= self.support_session_minutes <= 240:
            raise ValidationError({'support_session_minutes': 'Informe um prazo entre 1 e 240 minutos.'})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).only('enforcement_enabled').first()
            if previous and previous.enforcement_enabled and not self.enforcement_enabled:
                raise ValidationError({'enforcement_enabled': 'O cutover SaaS nao pode ser desabilitado.'})

    def save(self, *args, **kwargs):
        if not self.pk and type(self).objects.exists():
            raise ValidationError('Existe apenas uma configuracao global SaaS.')
        self.full_clean()
        return super().save(*args, **kwargs)


class CycleUsage(BaseModel):
    objects = ProtectedQuerySet.as_manager()

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name='usage_history')
    capability = models.ForeignKey(Capability, on_delete=models.PROTECT, related_name='usage_history')
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('-period_start', 'capability__code')
        constraints = [
            models.UniqueConstraint(
                fields=('subscription', 'capability', 'period_start'),
                name='saas_cycle_usage_unique',
            ),
            models.CheckConstraint(
                condition=Q(period_start__lt=F('period_end')),
                name='saas_cycle_usage_period_valid',
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError('Historico de uso nao pode ser excluido.')


class BillingRecord(BaseModel):
    objects = AppendOnlyQuerySet.as_manager()

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name='billing_records')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField()
    payment_method = models.CharField(max_length=50)
    note = models.TextField(blank=True)
    proof_reference = models.CharField(max_length=500, blank=True)
    competency_start = models.DateTimeField()
    competency_end = models.DateTimeField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='saas_billing_records'
    )
    idempotency_key = models.CharField(max_length=100)
    request_fingerprint = models.CharField(max_length=64)

    class Meta:
        ordering = ('-paid_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('subscription', 'idempotency_key'),
                name='saas_billing_record_idempotency_unique',
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name='saas_billing_record_amount_positive'),
            models.CheckConstraint(
                condition=Q(competency_start__lt=F('competency_end')),
                name='saas_billing_record_competency_valid',
            ),
        ]

    def clean(self):
        if self.proof_reference and not re.fullmatch(
            r'(?:https://[^\s]+|[A-Za-z0-9][A-Za-z0-9._/-]{0,499})',
            self.proof_reference,
        ):
            raise ValidationError({'proof_reference': 'Referencia de comprovante invalida.'})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Pagamentos sao append-only.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Pagamentos nao podem ser excluidos.')


class SubscriptionRequest(BaseModel):
    class RequestType(models.TextChoices):
        PLAN_CHANGE = 'PLAN_CHANGE', 'Mudanca de plano'
        CANCELLATION = 'CANCELLATION', 'Cancelamento'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendente'
        APPROVED = 'APPROVED', 'Aprovada'
        REJECTED = 'REJECTED', 'Rejeitada'

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name='change_requests')
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    requested_plan_version = models.ForeignKey(
        PlanVersion, on_delete=models.PROTECT, blank=True, null=True,
        related_name='subscription_requests',
    )
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='subscription_requests'
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True,
        related_name='resolved_subscription_requests',
    )
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('-created_at', '-id')


class SupportSessionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Support Sessions so podem ser encerradas pelo service.')

    def delete(self):
        raise ValidationError('Support Sessions nao podem ser excluidas.')


class SupportSession(BaseModel):
    class Mode(models.TextChoices):
        READ_ONLY = 'READ_ONLY', 'Somente leitura'
        READ_WRITE = 'READ_WRITE', 'Leitura e escrita'

    objects = SupportSessionQuerySet.as_manager()

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='support_sessions'
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='support_sessions')
    impersonated_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True,
        related_name='impersonated_support_sessions',
    )
    mode = models.CharField(max_length=10, choices=Mode.choices)
    reason = models.TextField()
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(blank=True, null=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True,
        related_name='ended_support_sessions',
    )

    class Meta:
        ordering = ('-created_at', '-id')

    IMMUTABLE_FIELDS = ('actor_id', 'company_id', 'impersonated_user_id', 'mode', 'reason', 'expires_at')

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            changed = [field for field in self.IMMUTABLE_FIELDS if getattr(previous, field) != getattr(self, field)]
            if changed:
                raise ValidationError({field: 'Support Sessions sao imutaveis apos a criacao.' for field in changed})
            if previous.ended_at and (self.ended_at != previous.ended_at or self.ended_by_id != previous.ended_by_id):
                raise ValidationError('Uma Support Session encerrada nao pode ser alterada.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Support Sessions nao podem ser excluidas.')


class ProvisioningOperation(BaseModel):
    class Source(models.TextChoices):
        PUBLIC_SIGNUP = 'PUBLIC_SIGNUP', 'Autoatendimento'
        PLATFORM_MANUAL = 'PLATFORM_MANUAL', 'Plataforma'

    source = models.CharField(max_length=20, choices=Source.choices)
    idempotency_key = models.CharField(max_length=100)
    request_fingerprint = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    company = models.OneToOneField(Company, on_delete=models.PROTECT, related_name='provisioning_operation')
    subscription = models.OneToOneField(
        Subscription, on_delete=models.PROTECT, related_name='provisioning_operation'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('source', 'idempotency_key'),
                name='saas_provisioning_idempotency_unique',
            ),
        ]
