MISSÃO — Corrigir pendências finais do módulo de impressão + erro de build do POS

Trabalhe no HEAD mais recente da main.

Na última revisão, a main estava em:

89b4d5a9dcffd6d57902e29316dc1bc390728d05

Antes de alterar, confira o HEAD atual.

NÃO refaça a arquitetura de impressão.

Preservar:

PrintDocument
PrintRoute
PrintRouteOverride
PrintDocumentRequest
PrintJob
ProductionJob
PrintManager
claim / lease / dispatch / reconcile
UNCERTAIN
impressão NETWORK local
roteamento por finalidade
ProductionDestination
margens ESC/POS
wrapping
feed/corte
herança filial -> POS
==================================================
REGRA CRÍTICA

NÃO EXECUTE TESTES.

NÃO execute:

flutter analyze
flutter test
build Flutter
pytest
npm test
npm build
npm lint
backend suites
frontend suites
makemigrations --check
qualquer validação pesada

Pode criar migration se realmente necessária.

EU FAREI O BUILD E OS TESTES MANUALMENTE.

==================================================

ERRO DE BUILD CONFIRMADO — PRIORIDADE MÁXIMA
==================================================

O build real do CORE POS falhou com:

lib/payments/table_payment_page.dart:94:21:
Error: The getter 'printDocument' isn't defined for the type 'TablePayment'.

lib/payments/table_payment_page.dart:94:84:
Error: The getter 'printDocument' isn't defined for the type 'TablePayment'.

O código atual usa:

if (payment.printDocument != null)
  _paymentDocuments[payment.id] = payment.printDocument!;

porém TablePayment, em:

pos/lib/attendance/attendance_models.dart

não possui printDocument.

CORRIGIR COMPLETAMENTE, NÃO APENAS PARA COMPILAR.

==================================================
2. TABLE PAYMENT — FLUTTER

Em TablePayment:

adicionar:

PrintDocumentResult? printDocument

Fazer:

adicionar no construtor;
adicionar no model;
interpretar json['print_document'];
usar PrintDocumentResult.maybeFromJson(...);
manter null quando não existir comprovante.

Garantir import correto do model de impressão sem criar dependência circular desnecessária.

==================================================
3. TABLE PAYMENT — BACKEND

Em:

backend/apps/attendance/serializers.py

no TablePaymentSerializer,

retornar:

print_document

correspondente a:

document_type = payment_receipt
source_type = table_payment
source_id = payment.id

IMPORTANTE:

O serializer deve SOMENTE CONSULTAR.

NÃO chamar:

create_print_document()

NÃO criar:

PrintDocument
PrintJob
version
auditoria de emissão

Se não existir documento:

"print_document": null

Se existir, retornar estado suficiente para o POS saber:

id
document_type
initial_printed
reprint_eligible
queued
retry_eligible
jobs/status necessários
==================================================
4. PERSISTÊNCIA DO COMPROVANTE DE MESA

Após:

Pagamento R$50
→ IMPRIMIR COMPROVANTE

se o usuário:

sair da tela;
voltar;
atualizar;
fechar e reabrir o fluxo;

o backend deve devolver o print_document existente.

A UI deve continuar mostrando:

REIMPRIMIR COMPROVANTE

quando aplicável.

Não depender só de _paymentDocuments em memória.

==================================================
5. QUICK SALE PAYMENT — MESMO PROBLEMA

O backend já suporta:

document_type = payment_receipt
source_type = quick_sale_payment

mas _quick_checkout_payload() ainda não devolve print_document por pagamento.

CORRIGIR.

Cada QuickSalePayment deve retornar o PrintDocument existente correspondente.

SOMENTE consultar.

NÃO criar documento em GET/payload.

==================================================
6. QUICK SALE PAYMENT — FLUTTER

O model Flutter de pagamento rápido deve possuir:

PrintDocumentResult? printDocument

A tela deve reconstruir:

_paymentDocuments

a partir do payload retornado pelo backend.

Então:

imprime comprovante
→ atualiza checkout
→ sai
→ volta
→ continua REIMPRIMIR
==================================================
7. GET DA MESA DEVE SER 100% READ-ONLY

Existe um erro arquitetural atual em:

POSTableAttendanceView.get()

Hoje o GET chama:

create_print_document(...)

para:

TABLE_BILL
TABLE_CONFERENCE
TABLE_FINAL_RECEIPT

ISSO DEVE SER REMOVIDO.

Um GET não pode persistir PrintDocument.

Hoje apenas abrir/atualizar a Mesa pode criar versões e poluir histórico.

==================================================
8. LOCALIZAR DOCUMENTO DO SNAPSHOT ATUAL SEM CRIAR

Criar selector/helper read-only apropriado.

Conceito:

calcular snapshot atual;
calcular snapshot_hash;
procurar:
branch
document_type
source_type
source_id
snapshot_hash
retornar o PrintDocument se existir;
retornar None se não existir.

NÃO criar.

==================================================
9. VERSIONAMENTO DE CONTA/CONFERÊNCIA

Exemplo:

Mesa = R$100
Conferência v1 impressa

Depois:

+ produto
Mesa = R$130

GET deve calcular snapshot atual.

Como não existe documento para o novo hash:

→ UI mostra IMPRIMIR

Não pode reimprimir v1 de R$100.

Histórico antigo permanece intacto.

==================================================
10. FAILED NÃO É PENDING

Existe bug em:

PrintDocumentResult.fromJson

Hoje:

queued: json['queued'] == true || jobs.isNotEmpty

Isso está errado.

