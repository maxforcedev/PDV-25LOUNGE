from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.base.audit import audit_log
from apps.saas.models import PlatformPermission, PlatformRole, PlatformUserAccess
from apps.saas.services import ensure_capability_catalog, get_global_settings


PERMISSIONS = (
    ('platform.access', 'Acessar Platform Admin'),
    ('platform.dashboard.view', 'Visualizar dashboard SaaS'),
    ('platform.tenants.manage', 'Administrar tenants'),
    ('platform.plans.manage', 'Administrar planos e entitlements'),
    ('platform.billing.manage', 'Administrar pagamentos'),
    ('platform.settings.manage', 'Administrar configuracoes globais'),
    ('platform.support.manage', 'Administrar sessoes de suporte'),
)


class Command(BaseCommand):
    help = 'Garante, de forma idempotente, o primeiro Super Admin da plataforma.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        try:
            user = User.objects.select_for_update().get(email__iexact=email)
        except User.DoesNotExist as error:
            raise CommandError('Usuario nao encontrado; crie a identidade explicitamente primeiro.') from error
        if not user.is_active or not user.can_login or not user.has_usable_password():
            raise CommandError('O usuario precisa estar ativo, habilitado e possuir senha utilizavel.')

        permissions = []
        for code, label in PERMISSIONS:
            permission, _ = PlatformPermission.objects.update_or_create(
                code=code, defaults={'label': label}
            )
            permissions.append(permission)
        role, _ = PlatformRole.objects.get_or_create(
            code='super-admin',
            defaults={'name': 'Super Admin', 'is_system': True},
        )
        role.permissions.set(permissions)
        access, created = PlatformUserAccess.objects.get_or_create(
            user=user, defaults={'role': role, 'is_active': True}
        )
        changed = created or access.role_id != role.pk or not access.is_active
        if not created and changed:
            access.role = role
            access.is_active = True
            access.save(update_fields=('role', 'is_active', 'updated_at'))
        ensure_capability_catalog()
        get_global_settings()
        if changed:
            audit_log(
                actor=user, action='platform.admin.bootstrap', obj=access,
                after={'role': role.code, 'is_active': True},
                metadata={'source': 'management_command'},
            )
        self.stdout.write(
            self.style.SUCCESS(
                f'Platform Super Admin {"criado/atualizado" if changed else "ja configurado"}: {email}'
            )
        )
