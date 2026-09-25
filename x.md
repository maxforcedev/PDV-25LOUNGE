# MISSÃO — FECHAR PENDÊNCIAS DO CORE POS + CORRIGIR BUILD

Continue no HEAD atual.

Na última revisão, o HEAD era:

`9450854f9c61f6ddcf775ecf9ec96b43c5dd3021`

Antes de alterar, confira o HEAD atual.

Esta missão deve corrigir TODAS as pendências abaixo sem regredir o que já foi implementado.

---

# 1. ERRO FATAL DE COMPILAÇÃO NO `production_ticket_renderer.dart`

O build atual está quebrando com:

```text
lib/printing/production_ticket_renderer.dart:427:9:
Error: The method 'toStringAsFixed' isn't defined for the type '(num)'.

).toStringAsFixed(2);

A causa está no código atual:

String _totalDiscount(Map<String, dynamic> values) => (
      _number(values['promotion_discount_total']) +
      _number(values['item_discount_total']) +
      _number(values['checkout_discount_total'] ?? values['discount']),
    ).toStringAsFixed(2);

O , dentro dos parênteses transforma a expressão em um Record Dart:

(num,)

e não em num.

Por isso:

toStringAsFixed()

não existe nesse tipo.

CORRIGIR.

Preferir algo explícito e legível:

String _totalDiscount(Map<String, dynamic> values) {
  final total =
      _number(values['promotion_discount_total']) +
      _number(values['item_discount_total']) +
      _number(values['checkout_discount_total'] ?? values['discount']);

  return total.toStringAsFixed(2);
}

ou solução equivalente.

Não mascarar com cast de Record.

A soma precisa continuar sendo numérica.

2. AVISO KOTLIN / KGP

Também apareceu orientação do Flutter relacionada ao Kotlin Gradle Plugin.

O projeto atual possui em:

pos/android/settings.gradle
id 'org.jetbrains.kotlin.android' version '2.2.20' apply false

e:

id 'com.android.application' version '8.11.1' apply false

Java/JVM:

17

IMPORTANTE:

O erro fatal mostrado no build atual NÃO é Kotlin.

O build parou no:

Target kernel_snapshot_program failed

por causa do erro Dart de _totalDiscount().

Portanto:

NÃO atualizar/downgrade Kotlin cegamente só porque apareceu a mensagem genérica:

Potential fix: Your project's KGP version...

Revise o aviso completo e a configuração Android existente.

Se houver incompatibilidade REAL e explícita entre Flutter atual / Gradle / AGP / KGP, corrija somente a versão necessária.

Se 2.2.20 já for válida para o ambiente atual, NÃO alterar.

No checkpoint informe se foi necessária alguma alteração Android.

3. STATUS DE IMPRESSÃO CONTINUA STALE

O usuário confirmou no aparelho:

Aguardando impressão

só muda se sair da tela e entrar novamente.

Isso continua acontecendo em alguns fluxos.

Precisamos resolver definitivamente.

4. PRODUÇÃO DA MESA

Hoje existe:

_pollProductionPrintStatus()

com aproximadamente:

5 tentativas
2 segundos
≈ 10 segundos

Depois disso o polling termina.

Se o PrintManager concluir depois:

backend = PRINTED
UI = Aguardando impressão

até sair e voltar.

CORRIGIR.

Enquanto a tela da Mesa estiver visível e existir item com:

pending
processing

iniciar acompanhamento limitado.

Não criar polling infinito.

Pode utilizar uma janela maior e segura, por exemplo:

10 a 15 tentativas
intervalo de 2 segundos

ou solução equivalente.

Parar imediatamente quando nenhum item estiver:

pending
processing

Também iniciar esse acompanhamento quando _load() encontrar produção pendente, não somente imediatamente depois de salvar o pedido.

Evitar múltiplos pollings simultâneos.

Usar guard interno se necessário:

_pollingProduction = true/false
5. CONFERÊNCIA COM IMPRESSÃO PENDENTE NÃO ATUALIZA SOZINHA

Hoje _TableConferencePage._load() consulta uma vez.

Se entrar na tela com:

_document.awaitingInitialPrint == true

a UI fica:

IMPRESSAO PENDENTE

mesmo depois de o backend virar:

PRINTED

Além disso, _print() atualmente faz:

if (_document?.awaitingInitialPrint == true) {
    ...
    return;
}

e retorna sem iniciar polling.

CORRIGIR.

Ao abrir Visualizar conferência:

_load()
→ encontrou documento queued?
→ iniciar pollPrintDocument()

Automaticamente.

Se o operador tocar no ícone enquanto estiver pendente:

não criar outra impressão
não criar reprint

mas pode:

informar "A impressão inicial ainda está pendente."
+
garantir que o polling esteja ativo

Quando backend virar:

PRINTED

o botão deve mudar automaticamente para:

REIMPRIMIR

sem sair da tela.

6. COMPROVANTES TAMBÉM DEVEM ACOMPANHAR ESTADO PENDENTE

Aplicar a mesma regra onde existir PrintDocument visível:

PAYMENT_RECEIPT da Mesa
PAYMENT_RECEIPT da Venda Rápida
TABLE_CONFERENCE

Se a tela carregar um documento:

queued = true

iniciar acompanhamento.

Não depender exclusivamente de o polling ter sido iniciado pela ação de imprimir naquela mesma tela.

7. FAILED BEFORE SEND

A correção recente deve ser preservada.

Hoje o POS manda:

'failed_before_send': true

quando:

não abriu conexão / nenhum byte foi enviado

e o backend limpa:

physical_dispatch_started_at

para permitir:

TENTAR NOVAMENTE

Preservar.

Regra definitiva:

FAILED BEFORE SEND
→ TENTAR NOVAMENTE
→ não é reimpressão
→ sem tarja preta
UNCERTAIN
→ nenhum retry automático
→ somente nova cópia explícita
→ REIMPRESSÃO
→ tarja preta
PRINTED
→ nova cópia somente REIMPRESSÃO
→ tarja preta

Não enfraquecer essa segurança.

8. SOLICITAR CONTA DEVE GERAR A PRIMEIRA CONFERÊNCIA

Hoje ainda existe no backend:

automatic_only=True

em:

set_table_bill_requested()

Isso faz:

TABLE_CONFERENCE = automatic
→ imprime

TABLE_CONFERENCE = manual
→ Solicitar Conta NÃO imprime

Mas a regra definida é:

SOLICITAR CONTA
→ emitir a primeira CONFERÊNCIA DA CONTA

Portanto corrigir.

A ação explícita:

SOLICITAR CONTA

deve ser o gatilho da primeira impressão.

Comportamento esperado:

rota disabled
→ não imprime
→ solicitação da conta continua válida
rota manual
→ Solicitar Conta cria/enfileira primeira impressão
rota automatic
→ Solicitar Conta cria/enfileira primeira impressão

Pode usar:

automatic_only=False

ou solução arquitetural equivalente.

Não imprimir diretamente pela UI.

Continuar usando:

PrintDocument
PrintRoute
PrintRouteOverride
PrintJob
PrintManager
9. UMA ÚNICA PRIMEIRA IMPRESSÃO

Preservar fortemente:

mesmo PrintDocument
mesmo snapshot
→ apenas uma impressão inicial

Se já existe initial PrintJob:

não criar outra primeira impressão

Nova cópia:

REPRINT

Se a inicial falhou antes de enviar:

RETRY

Não confundir RETRY com REPRINT.

10. CONFERÊNCIA MANUAL SOMENTE NA TELA "VISUALIZAR CONFERÊNCIA"

Preservar a mudança recente.

Não voltar com:

IMPRIMIR CONFERÊNCIA
REIMPRIMIR CONFERÊNCIA

no menu da Mesa.

O único ponto manual deve ser:

Mesa
→ Visualizar conferência
→ ícone de impressora
11. TARJA PRETA EM TODA REIMPRESSÃO

Preservar o _reprintBanner() atual com modo reverso ESC/POS:

fundo preto
texto branco
REIMPRESSAO #N

A regra é global.

Aplicar a:

TABLE_CONFERENCE
TABLE_FINAL_RECEIPT
PAYMENT_RECEIPT
QUICK_SALE_RECEIPT
TICKET
produção quando reimpressa
demais PrintDocuments

Primeira impressão:

sem tarja

Retry de FAILED BEFORE SEND:

sem tarja
12. DATAS DOS CUPONS

A correção recente deve ser preservada e revisada para todos os documentos.

Nunca imprimir:

2026-09-24T23:18:37.482193+00:00

ou:

2026-09-24 20:18

Formato desejado:

24/09/2026 20:18

Usar helper central.

Aplicar a:

Data/hora
Aberta em
Fechada em
Impresso em
issued_at
created_at
paid_at

onde aparecerem em documentos térmicos.

13. DESCONTOS — UMA ÚNICA LINHA

A correção recente consolidou:

promotion_discount_total
item_discount_total
checkout_discount_total

em:

discount_total

Preservar.

No cupom:

SUBTOTAL
DESCONTOS
TAXA DE SERVICO
TOTAL

Não imprimir:

Promoções
Desconto por item
Desconto da mesa

separadamente.

Se desconto for zero:

não imprimir linha de desconto
14. BUG NO DEDUPE DO RENDERER

Existe atualmente:

if (!rows.any((row) => row.value == entry.value))

Mas:

row.value = valor monetário
entry.value = label

Exemplo:

row.value = "10.00"
entry.value = "Taxa de servico"

Essa comparação está errada.

Pode gerar duplicatas como:

Taxa de servico
Taxa de servico

ou:

TOTAL
TOTAL

quando o snapshot possuir mais de um campo equivalente:

service_fee_total
service_fee_amount
service_fee

total_due
total

CORRIGIR.

Deduplicar pelo label lógico.

Exemplo conceitual:

!rows.any((row) => row.key == entry.value)

ou solução melhor.

Definir prioridade coerente para campos equivalentes.

Resultado esperado:

Subtotal
Descontos
Taxa de servico
TOTAL
TOTAL PAGO
SALDO A PAGAR

cada label no máximo uma vez.

15. VENDA RÁPIDA — NÃO RECUPERAR VENDA ANTIGA NA UI

Preservar a remoção recente de:

_resumeCheckout()
_restoreCheckoutDraft()
"Venda em andamento recuperada."

Ao abrir Venda Rápida:

carrinho vazio
cliente vazio
desconto vazio
nova operação

Não restaurar venda antiga visualmente.

16. CHECKOUT ABANDONADO DA VENDA RÁPIDA AINDA ESTÁ FRÁGIL

Hoje SharedPaymentPage faz:

if (didPop) {
    unawaited(_cancelAbandonedCheckout());
}

Isso significa:

tela já saiu
→ depois tenta cancelar checkout

Se internet falhar:

checkout continua OPEN
estado local continua podendo apontar para ele

Isso precisa ser corrigido.

17. SAIR DE CHECKOUT SEM PAGAMENTO

Se NÃO existe pagamento aplicado:

operador tenta voltar
→ cancelar checkout
→ AGUARDAR confirmação do backend
→ somente depois sair da tela

Não usar:

unawaited(...)

para uma operação que determina se o checkout foi realmente abandonado.

Se cancelamento falhar:

permanecer na tela
mostrar erro

Não fingir que checkout foi descartado.

18. CHECKOUT COM PAGAMENTO

Se existe pagamento aplicado:

não permitir sair abandonando

Já existe regra semelhante.

Preservar:

Conclua ou estorne os pagamentos para sair desta venda.

Nunca:

limpar checkout silenciosamente
cancelar com dinheiro aplicado
usar checkout antigo como uma nova venda
19. RECUPERAÇÃO INTERNA DE SEGURANÇA PODE CONTINUAR

Não remover mecanismos internos necessários para:

idempotência
falha de rede
resultado incerto
reconciliação de pagamento
reconciliação de finalização

recoverQuickSaleCheckout() pode continuar existindo internamente se for necessário para essas garantias.

Mas NÃO pode voltar a ser experiência de:

abrir Venda Rápida
→ venda velha reaparece
20. NOVA VENDA NÃO PODE HERDAR CHECKOUT ANTIGO

Hoje createQuickSaleCheckout() ainda pode encontrar:

state['checkout_id']

e chamar internamente:

recoverQuickSaleCheckout()

Revisar esse comportamento.

Cenário:

checkout antigo OPEN
sem pagamento
sem operação incerta

Ao iniciar uma NOVA Venda Rápida:

não restaurar
não reutilizar silenciosamente

Deve cancelar/encerrar o checkout antigo de maneira segura e criar um novo.

Cenário:

checkout antigo
com pagamento
ou operação financeira incerta

Não reutilizar como venda nova.

O sistema deve impedir a nova operação e orientar resolução financeira, sem expor a antiga como um carrinho recuperado normal.

21. FECHAR MESA → GRID

Preservar a correção atual.

Fluxo correto:

TablePaymentPage
→ CLOSED
→ pop(closed)

TableOrderPage
→ recebe CLOSED
→ pop(closed)

TablesPage
→ recebe CLOSED
→ recarrega grid
→ mostra "Mesa fechada com sucesso."

Não voltar a mostrar mensagem na tela que será fechada.

Não reintroduzir modal de recibo final.

22. MESA VAZIA NÃO SOLICITA CONTA

Preservar backend e frontend.

Backend deve continuar exigindo pelo menos um:

TableOrderItem CONFIRMED

Mensagem:

Adicione e envie pelo menos um produto antes de solicitar a conta.

Itens cancelados não contam.

Produto apenas no carrinho local também não conta.

23. TICKET

Preservar as correções já feitas:

Mesa → pos_device
Comanda → pos_device
Venda Rápida → pos_device

A rota:

TICKET

continua respeitando:

PrintRoute
PrintRouteOverride
inherit_branch
POS de origem

Produto:

emits_ticket = true

deve gerar Ticket uma única vez.

Não duplicar impressão inicial.

24. RECIBO FINAL DA MESA

Preservar:

TABLE_FINAL_RECEIPT

ao fechar Mesa.

Fechamento da Mesa NÃO depende do sucesso da impressão.

Fluxo:

Mesa CLOSED
→ volta ao grid imediatamente
→ PrintManager processa recibo
25. CUPOM DE CONFERÊNCIA

Preservar o novo layout:

CONFERENCIA DA CONTA
RELATORIO GERENCIAL
*** NAO E DOCUMENTO FISCAL ***

no mesmo estilo do recibo final.

Mesa ainda aberta.

Não incluir Fechada em.

26. ARQUIVOS A REVISAR

No mínimo:

pos/lib/printing/production_ticket_renderer.dart
pos/lib/printing/print_document_polling.dart
pos/lib/printing/print_manager.dart

pos/lib/attendance/table_attendance_page.dart
pos/lib/attendance/attendance_pages.dart

pos/lib/payments/table_payment_page.dart
pos/lib/payments/shared_payment_page.dart

pos/lib/sales/quick_sale_page.dart
pos/lib/core/app_controller.dart

backend/apps/attendance/services.py
backend/apps/production/services.py
backend/apps/production/serializers.py

pos/android/settings.gradle
pos/android/build.gradle
pos/android/app/build.gradle

Alterar somente o necessário.

27. NÃO REGREDIR

Preservar obrigatoriamente:

retry != reprint
UNCERTAIN
physical_dispatch_started_at
claim/lease
idempotência
PrintDocumentRequest
hash + fallback legado
PrintRoute / PrintRouteOverride
NETWORK local
quantidade 1.000x → 1x
tarja preta de reimpressão
Tickets
Mesa vazia bloqueada
fechamento voltando ao grid
28. RESULTADOS ESPERADOS
Build

O código não pode mais conter a construção Dart inválida:

(num,).toStringAsFixed(...)
Impressão pendente
PENDING
→ tela acompanha backend
→ PRINTED
→ UI muda automaticamente

sem sair e voltar.

Falha antes do envio
Socket nem conectou
→ FAILED BEFORE SEND
→ botão TENTAR NOVAMENTE
Conferência
Solicitar Conta
→ primeira Conferência
→ impressão inicial única

Depois:

nova cópia
→ REIMPRESSÃO
→ tarja preta
Venda Rápida
abrir módulo
→ nova venda limpa

Se abandonar checkout sem pagamento:

cancelar no backend
→ confirmar cancelamento
→ só então sair
Fechar Mesa
Fechar Mesa
→ CLOSED
→ grid
→ reload
→ "Mesa fechada com sucesso."
Cupom
24/09/2026 20:18

Uma única linha:

Descontos

Sem:

Taxa de serviço
Taxa de serviço

ou:

TOTAL
TOTAL

duplicados.

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

Não execute build para validar o erro.
Corrija estaticamente o código e informe no checkpoint.

CHECKPOINT

Ao terminar informe:

como corrigiu o erro (num) / toStringAsFixed;
se alterou ou não KGP e por quê;
versão final de Kotlin/AGP se houve alteração;
como ficou o polling de produção;
como Conferência pendente passa a atualizar sozinha;
como comprovantes pendentes passam a atualizar;
como preservou FAILED BEFORE SEND;
se Solicitar Conta agora dispara a primeira Conferência em rota manual/automatic;
como garantiu uma única impressão inicial;
como corrigiu o dedupe de Taxa/TOTAL;
como ficaram os descontos;
como ficaram as datas;
como ficou a saída da Venda Rápida sem pagamento;
como evita checkout antigo sendo usado por uma nova venda;
como preservou operações financeiras incertas;
se Fechar Mesa continua retornando ao grid;
se Mesa vazia continua bloqueada;
se Tickets continuam respeitando o POS/override;
arquivos backend alterados;
arquivos Flutter alterados;
arquivos Android alterados;
migrations criadas — não deveria precisar;
pontos restantes para teste manual.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.
NÃO EXECUTE FLUTTER RUN.

Depois pare.