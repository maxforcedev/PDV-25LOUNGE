ACTION_LABELS = {
    'auth.login': 'Login realizado',
    'auth.logout': 'Sessão encerrada',
    'user.create': 'Usuário criado',
    'user.update': 'Usuário alterado',
    'user.update_self': 'Dados pessoais alterados',
    'user.activate': 'Usuário ativado',
    'user.deactivate': 'Usuário inativado',
    'company.create': 'Empresa criada',
    'company.update': 'Empresa alterada',
    'company.activate': 'Empresa ativada',
    'company.deactivate': 'Empresa inativada',
    'branch.create': 'Filial criada',
    'branch.update': 'Filial alterada',
    'branch.activate': 'Filial ativada',
    'branch.deactivate': 'Filial inativada',
    'branch_settings.create': 'Configurações da filial criadas',
    'branch_settings.update': 'Configurações da filial alteradas',
    'access_profile.create': 'Perfil de acesso criado',
    'access_profile.update': 'Perfil de acesso alterado',
    'access_profile.activate': 'Perfil de acesso ativado',
    'access_profile.deactivate': 'Perfil de acesso inativado',
    'user_company_access.create': 'Acesso de empresa concedido',
    'user_branch_access.create': 'Acesso de filial concedido',
    'user_permission_block.create': 'Bloqueio de permissão criado',
    'user_permission_block.revoke': 'Bloqueio de permissão revogado',
    'commission_override.create': 'Comissão individual configurada',
    'commission_override.update': 'Comissão individual alterada',
    'commission_override.delete': 'Comissão individual removida',
    'category.create': 'Categoria criada',
    'category.update': 'Categoria alterada',
    'category.activate': 'Categoria ativada',
    'category.deactivate': 'Categoria inativada',
    'category.reorder': 'Ordem das categorias alterada',
    'product.create': 'Produto criado',
    'product.update': 'Produto alterado',
    'product.activate': 'Produto ativado',
    'product.deactivate': 'Produto inativado',
    'product.bulk_create': 'Produto cadastrado em lote',
    'product.composition.update': 'Composição do produto alterada',
    'branch_price.create': 'Preço da filial criado',
    'branch_price.update': 'Preço da filial alterado',
    'branch_price.delete': 'Preço da filial removido',
    'supplier.create': 'Fornecedor criado',
    'supplier.update': 'Fornecedor alterado',
    'supplier.activate': 'Fornecedor ativado',
    'supplier.deactivate': 'Fornecedor inativado',
    'product_supplier.create': 'Fornecedor vinculado ao produto',
    'product_supplier.update': 'Vínculo de fornecedor alterado',
    'product_supplier.activate': 'Vínculo de fornecedor ativado',
    'product_supplier.deactivate': 'Vínculo de fornecedor inativado',
    'product_supplier_unit.create': 'Apresentação de compra criada',
    'product_supplier_unit.update': 'Apresentação de compra alterada',
    'product_supplier_unit.activate': 'Apresentação de compra ativada',
    'product_supplier_unit.deactivate': 'Apresentação de compra inativada',
    'modifier_group.create': 'Grupo de modificador criado',
    'modifier_group.update': 'Grupo de modificador alterado',
    'modifier_group.activate': 'Grupo de modificador ativado',
    'modifier_group.deactivate': 'Grupo de modificador inativado',
    'product_modifier_link.create': 'Modificador vinculado ao produto',
    'product_modifier_link.update': 'Vínculo de modificador alterado',
    'product_modifier_link.activate': 'Vínculo de modificador ativado',
    'product_modifier_link.deactivate': 'Vínculo de modificador inativado',
    'table.create': 'Mesa criada',
    'table.update': 'Mesa alterada',
    'command.open': 'Comanda aberta',
    'order_item.create': 'Item adicionado à comanda',
    'order_item.confirm': 'Item confirmado com baixa de estoque',
    'order_item.cancel': 'Item cancelado com estorno',
    'command.finalize': 'Comanda fechada com venda',
    'purchase.create': 'Compra criada',
    'purchase.update': 'Compra alterada',
    'purchase.place': 'Pedido de compra realizado',
    'purchase.receive': 'Recebimento de compra confirmado',
    'purchase.close_partial': 'Pendência de compra encerrada',
    'purchase.cancel': 'Compra cancelada',
    'purchase.payables.define': 'Parcelas da compra definidas',
    'purchase.payable.create': 'Parcela da compra criada',
    'purchase.payable.pay': 'Parcela da compra paga',
    'purchase.payable.cancel': 'Parcela da compra cancelada',
    'promotion.create': 'Promoção criada',
    'promotion.update': 'Promoção alterada',
    'promotion.activate': 'Promoção ativada',
    'promotion.deactivate': 'Promoção inativada',
    'payment_method.create': 'Forma de pagamento criada',
    'payment_method.update': 'Forma de pagamento alterada',
    'payment_method.activate': 'Forma de pagamento ativada',
    'payment_method.deactivate': 'Forma de pagamento inativada',
    'inventory.entry': 'Entrada de estoque registrada',
    'inventory.exit': 'Saída de estoque registrada',
    'inventory.adjustment': 'Ajuste de estoque registrado',
    'inventory.regularize': 'Estoque negativo regularizado',
    'inventory.minimum.update': 'Estoque mínimo alterado',
    'cash_register.create': 'Caixa criado',
    'cash_register.update': 'Caixa alterado',
    'cash_register.activate': 'Caixa ativado',
    'cash_register.deactivate': 'Caixa inativado',
    'cash_session.open': 'Sessão de caixa aberta',
    'cash_session.close': 'Sessão de caixa fechada',
    'cash_movement.manual_entry': 'Entrada manual de caixa registrada',
    'cash_movement.withdrawal': 'Sangria registrada',
    'sale.finalize': 'Venda finalizada',
    'sale.cancel': 'Venda cancelada',
    'consumption.finalize': 'Consumação finalizada',
    'consumption.cancel': 'Consumação cancelada',
    'api.create': 'Inclusão registrada pelo sistema',
    'api.update': 'Alteração registrada pelo sistema',
    'api.partial_update': 'Alteração registrada pelo sistema',
    'api.destroy': 'Exclusão registrada pelo sistema',
    'api.post': 'Operação registrada pelo sistema',
    'api.put': 'Alteração registrada pelo sistema',
    'api.patch': 'Alteração registrada pelo sistema',
    'api.delete': 'Exclusão registrada pelo sistema',
}

