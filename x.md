TRABALHE SOMENTE NESTES DOIS PONTOS NO HEAD ATUAL DO CORE PDV E DEPOIS PARE.

NÃO INICIE:

* impressão;
* fiscal;
* Stone/Cielo/PagBank;
* nova fase;
* alterações no módulo legado de Comandas.

==================================================

1. MESAS — AGRUPAR ITENS IGUAIS NO RESUMO
   ==================================================

No CORE POS, em:

pos/lib/attendance/table_attendance_page.dart

o RESUMO DA MESA atualmente renderiza cada TableOrderItem individualmente:

attendance.orders
→ order.items
→ _ConfirmedOrderItemRow

Alterar SOMENTE A APRESENTAÇÃO do resumo para agrupar itens equivalentes.

IMPORTANTE:

NÃO consolidar registros no backend.
NÃO alterar TableOrderItem.
NÃO perder IDs individuais.
NÃO alterar pagamento por itens.
NÃO alterar estoque, produção, tickets, cancelamento ou transferência.

O agrupamento é SOMENTE VISUAL.

Exemplo:

Hoje:

1x HEINEKEN
1x HEINEKEN
1x HEINEKEN
2x COCA

Quero:

3x HEINEKEN
2x COCA

Um grupo só pode juntar itens que sejam realmente equivalentes.

Considerar pelo menos:

* mesmo produto;
* mesmo preço efetivo;
* mesmos modificadores;
* mesma observação;
* mesmo estado relevante.

NÃO agrupar, por exemplo:

HAMBÚRGUER
HAMBÚRGUER + BACON
HAMBÚRGUER sem cebola

como se fossem o mesmo item.

Somar corretamente:

* quantity;
* line total.

Preservar os TableOrderItem originais dentro do grupo para qualquer ação posterior.

==================================================
2. DETALHES DO ITEM AGRUPADO
============================

Hoje "Ver detalhes" recebe um TableOrderItem + TableOrder individual.

Adaptar a experiência para o grupo.

Exemplo:

3x HEINEKEN

Ao abrir detalhes:

HEINEKEN

Quantidade total: 3

ENTRADAS

1x • 13:02 • Pedido #18 • Felipe
1x • 13:17 • Pedido #21 • João
1x • 13:41 • Pedido #27 • Felipe

Os dados JÁ EXISTEM no payload:

* order.createdAt;
* order.id;
* order.createdByName;
* item.confirmedAt;
* item.quantity.

Usar preferencialmente confirmedAt como horário operacional do item.
Se não existir, usar createdAt como fallback.

Se todas as entradas tiverem exatamente o mesmo horário/contexto, não precisa gerar informação repetitiva desnecessária.

Continuar mostrando quando aplicável:

* modificadores;
* observação;
* status;
* impressão;
* cancelamento.

IMPORTANTE:

Cancelar e Transferir continuam sendo ações sobre TableOrderItem individual.

Se um grupo possuir vários itens de origem, NÃO cancelar nem transferir todos automaticamente.

Ao escolher uma ação que exige item individual, permitir selecionar a entrada correspondente ou manter a granularidade individual de forma clara.

Pagamento por itens também continua usando os IDs individuais reais.

==================================================
3. CONFERÊNCIA
==============

A conferência da Mesa atualmente também percorre:

order
→ item

Avaliar e deixar coerente com o Resumo da Mesa:

itens idênticos devem aparecer agrupados visualmente também na conferência, desde que isso não remova nenhuma informação financeira necessária.

Isso continua sendo apenas apresentação.

==================================================
4. ERRO REAL AO REGISTRAR/FECHAR MESA
=====================================

Existe erro confirmado em PostgreSQL:

FOR UPDATE cannot be applied to the nullable side of an outer join

O CI do HEAD atual reproduz o problema.

A causa NÃO é Flutter.

A causa está nas consultas de TablePayment/TablePaymentAllocation que combinam:

select_for_update(...)

com filtros do tipo:

reversal__isnull=True

`reversal` é uma relação reversa OneToOne opcional.

Esse filtro gera LEFT OUTER JOIN.

Mesmo:

select_for_update(of=('self',))

NÃO resolve se o SQL ainda possuir o OUTER JOIN.

O CI atual confirma falha em:

backend/apps/attendance/services.py

record_table_payment()

na consulta equivalente a:

TablePayment.objects
.select_for_update(of=('self',))
.filter(
attendance=attendance,
status=AttendancePaymentStatus.APPLIED,
reversal__isnull=True,
)
.exists()

O fechamento também passa por:

close_table_attendance()
→ table_financial_state(attendance, lock=True)

e `table_financial_state` contém a mesma combinação:

TablePayment

* reversal__isnull=True
* select_for_update

