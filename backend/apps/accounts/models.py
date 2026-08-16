from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.base.models import BaseModel

from .managers import UserManager


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
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.EMPLOYEE,
        db_default=UserType.EMPLOYEE,
    )

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

    def save(self, *args, **kwargs):
        self.email = self._normalize_email(self.email)
        if self.can_login and not self.email:
            raise ValidationError({'email': 'Usuarios com login precisam de e-mail.'})
        if not self.can_login and self.has_usable_password():
            self.set_unusable_password()
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = tuple(set(update_fields) | {'password'})
        return super().save(*args, **kwargs)

    @classmethod
    def _normalize_email(cls, value):
        value = (value or '').strip()
        return cls.objects.normalize_email(value).lower() if value else None

    def __str__(self):
        return self.email or self.get_full_name().strip() or f'Usuario {self.pk or "novo"}'
