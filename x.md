CONTINUE A MESMA FASE E CORRIJA OS 500 AGORA.

FONTE DE VERDADE:
HEAD ATUAL DA MAIN.

NÃO INICIE:
- impressão;
- Stone;
- Cielo;
- PagBank;
- fiscal;
- outra fase.

NÃO MEXER EM COMANDA LEGADO.

A arquitetura atual deve ser PRESERVADA:

CashSession pertence ao POSDevice / módulo CAIXA.

Venda Rápida, Mesa e Pagamentos consomem o contexto ativo do POS.

NÃO VOLTAR A COLOCAR seletor de caixa em:
- Venda Rápida;
- Mesa;
- Pagamento;
- Dinheiro;
- fechamento da Mesa.

==================================================
1. BLOCKER 500 — POSCashSessionSelectView
==================================================

Hoje existe:

class POSCashSessionSelectView(POSCashView):
    ...
    self._require(...)

PROBLEMA:

POSCashView NÃO possui `_require()`.

Esse helper existe em outras subclasses como:
- POSQuickSaleView;
- POSAttendanceView;

mas NÃO em POSCashView.

Resultado real:

FLEXIBLE
→ selecionar outro caixa
→ AttributeError
→ HTTP 500.

ERRO CONFIRMADO:

'POSCashSessionSelectView' object has no attribute '_require'

CORRIGIR.

==================================================
2. REGRA ESPERADA PARA PERMISSÃO FLEXIBLE
==================================================

Selecionar outro caixa em modo FLEXIBLE deve exigir:

cash_registers.open

Comportamento esperado:

COM permissão:
→ 200
→ active_cash_session atualizada.

SEM permissão:
→ 403
→ active_cash_session permanece inalterada.

Caixa não disponível:
→ 409.

NUNCA retornar 500.

Use mecanismo de permission check apropriado para POSCashView.

Pode:
- adicionar helper genérico apropriado em POSCashView;
- ou fazer validação explícita nessa view;
- ou reutilizar mecanismo já existente.

Evitar duplicação desnecessária.

==================================================
3. BLOCKER 500 — POSQuickCheckoutPaymentView
==================================================

Hoje existe na View:

session = current_pos_cash_session(
    device,
    for_update=True,
)

PROBLEMA:

`current_pos_cash_session(..., for_update=True)` executa:

select_for_update()

no POSDevice e na CashSession.

Mas `POSQuickCheckoutPaymentView.post()` NÃO está dentro de
`transaction.atomic()`.

Resultado real:

TransactionManagementError:
select_for_update cannot be used outside of a transaction.

Isso está causando:

POST
/api/v1/pos/sales/checkouts/<id>/payments/
→ HTTP 500.

CORRIGIR A ARQUITETURA TRANSACIONAL.

==================================================
4. NÃO RESOLVER APENAS COM for_update=False
==================================================

NÃO fazer simplesmente:

current_pos_cash_session(
    device,
    for_update=False,
)

só para remover o erro.

Isso abriria janela de race condition:

lê Caixa A
↓
contexto muda para B
↓
pagamento continua usando informação antiga.

Queremos manter a proteção de concorrência.

==================================================
5. RESOLUÇÃO RECOMENDADA
==================================================

`record_quick_checkout_payment()` já é:

@transaction.atomic

Portanto a resolução/lock do contexto ativo deve acontecer
DENTRO do serviço transacional.

Fluxo recomendado:

record_quick_checkout_payment(...)
↓
transaction.atomic
↓
lock POSDevice
↓
resolver active_cash_session
↓
lock CashSession
↓
lock checkout
↓
validar:
checkout.cash_session == active POS CashSession
↓
registrar pagamento.

Ou solução equivalente que mantenha:
- lock;
- atomicidade;
- consistência.

A View NÃO deve ser responsável por lock transacional de domínio.

==================================================
6. EVOLUIR CONTRATO DO SERVIÇO
==================================================

Preferência:

