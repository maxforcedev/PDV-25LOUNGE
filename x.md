CONTINUE A MESMA FASE A PARTIR DO HEAD ATUAL.

OBJETIVO:
FECHAR TODOS OS PROBLEMAS RESTANTES DESTA RODADA SEM REGREDIR A ARQUITETURA JÁ CORRIGIDA.

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
1. DECISÃO DE UI/UX — NÃO RECOLOCAR TEXTOS REMOVIDOS
==================================================

As descrições removidas do Backoffice foram removidas INTENCIONALMENTE.

Objetivo visual:
deixar as telas mais limpas e com menos texto explicando o óbvio.

Portanto NÃO quero recolocar:

- notas explicativas dos KPIs do Dashboard;
- descriptions dos EmptyStates onde foram removidas;
- textos auxiliares removidos de Caixas;
- textos auxiliares removidos de Vendas;
- descrições redundantes de modais;
- subtítulos desnecessários.

NÃO resolver o TypeScript adicionando novamente esses textos.

==================================================
2. CORRIGIR Kpi PARA `note` OPCIONAL
==================================================

Hoje o componente Kpi exige:

note: string

Mas agora vários KPIs devem funcionar apenas com:

- label;
- value;
- icon;
- href/tone quando aplicável.

Alterar o contrato para:

note?: string

E renderizar o elemento visual da note SOMENTE se existir conteúdo.

Exemplo desejado:

Faturamento
R$ 25.000

e NÃO:

Faturamento
R$ 25.000
Faturamento comercial no período

Não usar:

note=""

como gambiarra.

O componente deve suportar ausência real da propriedade.

==================================================
3. CORRIGIR EmptyState PARA `description` OPCIONAL
==================================================

Hoje EmptyState exige:

description: string

Alterar para:

description?: string

Renderizar a descrição somente quando existir.

Exemplo:

Carrinho vazio

em vez de:

Carrinho vazio
Toque em um produto do catálogo para adicionar.

Não passar string vazia apenas para satisfazer TypeScript.

==================================================
4. PRESERVAR HIERARQUIA E ESPAÇAMENTO
==================================================

Ao tornar note/description opcionais:

não deixar:
- espaço vazio;
- margin/padding sobrando;
- altura reservada;
- gap visual estranho.

Se não houver texto secundário, o componente deve compactar naturalmente.

==================================================
5. NÃO GENERALIZAR ERRADO
==================================================

Não remover textos úteis de telas que ainda precisam deles.

A decisão é:

TEXTO SECUNDÁRIO DEVE SER OPCIONAL.

Não:

"Toda description do sistema deve desaparecer."

Preservar instruções quando forem realmente necessárias para:
- segurança;
- erro;
- confirmação;
- comportamento não óbvio;
- contexto importante da operação.

==================================================
6. 500 DO FLEXIBLE — PRESERVAR CORREÇÃO
==================================================

O problema anterior:

POSCashSessionSelectView
→ self._require inexistente
→ AttributeError
→ HTTP 500

já foi corrigido usando mecanismo válido em POSCashView.

PRESERVAR.

Comportamento final obrigatório:

com `cash_registers.open`
→ 200.

sem `cash_registers.open`
→ 403.

caixa sem sessão disponível
→ 409.

nunca 500.

==================================================
7. 500 DO QUICK CHECKOUT PAYMENT — PRESERVAR CORREÇÃO
==================================================

O problema anterior:

current_pos_cash_session(device, for_update=True)

sendo chamado na View fora de transaction.atomic

gerava:

TransactionManagementError:
select_for_update cannot be used outside of a transaction.

A correção atual moveu essa responsabilidade para:

record_quick_checkout_payment()

que já roda em:

@transaction.atomic

e recebe:

pos_device=device.

PRESERVAR ESSA ARQUITETURA.

A View NÃO deve voltar a realizar lock de domínio.

==================================================
8. QUICK SALE — ORDEM TRANSACIONAL
==================================================

Manter conceitualmente:

record_quick_checkout_payment()
↓
transaction.atomic
↓
lock POSDevice
↓
resolve active_cash_session
↓
lock CashSession
↓
lock checkout
↓
valida contexto
↓
registra pagamento

Se:

checkout pertence ao Caixa A

mas POS atualmente está no Caixa B:

