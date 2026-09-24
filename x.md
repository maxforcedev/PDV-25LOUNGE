MISSÃO — Correção final do estado queued + hardening de concorrência na impressão

Trabalhe no HEAD mais recente da main.

Na última revisão, o HEAD era:

5f920aa7443776c35e94312a5ad4891586dd33d4

Antes de alterar, confira o HEAD atual.

NÃO refaça a arquitetura.

Preservar tudo que já está correto:

PrintDocument
PrintRoute
PrintRouteOverride
PrintDocumentRequest
PrintJob
ProductionJob
PrintManager
claim / lease / dispatch / reconcile
UNCERTAIN
retry != reprint
NETWORK local
múltiplas impressoras
múltiplas cópias
GET da Mesa read-only
snapshot/versionamento
request_fingerprint
generated_jobs
persistência dos comprovantes
margens ESC/POS
wrapping
feed/corte
==================================================
REGRA CRÍTICA

NÃO EXECUTE TESTES.

NÃO execute:

flutter analyze
flutter test
build
pytest
npm test
npm build
npm lint
suites
makemigrations --check

Eu farei a validação manual.

==================================================

CORRIGIR _print_document_effect()
==================================================

Existe uma inconsistência atual em:

backend/apps/pos/views.py

Hoje a função faz algo equivalente a:

state = print_document_state(document)

return {
    ...
    **state,
    ...
    'queued': jobs.filter(
        status__in=(PENDING, PROCESSING)
    ).exists(),
}

Isso está errado porque sobrescreve o queued já calculado corretamente por:

print_document_state(document)

Exemplo:

Printer A → FAILED antes do dispatch
Printer B → PENDING

print_document_state() corretamente retorna:

retry_eligible = true
queued = false

Mas _print_document_effect() sobrescreve e termina devolvendo:

retry_eligible = true
queued = true

Isso cria estado contraditório na API.

CORRIGIR.

_print_document_effect() deve usar print_document_state() como ÚNICA fonte da verdade para:

initial_printed
retry_eligible
queued
reprint_eligible

Remover qualquer recálculo duplicado desses campos.

Exemplo conceitual:

state = print_document_state(document)

return {
    'id': document.pk,
    'document_type': document.document_type,
    **state,
    'reprint_number': ...,
    'print_jobs': ...,
}
==================================================
2. EVITAR DUPLICAÇÃO DA REGRA DE ESTADO

Revisar o backend e garantir que não existam outras funções calculando esses estados de forma diferente.

Toda lógica agregada deve passar por:

print_document_state(document)

Não duplicar regras com .exists() ou .filter() espalhadas.

==================================================
3. PRESERVAR REGRAS ATUAIS

A regra correta deve continuar:

qualquer FAILED antes do dispatch
→ retry_eligible = true
→ queued = false
→ reprint_eligible = false

senão qualquer PENDING/PROCESSING
→ queued = true
→ retry_eligible = false
→ reprint_eligible = false

senão todos PRINTED/UNCERTAIN
→ reprint_eligible = true

todos PRINTED
→ initial_printed = true
==================================================
4. FLUTTER

Preservar a prioridade atual:

retryEligible
→ TENTAR NOVAMENTE

awaitingInitialPrint
→ IMPRESSÃO PENDENTE

canReprint
→ REIMPRIMIR

senão
→ IMPRIMIR

Não precisa alterar Flutter se não houver inconsistência nova.

==================================================
5. HARDENING DE CONCORRÊNCIA

Revisar a criação de PrintJob de documento para garantir proteção contra duas requisições simultâneas tentando gerar a mesma execução física.

Hoje PrintJob possui constraint de idempotência voltada para production_job, mas não uma constraint específica equivalente para:

print_document
+ printer_device
+ idempotency_key

Avaliar adicionar constraint apropriada para PrintJob de documento.

Objetivo:

duas requisições simultâneas para a mesma intenção NÃO podem gerar dois jobs físicos equivalentes.

==================================================
6. NÃO QUEBRAR MÚLTIPLAS CÓPIAS

A constraint NÃO pode impedir:

Printer A
copy 1
copy 2

porque são cópias legítimas.

Hoje a chave já é determinística por:

document
printer
copy_number

Portanto use a idempotency_key como parte da proteção.

==================================================
7. CONCORRÊNCIA DE PrintDocumentRequest

PrintDocumentRequest já possui:

branch
action
idempotency_key

com UniqueConstraint.

Preservar.

Se duas requisições simultâneas usarem a mesma chave:

uma pode ganhar a corrida;

a outra deve tratar o conflito como replay/idempotência, não como erro 500.

Revisar issue_print_document() e reprint_print_document() para tratar IntegrityError de concorrência de forma segura, se necessário.

==================================================
8. CONCORRÊNCIA DE PrintDocument

PrintDocument já possui UniqueConstraint em:

branch
document_type
source_type
source_id
snapshot_hash

Preservar.

Se duas requisições tentarem criar o mesmo snapshot simultaneamente:

não deixar isso virar erro 500.

Uma deve criar.

A outra deve recuperar o registro já criado.

Fazer isso sem duplicar versionamento.

==================================================
9. NÃO ALTERAR COMPORTAMENTO DE NEGÓCIO

NÃO mexer em:

quando Mesa imprime produção;
quando Venda Rápida imprime produção;
cancelamento;
Conta;
Conferência;
Recibo;
Comprovante;
Ticket;
roteamento;
destinos;
permissões;
Stone/USB/Bluetooth.
==================================================
10. NÃO COMEÇAR NOVO BLOCO

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
CHECKPOINT

Ao terminar informe:

como corrigiu o overwrite de queued;
se print_document_state() ficou como única fonte da verdade;
se adicionou constraint para PrintJob de documento;
como protegeu múltiplas cópias;
como tratou corrida na criação de PrintDocument;
como tratou corrida em PrintDocumentRequest;
migrations criadas;
arquivos alterados;
se restou algum ponto que dependa somente de teste físico.

NÃO EXECUTE TESTES.

NÃO EXECUTE ANALYZE.

NÃO EXECUTE BUILD.

Depois pare.