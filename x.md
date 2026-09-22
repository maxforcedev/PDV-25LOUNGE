TRABALHE NO HEAD ATUAL DA MAIN.

CORRIJA SOMENTE OS PONTOS ABAIXO DO BLOCO 1 DE IMPRESSÃO.

NÃO INICIE BLOCO 2.

NÃO EXECUTE TESTES.

NÃO EXECUTE:

flutter test
flutter analyze
flutter build
python manage.py test
python manage.py check
makemigrations --check
git diff --check
ou qualquer suíte/comando de validação.

APENAS implemente as correções, revise o código/diff localmente sem comandos pesados e entregue o checkpoint final.

==================================================

1. PROBLEMA CRÍTICO — LEASE PODE DUPLICAR IMPRESSÃO
   ==================================================

Estado atual:

PrintJob PENDING
→ POS 01 claim
→ PROCESSING
→ lease de 60 segundos
→ POS 01 envia fisicamente para impressora
→ internet com a API cai antes do POST /printed
→ lease expira
→ POS 02 pode pegar o mesmo PROCESSING expirado
→ POS 02 imprime novamente.

Isso viola a principal regra do sistema:

UMA OPERAÇÃO FÍSICA NÃO PODE SER REENVIADA AUTOMATICAMENTE QUANDO EXISTE POSSIBILIDADE DE O PAPEL JÁ TER SAÍDO.

O LocalPrintLedger do POS 01 sozinho não resolve isso porque o POS 02 não conhece o ledger local do POS 01.

==================================================
2. SEPARAR RESERVA DE INÍCIO DE TRANSMISSÃO FÍSICA
==================================================

Precisamos distinguir:

A)

POS apenas reservou/claimou o job
MAS ainda não começou a mandar para a impressora.

Esse job pode voltar para outro POS após lease expirada.

B)

POS informou ao backend que está prestes a iniciar a transmissão física.

A partir daí o job NÃO pode ser automaticamente entregue para outro POS apenas porque a lease expirou.

Implementar conceito equivalente a:

CLAIMED / PROCESSING
→ transmissão ainda não iniciada

DISPATCHING
ou
dispatch_started_at != null
→ transmissão física pode ter acontecido

Não é obrigatório criar exatamente um novo status `dispatching`.

Pode usar campo explícito como:

dispatch_started_at
physical_dispatch_started_at
transport_started_at

ou arquitetura equivalente.

O importante é a semântica.

==================================================
3. FLUXO CORRETO
================

Fluxo desejado:

PENDING

↓

POS 01 CLAIM

↓

PROCESSING
transmissão física ainda não iniciada

↓

POS 01 chama API informando:

"VOU INICIAR O ENVIO FÍSICO"

↓

backend persiste isso atomicamente

↓

SÓ DEPOIS

POS abre socket:

192.168.x.x:9100

↓

envia ESC/POS

↓

se sucesso:

PRINTED

se falha comprovadamente antes do envio:

FAILED

se envio começou e resultado não é confiável:

UNCERTAIN.

==================================================
4. LEASE EXPIRADA
=================

Se:

PROCESSING
+
transmissão física NÃO iniciada
+
lease expirou

outro POS pode assumir.

Se:

transmissão física iniciada
+
não temos PRINTED/FAILED definitivo

NÃO colocar novamente na fila automática.

Esse estado deve exigir reconciliação e, se necessário:

UNCERTAIN.

Prioridade:

EVITAR DUPLICAÇÃO.

É aceitável exigir intervenção/reimpressão explícita quando existe dúvida.

Não é aceitável imprimir duas vezes automaticamente.

==================================================
5. RACE ACEITÁVEL
=================

Pode acontecer:

POS marca "dispatch iniciado"
↓
app morre
↓
nem chegou a abrir o socket.

Nesse cenário o backend pode ficar UNCERTAIN mesmo sem papel ter saído.

Isso é propositalmente mais seguro.

Melhor exigir decisão humana/reprint do que mandar automaticamente outra impressão e correr risco de duplicidade na cozinha.

