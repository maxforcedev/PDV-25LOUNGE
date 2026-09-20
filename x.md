CORREÇÃO DE ARQUITETURA IMPORTANTE.

A FONTE DE VERDADE É O ESTADO ATUAL DO PROJETO.

A DECISÃO ANTERIOR SOBRE CASH SESSION PRECISA SER CORRIGIDA.

==================================================
REGRA DEFINITIVA
==================================================

CASH SESSION NÃO PERTENCE:

- à Venda Rápida;
- à Mesa;
- ao método Dinheiro;
- à tela de Pagamento.

CASH SESSION PERTENCE EXCLUSIVAMENTE AO MÓDULO:

CAIXA

dentro do CORE POS.

Venda Rápida e Mesa apenas utilizam automaticamente
o caixa operacional que já está aberto/ativo no POS.

==================================================
1. FLUXO CORRETO
==================================================

Usuário:

CAIXA
↓
seleciona/abre caixa quando necessário
↓
CashSession fica ATIVA para este POS/device
↓
volta ao Home
↓
Venda Rápida / Mesa / demais operações
↓
usam automaticamente essa CashSession.

NUNCA perguntar novamente qual caixa usar dentro de:

- Venda Rápida;
- Mesa;
- Pagamento;
- Dinheiro;
- fechamento da Mesa.

==================================================
2. CAIXA FIXO
==================================================

Se `cash_binding_mode = FIXED`:

o POS já possui CashRegister configurado.

Na área CAIXA:

- mostrar esse caixa;
- permitir abrir a sessão;
- sessão aberta torna-se a CashSession operacional ativa.

Venda e Mesa usam automaticamente essa sessão.

==================================================
3. CAIXA FLEXÍVEL
==================================================

Se `cash_binding_mode = FLEXIBLE`:

a escolha do CashRegister acontece NA TELA CAIXA.

Exemplo:

CAIXA

[ Caixa Balcão ▼ ]

[ ABRIR CAIXA ]

Depois da abertura/seleção:

CAIXA ATIVO
Caixa Balcão

Essa seleção deve tornar-se contexto operacional do POS/device.

NÃO manter isso somente como `_selectedRegisterId`
local dentro de `CashPage`.

==================================================
4. PERSISTÊNCIA DO CAIXA ATIVO
==================================================

Hoje `_selectedRegisterId` em CashPage é estado local da tela.

Isso não é suficiente.

O caixa/sessão operacional ativa precisa sobreviver:

- navegação entre módulos;
- troca de página;
- rebuild;
- restart do app quando a sessão continuar válida.

Preferencialmente o backend/device deve ser a fonte de verdade.

Não depender apenas de variável local Flutter.

==================================================
5. CONTEXTO POR DEVICE
==================================================

O caixa operacional deve pertencer ao contexto do POSDevice.

Não ao checkout.

Não à Mesa.

Não ao PaymentEntryPage.

Trocar de operador no mesmo POS não deve, por si só,
trocar o caixa físico ativo daquele dispositivo.

Preservar permissões do operador para operações de Caixa.

==================================================
6. SEM CASH SESSION ATIVA
==================================================

Se não houver uma CashSession operacional aberta:

Venda Rápida e Mesa NÃO devem apresentar seletor de caixa.

Devem bloquear a operação que exige caixa e apresentar algo como:

"Nenhum caixa está aberto neste POS."

[ IR PARA CAIXA ]

O usuário abre/seleciona o caixa na área CAIXA
e depois retorna.

==================================================
7. PAYMENT ENTRY
==================================================

`PaymentEntryPage` NÃO deve conhecer:

- CashSession;
- CashRegister;
- lista de caixas;
- seletor de caixa.

Remover `cashSessionId` do contrato visual se ele estiver ali
somente por causa dessa arquitetura antiga.

PaymentEntryPage cuida apenas de:

- método;
- valor aplicado;
- valor recebido;
- troco;
- pagar saldo;
- confirmação.

==================================================
8. VENDA RÁPIDA
==================================================

Hoje Venda Rápida ainda possui `_pickCashSession()`
antes da criação do checkout.

REMOVER ESSA ESCOLHA DO FLUXO DA VENDA.

Não quero:

VENDA
→ selecionar caixa
→ checkout.

Quero:

CAIXA já está aberto
→ VENDA
→ checkout automaticamente vinculado ao caixa ativo.

==================================================
9. MESA
==================================================

Remover da Mesa:

- `_resolveCashSession()`;
- `PaymentCashSessionPicker`;
- escolha de sessão ao tocar Dinheiro;
- escolha de sessão ao fechar Mesa.

Mesa usa automaticamente o contexto de Caixa ativo.

==================================================
10. FECHAMENTO DA MESA
==================================================

FECHAR MESA não pergunta caixa.

O backend deve usar a sessão operacional correta já associada
às operações/pagamentos.

Se existir inconsistência histórica de sessão,
o backend deve rejeitar explicitamente.

Não pedir ao operador para escolher um caixa arbitrariamente
no momento do fechamento.

==================================================
11. BACKEND
==================================================