Esse é o motivo do 500 em:

POSTableAttendanceCloseView

==================================================
5. CORREÇÃO CORRETA DO LEDGER
=============================

NÃO remover os locks.

NÃO trocar simplesmente select_for_update por consulta sem lock.

NÃO mascarar NotSupportedError.

NÃO capturar a exceção para retornar 200.

Corrigir a estratégia de consulta.

O lock deve acontecer em TablePayment SEM atravessar a relação reversa nullable.

Estratégia desejada:

1. lockar os TablePayment pertencentes à Mesa diretamente, sem `reversal__isnull=True`;
2. dentro do conjunto já travado, identificar quais IDs possuem reversão;
3. determinar os pagamentos ativos:

   * status APPLIED;
   * que não tenham um TablePayment de reversão apontando para eles;
4. trabalhar com esses registros já seguros.

Pode ser criada uma função interna compartilhada para obter o ledger ativo lockado, evitando repetir a lógica.

Exemplo conceitual:

locked_payments =
TablePayment.objects
.select_for_update(of=('self',))
.filter(attendance=attendance)

Depois identificar:

reversed_payment_ids = {
payment.reversal_of_id
for payment in locked_payments
if payment.reversal_of_id is not None
}

active_payments = [
payment
for payment in locked_payments
if payment.status == APPLIED
and payment.id not in reversed_payment_ids
]

Não precisa obrigatoriamente usar exatamente esse código, mas preserve essa arquitetura:

LOCK NA TABELA PRINCIPAL
→ SEM OUTER JOIN
→ determinar ledger ativo depois.

==================================================
6. APLICAR EM TODOS OS PONTOS AFETADOS
======================================

Revisar em backend/apps/attendance/services.py todos os usos onde:

select_for_update

é combinado direta ou indiretamente com:

reversal__isnull=True
payment__reversal__isnull=True

Especial atenção a:

* table_financial_state();
* record_table_payment();
* _table_allocation_amount();
* close_table_attendance();
* qualquer fluxo de pagamento por itens que trave TablePaymentAllocation e atravesse payment__reversal.

Não corrigir apenas a linha que apareceu no traceback.

A mesma classe de erro não pode permanecer em outro caminho da Mesa.

Consultas somente leitura que não usam FOR UPDATE podem continuar usando reversal__isnull=True se forem seguras e fizer sentido.

==================================================
7. CONCORRÊNCIA / INTEGRIDADE
=============================

Preservar:

* transaction.atomic;
* lock da TableAttendance;
* lock do ledger;
* idempotência;
* proteção contra pagamentos concorrentes;
* proteção contra mistura de CashSession;
* `table_cash_session_mismatch`;
* saldo oficial;
* estorno;
* pagamento por valor;
* pagar saldo;
* dividir igual;
* pagar por itens;
* fechamento da Mesa.

Não reduzir segurança transacional para eliminar o erro.

Se necessário, faça `reverse_table_payment()` participar da mesma estratégia de serialização da Mesa para impedir corrida entre:

pagamento
vs
estorno
vs
fechamento.

==================================================
8. NÃO REGREDIR CASHSESSION
===========================

Preservar arquitetura atual:

CAIXA
→ POSDevice.active_cash_session
→ Venda Rápida / Mesa / Pagamentos usam automaticamente.

Não recolocar seletor de caixa dentro:

* Venda Rápida;
* Mesa;
* Pagamento;
* Dinheiro;
* fechamento.

==================================================
9. TESTE FUNCIONAL NÃO É PARA SER INVENTADO
===========================================

NÃO criar bateria nova de testes Flutter/E2E.

Corrija o código.

Preserve os testes backend existentes.

O CI atual já demonstra o problema real de PostgreSQL e deve deixar de apresentar:

FOR UPDATE cannot be applied to the nullable side of an outer join

nos testes de Mesa.

==================================================
10. AO TERMINAR
===============

Informe objetivamente:

1. como agrupou itens no resumo;
2. qual chave define itens equivalentes;
3. como preservou os TableOrderItem individuais;
4. como os horários aparecem nos detalhes;
5. como cancelamento/transferência continuam individuais;
6. se a conferência também foi agrupada;
7. qual query causava o erro PostgreSQL;
8. como removeu o OUTER JOIN do caminho lockado;
9. quais pontos de `reversal__isnull=True` + lock foram corrigidos;
10. como `table_financial_state()` funciona agora;
11. como `record_table_payment()` funciona agora;
12. como `close_table_attendance()` funciona agora;
13. confirmação de preservação da CashSession global;
14. arquivos alterados;
15. flutter analyze;
16. Django check;
17. migrations check;
18. git diff --check.

DEPOIS PARE.
