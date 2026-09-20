CONTINUE A CORREÇÃO DO MÓDULO DE MESAS A PARTIR DO HEAD ATUAL.

FONTE DE VERDADE: ESTADO ATUAL DO PROJETO.

HÁ TRÊS AJUSTES DE PRODUTO/ARQUITETURA OBRIGATÓRIOS.

==================================================
1. REMOVER SELETOR DE CAIXA DE DENTRO DO DINHEIRO
==================================================

NÃO quero dropdown:

CAIXA
[ Caixa 01 ▼ ]

dentro da tela de pagamento em Dinheiro.

Hoje isso acontece na Mesa porque `TablePaymentPage` envia:

`cashSessions`

para o componente compartilhado:

`PaymentEntryPage`

e `PaymentEntryPage` possui conhecimento de sessão de caixa.

REMOVER ISSO.

O componente compartilhado de entrada de pagamento NÃO deve saber escolher caixa.

A experiência de Dinheiro deve ser:

DINHEIRO

FALTA R$ XX,XX

VALOR APLICADO
R$ XX,XX

[ INFORMAR VALOR RECEBIDO ]

VALOR RECEBIDO
R$ XX,XX

TROCO
R$ XX,XX

[ CONFIRMAR PAGAMENTO MANUAL ]

SEM seletor de caixa.

==================================================
2. CAIXA É CONTEXTO OPERACIONAL, NÃO ELEMENTO DO DINHEIRO
==================================================

Venda Rápida já trabalha dessa maneira:

o caixa é resolvido antes do fluxo de Pagamento.

Depois:

PaymentEntryPage
→ apenas registra o valor.

Mesa deve seguir o mesmo princípio.

Para Mesa, resolver `cash_session_id` FORA de `PaymentEntryPage`.

Usar as regras existentes de:

- `cash_binding_mode`
- `fixed_register`
- sessões abertas elegíveis
- configuração do POS/device.

Regra:

FIXED:
→ usar automaticamente a sessão elegível do caixa configurado.

Somente uma sessão elegível:
→ usar automaticamente.

FLEXIBLE + várias sessões:
→ se realmente precisar de escolha humana, escolher UMA VEZ no contexto de entrada da página de Pagamento, e não dentro de cada pagamento em Dinheiro.

Essa sessão fica no contexto do pagamento da Mesa.

NÃO perguntar novamente a cada pagamento em dinheiro.

Não mover regra de validação financeira para Flutter.

Backend continua validando a sessão.

==================================================
3. PaymentEntryPage NÃO DEVE RECEBER LISTA DE CAIXAS
==================================================

Remover do componente compartilhado, se possível:

`cashSessions`

e o `DropdownButtonFormField` de Caixa.

O componente pode receber, caso necessário para o resultado interno:

um `cashSessionId` já resolvido pelo contexto.

Mas não deve permitir selecionar caixa.

Idealmente:

PaymentEntryPage
→ valor / recebido / troco

Context Adapter
→ resolve sessão operacional.

==================================================
4. PAGAMENTO NÃO DEVE FICAR NO MENU SUPERIOR DA MESA
==================================================

Hoje em:

`table_attendance_page.dart`

existe no AppBar:

ícone `payments_outlined`

com tooltip:

`Pagamento`

REMOVER esse acesso do AppBar.

Não quero o Pagamento no menu superior da Mesa.

==================================================
5. PAGAMENTO DEVE FICAR NO RESUMO DA MESA
==================================================

Na lateral / página:

`RESUMO DA MESA`

já existe:

- itens;
- subtotal;
- promoções;
- descontos;
- taxa;
- total oficial;
- SALVAR E ENVIAR PEDIDO.

Adicionar o botão:

PAGAMENTO

IMEDIATAMENTE ANTES de:

SALVAR E ENVIAR PEDIDO.

Resultado:

RESUMO DA MESA

...

Subtotal
Descontos
Taxa
Total oficial

[ PAGAMENTO ]

[ SALVAR E ENVIAR PEDIDO ]

==================================================
6. MESMO LOCAL NO DESKTOP E MOBILE
==================================================

O `_TableOrderSummaryPanel` é usado:

- na lateral do desktop;
- na página de resumo mobile.

