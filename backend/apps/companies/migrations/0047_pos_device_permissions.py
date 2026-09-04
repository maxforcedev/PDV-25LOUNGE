from django.db import migrations


PERMISSIONS = (
    ('pos_devices.view', 'pos_devices', 'COMPANY', 'Visualizar dispositivos POS', 'Visualizar dispositivos POS autorizados da empresa.'),
    ('pos_devices.manage', 'pos_devices', 'COMPANY', 'Administrar dispositivos POS', 'Bloquear, revogar e configurar dispositivos POS da empresa.'),
)


def add_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    created = []
    for code, module, scope, label, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'scope': scope,
                'label': label,
                'description': description,
                'status': 'active',
            },
        )
        created.append(permission)
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(*created)


class Migration(migrations.Migration):
    dependencies = [('companies', '0046_branch_licensing_code')]
    operations = [migrations.RunPython(add_permissions, migrations.RunPython.noop)]