MODULE_LABELS = {
    'accounts': 'Usuários e acesso',
    'auth': 'Acesso',
    'user': 'Usuários e acesso',
    'api': 'Sistema',
    'base': 'Auditoria',
    'cash': 'Caixa',
    'cash_movement': 'Caixa',
    'cash_register': 'Caixa',
    'cash_session': 'Caixa',
    'companies': 'Empresas e filiais',
    'company': 'Empresas e filiais',
    'branch': 'Empresas e filiais',
    'branch_settings': 'Empresas e filiais',
    'access_profile': 'Usuários e acesso',
    'user_permission_block': 'Usuários e acesso',
    'commission_override': 'Comissões',
    'inventory': 'Estoque',
    'products': 'Produtos',
    'product': 'Produtos',
    'category': 'Produtos',
    'branch_price': 'Produtos',
    'suppliers': 'Fornecedores',
    'supplier': 'Fornecedores',
    'product_supplier': 'Fornecedores',
    'product_supplier_unit': 'Fornecedores',
    'modifiers': 'Modificadores',
    'modifier_group': 'Modificadores',
    'modifier_option': 'Modificadores',
    'product_modifier_group': 'Modificadores',
    'purchases': 'Compras',
    'purchase': 'Compras',
    'sales': 'Vendas',
    'sale': 'Vendas',
    'consumption': 'Consumações',
    'promotion': 'Promoções',
    'payment_method': 'Formas de pagamento',
}