Portanto o botão PAGAMENTO deve fazer parte do próprio:

`_TableOrderSummaryPanel`

e não ser inserido separadamente em apenas um layout.

Adicionar callbacks/capabilities ao painel, por exemplo conceitualmente:

`canOpenPayment`
`onPayment`

Não precisa seguir exatamente esses nomes.

==================================================
7. REGRA PARA ITENS AINDA NÃO ENVIADOS
==================================================

Preservar a regra atual:

não registrar pagamento enquanto existirem itens novos ainda não enviados.

Portanto:

se `cart.isNotEmpty`

o botão PAGAMENTO pode aparecer desabilitado.

Não remover a proteção backend/fluxo existente.

Depois que:

SALVAR E ENVIAR PEDIDO

for concluído:

PAGAMENTO fica habilitado.

Se necessário, tooltip/mensagem curta:

`Envie os itens novos antes de registrar pagamentos.`

==================================================
8. PERMISSÃO
==================================================

O botão PAGAMENTO depende de:

`tables.payments.view`

Se não possuir a permissão:

não permitir acesso.

Manter também validação backend.

==================================================
9. COMPARAR NOVAMENTE VENDA RÁPIDA × MESA
==================================================

Além dos ajustes acima, revise os dois fluxos.

REGRA:

não quero duas implementações que apenas parecem iguais.

Quero os mesmos componentes onde a interação é a mesma.

Hoje já estão compartilhados e DEVEM continuar compartilhados:

- `PaymentPageLayout`
- `PaymentHeaderActions`
- `PaymentMethodGrid`
- `PaymentSplitSelector`
- `PaymentEntryPage`
- `PaymentItemAllocationPage`
- `PaymentBalanceCard`
- `PaymentFinancialSummary`
- `PaymentHistoryItem`
- `PaymentReversalDialog`
- `SharedAuthorizationDialog`
- `SharedDiscountDialog`
- `SharedCustomerPickerDialog`

NÃO regredir isso.

==================================================
10. DIVIDIR IGUAL AINDA ESTÁ DIFERENTE
==================================================

Hoje:

VENDA RÁPIDA
→ abre `_EqualSplitPage`
→ escolhe quantidade de pessoas
→ escolhe uma parte
→ escolhe forma
→ pagamento

MESA
→ lê `next_person`
→ lê `next_amount`
→ abre seletor de forma diretamente
→ pagamento

Os domínios realmente são diferentes.

Mas a EXPERIÊNCIA VISUAL deve reutilizar o mesmo elemento.

Criar/generalizar um componente compartilhado equivalente a:

`PaymentEqualSplitPage`

que consiga receber o contexto.

Venda Rápida:

- permite definir quantidade de pessoas;
- usa suas partes calculadas pelo checkout atual.

Mesa:

- quantidade vem da Mesa;
- usa `next_person`;
- usa `next_amount`;
- não recalcula financeiramente no Flutter.

Mas visualmente:

DIVIDIR IGUAL

Pessoa/Parte X de Y

R$ XX,XX

[ PAGAR ESTA PARTE ]

deve seguir o mesmo padrão.

==================================================
11. SELETOR DE FORMA DE PAGAMENTO
==================================================

Hoje `_pickMethod()` ainda existe separadamente em:

- Venda Rápida;
- Mesa.

Extrair um único seletor compartilhado.

Exemplo conceitual:

`PaymentMethodPicker`

Ele recebe:

- título;
- métodos;
- callback/resultado.

Usar nos dois contextos.

==================================================
12. HISTÓRICO
==================================================

Os dois já usam:

`PaymentHistoryItem`

mas cada página recria praticamente a mesma:

`ListView.separated`

Avaliar extrair:

`PaymentHistoryList`

recebendo uma lista de `PaymentDisplayEntry`.

O adapter de cada domínio transforma:

QuickSaleCheckoutPayment
→ PaymentDisplayEntry

TablePayment
→ PaymentDisplayEntry

A apresentação deve ser única.

==================================================
13. RESUMO
==================================================

Os dois já usam:

`PaymentFinancialSummary`

Isso está correto.

Se ainda houver composição duplicada idêntica em volta dele, extrair somente se simplificar.

Não fazer abstração artificial.

