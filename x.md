FAÇA SOMENTE ESTA CORREÇÃO E DEPOIS PARE.

FONTE DE VERDADE:
HEAD ATUAL DA MAIN.

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
CORRIGIR reverse_table_payment()
==================================================

Ainda existe um risco de PostgreSQL no estorno da Mesa.

Hoje `reverse_table_payment()` possui algo equivalente a:

TablePayment.objects
    .select_for_update()
    .select_related(
        'attendance__branch__company',
        'cash_session',
    )
    .get(pk=payment.pk)

PROBLEMA:

`cash_session` é nullable.

Esse `select_related('cash_session')` pode gerar LEFT OUTER JOIN.

Com:

select_for_update()

sem limitar o lock à tabela principal,

PostgreSQL pode gerar:

FOR UPDATE cannot be applied to the nullable side of an outer join

É o mesmo tipo de problema que já foi corrigido em:

- record_table_payment();
- close_table_attendance().

==================================================
CORREÇÃO
==================================================

Preservar o lock.

NÃO remover `select_for_update()`.

Corrigir para travar apenas o TablePayment principal.

Preferência:

select_for_update(of=('self',))

e manter/carregar as relações necessárias de forma segura.

Exemplo conceitual:

TablePayment.objects
    .select_for_update(of=('self',))
    .select_related(
        'attendance__branch__company',
        'cash_session',
    )
    .get(pk=payment.pk)

Se ainda houver qualquer risco de outer join nessa consulta:

separar o lock da leitura de `cash_session`.

O importante é:

- TablePayment continua lockado;
- transaction.atomic continua preservada;
- cash_session continua disponível para validação;
- nenhum FOR UPDATE é aplicado ao lado nullable do join.

==================================================
PRESERVAR COMPORTAMENTO
==================================================

Não alterar a regra de negócio do estorno.

Deve continuar:

Mesa aberta
→ pagamento APPLIED
→ ESTORNAR
→ cria novo TablePayment REVERSED
→ mantém histórico imutável
→ preserva reversal_of
→ motivo opcional
→ valida CashSession OPEN quando aplicável
→ limpa equal split quando necessário
→ mantém auditoria.

Também preservar:

Pagamento Caixa A
→ estorno total
→ POS muda para Caixa B
→ novo pagamento no B
→ fechamento da Mesa permitido.

==================================================
NÃO REGREDIR
==================================================

Preservar tudo já corrigido nesta fase:

- CashSession global no POSDevice;
- ausência de seletor de caixa em Venda/Mesa/Pagamento;
- FLEXIBLE sem 500;
- Quick Sale sem TransactionManagementError;
- record_table_payment com lock seguro;
- close_table_attendance com lock seguro;
- PageHeader.description opcional;
- Kpi.note opcional;
- EmptyState.description opcional;
- pending da Mesa;
- pagar saldo;
- equal split;
- componentes compartilhados;
- PAGAMENTO no Resumo da Mesa.

==================================================
CHECKS
==================================================

NÃO iniciar nova bateria de testes funcionais.

OS TESTES FUNCIONAIS SERÃO EXECUTADOS MANUALMENTE POR MIM.

Apenas rode:

- flutter analyze
- git diff --check
- python manage.py check
- python manage.py makemigrations --check --dry-run

Se quiser rodar teste backend direcionado especificamente para
reverse_table_payment, tudo bem.

NÃO ampliar para nova suíte Widget/E2E.

==================================================
CHECKPOINT
==================================================

Ao terminar informe somente:

1. como corrigiu o lock em reverse_table_payment();
2. confirmação de que o TablePayment continua protegido por select_for_update;
3. confirmação de que cash_session nullable não entra mais em lock inválido;
4. arquivos alterados;
5. flutter analyze;
6. git diff --check;
7. Django check;
8. migrations check.

DEPOIS PARE.

A VALIDAÇÃO FUNCIONAL SERÁ FEITA MANUALMENTE POR MIM.