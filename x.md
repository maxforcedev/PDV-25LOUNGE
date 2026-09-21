CONTINUE A MESMA FASE A PARTIR DO HEAD ATUAL.

OBJETIVO:
FECHAR OS ÚLTIMOS BLOCKERS DESTA ETAPA SEM REGREDIR O QUE JÁ FOI CORRIGIDO.

NÃO INICIE:
- impressão;
- Stone;
- Cielo;
- PagBank;
- fiscal;
- outra fase;
- Comanda nova.

NÃO MEXER EM COMANDA LEGADO.

==================================================
1. BLOCKER — FOR UPDATE EM TABLEPAYMENT COM JOIN NULLABLE
==================================================

O CI mostrou erro real de PostgreSQL:

FOR UPDATE cannot be applied to the nullable side of an outer join

Hoje existem queries em Mesa como:

TablePayment.objects.select_for_update().filter(
    attendance=attendance,
    status=APPLIED,
    reversal__isnull=True,
)

e também no fechamento:

TablePayment.objects
    .select_for_update()
    .select_related(
        'payment_method',
        'cash_session',
    )
    .filter(
        attendance=attendance,
        status=APPLIED,
        reversal__isnull=True,
    )

O problema é que:

- `reversal` é relação reversa OneToOne opcional;
- `cash_session` também é nullable;
- o Django pode gerar OUTER JOIN;
- PostgreSQL não aceita FOR UPDATE no lado nullable desse join.

CORRIGIR.

==================================================
2. NÃO REMOVER O LOCK
==================================================

NÃO resolver tirando:

select_for_update()

O lock é necessário para:

- impedir concorrência entre pagamentos;
- impedir mistura de contextos;
- preservar integridade do ledger;
- sincronizar pagamento/estorno/fechamento.

Corrigir a estratégia de lock.

==================================================
3. ESTRATÉGIA RECOMENDADA
==================================================

Travar somente a tabela principal:

TablePayment

Exemplo conceitual:

TablePayment.objects.select_for_update(
    of=('self',)
)

quando for suficiente.

Se a query com:

reversal__isnull=True

continuar produzindo join problemático:

separar em etapas.

Exemplo conceitual:

1. lockar TablePayment base;
2. buscar/filtrar os IDs necessários;
3. carregar relações nullable separadamente;
4. aplicar regra de negócio.

Não precisa usar exatamente essa implementação.

O importante é:

- manter o lock;
- evitar FOR UPDATE sobre lado nullable de outer join;
- preservar atomicidade.

==================================================
4. RECORD_TABLE_PAYMENT
==================================================

Revisar especificamente:

record_table_payment()

Hoje ele precisa:

- lockar Attendance;
- resolver active CashSession;
- lockar pagamentos existentes;
- identificar sessões ativas existentes;
- impedir novo pagamento em outra CashSession;
- registrar pagamento.

Essa consulta de pagamentos existentes NÃO pode gerar:

FOR UPDATE cannot be applied to the nullable side of an outer join.

Preservar regra:

pagamentos ativos:
- status APPLIED;
- não estornados;

definem o contexto financeiro atual.

==================================================
5. CLOSE_TABLE_ATTENDANCE
==================================================

Revisar:

close_table_attendance()

Hoje ele precisa:

- lockar Attendance;
- calcular estado financeiro;
- lockar pagamentos ativos;
- confirmar saldo zero;
- validar CashSession atual;
- materializar Sale;
- fechar Attendance.

Não usar select_for_update em queryset com joins nullable que causem erro no PostgreSQL.

Carregar:

payment_method
cash_session

de forma segura.

==================================================
6. NÃO REGREDIR REGRA DE ESTORNO
==================================================

Preservar:

Pagamento Caixa A
→ estorno total
→ troca POS para Caixa B
→ novo pagamento no B
→ fechar Mesa normalmente.

Pagamentos já estornados NÃO devem prender a Mesa ao contexto anterior.

Mas continuam preservados no histórico/auditoria.

==================================================
7. NÃO REGREDIR MÚLTIPLAS CASH SESSIONS
==================================================

Preservar:

Mesa com pagamento ativo no Caixa A
→ POS muda para Caixa B
→ novo pagamento deve ser rejeitado ANTES de gravar.

Se por inconsistência existirem pagamentos ativos em mais de uma CashSession:

fechamento deve rejeitar.

==================================================
8. FECHAMENTO DA CASH SESSION
==================================================

Preservar regra nova:

Mesa aberta com qualquer TablePayment ativo naquela CashSession
impede fechamento do Caixa.

Independentemente do método:

- Dinheiro;
- PIX;
- Crédito;
- Débito;
- Benefício;
- outros.

Mesa fechada NÃO deve continuar bloqueando fechamento da CashSession.

==================================================
9. CORRIGIR TESTE FIXED
==================================================

O teste:

test_bootstrap_reports_fixed_and_flexible_cash_state_without_fake_selection

está inconsistente com a arquitetura nova.

Hoje:

CashSession só é contexto ativo se estiver vinculada em:

