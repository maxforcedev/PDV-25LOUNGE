from django.db import migrations


PERMISSIONS = (
    ('inventory.view_stock_kpis', 'inventory', 'Visualizar indicadores de estoque', 'Visualizar indicadores de estoque baixo e zerado.'),
    ('inventory.view_stock_costs', 'inventory', 'Visualizar custos de estoque', 'Visualizar custos e valor estimado do estoque.'),
    ('sales.apply_discount', 'sales', 'Aplicar desconto', 'Aplicar descontos em vendas.'),
    ('sales.create_consumption', 'sales', 'Criar consumacao', 'Criar consumacoes.'),
    ('sales.view_consumption', 'sales', 'Visualizar consumacao', 'Visualizar consumacoes.'),
    ('sales.cancel_consumption', 'sales', 'Cancelar consumacao', 'Cancelar consumacoes.'),
)


def add_permissions_to_system_profiles(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permissions = {}
    for code, module, label, description in PERMISSIONS:
        permission, _ = FunctionalPermission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'label': label,
                'description': description,
                'status': 'active',
            },
        )
        permissions[code] = permission

    for profile in AccessProfile.objects.filter(
        is_system=True, name__in=('Administrador', 'Gerente')
    ):
        profile.permissions.add(*permissions.values())
    for profile in AccessProfile.objects.filter(
        is_system=True, name='Operador de Estoque'
    ):
        profile.permissions.add(permissions['inventory.view_stock_kpis'])
    for profile in AccessProfile.objects.filter(
        is_system=True, name='Operador de Caixa'
    ):
        profile.permissions.add(
            permissions['sales.create_consumption'],
            permissions['sales.view_consumption'],
        )
        profile.permissions.remove(
            *FunctionalPermission.objects.filter(
                code__in=(
                    'sales.cancel',
                    'sales.apply_discount',
                    'sales.cancel_consumption',
                )
            )
        )


class Migration(migrations.Migration):
    dependencies = [('companies', '0011_nullable_company_access_profile')]

    operations = [
        migrations.RunPython(add_permissions_to_system_profiles, migrations.RunPython.noop)
    ]
