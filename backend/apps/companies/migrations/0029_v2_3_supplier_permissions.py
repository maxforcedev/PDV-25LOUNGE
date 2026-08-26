from django.db import migrations


PERMISSIONS = (
    (
        'suppliers.view', 'suppliers', 'Visualizar fornecedores',
        'Visualizar fornecedores e suas relações com produtos.',
    ),
    (
        'suppliers.change', 'suppliers', 'Administrar fornecedores',
        'Criar, editar e alterar o status de fornecedores, relações e apresentações.',
    ),
)


def add_supplier_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    Profile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, module, label, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'label': label,
                'description': description,
                'status': 'active',
            },
        )
        permissions.append(permission)
    for profile in Profile.objects.filter(is_system=True, name='Administrador'):
        profile.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0028_usercompanyaccess_saas_status_and_more')]
    operations = [
        migrations.RunPython(add_supplier_permissions, migrations.RunPython.noop),
    ]