POSDevice.active_cash_session

Não basta existir uma sessão OPEN no CashRegister.

Portanto corrigir o teste para:

- criar/obter o device;
- configurar FIXED;
- abrir sessão;
- definir active_cash_session corretamente;
- chamar bootstrap;
- validar estado.

NÃO alterar produção para fazer seleção "fake" automática só para o teste passar.

A fonte da verdade continua sendo:

POSDevice.active_cash_session

==================================================
10. CORRIGIR TESTE FLEXIBLE INDISPONÍVEL
==================================================

O teste:

test_flexible_cash_selection_rejects_unavailable_register

está morrendo antes da regra testada.

Hoje usa algo como:

open_session(
    active_register,
    ...,
    self.owner,
    ...,
    allow_pos_only=True,
)

e recebe:

PermissionDenied:
Você não possui permissão nesta filial.

CORRIGIR O FIXTURE/ATOR DO TESTE.

Usar operador/usuário coerente com:

allow_pos_only=True

ou abrir sessão pelo fluxo correto.

Objetivo do teste:

- existir uma sessão ativa válida no POS;
- tentar selecionar outro CashRegister sem sessão aberta;
- endpoint retornar 409;
- active_cash_session permanecer inalterada.

O teste precisa chegar nessa regra.

==================================================
11. NÃO MASCARAR TESTES
==================================================

Não:
- pular testes;
- remover asserts;
- afrouxar validações;
- desativar constraint;
- trocar comportamento só para verde.

Corrigir fixture/setup e lógica real.

==================================================
12. PAGEHEADER — DESCRIPTION DEVE SER OPCIONAL
==================================================

DECISÃO DE UI/UX:

Quero o Backoffice mais limpo.

Hoje `PageHeader` exige:

description: string

e algumas telas estão passando:

description=""

Isso não é o padrão desejado.

Alterar contrato para:

description?: string

==================================================
13. PAGEHEADER — RENDERIZAÇÃO CONDICIONAL
==================================================

Hoje existe algo como:

<p className="mt-1 text-xs text-muted">
  {description}
</p>

Alterar para renderizar SOMENTE se existir conteúdo.

Exemplo conceitual:

{description ? (
  <p className="mt-1 ...">
    {description}
  </p>
) : null}

Não deixar:

- `<p>` vazio;
- margin vazia;
- gap desnecessário;
- altura reservada.

==================================================
14. NÃO PASSAR description=""
==================================================

Nas telas onde o texto foi removido intencionalmente:

preferir:

<PageHeader
  title="Caixas"
/>

e não:

<PageHeader
  title="Caixas"
  description=""
/>

Remover strings vazias onde fizer sentido.

==================================================
15. PRESERVAR TEXTOS ÚTEIS
==================================================

Não transformar isso em remoção geral de todas as descriptions.

A regra é:

description é OPCIONAL.

Usar quando realmente ajuda.

Preservar textos necessários para:

- comportamento não óbvio;
- segurança;
- instruções importantes;
- contexto operacional relevante;
- erros;
- confirmações.

==================================================
16. PRESERVAR Kpi.note OPCIONAL
==================================================

Já foi corrigido:

note?: string

com renderização condicional.

Preservar.

Não recolocar os textos removidos do Dashboard.

==================================================
17. PRESERVAR EmptyState.description OPCIONAL
==================================================

Já foi corrigido:

description?: string

com renderização condicional.

Preservar.

Não recolocar:

"Toque em um produto..."

ou outros textos removidos intencionalmente só para preencher espaço.

==================================================
18. 500 DO FLEXIBLE
==================================================

Preservar correção:

POSCashSessionSelectView
usa mecanismo válido de permission check.

Comportamento:

com cash_registers.open
→ 200.

sem permissão
→ 403.

caixa sem sessão disponível
→ 409.

nunca 500.

==================================================
19. 500 DO QUICK SALE PAYMENT
==================================================

Preservar correção:

POSQuickCheckoutPaymentView
NÃO chama mais:

current_pos_cash_session(..., for_update=True)

na View.

O lock acontece dentro de:

record_quick_checkout_payment()

que roda em:

@transaction.atomic

Preservar.

==================================================
20. POS FINALIZE
==================================================

Preservar:

POSFinalizeSaleView
não faz lock de CashSession na camada HTTP.

A resolução acontece em:

finalize_sale()

dentro da transaction.

==================================================
21. current_pos_cash_session(for_update=True)
==================================================

Revisar novamente todos os usos atuais.

Todos devem estar dentro de fluxo transacional real.

Não deixar:

select_for_update

fora de:

transaction.atomic.

==================================================
22. CASHSESSION GLOBAL
==================================================

Preservar arquitetura definitiva:

CAIXA
→ POSDevice.active_cash_session
→ Venda Rápida / Mesa / Pagamentos consomem.

NÃO existe seletor de caixa em:

- Venda Rápida;
- Mesa;
- Pagamento;
- Dinheiro;
- fechamento da Mesa.

==================================================
23. PENDING / PAGAR SALDO / EQUAL SPLIT
==================================================