==================================================
14. CLASSIFICAÇÃO/ÍCONE DE FORMAS
==================================================

Não manter `_methodIcon()` diferente espalhado em vários arquivos.

A classificação já foi centralizada em:

`paymentMethodGroup()`

Centralizar também a representação visual necessária para:

- cash
- debit
- pix
- credit
- other

para evitar Venda Rápida e Mesa divergirem novamente.

==================================================
15. REMOVER CÓDIGO ANTIGO/MORTO
==================================================

Após a nova extração, ainda existem implementações antigas no código.

Em `shared_payment_page.dart` ainda aparecem estruturas antigas como:

- `_PaymentEntryPage`
- `_ItemAllocationPage`
- `_MoneyEntry`

quando o fluxo ativo já usa os elementos compartilhados novos.

Em `table_payment_page.dart` ainda existem:

- `_TablePaymentDialog`
- `_TableItemAllocationPage`

mesmo com o fluxo novo usando:

- `PaymentEntryPage`
- `PaymentItemAllocationPage`

Confirmar que não possuem chamadas ativas.

Se estiverem realmente mortas:

REMOVER.

Não deixar duas implementações do mesmo fluxo dentro do projeto.

==================================================
16. O QUE PODE SER DIFERENTE
==================================================

As diferenças de contexto DEVEM continuar.

VENDA RÁPIDA:

- `QuickSaleCheckout`
- `sales.*`
- finaliza Venda
- volta ao Catálogo
- regras QuickSale.

MESA:

- `TableAttendance`
- `TablePayment`
- `tables.*`
- Fecha Mesa
- volta ao Grid de Mesas
- `table_summary`
- equal split oficial da Mesa.

Isso NÃO precisa ser artificialmente unificado.

Compartilhar UI/interação.

Separar domínio/regra.

==================================================
17. CRITÉRIO DE ACEITE
==================================================

Ao abrir Pagamento de Venda Rápida e Pagamento de Mesa:

quero reconhecer exatamente o mesmo sistema de pagamento CORE.

Diferenças somente onde o contexto exige.

Principalmente:

MESMO:
- header
- formas
- entrada de pagamento
- Dinheiro
- valor recebido
- troco
- Pagar Saldo
- Dividir
- Pagar por Itens
- histórico
- estorno
- desconto
- resumo
- pending/retry
- responsividade.

DIFERENTE:
- dados
- endpoints
- permissões
- fechamento/finalização
- regras de domínio.

==================================================
18. NÃO ESQUECER DAS PENDÊNCIAS ANTERIORES
==================================================

Preservar/corrigir também:

- pending seguro;
- pending não pode ser apagado quando checkout-options falhar;
- Mesa deve usar `mode=remaining` quando contexto for PAGAR SALDO;
- `next_person/next_amount`;
- `equal_split.active` semanticamente correto;
- fechamento da Mesa usando sessão já determinada pelos pagamentos quando aplicável.

==================================================
19. CHECKPOINT
==================================================

Ao concluir informe:

1. como removeu o seletor de caixa do Dinheiro;
2. onde a Mesa resolve cash_session agora;
3. confirmação de que PaymentEntryPage não escolhe caixa;
4. confirmação de que Pagamento saiu do AppBar da Mesa;
5. confirmação de que Pagamento está no RESUMO DA MESA;
6. posição exata em relação a SALVAR E ENVIAR PEDIDO;
7. comportamento desktop;
8. comportamento mobile;
9. comportamento quando há itens não enviados;
10. quais elementos Venda Rápida/Mesa estão compartilhando;
11. o que ainda precisa permanecer específico por contexto;
12. como Dividir Igual foi unificado visualmente;
13. como seletor de método foi compartilhado;
14. se histórico foi compartilhado;
15. se ícones/classificação foram centralizados;
16. quais classes antigas/mortas foram removidas;
17. confirmação de não regressão da Venda Rápida;
18. flutter analyze;
19. git diff --check;
20. Django system check;
21. migrations check.

DEPOIS PARE.

NÃO INICIE OUTRA FASE.

NÃO IMPLEMENTE STONE/CIELO/PAGBANK.

O TESTE FUNCIONAL SERÁ FEITO MANUALMENTE.