AUDIT_MODULE_LABELS = {
    'access': 'Acesso',
    'users_access': 'Usuários e acesso',
    'commissions': 'Comissões',
    'companies': 'Empresas e filiais',
    'cash': 'Caixa',
    'inventory': 'Estoque',
    'products': 'Produtos',
    'suppliers': 'Fornecedores',
    'modifiers': 'Modificadores',
    'purchases': 'Compras',
    'sales': 'Vendas',
    'commands': 'Mesas e comandas',
    'table': 'Mesas',
    'command': 'Comandas',
    'order': 'Pedidos',
    'order_item': 'Itens de pedido',
    'consumptions': 'Consumações',
    'promotions': 'Promoções',
    'payment_methods': 'Formas de pagamento',
    'audit': 'Auditoria',
    'system': 'Sistema',
}

ACTION_MODULE_KEYS = {
    'auth': 'access',
    'user': 'users_access',
    'access_profile': 'users_access',
    'user_company_access': 'users_access',
    'user_branch_access': 'users_access',
    'user_permission_block': 'users_access',
    'commission_override': 'commissions',
    'company': 'companies',
    'branch': 'companies',
    'branch_settings': 'companies',
    'cash_register': 'cash',
    'cash_session': 'cash',
    'cash_movement': 'cash',
    'inventory': 'inventory',
    'category': 'products',
    'product': 'products',
    'branch_price': 'products',
    'supplier': 'suppliers',
    'product_supplier': 'suppliers',
    'product_supplier_unit': 'suppliers',
    'purchase': 'purchases',
    'sale': 'sales',
    'consumption': 'consumptions',
    'promotion': 'promotions',
    'payment_method': 'payment_methods',
}

OBJECT_MODULE_KEYS = {
    'user': 'users_access',
    'userviewset': 'users_access',
    'accessprofile': 'users_access',
    'accessprofileviewset': 'users_access',
    'usercompanyaccess': 'users_access',
    'userbranchaccess': 'users_access',
    'userpermissionblock': 'users_access',
    'userpermissionblockviewset': 'users_access',
    'usercommissionoverride': 'commissions',
    'usercommissionoverrideviewset': 'commissions',
    'company': 'companies',
    'companyviewset': 'companies',
    'branch': 'companies',
    'branchviewset': 'companies',
    'branchsettings': 'companies',
    'branchsettingsviewset': 'companies',
    'cashregister': 'cash',
    'cashregisterviewset': 'cash',
    'cashsession': 'cash',
    'cashsessionviewset': 'cash',
    'cashmovement': 'cash',
    'cashmovementviewset': 'cash',
    'stock': 'inventory',
    'stockviewset': 'inventory',
    'stockmovement': 'inventory',
    'stockmovementviewset': 'inventory',
    'category': 'products',
    'categoryviewset': 'products',
    'product': 'products',
    'productviewset': 'products',
    'productcomponent': 'products',
    'branchproductprice': 'products',
    'branchproductpriceviewset': 'products',
    'supplier': 'suppliers',
    'supplierviewset': 'suppliers',
    'productsupplier': 'suppliers',
    'productsupplierviewset': 'suppliers',
    'productsupplierunit': 'suppliers',
    'productsupplierunitviewset': 'suppliers',
    'purchaseorder': 'purchases',
    'purchaseorderviewset': 'purchases',
    'purchasereceipt': 'purchases',
    'purchasereceiptviewset': 'purchases',
    'purchasereceiptitem': 'purchases',
    'payableinstallment': 'purchases',
    'payableinstallmentviewset': 'purchases',
    'sale': 'sales',
    'saleviewset': 'sales',
    'promotion': 'promotions',
    'promotionviewset': 'promotions',
    'promotionschedule': 'promotions',
    'payment': 'payment_methods',
    'paymentmethod': 'payment_methods',
    'paymentmethodviewset': 'payment_methods',
    'auditlog': 'audit',
    'auditlogviewset': 'audit',
}

APP_MODULE_KEYS = {
    'accounts': 'users_access',
    'companies': 'companies',
    'cash': 'cash',
    'inventory': 'inventory',
    'products': 'products',
    'suppliers': 'suppliers',
    'purchases': 'purchases',
    'sales': 'sales',
    'base': 'audit',
}

