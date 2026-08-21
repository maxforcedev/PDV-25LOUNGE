from django.db import migrations


PERMISSIONS = (
    ('audit_logs.view', 'audit_logs', 'Visualizar auditoria', 'Consultar logs de auditoria.'),
    ('branch_prices.change', 'products', 'Alterar preços por filial', 'Alterar preços específicos de produtos por filial.'),
    ('branches.change_settings', 'companies', 'Alterar configurações da filial', 'Alterar regras operacionais, taxa de serviço, comissão e custo fixo.'),
    ('commissions.change_branch_default', 'commissions', 'Alterar comissão da filial', 'Alterar percentual padrão de comissão da filial.'),
    ('commissions.change_profile', 'commissions', 'Alterar comissão do perfil', 'Alterar regra de comissão em perfis de acesso.'),
    ('commissions.change_user_override', 'commissions', 'Alterar comissão individual', 'Alterar configuração individual de comissão por usuário.'),
    ('commissions.view', 'commissions', 'Visualizar comissões', 'Visualizar valores e relatórios de comissão.'),
    ('reports.view_stock_consumption', 'reports', 'Visualizar consumo físico', 'Visualizar produtos e insumos consumidos.'),
    ('sales.waive_service_fee', 'sales', 'Retirar taxa de serviço', 'Retirar taxa de serviço com permissão ou autorização pontual.'),
    ('user_permission_blocks.change', 'accounts', 'Alterar bloqueios individuais', 'Criar e revogar bloqueios individuais de permissões.'),
    ('user_permission_blocks.view', 'accounts', 'Visualizar bloqueios individuais', 'Visualizar permissões bloqueadas por usuário.'),
)

PROFILE_ADDITIONS = {
    'Gerente': {
        'commissions.view',
        'reports.view_stock_consumption',
        'sales.waive_service_fee',
    },
    'Operador de Caixa': {'sales.waive_service_fee'},
}


def sync_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    Profile = apps.get_model('companies', 'AccessProfile')

    permissions = {}
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
        permissions[code] = permission

    new_permissions = list(permissions.values())
    for profile in Profile.objects.filter(is_system=True, name='Administrador'):
        profile.permissions.add(*new_permissions)

    for profile_name, codes in PROFILE_ADDITIONS.items():
        profile_permissions = [permissions[code] for code in codes]
        for profile in Profile.objects.filter(is_system=True, name=profile_name):
            profile.permissions.add(*profile_permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0023_sales_item_discount_permission')]
    operations = [migrations.RunPython(sync_permissions, migrations.RunPython.noop)]