retornar conflito controlado:

cash_context_changed

e NÃO 500.

==================================================
9. POSFinalizeSaleView — PRESERVAR CORREÇÃO
==================================================

A View também não deve chamar:

current_pos_cash_session(..., for_update=True)

fora da transaction.

Manter a resolução dentro de:

finalize_sale()

que já é:

@transaction.atomic

Para venda direta POS no COUNTER:

- resolve CashSession do POSDevice no serviço;
- mantém lock;
- mantém validação de filial;
- mantém segurança server-side.

==================================================
10. REVISAR TODOS OS `current_pos_cash_session(for_update=True)`
==================================================

Faça uma busca no projeto.

Todos os usos com:

for_update=True

devem estar dentro de fluxo transacional real.

Já existem usos corretos em serviços como:
- create_quick_checkout;
- update_quick_checkout;
- record_quick_checkout_payment;
- record_table_payment;
- close_table_attendance;
- finalize_sale.

Confirmar que nenhum uso restante está em View ou camada HTTP fora de transaction.

==================================================
11. FIXTURE DE STOCK — PRESERVAR CORREÇÃO
==================================================

Os testes estavam falhando porque tentavam:

Stock.objects.create(...)

mesmo quando a criação/configuração do produto já gerava Stock.

A correção atual reutiliza:

Stock.objects.get(...)

e atualiza os valores.

PRESERVAR.

Não:
- remover constraint;
- criar Stock duplicado;
- furar validação do model.

==================================================
12. NÃO REGREDIR CASHSESSION GLOBAL DO POS
==================================================

CashSession continua pertencendo ao contexto operacional do POSDevice.

Não pertence:
- à Venda Rápida;
- à Mesa;
- ao método Dinheiro;
- à tela de Pagamento.

Fluxo:

CAIXA
→ define POSDevice.active_cash_session
→ Venda Rápida / Mesa usam automaticamente.

Nenhum seletor de caixa deve reaparecer dentro de pagamento.

==================================================
13. NÃO REGREDIR MESA
==================================================

Preservar tudo que já foi corrigido:

- pagamentos ativos definem o contexto financeiro atual;
- pagamento estornado não prende a Mesa para sempre ao contexto anterior;
- após estorno total, Mesa pode assumir novo caixa;
- pagamentos ativos em duas CashSessions são rejeitados;
- fechamento usa somente pagamentos ativos;
- PIX/Crédito/Débito/etc também pertencem à CashSession operacional;
- Mesa aberta com pagamento ativo impede fechamento daquela CashSession;
- Mesa fechada não deve continuar bloqueando o caixa.

==================================================
14. NÃO REGREDIR PAGAR SALDO
==================================================

Preservar:

PAGAR SALDO
→ payingRemaining=true.

Editar VALOR RECEBIDO:
→ continua true.

Backspace no VALOR RECEBIDO:
→ continua true.

Editar VALOR APLICADO:
→ false.

Backspace no VALOR APLICADO:
→ false.

==================================================
15. NÃO REGREDIR PENDING DA MESA
==================================================

Pending persistido continua existindo mesmo se:

- checkout-options falhar;
- payment methods não carregarem;
- DTO não puder ser reconstruído temporariamente.

Só limpar pending após:
- confirmação pelo ledger/idempotency_key;
ou
- resolução explícita segura.

==================================================
16. NÃO REGREDIR EQUAL SPLIT
==================================================

Antes de iniciar divisão:

available = true
active = false

Depois que existe ciclo real:

active = true.

Não voltar a usar active=true apenas porque a divisão é possível.

==================================================
17. NÃO REGREDIR COMPONENTES COMPARTILHADOS
==================================================

Venda Rápida e Mesa devem continuar usando os mesmos componentes de pagamento.

Preservar:

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

==================================================
18. PAGAMENTO CONTINUA NO RESUMO DA MESA
==================================================

Preservar:

RESUMO DA MESA
...
TOTAL

[ PAGAMENTO ]

[ SALVAR E ENVIAR PEDIDO ]

Não devolver Pagamento para AppBar/menu superior.

==================================================
19. FRONTEND BUILD
==================================================

Corrigir os erros atuais de TypeScript CAUSADOS pela remoção intencional de textos.

Já identificados:

Dashboard:
Kpi sem `note`.

