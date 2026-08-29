from django.db import migrations

PERMISSIONS = (
    ('commands.payments.view', 'commands', 'Ver pagamentos de comanda', 'Consultar o extrato de pagamentos parciais da comanda.'),
    ('commands.payments.record', 'commands', 'Registrar pagamento parcial', 'Registrar um pagamento parcial em comanda aberta.'),
    ('commands.payments.reverse', 'commands', 'Estornar pagamento parcial', 'Estornar um pagamento parcial de comanda aberta.'),
)

def add_permissions(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, module, label, description in PERMISSIONS:
        permission, _ = FunctionalPermission.objects.update_or_create(code=code, defaults={'module': module, 'label': label, 'description': description, 'scope': 'BRANCH', 'status': 'active'})
        permissions.append(permission)
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(*permissions)

class Migration(migrations.Migration):
    dependencies = [('companies', '0037_command_operation_permissions')]
    operations = [migrations.RunPython(add_permissions, migrations.RunPython.noop)]
