from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower

from apps.base.models import BaseModel

from .managers import UserManager
from .storage import PrivateProfileStorage, profile_photo_path, validate_profile_photo


class User(AbstractUser, BaseModel):
    class UserType(models.TextChoices):
        EMPLOYEE = 'employee', 'Funcionario'
        PROMOTER = 'promoter', 'Promoter'
        DJ = 'dj', 'DJ'
        ARTIST = 'artist', 'Artista'
        OTHER = 'other', 'Outro'

    username = None
    email = models.EmailField(blank=True, null=True)
    can_login = models.BooleanField(default=True, db_default=True)
    can_access_pos = models.BooleanField(default=False, db_default=False)
    pos_pin_hash = models.CharField(max_length=256, blank=True, default='', editable=False)
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.EMPLOYEE,
        db_default=UserType.EMPLOYEE,
    )
    archived_at = models.DateTimeField(blank=True, null=True, default=None)
    profile_photo = models.FileField(
        upload_to=profile_photo_path,
        storage=PrivateProfileStorage(),
        validators=[validate_profile_photo],
        blank=True,
        null=True,
    )
    birth_date = models.DateField(blank=True, null=True)
    cpf = models.CharField(max_length=14, blank=True, default='')
    zip_code = models.CharField(max_length=9, blank=True, default='')
    street = models.CharField(max_length=160, blank=True, default='')
    address_number = models.CharField(max_length=20, blank=True, default='')
    address_complement = models.CharField(max_length=100, blank=True, default='')
    neighborhood = models.CharField(max_length=100, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=2, blank=True, default='')

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        constraints = [
            models.UniqueConstraint(
                Lower('email'),
                condition=Q(email__isnull=False),
                name='accounts_user_email_ci_unique_not_null',
            ),
            models.CheckConstraint(
                condition=Q(can_login=False) | Q(email__isnull=False),
                name='accounts_user_login_requires_email',
            ),
        ]

    def clean(self):
        super().clean()
        self.email = self._normalize_email(self.email)
        if self.can_login and not self.email:
            raise ValidationError({'email': 'Usuarios com login precisam de e-mail.'})
        self._validate_owner_login_state()

    def save(self, *args, **kwargs):
        self.email = self._normalize_email(self.email)
        if self.can_login and not self.email:
            raise ValidationError({'email': 'Usuarios com login precisam de e-mail.'})
        if not self.can_login and self.has_usable_password():
            self.set_unusable_password()
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = tuple(set(update_fields) | {'password'})
        if self.pk:
            with transaction.atomic():
                previous = type(self).objects.select_for_update().filter(pk=self.pk).values(
                    'is_active', 'can_login'
                ).first()
                if (
                    previous
                    and self.is_active
                    and self.can_login
                    and (not previous['is_active'] or not previous['can_login'])
                ):
                    from apps.saas.services import validate_user_login_activation

                    validate_user_login_activation(self)
                self._validate_owner_login_state()
                return super().save(*args, **kwargs)
        self._validate_owner_login_state()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._validate_owner_removal()
        from django.utils import timezone
        self.archived_at = timezone.now()
        self.is_active = False
        self.save(update_fields=['archived_at', 'is_active', 'updated_at'])
        return None

    def _validate_owner_login_state(self):
        if not self.pk or self.is_active and self.can_login:
            return
        from apps.companies.models import UserCompanyAccess

        if UserCompanyAccess.objects.filter(user_id=self.pk, is_owner=True).exists():
            errors = {}
            if not self.is_active:
                errors['is_active'] = 'O proprietário de uma empresa deve permanecer ativo.'
            if not self.can_login:
                errors['can_login'] = 'O proprietário de uma empresa deve permanecer habilitado para login.'
            raise ValidationError(errors)

    def _validate_owner_removal(self):
        if not self.pk:
            return
        from apps.companies.models import UserCompanyAccess

        if UserCompanyAccess.objects.filter(user_id=self.pk, is_owner=True).exists():
            raise ValidationError(
                {'is_owner': 'Transfira a propriedade antes de remover este usuário.'}
            )

    @classmethod
    def _normalize_email(cls, value):
        value = (value or '').strip()
        return cls.objects.normalize_email(value).lower() if value else None

    def __str__(self):
        return self.email or self.get_full_name().strip() or f'Usuario {self.pk or "novo"}'
