from decimal import Decimal

from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.conf import settings
from django.core.exceptions import ValidationError

from apps.base.models import BaseModel

from .validators import normalize_cnpj, validate_cnpj


class Status(models.TextChoices):
    ACTIVE = 'active', 'Ativo'
    INACTIVE = 'inactive', 'Inativo'


class AccessProfileQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if 'status' in kwargs and kwargs['status'] != Status.ACTIVE:
            with transaction.atomic(using=self.db):
                list(self.select_for_update().values_list('pk', flat=True))
                if self.filter(user_accesses__is_owner=True).exists():
                    raise ValidationError(
                        {'status': 'O perfil do proprietário da empresa não pode ser inativado.'}
                    )
                return super().update(**kwargs)
        return super().update(**kwargs)


class UserCompanyAccessQuerySet(models.QuerySet):
    OWNER_PROTECTED_FIELDS = {
        'company',
        'company_id',
        'is_active',
        'is_owner',
        'saas_status',
        'user',
        'user_id',
    }

    def update(self, **kwargs):
        if 'is_owner' in kwargs:
            raise ValidationError(
                {'is_owner': 'Use o serviço de propriedade para alterar o proprietário.'}
            )
        if kwargs.get('is_active') is True or kwargs.get('saas_status') == 'ACTIVE':
            raise ValidationError(
                {'limit': 'Ativacoes de membership devem usar save/service para validar users.max.'}
            )
        if {'company', 'company_id', 'user', 'user_id'}.intersection(kwargs):
            raise ValidationError(
                {'limit': 'Mudancas de escopo do membership devem usar save/service.'}
            )
        if self.OWNER_PROTECTED_FIELDS.intersection(kwargs):
            with transaction.atomic(using=self.db):
                list(self.select_for_update().values_list('pk', flat=True))
                if self.filter(is_owner=True).exists():
                    raise ValidationError(
                        {'is_owner': 'Transfira a propriedade antes de alterar este acesso.'}
                    )
                return super().update(**kwargs)
        return super().update(**kwargs)

    def delete(self):
        with transaction.atomic(using=self.db):
            list(self.select_for_update().values_list('pk', flat=True))
            if self.filter(is_owner=True).exists():
                raise ValidationError(
                    {'is_owner': 'Transfira a propriedade antes de remover este acesso.'}
                )
            return super().delete()

    def bulk_update(self, objs, fields, batch_size=None):
        if self.OWNER_PROTECTED_FIELDS.intersection(fields):
            raise ValidationError({
                'limit': 'Alteracoes em massa de memberships protegidos devem usar save/service.'
            })
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, *args, **kwargs):
        seats_by_company = {}
        for item in objs:
            if item.is_active and item.saas_status == item.SaaSStatus.ACTIVE and item.user.can_login and item.user.is_active:
                seats_by_company[item.company_id] = seats_by_company.get(item.company_id, 0) + 1
        with transaction.atomic(using=self.db):
            from apps.saas.services import assert_resource_limit

            for company_id, delta in sorted(seats_by_company.items()):
                company = Company.objects.select_for_update().get(pk=company_id)
                assert_resource_limit(company, 'users.max', delta=delta, company_locked=True)
            return super().bulk_create(objs, *args, **kwargs)