OBJECT_LABELS = {
    'accessprofile': 'Perfil de acesso',
    'branch': 'Filial',
    'branchproductprice': 'Preço por filial',
    'branchsettings': 'Configurações da filial',
    'cashmovement': 'Movimentação de caixa',
    'cashregister': 'Caixa',
    'cashsession': 'Sessão de caixa',
    'category': 'Categoria',
    'company': 'Empresa',
    'functionalpermission': 'Permissão funcional',
    'payment': 'Pagamento',
    'paymentmethod': 'Forma de pagamento',
    'product': 'Produto',
    'productcomponent': 'Componente de produto',
    'promotion': 'Promoção',
    'promotionschedule': 'Horário da promoção',
    'sale': 'Venda',
    'saleitem': 'Item de venda',
    'stock': 'Estoque',
    'stockmovement': 'Movimentação de estoque',
    'supplier': 'Fornecedor',
    'productsupplier': 'Fornecedor do produto',
    'productsupplierunit': 'Apresentação de compra',
    'purchaseorder': 'Compra',
    'purchaseorderitem': 'Item de compra',
    'purchasereceipt': 'Recebimento de compra',
    'purchasereceiptitem': 'Item recebido',
    'payableinstallment': 'Parcela da compra',
    'user': 'Usuário',
    'userbranchaccess': 'Acesso de filial do usuário',
    'usercompanyaccess': 'Acesso de empresa do usuário',
    'usercommissionoverride': 'Comissão individual',
    'userpermissionblock': 'Bloqueio de permissão',
}