Não regredir:

PENDING:
- não apagar por falha de options/methods;
- limpar só por reconciliação segura.

PAGAR SALDO:
- editar recebido não muda remaining;
- backspace no recebido não muda remaining;
- editar aplicado muda para value;
- backspace no aplicado muda para value.

EQUAL SPLIT:
antes de iniciar:
available=true
active=false

depois de ciclo real:
active=true.

==================================================
24. COMPONENTES COMPARTILHADOS
==================================================

Preservar arquitetura compartilhada entre Venda Rápida e Mesa:

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

Não criar implementações duplicadas novamente.

==================================================
25. PAGAMENTO NA MESA
==================================================

Preservar:

RESUMO DA MESA

...
TOTAL

[ PAGAMENTO ]

[ SALVAR E ENVIAR PEDIDO ]

Pagamento não volta para AppBar.

==================================================
26. NÃO CRIAR NOVA BATERIA PESADA DE TESTES
==================================================

Teste funcional final será feito manualmente por mim.

Pode corrigir/adicionar apenas testes backend direcionados
necessários para os blockers desta fase.

Não criar nova suíte pesada Widget/E2E.

==================================================
27. TESTES DIRECIONADOS
==================================================

Validar especificamente:

A.
record_table_payment
→ não gera erro de FOR UPDATE em outer join.

B.
Mesa sem pagamentos
→ fecha normalmente.

C.
Mesa paga
→ fecha normalmente.

D.
Mesa:
Caixa A
→ pagamento
→ estorno total
→ Caixa B
→ pagamento
→ fecha normalmente.

E.
Mesa:
pagamento ativo Caixa A
→ POS em B
→ novo pagamento rejeitado.

F.
Mesa:
PIX no Caixa A
→ CashSession A não pode fechar enquanto Mesa aberta.

G.
Mesa:
Crédito no Caixa A
→ CashSession A não pode fechar enquanto Mesa aberta.

H.
Mesa fechada
→ não bloqueia CashSession.

I.
FIXED bootstrap
→ active_cash_session real do POS é exibida.

J.
FLEXIBLE seleção de caixa indisponível
→ 409
→ active_cash_session não muda.

K.
FLEXIBLE sem permissão
→ 403.

L.
Quick Sale pagamento
→ sem TransactionManagementError.

M.
Quick Sale muda A → B
→ cash_context_changed.

==================================================
28. CHECKS
==================================================

Ao terminar:

FRONTEND:
- npm lint
- npm run build

BACKEND:
- python manage.py check
- python manage.py makemigrations --check --dry-run
- testes direcionados desta fase

POS:
- flutter analyze

GERAL:
- git diff --check

==================================================
29. GITHUB ACTIONS
==================================================

Depois subir o commit e conferir o CI.

Nesta fase, NÃO considerar concluído se ainda falharem testes ligados a:

- CashSession;
- POS FLEXIBLE;
- Quick Sale cash context;
- Table Payment;
- Table Close;
- Cash Session Close;
- fixtures alterados desta fase.

Se houver falhas antigas fora do escopo:

informar separadamente.

==================================================
30. CHECKPOINT FINAL
==================================================

No final informe:

1. qual query de TablePayment causava FOR UPDATE + outer join;
2. como corrigiu o lock;
3. como manteve atomicidade;
4. resultado de record_table_payment;
5. resultado de close_table_attendance;
6. confirmação de estorno A → B funcionando;
7. confirmação de múltiplas sessões ativas sendo rejeitadas;
8. confirmação de PIX/Crédito bloqueando fechamento do Caixa quando Mesa aberta;
9. como corrigiu o teste FIXED;
10. como corrigiu o teste FLEXIBLE indisponível;
11. resultado desses testes;
12. como deixou PageHeader.description opcional;
13. confirmação de que removeu description="" quando aplicável;
14. confirmação de ausência de espaço vazio no PageHeader;
15. confirmação de que Kpi.note continua opcional;
16. confirmação de que EmptyState.description continua opcional;
17. Frontend lint;
18. Frontend build;
19. Django check;
20. migrations check;
21. testes backend direcionados;
22. flutter analyze;
23. git diff --check;
24. status do GitHub Actions;
25. falhas restantes relacionadas à fase, se houver;
26. falhas preexistentes fora do escopo, se houver;
27. confirmação de que os dois 500 anteriores continuam resolvidos;
28. confirmação de CashSession global no POSDevice;
29. confirmação de ausência de seletor de caixa em Venda/Mesa/Pagamento;
30. confirmação de que não iniciou impressão.

DEPOIS PARE.

NÃO INICIE IMPRESSÃO.

DEPOIS DISSO:
1. eu audito o GitHub novamente;
2. eu faço o teste manual de:
   - Caixa;
   - Venda Rápida;
   - Mesa;
   - Pagamentos.

PASSANDO ESSA VALIDAÇÃO:

- NOTINHA / RESUMO / DOCUMENTO NÃO FISCAL;
- IMPRESSÃO DE PRODUÇÃO.