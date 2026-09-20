CONTINUE A MESMA MISSÃO, MAS CORRIJA UMA DECISÃO DE ARQUITETURA ANTES DE AVANÇAR.

FONTE DE VERDADE: ESTADO ATUAL DO PROJETO / HEAD ATUAL.

NÃO REFAÇA O BACKEND QUE JÁ FOI IMPLEMENTADO.
NÃO DESCARTE RBAC, PREVIEW, PENDING, ADAPTERS OU CORREÇÕES JÁ FEITAS.

PORÉM HÁ UMA REGRA DE PRODUTO/ARQUITETURA QUE NÃO ESTÁ SENDO SEGUIDA:

==================================================
REGRA PRINCIPAL
==================================================

EU NÃO QUERO:

"UMA TELA DE PAGAMENTO DE VENDA RÁPIDA"

E

"UMA TELA DE PAGAMENTO DE MESA"

QUE APENAS SE PARECEM.

EU QUERO OS MESMOS ELEMENTOS E O MESMO FLUXO DE PAGAMENTO.

O CONTEXTO MUDA.

A EXPERIÊNCIA BASE NÃO.

A arquitetura precisa representar isto:

                         CORE PAYMENT UI
                               │
                    MESMOS COMPONENTES/FLOW
                               │
                  ┌────────────┴────────────┐
                  │                         │
             VENDA RÁPIDA                 MESA
                  │                         │
        QuickSale Context/Adapter    Table Context/Adapter
                  │                         │
          backend QuickSale           backend Table

Ou seja:

- mesma estrutura visual;
- mesmos componentes;
- mesma entrada de pagamento;
- mesmo seletor;
- mesmo histórico;
- mesmo resumo;
- mesmo fluxo de dinheiro;
- mesmo fluxo de estorno;
- mesmo modal de desconto;
- mesmo DIVIDIR;
- mesmo Pagar por Itens;
- mesma experiência de pending/retry;
- mesmos padrões de responsividade.

MAS:

cada contexto chama seus próprios endpoints e respeita suas próprias regras de domínio.

==================================================
1. NÃO DUPLICAR O FLUXO
==================================================

Hoje `TablePaymentPage` ainda implementa um fluxo próprio.

Exemplo atual da Mesa:

FORMA DE PAGAMENTO
↓
modal:
- PAGAR POR VALOR
- PAGAR SALDO
- DIVIDIR IGUAL
- PAGAR POR ITENS

Isso NÃO é a experiência que temos na Venda Rápida.

Não quero manter essas duas lógicas em paralelo.

Venda Rápida já possui uma experiência validada.

Mesa deve consumir a mesma experiência através de um contexto/adapter próprio.

==================================================
2. O QUE DEVE SER IGUAL
==================================================

A tela base de Pagamento deve ter a mesma composição.

Exemplo:

← PAGAMENTO              CLIENTE   DIVIDIR   ⋮

FALTA                              R$ XX,XX

[ DINHEIRO ] [ DÉBITO  ]
[ PIX      ] [ CRÉDITO ]
[ OUTROS ]

PAGAMENTOS REALIZADOS

...

RESUMO

Total
Pago
Falta

[ CTA FINAL ]

Na Venda Rápida:

CTA = FINALIZAR VENDA

Na Mesa:

CTA = FECHAR MESA

Essa é uma DIFERENÇA DE CONTEXTO.

Não uma segunda UI.

==================================================
3. HEADER IGUAL
==================================================

Venda Rápida possui:

CLIENTE
DIVIDIR
⋮

Mesa deve usar os MESMOS ELEMENTOS.

Não quero:

Mesa:
Cliente
Atualizar
⋮

e Venda Rápida:
Cliente
Dividir
⋮

A atualização pode existir internamente ou em local apropriado, mas não deve substituir a estrutura principal.

Em tela pequena:

← PAGAMENTO        👤   ⇄   ⋮

Em tela maior:

CLIENTE
DIVIDIR
⋮

Mesma UX.

==================================================
4. FORMA DE PAGAMENTO DIRETA
==================================================

Ao clicar:

DINHEIRO
DÉBITO
PIX
CRÉDITO

o comportamento base deve ser equivalente ao da Venda Rápida.

Não abrir primeiro um modal perguntando:

- pagar por valor
- pagar saldo
- dividir
- itens

O clique direto representa pagamento normal.

A entrada de pagamento deve permitir:

VALOR APLICADO

e ação:

PAGAR SALDO

quando aplicável.

==================================================
5. DIVIDIR É UMA AÇÃO SEPARADA
==================================================

`DIVIDIR` fica no header.

Ao tocar:

DIVIDIR PAGAMENTO

- DIVIDIR IGUAL
- PAGAR POR ITENS

Exatamente seguindo o padrão da Venda Rápida.

Depois:

escolhe contexto da divisão
↓
escolhe forma
↓
mesma entrada de pagamento

==================================================
6. DIVIDIR IGUAL — MESMA UI, CONTEXTO DIFERENTE
==================================================

