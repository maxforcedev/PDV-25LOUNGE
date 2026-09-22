TRABALHE NO HEAD ATUAL DA MAIN.

IMPLEMENTE SOMENTE O BLOCO 1 DA NOVA ARQUITETURA DE IMPRESSÃO DO CORE POS.

AO TERMINAR, PARE.

==================================================
OBJETIVO DO BLOCO 1
===================

Fazer o CORE POS imprimir fisicamente tickets de PRODUÇÃO em impressoras térmicas de REDE LOCAL, sem depender de PC, Print Agent ou comunicação direta da VPS com a impressora.

O fluxo final deve ser:

Mesa / Venda Rápida
↓
ProductionJob
↓
ProductionDestination
↓
PrintJob
↓
CORE POS local
↓
TCP/IP LAN
↓
Impressora térmica ESC/POS

Exemplo:

Mesa 10
2x X-Bacon
1x Coca-Cola

X-Bacon → COZINHA
Coca-Cola → BAR

Resultado:

ticket da cozinha sai na impressora vinculada ao setor COZINHA;

ticket do bar sai na impressora vinculada ao setor BAR.

==================================================

1. REGRAS DE ARQUITETURA
   ==================================================

NÃO criar um novo sistema paralelo de impressão.

Preservar e evoluir o que já existe:

ProductionDestination
ProductProductionDestination
PrinterDevice
ProductionJob
PrintJob
ProductionEvent.NEW
ProductionEvent.CANCEL

Preservar a separação:

ProductionJob
= evento operacional de produção

PrintJob
= execução física daquele evento em determinada impressora.

Produto NÃO deve apontar diretamente para IP/impressora.

Manter:

Produto
→ ProductionDestination
→ PrinterDevice

Exemplo:

HEINEKEN
→ BAR
→ Impressora Bar

X-BACON
→ COZINHA
→ Impressora Cozinha.

==================================================
2. NÃO IMPRIMIR PELA VPS
========================

Hoje existe NetworkPrinterAdapter no backend usando algo semelhante a:

socket.create_connection((host, port))

Isso NÃO será o fluxo operacional real.

A API Django está em uma VPS e normalmente não consegue acessar:

192.168.x.x

da rede interna da loja.

Portanto:

NÃO utilizar backend/VPS para realizar impressão física de produção.

Backend deve:

* criar ProductionJob;
* criar PrintJob;
* controlar estado;
* controlar claim;
* controlar retry;
* registrar auditoria.

CORE POS dentro da filial deve:

* receber/consultar PrintJobs;
* assumir o job;
* renderizar ESC/POS;
* abrir socket TCP local;
* enviar para a impressora;
* confirmar resultado para a API.

Não remover o adapter existente de maneira destrutiva se ele ainda servir a testes/legado.

Mas NÃO tratá-lo como executor de produção desta nova arquitetura.

==================================================
3. ESCOPO DO BLOCO 1
====================

Implementar:

A) Impressoras NETWORK.

B) TCP/IP local pelo Flutter.

C) ESC/POS básico para produção.

D) Fila segura de PrintJob.

E) Claim/lease de jobs.

F) Confirmação de PRINTED.

G) FAILED.

H) tratamento de resultado incerto.

I) retry seguro.

J) tickets NEW.

K) tickets CANCEL.

L) reimpressão.

M) Mesa.

N) Venda Rápida.

O) teste de impressão executado localmente pelo CORE POS.

P) status básico das impressoras.

NÃO implementar ainda:

* StoneLocalPrinterTransport;
* impressora interna Stone;
* Print Agent;
* USB;
* Bluetooth;
* spooler Windows;
* impressão fiscal;
* NFC-e;
* SAT;
* cupom fiscal;
* integração Cielo;
* integração Stone;
* integração PagBank;
* impressão de recibo do cliente;
* conta da Mesa;
* via loja;
* via cliente;
* gaveta;
* impressão automática de comprovante de pagamento.

Esses itens pertencem aos blocos seguintes.

==================================================
4. PRINTJOB — CLAIM/LEASE
=========================

Hoje vários POS podem estar na mesma filial.

Exemplo:

POS 01
POS 02
POS 03

Todos podem alcançar:

192.168.0.100:9100

Mas APENAS UM pode executar cada PrintJob.

Implementar conceito de claim/lease.

Exemplo conceitual:

PrintJob:
PENDING

POS 02:
claim

PrintJob:
PROCESSING
claimed_by = POS 02
lease_until = ...

Enquanto a lease for válida:

POS 01 não executa;
POS 03 não executa.

Se POS 02 realmente executar:

→ PRINTED

