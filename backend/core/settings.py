import os
from pathlib import Path

from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / '.env')


_MISSING = object()


def env_or_file(name, default=_MISSING):
    """Read a value directly or from Docker Secrets without exposing it."""
    value = os.environ.get(name)
    file_path = os.environ.get(f'{name}_FILE')
    if value is not None and file_path is not None:
        raise ImproperlyConfigured(
            f'Set either {name} or {name}_FILE, not both.'
        )
    if file_path is not None:
        try:
            value = Path(file_path).read_text(encoding='utf-8').rstrip('\r\n')
        except OSError as error:
            raise ImproperlyConfigured(
                f'Could not read {name}_FILE.'
            ) from error
    if value is not None:
        if not value:
            raise ImproperlyConfigured(f'{name} cannot be empty.')
        return value
    if default is not _MISSING:
        return default
    raise ImproperlyConfigured(f'{name} or {name}_FILE is required.')


SECRET_KEY = env_or_file('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])

TRUST_PROXY_HEADERS = env.bool('TRUST_PROXY_HEADERS', default=not DEBUG)
SECURE_PROXY_SSL_HEADER = (
    ('HTTP_X_FORWARDED_PROTO', 'https') if TRUST_PROXY_HEADERS else None
)
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=not DEBUG)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=not DEBUG)
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    'SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False
)
SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=False)
SECURE_CONTENT_TYPE_NOSNIFF = env.bool(
    'SECURE_CONTENT_TYPE_NOSNIFF', default=True
)


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'apps.base',
    'apps.accounts',
    'apps.companies',
    'apps.products',
    'apps.inventory',
    'apps.cash',
    'apps.sales',
    'apps.reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.base.audit.AuditRequestContextMiddleware',
    'apps.accounts.middleware.CanLoginMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


DATABASE_URL = env_or_file('DATABASE_URL')
DATABASES = {'default': environ.Env.db_url_config(DATABASE_URL)}
database_password = env_or_file('POSTGRES_PASSWORD', default=None)
if database_password is not None:
    DATABASES['default']['PASSWORD'] = database_password
if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
    DATABASES['default'].setdefault('OPTIONS', {})['connect_timeout'] = env.int(
        'DATABASE_CONNECT_TIMEOUT', default=3
    )


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = env('LANGUAGE_CODE', default='pt-br')

TIME_ZONE = env('TIME_ZONE', default='America/Sao_Paulo')

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'
# USERNAME_FIELD is protected by a conditional case-insensitive database constraint.
SILENCED_SYSTEM_CHECKS = ['auth.E003']

REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'apps.base.exceptions.api_exception_handler',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.base.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'apps.base.pagination.StandardPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/minute',
    },
}

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (
    *default_headers,
    'x-branch-id',
    'x-correlation-id',
    'x-request-id',
)
CORS_EXPOSE_HEADERS = ['X-CSRFToken', 'X-Request-ID', 'X-Correlation-ID']


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': env(
            'EMAIL_BACKEND',
            default='django.core.mail.backends.console.EmailBackend',
        ),
    },
}
