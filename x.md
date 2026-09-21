CONTINUE A MESMA FASE.

NÃO INICIE IMPRESSÃO AINDA.
NÃO INICIE STONE/CIELO/PAGBANK.
NÃO INICIE OUTRA FASE.

FONTE DE VERDADE:
ESTADO ATUAL DO PROJETO / HEAD ATUAL.

A ARQUITETURA NOVA DE CASH SESSION ESTÁ NO CAMINHO CERTO:

CashSession pertence ao POSDevice / módulo CAIXA.

Venda Rápida, Mesa e Pagamentos apenas consomem automaticamente o contexto ativo.

NÃO VOLTAR A COLOCAR SELETOR DE CAIXA EM:
- Venda Rápida;
- Mesa;
- Dinheiro;
- Pagamento;
- fechamento da Mesa.

Agora conclua os problemas restantes encontrados na auditoria.

==================================================
1. CORRIGIR ESTADO STALE AO ABRIR CAIXA
==================================================

Hoje, ao abrir uma CashSession:

backend atualiza:

POSDevice.active_cash_session

via `.update()`.

Logo depois, a resposta é montada utilizando o objeto `device`
que já estava carregado antes dessa atualização.

Isso pode fazer o backend responder um `cash_state`
desatualizado, ainda sem a nova sessão ativa.

Cenário:

CAIXA FECHADO
→ ABRIR CAIXA
→ banco grava active_cash_session
→ response usa device stale
→ Flutter recebe cash_state como se ainda estivesse fechado.

CORRIGIR.

Após definir `active_cash_session`, o estado retornado deve
obrigatoriamente refletir a sessão atual persistida no banco.

Pode:

- atualizar/refetch do device;
- ou fazer `cash_state_for_device()` consultar o device atual;
- ou solução equivalente segura.

Mesmo problema deve ser corrigido em:

- abrir sessão;
- selecionar sessão FLEXIBLE.

==================================================
2. FLEXIBLE: NÃO ALTERAR SELEÇÃO LOCAL ANTES DO SUCESSO
==================================================

Hoje em CashPage o `_selectedRegisterId`
é alterado antes de confirmar que o backend aceitou a sessão.

Problema:

POS está no Caixa A.

Usuário toca Caixa B.

Flutter:
_selectedRegisterId = B

Backend:
Caixa B não tem sessão aberta
→ 409.

Resultado possível:

seletor mostra Caixa B
mas activeSession continua Caixa A.

CORRIGIR.

A seleção só deve ser confirmada na UI depois de sucesso do backend.

Em caso de erro:

manter/reverter para o caixa ativo real vindo do backend.

A fonte da verdade deve ser o estado retornado pelo servidor.

==================================================
3. PROTEGER SELEÇÃO DE CAIXA FLEXIBLE COM PERMISSÃO
==================================================

Revisar `POSCashSessionSelectView`.

Trocar o contexto de caixa ativo do POS é uma ação operacional de Caixa.

Não basta apenas existir uma sessão de operador válida.

Aplicar validação explícita de permissão adequada.

Usar o RBAC existente.

Não criar permissão paralela sem necessidade.

O usuário precisa ter autorização operacional de caixa
para alterar o contexto ativo do POS.

Auditar também:

- seleção;
- abertura;
- fechamento.

==================================================
4. BLOCKER: MESA NÃO PODE MISTURAR CASH SESSIONS
==================================================

Esse é bloqueador.

Hoje:

Mesa 10
→ primeiro pagamento com CashSession A.

Depois alguém troca o POS para CashSession B.

A mesma Mesa pode registrar outro pagamento usando B.

Resultado:

TablePayment 1 → A
TablePayment 2 → B.

Depois o fechamento detecta mismatch e a Mesa fica impossível de fechar.

NÃO permitir isso.

A regra deve ser:

PRIMEIRO PAGAMENTO DA MESA
→ determina implicitamente o contexto de caixa daquele ciclo financeiro.

PAGAMENTOS SEGUINTES
→ devem usar a mesma CashSession.

Se o POS estiver atualmente em outra CashSession:

REJEITAR O NOVO PAGAMENTO ANTES DE GRAVAR.

Mensagem adequada, por exemplo:

"Esta Mesa possui pagamentos vinculados a outro caixa."

Não esperar o fechamento para descobrir a inconsistência.

==================================================
5. NÃO PRECISA NECESSARIAMENTE CRIAR CAMPO NOVO NA MESA
==================================================

Antes de adicionar campo persistido em TableAttendance,
avalie se o contexto pode ser inferido com segurança pelo primeiro
TablePayment histórico não-reversal.

Se isso for suficiente e consistente:

usar o ledger existente.

Não duplicar estado sem necessidade.

Mas garantir atomicidade e lock corretos.

