CONTINUE A MESMA FASE.

FONTE DE VERDADE:
ESTADO ATUAL DO PROJETO / HEAD ATUAL.

NÃO INICIE:
- impressão;
- Stone;
- Cielo;
- PagBank;
- fiscal;
- outra fase.

NÃO MEXER EM COMANDA LEGADO.

A arquitetura de CashSession como contexto global do POS está correta e deve ser preservada.

NÃO VOLTAR A COLOCAR seleção de caixa em:
- Venda Rápida;
- Mesa;
- Pagamento;
- Dinheiro;
- fechamento da Mesa.

Agora corrija SOMENTE os pontos abaixo.

==================================================
1. BLOCKER — REGRA DE CASH SESSION DA MESA APÓS ESTORNO
==================================================

Hoje existe uma inconsistência entre:

`record_table_payment()`

e

`close_table_attendance()`.

No registro de novo pagamento, o contexto da Mesa é inferido usando pagamentos:

- status APPLIED;
- sem reversal.

Ou seja, pagamentos efetivamente ativos.

Isso permite o cenário:

Caixa A
→ pagamento R$ 50
→ estorna R$ 50
→ troca POS para Caixa B
→ novo pagamento R$ 100 no B.

Até aí essa regra é válida.

PORÉM no fechamento da Mesa hoje existe algo equivalente a:

`historical_payments`

pegando pagamentos originais mesmo que já tenham sido estornados.

Resultado:

Pagamento original A estornado
+
Pagamento ativo B
↓
FECHAR MESA
↓
table_cash_session_mismatch

A Mesa fica paga e impossível de fechar.

CORRIGIR.

==================================================
2. USAR UMA ÚNICA DEFINIÇÃO DE CONTEXTO FINANCEIRO DA MESA
==================================================

A regra deve ser consistente em:

- registrar pagamento;
- estornar;
- fechar Mesa.

Recomendação:

O CONTEXTO FINANCEIRO ATUAL DA MESA É DETERMINADO
PELOS PAGAMENTOS ATIVOS.

Ou seja:

TablePayment:
- status APPLIED;
- reversal__isnull=True.

Se todos os pagamentos associados ao Caixa A forem estornados,
a Mesa pode posteriormente receber pagamentos no Caixa B.

O histórico do Caixa A permanece imutável para auditoria.

NÃO apagar ou alterar registros históricos.

Mas pagamentos totalmente estornados NÃO devem bloquear o fechamento
em um novo contexto válido.

==================================================
3. FECHAMENTO DA MESA DEVE USAR A MESMA REGRA
==================================================

No `close_table_attendance()`:

não comparar a CashSession atual com pagamentos antigos já totalmente estornados.

Validar somente os pagamentos financeiros ativos que efetivamente
compõem o saldo pago atual da Mesa.

Se existirem pagamentos ativos em mais de uma CashSession:

isso é inconsistência e o fechamento deve rejeitar.

Mas o registro de novos pagamentos já deve impedir esse estado antes.

==================================================
4. BLOCKER — FECHAMENTO DO CAIXA NÃO PODE CONSIDERAR SÓ DINHEIRO
==================================================

Na arquitetura nova:

CashSession não é "sessão de dinheiro".

CashSession é o CONTEXTO OPERACIONAL DO POS.

Portanto todos os pagamentos feitos durante esse contexto são vinculados à sessão:

- Dinheiro;
- PIX;
- Crédito;
- Débito;
- Benefício;
- outros.

Hoje `close_session()` ainda possui regra de Mesa semelhante a:

TablePayment.objects.filter(
    cash_session=session,
    payment_method__code='cash',
    status=APPLIED,
    reversal__isnull=True,
    attendance__status=OPEN,
)

Esse filtro:

`payment_method__code='cash'`

ESTÁ ERRADO para a arquitetura atual.

==================================================
5. BLOQUEAR FECHAMENTO DA CASH SESSION POR QUALQUER PAGAMENTO ATIVO DE MESA
==================================================

Se uma Mesa ainda está ABERTA e possui qualquer TablePayment ativo
vinculado àquela CashSession:

NÃO permitir fechar a CashSession.

Independentemente da forma de pagamento.

Exemplo:

Caixa A ativo
↓
Mesa 10
↓
PIX R$ 50

A Mesa continua aberta.

Nesse momento:

FECHAR CAIXA A

deve ser rejeitado.

Porque aquela Mesa ainda possui operação financeira ativa
vinculada ao contexto A.

==================================================
6. MOTIVO
==================================================

Não permitir:

Mesa aberta
Pagamento PIX → Caixa A
↓
fecha Caixa A
↓
abre Caixa B
↓
Mesa continua aberta

Isso criaria uma Mesa presa ao contexto anterior e impossibilitaria
ou confundiria novos pagamentos/fechamento.

O fechamento do caixa deve proteger operações abertas associadas
àquela sessão.

==================================================
7. NÃO LIMITAR ESSA REGRA A DINHEIRO
==================================================

Remover o filtro por:

payment_method__code='cash'

da verificação de TablePayment ativo ao fechar CashSession.

Avaliar a mesma coerência em outros fluxos POS novos.

NÃO alterar Comanda legado nesta fase além do necessário para
não quebrar o código existente.

