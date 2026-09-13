from django.db import migrations


def add_table_set_customer_permission(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permission, _ = Permission.objects.update_or_create(
        code='tables.set_customer',
        defaults={
            'module': 'tables', 'scope': 'BRANCH', 'label': 'Alterar cliente da mesa',
            'description': 'Definir ou remover o cliente do atendimento de mesa.',
            'status': 'active',
        },
    )
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [('companies', '0052_table_operation_permissions')]
    operations = [migrations.RunPython(add_table_set_customer_permission, migrations.RunPython.noop)]
