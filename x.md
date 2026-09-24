Continue a missão no HEAD atual.

Na última revisão, o HEAD era:

`066ef7210a097b9bfc929ee4b3b62e065eda8666`

Antes de alterar, confira o HEAD atual.

Faltam fechar 3 pontos:

1. corrigir inconsistência do hash do PrintDocument;
2. corrigir de verdade o estado “Aguardando impressão”;
3. fechar o fluxo de comprovante de pagamento.

---

# 1. HASH DO SNAPSHOT ESTÁ INCONSISTENTE

Hoje `create_print_document()` adiciona:

```python
snapshot.setdefault('company_name', ...)
snapshot.setdefault('branch_name', ...)

antes de calcular o snapshot_hash.

Mas current_print_document() monta o snapshot com _source_snapshot() e calcula o hash sem adicionar esses campos.

Resultado:

create_print_document hash != current_print_document hash

para o mesmo estado da Mesa.

Isso pode fazer o GET da Mesa não encontrar o PrintDocument atual recém-criado.

CORRIGIR.

Criar uma única forma de montar o snapshot final do documento, incluindo empresa/filial, e reutilizar em:

create_print_document()
current_print_document()
qualquer outro ponto que calcule snapshot_hash para o mesmo documento

Exemplo conceitual:

def _document_snapshot(...):
    source, snapshot = _source_snapshot(...)
    snapshot = dict(snapshot)
    snapshot.setdefault('company_name', ...)
    snapshot.setdefault('branch_name', ...)
    return source, snapshot

Não duplicar a mesma montagem em vários lugares.

IMPORTANTE:
não alterar snapshots históricos já salvos.
A correção vale para a criação/consulta daqui para frente e deve preservar a lógica imutável existente.

2. "AGUARDANDO IMPRESSÃO" NÃO PODE DEPENDER DE UM ÚNICO REFRESH DE 2s

Hoje foi colocado algo equivalente a:

Future.delayed(const Duration(seconds: 2), _load)

e:

Future.delayed(const Duration(seconds: 2), _refresh)

Isso é insuficiente.

O PrintManager roda aproximadamente a cada 3 segundos.

Pode acontecer:

0s cria PrintJob
2s refresh → ainda PENDING
3s PrintManager imprime → PRINTED
UI não consulta de novo

e a tela fica eternamente em:

Aguardando impressão

CORRIGIR com polling curto e limitado.

3. POLLING DE DOCUMENTO

Criar um helper reutilizável e pequeno.

Exemplo conceitual:

após emitir documento
→ esperar 2s
→ consultar estado
→ se terminal, parar
→ se pending/processing, esperar novamente
→ limitar tentativas

Pode usar algo como:

até 4 ou 5 tentativas
intervalo de ~2s

Não precisa seguir exatamente esses valores, mas deve ser curto, limitado e seguro.

Parar imediatamente quando chegar em estado terminal:

PRINTED
FAILED
UNCERTAIN

ou quando o documento não estiver mais:

queued == true

NÃO criar polling infinito.

Cancelar/ignorar atualização se a tela não estiver mais mounted.

4. CONFERÊNCIA

Depois de:

IMPRIMIR CONFERÊNCIA
→ requestPrintDocument()

usar o polling.

Quando o backend confirmar:

PRINTED

a UI deve atualizar automaticamente:

AGUARDANDO IMPRESSÃO
→ REIMPRIMIR

Não exigir fechar e abrir a tela.

5. COMPROVANTE DE PAGAMENTO

Fazer o mesmo para:

PAYMENT_RECEIPT

Depois de:

IMPRIMIR COMPROVANTE

o documento deve atualizar até ficar terminal.

Se PRINTED:

IMPRIMIR COMPROVANTE
→ REIMPRIMIR COMPROVANTE
6. NÃO FAZER POLLING PELO PrintJob DIRETO SE JÁ EXISTE FONTE DE VERDADE DO DOCUMENTO

Preferir atualizar usando APIs existentes:

Conferência:

tableAttendanceDetail()

porque já retorna print_documents.

Pagamento:

tablePaymentLedger()

porque o TablePaymentSerializer já devolve print_document.

Evitar endpoint novo se não for necessário.

7. PAYMENT_RECEIPT — VALIDAR FLUXO COMPLETO

Revisar o caminho inteiro:

TablePaymentPage
→ _printPaymentReceipt()
→ requestPrintDocument()
→ POSPrintDocumentIssueView
→ issue_print_document()
→ effective_print_route(PAYMENT_RECEIPT)
→ PrintJob
→ POSPrintJobsView
→ PrintManager
→ renderer

Confirmar que:

document_type = payment_receipt
source_type = table_payment
source_id = payment.id

está correto.

8. ROTA DO COMPROVANTE

Se a rota efetiva estiver:

DISABLED

não fazer parecer que o botão não funcionou.

A UI deve mostrar claramente o erro retornado pelo backend.

Exemplo:

A rota de comprovante de pagamento está desabilitada.

Se estiver sem impressora:

A rota exige ao menos uma impressora NETWORK ativa.

Não engolir erro.

9. NÃO DUPLICAR COMPROVANTE

Se o PAYMENT_RECEIPT já existir para o mesmo pagamento/snapshot:

primeira impressão
→ mesmo PrintDocument

segunda ação após PRINTED
→ REPRINT

Não criar nova impressão inicial duplicada.

10. HASH E PAYMENT_RECEIPT

A correção do snapshot/hash deve também valer para:

TABLE_CONFERENCE
TABLE_FINAL_RECEIPT
QUICK_SALE_RECEIPT
PAYMENT_RECEIPT
TICKET
TABLE_BILL legado enquanto existir

Ou seja, não corrigir só Conferência.

11. NÃO REGREDIR CORREÇÕES JÁ FEITAS

Preservar:

1.000x → 1x;
formatter de quantidade em Ticket;
Solicitar Conta → TABLE_CONFERENCE;
manual de Conferência → TABLE_CONFERENCE;
bloqueio de produtos após conta solicitada;
bloqueio de long press/lote;
fechamento da Mesa voltando ao grid;
grid recarregando;
cabeçalho empresa/filial;
retry != reprint;
UNCERTAIN;
idempotência;
PrintDocumentRequest;
multiple printers;
multiple copies;
impressão NETWORK local.
12. NÃO MEXER NO TIMER DO PrintManager SÓ PARA MASCARAR A UI

Não reduzir arbitrariamente:

Timer.periodic(Duration(seconds: 3))

para tentar resolver o problema.

O PrintManager pode continuar com sua cadência.

O problema é a UI não acompanhar o estado do backend.

13. RESULTADO ESPERADO — CONFERÊNCIA
IMPRIMIR CONFERÊNCIA
→ POST 201
→ documento queued
→ PrintManager pega
→ imprime
→ backend PRINTED
→ polling detecta
→ botão vira REIMPRIMIR
14. RESULTADO ESPERADO — COMPROVANTE
pagamento ativo
→ IMPRIMIR COMPROVANTE
→ PAYMENT_RECEIPT
→ PrintJob
→ papel sai
→ polling detecta PRINTED
→ REIMPRIMIR COMPROVANTE
15. RESULTADO ESPERADO — HASH

Depois de criar um documento:

create_print_document()
→ snapshot hash X

um GET posterior:

current_print_document()

deve reconstruir exatamente o mesmo snapshot atual e encontrar:

snapshot hash X

Não pode retornar None por diferença de company_name/branch_name.

REGRA CRÍTICA

NÃO EXECUTE TESTES.

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

Eu farei os testes manualmente.

CHECKPOINT

Ao terminar informe:

como unificou a montagem do snapshot;
como garantiu o mesmo hash em create/current;
como ficou o polling limitado;
quantas tentativas/intervalo usou;
como Conferência atualiza após PRINTED;
como PAYMENT_RECEIPT atualiza após PRINTED;
como os erros de rota do comprovante aparecem na UI;
arquivos backend alterados;
arquivos Flutter alterados;
migrations criadas — não deveria precisar;
pontos restantes para teste manual.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.

Depois pare.