from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.conf import settings
from django.core.exceptions import ValidationError

from apps.base.models import BaseModel

from .validators import normalize_cnpj, validate_cnpj


class Status(models.TextChoices):
    ACTIVE = 'active', 'Ativo'
    INACTIVE = 'inactive', 'Inativo'


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
            models.UniqueConstraint(
                Lower('trade_name'),
                name='companies_company_trade_name_ci_unique',
            ),
            models.UniqueConstraint(
                Lower('legal_name'),
                name='companies_company_legal_name_ci_unique',
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
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'Configurações de {self.branch}'


class FunctionalPermission(BaseModel):
    code = models.CharField(max_length=100, unique=True)
    module = models.CharField(max_length=50)
    label = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('module', 'code')

    def __str__(self):
        return self.label


class AccessProfile(BaseModel):
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

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class UserCompanyAccess(BaseModel):
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

    class Meta:
        ordering = ('company__trade_name', 'user__email')
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'company'),
                name='companies_user_company_access_unique',
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

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

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
                    {'branch': 'O usuario precisa de acesso ativo a empresa da filial.'}
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
            from .rbac import OPERATING_PERMISSION_CODES

            if self.permission.code not in OPERATING_PERMISSION_CODES:
                raise ValidationError({'permission': 'Bloqueios por filial aceitam somente permissoes operacionais.'})
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
            branch__company__user_accesses__access_profile__status=Status.ACTIVE,
        ).exists()

    def clean(self):
        super().clean()
        if self.commission_rate is not None and not (Decimal('0') <= self.commission_rate <= Decimal('100')):
            raise ValidationError({'commission_rate': 'A comissão do usuario deve estar entre 0 e 100.'})
        if (
            self.user_id
            and self.branch_id
            and not self.target_has_active_branch_access(self.branch_id, self.user_id)
        ):
            raise ValidationError({
                'user': 'O usuario deve estar ativo e possuir acesso e perfil ativos nesta filial.'
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user} - {self.branch}'