A Venda Rápida possui seu mecanismo.

Mesa possui backend próprio com:

equal_split
next_person
next_amount
paid_people
remaining_people

A UI continua sendo compartilhada.

Mas o TablePaymentAdapter/Context fornece:

Pessoa 2 de 4

R$ 25,00

O Flutter NÃO divide sozinho.

Mesa usa `next_amount`.

Venda Rápida usa sua regra existente.

MESMO COMPONENTE.

FONTES DE DADOS DIFERENTES.

==================================================
7. PAGAR POR ITENS — MESMO COMPONENTE
==================================================

Não quero:

`_ItemAllocationPage` para QuickSale

e

`_TableItemAllocationPage` com outra experiência

se ambos fazem a mesma coisa visualmente.

Criar/generalizar um componente compartilhado de seleção de itens.

O contexto fornece:

- itens;
- quantidade;
- quantidade disponível;
- unidade;
- callbacks;
- preview oficial.

Venda Rápida:

usa preview QuickSale.

Mesa:

usa:

`table-attendances/{id}/payment-preview/`

A UI deve ser a mesma.

==================================================
8. ENTRADA DE PAGAMENTO DEVE SER COMPARTILHADA
==================================================

Hoje existem fluxos diferentes de entrada.

Isso deve ser unificado.

Precisamos de um componente equivalente a:

`PaymentEntryPage`

capaz de receber:

- método;
- valor oficial;
- saldo;
- valor travado ou editável;
- contexto do pagamento;
- sessões de caixa;
- callbacks.

Contextos:

NORMAL
ITEMS
EQUAL_SPLIT
REMAINING

Não importa se o nome técnico será outro.

==================================================
9. DINHEIRO
==================================================

A MESMA experiência de Dinheiro deve ser usada nos dois lugares.

VALOR APLICADO
R$ 40,00

VALOR RECEBIDO
R$ 50,00

TROCO
R$ 10,00

Mesma UI.

Mesa e QuickSale apenas fornecem dados diferentes.

Sempre:

received >= applied

Também no contexto:

- itens;
- dividir;
- saldo.

==================================================
10. PAGAR SALDO
==================================================

A mesma ação/componente.

Quando escolhido:

VALOR APLICADO

R$ 87,50

TRAVADO.

Mesa usa saldo oficial de `table_summary`.

QuickSale usa saldo oficial de checkout.

Mesma apresentação.

==================================================
11. DESCONTO
==================================================

NÃO manter o AlertDialog próprio criado para Mesa.

Reutilizar:

`SharedDiscountDialog`

Mesma experiência de:

- valor;
- percentual.

Venda Rápida chama seu endpoint.

Mesa chama:

`table-attendances/{id}/checkout-context/`

CONTEXTO diferente.

COMPONENTE igual.

==================================================
12. CLIENTE
==================================================

Continuar reutilizando:

`SharedCustomerPickerDialog`

Venda Rápida:
atualiza checkout.

Mesa:
atualiza TableAttendance.

Mesma UI.

==================================================
13. ESTORNO
==================================================

Manter compartilhados:

`PaymentHistoryItem`

`PaymentReversalDialog`

`SharedAuthorizationDialog`

Fluxo visual:

pagamento
↓
ESTORNAR
↓
confirmação
↓
se necessário PIN

Na Venda Rápida:

`sales.payments.reverse`

Na Mesa:

`tables.payments.reverse`

Mesma experiência.

Contexto/permissão diferente.

==================================================
14. HISTÓRICO
==================================================

Mesma lista visual.

Mesmo comportamento:

- método;
- valor;
- recebido/troco;
- status;
- estornado;
- motivo opcional;
- botão de estorno.

Venda Rápida adapta `QuickSaleCheckoutPayment`.

Mesa adapta `TablePayment`.

==================================================
15. RESUMO
==================================================

Continuar reutilizando:

`PaymentBalanceCard`

e

`PaymentFinancialSummary`

Mesa:

TablePaymentAdapter → table_summary()

Venda:

QuickSalePaymentAdapter → checkout preview.

Mesmos componentes.

==================================================
16. PENDING / RETRY
==================================================

A experiência também deve ser a mesma.

Se existe pagamento incerto:

NOVOS PAGAMENTOS BLOQUEADOS

mostrar:

TENTAR NOVAMENTE

e permitir reconciliação.

Venda Rápida usa seu storage/recovery.

Mesa usa o pending persistido que está sendo implementado.

O estado/origem muda.

A experiência visual não.

==================================================
17. RESPONSABILIDADE DO CONTEXTO
==================================================

A camada compartilhada NÃO deve saber detalhes como:

QuickSaleCheckout

ou

TableAttendance

para decidir UI.

O contexto/adapter deve traduzir isso.

Algo conceitualmente como:

PaymentContext

- summary
- methods
- payments
- pending
- canRecord
- canEditFinancials
- canFinalize
- customer
- splitState