FIELD_LABELS = {
    'id': 'Identificador',
    'company_id': 'Empresa',
    'supplier_id': 'Fornecedor',
    'purchase_order_id': 'Compra',
    'purchase_order_item_id': 'Item de compra',
    'product_supplier_id': 'Fornecedor do produto',
    'category_id': 'Categoria',
    'access_profile_id': 'Perfil de acesso',
    'authenticated': 'Sessão autenticada',
    'email': 'E-mail',
    'can_login': 'Pode acessar o sistema',
    'user_type': 'Tipo de usuário',
    'first_name': 'Nome',
    'last_name': 'Sobrenome',
    'is_active': 'Ativo',
    'is_superuser': 'Superusuário',
    'created_at': 'Criado em',
    'updated_at': 'Alterado em',
    'code': 'Código',
    'module': 'Módulo',
    'label': 'Rótulo',
    'company_accesses': 'Acessos de empresa',
    'branch_accesses': 'Acessos de filial',
    'trade_name': 'Nome fantasia',
    'legal_name': 'Razão social',
    'cnpj': 'CNPJ',
    'tax_id': 'CPF/CNPJ',
    'phone': 'Telefone',
    'contact_name': 'Contato',
    'notes': 'Observações',
    'address': 'Endereço',
    'address_pending': 'Endereço pendente',
    'is_matrix': 'Matriz',
    'name': 'Nome',
    'description': 'Descrição',
    'status': 'Status',
    'allow_negative_stock': 'Permitir estoque negativo',
    'service_fee_rate': 'Taxa de serviço',
    'commission_rate': 'Percentual de comissão',
    'fixed_daily_cost': 'Custo fixo diário',
    'receives_commission': 'Recebe comissão',
    'permission_codes': 'Permissões',
    'user_id': 'Usuário',
    'user_name': 'Usuário',
    'permission_id': 'Permissão',
    'permission_code': 'Permissão',
    'permission_label': 'Permissão',
    'created_by_id': 'Criado por',
    'updated_by_id': 'Alterado por',
    'reason': 'Motivo',
    'revoked_at': 'Revogado em',
    'revoked_by_id': 'Revogado por',
    'sort_order': 'Ordem',
    'internal_code': 'Código interno',
    'barcode': 'Código de barras',
    'supplier_code': 'Código no fornecedor',
    'unit_code': 'Unidade de compra',
    'conversion_factor': 'Fator de conversão',
    'is_preferred': 'Preferencial',
    'is_exclusive': 'Exclusivo',
    'is_default': 'Apresentação padrão',
    'cost': 'Custo',
    'sale_price': 'Preço de venda',
    'inventory_behavior': 'Comportamento de estoque',
    'unit': 'Unidade',
    'image': 'Imagem',
    'is_sellable': 'Disponível para venda',
    'is_favorite': 'Favorito',
    'components': 'Composição',
    'product_id': 'Produto',
    'product_name': 'Produto',
    'parent_product_id': 'Produto composto',
    'component_product_id': 'Componente',
    'branch_id': 'Filial',
    'discount_type': 'Tipo de desconto',
    'discount_value': 'Valor do desconto',
    'starts_at': 'Início',
    'ends_at': 'Fim',
    'product_ids': 'Produtos',
    'category_ids': 'Categorias',
    'schedules': 'Horários',
    'weekday': 'Dia da semana',
    'start_time': 'Horário inicial',
    'end_time': 'Horário final',
    'is_system': 'Registro padrão do sistema',
    'stock_id': 'Estoque',
    'current_quantity': 'Saldo atual',
    'movement_type': 'Tipo de movimentação',
    'nature': 'Natureza',
    'quantity': 'Quantidade movimentada',
    'previous_quantity': 'Saldo anterior',
    'final_quantity': 'Saldo final',
    'minimum_quantity': 'Estoque mínimo',
    'operation_reference': 'Referência da operação',
    'sale_id': 'Venda ou consumação',
    'original_movement_id': 'Movimentação original',
    'cash_register_id': 'Caixa',
    'cash_session_id': 'Sessão de caixa',
    'opened_by_id': 'Aberto por',
    'opened_at': 'Aberto em',
    'closed_by_id': 'Fechado por',
    'closed_at': 'Fechado em',
    'opening_amount': 'Valor de abertura',
    'closing_expected_amount': 'Valor esperado',
    'closing_amount_informed': 'Valor informado',
    'closing_difference': 'Diferença de caixa',
    'amount': 'Valor',
    'withdrawal_category': 'Categoria da sangria',
    'beneficiary_user_id': 'Beneficiário',
    'result_effect': 'Efeito no resultado',
    'sale_number': 'Número da operação',
    'operation_type': 'Tipo de operação',
    'idempotency_key': 'Chave de idempotência',
    'subtotal': 'Subtotal',
    'promotion_discount_total': 'Desconto de promoções',
    'item_discount_total': 'Desconto em itens',
    'discount': 'Desconto geral',
    'service_fee_amount': 'Taxa de serviço',
    'service_fee_waived': 'Taxa de serviço dispensada',
    'commission_amount': 'Valor da comissão',
    'charged_amount': 'Valor cobrado',
    'total': 'Total',
    'seller_user_id': 'Atendente',
    'discount_approved_by_id': 'Desconto aprovado por',
    'service_fee_waived_by_id': 'Dispensa aprovada por',
    'item_discount_approved_by_id': 'Desconto em itens aprovado por',
    'cancelled_at': 'Cancelado em',
    'cancelled_by_id': 'Cancelado por',
    'cancellation_reason': 'Motivo do cancelamento',
    'promotion_id': 'Promoção',
    'promotion_name': 'Promoção',
    'promotion_discount_type': 'Tipo do desconto promocional',
    'promotion_discount_value': 'Valor do desconto promocional',
    'promotion_benefit': 'Benefício promocional',
    'manual_discount': 'Desconto manual',
    'unit_cost': 'Custo unitário',
    'average_unit_cost': 'Custo médio da filial',
    'last_unit_cost': 'Último custo da filial',
    'order_number': 'Número da compra',
    'order_type': 'Tipo da compra',
    'gross_total': 'Total bruto',
    'global_discount': 'Desconto global',
    'freight_total': 'Frete',
    'other_expenses_total': 'Outras despesas',
    'payable_total': 'Total a pagar',
    'ordered_quantity': 'Quantidade pedida',
    'effective_stock_unit_cost': 'Custo efetivo unitário',
    'divergence_reason': 'Motivo da divergência',
    'closure_reason': 'Motivo do encerramento',
    'unit_price': 'Preço unitário',
    'component_cost_snapshot': 'Custos dos componentes',
    'net_subtotal': 'Subtotal líquido',
    'payment_method_id': 'Forma de pagamento',
    'payment_method_name': 'Forma de pagamento',
    'payment_method_code': 'Código da forma de pagamento',
    'received_amount': 'Valor recebido',
    'change_amount': 'Troco',
    'items': 'Itens',
    'payments': 'Pagamentos',
}

