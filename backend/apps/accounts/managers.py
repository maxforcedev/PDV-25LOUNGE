from django.contrib.auth.base_user import BaseUserManager
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models, transaction


class UserQuerySet(models.QuerySet):
    LOGIN_LIMIT_FIELDS = {'is_active', 'can_login'}

    def _supports_company_owner(self):
        try:
            relation = self.model._meta.get_field('company_accesses')
            relation.related_model._meta.get_field('is_owner')
        except FieldDoesNotExist:
            return False
        return True

    def update(self, **kwargs):
        disables_login = (
            'is_active' in kwargs and kwargs['is_active'] is not True
        ) or (
            'can_login' in kwargs and kwargs['can_login'] is not True
        )
        enables_login = kwargs.get('is_active') is True or kwargs.get('can_login') is True
        if enables_login and self._supports_company_owner():
            from apps.saas.services import validate_user_login_activation

            with transaction.atomic(using=self.db):
                users = list(self.select_for_update())
                for user in users:
                    target_active = kwargs.get('is_active', user.is_active)
                    target_can_login = kwargs.get('can_login', user.can_login)
                    if target_active and target_can_login and (not user.is_active or not user.can_login):
                        user.is_active = target_active
                        user.can_login = target_can_login
                        validate_user_login_activation(user)
                return super().update(**kwargs)
        if disables_login and self._supports_company_owner():
            with transaction.atomic(using=self.db):
                list(self.select_for_update().values_list('pk', flat=True))
                if self.filter(company_accesses__is_owner=True).exists():
                    raise ValidationError(
                        {'is_owner': 'Transfira a propriedade antes de desativar este usuário.'}
                    )
                return super().update(**kwargs)
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if self.LOGIN_LIMIT_FIELDS.intersection(fields):
            raise ValidationError({
                'limit': 'Ativacoes em massa devem usar save/service para validar users.max.'
            })
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def delete(self):
        if self._supports_company_owner():
            from django.utils import timezone

            with transaction.atomic(using=self.db):
                list(self.select_for_update().values_list('pk', flat=True))
                if self.filter(company_accesses__is_owner=True).exists():
                    raise ValidationError(
                        {'is_owner': 'Transfira a propriedade antes de remover este usuário.'}
                    )
                count = super().update(is_active=False, archived_at=timezone.now())
                return count, {self.model._meta.label: count}
        return super().delete()


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    use_in_migrations = True

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)

    def _create_user(self, email, password, **extra_fields):
        can_login = extra_fields.get('can_login', True)
        email = (email or '').strip()
        if can_login and not email:
            raise ValueError('The email address is required for users who can log in.')
        email = self.normalize_email(email).lower() if email else None
        user = self.model(email=email, **extra_fields)
        if can_login:
            if not password:
                raise ValueError('A password is required for users who can log in.')
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('can_login', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('A superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('A superuser must have is_superuser=True.')
        if extra_fields.get('can_login') is not True:
            raise ValueError('A superuser must have can_login=True.')
        if not email or not password:
            raise ValueError('A superuser must have an email address and password.')

        return self._create_user(email, password, **extra_fields)
