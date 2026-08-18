from django.db import migrations


PERMISSION = (
    'sales.apply_item_discount',
    'sales',
    'Aplicar desconto por item',
    'Aplicar desconto manual em itens de venda com permissao independente do desconto na conta.',
)


def add_permission(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    code, module, label, description = PERMISSION
    permission, _ = FunctionalPermission.objects.update_or_create(
        code=code,
        defaults={
            'module': module,
            'label': label,
            'description': description,
            'status': 'active',
        },
    )
    for profile in AccessProfile.objects.filter(is_system=True, name='Administrador'):
        profile.permissions.add(permission)


def remove_permission(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    FunctionalPermission.objects.filter(code=PERMISSION[0]).delete()


class Migration(migrations.Migration):
    dependencies = [('companies', '0022_reduce_manager_permissions')]
    operations = [migrations.RunPython(add_permission, remove_permission)]
