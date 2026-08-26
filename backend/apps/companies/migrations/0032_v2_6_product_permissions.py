from django.db import migrations


PERMISSIONS = (
    ('products.configure_branch', 'Configurar produto por filial', 'Configurar disponibilidade, canais, precos e copiar configuracoes entre filiais.'),
    ('products.configure_fraction', 'Configurar produto fracionavel', 'Configurar e ativar rastreamento exato de conteudo.'),
    ('products.configure_destinations', 'Configurar destinos de producao', 'Configurar destinos e vinculos de produtos na filial.'),
    ('products.duplicate', 'Duplicar produtos', 'Duplicar produtos e relacoes selecionadas sem copiar historico ou estoque.'),
)


def add_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    Profile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, label, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                'module': 'products', 'label': label,
                'description': description, 'status': 'active',
            },
        )
        permissions.append(permission)
    for profile in Profile.objects.filter(is_system=True, name__in=(
        'Administrador', 'Operador de Estoque',
    )):
        profile.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0031_v2_5_inventory_permissions')]
    operations = [migrations.RunPython(add_permissions, migrations.RunPython.noop)]