Sales PDV:
EmptyState sem `description`.

A solução é ajustar os contratos/componentes,
NÃO recolocar os textos.

Depois executar build completo do Frontend.

==================================================
20. NÃO SAIR CAÇANDO WARNINGS FORA DO ESCOPO
==================================================

Existem warnings ESLint antigos no Frontend.

Não transformar esta missão em limpeza geral do projeto.

Corrigir:
- errors de build;
- regressões introduzidas por esta rodada;
- problemas diretamente relacionados à fase atual.

Warnings antigos podem permanecer para revisão futura,
desde que não sejam erros/blockers.

==================================================
21. BACKEND CI
==================================================

Aguardar/rodar os testes backend.

Se houver falha:

se for desta fase:
→ CORRIGIR.

Exemplos:
- CashSession;
- POS FLEXIBLE;
- Quick Checkout;
- Venda Rápida;
- Mesa;
- pagamento;
- fechamento de caixa;
- fixtures modificados nesta rodada.

Se for falha comprovadamente preexistente e fora da fase:
→ informar separadamente;
→ não ampliar escopo sem necessidade.

==================================================
22. NÃO CRIAR NOVA BATERIA PESADA DE TESTES FLUTTER
==================================================

O teste FUNCIONAL final será feito manualmente por mim.

Já existem alguns testes simples adicionados.

Não ampliar agora para nova suíte pesada Widget/E2E.

Prioridade:
corrigir funcionamento real e checks necessários.

==================================================
23. CHECKS OBRIGATÓRIOS
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
24. TESTES BACKEND DIRECIONADOS
==================================================

Validar especificamente:

A. FLEXIBLE com permissão
→ 200.

B. FLEXIBLE sem permissão
→ 403.

C. FLEXIBLE sem sessão disponível
→ 409.

D. Quick Sale pagamento normal
→ funciona.

E. Quick Sale checkout Caixa A
→ POS muda para B
→ pagamento rejeitado com cash_context_changed.

F. Nenhum Quick Checkout Payment gera:
TransactionManagementError.

G. POSFinalizeSale
→ usa active CashSession dentro do serviço transacional.

H. Mesa:
→ pagamento;
→ estorno;
→ troca de caixa;
→ novo pagamento;
→ fechamento.

I. Mesa com PIX/Crédito ativa
→ bloqueia fechamento da CashSession enquanto Mesa está aberta.

J. Testes de TableAttendance realmente executam
e não morrem no setup do Stock.

==================================================
25. CHECKPOINT FINAL
==================================================

No final informe objetivamente:

1. como deixou Kpi.note opcional;
2. como deixou EmptyState.description opcional;
3. confirmação de que NÃO recolocou os textos removidos;
4. confirmação de que não ficaram espaços vazios nos componentes;
5. status do Frontend build;
6. status do Frontend lint;
7. confirmação do fix do POSCashSessionSelectView;
8. resultado 200/403/409 do FLEXIBLE;
9. confirmação de ausência de 500;
10. confirmação do fix transacional do Quick Checkout Payment;
11. onde current_pos_cash_session(for_update=True) é executado;
12. confirmação de cash_context_changed funcionando;
13. confirmação do POSFinalizeSale sem lock na View;
14. resultado dos testes de TableAttendance;
15. resultado do fixture de Stock;
16. Django check;
17. migrations check;
18. flutter analyze;
19. git diff --check;
20. status final do GitHub Actions;
21. quais falhas restantes, se houver, são desta fase;
22. quais falhas restantes, se houver, são preexistentes;
23. confirmação de que CashSession continua global no POSDevice;
24. confirmação de que não há seletor em Venda/Mesa/Pagamento;
25. confirmação de que PAGAMENTO continua no RESUMO DA MESA.

DEPOIS PARE.

NÃO INICIE IMPRESSÃO.

DEPOIS DISSO:

EU VOU AUDITAR O GITHUB NOVAMENTE.

PASSANDO A AUDITORIA, EU FAÇO O TESTE MANUAL DE:

- CAIXA;
- VENDA RÁPIDA;
- MESA;
- PAGAMENTOS.

SÓ DEPOIS COMEÇAMOS:

- NOTINHA / RESUMO / DOCUMENTO NÃO FISCAL;
- IMPRESSÃO DE PRODUÇÃO.