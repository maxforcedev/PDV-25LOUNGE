<role>
Evolua a experiência operacional atual do Backoffice sem transformá-la ainda no futuro CORE POS/App.

Foque:
- PDV;
- Promoções;
- configurações de Mesa;
- limites de consumo.
</role>

<tasks>

1. TAXA DE SERVIÇO NO PDV

Se:

charges_service_fee = false

não exibir:
"Retirar taxa de serviço".

Não existe taxa para retirar.

Se habilitada, preserve regras atuais.
</tasks>

<task>
2. TOOLBAR OPERACIONAL

Próximo de "Filial em operação", criar toolbar compacta conforme RBAC/Feature/configuração.

Possíveis ações:

- indicador Caixa;
- Desconto;
- Taxa;
- Consumação;
- Dividir por pessoa.

Caixa:

verde → OPEN;
vermelho → não OPEN.

A ação pode abrir/mostrar o fluxo atual correspondente.
</task>

<task>
3. CARRINHO

Deixe o card focado em:

- itens;
- modifiers;
- quantidade;
- subtotal;
- total;
- pagamentos.

Remova dali ações operacionais que foram para toolbar.
</task>

<task>
4. DIVIDIR POR PESSOA

Isto NÃO é pagamento parcial persistente.

Exemplo:

Total R$ 100
3 pessoas

Criar automaticamente linhas:

33,34
33,33
33,33.

O usuário pode:
- selecionar método em cada linha;
- editar;
- excluir;
- adicionar linha.

Antes de finalizar:

Σ pagamentos = total.

Preserve engine atual de pagamentos.
</task>

<task>
5. PROMOÇÕES

Ao ativar uma Promotion conflitante, exiba o conflito real retornado pelo backend.

Exemplo:

"Não foi possível ativar esta promoção porque ela conflita com \"Happy Hour\"."

Inclua detalhes úteis existentes:
- produto/categoria;
- período;
- horário;
- Branch.

Não altere a regra de conflito apenas para facilitar a mensagem.
</task>

<task>
6. DEFAULTS DE MESAS

Adicionar em BranchSettings, se coerente com arquitetura:

- quantidade padrão de mesas;
- lugares padrão;
- prefixo padrão.

O fluxo de geração em lote deve iniciar com esses defaults.

Permita alteração pelo usuário.

Não pré-crie Commands vazias.
</task>

<task>
7. LIMITES DE CONSUMO

Adicionar configuração para habilitar limite de consumo.

Suportar:

- limite da Command;
- limite agregado da Table.

Uma Table com várias Commands abertas deve considerar o consumo agregado.
</task>

<task>
8. BASE DO LIMITE

Limite de consumo representa exposição/consumo físico, não preço promocional final.

Calcule usando consumo confirmado bruto relevante:

- quantidade;
- preço do item;
- modifiers.

ANTES de:
- Promotion;
- Discount;
- Service Fee.

Confirme no código atual qual snapshot é a fonte correta.

Não invente uma segunda engine.
</task>

<task>
9. CONCORRÊNCIA

A validação do limite deve ocorrer no backend dentro da transação adequada.

Dois operadores não podem confirmar simultaneamente valores que individualmente passam, mas juntos ultrapassam o limite.

Use lock adequado sobre Command/Table ou agregado equivalente.
</task>

<task>
10. ERRO DO LIMITE

Retornar erro amigável com:

- limite;
- consumo atual;
- valor da tentativa;
- valor excedente.

Não retornar 500.
</task>

<task>
11. BACKOFFICE

NÃO redesenhe Mesas/Comandas para parecer o futuro POS.

Aqui elas permanecem funcionais para:
- administração;
- testes;
- suporte.

O CORE POS/App será outra etapa.
</task>

<validation>
Teste:

- service fee false/true;
- toolbar por feature;
- divisão de centavos;
- promoção conflitante;
- defaults de mesas;
- múltiplas Commands;
- limite Command;
- limite Table;
- concorrência;
- modifiers no limite;
- cross-branch;
- RBAC.

Execute testes direcionados + frontend lint/build.
</validation>

<rules>
- Não implementar pagamento parcial persistente.
- Não alterar Command→Sale→Inventory invariants.
- Não implementar CORE POS.
- Não fazer commit.
- Não avançar para BLOCO 6.
</rules>

<final_response>
Informe implementação, regras finais e testes.

Finalize:
BLOCO 5 APROVADO
ou
BLOCO 5 NÃO APROVADO.
</final_response>