from django.db import migrations


PERMISSION_TEXTS = {
    'branches.change_settings': ('Alterar configurações da filial', 'Alterar regras operacionais, taxa de serviço, comissão e custo fixo.'),
    'users.view': ('Visualizar usuários', 'Visualizar usuários autorizados.'),
    'users.add': ('Cadastrar usuários', 'Cadastrar usuários e seus acessos.'),
    'users.change': ('Editar usuários', 'Editar usuários e seus acessos.'),
    'users.change_status': ('Alterar status de usuários', 'Ativar e inativar usuários.'),
    'user_permission_blocks.view': ('Visualizar bloqueios individuais', 'Visualizar permissões bloqueadas por usuário.'),
    'user_permission_blocks.change': ('Alterar bloqueios individuais', 'Criar e revogar bloqueios individuais de permissões.'),
    'access_profiles.change': ('Editar perfis', 'Editar perfis e permissões.'),
    'products.view': ('Visualizar produtos', 'Visualizar o catálogo de produtos.'),
    'products.configure_composition': ('Configurar composição', 'Configurar a composição de produtos.'),
    'products.change_price': ('Alterar preço padrão', 'Alterar preço padrão de produtos.'),
    'branch_prices.change': ('Alterar preços por filial', 'Alterar preços específicos de produtos por filial.'),
    'inventory.move': ('Movimentar estoque', 'Registrar movimentações de estoque.'),
    'inventory.exit': ('Registrar saída', 'Registrar saídas de estoque.'),
    'inventory.adjust': ('Ajustar estoque', 'Registrar inventário e correção de saldo.'),
    'inventory.change_minimum': ('Alterar estoque mínimo', 'Configurar estoque mínimo.'),
    'inventory.view_history': ('Visualizar histórico', 'Visualizar histórico de estoque.'),
    'cash_registers.administer_others': ('Administrar caixas de outros', 'Operar sessões abertas por outros usuários.'),
    'sales.waive_service_fee': ('Retirar taxa de serviço', 'Retirar taxa de serviço com permissão ou autorização pontual.'),
    'sales.apply_item_discount': ('Aplicar desconto por item', 'Aplicar desconto manual em itens de venda, independente do desconto na conta.'),
    'sales.create_consumption': ('Criar consumação', 'Criar consumações.'),
    'sales.view_consumption': ('Visualizar consumação', 'Visualizar consumações.'),
    'sales.cancel_consumption': ('Cancelar consumação', 'Cancelar consumações.'),
    'promotions.view': ('Visualizar promoções', 'Visualizar promoções.'),
    'promotions.change': ('Configurar promoções', 'Criar, editar e alterar o status de promoções.'),
    'reports.view_sales': ('Visualizar relatório de vendas', 'Visualizar relatório operacional de vendas.'),
    'reports.view_consumptions': ('Visualizar relatório de consumações', 'Visualizar relatório operacional de consumações.'),
    'reports.view_cash': ('Visualizar relatório de caixa', 'Visualizar relatório operacional de caixa.'),
    'reports.view_withdrawals': ('Visualizar relatório de sangrias', 'Visualizar relatório operacional de sangrias.'),
    'reports.view_inventory': ('Visualizar relatório de estoque', 'Visualizar relatório de movimentações de estoque.'),
    'reports.view_stock_consumption': ('Visualizar consumo físico', 'Visualizar produtos e insumos consumidos.'),
    'reports.view_prices': ('Visualizar preços', 'Visualizar comparativo de preços por filial.'),
    'reports.export': ('Exportar relatórios', 'Exportar relatórios operacionais.'),
    'commissions.view': ('Visualizar comissões', 'Visualizar valores e relatórios de comissão.'),
    'commissions.change_branch_default': ('Alterar comissão da filial', 'Alterar percentual padrão de comissão da filial.'),
    'commissions.change_profile': ('Alterar comissão do perfil', 'Alterar regra de comissão em perfis de acesso.'),
    'commissions.change_user_override': ('Alterar comissão individual', 'Alterar configuração individual de comissão por usuário.'),
}


def localize_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    for code, (label, description) in PERMISSION_TEXTS.items():
        Permission.objects.filter(code=code).update(
            label=label,
            description=description,
        )


class Migration(migrations.Migration):
    dependencies = [('companies', '0024_sync_sprint_12_4_permissions')]
    operations = [migrations.RunPython(localize_permissions, migrations.RunPython.noop)]
