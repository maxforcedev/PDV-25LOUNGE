from django.db import migrations


PERMISSIONS = (
    (
        'promotions.view',
        'promotions',
        'Visualizar promocoes',
        'Visualizar promocoes.',
    ),
    (
        'promotions.change',
        'promotions',
        'Configurar promocoes',
        'Criar, editar e alterar o status de promocoes.',
    ),
)


def add_promotions_permissions(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permissions = {}
    for code, module, label, description in PERMISSIONS:
        permission, _ = FunctionalPermission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'label': label,
                'description': description,
                'status': 'active',
            },
        )
        permissions[code] = permission

    for profile in AccessProfile.objects.filter(
        is_system=True, name__in=('Administrador', 'Gerente')
    ).iterator():
        profile.permissions.add(*permissions.values())
    for profile in AccessProfile.objects.filter(
        is_system=True, name='Operador de Caixa'
    ).iterator():
        profile.permissions.add(permissions['promotions.view'])


class Migration(migrations.Migration):
    dependencies = [('companies', '0014_reports_permissions')]

    operations = [
        migrations.RunPython(add_promotions_permissions, migrations.RunPython.noop),
    ]
