# MISSÃO — REMOVER DEFINITIVAMENTE MESAS LEGADO E LIMPAR LEGADO DO CORE POS

Continue no HEAD atual.

Na última revisão, o HEAD era:

`fc24b415d160e8f7c1f5e1e6749e97fd25f6b929`

Antes de alterar, confira o HEAD atual.

Esta é uma missão de LIMPEZA ARQUITETURAL.

Objetivo:

1. remover definitivamente o fluxo antigo de Mesa;
2. deixar somente a Mesa nova baseada em `TableAttendance`;
3. remover código morto/legado do POS que já foi substituído;
4. retirar `TABLE_BILL` do runtime moderno;
5. remover o antigo fluxo direto da Venda Rápida;
6. corrigir o Backoffice `/mesas`, que ainda usa o modelo antigo;
7. NÃO implementar, redesenhar ou refatorar COMANDAS nesta missão.

---

# REGRA ABSOLUTA — NÃO MEXER EM COMANDAS

COMANDAS ainda serão planejadas e implementadas em uma próxima etapa.

NÃO modificar comportamento de:

```text
CommandsPage
CommandDetailPage

/api/v1/pos/commands/
/api/v1/pos/commands/*
/api/v1/pos/command-items/*
/api/v1/pos/command-payments/*

AttendanceCommand
AttendanceOrder
AttendanceOrderItem
AttendancePayment

Command
Order
OrderItem
CommandPayment

Não redesenhar:

abertura de Comanda;
fechamento de Comanda;
pagamentos de Comanda;
itens de Comanda;
transferência de Comanda;
transferência entre Comandas;
produção de Comanda;
tickets de Comanda;
relatórios de Comanda.

Não mexer em:

/comandas
/relatorios/mesas-comandas

salvo referências estritamente necessárias para remover o antigo comportamento operacional da página /mesas, conforme descrito abaixo.

Não tomar decisões novas sobre como Mesa e Comanda irão se relacionar.

Isso será outra missão.

1. DEFINIÇÃO OFICIAL DE MESA

A partir desta missão, a arquitetura oficial é:

commands.Table
    ↓
attendance.TableAttendance
    ↓
attendance.TableOrder
    ↓
attendance.TableOrderItem
    ↓
attendance.TablePayment
    ↓
sales.Sale

commands.Table CONTINUA EXISTINDO.

Apesar de estar dentro do app Django commands, ela é atualmente a entidade física/cadastral da Mesa:

filial;
nome;
quantidade de lugares;
status;
soft delete.

NÃO remover:

apps.commands.models.Table

NÃO criar outra entidade Table.

NÃO migrar Table para outro app nesta missão.

2. TableAttendance É A ÚNICA FONTE OPERACIONAL DA MESA

Para o módulo Mesa:

Mesa livre
→ não existe TableAttendance OPEN

Mesa ocupada
→ existe TableAttendance OPEN

Mesa fechada
→ TableAttendance CLOSED

Não determinar mais estado operacional da Mesa a partir de:

Command
AttendanceCommand
legacy_occupied
is_primary
open_commands

Isso pertence aos fluxos antigos / futuros de Comanda, não ao motor atual de Mesa.

3. FLUTTER — REMOVER legacyOccupied

Hoje existe em:

pos/lib/attendance/attendance_models.dart

campo:

legacyOccupied

e parsing:

json['legacy_occupied']

REMOVER.

Também remover todas as regras no Flutter do tipo:

if (table.legacyOccupied) ...

ou:

disabled = table.legacyOccupied

Revisar principalmente:

pos/lib/attendance/attendance_pages.dart
pos/lib/attendance/shared_tables_grid.dart
pos/lib/attendance/attendance_models.dart

O grid deve usar somente:

table.status
table.attendance

do motor novo.

4. REMOVER COMPONENTES MORTOS DA MESA ANTIGA NO FLUTTER

Em:

pos/lib/attendance/attendance_pages.dart

existem atualmente classes antigas sem uso:

_OpenTableDetails
_OpenTableDialog
_OpenTableDialogState

A Mesa nova abre pelo fluxo atual de:

openAttendanceTable(...)

Remover os componentes mortos e imports relacionados, desde que a busca estática confirme que não possuem caller.

Não alterar a UI atual da Mesa nova.

5. BACKEND POS — POSTablesView

Hoje POSTablesView ainda cria:

legacy_ids

consultando:

Command
AttendanceCommand

e responde:

{
  "legacy_occupied": true
}

REMOVER essa compatibilidade.

O payload de Mesa deve ser baseado somente em:

TableAttendance status=OPEN

Conceitualmente:

attendance existe
→ occupied

attendance não existe
→ free

Não consultar Command ou AttendanceCommand para determinar o estado operacional da Mesa.

Remover imports mortos resultantes dessa mudança.

6. REMOVER SERVIÇO ANTIGO open_table()

Em:

backend/apps/attendance/services.py

existe:

def open_table(...)

com docstring semelhante a:

Open exactly one primary POS-5 command for a physical table.

Esse serviço:

exige tables;
exige commands;
cria AttendanceCommand;
usa is_primary;
representa o motor antigo onde Mesa era uma Comanda principal.

O endpoint atual de Mesa usa:

open_table_attendance(...)

Portanto:

FAZER BUSCA ESTÁTICA NO REPOSITÓRIO.

Se open_table() não possui nenhum caller moderno fora do fluxo antigo, REMOVER:

open_table(...)

e limpar imports relacionados.

NÃO substituir por Comanda.

NÃO alterar open_command().

7. REMOVER AttendanceOpenTableSerializer

Em:

backend/apps/attendance/serializers.py

existe:

AttendanceOpenTableSerializer

A Mesa nova usa:

TableAttendanceOpenSerializer

Confirmar por busca estática e remover o serializer antigo se não possuir caller.

Limpar imports no:

backend/apps/pos/views.py
8. AttendanceOperationType.OPEN_TABLE

Existe histórico antigo:

OPEN_TABLE = 'open_table'

enquanto a Mesa nova usa:

TABLE_OPEN = 'table_open'

NÃO apagar registros históricos do banco.

NÃO criar migration destrutiva só para remover o valor antigo.

Se a choice antiga precisar permanecer para leitura histórica, manter com comentário explícito de HISTÓRICO.

Mas nenhum fluxo runtime novo pode criar:

OPEN_TABLE

A Mesa nova deve continuar criando:

TABLE_OPEN
9. open_table_attendance() — RETIRAR DEPENDÊNCIA DO MOTOR ANTIGO

Hoje o serviço novo ainda verifica algo semelhante a:

Command.objects...
AttendanceCommand.objects...

e gera:

table_in_legacy_use

Essa regra veio da convivência temporária entre motores.

A fonte operacional da Mesa agora é:

TableAttendance

Portanto remover do motor novo a dependência de:

Command
AttendanceCommand
table_in_legacy_use

A abertura deve verificar:

Table válida/ativa
TableAttendance OPEN existente

e nada além disso para determinar se a Mesa está operacionalmente ocupada.

IMPORTANTE:

isso NÃO significa implementar integração entre Mesa e Comanda.

Não mexer em Comanda.

O relacionamento futuro Mesa ↔ Comanda será definido depois.

10. BACKOFFICE /mesas ESTÁ NO MODELO ANTIGO

Hoje:

frontend/src/app/(private)/mesas/page.tsx

usa:

tables/operational/

e trabalha com:

open_commands
operational_status por Command
pagamento parcial de Command
link /comandas/{id}
POST commands/open/
modal Nova comanda

Isso precisa sair.

A página /mesas nesta etapa será exclusivamente:

CADASTRO E CONFIGURAÇÃO FÍSICA DE MESAS

Deve permitir:

listar mesas;
criar mesa;
editar nome;
editar lugares;
excluir/arquivar;
configurar intervalo/lote;
pesquisar por nome.

Não deve abrir atendimento.

Não deve abrir Comanda.

Não deve mostrar:

LIVRE
OCUPADA
PAGAMENTO PARCIAL
open_commands
open_commands_total
open_commands_count

Não deve possuir:

Abrir mesa
Adicionar comanda
Nova comanda
links /comandas/*

A operação da Mesa acontece no CORE POS.

11. BACKOFFICE NÃO DEVE IMPLEMENTAR A NOVA OPERAÇÃO DE MESA AGORA

Não transformar /mesas em outro POS web.

Não implementar:

adicionar produtos
pagamentos
Solicitar Conta
fechamento

no Backoffice nesta missão.

/mesas é cadastro físico.

CORE POS é a operação.

12. REMOVER tables/operational/ SE NÃO HOUVER MAIS CALLER

Existe atualmente no backend:

TableViewSet.operational

que monta:

open_commands
open_commands_count
open_commands_total
operational_status

FAZER BUSCA ESTÁTICA em frontend, POS e backend.

Se depois da mudança de /mesas não existir nenhum caller:

REMOVER:

TableViewSet.operational

e os serializers exclusivos dele:

OperationalCommandSerializer
OperationalTableSerializer

Essa é a ÚNICA limpeza permitida dentro de apps.commands relacionada a Comandas nesta missão.

NÃO alterar nenhum comportamento de Command.

13. LIMPAR O TYPE Table DO FRONTEND

Hoje o type possui campos antigos:

operational_status
open_commands_count
open_commands_total
open_commands

Depois de remover o endpoint antigo, verificar callers.

Se forem usados somente pelo /mesas antigo, remover.

Preservar:

id
branch
name
seats
status
created_at
updated_at

Não alterar os types de Command.

14. PROTEÇÃO DE EDIÇÃO/EXCLUSÃO DA MESA FÍSICA

Hoje as proteções do Backoffice ainda estão centradas nos motores antigos.

Precisamos proteger a Mesa física quando existir atendimento NOVO aberto:

TableAttendance.objects.filter(
    table=table,
    status=TableAttendanceStatus.OPEN,
).exists()

Ao editar estrutura de Mesa com atendimento novo aberto:

BLOQUEAR.

Ao excluir/arquivar Mesa com atendimento novo aberto:

BLOQUEAR.

Mensagem conceitual:

Não é possível alterar/excluir esta mesa enquanto houver um atendimento aberto.
Feche o atendimento antes de continuar.

Preservar as proteções existentes relacionadas a Comandas.

Não redesenhar Comanda.

Apenas ADICIONAR TableAttendance como fonte oficial do atendimento de Mesa novo.

15. CORRIGIR HELPER ENGANOSO DE ATENDIMENTO ABERTO

Em:

backend/apps/commands/services.py

há helper semelhante a:

_open_table_attendance_exists()

mas atualmente ele consulta:

AttendanceCommand

e não TableAttendance.

Isso está semanticamente errado.

Refatorar nomes/helpers para que:

atendimento de Mesa
→ TableAttendance

e:

Comanda
→ estruturas de Comanda

continuem separados.

Não alterar regras de negócio de Comandas.

16. TABLE_BILL É LEGADO DO MOTOR DE IMPRESSÃO DA MESA

A arquitetura oficial agora é:

SOLICITAR CONTA
→ TABLE_CONFERENCE

e:

FECHAR MESA
→ TABLE_FINAL_RECEIPT

Logo:

TABLE_BILL

não deve mais fazer parte do runtime moderno.

17. BUG ATUAL DO POSTableAttendanceBillView

Hoje set_table_bill_requested() emite:

PrintDocumentType.TABLE_CONFERENCE

mas POSTableAttendanceBillView procura:

PrintDocumentType.TABLE_BILL

para montar o effects.

CORRIGIR IMEDIATAMENTE.

Após Solicitar Conta, o documento retornado em effects deve ser:

TABLE_CONFERENCE
18. POSTableAttendanceView NÃO DEVE MAIS EXPOR TABLE_BILL

Hoje consulta:

TABLE_BILL
TABLE_CONFERENCE
TABLE_FINAL_RECEIPT

Mudar para:

TABLE_CONFERENCE
TABLE_FINAL_RECEIPT

Comprovantes de pagamentos continuam no ledger próprio.

19. REMOVER TABLE_BILL DAS ROTAS ATIVAS

Remover TABLE_BILL de:

INITIAL_DOCUMENT_TYPES

Não criar rota default nova para esse documento.

Remover da configuração atual de rotas no Backoffice:

Conta da mesa

Devem permanecer:

Conferência
Recibo final da mesa
Recibo venda rápida
Comprovante de pagamento
Ticket
20. NÃO DESTRUIR HISTÓRICO TABLE_BILL

Podem existir:

PrintDocument
PrintJob
PrintRoute

históricos com:

table_bill

NÃO apagar esses registros.

NÃO fazer migration para deletá-los.

Se o enum/model precisar reconhecer:

table_bill

para leitura de histórico ou jobs antigos, manter compatibilidade mínima.

Mas:

novo documento
nova rota
nova emissão
nova UI

NÃO deve criar ou oferecer TABLE_BILL.

O renderer antigo pode permanecer somente se necessário para imprimir/reconciliar job histórico já persistido.

Marcar claramente como compatibilidade histórica, não runtime atual.

21. FLUTTER — NÃO USAR PrintDocumentType.tableBill NO FLUXO NOVO

Fazer busca estática.

Nenhuma tela moderna de Mesa deve solicitar:

PrintDocumentType.tableBill

Conferência:

PrintDocumentType.tableConference

Recibo final:

PrintDocumentType.tableFinalReceipt
22. REMOVER VENDA RÁPIDA DIRETA ANTIGA

A Venda Rápida atual oficial é:

QuickSaleCheckout
→ QuickSaleCheckoutPayment
→ finalizeQuickSaleCheckout()

Existe ainda um fluxo antigo paralelo:

finalizeQuickSale(...)

que envia diretamente:

POST /api/v1/pos/sales/

Esse caminho não deve coexistir com o checkout persistente atual.

23. FLUTTER — REMOVER finalizeQuickSale() LEGADO

Em:

pos/lib/core/app_controller.dart

remover, se busca estática confirmar ausência de caller moderno:

finalizeQuickSale(...)

e todo estado exclusivo desse fluxo:

_uncertainSaleKeys
finalizingSale
saleFinalizationError

_restoreUncertainSaleIntents()
_persistUncertainSaleIntents()

Remover também a chamada:

_restoreUncertainSaleIntents()

de initialize().

NÃO remover recovery/idempotência do QuickSaleCheckout.

24. PosApi — REMOVER FINALIZAÇÃO DIRETA ANTIGA

Remover do contrato e implementação:

finalizeQuickSale(...)

que chama:

POST sales/

Preservar:

createQuickSaleCheckout
recoverQuickSaleCheckout
getQuickSaleCheckout
updateQuickSaleCheckout
recordQuickSalePayment
reverseQuickSalePayment
previewQuickSalePayment
finalizeQuickSaleCheckout
cancelQuickSaleCheckout
25. BACKEND — REMOVER ENDPOINT DIRETO ANTIGO DA VENDA RÁPIDA

Fazer busca estática primeiro.

Se não existir caller moderno:

remover:

POSFinalizeSaleView
POSFinalizeSaleSerializer

e:

path('sales/', POSFinalizeSaleView.as_view(), ...)

NÃO alterar:

sales/preview/
sales/availability/
sales/checkout-options/
sales/checkouts/*
26. SECURE STORAGE — REMOVER ESTADO DA VENDA DIRETA ANTIGA

O fluxo antigo ainda possui:

core_pos.pending_sale_intents

e:

readPendingSaleIntents()
writePendingSaleIntents()

Se após remover finalizeQuickSale() não houver caller:

REMOVER.

Preservar:

core_pos.quick_sale_checkout
core_pos.table_payment_state
core_pos.print_ledger
device credential
operator session
27. NÃO REMOVER RECOVERY ATUAL DO QUICK SALE

IMPORTANTE.

Não remover:

recoverQuickSaleCheckout()

Nem a máquina atual de:

creation_idempotency_key
creation_request
payment_attempts
pending finalize
checkout_id
recovered result por checkoutId

Esse é o motor atual e já foi corrigido.

28. MANTER FALLBACK DE STORAGE ANTIGO DO QUICK CHECKOUT

Em _quickCheckoutState() existe compatibilidade com registro antigo:

operator_id

Esse fallback pode conter operação financeira de dispositivo atualizado.

NÃO remover nesta missão sem uma migração explícita e segura.

É compatibilidade de dados, não motor antigo de Venda Rápida.

29. MANTER MIGRAÇÃO DE CREDENCIAL DE DISPOSITIVO

Em authenticate_device() existe fallback para dispositivos antigos com:

credential_hash
credential_fingerprint vazio

e depois ele atualiza o fingerprint.

NÃO remover.

Isso protege dispositivos já pareados.

Não confundir compatibilidade de autenticação com código legado de negócio.

30. NÃO APAGAR MIGRATIONS HISTÓRICAS

NÃO deletar migrations antigas.

NÃO reescrever migrations aplicadas.

NÃO apagar modelos/colunas históricos de Comanda nesta missão.

Limpeza de runtime != reescrever histórico do banco.

31. NÃO MEXER NA IMPRESSÃO QUE JÁ ESTÁ CORRETA

Preservar integralmente:

PrintManager
claim
lease
dispatch
physical_dispatch_started_at
FAILED BEFORE SEND
UNCERTAIN
retry != reprint
local ledger
polling
tarja preta de REIMPRESSÃO
PrintRoute
PrintRouteOverride
NETWORK local

Só limpar o documento legado:

TABLE_BILL

conforme regras acima.

32. NÃO MEXER EM PAGAMENTOS DA MESA

Preservar:

pagamento parcial;
pagamento por valor;
pagar restante;
divisão por pessoas;
pagamento por itens;
allocations;
estorno;
descontos;
taxa de serviço;
autorizações;
cash session;
idempotência.
33. NÃO MEXER NO FECHAMENTO DA MESA

Preservar:

pagar
→ fechar Mesa
→ backend CLOSED
→ Sale
→ TABLE_FINAL_RECEIPT
→ voltar para grid
→ recarregar grid
→ Mesa livre
→ "Mesa fechada com sucesso."
34. NÃO MEXER EM PRODUÇÃO/TICKETS

Preservar:

Salvar e enviar pedido
→ TableOrderItem CONFIRMED
→ baixa estoque
→ ProductionJob
→ Ticket se emits_ticket=true

Preservar cancelamento:

cancelar item
→ devolução estoque
→ ProductionJob CANCEL
→ cancelamento Ticket
35. NÃO MEXER EM CAIXA

Preservar:

FIXED;
FLEXIBLE;
seleção;
abertura;
entrada;
sangria;
resumo;
fechamento.
36. NÃO MEXER EM PAREAMENTO/AUTH

Preservar:

identificação da filial;
OTP;
credential;
device auth;
operador;
PIN;
bootstrap;
version gate;
device status;
permissões.
37. SINCRONIZAÇÃO NÃO É ALVO DESTA MISSÃO

A Central de Sincronização atualmente faz principalmente:

heartbeat
bootstrap
status

Não implementar o motor offline/sync completo agora.

Não expandir escopo.

38. INVENTÁRIO/RELATÓRIOS DO POS NÃO SÃO ALVO

Hoje estão:

not_implemented

Não implementar nesta missão.

39. BUSCA ESTÁTICA OBRIGATÓRIA ANTES DE REMOVER CÓDIGO

Antes de excluir qualquer:

class
function
serializer
endpoint
type
field

fazer busca estática no repositório por referências.

Se ainda houver caller legítimo fora do legado descrito:

NÃO apagar cegamente.

Entender o uso e preservar o necessário.

40. RESULTADO ESPERADO — MESA

Depois da limpeza:

commands.Table
→ configuração física

TableAttendance
→ operação da Mesa

Não existe mais no POS:

legacyOccupied
legacy_occupied
Mesa = AttendanceCommand principal
Mesa = Command
41. RESULTADO ESPERADO — BACKOFFICE MESAS
/mesas

deve ser:

CADASTRO DE MESAS

Mesa 1    4 lugares
Mesa 2    6 lugares
Mesa 3    2 lugares

Criar
Editar
Excluir/arquivar
Gerar intervalo
Pesquisar

Não:

Abrir Mesa
Nova Comanda
Adicionar Comanda
Pagamento parcial
Abrir atendimento
open_commands
42. RESULTADO ESPERADO — DOCUMENTOS DA MESA

Runtime atual:

SOLICITAR CONTA
→ TABLE_CONFERENCE

FECHAR MESA
→ TABLE_FINAL_RECEIPT

PAGAMENTO
→ PAYMENT_RECEIPT

Nenhum fluxo novo usa:

TABLE_BILL
43. RESULTADO ESPERADO — VENDA RÁPIDA

Somente:

QuickSaleCheckout
→ pagamentos persistentes
→ finalizeQuickSaleCheckout

Não existe mais o caminho operacional paralelo:

finalizeQuickSale
→ POST /pos/sales/
44. ARQUIVOS A REVISAR

No mínimo:

pos/lib/attendance/attendance_models.dart
pos/lib/attendance/attendance_pages.dart
pos/lib/attendance/shared_tables_grid.dart

pos/lib/core/app_controller.dart
pos/lib/network/pos_api.dart
pos/lib/storage/secret_store.dart

pos/lib/printing/models.dart
pos/lib/printing/production_ticket_renderer.dart

backend/apps/attendance/models.py
backend/apps/attendance/serializers.py
backend/apps/attendance/services.py

backend/apps/pos/urls.py
backend/apps/pos/views.py
backend/apps/pos/serializers.py

backend/apps/production/models.py
backend/apps/production/services.py

backend/apps/commands/views.py
backend/apps/commands/serializers.py
backend/apps/commands/services.py

frontend/src/app/(private)/mesas/page.tsx
frontend/src/components/document-print-routes.tsx
frontend/src/types/index.ts

Lembrando:

alterações em apps.commands nesta missão são SOMENTE as necessárias para:

cadastro físico de Table
proteção por TableAttendance
remoção do antigo endpoint operacional de Mesas

NÃO mexer em negócio de Comandas.

45. MIGRATIONS

A princípio NÃO deveria ser necessária migration.

Não estamos apagando dados históricos nem schema principal.

Se encontrar necessidade real de migration:

PARE e informe no checkpoint antes de tentar fazer limpeza destrutiva.

REGRA CRÍTICA — NÃO EXECUTAR TESTES

NÃO execute:

flutter analyze
flutter test
flutter build
flutter run
pytest
npm test
npm build
npm lint
suites
makemigrations --check

Não executar testes automáticos.

Não executar build.

Não executar analyze.

Eu farei os testes manualmente.

CHECKPOINT

Ao terminar informe:

qual era exatamente o fluxo antigo de Mesa encontrado;
se removeu legacyOccupied do Flutter;
se removeu legacy_occupied do backend;
se POSTablesView passou a usar somente TableAttendance;
se removeu o open_table() antigo;
se removeu AttendanceOpenTableSerializer;
o que fez com AttendanceOperationType.OPEN_TABLE histórico;
como ficou open_table_attendance();
como ficou o Backoffice /mesas;
se removeu tables/operational/;
quais serializers operacionais antigos de Mesa foram removidos;
como ficou o type Table do frontend;
como edição de Mesa é bloqueada com TableAttendance OPEN;
como exclusão de Mesa é bloqueada com TableAttendance OPEN;
como corrigiu POSTableAttendanceBillView para TABLE_CONFERENCE;
onde TABLE_BILL deixou de ser oferecido no runtime;
o que foi mantido somente para compatibilidade histórica de TABLE_BILL;
se removeu o antigo finalizeQuickSale();
se removeu POST /api/v1/pos/sales/;
se removeu POSFinalizeSaleView/serializer antigos;
se removeu _uncertainSaleKeys e pending sale intents antigos;
se preservou integralmente o recovery atual do QuickSaleCheckout;
se preservou o fallback antigo por operator_id;
se preservou upgrade credential_hash → fingerprint;
confirme explicitamente que NÃO alterou lógica de Comandas;
confirme que NÃO alterou /comandas;
confirme que NÃO alterou relatórios de Comandas;
arquivos Flutter alterados;
arquivos backend alterados;
arquivos frontend alterados;
migrations criadas — esperado: nenhuma;
qualquer código legado encontrado que decidiu NÃO remover, e por quê;
pontos restantes para teste manual.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.
NÃO EXECUTE FLUTTER RUN.

Depois pare.