==================================================
6. BATCH INTEIRO
================

Essa regra precisa valer para o ticket físico inteiro.

Se:

PrintJob 10
PrintJob 11
PrintJob 12

possuem o mesmo:

batch_key

e formam um único ticket físico:

todos devem compartilhar coerentemente:

claim;
dispatch;
resultado;
uncertainty.

Não permitir:

job 10 PRINTED
job 11 reaparecer para outro POS
job 12 PROCESSING

quando os três foram transmitidos em um único pacote ESC/POS.

==================================================
7. RECONCILIAÇÃO LOCAL ESTÁ APAGANDO PROTEÇÃO DEMAIS
====================================================

Hoje o Flutter:

LocalPrintLedger
→ pega todos `sent`

chama:

reconcilePrintJobs(...)

e depois remove TODOS os IDs enviados ao endpoint caso a requisição HTTP tenha retornado com sucesso.

Porém o backend:

reconcile_print_jobs()

pode ignorar individualmente registros que não conseguiu reconciliar e retornar apenas:

job_ids efetivamente reconciliados.

Isso significa que:

HTTP 200
NÃO significa
"todos os entries foram reconciliados".

Corrigir.

==================================================
8. RECONCILE DEVE RETORNAR IDS REAIS
====================================

A API já retorna:

job_ids

Usar isso no Flutter.

Alterar o contrato:

reconcilePrintJobs(...)

para devolver os IDs que o backend realmente reconciliou.

LocalPrintLedger deve remover APENAS:

IDs confirmados pelo backend.

Exemplo:

enviados:

10
11
12

backend responde:

job_ids:
10
11

Flutter remove:

10
11

e MANTÉM:

12.

Nunca descartar um registro local `sent` só porque o endpoint respondeu HTTP 200.

==================================================
9. CONCORRÊNCIA ENTRE POS DURANTE RECONCILIAÇÃO
===============================================

Se o POS original possui localmente:

job 10 = sent

e o backend não consegue reconciliar porque o estado mudou:

NÃO apagar o ledger.

NÃO reenviar fisicamente.

Manter o registro para decisão/reconciliação posterior.

Se necessário o backend deve retornar informação suficiente para distinguir:

já PRINTED;
UNCERTAIN;
reconciliado;
conflito;
claim perdido.

Mas não transformar isso em retry físico automático.

==================================================
10. PRINTMANAGER NÃO DEVE DEPENDER DO OPERADOR HUMANO
=====================================================

Hoje:

PrintManager.setOperational(
controller.phase == AppPhase.home
)

Isso faz o executor de impressão parar quando:

* usuário faz logout;
* POS está na seleção de operador;
* POS está aguardando PIN.

Mas as APIs de impressão foram corretamente implementadas como:

device-authenticated

SEM depender de RBAC do operador humano.

Portanto o executor físico deve seguir a identidade do POSDevice, e não a sessão do operador.

Cenário:

POS da cozinha está pareado e ligado.

Está na tela:

SELECIONE O OPERADOR

Outro POS envia pedido da Mesa.

A impressora da cozinha deve continuar recebendo os tickets.

Não exigir que algum operador fique permanentemente logado só para o dispositivo servir como executor de impressão.

==================================================
11. FASES DO APP
================

Ativar PrintManager quando:

* device está pareado;
* device está operacional;
* app está foreground;
* versão não está bloqueada;
* device possui network_printing.

Por exemplo:

operatorSelection
e
home

podem permitir impressão.

Não imprimir durante:

pairing;
device bloqueado;
device revogado;
update obrigatório;
estado sem credencial válida.

Não acoplar ao PIN do operador.

==================================================
12. REPRINT DE TICKET AGRUPADO
==============================

Hoje vários PrintJobs podem possuir o mesmo:

batch_key

e serem renderizados como UM ÚNICO ticket físico.

Exemplo:

PrintJob 100:
2x X-Bacon

PrintJob 101:
1x Batata

mesmo batch_key
mesma cozinha
mesma impressora

papel físico:

