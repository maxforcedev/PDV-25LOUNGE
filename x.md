MISSÃO — Correção final de estado de impressão com múltiplas impressoras/cópias

Trabalhe no HEAD mais recente da main.

Na última revisão, o HEAD era:

fee6692cd3d2d8790d7238222a0f9d6460ec8a3c

Antes de alterar, confira o HEAD atual.

NÃO refaça a arquitetura de impressão.

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
NETWORK local
roteamento por finalidade
múltiplas impressoras por finalidade
múltiplas cópias
Product -> ProductionDestination -> PrinterDevice
GET da Mesa read-only
snapshot/versionamento
persistência de comprovantes
fingerprint de idempotência
generated_jobs para replay exato
margens ESC/POS
wrapping
feed/corte
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

EU FAREI O BUILD E OS TESTES MANUALMENTE.

==================================================
PROBLEMA ENCONTRADO

O estado agregado de PrintDocument ainda está incorreto quando existem múltiplos jobs iniciais.

Exemplo:

CONTA DA MESA
├─ Printer A → PRINTED
└─ Printer B → FAILED antes do dispatch

Hoje o documento pode ficar simultaneamente:

reprintEligible = true
retryEligible = true

porque:

existe pelo menos um PRINTED;
existe pelo menos um FAILED.

E no Flutter a prioridade atual é:

if (canReprint) return 'REIMPRIMIR';
if (retryEligible) return 'TENTAR NOVAMENTE';

Resultado:

aparece REIMPRIMIR, quando na verdade a impressão inicial ainda não foi concluída em todos os destinos.

Isso está errado.

==================================================

REGRA CORRETA DE ESTADO AGREGADO
==================================================

Para um PrintDocument, considerar APENAS os jobs iniciais:

reprint_of IS NULL

A prioridade deve ser:

A) FAILED antes do dispatch

Se existir qualquer job inicial:

status = FAILED
physical_dispatch_started_at IS NULL

então:

retryEligible = true
reprintEligible = false
queued = false

ação:

TENTAR NOVAMENTE

==================================================
2. PENDING / PROCESSING

Se não houver FAILED elegível para retry, mas existir qualquer job inicial:

PENDING
ou
PROCESSING

então:

queued = true
reprintEligible = false
retryEligible = false

ação:

IMPRESSÃO PENDENTE

==================================================
3. REPRINT ELIGIBLE

reprintEligible = true SOMENTE quando:

existe pelo menos um job inicial;
TODOS os jobs iniciais estão em estado terminal seguro para reimpressão:
PRINTED
ou
UNCERTAIN

Exemplo:

Printer A → PRINTED
Printer B → UNCERTAIN

então:

REIMPRIMIR

pois não existe mais job inicial pendente ou retry seguro.

==================================================
4. NÃO USAR ANY() PARA REPRINT ELIGIBLE

Hoje existem pontos equivalentes a:

jobs.filter(
    reprint_of__isnull=True,
    status__in=(PRINTED, UNCERTAIN),
).exists()

Isso só verifica se ALGUM job terminou.

Trocar por lógica de conjunto completo.

Exemplo conceitual:

initial_jobs = todos os jobs iniciais

reprintEligible =
initial_jobs existem
E
todos initial_jobs estão em PRINTED ou UNCERTAIN
==================================================
5. CORRIGIR TODOS OS SERIALIZERS/EFFECTS

Aplicar a mesma regra em todos os lugares que calculam estado de documento.

Revisar principalmente:

PrintDocumentSerializer
PrintDocumentResultSerializer
_print_document_effect()
qualquer helper duplicado que calcule:
initial_printed
reprint_eligible
queued
retry_eligible

Não deixar backend retornar estados contraditórios.

==================================================
6. INITIAL_PRINTED

Revisar também initial_printed.

Para documento com múltiplos jobs:

Printer A → PRINTED
Printer B → FAILED

initial_printed NÃO deve significar que a impressão inicial completa foi concluída.

Separar semanticamente:

algum job impresso;
impressão inicial completamente resolvida.

Se initial_printed continuar existindo como booleano público, ele deve representar a conclusão adequada do conjunto inicial, não apenas exists(PRINTED).

Preferência:

initial_printed = todos os initial_jobs == PRINTED

UNCERTAIN não significa impresso confirmado.

==================================================
7. FLUTTER — ORDEM DOS ESTADOS

