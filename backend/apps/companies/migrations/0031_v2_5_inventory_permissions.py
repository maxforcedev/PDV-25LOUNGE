from django.db import migrations


PERMISSIONS = (
    ('inventory.transfer.view', 'Visualizar transferencias', 'Visualizar transferencias e divergencias entre filiais autorizadas.'),
    ('inventory.transfer.create', 'Criar transferencias', 'Criar e cancelar rascunhos de transferencia da filial.'),
    ('inventory.transfer.dispatch', 'Despachar transferencias', 'Confirmar a baixa de origem no despacho.'),
    ('inventory.transfer.receive', 'Receber transferencias', 'Confirmar recebimentos fisicos na filial de destino.'),
    ('inventory.transfer.resolve', 'Resolver divergencias', 'Resolver divergencias de transferencia por evento fisico auditado.'),
    ('inventory.loss.record', 'Registrar perdas', 'Registrar perdas conhecidas com baixa e snapshots financeiros.'),
    ('inventory.count.perform', 'Realizar inventarios', 'Capturar e confirmar contagens fisicas de estoque.'),
    ('inventory.report.view', 'Visualizar estoque avancado', 'Consultar relatorios de transferencias, divergencias, perdas e inventarios.'),
)


def add_inventory_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    Profile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, label, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                'module': 'inventory',
                'label': label,
                'description': description,
                'status': 'active',
            },
        )
        permissions.append(permission)
    for profile in Profile.objects.filter(is_system=True, name='Administrador'):
        profile.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0030_v2_4_purchase_permissions')]
    operations = [
        migrations.RunPython(add_inventory_permissions, migrations.RunPython.noop),
    ]