2x X-Bacon
1x Batata.

Porém atualmente:

reprint_print_job(job=100)

cria somente uma cópia do job 100.

Resultado:

reimpressão fica:

2x X-Bacon

e perde:

1x Batata.

Isso está errado para uma REIMPRESSÃO DO TICKET FÍSICO.

==================================================
13. REPRINT DE BATCH
====================

Se o PrintJob original pertencer a um batch físico:

reimprimir qualquer item daquele batch

deve recriar o ticket físico completo.

Ou seja:

batch original:
100
101

reprint #1:

novo PrintJob A
novo PrintJob B

ambos com:

novo batch_key compartilhado;

reprint_number = 1;

relação/histórico com os jobs originais.

O renderer imprime:

*** REIMPRESSÃO #1 ***

2x X-Bacon
1x Batata.

Não perder rastreabilidade individual.

==================================================
14. REPRINT SEM BATCH
=====================

Se o PrintJob original não possuir batch_key:

comportamento atual de reimpressão individual pode permanecer.

==================================================
15. RETRY CONTINUA DIFERENTE DE REPRINT
=======================================

Preservar:

FAILED
→ retry técnico permitido.

UNCERTAIN
→ NÃO retry automático.

PRINTED
→ reprint explícito.

DISPATCH iniciado + resultado perdido
→ nunca voltar silenciosamente para PENDING.

==================================================
16. LAST_SEEN DA IMPRESSORA
===========================

Revisar também `_record_printer_observation()`.

Hoje `last_seen_at` é atualizado mesmo em alguns resultados FAILED.

Isso pode afirmar que a impressora foi "vista agora" quando nem foi possível conectar.

Sem alterar demais o escopo:

last_seen_at deve representar comunicação real/observação real do equipamento.

Falha antes de conectar não deve atualizar last_seen_at como se a impressora tivesse respondido.

Se houve transmissão iniciada/conexão real mas resultado ficou incerto, pode registrar observação coerente conforme os metadados disponíveis.

==================================================
17. PRESERVAR O QUE JÁ ESTÁ CORRETO
===================================

NÃO refazer:

ProductionDestination;

ProductProductionDestination;

PrinterDevice;

ProductionJob;

PrintJob;

ESC/POS renderer;

TCP LAN;

paper width 58/80;

Product → Destination → Printer;

Mesa → TableOrderItem → ProductionJob;

Venda Rápida → SaleItem → ProductionJob;

batch_key;

CANCEL;

teste enfileirado;

network_printing capability;

heartbeat atualizando capabilities;

device-authenticated printing endpoints.

Também preservar que:

fechamento da Mesa NÃO gera produção novamente.

O `confirmed_order_items` já impede `create_sale_production_jobs()` nesse fechamento.

==================================================
18. COMANDAS FORA DO ESCOPO
===========================

NÃO mexer em Comandas.

Ela será refeita futuramente.

==================================================
19. NÃO EXECUTAR TESTES
=======================

NÃO RODAR NENHUM TESTE.

NÃO RODAR ANALYZER.

NÃO RODAR BUILD.

NÃO RODAR SUÍTE BACKEND.

NÃO GASTAR TEMPO/CRÉDITOS COM VALIDAÇÕES AUTOMÁTICAS.

Eu farei a revisão do código pelo GitHub depois.

==================================================
20. CHECKPOINT FINAL
====================

Ao terminar informe SOMENTE:

1. como eliminou a possibilidade de outro POS assumir automaticamente um job cuja transmissão física já pode ter começado;
2. qual estado/campo representa início de dispatch físico;
3. quando uma lease expirada pode ser reclamada;
4. quando vira UNCERTAIN;
5. como ficou a reconciliação e quais IDs o Flutter remove do ledger;
6. como o PrintManager funciona sem operador logado;
7. quais fases do app permitem impressão;
8. como ficou reprint de batch;
9. como ficou last_seen_at;
10. migrations criadas;
11. arquivos alterados.

NÃO EXECUTE TESTES.

DEPOIS PARE.
