from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

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
