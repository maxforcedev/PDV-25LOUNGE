from django.db import migrations


NEW_PERMISSIONS = (
    ('products.change_cost', 'products', 'Alterar custo de produto', 'Alterar custo cadastral de produtos.'),
    ('products.change_price', 'products', 'Alterar preco padrao', 'Alterar preco padrao de produtos.'),
    ('categories.view', 'products', 'Visualizar categorias', 'Visualizar categorias de produtos.'),
    ('categories.add', 'products', 'Cadastrar categorias', 'Cadastrar categorias de produtos.'),
    ('categories.change', 'products', 'Editar categorias', 'Editar categorias de produtos.'),
    ('categories.change_status', 'products', 'Alterar status de categorias', 'Ativar e inativar categorias.'),
    ('inventory.entry', 'inventory', 'Registrar entrada', 'Registrar entradas individuais ou em grupo.'),
    ('inventory.exit', 'inventory', 'Registrar saida', 'Registrar saidas de estoque.'),
    ('inventory.adjust', 'inventory', 'Ajustar estoque', 'Registrar inventario e correcao de saldo.'),
    ('inventory.regularize', 'inventory', 'Regularizar negativos', 'Regularizar explicitamente saldos negativos.'),
    ('cash_registers.add', 'cash_registers', 'Cadastrar caixa', 'Cadastrar caixas na filial.'),
    ('cash_registers.change', 'cash_registers', 'Editar caixa', 'Editar caixas da filial.'),
    ('cash_registers.change_status', 'cash_registers', 'Alterar status de caixa', 'Ativar e inativar caixas.'),
    ('cash_registers.administer_others', 'cash_registers', 'Administrar caixas de outros', 'Operar sessoes abertas por outros usuarios.'),
    ('dashboard.view', 'reports', 'Visualizar Dashboard', 'Visualizar indicadores executivos autorizados.'),
    ('reports.view_products', 'reports', 'Visualizar performance de produtos', 'Visualizar produtos e categorias vendidos.'),
    ('reports.view_receipts', 'reports', 'Visualizar recebimentos', 'Visualizar recebimentos por forma de pagamento.'),
    ('reports.view_team', 'reports', 'Visualizar equipe', 'Visualizar desempenho de operadores e atendentes.'),
    ('reports.view_discounts', 'reports', 'Visualizar descontos', 'Visualizar descontos manuais e promocionais.'),
    ('reports.view_cancellations', 'reports', 'Visualizar cancelamentos', 'Visualizar cancelamentos e estornos.'),
    ('reports.view_prices', 'reports', 'Visualizar precos', 'Visualizar comparativo de precos por filial.'),
)


MANAGER_CODES = {
    'companies.view', 'branches.view', 'users.view', 'access_profiles.view',
    'products.view', 'products.add', 'products.change', 'products.change_status',
    'products.configure_composition', 'products.change_cost', 'products.change_price',
    'categories.view', 'categories.add', 'categories.change', 'categories.change_status',
    'branch_prices.change', 'inventory.view', 'inventory.move', 'inventory.entry',
    'inventory.exit', 'inventory.adjust', 'inventory.regularize',
    'inventory.change_minimum', 'inventory.view_history', 'inventory.view_stock_kpis',
    'inventory.view_stock_costs', 'cash_registers.view', 'cash_registers.open',
    'cash_registers.manual_entry', 'cash_registers.withdraw', 'cash_registers.close',
    'sales.create', 'sales.view', 'sales.cancel', 'sales.apply_discount',
    'sales.waive_service_fee', 'sales.create_consumption', 'sales.view_consumption',
    'sales.cancel_consumption', 'payment_methods.view', 'payment_methods.change',
    'promotions.view', 'promotions.change', 'dashboard.view', 'reports.view_sales',
    'reports.view_consumptions', 'reports.view_cash', 'reports.view_withdrawals',
    'reports.view_inventory', 'reports.view_operational_result',
    'reports.view_stock_consumption', 'reports.view_products', 'reports.view_receipts',
    'reports.view_team', 'reports.view_discounts', 'reports.view_cancellations',
    'reports.view_prices', 'reports.export', 'commissions.view',
}


def forwards(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    Profile = apps.get_model('companies', 'AccessProfile')
    Branch = apps.get_model('companies', 'Branch')

    for code, module, label, description in NEW_PERMISSIONS:
        Permission.objects.update_or_create(
            code=code,
            defaults={
                'module': module, 'label': label, 'description': description,
                'status': 'active',
            },
        )

    all_active = Permission.objects.filter(status='active')
    for profile in Profile.objects.filter(is_system=True, name='Administrador'):
        profile.permissions.set(all_active)
    manager_permissions = Permission.objects.filter(code__in=MANAGER_CODES, status='active')
    for profile in Profile.objects.filter(is_system=True, name='Gerente'):
        profile.permissions.set(manager_permissions)
        profile.description = 'Acesso gerencial operacional sem capacidades sensiveis de seguranca.'
        profile.save(update_fields=('description', 'updated_at'))

    inheritance = {
        'products.view': ('categories.view',),
        'products.add': ('categories.add',),
        'products.change': ('categories.change', 'products.change_cost', 'products.change_price'),
        'products.change_status': ('categories.change_status',),
        'inventory.move': ('inventory.entry', 'inventory.exit', 'inventory.adjust', 'inventory.regularize'),
        'branches.change': ('cash_registers.add', 'cash_registers.change', 'cash_registers.change_status'),
    }
    system_names = {'Administrador', 'Gerente'}
    for profile in Profile.objects.exclude(is_system=True, name__in=system_names).prefetch_related('permissions'):
        current = set(profile.permissions.values_list('code', flat=True))
        additions = {new for old, values in inheritance.items() if old in current for new in values}
        if any(code.startswith('reports.') for code in current):
            additions.add('dashboard.view')
        if additions:
            profile.permissions.add(*Permission.objects.filter(code__in=additions))

    Branch.objects.filter(is_matrix=True, address={}).update(address_pending=True)


class Migration(migrations.Migration):
    dependencies = [('companies', '0020_branch_address_pending')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