class BranchQuerySet(models.QuerySet):
    LIMIT_FIELDS = {'company', 'company_id', 'status'}

    def update(self, **kwargs):
        if kwargs.get('status') == Status.ACTIVE:
            raise ValidationError({'limit': 'Ative filiais pelo service para validar branches.max.'})
        if {'company', 'company_id'}.intersection(kwargs):
            raise ValidationError({'limit': 'A empresa da filial nao pode ser alterada em massa.'})
        return super().update(**kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        active_by_company = {}
        for branch in objs:
            if branch.status == Status.ACTIVE:
                active_by_company[branch.company_id] = active_by_company.get(branch.company_id, 0) + 1
        with transaction.atomic(using=self.db):
            from apps.saas.services import assert_resource_limit

            for company_id, delta in sorted(active_by_company.items()):
                company = Company.objects.select_for_update().get(pk=company_id)
                assert_resource_limit(company, 'branches.max', delta=delta, company_locked=True)
            return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if self.LIMIT_FIELDS.intersection(fields):
            raise ValidationError({
                'limit': 'Alteracoes em massa de filiais devem usar save/service.'
            })
        return super().bulk_update(objs, fields, batch_size=batch_size)


class Company(BaseModel):
    trade_name = models.CharField(max_length=150)
    legal_name = models.CharField(max_length=200)
    cnpj = models.CharField(
        max_length=14,
        blank=True,
        null=True,
        db_index=True,
        validators=[validate_cnpj],
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('trade_name',)
        verbose_name_plural = 'companies'
        constraints = [
            models.UniqueConstraint(
                fields=('cnpj',),
                condition=Q(cnpj__isnull=False),
                name='companies_company_cnpj_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.trade_name = ' '.join(self.trade_name.split())
        self.legal_name = ' '.join(self.legal_name.split())
        self.cnpj = normalize_cnpj(self.cnpj)
        validate_cnpj(self.cnpj)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.trade_name


class Branch(BaseModel):
    objects = BranchQuerySet.as_manager()

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='branches')
    name = models.CharField(max_length=150)
    cnpj = models.CharField(
        max_length=14,
        blank=True,
        null=True,
        db_index=True,
        validators=[validate_cnpj],
    )
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.JSONField(default=dict, blank=True)
    address_pending = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_matrix = models.BooleanField(default=False)

    class Meta:
        ordering = ('company__trade_name', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'name'),
                name='companies_branch_company_name_unique',
            ),
            models.UniqueConstraint(
                fields=('cnpj',),
                condition=Q(cnpj__isnull=False),
                name='companies_branch_cnpj_unique',
            ),
            models.UniqueConstraint(
                fields=('company',),
                condition=Q(is_matrix=True),
                name='companies_branch_one_matrix_per_company',
            ),
        ]

    def clean(self):
        super().clean()
        self.cnpj = normalize_cnpj(self.cnpj)
        validate_cnpj(self.cnpj)
        if self.is_matrix:
            self.name = 'Matriz'

    def save(self, *args, **kwargs):
        enforce_saas_limit = kwargs.pop('enforce_saas_limit', True)
        with transaction.atomic():
            previous_status = None
            previous_company_id = None
            if self.pk:
                previous = type(self).objects.filter(pk=self.pk).values('status', 'company_id').first()
                if previous:
                    previous_status = previous['status']
                    previous_company_id = previous['company_id']
            activating = self.status == Status.ACTIVE and (
                previous_status != Status.ACTIVE or previous_company_id != self.company_id
            )
            if enforce_saas_limit and activating and self.company_id:
                from apps.saas.services import assert_resource_limit

                company = Company.objects.select_for_update().get(pk=self.company_id)
                assert_resource_limit(company, 'branches.max', company_locked=True)
            self.full_clean()
            return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company.trade_name} - {self.name}'