ENUM_LABELS = {
    'active': 'Ativo',
    'inactive': 'Inativo',
    'open': 'Aberto',
    'closed': 'Fechado',
    'finalized': 'Finalizada',
    'cancelled': 'Cancelada',
    'employee': 'Funcionário',
    'promoter': 'Promoter',
    'dj': 'DJ',
    'artist': 'Artista',
    'other': 'Outros',
    'un': 'UN',
    'kg': 'KG',
    'g': 'G',
    'l': 'L',
    'ml': 'ML',
    'direct': 'Estoque próprio',
    'none': 'Sem estoque',
    'components': 'Baixa por componentes',
    'entry': 'Entrada',
    'exit': 'Saída',
    'adjustment': 'Ajuste',
    'sale': 'Venda',
    'sale_cancellation': 'Cancelamento de venda',
    'consumption': 'Consumação',
    'consumption_cancellation': 'Cancelamento de consumação',
    'normal': 'Normal',
    'bonus': 'Bonificada',
    'return': 'Devolução',
    'opening_balance': 'Saldo inicial',
    'correction': 'Correção',
    'transfer': 'Transferência',
    'damage': 'Avaria',
    'loss': 'Perda',
    'internal_use': 'Uso interno',
    'inventory': 'Inventário',
    'regularization': 'Regularização',
    'balance_correction': 'Correção de saldo',
    'cancellation': 'Cancelamento ou estorno',
    'manual_entry': 'Entrada manual',
    'withdrawal': 'Sangria',
    'advance': 'Vale ou adiantamento',
    'supplier': 'Fornecedor',
    'unclassified': 'Não classificado',
    'operating_expense': 'Despesa operacional',
    'neutral': 'Não afeta o resultado',
    'cash': 'Dinheiro',
    'pix': 'PIX',
    'credit_card': 'Cartão de crédito',
    'debit_card': 'Cartão de débito',
    'percentage': 'Percentual',
    'fixed_amount': 'Valor fixo',
    'purchase': 'Compra',
    'ORDER': 'Pedido de compra',
    'DIRECT': 'Entrada direta',
    'DRAFT': 'Rascunho',
    'PLACED': 'Realizado',
    'PARTIALLY_RECEIVED': 'Recebido parcialmente',
    'RECEIVED': 'Recebido',
    'CANCELLED': 'Cancelado',
    'CLOSED_PARTIAL': 'Parcial encerrado',
    'PENDING': 'Pendente',
    'PAID': 'Pago',
}

