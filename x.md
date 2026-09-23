TRABALHE NO HEAD MAIS RECENTE DA MAIN.

Na última revisão, o HEAD era:

`89b4d5a9dcffd6d57902e29316dc1bc390728d05`

NÃO refaça a arquitetura de impressão.

Preservar:

* PrintDocument
* PrintRoute
* PrintRouteOverride
* PrintDocumentRequest
* PrintJob
* ProductionJob
* PrintManager
* claim / lease / dispatch / reconcile
* UNCERTAIN
* impressão NETWORK local
* roteamento por finalidade
* ProductionDestination
* margem ESC/POS já implementada
* wrapping
* feed/corte
* herança filial -> POS

Esta missão é SOMENTE para corrigir os problemas abaixo encontrados na revisão do HEAD atual.

==================================================
REGRA CRÍTICA
=============

NÃO EXECUTE TESTES.

NÃO execute:

* flutter analyze
* flutter test
* pytest
* npm test
* npm build
* npm lint
* builds
* suites
* makemigrations --check
* qualquer validação pesada

Pode criar migration se necessária.

EU FAREI A VALIDAÇÃO MANUAL.

==================================================

1. CORRIGIR TABLE PAYMENT + PRINT DOCUMENT
   ==================================================

Existe uma inconsistência concreta.

Hoje:

`pos/lib/payments/table_payment_page.dart`

usa:

`payment.printDocument`

Porém:

`pos/lib/attendance/attendance_models.dart`

na classe `TablePayment`

NÃO possui o campo:

`printDocument`

E:

`backend/apps/attendance/serializers.py`

em `TablePaymentSerializer`

também NÃO retorna `print_document`.

CORRIGIR OS DOIS LADOS.

O backend deve retornar para cada pagamento de Mesa o PrintDocument atual de:

`PAYMENT_RECEIPT`

com:

source_type:
`table_payment`

source_id:
ID do pagamento

IMPORTANTE:

NÃO criar PrintDocument só para montar o serializer.

A consulta deve apenas procurar documento existente.

Exemplo conceitual:

payment:
{
id: 10,
amount: "50.00",
...
print_document: {
...
}
}

ou:

`print_document: null`

O Flutter deve:

* adicionar `PrintDocumentResult? printDocument` em `TablePayment`;
* interpretar `print_document`;
* restaurar `_paymentDocuments` corretamente em `_refresh()`.

Isso deve eliminar também qualquer provável erro de compilação causado pelo acesso atual a `payment.printDocument`.

==================================================
2. GET DE MESA DEVE SER 100% READ-ONLY
======================================

Existe um problema arquitetural atual em:

`POSTableAttendanceView.get()`

Hoje o GET percorre:

* TABLE_BILL
* TABLE_CONFERENCE
* TABLE_FINAL_RECEIPT

e chama:

`create_print_document(...)`

Isso NÃO pode acontecer.

GET não deve persistir documentos.

Hoje apenas abrir/atualizar uma Mesa pode:

* criar PrintDocument;
* aumentar version;
* gerar auditoria;
* poluir histórico.

REMOVER qualquer criação/persistência de PrintDocument do GET.

==================================================
3. RESOLVER ESTADO ATUAL DO DOCUMENTO SEM CRIAR
===============================================

Precisamos continuar devolvendo:

`print_documents`

no GET da Mesa.

Mas de forma READ-ONLY.

Criar um selector/helper equivalente a:

`current_print_document(...)`

ou nome apropriado.

Ele deve:

1. calcular o snapshot atual da origem;
2. calcular o snapshot_hash atual;
3. procurar um PrintDocument já existente com:

* branch;
* document_type;
* source_type;
* source_id;
* snapshot_hash;

4. retornar o documento se existir;
5. retornar `None` se nunca foi emitido.

NÃO criar documento.

Exemplo:

Mesa R$100
→ Conferência v1 impressa.

Depois adiciona produto:
Mesa R$130.