Um job:

FAILED
physical_dispatch_started_at = null

deve resultar:

queued = false
retryEligible = true
awaitingInitialPrint = false
ação = TENTAR NOVAMENTE

Remover:

|| jobs.isNotEmpty

queued deve significar somente:

PENDING
PROCESSING
==================================================
11. PRIORIDADE DOS ESTADOS

Ajustar getters para ficar:

PRINTED / UNCERTAIN inicial
→ REIMPRIMIR

FAILED antes do dispatch
→ TENTAR NOVAMENTE

PENDING / PROCESSING
→ IMPRESSÃO PENDENTE

nenhum job inicial
→ IMPRIMIR

Não deixar FAILED cair em “impressão pendente”.

==================================================
12. RETRY DE DOCUMENTO

Hoje vários botões fazem só:

canReprint ? reprint : issue

Isso é insuficiente.

Se:

retryEligible = true

deve executar RETRY do job inicial existente.

NÃO criar nova emissão.

NÃO criar reprint.

Criar/usar endpoint de retry por documento se necessário.

==================================================
13. RETRY COM MÚLTIPLAS IMPRESSORAS

Exemplo:

Conta
→ Printer A = PRINTED
→ Printer B = FAILED antes do dispatch

Retry deve reenviar SOMENTE Printer B.

Nunca reenviar:

PRINTED
UNCERTAIN

O mesmo vale para múltiplas cópias.

==================================================
14. IDEMPOTÊNCIA — HARDENING

PrintDocumentRequest já existe.

Hoje possui:

branch
document
action
idempotency_key

Adicionar fingerprint persistente da intenção.

==================================================
15. FINGERPRINT DE ISSUE

Deve considerar pelo menos:

action
branch
document_type
source_type
source_id
pos_device quando necessário

Mesma key + mesma intenção:

→ replay

Mesma key + dados diferentes:

→ conflito de idempotência

NÃO retornar silenciosamente documento de outra operação.

==================================================
16. FINGERPRINT DE REPRINT

Para reprint considerar:

action
branch
document_id
reason quando fizer sentido

Mesma key + mesmo documento:

→ replay

Mesma key + outro documento:

→ conflito.

==================================================
17. REPLAY EXATO DE REPRINT

Hoje reprint_print_document() no replay pode devolver todos os reprints históricos do documento.

Isso não é correto.

Se key X criou:

reprint #3

replay de X deve devolver exatamente a execução criada por X.

Não:

#1
#2
#3

Relacionar PrintDocumentRequest aos jobs criados ou guardar metadata suficiente para localizar exatamente a execução daquela requisição.

==================================================
18. VENDA NÃO PODE FALHAR POR IMPRESSÃO

Preservar:

fechamento da Mesa independente da impressão;
Venda Rápida independente da impressão;
tickets independentes da operação financeira;
transaction.on_commit() onde já foi aplicado.

NÃO reintroduzir impressão dentro da transação financeira principal.

==================================================
19. QUICK SALE RECEIPT

Preservar o comportamento atual.

Se impressão automática falhar:

venda continua válida.

==================================================
20. TABLE FINAL RECEIPT

Preservar o transaction.on_commit() atual.

==================================================
21. TABLE BILL

Preservar o transaction.on_commit() atual ao solicitar conta.

==================================================
22. DOCUMENT TYPE

Preservar lowercase:

table_bill
table_conference
table_final_receipt
quick_sale_receipt
payment_receipt
ticket
==================================================
23. PRINT ROUTES

Preservar:

DISABLED
→ pode não ter impressora

MANUAL / AUTOMATIC
→ exige impressora

neste bloco:
→ somente NETWORK ativo
==================================================
24. TESTE DE IMPRESSORA

Preservar a correção atual:

teste de impressora NETWORK não exige ProductionDestination.

==================================================
25. MARGENS ESC/POS

NÃO mexer desnecessariamente.

Preservar:

58mm:
printable width = 28
left margin = 2

80mm:
printable width = 42
left margin = 3

Preservar:

wrapping;
centralização;
margem;
4 feeds antes do corte.
==================================================
26. AVISO DE KOTLIN DO BUILD

O build também exibiu:

If you don't see a plugins block, your project was likely created with an older template version...

NÃO alterar Kotlin/Gradle só por causa desse aviso.

O erro fatal real do build é:

The getter 'printDocument' isn't defined for the type 'TablePayment'

Só mexer em Kotlin/Gradle se houver erro explícito posterior relacionado a isso.

==================================================
27. NÃO COMEÇAR NOVO BLOCO

NÃO implementar:

Stone printer
USB
Bluetooth
Print Agent
fiscal
delivery
KDS
Comanda
==================================================
CHECKPOINT FINAL

Ao terminar informe:

como corrigiu o erro de build TablePayment.printDocument;
como ficou TablePayment no Flutter;
como ficou TablePaymentSerializer;
como QuickSalePayment passou a retornar print_document;
como o estado persiste após refresh;
como GET da Mesa ficou read-only;
como localiza documento do snapshot atual;
como FAILED passou a virar TENTAR NOVAMENTE;
como funciona retry de documento;
como funciona retry com múltiplos jobs;
como ficou fingerprint de idempotência;
como replay de reprint retorna exatamente sua própria execução;
migrations criadas;
arquivos backend alterados;
arquivos Flutter alterados;
qualquer ponto que ainda dependa de teste físico.

NÃO EXECUTE TESTES.

NÃO EXECUTE ANALYZE.

NÃO EXECUTE BUILD.

DEPOIS PARE.