FIELD_ENUM_LABELS = {
    'user_type': {
        'employee': 'Funcionário',
        'promoter': 'Promoter',
        'dj': 'DJ',
        'artist': 'Artista',
        'other': 'Outro',
    },
    'unit': {
        'un': 'UN', 'kg': 'KG', 'g': 'G', 'l': 'L', 'ml': 'ML',
    },
    'inventory_behavior': {
        'direct': 'Estoque próprio',
        'none': 'Sem estoque',
        'components': 'Baixa por componentes',
    },
    'movement_type': {
        'entry': 'Entrada',
        'exit': 'Saída',
        'adjustment': 'Ajuste',
        'sale': 'Venda',
        'sale_cancellation': 'Cancelamento de venda',
        'consumption': 'Consumação',
        'consumption_cancellation': 'Cancelamento de consumação',
        'manual_entry': 'Entrada manual',
        'withdrawal': 'Sangria',
    },
    'nature': {
        'normal': 'Normal',
        'bonus': 'Bonificada',
        'return': 'Devolução',
        'opening_balance': 'Saldo inicial',
        'correction': 'Correção',
        'transfer': 'Transferência',
        'damage': 'Avaria',
        'loss': 'Perda',
        'internal_use': 'Uso interno',
        'inventory': 'Inventário',
        'regularization': 'Regularização',
        'balance_correction': 'Correção de saldo',
        'sale': 'Venda',
        'consumption': 'Consumação',
        'cancellation': 'Cancelamento ou estorno',
        'other': 'Outros',
    },
    'withdrawal_category': {
        'dj': 'DJ',
        'artist': 'Pagode ou artista',
        'advance': 'Vale ou adiantamento',
        'promoter': 'Promoter',
        'supplier': 'Fornecedor',
        'other': 'Outros',
    },
    'result_effect': {
        'unclassified': 'Não classificado',
        'operating_expense': 'Despesa operacional',
        'neutral': 'Não afeta o resultado',
    },
    'operation_type': {
        'sale': 'Venda', 'consumption': 'Consumação',
    },
    'payment_method_code': {
        'cash': 'Dinheiro',
        'pix': 'PIX',
        'credit_card': 'Cartão de crédito',
        'debit_card': 'Cartão de débito',
    },
    'discount_type': {
        'percentage': 'Percentual', 'fixed_amount': 'Valor fixo',
    },
    'promotion_discount_type': {
        'percentage': 'Percentual', 'fixed_amount': 'Valor fixo',
    },
    'weekday': {
        '0': 'Domingo',
        '1': 'Segunda-feira',
        '2': 'Terça-feira',
        '3': 'Quarta-feira',
        '4': 'Quinta-feira',
        '5': 'Sexta-feira',
        '6': 'Sábado',
    },
}

TECHNICAL_FIELDS = {
    'id',
    'company_accesses',
    'branch_accesses',
    'permission_codes',
    'product_ids',
    'category_ids',
    'schedules',
    'idempotency_key',
    'operation_reference',
}


def action_label(action):
    return ACTION_LABELS.get(action, 'Ação do sistema')


def field_label(field):
    return FIELD_LABELS.get(field, 'Campo técnico')


def value_label(field, value):
    if value is None or value == '':
        return 'Não informado'
    if isinstance(value, bool):
        return 'Sim' if value else 'Não'
    if field == 'components' and isinstance(value, list):
        components = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = item.get('component_name') or 'Componente'
            quantity = item.get('quantity') or '0'
            unit = str(item.get('component_unit') or '').upper()
            components.append(f'{name}: {quantity} {unit}'.strip())
        return '; '.join(components) if components else 'Sem componentes'
    if isinstance(value, (dict, list)):
        return 'Dados estruturados'
    if field in TECHNICAL_FIELDS or field.endswith('_id') or field.endswith('_ids'):
        return 'Definido'
    text = str(value)
    return FIELD_ENUM_LABELS.get(field, {}).get(text, ENUM_LABELS.get(text, text))


def _count_label(count, singular, plural):
    return f'{count} {singular if count == 1 else plural}'


def _access_summary(value, scope):
    if not isinstance(value, list):
        return value_label('', value)
    entries = [item for item in value if isinstance(item, dict)]
    if not entries:
        return f'Nenhum acesso de {scope}'
    active = sum(item.get('is_active', True) is not False for item in entries)
    profiles = sum(bool(item.get('access_profile_id')) for item in entries)
    return '; '.join((
        _count_label(len(entries), f'acesso de {scope}', f'acessos de {scope}'),
        _count_label(active, 'ativo', 'ativos'),
        _count_label(profiles, 'com perfil', 'com perfil'),
    ))


