from django.db import migrations


def add_table_manage_permission(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permission, _ = Permission.objects.update_or_create(
        code='tables.manage',
        defaults={
            'module': 'tables', 'scope': 'BRANCH', 'label': 'Administrar mesas',
            'description': 'Criar, editar, gerar intervalo e excluir mesas da filial.',
            'status': 'active',
        },
    )
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [('companies', '0050_pos5_table_permissions')]
    operations = [migrations.RunPython(add_table_manage_permission, migrations.RunPython.noop)]
