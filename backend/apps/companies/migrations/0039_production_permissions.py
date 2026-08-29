from django.db import migrations


PERMISSIONS = [
    ('production.view', 'production', 'BRANCH', 'Visualizar produção', 'Visualizar jobs de produção da filial.'),
    ('printers.manage', 'production', 'BRANCH', 'Administrar impressoras', 'Cadastrar e configurar dispositivos de impressão da filial.'),
    ('print_jobs.view', 'production', 'BRANCH', 'Visualizar fila de impressão', 'Visualizar fila e detalhes de impressão da filial.'),
    ('print_jobs.retry', 'production', 'BRANCH', 'Reprocessar impressão', 'Solicitar novo processamento técnico ou despacho manual auditado.'),
    ('print_jobs.reprint', 'production', 'BRANCH', 'Reimprimir', 'Criar uma reimpressão explícita e auditada.'),
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
    dependencies = [('companies', '0038_command_payment_permissions')]
    operations = [migrations.RunPython(add_permissions, migrations.RunPython.noop)]