==================================================
6. VENDA RÁPIDA JÁ TEM CONCEITO CORRETO
==================================================

Venda Rápida já faz melhor:

checkout nasce vinculado à sessão ativa.

Se o POS mudar de contexto antes de outro pagamento:

backend detecta:

cash_context_changed

e não grava.

Manter esse comportamento.

Mesa deve adotar o mesmo princípio.

==================================================
7. REVISAR current_pos_cash_session COM LOCK SEGURO
==================================================

Hoje `current_pos_cash_session(device, for_update=True)`
carrega POSDevice com `select_for_update()` e relação nullable
de `active_cash_session`.

Revisar o SQL/locking.

Preferência arquitetural:

lock POSDevice
↓
ler active_cash_session_id
↓
lock CashSession separadamente
↓
validar:
- OPEN;
- mesma filial;
- CashRegister ACTIVE;
- FIXED compatível.

Evitar lock ambíguo envolvendo outer join de relação nullable.

Manter atomicidade.

==================================================
8. CASH SESSION CONTINUA SENDO CONTEXTO DO DEVICE
==================================================

Preservar:

POSDevice.active_cash_session

Isso está correto.

FIXED:

- device usa CashRegister configurado;
- abrir Caixa define active_cash_session;
- operações usam essa sessão.

FLEXIBLE:

- seleção acontece na área CAIXA;
- seleção/open define active_cash_session;
- Venda/Mesa apenas consomem.

==================================================
9. FECHAR CAIXA
==================================================

Ao fechar a sessão ativa:

- limpar active_cash_session dos devices vinculados;
- POS deve imediatamente ficar `cash_ready = false`;
- novas operações financeiras que exigem contexto ativo devem falhar.

Preservar comportamento existente.

Revisar se a resposta após fechamento também usa estado atualizado,
não objeto stale.

==================================================
10. VENDA RÁPIDA NÃO DEVE ENVIAR CASH SESSION
==================================================

Preservar a nova arquitetura:

create checkout:
NÃO recebe cash_session do Flutter.

update checkout:
NÃO recebe cash_session do Flutter.

record payment:
NÃO recebe cash_session do Flutter.

finalize:
NÃO escolhe caixa no client.

Backend resolve e valida pelo POSDevice/contexto do checkout.

==================================================
11. MESA NÃO DEVE ENVIAR CASH SESSION
==================================================

Preservar:

record TablePayment:
NÃO recebe cash_session do Flutter.

close Table:
NÃO recebe cash_session do Flutter.

Nenhuma seleção na UI.

Backend resolve o contexto.

==================================================
12. PAYMENT ENTRY NÃO SABE NADA DE CAIXA
==================================================

Preservar `PaymentEntryPage` sem:

- cashSessionId;
- lista de caixas;
- CashRegister;
- dropdown;
- picker.

Dinheiro continua sendo apenas forma de pagamento.

==================================================
13. CORRIGIR PENDING DA MESA
==================================================

Ainda existe problema no recovery.

Hoje:

pending salvo
↓
reabre app
↓
checkout-options falha
↓
_methods pode ficar vazio
↓
fromJson não encontra method
↓
_pending vira null
↓
pending persistido pode ser apagado.

ISSO NÃO PODE ACONTECER.

Falha de rede ou falha ao carregar payment methods
não pode apagar uma tentativa incerta.

Regra:

pending só pode ser removido quando:

1. ledger confirmar o mesmo idempotency_key;
ou
2. operação for explicitamente resolvida/cancelada de forma segura.

Não apagar pending porque DTO/UI não conseguiu reconstruir o método.

O estado persistido deve preservar ao menos os dados necessários
para reconciliar a operação.

==================================================
14. CORRIGIR PAGAR SALDO + DINHEIRO
==================================================

Ainda existe bug em `PaymentEntryPage`.

Fluxo:

PAGAR SALDO
→ `_payingRemaining = true`

Depois operador ativa:

INFORMAR VALOR RECEBIDO

e digita o recebido.

Hoje o mesmo handler pode fazer:

`_payingRemaining = false`

mesmo o operador tendo alterado apenas VALOR RECEBIDO.

Isso está errado.

`payingRemaining` só pode virar false se o operador alterar
o VALOR APLICADO.

Alterar:

- valor recebido;
- troco;
- teclado do recebido;

NÃO pode mudar:

mode=remaining.

==================================================
15. EQUAL SPLIT ACTIVE
==================================================

Ainda corrigir semântica.

Hoje o estado prospectivo pode retornar:

active = true

antes de existir de fato um ciclo de equal split iniciado.

Não misturar:

"divisão disponível"

com:

"divisão ativa".

Separar semanticamente.

Exemplo conceitual:

available = true
active = false

antes do primeiro pagamento.

Depois que o ciclo realmente existe:

active = true.

