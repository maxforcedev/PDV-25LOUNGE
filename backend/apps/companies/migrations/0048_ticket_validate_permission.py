from django.db import migrations


def add_permission(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permission, _ = Permission.objects.update_or_create(
        code='tickets.validate',
        defaults={
            'module': 'tickets', 'scope': 'BRANCH', 'label': 'Validar tickets',
            'description': 'Registrar retirada ou entrega de itens emitidos por ticket na filial autorizada.',
            'status': 'active',
        },
    )
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [('companies', '0047_pos_device_permissions')]
    operations = [migrations.RunPython(add_permission, migrations.RunPython.noop)]