class BranchSettings(BaseModel):
    branch = models.OneToOneField(
        Branch, on_delete=models.CASCADE, related_name='settings'
    )
    allow_negative_stock = models.BooleanField(default=False)
    service_fee_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00')
    )
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00')
    )
    fixed_daily_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    uses_tables = models.BooleanField(default=False)
    uses_commands = models.BooleanField(default=False)
    uses_counter = models.BooleanField(default=True)
    uses_consumption = models.BooleanField(default=True)
    uses_cash_register = models.BooleanField(default=True)
    charges_service_fee = models.BooleanField(default=False)
    default_table_quantity = models.PositiveIntegerField(default=20)
    default_table_seats = models.PositiveIntegerField(default=0)
    default_table_prefix = models.CharField(max_length=50, default='Mesa ')
    consumption_limit_enabled = models.BooleanField(default=False)
    command_consumption_limit = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    table_consumption_limit = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(service_fee_rate__gte=0) & Q(service_fee_rate__lte=100),
                name='companies_branchsettings_service_fee_range',
            ),
            models.CheckConstraint(
                condition=Q(commission_rate__gte=0) & Q(commission_rate__lte=100),
                name='companies_branchsettings_commission_range',
            ),
            models.CheckConstraint(
                condition=Q(fixed_daily_cost__gte=0),
                name='companies_branchsettings_fixed_cost_nonnegative',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.service_fee_rate is not None and not (Decimal('0') <= self.service_fee_rate <= Decimal('100')):
            errors['service_fee_rate'] = 'A taxa de serviço deve estar entre 0 e 100.'
        if self.commission_rate is not None and not (Decimal('0') <= self.commission_rate <= Decimal('100')):
            errors['commission_rate'] = 'A comissão deve estar entre 0 e 100.'
        if self.fixed_daily_cost is not None and self.fixed_daily_cost < 0:
            errors['fixed_daily_cost'] = 'O custo fixo não pode ser negativo.'
        if self.default_table_quantity > 500:
            errors['default_table_quantity'] = 'O padrão de mesas não pode exceder 500.'
        if self.consumption_limit_enabled:
            if self.command_consumption_limit is not None and self.command_consumption_limit <= 0:
                errors['command_consumption_limit'] = 'O limite da comanda deve ser maior que zero.'
            if self.table_consumption_limit is not None and self.table_consumption_limit <= 0:
                errors['table_consumption_limit'] = 'O limite da mesa deve ser maior que zero.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def feature_flags(self):
        return {
            'tables': self.uses_tables,
            'commands': self.uses_commands,
            'counter': self.uses_counter,
            'consumption': self.uses_consumption,
            'cash_register': self.uses_cash_register,
            'service_fee': self.charges_service_fee,
            'negative_stock': self.allow_negative_stock,
            'consumption_limit': self.consumption_limit_enabled,
        }

    def __str__(self):
        return f'Configurações de {self.branch}'


class FunctionalPermission(BaseModel):
    class Scope(models.TextChoices):
        COMPANY = 'COMPANY', 'Company'
        BRANCH = 'BRANCH', 'Branch'

    code = models.CharField(max_length=100, unique=True)
    module = models.CharField(max_length=50)
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.COMPANY)
    label = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('module', 'code')

    def __str__(self):
        return self.label


class AccessProfile(BaseModel):
    objects = AccessProfileQuerySet.as_manager()

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='access_profiles',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    receives_commission = models.BooleanField(default=True)
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
    )
    permissions = models.ManyToManyField(
        FunctionalPermission,
        related_name='access_profiles',
        blank=True,
    )
    archived_at = models.DateTimeField(blank=True, null=True, default=None)

    class Meta:
        ordering = ('company__trade_name', 'name')
        constraints = [
            models.UniqueConstraint(
                'company',
                Lower('name'),
                name='companies_access_profile_company_name_ci_unique',
            ),
        ]

    def __str__(self):
        return f'{self.company} - {self.name}'

    def clean(self):
        super().clean()
        if self.commission_rate is not None and not (Decimal('0') <= self.commission_rate <= Decimal('100')):
            raise ValidationError({'commission_rate': 'A comissão do perfil deve estar entre 0 e 100.'})
        if (
            self.pk
            and self.status == Status.INACTIVE
            and self.user_accesses.filter(is_owner=True).exists()
        ):
            raise ValidationError(
                {'status': 'O perfil do proprietário da empresa não pode ser inativado.'}
            )

    def save(self, *args, **kwargs):
        if self.pk and self.status == Status.INACTIVE:
            with transaction.atomic():
                type(self).objects.select_for_update().filter(pk=self.pk).exists()
                self.full_clean()
                return super().save(*args, **kwargs)
        self.full_clean()
        return super().save(*args, **kwargs)


