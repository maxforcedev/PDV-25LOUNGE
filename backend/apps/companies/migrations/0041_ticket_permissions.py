from django.db import migrations


PERMISSIONS = [
    ('tickets.view', 'tickets', 'BRANCH', 'Visualizar tickets', 'Visualizar tickets emitidos na filial.'),
    ('tickets.reprint', 'tickets', 'BRANCH', 'Reimprimir tickets', 'Registrar e solicitar reimpressão de tickets.'),
]


def add_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, module, scope, label, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(code=code, defaults={'module': module, 'scope': scope, 'label': label, 'description': description, 'status': 'active'})
        permissions.append(permission)
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0040_customer_and_permissions')]
    operations = [migrations.RunPython(add_permissions, migrations.RunPython.noop)]
