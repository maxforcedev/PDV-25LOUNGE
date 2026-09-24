Continue a missão no HEAD atual.

Na última revisão, o HEAD era:

`9bc61d04653940b4b860d97618ca62073d1770c2`

Antes de alterar, confira o HEAD atual.

Ainda restam estes problemas reais:

---

# 1. RESUMO DA MESA CONTINUA COM "AGUARDANDO IMPRESSÃO" DEPOIS QUE A PRODUÇÃO JÁ IMPRIMIU

O polling criado para `PrintDocument` resolveu Conferência/Comprovante, mas o resumo da Mesa usa outro fluxo:

```text
TableOrderItem.printStatus
→ ProductionJob
→ PrintJob

Hoje acontece:

pedido enviado
→ _load()
→ PrintJob ainda PENDING
→ item.printStatus = pending
→ UI mostra "Aguardando impressão"

alguns segundos depois:
→ PrintManager imprime
→ backend passa PrintJob para PRINTED
→ UI da Mesa não atualiza novamente

Resultado:

papel saiu
mas o resumo continua "Aguardando impressão"

CORRIGIR.

Depois de enviar um pedido, se houver item com:

printStatus == pending
ou
printStatus == processing

fazer refresh curto e limitado do tableAttendanceDetail() até os itens chegarem a estado terminal.

Não usar pollPrintDocument() diretamente porque produção não é PrintDocument.

Criar helper pequeno/reutilizável se fizer sentido.

Exemplo:

pedido salvo
→ carregar Mesa
→ encontrou produção pending/processing?
→ esperar 2s
→ tableAttendanceDetail()
→ atualizar UI
→ repetir limitado
→ parar quando nenhum item estiver pending/processing

Limitar tentativas.

Não criar polling infinito.

Não reenviar produção.

Não criar novo ProductionJob.

Não mexer em estoque.

2. ERROS DO COMPROVANTE DE PAGAMENTO NÃO ESTÃO APARECENDO CORRETAMENTE

Hoje _printPaymentReceipt() faz algo parecido com:

if (result == null) {
    final error = widget.controller.errorMessage;
    ...
}

Isso não resolve os erros normais de API.

No AppController, _handleApiError() para 400/409 normalmente chama:

_showTransientMessage(message, notify: false);

e não salva em errorMessage.

Então cenários como:

A rota deste documento está desabilitada.

ou:

A rota exige ao menos uma impressora NETWORK ativa.

podem continuar parecendo que o botão não fez nada.

CORRIGIR o tratamento de erro.

Não usar errorMessage para erro operacional comum.

O erro retornado pelo backend deve aparecer imediatamente no padrão de alerta do CORE POS.

Exemplo esperado:

PAYMENT_RECEIPT disabled
→ clicar IMPRIMIR COMPROVANTE
→ alerta:
"A rota deste documento está desabilitada."

ou mensagem operacional equivalente.

Não duplicar Snackbar + alerta global para o mesmo erro.

Escolher um padrão consistente.

3. REVISAR _attendance() / _handleApiError()

Hoje _attendance() captura:

PosApiException
PosNetworkException

Revisar para garantir que erro operacional:

400
404
409

seja exibido imediatamente.

Não transformar esses erros em erro persistente de tela.

Não usar errorMessage global como mecanismo de Snackbar.

Preservar comportamento especial para:

device unavailable
update required
500+

conforme arquitetura atual.

4. CONFERÊNCIA AINDA USA DADOS STALE NO RESUMO

Na _TableConferencePage, já existe:

late TableAttendance _attendance

e _load() atualiza esse objeto via:

tableAttendanceDetail()

Mas a parte de baixo ainda usa:

TableSummaryWidgets(widget.attendance.summary)

e também:

widget.attendance.customerName

Isso está errado.

Trocar para o estado atualizado:

TableSummaryWidgets(_attendance.summary)

e cliente também deve vir de:

_attendance.customerName

A Conferência inteira deve usar _attendance.

Não misturar:

itens novos
com
resumo antigo
5. CONFERÊNCIA DEVE REFLETIR O ESTADO ATUAL COMPLETO

Depois de _load():

usar _attendance para:

mesa;
horário;
atendente;
itens;
modificadores;
observações;
summary;
cliente;
print_documents.

Não usar widget.attendance para dados que podem mudar.

6. PRESERVAR POLLING DE PrintDocument

NÃO remover o helper atual:

pos/lib/printing/print_document_polling.dart

Preservar:

5 tentativas
2 segundos
parar quando !document.queued

ou equivalente atual.

Ele continua sendo usado para:

TABLE_CONFERENCE;
PAYMENT_RECEIPT.

O novo polling de produção é separado.

7. PRODUÇÃO E DOCUMENTOS SÃO FLUXOS DIFERENTES

Não misturar:

ProductionJob / PrintJob

com:

PrintDocument / PrintJob

O mesmo PrintJob executor pode existir, mas a origem operacional é diferente.

Resumo da Mesa:

TableOrderItem
→ ProductionJob
→ PrintJob

Conferência/Comprovante:

PrintDocument
→ PrintJob

Manter essa separação.

8. NÃO REGREDIR HASH DO SNAPSHOT

Preservar:

_document_snapshot(...)
_document_snapshot_hash(...)

e o uso unificado em:

create_print_document()
current_print_document()
issue_print_document()

Não voltar a duplicar montagem de snapshot.

9. COMPATIBILIDADE COM DOCUMENTOS ANTIGOS

Revisar se documentos criados ANTES da inclusão de:

company_name
branch_name

ficam invisíveis para current_print_document() por causa do hash antigo.

Se isso puder acontecer no ambiente atual, implementar fallback seguro de leitura para o snapshot/hash legado.

IMPORTANTE:

não alterar snapshot histórico;
não recalcular e salvar hash antigo;
não modificar documento imutável;
apenas localizar documento legado quando o estado operacional for equivalente.

Se concluir que não é necessário por ainda estarmos em desenvolvimento e não houver dados relevantes, apenas informar no checkpoint.

10. COMPROVANTE DE PAGAMENTO — PRESERVAR FLUXO

Continuar usando:

document_type = PAYMENT_RECEIPT
source_type = table_payment
source_id = payment.id

Não criar novo tipo.

Não usar Sale para comprovante de pagamento da Mesa.

Não recriar pagamento.

11. STATUS DO COMPROVANTE

Depois de impressão:

IMPRIMIR COMPROVANTE
→ queued
→ PrintManager
→ PRINTED
→ polling
→ REIMPRIMIR COMPROVANTE

Preservar o polling já criado.

12. STATUS DA PRODUÇÃO NO RESUMO

Esperado:

PENDING
→ Aguardando impressão

PROCESSING
→ Impressão em andamento

PRINTED
→ Impresso

FAILED
→ Falha na impressão

Se existir UNCERTAIN no serializer de produção e ele ainda cair como pending, revisar.

Não mascarar UNCERTAIN como "Aguardando impressão".

Se aplicável, mostrar algo como:

Impressão com resultado incerto

sem retry automático.

13. NÃO ALTERAR O TIMER DO PrintManager

Não reduzir o timer de:

Timer.periodic(const Duration(seconds: 3), ...)

só para esconder o problema.

O problema é a UI não fazer refresh.

14. NÃO REGREDIR O QUE JÁ ESTÁ CORRETO

Preservar:

1.000x → 1x;
quantidade formatada em Ticket;
Solicitar Conta → TABLE_CONFERENCE;
impressão manual → TABLE_CONFERENCE;
bloqueio de novos produtos após Solicitar Conta;
bloqueio de long press/lote;
backend protegendo table_bill_requested;
Mesa fechando e voltando ao grid;
grid atualizando;
empresa/filial no documento;
polling de Conferência;
polling de PAYMENT_RECEIPT;
retry != reprint;
UNCERTAIN;
idempotência;
claim/lease;
physical_dispatch_started_at;
impressão NETWORK local.
RESULTADO ESPERADO 1 — PRODUÇÃO
Adicionar produto
→ enviar pedido
→ status "Aguardando impressão"

PrintManager imprime
→ backend PRINTED
→ refresh limitado detecta
→ resumo muda para "Impresso"

sem fechar/reabrir a Mesa.

RESULTADO ESPERADO 2 — COMPROVANTE COM ROTA DESABILITADA
PAYMENT_RECEIPT = disabled
→ clicar IMPRIMIR COMPROVANTE
→ erro aparece imediatamente

Não botão morto.

RESULTADO ESPERADO 3 — CONFERÊNCIA
abrir Conferência
→ tableAttendanceDetail()
→ itens atuais
→ summary atual
→ cliente atual

Tudo vindo do mesmo _attendance.

RESULTADO ESPERADO 4 — COMPROVANTE IMPRESSO
IMPRIMIR COMPROVANTE
→ papel sai
→ polling detecta PRINTED
→ botão vira REIMPRIMIR COMPROVANTE
ARQUIVOS A REVISAR

No mínimo:

pos/lib/attendance/table_attendance_page.dart
pos/lib/attendance/attendance_presentation.dart
pos/lib/payments/table_payment_page.dart
pos/lib/core/app_controller.dart
pos/lib/printing/print_document_polling.dart
backend/apps/attendance/serializers.py
backend/apps/production/services.py

Alterar apenas o necessário.

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

como atualizou o status da produção no resumo da Mesa;
quantas tentativas/intervalo usou nesse refresh;
se tratou UNCERTAIN separadamente;
como corrigiu exibição de erros do PAYMENT_RECEIPT;
se removeu dependência incorreta de errorMessage;
se a Conferência agora usa _attendance.summary;
se a Conferência agora usa _attendance.customerName;
se implementou fallback de hash legado ou por que não;
arquivos backend alterados;
arquivos Flutter alterados;
migrations criadas — não deveria precisar;
pontos restantes para teste manual.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.

Depois pare.