from django.db import migrations


PERMISSIONS = (
    ('commands.transfer', 'commands', 'Transferir mesa', 'Transferir uma comanda aberta entre mesas.'),
    ('commands.transfer_items', 'commands', 'Transferir itens', 'Transferir itens entre comandas abertas.'),
    ('commands.merge', 'commands', 'Mesclar comandas', 'Mesclar uma comanda aberta em outra.'),
    ('commands.split', 'commands', 'Dividir comanda', 'Criar uma nova comanda a partir de itens selecionados.'),
)


def add_permissions(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, module, label, description in PERMISSIONS:
        permission, _ = FunctionalPermission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'label': label,
                'description': description,
                'scope': 'BRANCH',
                'status': 'active',
            },
        )
        permissions.append(permission)
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(*permissions)


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0036_block_5_operation_defaults_and_limits'),
    ]

    operations = [
        migrations.RunPython(add_permissions, migrations.RunPython.noop),
    ]