GET:

calcula hash de R$130.

Não existe documento com esse hash.

Retorna:

nenhum documento atual para Conferência.

Logo o POS mostra:

IMPRIMIR

A Conferência v1 de R$100 continua no histórico, mas NÃO é considerada documento atual.

==================================================
4. GET DE MESA E VERSIONAMENTO
==============================

O GET deve devolver somente o documento correspondente ao SNAPSHOT ATUAL para cada finalidade.

Não simplesmente:

"último documento criado".

Tipos:

* TABLE_BILL
* TABLE_CONFERENCE
* TABLE_FINAL_RECEIPT

TABLE_FINAL_RECEIPT só é válido se a Mesa estiver fechada e possuir venda finalizada válida.

Não gerar erro de domínio no GET por documento que ainda não é aplicável.

Apenas omitir/null.

==================================================
5. CORRIGIR ESTADO FAILED NO FLUTTER
====================================

Existe bug atual em:

`PrintDocumentResult.fromJson`

Hoje:

`queued: json['queued'] == true || jobs.isNotEmpty`

Isso está errado.

Um documento que possui um job FAILED não está necessariamente "queued".

Exemplo:

FAILED
physical_dispatch_started_at = null

deve resultar em:

* queued = false
* retryEligible = true
* awaitingInitialPrint = false
* label = TENTAR NOVAMENTE

CORRIGIR.

`queued` deve significar SOMENTE que existe job inicial em:

* pending
* processing

Não usar:

`jobs.isNotEmpty`

como sinônimo de queued.

==================================================
6. ORDEM DOS ESTADOS NO FLUTTER
===============================

Revisar os getters:

* canReprint
* awaitingInitialPrint
* needsInitialPrint
* retryEligible
* printActionLabel

A prioridade deve ser coerente.

Conceitualmente:

UNCERTAIN ou PRINTED inicial
→ REIMPRIMIR

FAILED antes de dispatch físico
→ TENTAR NOVAMENTE

PENDING / PROCESSING
→ IMPRESSÃO PENDENTE

nenhum job inicial
→ IMPRIMIR

Não bloquear retry de FAILED porque existe PrintJob no documento.

==================================================
7. RETRY DO DOCUMENTO
=====================

Hoje a UI sabe identificar `retryEligible`, mas a ação de vários botões ainda segue apenas:

canReprint
? reprint
: issue

Isso precisa ser corrigido.

Se o documento atual possui job inicial:

FAILED
+
physical_dispatch_started_at == null

o usuário deve executar retry do job inicial existente.

NÃO criar nova emissão.
NÃO criar reprint.

Criar/usar endpoint seguro de retry de PrintDocument se necessário.

Pode internamente executar `retry_print_job()` para os jobs iniciais FAILED elegíveis.

A UI deve tratar:

TENTAR NOVAMENTE

como retry técnico.

Preservar:

retry != reprint.

==================================================
8. RETRY DE DOCUMENTO COM MÚLTIPLAS IMPRESSORAS/CÓPIAS
======================================================

Se um PrintDocument inicial gerou múltiplos PrintJobs:

Exemplo:

TABLE_BILL
→ Printer A
→ Printer B

ou:

copies = 2

retry deve considerar cada job.

Nunca reenviar automaticamente um job que já está:

PRINTED
ou
UNCERTAIN.

Somente FAILED comprovadamente antes de envio físico pode voltar a PENDING.

Não duplicar as cópias já concluídas.

==================================================
9. VENDA RÁPIDA — PERSISTIR PRINTDOCUMENT DOS PAGAMENTOS
========================================================

A Venda Rápida agora permite:

PAYMENT_RECEIPT
source_type = quick_sale_payment

Isso ficou correto.

Porém `_quick_checkout_payload()` ainda devolve pagamentos sem:

`print_document`

Então o estado desaparece quando o checkout é recarregado.

CORRIGIR.

Para cada `QuickSalePayment` não reverso, devolver o PrintDocument atual correspondente a:

document_type:
`payment_receipt`

source_type:
`quick_sale_payment`

source_id:
payment.id

SOMENTE consultar documento existente.

NÃO criar documento durante GET/payload.

==================================================
10. FLUTTER — QUICK SALE PAYMENT STATE
======================================

Ao receber `_quick_checkout_payload()`, o model Flutter de pagamento rápido deve conter:

`PrintDocumentResult? printDocument`

e a tela deve reconstruir:

`_paymentDocuments`

a partir desses dados.

Então:

imprimi comprovante
→ atualiza checkout
→ sai e volta
→ continua REIMPRIMIR

e não volta para IMPRIMIR.

==================================================
11. MESA — PAGAMENTO STATE
==========================

Fazer a mesma persistência para TablePayment.

Após:

IMPRIMIR COMPROVANTE

se o usuário:

* atualizar;
* sair da página de pagamentos;
* voltar;
* fechar/reabrir fluxo;

o sistema deve consultar backend e continuar mostrando o estado correto.

Não depender do Map em memória.

==================================================
12. NÃO CRIAR DOCUMENTOS EM SERIALIZERS
=======================================

Regra importante:

Serializers/GET/selectors de leitura podem:

* localizar;
* calcular hash;
* serializar;

mas NÃO devem:

* criar PrintDocument;
* criar PrintJob;
* alterar version;
* auditar emissão.

PrintDocument só deve nascer quando existir uma intenção real:

* emissão manual;
* impressão automática disparada por evento;
* outro fluxo explícito de emissão.

==================================================
13. HARDENING DA IDEMPOTÊNCIA DE PrintDocumentRequest
=====================================================

Foi criada corretamente:

`PrintDocumentRequest`

com:

* branch;
* document;
* action;
* idempotency_key.

Porém ainda falta proteger reutilização indevida da mesma chave.

Exemplo:

request 1:

idempotency_key = ABC
action = issue
document_type = table_bill
source = table 10

Depois por bug do cliente:

idempotency_key = ABC
action = issue
document_type = table_conference
source = table 15

Hoje não devemos simplesmente retornar o documento anterior.

Adicionar fingerprint persistente da INTENÇÃO.

Pode ser campo como:

`request_fingerprint`

ou estrutura equivalente.

==================================================
14. FINGERPRINT DE ISSUE
========================

Para ISSUE, fingerprint deve representar pelo menos:

* action;
* branch;
* document_type;
* source_type;
* source_id;
* pos_device quando semanticamente necessário.

Pode incluir snapshot_hash atual se isso fizer sentido sem quebrar replay da mesma intenção.

A decisão deve preservar idempotência correta mesmo com resposta HTTP perdida.

Se a mesma idempotency_key chegar com os mesmos dados:

→ retornar replay.

Se chegar com dados diferentes:

→ ERRO DE CONFLITO DE IDEMPOTÊNCIA.

Nunca retornar silenciosamente documento de outra operação.

==================================================
15. FINGERPRINT DE REPRINT
==========================

Para REPRINT:

fingerprint deve considerar pelo menos:

* action;
* branch;
* document_id;
* reason quando semanticamente relevante.

Mesma chave + mesmo documento:

→ replay.

Mesma chave + outro documento:

→ conflito.

==================================================
16. REPRINT IDEMPOTENTE DEVE RETORNAR EXATAMENTE A MESMA EXECUÇÃO
=================================================================

Revisar:

`reprint_print_document()`

Hoje, no replay, ele retorna todos os reprints existentes do documento.

Isso é amplo demais.

Exemplo:

Documento já possui:

reprint #1
reprint #2
reprint #3

A chave X criou apenas #3.

Replay da chave X deve representar especificamente a execução criada pela chave X.

Não simplesmente retornar:

todos os reprints históricos.

Se necessário, relacionar PrintDocumentRequest aos PrintJobs gerados pela ação ou registrar metadata suficiente para identificar exatamente os jobs daquela requisição.