Se houver falha confirmada:

→ FAILED

Se POS 02 morrer antes de executar e a lease expirar:

→ outro POS pode assumir com segurança.

NÃO permitir dois POS imprimirem o mesmo job simultaneamente.

Utilizar transação/locking adequado no backend.

O claim precisa ser atômico.

==================================================
5. MODELO DE EXECUTOR
=====================

Não amarrar PrintJob diretamente a um único POS fixo para impressoras de rede.

Uma impressora NETWORK pode ser alcançada por qualquer POS elegível da filial.

O backend deve permitir que um POS ativo da filial assuma um PrintJob compatível.

Preparar arquitetura para futuramente suportar:

executor_type:

POS
PRINT_AGENT
LOCAL_DEVICE

Mas NÃO implementar Print Agent/Stone agora.

Não precisa obrigatoriamente usar exatamente esse campo se existir arquitetura melhor.

O importante é não estruturar a solução assumindo que todo PrintJob sempre será executado pelo backend.

==================================================
6. ESTADOS DO PRINTJOB
======================

Preservar:

PENDING
PROCESSING
PRINTED
FAILED
CANCELLED

Adicionar estado equivalente a:

UNCERTAIN

se necessário.

Semântica obrigatória:

# FAILED

sabemos que a impressão NÃO foi concluída.

# UNCERTAIN

houve envio ou tentativa física e não é possível garantir se o papel saiu.

Exemplo:

socket conectou;
dados começaram a ser enviados;
conexão caiu antes do ACK local.

Não executar retry automático cego de UNCERTAIN.

Evitar ticket duplicado na cozinha.

==================================================
7. LEDGER LOCAL DE IMPRESSÃO
============================

O Flutter deve manter estado local mínimo e persistente dos PrintJobs executados.

Exemplo conceitual:

print_job_id
printer_id
idempotency_key
state
attempted_at
sent_at
acknowledged_at

Se:

POS enviar dados para impressora
↓
internet com CORE API cair antes da confirmação
↓
app reiniciar

o POS deve saber que aquele job já foi transmitido fisicamente.

Não reenviar automaticamente como se nunca tivesse tentado.

Reconciliar com o backend quando a conexão retornar.

Usar armazenamento local adequado.

Não armazenar secrets desnecessariamente.

==================================================
8. IDEMPOTÊNCIA
===============

Cada PrintJob precisa continuar sendo identificável de maneira estável.

Preservar a ideia atual de:

idempotency_key

Não gerar uma nova impressão física automaticamente apenas porque a confirmação HTTP falhou.

Diferenciar claramente:

retry técnico antes do envio;

retry após falha comprovada;

reprint solicitado;

resultado incerto.

==================================================
9. APIS POS DE IMPRESSÃO
========================

Criar endpoints específicos para o CORE POS, seguindo o padrão atual de:

device authentication;
operator session quando aplicável;
branch scope;
permissions;
audit metadata.

Precisamos de operações equivalentes a:

GET jobs disponíveis para execução;

POST claim;

POST printed;

POST failed;

POST uncertain;

POST reconcile/status;

GET configuração de impressoras NETWORK aplicável ao POS/filial.

Não é obrigatório usar esses paths/nomes literalmente.

Usar padrão já existente do projeto.

Não expor PrintJobs de outra filial.

Não permitir que POS de outra filial assuma impressão.

==================================================
10. POLLING / BUSCA DE JOBS
===========================

Para este primeiro bloco, pode utilizar polling eficiente pelo POS.

Não precisamos implementar WebSocket agora.

O POS deve verificar novos PrintJobs em intervalo curto e seguro enquanto estiver:

* ativo;
* autenticado;
* foreground;
* operacional.

Não criar polling agressivo.

Não permitir requisições sobrepostas.

Possibilidade conceitual:

2–5 segundos

ou estratégia equivalente razoável.

Se não houver jobs:

não gerar ruído desnecessário.

Se estiver sem internet:

não travar o restante do POS.

==================================================
11. PRINT MANAGER NO FLUTTER
============================

Criar arquitetura interna equivalente a:

PrintManager
PrintJobClient
PrintRenderer
PrinterTransport
LocalPrintLedger

Pode ajustar nomes conforme padrão do projeto.

Responsabilidades:

PrintManager
→ coordena ciclo.

PrintJobClient
→ conversa com CORE API.

PrintRenderer
→ transforma payload em bytes ESC/POS.

PrinterTransport
→ envia para hardware.

LocalPrintLedger
→ guarda estado local/reconciliação.

NÃO colocar toda a lógica dentro de AppController.

Evitar arquivo gigante.

