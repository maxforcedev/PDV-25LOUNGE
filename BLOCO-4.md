<role>
Evolua exclusivamente Fornecedores, Apresentações e Compras.

Preserve o domínio atual de Purchases e Inventory.
Não crie uma segunda engine de compras.
</role>

<tasks>

1. FORNECEDOR

Razão social:
→ opcional.

Nome fantasia:
→ obrigatório.

Atualize backend/frontend/migration de forma compatível.

---

2. APRESENTAÇÃO

Na interface utilize nomenclatura clara:

"Unidade de compra / Apresentação do fornecedor".

Explique:

Produto em estoque:
UN

Fornecedor vende:
Caixa com 24 unidades

Fator:
24.

Descrição da apresentação deve ser obrigatória e coerente com backend.

---

3. PRODUTO NÃO PRECISA DE VÍNCULO PRÉVIO

Uma PurchaseOrder possui Supplier.

Porém o usuário deve conseguir comprar QUALQUER Product comprável da mesma Company, mesmo que não exista ProductSupplier prévio.

Se existir ProductSupplierUnit para aquele Supplier/Product:
→ oferecer a apresentação.

Se não existir:
→ permitir unidade padrão do estoque com conversão 1.

Não remova ProductSupplier/ProductSupplierUnit.

---

4. COMPRA RÁPIDA / AGRUPADA

Melhore a entrada dos itens para permitir muitas linhas rapidamente:

Produto | Quantidade | Custo | Apresentação

Busca rápida e adição de várias linhas.

Continua sendo UMA PurchaseOrder com múltiplos PurchaseOrderItems.

Não criar novo domínio chamado "Compra Agrupada".
</tasks>

<task>
5. PARCELAMENTO AUTOMÁTICO

Adicionar:

Número de parcelas: N

Gerar automaticamente N parcelas.

Distribua centavos corretamente.

Exemplo R$ 1.000 / 3:

333,34
333,33
333,33

Permita edição posterior.

Regra obrigatória:

Σ parcelas = payable_total.

Nunca permitir soma superior.

Para concluir configuração também não deixar soma inferior.
</task>

<task>
6. VENCIMENTOS

Não permitir parcelas da mesma PurchaseOrder com due_date duplicado.

Valide backend.

Não depender apenas do frontend.

Confirme impacto nos dados atuais antes de criar constraint rígida.
</task>

<task>
7. FORMA DE PAGAMENTO

A forma efetivamente utilizada deve pertencer ao pagamento da parcela/conta a pagar.

Não reutilize Payment de Sale como se fosse pagamento de fornecedor.

Use modelagem adequada ao Financeiro/Purchases atual.

Ao marcar parcela paga, registrar:
- método;
- data;
- valor;
- observação/comprovante quando já suportado;
- auditoria.

Se existir "forma prevista", mantenha separado de "forma efetivamente paga".
</task>

<task>
8. ERROS DE COMPRA

Aplique a arquitetura do BLOCO 2.

Erros 400 devem mostrar a validação específica:

- produto;
- fornecedor;
- quantidade;
- apresentação;
- parcelas;
- vencimento;
- total.

Não use fallback genérico quando houver erro específico.
</task>

<validation>
Teste:

- Supplier sem razão social;
- cross-company;
- Product sem vínculo Supplier;
- Product com apresentação;
- conversão 1;
- compra multilinha;
- parcelamento;
- centavos;
- vencimento duplicado;
- pagamento de parcela;
- RBAC;
- recebimento parcial existente;
- regressão de estoque/custo.

Execute testes direcionados + lint/build.
</validation>

<rules>
- Não reescrever PurchaseService estável.
- Não remover recebimento parcial.
- Não quebrar contas a pagar.
- Não criar pagamento parcial de Sale.
- Não fazer commit.
- Não avançar para BLOCO 5.
</rules>

<final_response>
Informe implementação, migrations, resultado financeiro/estoque e testes.

Finalize:
BLOCO 4 APROVADO
ou
BLOCO 4 NÃO APROVADO.
</final_response>