PERMISSION_CATALOG = (
    ('companies.view', 'companies', 'Visualizar empresas', 'Visualizar empresas autorizadas.'),
    ('companies.change', 'companies', 'Editar empresas', 'Editar e alterar o status de empresas.'),
    ('branches.view', 'companies', 'Visualizar filiais', 'Visualizar filiais autorizadas.'),
    ('branches.add', 'companies', 'Cadastrar filiais', 'Cadastrar filiais em empresas autorizadas.'),
    ('branches.change', 'companies', 'Editar filiais', 'Editar e alterar o status de filiais.'),
    ('users.view', 'accounts', 'Visualizar usuarios', 'Visualizar usuarios autorizados.'),
    ('users.add', 'accounts', 'Cadastrar usuarios', 'Cadastrar usuarios e seus acessos.'),
    ('users.change', 'accounts', 'Editar usuarios', 'Editar usuarios e seus acessos.'),
    ('users.change_status', 'accounts', 'Alterar status de usuarios', 'Ativar e inativar usuarios.'),
    ('access_profiles.view', 'accounts', 'Visualizar perfis', 'Visualizar perfis de acesso.'),
    ('access_profiles.add', 'accounts', 'Cadastrar perfis', 'Cadastrar perfis de acesso.'),
    ('access_profiles.change', 'accounts', 'Editar perfis', 'Editar perfis e permissoes.'),
    ('access_profiles.change_status', 'accounts', 'Alterar status de perfis', 'Ativar e inativar perfis.'),
    ('products.view', 'products', 'Visualizar produtos', 'Visualizar o catalogo de produtos.'),
    ('products.add', 'products', 'Cadastrar produtos', 'Cadastrar produtos.'),
    ('products.change', 'products', 'Editar produtos', 'Editar produtos.'),
    ('products.change_status', 'products', 'Alterar status de produtos', 'Ativar e inativar produtos.'),
    ('products.configure_composition', 'products', 'Configurar composicao', 'Configurar a composicao de produtos.'),
    ('inventory.view', 'inventory', 'Visualizar estoque', 'Visualizar saldos de estoque.'),
    ('inventory.move', 'inventory', 'Movimentar estoque', 'Registrar movimentacoes de estoque.'),
    ('inventory.change_minimum', 'inventory', 'Alterar estoque minimo', 'Configurar estoque minimo.'),
    ('inventory.view_history', 'inventory', 'Visualizar historico', 'Visualizar historico de estoque.'),
    ('inventory.view_stock_kpis', 'inventory', 'Visualizar indicadores de estoque', 'Visualizar indicadores de estoque baixo e zerado.'),
    ('inventory.view_stock_costs', 'inventory', 'Visualizar custos de estoque', 'Visualizar custos e valor estimado do estoque.'),
    ('cash_registers.view', 'cash_registers', 'Visualizar caixas', 'Visualizar caixas.'),
    ('cash_registers.open', 'cash_registers', 'Abrir caixa', 'Abrir caixas.'),
    ('cash_registers.manual_entry', 'cash_registers', 'Realizar entrada manual', 'Registrar entradas manuais no caixa.'),
    ('cash_registers.withdraw', 'cash_registers', 'Realizar sangria', 'Registrar sangrias no caixa.'),
    ('cash_registers.close', 'cash_registers', 'Fechar caixa', 'Fechar caixas.'),
    ('sales.create', 'sales', 'Realizar vendas', 'Registrar vendas.'),
    ('sales.view', 'sales', 'Visualizar vendas', 'Visualizar vendas.'),
    ('sales.cancel', 'sales', 'Cancelar vendas', 'Cancelar vendas.'),
    ('sales.apply_discount', 'sales', 'Aplicar desconto', 'Aplicar descontos em vendas.'),
    ('sales.create_consumption', 'sales', 'Criar consumacao', 'Criar consumacoes.'),
    ('sales.view_consumption', 'sales', 'Visualizar consumacao', 'Visualizar consumacoes.'),
    ('sales.cancel_consumption', 'sales', 'Cancelar consumacao', 'Cancelar consumacoes.'),
    ('payment_methods.view', 'payment_methods', 'Visualizar formas de pagamento', 'Visualizar formas de pagamento.'),
    ('payment_methods.change', 'payment_methods', 'Configurar formas de pagamento', 'Configurar formas de pagamento.'),
    ('promotions.view', 'promotions', 'Visualizar promocoes', 'Visualizar promocoes.'),
    ('promotions.change', 'promotions', 'Configurar promocoes', 'Criar, editar e alterar o status de promocoes.'),
    ('reports.view_sales', 'reports', 'Visualizar relatorio de vendas', 'Visualizar relatorio operacional de vendas.'),
    ('reports.view_consumptions', 'reports', 'Visualizar relatorio de consumacoes', 'Visualizar relatorio operacional de consumacoes.'),
    ('reports.view_cash', 'reports', 'Visualizar relatorio de caixa', 'Visualizar relatorio operacional de caixa.'),
    ('reports.view_withdrawals', 'reports', 'Visualizar relatorio de sangrias', 'Visualizar relatorio operacional de sangrias.'),
    ('reports.view_inventory', 'reports', 'Visualizar relatorio de estoque', 'Visualizar relatorio de movimentacoes de estoque.'),
    ('reports.view_operational_result', 'reports', 'Visualizar resultado operacional', 'Visualizar resultado operacional estimado da filial.'),
    ('reports.export', 'reports', 'Exportar relatorios', 'Exportar relatorios operacionais.'),
)

ALL_PERMISSION_CODES = frozenset(item[0] for item in PERMISSION_CATALOG)

OPERATING_PERMISSION_CODES = frozenset(
    code
    for code in ALL_PERMISSION_CODES
    if code.split('.', 1)[0]
    in {'products', 'inventory', 'cash_registers', 'sales', 'payment_methods', 'promotions', 'reports'}
)

DEFAULT_PROFILE_PERMISSIONS = {
    'Administrador': ALL_PERMISSION_CODES,
    'Gerente': ALL_PERMISSION_CODES,
    'Operador de Caixa': frozenset(
        {
            'companies.view',
            'branches.view',
            'products.view',
            'inventory.view',
            'cash_registers.view',
            'cash_registers.open',
            'cash_registers.manual_entry',
            'cash_registers.withdraw',
            'cash_registers.close',
            'sales.create',
            'sales.view',
            'sales.create_consumption',
            'sales.view_consumption',
            'payment_methods.view',
            'promotions.view',
            'reports.view_sales',
            'reports.view_consumptions',
            'reports.view_cash',
            'reports.view_withdrawals',
        }
    ),
    'Operador de Estoque': frozenset(
        {
            'companies.view',
            'branches.view',
            'products.view',
            'products.add',
            'products.change',
            'products.change_status',
            'products.configure_composition',
            'inventory.view',
            'inventory.move',
            'inventory.change_minimum',
            'inventory.view_history',
            'inventory.view_stock_kpis',
            'reports.view_inventory',
        }
    ),
}

DEFAULT_PROFILE_DESCRIPTIONS = {
    'Administrador': 'Acesso completo a empresa.',
    'Gerente': 'Acesso gerencial e operacional completo.',
    'Operador de Caixa': 'Acesso a caixa, vendas e consultas operacionais.',
    'Operador de Estoque': 'Acesso ao catalogo de produtos e estoque.',
}