==================================================
12. NETWORK PRINTER TRANSPORT
=============================

Implementar transporte TCP local no Flutter.

Configuração existente:

PrinterDevice
connection_type = NETWORK

technical_configuration:

host
port
timeout

Exemplo:

host:
192.168.0.150

port:
9100

CORE POS deve abrir conexão direta:

POS
→ 192.168.0.150:9100

Não passar bytes da impressora pela VPS.

Usar timeout apropriado.

Fechar socket corretamente.

Capturar:

timeout;
host inválido;
connection refused;
network unreachable;
socket error.

Converter para estados controlados.

==================================================
13. ESC/POS
===========

Criar renderer central de produção.

No primeiro bloco suportar o necessário:

* texto;
* negrito;
* tamanho maior;
* alinhamento;
* quebra de linha;
* corte, quando suportado/configurado.

Não acoplar layout do ticket diretamente ao socket.

Exemplo:

ProductionTicketRenderer
→ bytes

NetworkPrinterTransport
→ transmite bytes.

Preparar para largura:

58mm
80mm

mesmo que inicialmente trabalhemos principalmente com 80mm.

Não depender de caracteres especiais que quebrem impressoras antigas.

Tratar encoding adequadamente para português.

==================================================
14. LAYOUT DO TICKET DE PRODUÇÃO
================================

Ticket NEW deve mostrar pelo menos:

CORE PDV ou nome da filial, se configurado;

SETOR;

MESA, quando origem for Mesa;

identificador da Venda Rápida quando origem for venda;

horário;

operador/atendente quando disponível;

quantidade;

produto;

modificadores;

observação.

Exemplo conceitual:

==============================
COZINHA

MESA 10
19:42

2x X-BACON

* SEM CEBOLA
* BACON EXTRA

OBS:
BEM PASSADO

# Atendente: Felipe

Não imprimir valores/preços no ticket de produção por padrão.

==================================================
15. CANCELAMENTO
================

ProductionEvent.CANCEL deve gerar ticket físico próprio.

Nunca apagar/reutilizar o ticket NEW.

Layout deve ser muito evidente.

Exemplo:

---

*** CANCELAMENTO ***

---

MESA 10

1x X-BACON

Motivo:
Cliente desistiu

Operador:
Felipe

Não confundir cancelamento com novo pedido.

Preservar relacionamento:

original_job.

==================================================
16. REIMPRESSÃO
===============

Preservar diferença entre:

retry
e
reprint.

Retry:

falhou tecnicamente.

Reprint:

já imprimiu, mas operador solicita nova via.

Usar:

reprint_of
reprint_number

já existentes.

Ticket de reimpressão deve trazer:

*** REIMPRESSÃO ***

e número, se disponível:

REIMPRESSÃO #1

Não reutilizar o PrintJob original mudando seu status.

Criar nova execução conforme arquitetura atual.

==================================================
17. AGRUPAMENTO FÍSICO POR SETOR
================================

Hoje ProductionJob é granular por item/destination.

Preservar isso.

Mas NÃO imprimir necessariamente uma folha por item.

Se uma única operação criar:

X-Bacon → COZINHA
Batata → COZINHA
Heineken → BAR

o ideal é:

1 ticket físico COZINHA:
X-Bacon
Batata

1 ticket físico BAR:
Heineken

Sem perder os ProductionJobs individuais.

Implementar agrupamento físico apenas quando os jobs forem compatíveis e fizerem parte da mesma operação lógica.

NÃO misturar:

Mesas diferentes;

vendas diferentes;

NEW com CANCEL;

jobs de horários/operações diferentes.

Se o agrupamento adicionar risco significativo nesta primeira implementação, estruturar corretamente o batch/dispatch para suportá-lo e documentar o que ficou para refinamento.

Mas NÃO quebrar rastreabilidade individual dos ProductionJobs.

==================================================
18. MESA
========

Mesa imprime no momento de:

ENVIAR PEDIDO / CONFIRMAR TableOrderItem.

NÃO esperar:

pagamento;
fechamento da Mesa;
Sale final.

Fluxo:

save_table_order
↓
TableOrderItem confirmado
↓
ProductionJob
↓
PrintJob
↓
CORE POS
↓
impressora.

Preservar:

estoque;
financial_snapshot;
produção;
tickets existentes.

Não mexer no motor financeiro da Mesa.

Não mexer em TablePayment.

Não mexer no agrupamento financeiro atual.

==================================================
19. VENDA RÁPIDA
================

Venda Rápida deve gerar produção quando a venda estiver efetivamente confirmada/finalizada conforme fluxo atual.

