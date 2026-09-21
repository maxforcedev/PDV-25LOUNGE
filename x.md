TRABALHE SOMENTE NESTAS CORREÇÕES NO HEAD ATUAL DA MAIN E DEPOIS PARE.

NÃO INICIE NOVA FASE.

NÃO MEXER EM:

* impressão;
* Stone;
* Cielo;
* PagBank;
* fiscal;
* Comanda legado;
* nova arquitetura;
* novas funcionalidades fora do escopo abaixo.

==================================================

1. CORRIGIR A CHAVE DE AGRUPAMENTO DOS ITENS DA MESA
   ==================================================

Arquivo principal:

pos/lib/attendance/table_attendance_page.dart

O agrupamento visual implementado ficou correto estruturalmente:

* não consolida TableOrderItem no backend;
* preserva os IDs individuais;
* preserva cancelamento individual;
* preserva transferência individual;
* preserva pagamento por item;
* detalhes mostram as entradas individuais.

PORÉM, a chave atual ainda pode agrupar itens que possuem condições financeiras diferentes.

Hoje ela considera aproximadamente:

* productId;
* unitPrice;
* modifierSnapshot;
* notes;
* status;
* printStatus;
* cancellationReason.

Isso NÃO é suficiente.

Dois itens do mesmo produto podem possuir:

* mesma quantidade;
* mesmo preço base;
* mesmos modificadores;

mas terem:

* promoção diferente;
* desconto manual diferente;
* benefício promocional diferente;
* regra financeira congelada diferente.

Esses itens NÃO devem ser agrupados visualmente como se fossem exatamente iguais.

A chave de equivalência também deve considerar o estado financeiro efetivo congelado do item.

Verifique o modelo/payload real de TableOrderItem e use o financial snapshot existente.

Considere na equivalência os campos financeiros relevantes disponíveis, incluindo quando existirem:

* financialSnapshot / financial_snapshot;
* promotion;
* promotionBenefit;
* manualDiscount;
* manualDiscountIntent;
* valor líquido efetivo;
* descontos;
* qualquer outro snapshot financeiro que diferencie o preço/regra aplicada naquele item.

NÃO inventar campos.

Use o que realmente existe no modelo/API atual.

Regra:

SÓ AGRUPAR se os itens forem equivalentes também financeiramente.

Exemplo:

HEINEKEN R$ 15 sem desconto
HEINEKEN R$ 15 com promoção

NÃO devem necessariamente virar uma única linha só porque productId e unitPrice aparentam ser iguais.

Preservar completamente:

* IDs individuais;
* TableOrderItem originais;
* ações individuais;
* horários individuais;
* pagamento por itens;
* valores oficiais do backend.

O agrupamento continua APENAS VISUAL.

==================================================
2. CORRIGIR O ERRO REAL EM POSCashSessionSelectView
===================================================

Arquivo:

backend/apps/pos/views.py

Existe atualmente:

raise DomainValidationError(
code='cash_session_unavailable',
message='Este caixa não possui uma sessão aberta disponível.',
status_code=status.HTTP_409_CONFLICT,
)

PROBLEMA:

DomainValidationError.**init**() atualmente não aceita o argumento:

status_code

A assinatura atual é aproximadamente:

def **init**(self, *, code, message, details=None):

O CI já reproduziu:

TypeError:
DomainValidationError.**init**() got an unexpected keyword argument 'status_code'

Isso pode gerar 500 no POS ao tentar selecionar um caixa indisponível.

Corrija sem mascarar a exceção.

Primeiro verifique como o projeto padroniza erros de domínio com HTTP 409.

Escolha a solução mais coerente com a arquitetura existente.

Pode ser:

* usar uma exceção específica já existente para conflict;
* ou ajustar DomainValidationError de maneira arquiteturalmente correta caso o projeto já espere status customizável.

NÃO faça uma alteração global arriscada somente para resolver uma chamada isolada.

Preferência:
se já existir uma exceção de conflito no projeto, reutilize-a.

Resultado esperado para caixa indisponível:

* resposta de domínio controlada;
* status HTTP adequado;
* sem TypeError;
* sem 500;
* mantendo code = cash_session_unavailable;
* mantendo a mensagem atual ou equivalente.

Também procure rapidamente outros usos de:

DomainValidationError(... status_code=...)

para não deixar a mesma falha em outro endpoint.

NÃO faça refatoração ampla.

==================================================
3. NÃO MEXER NO NOVO LEDGER DE TABLEPAYMENT
===========================================

A correção recente do PostgreSQL em Mesas está correta conceitualmente.

Preservar:

_locked_table_payments()
_active_locked_table_payments()
_locked_active_table_payments()

A estratégia deve continuar sendo:

TableAttendance lock
→ TablePayment base rows lockados SEM outer join
→ identificar reversões dentro do ledger lockado
→ determinar pagamentos ativos
→ continuar operação.

NÃO reintroduzir:

reversal__isnull=True

em queryset com:

select_for_update()

no fluxo novo de Mesas.

Preservar o comportamento já corrigido em:

* table_financial_state();
* record_table_payment();
* close_table_attendance();
* reverse_table_payment();
* equal split;
* pagamento por itens;
* transferência.

==================================================
4. NÃO MEXER EM COMANDA LEGADO NESTA MISSÃO
===========================================

Ainda existem queries do módulo legado de Comanda com:

AttendancePayment

* select_for_update()
* reversal__isnull=True

NÃO corrigir isso agora.

Registrar apenas no checkpoint que foi identificado e deixado intacto por estar fora do escopo.

Não misturar Mesa nova com Comanda legado.

==================================================
5. LIMPEZA PEQUENA EM transfer_table_items()
============================================

Revisar este ponto:

source_active_payment_ids = [...]
destination_active_payment_ids = [...]

logo depois existe bloqueio caso qualquer uma das listas tenha pagamentos ativos.

Mais abaixo existe uma consulta de TablePaymentAllocation filtrando novamente por:

payment_id__in=source_active_payment_ids

Se o fluxo já saiu anteriormente sempre que a lista não está vazia, essa consulta pode ter se tornado redundante/código morto.

CONFIRME primeiro.

Se realmente for inalcançável ou redundante:

remova somente essa redundância.

Se houver algum cenário válido em que ainda tenha função, preserve.

Não alterar regra de negócio de transferência.

==================================================
6. PRESERVAR CASHSESSION GLOBAL
===============================

Não alterar a arquitetura atual:

CAIXA
→ POSDevice.active_cash_session
→ Venda Rápida / Mesa / Pagamentos.

Não adicionar seletor de caixa dentro de:

* Venda Rápida;
* Mesa;
* tela de pagamento;
* Dinheiro;
* fechamento.

Preservar:

table_cash_session_mismatch.

==================================================
7. VALIDAÇÃO
============

NÃO criar bateria nova de testes Flutter/E2E.

OS TESTES FUNCIONAIS SERÃO FEITOS MANUALMENTE.

Rodar:

* flutter analyze;
* python manage.py check;
* python manage.py makemigrations --check --dry-run;
* git diff --check.

Se já existirem testes backend específicos para:

* POSCashSessionSelectView;
* cash_session_unavailable;
* Table Attendance grouping/backend;

pode rodar somente os testes direcionados necessários.

Não iniciar suíte nova inventada.

==================================================
8. CHECKPOINT FINAL
===================

Ao terminar informe objetivamente:

1. qual era o problema da chave de agrupamento;
2. quais dados financeiros passaram a participar da equivalência;
3. confirmação de que itens com condições financeiras diferentes não agrupam;
4. confirmação de que IDs individuais continuam preservados;
5. confirmação de que cancelamento e transferência continuam individuais;
6. causa do TypeError em POSCashSessionSelectView;
7. como corrigiu cash_session_unavailable;
8. qual status HTTP agora retorna nesse caso;
9. se encontrou outros DomainValidationError com status_code inválido;
10. confirmação de que o novo ledger de Mesa não foi alterado de forma regressiva;
11. confirmação de que não existe reversal__isnull=True + select_for_update no fluxo novo de Mesa;
12. se removeu ou preservou a checagem redundante de transfer_table_items e por quê;
13. confirmação de que Comanda legado não foi alterado;
14. arquivos alterados;
15. flutter analyze;
16. Django check;
17. migrations check;
18. git diff --check.

DEPOIS PARE.

NÃO INICIE OUTRA TAREFA.