Mesmo com o backend corrigido, reforçar a prioridade no Flutter:

retryEligible
→ TENTAR NOVAMENTE

awaitingInitialPrint
→ IMPRESSÃO PENDENTE

canReprint
→ REIMPRIMIR

caso contrário
→ IMPRIMIR

Não deixar canReprint ter prioridade sobre retry.

A regra agregada deve vir correta do backend, mas a UI também deve ser defensiva.

==================================================
8. AÇÃO DE RETRY

Quando retryEligible = true:

a ação deve executar retry técnico dos jobs iniciais FAILED elegíveis.

NÃO:

criar nova emissão;
criar reprint;
reenviar jobs já PRINTED;
reenviar UNCERTAIN.

Exemplo:

Printer A → PRINTED
Printer B → FAILED BEFORE SEND

TENTAR NOVAMENTE:

Printer A → permanece PRINTED
Printer B → volta para PENDING
==================================================
9. NÃO USAR retry_print_job() DE FORMA QUE AFETE BATCH ERRADO

Revisar cuidadosamente retry_print_job().

Ele atualmente pode trabalhar por batch_key.

Para PrintDocument com múltiplas impressoras/cópias, garantir que retry de um job FAILED não resete também um job já PRINTED do mesmo documento.

Se jobs de documento não usam batch_key, preservar isso.

Se usarem futuramente, garantir filtro por elegibilidade individual.

==================================================
10. MÚLTIPLAS CÓPIAS

Exemplo:

copies = 2

Printer A copy 1 → PRINTED
Printer A copy 2 → FAILED

Estado:

TENTAR NOVAMENTE

Retry:

somente copy 2.

Depois:

copy 1 → PRINTED
copy 2 → PRINTED

Estado:

REIMPRIMIR

==================================================
11. MÚLTIPLAS IMPRESSORAS

Exemplo:

TABLE_BILL

Printer Caixa → PRINTED
Printer Recepção → PENDING

Estado:

IMPRESSÃO PENDENTE

Não:

REIMPRIMIR

==================================================
12. UNCERTAIN

Exemplo:

Printer A → PRINTED
Printer B → UNCERTAIN

Não existe retry automático seguro.

Estado final pode ser:

REIMPRIMIR

porque qualquer nova cópia precisa ser ação explícita.

Não transformar UNCERTAIN em FAILED.

==================================================
13. DOCUMENTO SEM JOB

Se existe PrintDocument mas não existe job inicial:

IMPRIMIR

Isso é válido principalmente em rota MANUAL antes da primeira impressão.

==================================================
14. DOCUMENTO DISABLED

Se a rota estiver DISABLED:

não gerar novos jobs.

Não quebrar os estados históricos existentes.

==================================================
15. NÃO ALTERAR IDEMPOTÊNCIA

A última rodada implementou:

request_fingerprint
generated_jobs
replay exato

PRESERVAR.

Não reescrever sem necessidade.

==================================================
16. NÃO ALTERAR GET READ-ONLY

Preservar:

current_print_document()

e o GET da Mesa sem criação de PrintDocument.

==================================================
17. NÃO ALTERAR TABLEPAYMENT FIX

Preservar:

TablePayment.printDocument

e:

TablePaymentSerializer.print_document

O erro de build já foi corrigido.

==================================================
18. NÃO ALTERAR QUICK SALE PAYMENT FIX

Preservar:

QuickSaleCheckoutPayment.printDocument

e o payload com:

print_document

==================================================
19. NÃO MEXER EM KOTLIN/GRADLE

O commit anterior chamado fix erro kotlin corrigiu Dart/model.

NÃO mexer em Kotlin/Gradle nesta missão.

==================================================
20. NÃO COMEÇAR NOVO BLOCO

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

como ficou a regra agregada de estado dos jobs iniciais;
quando retryEligible fica true;
quando queued fica true;
quando reprintEligible fica true;
como ficou initial_printed;
como o Flutter prioriza TENTAR NOVAMENTE / PENDENTE / REIMPRIMIR / IMPRIMIR;
como retry funciona com duas impressoras;
como retry funciona com várias cópias;
arquivos backend alterados;
arquivos Flutter alterados;
se restou algum ponto que dependa apenas de teste físico.

NÃO EXECUTE TESTES.

NÃO EXECUTE ANALYZE.

NÃO EXECUTE BUILD.

DEPOIS PARE.