Fluxo esperado:

QuickSaleCheckout
↓
pagamentos
↓
finalize_quick_checkout
↓
Sale / SaleItem
↓
ProductionJob
↓
PrintJob.

Não imprimir produto antes de a operação que gera a venda estar confirmada, salvo se a arquitetura atual já possuir uma regra explícita diferente.

Preservar:

finalize_sale();
estoque;
pagamentos;
idempotência;
frozen quick preview.

==================================================
20. NÃO DUPLICAR PRODUÇÃO NO FECHAMENTO DA MESA
===============================================

Mesa já gerou produção ao confirmar o TableOrderItem.

Quando:

close_table_attendance()
↓
finalize_sale()

e surgirem SaleItems,

NÃO gerar novamente ticket de produção para os mesmos itens.

Verificar o fluxo atual de:

create_table_production_jobs
create_sale_production_jobs

e garantir que o fechamento da Mesa não imprima tudo novamente.

Mesa:
produção nasce do TableOrderItem.

Venda Rápida:
produção nasce do SaleItem.

Essa distinção deve permanecer.

==================================================
21. TESTE DE IMPRESSORA
=======================

Hoje o backend tenta executar teste.

No novo fluxo:

Backoffice/POS solicita teste;
↓
backend cria PrintJob is_test=True;
↓
POS local assume;
↓
POS imprime fisicamente;
↓
confirma resultado.

Ticket:

CORE PDV

TESTE DE IMPRESSÃO

Filial:
...

Impressora:
...

IP:
...

Data/hora:
...

Se sucesso:

operational_status = ONLINE
last_seen_at atualizado
last_test_at atualizado.

Se falha confirmada:

OFFLINE / FAILED conforme semântica.

Backend não deve tentar acessar o IP local.

==================================================
22. STATUS DA IMPRESSORA
========================

Para NETWORK, status deve refletir observação real do executor local.

Estados atuais podem ser reaproveitados:

NOT_TESTED
ONLINE
OFFLINE
FAILED

BRIDGE_UNAVAILABLE não se aplica normalmente a NETWORK.

Evitar considerar impressora ONLINE para sempre porque um teste antigo funcionou.

Guardar:

last_seen_at
last_test_at
last_operational_error.

==================================================
23. BACKOFFICE
==============

Não fazer redesign completo.

Aproveitar telas atuais de impressoras/produção.

Garantir no cadastro NETWORK:

nome;
filial;
host/IP;
porta;
timeout;
largura do papel, se necessário;
status;
destino(s).

Adicionar/ajustar ação:

TESTAR IMPRESSÃO

Agora o teste deve ser enfileirado para execução por POS local.

Mostrar feedback:

Aguardando POS executar;
Impresso;
Falhou;
Resultado incerto.

Mostrar histórico dos PrintJobs.

==================================================
24. CONFIGURAÇÃO DE PRODUTOS
============================

Preservar:

ProductProductionDestination.

Permitir configurar:

Produto
→ um ou mais setores de produção.

Exemplo:

Combo:
→ COZINHA
→ BAR

Se já existe UI funcional para isso, reutilizar.

Não criar vínculo Produto → PrinterDevice direto.

==================================================
25. PERMISSÕES
==============

Reutilizar RBAC Django existente.

Preservar permissões atuais como:

printers.manage
print_jobs.view
print_jobs.retry
print_jobs.reprint
production.view

Criar novas somente se realmente necessário.

Execução automática de PrintJob pelo POS deve depender principalmente de:

device válido;
branch correta;
capacidade de impressão;

e não de o operador ter de possuir uma permissão humana de "gerenciar impressoras".

Ações manuais como:

reprint;
retry;
configuração;

continuam respeitando permissões.

==================================================
26. AUDITORIA
=============

Registrar eventos relevantes:

print_job.claimed
print_job.printed
print_job.failed
print_job.uncertain
print_job.reconciled
print_job.retry
print_job.reprint
printer.test

Guardar quando aplicável:

PrintJob;
POSDevice executor;
PrinterDevice;
branch;
operador quando ação humana;
tentativa;
erro;
timestamp.

Não gravar dados desnecessariamente sensíveis.

==================================================
27. NÃO MEXER
=============

NÃO alterar nesta missão:

Comandas;

motor financeiro de Venda Rápida;

motor financeiro de Mesa;

TablePayment;

QuickSalePayment;

CashSession;

descontos;

promoções;

comissões;

taxa de serviço;

estoque além da integração de produção já existente;

Stone;

Cielo;

PagBank;

fiscal;

recibo do cliente;

impressora local Stone;

Print Agent.