class UserCompanyAccess(BaseModel):
    class SaaSStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Ativo no plano'
        SUSPENDED_BY_PLAN_LIMIT = 'SUSPENDED_BY_PLAN_LIMIT', 'Suspenso por limite do plano'

    objects = UserCompanyAccessQuerySet.as_manager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_accesses',
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='user_accesses',
    )
    access_profile = models.ForeignKey(
        AccessProfile,
        on_delete=models.PROTECT,
        related_name='user_accesses',
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True)
    is_owner = models.BooleanField(default=False)
    saas_status = models.CharField(
        max_length=30,
        choices=SaaSStatus.choices,
        default=SaaSStatus.ACTIVE,
        db_default=SaaSStatus.ACTIVE,
    )

    class Meta:
        ordering = ('company__trade_name', 'user__email')
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'company'),
                name='companies_user_company_access_unique',
            ),
            models.UniqueConstraint(
                fields=('company',),
                condition=Q(is_owner=True),
                name='companies_user_company_one_owner',
            ),
            models.CheckConstraint(
                condition=Q(is_owner=False) | Q(is_active=True),
                name='companies_user_company_owner_active',
            ),
            models.CheckConstraint(
                condition=Q(is_owner=False) | Q(saas_status='ACTIVE'),
                name='companies_user_company_owner_saas_active',
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.company_id
            and self.access_profile_id
            and self.access_profile.company_id != self.company_id
        ):
            raise ValidationError(
                {'access_profile': 'O perfil deve pertencer a empresa do acesso.'}
            )
        if self.is_owner:
            errors = {}
            if not self.is_active:
                errors['is_active'] = 'O acesso do proprietário deve permanecer ativo.'
            if self.saas_status != self.SaaSStatus.ACTIVE:
                errors['saas_status'] = 'O proprietário não pode ser suspenso por limite do plano.'
            if self.user_id and (not self.user.is_active or not self.user.can_login):
                errors['user'] = 'O proprietário deve estar ativo e habilitado para login.'
            if errors:
                raise ValidationError(errors)

        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                'company_id', 'user_id', 'is_active', 'is_owner',
                'saas_status',
            ).first()
            if previous and previous['is_owner']:
                errors = {}
                if not self.is_owner:
                    errors['is_owner'] = 'Use a transferência de propriedade para alterar o proprietário.'
                if self.company_id != previous['company_id']:
                    errors['company'] = 'A empresa do proprietário não pode ser alterada.'
                if self.user_id != previous['user_id']:
                    errors['user'] = 'O usuário proprietário não pode ser alterado.'
                if not self.is_active:
                    errors['is_active'] = 'O acesso do proprietário não pode ser inativado.'
                if self.saas_status != self.SaaSStatus.ACTIVE:
                    errors['saas_status'] = 'O proprietário não pode ser suspenso pelo plano.'
                if errors:
                    raise ValidationError(errors)

    def save(self, *args, **kwargs):
        enforce_saas_limit = kwargs.pop('enforce_saas_limit', True)
        with transaction.atomic():
            previous = None
            if self.pk:
                previous = type(self).objects.select_for_update().filter(pk=self.pk).values(
                    'is_active', 'saas_status', 'company_id', 'user_id'
                ).first()
            consuming_before = bool(
                previous and previous['is_active']
                and previous['saas_status'] == self.SaaSStatus.ACTIVE
                and previous['company_id'] == self.company_id
                and previous['user_id'] == self.user_id
            )
            consuming_after = bool(
                self.is_active and self.saas_status == self.SaaSStatus.ACTIVE
                and self.user.is_active and self.user.can_login
            )
            if enforce_saas_limit and consuming_after and not consuming_before and self.company_id:
                from apps.saas.services import assert_resource_limit

                company = Company.objects.select_for_update().get(pk=self.company_id)
                assert_resource_limit(company, 'users.max', company_locked=True)
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_owner:
            raise ValidationError(
                {'is_owner': 'Transfira a propriedade antes de remover este acesso.'}
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f'{self.user} - {self.company}'


class UserBranchAccess(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branch_accesses',
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='user_accesses',
    )
    access_profile = models.ForeignKey(
        AccessProfile,
        on_delete=models.PROTECT,
        related_name='branch_user_accesses',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('branch__company__trade_name', 'branch__name', 'user__email')
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'branch'),
                name='companies_user_branch_access_unique',
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.branch_id
            and self.access_profile_id
            and self.access_profile.company_id != self.branch.company_id
        ):
            raise ValidationError(
                {'access_profile': 'O perfil deve pertencer a empresa da filial.'}
            )
        if self.is_active and self.user_id and self.branch_id:
            has_company_access = UserCompanyAccess.objects.filter(
                user_id=self.user_id,
                company_id=self.branch.company_id,
                is_active=True,
            ).exists()
            if not has_company_access:
                raise ValidationError(
                    {'branch': 'O usuário precisa de acesso ativo à empresa da filial.'}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user} - {self.branch}'