em vez de a View resolver:

active_cash_session_id=session.pk

ela deve passar o contexto necessário ao serviço, por exemplo:

pos_device=device

E o serviço resolve server-side dentro da transaction.

Conceitualmente:

@transaction.atomic
def record_quick_checkout_payment(..., pos_device):
    active_session = current_pos_cash_session(
        pos_device,
        for_update=True,
    )

    checkout_session, checkout, ... = _lock_checkout_session(...)

    if checkout_session.pk != active_session.pk:
        raise QuickCheckoutConflict(
            'cash_context_changed',
            ...
        )

    ...

Não precisa usar exatamente essa assinatura,
mas preservar essa responsabilidade no domínio.

==================================================
7. NÃO PERDER A PROTEÇÃO cash_context_changed
==================================================

Venda Rápida deve continuar protegida:

checkout criado no Caixa A
↓
POS muda para Caixa B
↓
novo pagamento do checkout A
↓
rejeitado com conflito apropriado.

NÃO permitir pagamento em contexto diferente.

NÃO transformar isso em 500.

Resposta deve ser domínio controlado, por exemplo 409.

==================================================
8. PROCURAR TODOS OS for_update=True FORA DE TRANSACTION
==================================================

Não corrigir somente a linha 1881.

Revisar TODOS os usos de:

current_pos_cash_session(..., for_update=True)

principalmente em:
- Views;
- serializers;
- helpers HTTP;
- qualquer camada fora de @transaction.atomic.

Qualquer select_for_update deve executar dentro de transaction.atomic.

==================================================
9. POSFinalizeSaleView TAMBÉM ESTÁ SUSPEITO
==================================================

No HEAD atual existe também:

POSFinalizeSaleView
→ current_pos_cash_session(device, for_update=True)

diretamente na View.

Isso pode gerar o MESMO:

TransactionManagementError

se esse endpoint for acionado.

Corrigir o padrão também nele.

Não deixar outro 500 escondido.

==================================================
10. SERVIÇOS DEVEM SER DONOS DA TRANSAÇÃO
==================================================

Regra arquitetural:

VIEW:
- autentica;
- valida request;
- verifica permissão;
- chama domínio.

SERVICE:
- inicia transaction;
- faz select_for_update;
- valida consistência;
- grava.

Evitar espalhar `transaction.atomic()` apenas para mascarar erro de View.

Se algum endpoint realmente precisar de transaction na View,
justificar claramente.

==================================================
11. PRESERVAR current_pos_cash_session
==================================================

Não remover a segurança que já foi implementada:

current_pos_cash_session(for_update=True)

deve continuar capaz de:

- lockar POSDevice;
- ler active_cash_session_id;
- lockar CashSession;
- validar sessão OPEN;
- validar mesma filial;
- validar CashRegister ACTIVE;
- validar FIXED.

O problema NÃO está no helper.

O problema está em chamar o helper com lock fora de transaction.

==================================================
12. CORRIGIR TESTES DE TABLE ATTENDANCE QUE NEM EXECUTAM
==================================================

O CI anterior mostrou que os testes de:

TableAttendanceRegressionTests

morriam no setUp antes de testar a regra.

Erro:

Stock com este Product e Branch já existe.

Hoje o setUp ainda possui algo equivalente a:

Stock.objects.create(
    product=self.product,
    branch=self.branch,
    ...
)

Mas a criação/configuração anterior já pode gerar Stock.

CORRIGIR O FIXTURE.

Não furar validação do model.

Não apagar constraint.

Usar abordagem correta, por exemplo:
- get_or_create;
- update do estoque existente;
- serviço oficial de estoque;
- ou outra forma coerente com o projeto.

Objetivo:

os testes DEVEM chegar na lógica que pretendem validar.

==================================================
13. TESTES DIRECIONADOS OBRIGATÓRIOS
==================================================

Corrigir/validar explicitamente:

A. FLEXIBLE com permissão:
→ selecionar Caixa
→ 200.