Preservar histórico completo.

==================================================
17. ISSUE IDEMPOTENTE E NOVO SNAPSHOT
=====================================

Exemplo:

Mesa snapshot A.

Issue com key X
→ documento A.

Resposta se perde.

Cliente repete key X:
→ retorna documento A.

Correto.

Mas se o cliente reutilizar key X quando snapshot atual já é B por erro do cliente:

→ NÃO criar B;
→ NÃO retornar A silenciosamente como se fosse a nova intenção;
→ detectar fingerprint/conflito conforme política definida.

==================================================
18. QUICK SALE AUTOMATIC PRINT
==============================

Não mexer desnecessariamente.

A finalização da Venda Rápida atualmente conclui a venda e depois tenta:

* QUICK_SALE_RECEIPT
* TICKET

com tratamento que evita falha de impressão invalidar a venda.

Preservar isso.

Não reintroduzir impressão dentro da transação financeira principal.

==================================================
19. TABLE CLOSE AUTOMATIC PRINT
===============================

Preservar o `transaction.on_commit()` já implementado para:

TABLE_FINAL_RECEIPT

A Mesa deve continuar fechando mesmo se a impressão falhar.

==================================================
20. TABLE BILL AUTOMATIC PRINT
==============================

Preservar o `transaction.on_commit()` já implementado ao solicitar conta.

Não deixar falha de impressão desfazer a solicitação da conta.

==================================================
21. DOCUMENT TYPE
=================

Preservar o contrato novo lowercase:

* table_bill
* table_conference
* table_final_receipt
* quick_sale_receipt
* payment_receipt
* ticket

Não voltar a serializar como enum name uppercase.

==================================================
22. PRINT ROUTES
================

Preservar as validações atuais:

DISABLED
→ pode não ter impressora

MANUAL / AUTOMATIC
→ exige ao menos uma impressora

Neste bloco:
→ somente PrinterDevice NETWORK ativo

Não relaxar isso agora.

==================================================
23. TESTE DE IMPRESSORA
=======================

Preservar a correção atual.

Teste de PrinterDevice NETWORK NÃO deve exigir ProductionDestination.

Não voltar atrás.

==================================================
24. MARGENS ESC/POS
===================

Preservar a implementação atual:

58mm:

* printable width 28
* left margin 2

80mm:

* printable width 42
* left margin 3

Preservar:

* wrapping;
* centralização;
* margin em `_line`;
* 4 feeds antes do corte.

NÃO mexer nisso nesta missão, salvo erro inevitável relacionado à compilação.

==================================================
25. NÃO COMEÇAR NOVO BLOCO
==========================

NÃO implementar:

* Stone printer;
* USB;
* Bluetooth;
* Print Agent;
* fiscal;
* delivery;
* KDS;
* Comanda.

Somente corrigir o estado atual.

==================================================
26. CHECKPOINT
==============

Ao terminar informe:

1. como corrigiu `TablePayment.printDocument`;
2. como backend passou a retornar print_document no pagamento de Mesa;
3. como GET da Mesa ficou 100% read-only;
4. como o documento correspondente ao snapshot atual é localizado sem criar registro;
5. como `FAILED` é tratado no Flutter;
6. como funciona TENTAR NOVAMENTE;
7. como retry de PrintDocument funciona com múltiplos jobs;
8. como QuickSalePayment passou a persistir PrintDocument;
9. como TablePayment persiste estado após refresh;
10. como PrintDocumentRequest passou a detectar conflito de idempotência;
11. como replay de reprint identifica exatamente sua própria execução;
12. migrations criadas;
13. arquivos backend alterados;
14. arquivos Flutter alterados;
15. qualquer ponto que ainda dependa exclusivamente de teste físico.

NÃO EXECUTE TESTES.

NÃO EXECUTE ANALYZE.

NÃO EXECUTE BUILD.

DEPOIS PARE.