class UserPermissionBlock(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='permission_blocks')
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name='permission_blocks',
        blank=True, null=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='permission_blocks'
    )
    permission = models.ForeignKey(
        FunctionalPermission, on_delete=models.PROTECT, related_name='user_blocks'
    )
    reason = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_permission_blocks',
        blank=True, null=True,
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='revoked_permission_blocks',
        blank=True, null=True,
    )
    revoked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('company__trade_name', 'branch__name', 'user__email', 'permission__code')
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'branch', 'user', 'permission'),
                condition=Q(is_active=True, branch__isnull=False),
                name='companies_active_branch_user_permission_block_unique',
            ),
            models.UniqueConstraint(
                fields=('company', 'user', 'permission'),
                condition=Q(is_active=True, branch__isnull=True),
                name='companies_active_company_user_permission_block_unique',
            ),
        ]

    def clean(self):
        super().clean()
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            raise ValidationError({'branch': 'A filial deve pertencer a empresa do bloqueio.'})
        if self.permission_id and self.branch_id:
            from .rbac import PERMISSION_SCOPE_BRANCH, permission_scope

            if permission_scope(self.permission.code) != PERMISSION_SCOPE_BRANCH:
                raise ValidationError({'permission': 'Bloqueios por filial aceitam somente permissões de escopo Branch.'})
        if not self.is_active and not self.revoked_at:
            raise ValidationError({'revoked_at': 'Informe a data de revogacao.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        scope = self.branch or self.company
        return f'{self.user} - {scope} - {self.permission.code}'


class UserCommissionOverride(BaseModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='commission_overrides')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='commission_overrides'
    )
    receives_commission = models.BooleanField(default=True)
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_commission_overrides',
        blank=True, null=True,
    )
    archived_at = models.DateTimeField(blank=True, null=True, default=None)

    class Meta:
        ordering = ('branch__company__trade_name', 'branch__name', 'user__email')
        constraints = [
            models.UniqueConstraint(
                fields=('branch', 'user'), name='companies_user_commission_override_unique'
            ),
        ]

    @staticmethod
    def target_has_active_branch_access(branch_id, user_id):
        return UserBranchAccess.objects.filter(
            branch_id=branch_id,
            branch__status=Status.ACTIVE,
            branch__company__status=Status.ACTIVE,
            user_id=user_id,
            user__is_active=True,
            is_active=True,
            access_profile__status=Status.ACTIVE,
            branch__company__user_accesses__user_id=user_id,
            branch__company__user_accesses__is_active=True,
            branch__company__user_accesses__saas_status='ACTIVE',
        ).exists()

    def clean(self):
        super().clean()
        if self.commission_rate is not None and not (Decimal('0') <= self.commission_rate <= Decimal('100')):
            raise ValidationError({'commission_rate': 'A comissão do usuário deve estar entre 0 e 100.'})
        if (
            self.user_id
            and self.branch_id
            and not self.target_has_active_branch_access(self.branch_id, self.user_id)
        ):
            raise ValidationError({
                'user': 'O usuário deve estar ativo e possuir acesso e perfil ativos nesta filial.'
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.utils import timezone
        self.archived_at = timezone.now()
        self.save(update_fields=['archived_at', 'updated_at'])
        return None

    def __str__(self):
        return f'{self.user} - {self.branch}'