- recordPayment()
- reversePayment()
- refresh()
- reconcilePending()
- updateCustomer()
- updateDiscount()
- updateServiceFee()
- previewItems()
- finalize()

NÃO precisa seguir exatamente essa interface.

É uma direção arquitetural.

==================================================
18. O QUE MUDA ENTRE VENDA RÁPIDA E MESA
==================================================

VENDA RÁPIDA:

origem:
QuickSaleCheckout

final:
FINALIZAR VENDA

destino:
Venda concluída → Catálogo

permissões:
sales.*

MESA:

origem:
TableAttendance + TablePaymentLedger

final:
FECHAR MESA

destino:
Lista/Grid de Mesas

permissões:
tables.*

Essas são diferenças de CONTEXTO.

==================================================
19. O QUE NÃO MUDA
==================================================

NÃO deve mudar:

- grid de formas;
- header base;
- botão Cliente;
- botão Dividir;
- selector Dividir Igual/Pagar por Itens;
- entrada de valor;
- entrada de dinheiro;
- troco;
- Pagar Saldo;
- histórico;
- estorno visual;
- modal de estorno;
- autorização PIN visual;
- resumo;
- apresentação de pending/retry;
- modal de desconto;
- padrão responsivo.

==================================================
20. NÃO FAZER UMA MEGA-REESCRITA
==================================================

Não quero destruir a Venda Rápida para conseguir isso.

Faça refatoração incremental.

Primeiro identifique os elementos/fluxos já validados na Venda Rápida.

Extraia apenas o necessário.

Depois faça QuickSale e Mesa consumirem os mesmos elementos.

Venda Rápida não pode regredir.

==================================================
21. O CÓDIGO ATUAL MOSTRA A DUPLICAÇÃO
==================================================

No estado atual:

`SharedPaymentPage`

ainda é fortemente QuickSale.

E:

`TablePaymentPage`

está reimplementando:

- header;
- método;
- modo;
- entrada;
- desconto;
- divisão;
- itens;
- fechamento.

Isso precisa ser reduzido.

Não basta compartilhar:

- PaymentBalanceCard;
- PaymentHistoryItem;
- PaymentFinancialSummary.

Quero compartilhar O FLUXO E OS ELEMENTOS INTERATIVOS também.

==================================================
22. CONTINUE AS PENDÊNCIAS TÉCNICAS JÁ IDENTIFICADAS
==================================================

Além dessa correção arquitetural, conclua:

1. conectar persistência do pending à TablePaymentPage;
2. restaurar pending ao reabrir;
3. reconciliar por idempotency_key;
4. consumir preview oficial de itens;
5. usar next_person/next_amount;
6. saldo travado;
7. dinheiro/troco;
8. received >= applied;
9. caixa no fechamento;
10. equal_split sem semântica ambígua de active.

==================================================
23. NÃO ALTERAR
==================================================

NÃO iniciar:

- Stone;
- Cielo;
- PagBank;
- fiscal;
- outra fase.

NÃO mexer no Comanda legado.

NÃO duplicar backend financeiro.

NÃO mover cálculo financeiro para Flutter.

==================================================
24. CRITÉRIO DE ACEITE
==================================================

Quando eu alternar mentalmente entre:

VENDA RÁPIDA

e

MESA

eu devo reconhecer:

"ESSA É A MESMA TELA DE PAGAMENTO DO CORE."

E não:

"ESSA É A TELA DE PAGAMENTO DE MESA QUE FOI FEITA PARECIDA COM A OUTRA."

Exemplo final:

VENDA RÁPIDA:

[PAGAMENTO]

Cliente     Dividir     ⋮

Falta R$100

Dinheiro | Débito
PIX      | Crédito

Histórico

Total / Pago / Falta

FINALIZAR VENDA


MESA:

[PAGAMENTO]

Cliente     Dividir     ⋮

Falta R$100

Dinheiro | Débito
PIX      | Crédito

Histórico

Total / Pago / Falta

FECHAR MESA


O CONTEXTO MUDA.

OS ELEMENTOS E O FLUXO BASE SÃO OS MESMOS.

==================================================
25. CHECKPOINT
==================================================

Ao terminar, explique:

1. quais elementos antes estavam duplicados;
2. quais foram extraídos/compartilhados;
3. qual parte continua específica da Venda Rápida;
4. qual parte continua específica da Mesa;
5. como o Payment Context/Adapter separa domínio de UI;
6. confirmação de que a Venda Rápida não regrediu;
7. confirmação de que Mesa usa os mesmos elementos;
8. pending/recovery;
9. preview de itens;
10. dividir igual;
11. dinheiro/troco;
12. pagar saldo;
13. desconto;
14. estorno;
15. fechamento;
16. arquivos alterados;
17. flutter analyze;
18. git diff --check;
19. Django system check;
20. migrations check.

DEPOIS PARE.

NÃO INICIE OUTRA FASE.

O TESTE FUNCIONAL SERÁ FEITO MANUALMENTE POR MIM.