==================================================
8. PAGAR SALDO — BACKSPACE
==================================================

Foi corrigido corretamente:

botões rápidos e teclado numérico do VALOR RECEBIDO
não mudam mais `_payingRemaining`.

Mas ainda revisar o BACKSPACE.

Hoje:

PAGAR SALDO
→ `_payingRemaining = true`

Se operador estiver editando VALOR APLICADO e apertar backspace:

o valor muda,

mas `_payingRemaining` pode continuar true.

Isso cria divergência:

UI mostra valor alterado,
mas request continua mode=remaining.

CORRIGIR.

Regra:

Se BACKSPACE alterar o VALOR APLICADO:

`_payingRemaining = false`

Se BACKSPACE alterar apenas VALOR RECEBIDO:

manter `_payingRemaining = true`.

A mesma regra vale para qualquer futura alteração manual do valor aplicado.

==================================================
9. PRESERVAR CORREÇÕES JÁ FEITAS
==================================================

NÃO regredir:

- `POSDevice.active_cash_session`;
- `current_pos_cash_session()`;
- lock separado de POSDevice e CashSession;
- `cash_state_for_device()` lendo estado atual;
- FLEXIBLE refletindo apenas seleção confirmada pelo backend;
- permissão `cash_registers.open` para selecionar Caixa;
- Mesa bloqueando novo pagamento se já possui pagamento ativo em outro caixa;
- pending da Mesa preservado mesmo sem payment methods carregados;
- equal_split:
  - available=true;
  - active=false antes do ciclo;
- PaymentEntryPage sem conhecimento de CashSession;
- ausência de seletor de caixa em Venda/Mesa/Pagamento;
- código antigo de Table Item Allocation removido.

==================================================
10. NÃO REGREDIR VENDA RÁPIDA
==================================================

Venda Rápida deve continuar:

checkout criado no contexto ativo do POS;

se POS trocar de CashSession durante checkout com contexto já definido:

novo pagamento incompatível é rejeitado.

Não alterar essa proteção.

==================================================
11. NÃO REGREDIR MESA
==================================================

Mesa deve continuar:

primeiro pagamento ativo
→ determina contexto financeiro atual.

Segundo pagamento em outro contexto
→ rejeitado antes de gravar.

Se todos os pagamentos anteriores forem estornados:

pode assumir novo contexto posteriormente.

Essa mesma definição deve ser usada no fechamento.

==================================================
12. TESTES DIRECIONADOS
==================================================

Adicionar/ajustar somente testes backend DIRECIONADOS necessários.

Não criar bateria pesada de Widget/E2E.

Cenários mínimos:

A.
Mesa
→ pagamento Caixa A
→ troca POS para B
→ segundo pagamento rejeitado.

B.
Mesa
→ pagamento Caixa A
→ estorno total
→ troca para B
→ novo pagamento em B permitido
→ Mesa fecha normalmente no B.

C.
Mesa aberta
→ pagamento PIX no Caixa A
→ tentativa de fechar Caixa A
→ fechamento rejeitado.

D.
Mesa aberta
→ pagamento Crédito no Caixa A
→ tentativa de fechar Caixa A
→ fechamento rejeitado.

E.
Mesa fechada
→ não deve continuar bloqueando fechamento da CashSession
por causa dos pagamentos já consolidados.

F.
PAGAR SALDO em dinheiro
→ informa recebido maior
→ backspace no recebido
→ continua mode=remaining.

G.
PAGAR SALDO
→ backspace no valor aplicado
→ deixa de ser mode=remaining.

==================================================
13. CHECKS
==================================================

Ao terminar rode:

- flutter analyze
- git diff --check
- python manage.py check
- makemigrations --check --dry-run

E testes backend direcionados para:

- Table Payment;
- Table Reverse;
- Table Close;
- Cash Session Close;
- Quick Sale cash context.

==================================================
14. CHECKPOINT FINAL
==================================================

Ao concluir informe objetivamente:

1. qual definição passou a determinar o contexto financeiro da Mesa;
2. como pagamentos estornados são tratados;
3. como o fechamento da Mesa usa essa mesma regra;
4. como impediu Mesa paga de ficar impossível de fechar;
5. como alterou a proteção de fechamento da CashSession;
6. confirmação de que PIX/Crédito/Débito também bloqueiam fechamento
   quando pertencem a Mesa aberta;
7. confirmação de que pagamentos de Mesa fechada não bloqueiam o Caixa;
8. correção do backspace de PAGAR SALDO;
9. confirmação de não regressão da Venda Rápida;
10. confirmação de ausência de seletor de caixa em pagamento;
11. arquivos alterados;
12. flutter analyze;
13. git diff --check;
14. Django check;
15. migrations check;
16. testes direcionados executados.

DEPOIS PARE.

NÃO INICIE IMPRESSÃO.

DEPOIS DESSA CORREÇÃO O PRÓXIMO PASSO SERÁ:

VALIDAÇÃO MANUAL DE:
- CAIXA
- VENDA RÁPIDA
- MESA
- PAGAMENTOS

SÓ DEPOIS PARTIREMOS PARA:

- NOTINHA / RESUMO / DOCUMENTO NÃO FISCAL;
- IMPRESSÃO DE PRODUÇÃO POR SETOR.