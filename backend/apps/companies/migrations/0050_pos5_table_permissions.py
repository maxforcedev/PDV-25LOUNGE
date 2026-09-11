from django.db import migrations


TABLE_PERMISSIONS = (
    ('tables.view', 'Visualizar mesas', 'Consultar mesas operacionais da filial.'),
    ('tables.open', 'Abrir mesas', 'Abrir mesas e criar sua comanda principal.'),
    ('tables.transfer', 'Transferir mesas', 'Transferir atendimento entre mesas.'),
    ('tables.transfer_items', 'Transferir itens de mesa', 'Transferir itens entre comandas de mesas.'),
    ('tables.merge', 'Agrupar mesas', 'Agrupar mesas operacionalmente.'),
    ('tables.close', 'Fechar mesas', 'Encerrar atendimentos de mesa quando resolvidos.'),
)


def add_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    for code, label, description in TABLE_PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                'module': 'tables', 'scope': 'BRANCH', 'label': label,
                'description': description, 'status': 'active',
            },
        )
        for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
            profile.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [('companies', '0049_customer_identity_constraints')]
    operations = [migrations.RunPython(add_permissions, migrations.RunPython.noop)]