B. FLEXIBLE sem cash_registers.open:
→ 403.

C. FLEXIBLE caixa indisponível:
→ 409.

D. Nenhum desses casos retorna 500.

E. Quick Sale:
→ pagamento com Caixa ativo correto
→ sucesso.

F. Quick Sale:
→ checkout Caixa A
→ muda POS para Caixa B
→ pagamento rejeitado com cash_context_changed
→ sem 500.

G. Quick Sale:
→ fluxo normal não gera TransactionManagementError.

H. POSFinalizeSaleView:
→ confirmar que não executa select_for_update fora de transaction.

I. Mesa:
→ testes de regressão realmente executam e não morrem no setUp.

==================================================
14. NÃO REGREDIR AS CORREÇÕES JÁ FEITAS
==================================================

Preservar:

- POSDevice.active_cash_session;
- CashSession como contexto do POS;
- CashSession não sendo escolhida no pagamento;
- Mesa bloqueando múltiplas sessões ativas;
- Mesa após estorno podendo assumir novo contexto;
- fechamento da Mesa usando somente pagamentos ativos;
- fechamento da CashSession bloqueado por PIX/Crédito/Débito/etc
  quando Mesa continua aberta;
- backspace do PAGAR SALDO;
- pending da Mesa;
- equal_split available/active;
- componentes compartilhados de pagamento;
- Pagamento dentro do Resumo da Mesa.

==================================================
15. SOBRE OS WIDGET TESTS
==================================================

Foram adicionados testes Flutter em:

pos/test/payment_flow_components_test.dart

NÃO ampliar essa bateria.

O teste funcional final será feito manualmente.

Se esses 2 testes simples forem mantidos,
não criar nova suíte Widget/E2E nesta fase.

Prioridade agora é corrigir os blockers reais.

==================================================
16. CHECKS
==================================================

Ao terminar rode:

- flutter analyze
- git diff --check
- python manage.py check
- makemigrations --check --dry-run

E testes backend DIRECIONADOS para:

- POSCashSessionSelectView;
- POS cash context;
- Quick Checkout Payment;
- Quick Checkout cash context change;
- POSFinalizeSale;
- Table Attendance regression;
- Cash Session Close.

==================================================
17. CI
==================================================

O commit deve subir com esses blockers resolvidos.

Depois conferir o GitHub Actions.

Se o backend continuar vermelho:

informar quais falhas são:
- diretamente relacionadas a esta fase;
- preexistentes de outras áreas.

NÃO declarar esta fase concluída se os testes desta fase
continuarem falhando.

==================================================
18. CHECKPOINT FINAL
==================================================

Ao concluir informe objetivamente:

1. por que POSCashSessionSelectView dava 500;
2. como corrigiu;
3. comportamento com permissão;
4. comportamento sem permissão;
5. por que POSQuickCheckoutPaymentView dava TransactionManagementError;
6. onde o lock passou a acontecer;
7. como a transaction agora envolve o lock;
8. como preservou cash_context_changed;
9. se POSFinalizeSaleView tinha o mesmo risco;
10. como foi corrigido;
11. todos os usos revisados de current_pos_cash_session(for_update=True);
12. como corrigiu o fixture duplicado de Stock;
13. testes direcionados executados;
14. flutter analyze;
15. git diff --check;
16. Django check;
17. migrations check;
18. status final do CI;
19. confirmação de que não há seletor de caixa em Venda/Mesa/Pagamento;
20. confirmação de que não iniciou impressão.

DEPOIS PARE.

NÃO INICIE IMPRESSÃO.

DEPOIS EU VOU:

1. auditar o GitHub novamente;
2. testar manualmente:
   - Caixa;
   - Venda Rápida;
   - Mesa;
   - Pagamentos.

SÓ DEPOIS PASSAMOS PARA:

- NOTINHA / RESUMO / DOCUMENTO NÃO FISCAL;
- IMPRESSÃO DE PRODUÇÃO.