def _access_delta(before, after, identity):
    before = before if isinstance(before, list) else []
    after = after if isinstance(after, list) else []
    before_items = {
        item.get(identity): item for item in before
        if isinstance(item, dict) and item.get(identity) is not None
    }
    after_items = {
        item.get(identity): item for item in after
        if isinstance(item, dict) and item.get(identity) is not None
    }
    added = len(after_items.keys() - before_items.keys())
    removed = len(before_items.keys() - after_items.keys())
    shared = before_items.keys() & after_items.keys()
    profile_changes = sum(
        before_items[key].get('access_profile_id')
        != after_items[key].get('access_profile_id')
        for key in shared
    )
    status_changes = sum(
        before_items[key].get('is_active', True)
        != after_items[key].get('is_active', True)
        for key in shared
    )
    changes = []
    if added:
        changes.append(_count_label(added, 'adicionado', 'adicionados'))
    if removed:
        changes.append(_count_label(removed, 'removido', 'removidos'))
    if profile_changes:
        changes.append(_count_label(
            profile_changes, 'perfil alterado', 'perfis alterados'
        ))
    if status_changes:
        changes.append(_count_label(
            status_changes, 'status alterado', 'status alterados'
        ))
    return ', '.join(changes)


def _structured_change_labels(field, before, after):
    access_fields = {
        'company_accesses': ('empresa', 'company_id'),
        'branch_accesses': ('filial', 'branch_id'),
    }
    if field in access_fields:
        scope, identity = access_fields[field]
        before_label = _access_summary(before, scope)
        after_label = _access_summary(after, scope)
        delta = _access_delta(before, after, identity)
        if delta:
            after_label = f'{after_label} ({delta})'
        return before_label, after_label
    if field == 'permission_codes':
        before_codes = {
            str(code) for code in before
            if isinstance(code, (str, int))
        } if isinstance(before, list) else set()
        after_codes = {
            str(code) for code in after
            if isinstance(code, (str, int))
        } if isinstance(after, list) else set()
        before_label = _count_label(
            len(before_codes), 'permissão', 'permissões'
        )
        after_label = _count_label(len(after_codes), 'permissão', 'permissões')
        added = len(after_codes - before_codes)
        removed = len(before_codes - after_codes)
        changes = []
        if added:
            changes.append(_count_label(added, 'adicionada', 'adicionadas'))
        if removed:
            changes.append(_count_label(removed, 'removida', 'removidas'))
        if changes:
            after_label = f'{after_label} ({", ".join(changes)})'
        return before_label, after_label
    return value_label(field, before), value_label(field, after)


def audit_changes_values(before, after):
    before = before or {}
    after = after or {}
    keys = dict.fromkeys((*before.keys(), *after.keys()))
    changes = []
    for field in keys:
        if before.get(field) == after.get(field):
            continue
        before_label, after_label = _structured_change_labels(
            field, before.get(field), after.get(field)
        )
        changes.append({
            'field': field,
            'field_label': field_label(field),
            'before_label': before_label,
            'after_label': after_label,
        })
    return changes


def audit_changes(log):
    return audit_changes_values(log.before, log.after)


def audit_module_key(action, object_type):
    action_key = action.split('.')[0]
    if action_key != 'api' and action_key in ACTION_MODULE_KEYS:
        return ACTION_MODULE_KEYS[action_key]
    object_key = object_type.rsplit('.', 1)[-1].replace('_', '').lower()
    if object_key in OBJECT_MODULE_KEYS:
        module_key = OBJECT_MODULE_KEYS[object_key]
        if module_key == 'sales' and action.startswith('consumption.'):
            return 'consumptions'
        return module_key
    parts = object_type.split('.')
    if len(parts) > 2 and parts[0] == 'apps':
        return APP_MODULE_KEYS.get(parts[1], 'system')
    return ACTION_MODULE_KEYS.get(action_key, 'system')


def audit_module_label(action, object_type):
    return AUDIT_MODULE_LABELS[audit_module_key(action, object_type)]


def audit_labels(log):
    model = log.object_type.rsplit('.', 1)[-1]
    object_key = model.replace('_', '').lower()
    object_label = OBJECT_LABELS.get(object_key, 'Registro do sistema')
    if object_key == 'sale' and log.action.startswith('consumption.'):
        object_label = 'Consumação'
    return {
        'action_label': action_label(log.action),
        'module_label': audit_module_label(log.action, log.object_type),
        'object_label': object_label,
        'changes': audit_changes(log),
    }
