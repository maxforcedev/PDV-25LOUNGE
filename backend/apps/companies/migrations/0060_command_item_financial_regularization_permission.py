from django.db import migrations


def add_permission(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permission, _ = Permission.objects.update_or_create(code='commands.regularize_item_financial_snapshots', defaults={'module': 'commands', 'scope': 'BRANCH', 'label': 'Regularizar itens históricos de comanda', 'description': 'Registrar condições financeiras comprovadas de itens históricos bloqueados.', 'status': 'active'})
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [('companies', '0059_command_service_fee_regularization_permission')]
    operations = [migrations.RunPython(add_permission, migrations.RunPython.noop)]
