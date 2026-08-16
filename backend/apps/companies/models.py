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