Não precisa obrigatoriamente usar esses nomes,
mas o contrato deve ser semanticamente correto.

==================================================
16. REMOVER CÓDIGO MORTO
==================================================

Revisar `table_payment_page.dart`.

Ainda existe implementação antiga como:

`_TableItemAllocationPage`

mesmo com o fluxo ativo usando:

`PaymentItemAllocationPage`.

Se não houver referência ativa:

REMOVER.

Revisar também outros helpers antigos de cash/payment
que ficaram sem uso após essa refatoração.

Não deixar duas implementações da mesma funcionalidade.

==================================================
17. PRESERVAR ARQUITETURA COMPARTILHADA DE PAGAMENTO
==================================================

NÃO regredir os componentes compartilhados:

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

Venda Rápida e Mesa devem continuar usando os mesmos elementos.

==================================================
18. PRESERVAR PAGAMENTO NO RESUMO DA MESA
==================================================

Manter:

RESUMO DA MESA

...
Total oficial

[ PAGAMENTO ]

[ SALVAR E ENVIAR PEDIDO ]

Não devolver Pagamento ao AppBar.

Desktop e mobile devem continuar usando o mesmo painel de resumo.

==================================================
19. NÃO MEXER EM COMANDA LEGADO
==================================================

Não alterar fluxo legado de Comanda nesta fase.

Não usar Comanda como justificativa para ampliar escopo.

==================================================
20. TESTES / CHECKS
==================================================

NÃO criar nova bateria pesada de Widget/E2E.

O teste funcional final será feito manualmente por mim.

Pode rodar checks estáticos e backend direcionado.

Obrigatório no final:

- flutter analyze
- git diff --check
- python manage.py check
- makemigrations --check --dry-run

Se backend mudou:
rodar testes direcionados relacionados a:

- POS cash context;
- abertura de caixa;
- seleção FLEXIBLE;
- fechamento de caixa;
- Quick Sale;
- Table Payment;
- Table Close.

==================================================
21. CENÁRIOS QUE O CÓDIGO DEVE SUPORTAR
==================================================

A. FIXED:

abrir Caixa
→ active_cash_session definida
→ Venda Rápida funciona
→ Mesa funciona.

B. FLEXIBLE:

Caixa A aberto
→ selecionar Caixa A
→ active_cash_session=A
→ Venda/Mesa usam A.

C. FLEXIBLE selecionar caixa inválido:

POS permanece no contexto anterior.

D. Fechar Caixa:

active_cash_session limpa
→ Venda/Mesa bloqueadas até novo Caixa ativo.

E. Venda Rápida:

checkout iniciado no Caixa A
→ trocar POS para Caixa B
→ novo pagamento do checkout A deve ser rejeitado.

F. Mesa:

primeiro pagamento no Caixa A
→ trocar POS para Caixa B
→ segundo pagamento da mesma Mesa deve ser rejeitado ANTES de gravar.

G. Pending Mesa:

timeout
→ fechar app
→ checkout-options falhar
→ pending continua preservado.

H. Pagar Saldo em Dinheiro:

PAGAR SALDO
→ informar recebido maior
→ mode continua remaining
→ troco correto.

==================================================
22. CHECKPOINT FINAL
==================================================

Quando concluir, informe objetivamente:

1. como corrigiu o device stale após abrir Caixa;
2. como corrigiu o device stale após selecionar Caixa;
3. como corrigiu a seleção FLEXIBLE no Flutter;
4. qual permissão protege seleção de caixa;
5. onde active_cash_session vive;
6. como FIXED funciona;
7. como FLEXIBLE funciona;
8. como Venda Rápida consome CashSession;
9. como Mesa consome CashSession;
10. como impediu Mesa de misturar sessões;
11. como Venda Rápida trata mudança de contexto;
12. como funciona fechamento de Caixa;
13. como `current_pos_cash_session` faz lock;
14. como corrigiu pending;
15. como corrigiu PAGAR SALDO + valor recebido;
16. como corrigiu equal_split.active;
17. qual código morto foi removido;
18. confirmação de que não existe seletor de caixa em Venda/Mesa/Pagamento;
19. confirmação de que PAGAMENTO continua no RESUMO DA MESA;
20. arquivos alterados;
21. flutter analyze;
22. git diff --check;
23. Django check;
24. migrations check;
25. testes backend direcionados executados.

DEPOIS PARE.

NÃO INICIE IMPRESSÃO.

DEPOIS DESSA FASE EU VOU VALIDAR MANUALMENTE:

CAIXA
+
VENDA RÁPIDA
+
MESA
+
PAGAMENTOS

SÓ DEPOIS DA VALIDAÇÃO COMEÇAREMOS:

- NOTINHA / RESUMO / DOCUMENTO NÃO FISCAL;
- IMPRESSÃO DE PRODUÇÃO POR SETOR.