==================================================
28. COMPATIBILIDADE
===================

Não quebrar registros históricos já existentes de:

PrinterDevice
ProductionJob
PrintJob
Ticket.

Criar migrations seguras caso precise adicionar:

claimed_by;
lease_until;
uncertain status;
executor metadata;
paper width;
ou campos equivalentes.

Não apagar histórico.

==================================================
29. CENÁRIOS OBRIGATÓRIOS
=========================

CENÁRIO A — MESA / COZINHA

Mesa 10 envia:

2x X-Bacon

Produto:
X-Bacon → COZINHA

COZINHA:
PrinterDevice NETWORK
192.168.0.150:9100

Esperado:

1 ProductionJob NEW;
PrintJob disponível;
um POS da filial faz claim;
imprime fisicamente;
backend fica PRINTED.

==================================================

CENÁRIO B — DOIS POS

POS 01 e POS 02 veem a mesma impressora.

Existe PrintJob PENDING.

Esperado:

somente um consegue claim.

Nunca duas impressões físicas automáticas.

==================================================

CENÁRIO C — FALHA ANTES DE ENVIAR

POS faz claim.

Não consegue conectar à impressora.

Esperado:

FAILED.

Pode ser submetido a retry seguro.

==================================================

CENÁRIO D — RESULTADO INCERTO

POS consegue iniciar transmissão.

Estado final não é confiável.

Esperado:

UNCERTAIN ou equivalente.

Não executar retry automático cego.

==================================================

CENÁRIO E — CANCELAMENTO

Item já foi enviado à cozinha.

Operador cancela.

Esperado:

ProductionJob CANCEL;
ticket físico de CANCELAMENTO.

==================================================

CENÁRIO F — REPRINT

PrintJob já PRINTED.

Operador solicita reimpressão.

Esperado:

novo PrintJob;
reprint_of;
reprint_number = 1;
papel identificado como REIMPRESSÃO.

==================================================

CENÁRIO G — VENDA RÁPIDA

Venda contém item do setor BAR.

Venda finaliza.

Esperado:

SaleItem;
ProductionJob;
PrintJob;
BAR imprime.

==================================================

CENÁRIO H — FECHAMENTO DE MESA

Mesa já teve seus pedidos impressos.

Mesa é paga e fechada.

Esperado:

NÃO imprimir novamente todos os itens por causa da criação da Sale.

==================================================

CENÁRIO I — TESTE

Operador solicita teste da Impressora Cozinha.

Esperado:

backend enfileira is_test;
POS local imprime;
resultado atualiza status real da impressora.

==================================================
30. TESTES / VALIDAÇÃO
======================

Adicionar testes direcionados para o novo domínio crítico.

Backend:

claim atômico;

lease;

filial;

device;

state transition;

printed;

failed;

uncertain;

retry;

reprint;

test print;

não duplicação da Mesa no fechamento;

Venda Rápida gera produção corretamente.

Flutter:

renderer;

ledger local;

seleção de job;

transições;

tratamento de socket;

reconciliação.

Rodar ao final:

flutter analyze
flutter test

python manage.py check
python manage.py makemigrations --check --dry-run

testes direcionados da production/pos/attendance/sales afetados.

git diff --check

Não tente corrigir toda a suíte backend antiga nesta missão caso existam failures não relacionados ao Bloco 1.

Documentar os failures pré-existentes separadamente.

==================================================
31. CHECKPOINT FINAL
====================

Ao terminar informe:

1. arquitetura implementada;
2. models alterados/criados;
3. migrations;
4. endpoints POS adicionados;
5. como funciona claim;
6. duração/renovação de lease;
7. como dois POS são impedidos de imprimir o mesmo job;
8. como funciona LocalPrintLedger;
9. como diferencia FAILED e UNCERTAIN;
10. como funciona TCP LAN;
11. como ESC/POS é renderizado;
12. formato do ticket NEW;
13. formato do CANCEL;
14. como funciona retry;
15. como funciona reprint;
16. como funciona teste de impressora;
17. como Mesa dispara impressão;
18. como Venda Rápida dispara impressão;
19. confirmação de que fechar Mesa NÃO imprime novamente;
20. como Product → Destination → Printer foi preservado;
21. alterações no Backoffice;
22. permissões;
23. auditoria;
24. arquivos alterados;
25. resultado dos testes;
26. limitações que ficaram explicitamente para Bloco 2 e Bloco 3.

DEPOIS PARE.

NÃO INICIE BLOCO 2.

NÃO INICIE STONE.

NÃO INICIE PRINT AGENT.

NÃO INICIE OUTRA TAREFA.
