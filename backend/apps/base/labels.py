ACTION_LABELS = {
    'create': 'Criado', 'update': 'Alterado', 'activate': 'Ativado',
    'deactivate': 'Inativado', 'delete': 'Excluido', 'destroy': 'Excluido',
    'open': 'Aberto', 'close': 'Fechado', 'cancel': 'Cancelado',
    'revoke': 'Revogado', 'entry': 'Entrada registrada', 'exit': 'Saida registrada',
    'adjustment': 'Ajuste registrado', 'manual_entry': 'Entrada manual registrada',
    'withdrawal': 'Sangria registrada', 'regularize': 'Regularizado',
    'regularize_negatives': 'Negativos regularizados', 'reorder': 'Ordem alterada',
}

MODULE_LABELS = {
    'accounts': 'Usuarios', 'api': 'Sistema', 'base': 'Auditoria', 'cash': 'Caixa',
    'companies': 'Empresas e filiais', 'inventory': 'Estoque',
    'products': 'Produtos', 'sales': 'Vendas',
}

OBJECT_LABELS = {
    'accessprofile': 'Perfil de acesso', 'branch': 'Filial',
    'branchproductprice': 'Preco por filial', 'branchsettings': 'Configuracoes da filial',
    'cashmovement': 'Movimentacao de caixa', 'cashregister': 'Caixa',
    'cashsession': 'Sessao de caixa', 'category': 'Categoria', 'company': 'Empresa',
    'paymentmethod': 'Forma de pagamento', 'product': 'Produto', 'promotion': 'Promocao',
    'sale': 'Venda/consumacao', 'stock': 'Estoque',
    'stockmovement': 'Movimentacao de estoque', 'user': 'Usuario',
    'usercommissionoverride': 'Comissao individual',
    'userpermissionblock': 'Bloqueio de permissao', 'inventory': 'Estoque',
    'api': 'Sistema', 'branchprice': 'Preco por filial',
}


def action_label(action):
    parts = action.split('.')
    verb = ACTION_LABELS.get(parts[-1], parts[-1].replace('_', ' ').capitalize())
    subject = OBJECT_LABELS.get(parts[0].replace('_', ''), parts[0].replace('_', ' ').capitalize())
    return f'{verb} - {subject}'


def audit_labels(log):
    model = log.object_type.rsplit('.', 1)[-1]
    module = log.object_type.split('.')
    module_key = module[1] if len(module) > 2 and module[0] == 'apps' else log.action.split('.')[0]
    return {
        'action_label': action_label(log.action),
        'module_label': MODULE_LABELS.get(module_key, module_key.replace('_', ' ').capitalize()),
        'object_label': OBJECT_LABELS.get(model.replace('_', '').lower(), model.replace('_', ' ')),
    }
