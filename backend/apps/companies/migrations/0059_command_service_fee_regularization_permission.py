from django.db import migrations


def add_command_service_fee_regularization_permission(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permission, _ = Permission.objects.update_or_create(
        code='commands.regularize_service_fee_rate',
        defaults={
            'module': 'commands',
            'scope': 'BRANCH',
            'label': 'Regularizar taxa histórica de comanda',
            'description': 'Registrar a taxa histórica comprovada de uma comanda bloqueada.',
            'status': 'active',
        },
    )
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [('companies', '0058_branchsettings_commercial_module_switches')]
    operations = [migrations.RunPython(add_command_service_fee_regularization_permission, migrations.RunPython.noop)]