Revisar os contratos atuais.

Hoje existem fluxos que recebem:

`cash_session`

do client.

Para operações POS novas, evoluir para resolução server-side
da sessão operacional ativa do POSDevice.

Conceitualmente:

`current_pos_cash_session(device)`

em vez de:

`_pos_sale_session(device, session_id)`

Não precisa necessariamente usar esse nome.

Objetivo:

o client NÃO escolhe uma sessão arbitrária para cada venda.

==================================================
12. SEGURANÇA
==================================================

O backend deve validar:

- sessão existe;
- status OPEN;
- filial correta;
- CashRegister ativo;
- compatível com o POSDevice;
- FIXED respeita caixa configurado;
- FLEXIBLE respeita caixa operacional escolhido pelo device.

Nunca confiar apenas em um ID enviado pelo Flutter.

==================================================
13. CHECKOUT OPTIONS
==================================================

Venda Rápida e Mesa não precisam receber uma lista de:

`cash_sessions`

para escolher pagamento.

Checkout options pode informar apenas o estado necessário, por exemplo:

- cash_ready
- active_cash_session
- active_cash_register

se a UI realmente precisar apresentar status.

Não utilizar isso como seletor financeiro.

==================================================
14. TELA CAIXA É A DONA DO CONTEXTO
==================================================

A área CAIXA passa a ser responsável por:

- selecionar register em FLEXIBLE;
- abrir sessão;
- definir sessão ativa;
- visualizar sessão;
- entradas;
- retiradas;
- fechamento;
- trocar contexto quando permitido.

Ao fechar a sessão ativa:

o POS imediatamente deixa de estar apto a criar novas
operações que exigem caixa.

==================================================
15. HOME / STATUS
==================================================

Se já existir espaço apropriado, deixar o AppController/bootstrap
conhecer o estado:

CAIXA ABERTO
ou
CAIXA FECHADO

Isso permite os módulos consumirem a mesma fonte de verdade.

Não criar estado de caixa independente em Venda Rápida e Mesa.

==================================================
16. NÃO CONFUNDIR DINHEIRO COM CAIXA
==================================================

Método:

DINHEIRO

é somente uma forma de pagamento.

CashSession:

é o turno/contexto operacional do caixa.

Portanto:

PIX
CRÉDITO
DÉBITO
DINHEIRO

pertencem todos à operação que está acontecendo
dentro do caixa ativo do POS.

Não selecionar CashSession apenas porque o método é Dinheiro.

==================================================
17. PRESERVAR UI COMPARTILHADA
==================================================

Preservar tudo que já foi corretamente compartilhado entre
Venda Rápida e Mesa:

- PaymentPageLayout
- PaymentHeaderActions
- PaymentMethodGrid
- PaymentSplitSelector
- PaymentMethodPicker
- PaymentEntryPage
- PaymentItemAllocationPage
- PaymentEqualSplitPage
- PaymentHistoryList
- PaymentBalanceCard
- PaymentFinancialSummary
- PaymentHistoryItem
- PaymentReversalDialog
- SharedAuthorizationDialog
- SharedDiscountDialog
- SharedCustomerPickerDialog

Não regredir essa arquitetura.

==================================================
18. PRESERVAR BOTÃO PAGAMENTO DA MESA
==================================================

Manter:

RESUMO DA MESA
...
TOTAL
[ PAGAMENTO ]
[ SALVAR E ENVIAR PEDIDO ]

Não devolver Pagamento para o AppBar.

==================================================
19. LIMPEZA
==================================================

Após migrar o contexto de Caixa:

remover seletores/helpers mortos relacionados a escolha
de CashSession dentro dos fluxos financeiros.

Incluindo, se ficarem sem uso:

- PaymentCashSessionPicker;
- `_pickCashSession`;
- `_resolveCashSession`;
- `_CashSessionDialog`;

e equivalentes.

==================================================
20. CHECKPOINT
==================================================

Ao terminar informe:

1. onde agora vive o estado da CashSession ativa;
2. como FIXED funciona;
3. como FLEXIBLE funciona;
4. como a escolha feita em Caixa persiste;
5. como Venda Rápida obtém automaticamente a sessão;
6. como Mesa obtém automaticamente a sessão;
7. como pagamento em Dinheiro funciona sem seletor;
8. como PIX/Crédito/Débito ficam vinculados ao mesmo contexto operacional;
9. comportamento sem caixa aberto;
10. comportamento ao fechar o caixa;
11. endpoints/backend alterados;
12. campos `cash_session` removidos do client onde aplicável;
13. segurança da resolução server-side;
14. código morto removido;
15. confirmação de que Pagamento continua no Resumo da Mesa;
16. confirmação de não regressão da Venda Rápida;
17. flutter analyze;
18. git diff --check;
19. Django system check;
20. migrations check.

DEPOIS PARE.

NÃO INICIE STONE/CIELO/PAGBANK.
NÃO INICIE OUTRA FASE.
NÃO ALTERE COMANDA LEGADO.
O TESTE FUNCIONAL SERÁ FEITO MANUALMENTE.