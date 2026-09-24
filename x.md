Continue a missão no HEAD atual.

Na última revisão, o HEAD era:

`1c0e419eba67c73adc0fd81374078e55d7232334`

Antes de alterar, confira o HEAD atual.

Além das correções pendentes de impressão já identificadas, adicionar estas regras funcionais.

---

# 1. REMOVER "RECUPERAR VENDA" DA VENDA RÁPIDA

Hoje `QuickSalePage` faz recuperação automática.

Existe em `_loadInitial()`:

```dart
await _resumeCheckout();

e _resumeCheckout() chama:

widget.controller.recoverQuickSaleCheckout()

depois restaura o carrinho e mostra:

Venda em andamento recuperada.

Também, ao voltar da tela de pagamento sem resultado, _openPayment() chama novamente:

recoverQuickSaleCheckout()

e restaura a venda antiga.

Não quero mais esse comportamento funcional.

2. COMPORTAMENTO DESEJADO DA VENDA RÁPIDA

Ao entrar em:

Venda Rápida

deve começar limpa.

Não deve aparecer:

Venda em andamento recuperada.

Não deve restaurar automaticamente:

produtos;
cliente;
desconto;
taxa;
carrinho;
checkout antigo.

Venda Rápida deve ser uma operação direta:

abre Venda Rápida
→ carrinho vazio
→ faz venda
→ conclui
→ tela limpa
3. IMPORTANTE: NÃO REMOVER SEGURANÇA DE IDEMPOTÊNCIA

Não confundir:

recuperar uma venda antiga para o operador

com:

reconciliar uma requisição incerta por falha de rede

A segunda precisa continuar existindo.

Preservar:

idempotência de criação;
idempotência de pagamento;
idempotência de finalização;
proteção contra venda duplicada;
proteção contra pagamento duplicado;
reconciliação de uma requisição cujo resultado ficou incerto.

O que deve sair é a EXPERIÊNCIA de:

fechei / saí da Venda Rápida
→ entro depois
→ sistema traz a venda antiga de volta

Não destruir as proteções internas necessárias para descobrir se uma operação enviada ao backend foi ou não concluída.

4. CHECKOUT ABANDONADO

Revisar corretamente o ciclo do QuickSaleCheckout.

Hoje existe:

OPEN
PAID
FINALIZED
CANCELLED

e existe endpoint:

sales/checkouts/{id}/cancel/

Não deixar checkouts OPEN abandonados indefinidamente só porque removemos a recuperação visual.

Quando o operador abandonar conscientemente uma Venda Rápida/checkout:

sem pagamento aplicado
→ cancelar o checkout de forma segura
→ limpar estado local

Se já existir pagamento aplicado:

NÃO cancelar silenciosamente
NÃO perder pagamento
NÃO simplesmente limpar estado

Nesse caso, preservar as proteções financeiras existentes e exigir o fluxo correto de estorno/finalização conforme a arquitetura atual.

Não inventar exclusão física.

5. REMOVER CÓDIGO DE UX DE RECUPERAÇÃO QUE FICAR SEM USO

Revisar principalmente:

pos/lib/sales/quick_sale_page.dart
pos/lib/core/app_controller.dart

Remover da UI o que ficar exclusivamente ligado à recuperação funcional, por exemplo:

_resumeCheckout()
_restoreCheckoutDraft()
Venda em andamento recuperada.

somente se realmente não houver outro uso necessário.

Não remover funções internas de recuperação de resultado incerto se elas forem necessárias para idempotência/segurança.

6. SOLICITAR CONTA SEM PRODUTO É PROIBIDO

Hoje o backend permite chegar em:

set_table_bill_requested(...)

sem verificar se a Mesa possui produto confirmado.

Isso precisa ser proibido.

Uma Mesa sem nenhum:

TableOrderItem status = CONFIRMED

não pode solicitar conta.

Também considerar Mesa que só possui itens:

CANCELLED

como Mesa sem produtos para essa finalidade.

7. VALIDAÇÃO DEVE EXISTIR NO BACKEND

Em:

set_table_bill_requested(...)

quando:

requested = true

validar antes de efetivar a solicitação.

Deve existir pelo menos um:

TableOrderItem
order__attendance = attendance
status = CONFIRMED

Se não existir:

HTTP 409
code = table_empty

ou código equivalente consistente.

Mensagem:

Adicione e envie pelo menos um produto antes de solicitar a conta.

Não criar:

bill_requested_at;
bill_requested_by;
PrintDocument;
PrintJob;
Conferência.
8. VALIDAR ANTES DE ALTERAR O ESTADO

Organizar set_table_bill_requested() para as validações ocorrerem antes de efetivar:

bill_requested_at
bill_requested_by

Mesmo que a transação hoje faça rollback em exceção, deixar a ordem lógica correta e explícita.

Fluxo:

requested=true
→ Mesa aberta?
→ possui item confirmado?
→ não possui pendência incompatível?
→ então solicitar conta
→ emitir Conferência
9. BLOQUEIO TAMBÉM NO POS

Na _toggleBill():

antes de chamar o backend, verificar se a Mesa possui ao menos um item confirmado.

Se não tiver:

Adicione e envie pelo menos um produto antes de solicitar a conta.

Não chamar a API desnecessariamente.

Mas o backend continua sendo a autoridade.

10. CARRINHO LOCAL NÃO CONTA COMO PRODUTO DA MESA

Se existir produto apenas no carrinho ainda não enviado:

NOVOS ITENS

continua proibido solicitar conta.

A regra já existente deve permanecer:

Envie os itens novos antes de solicitar a conta.

Fluxo correto:

produto no carrinho
→ Solicitar Conta
→ bloquear

SALVAR E ENVIAR PEDIDO
→ item vira CONFIRMED

Solicitar Conta
→ permitido
11. FECHAR MESA DEVE VOLTAR AO GRID DE MESAS

Regra definitiva:

Pagamento
→ FECHAR MESA
→ backend retorna CLOSED
→ sair da tela de pagamento
→ sair do detalhe da Mesa
→ voltar ao GRID DE MESAS
→ atualizar grid
→ mostrar sucesso

Não permanecer:

na tela de pagamento;
na Mesa fechada;
em modal de recibo;
em qualquer tela intermediária.
12. MENSAGEM DE SUCESSO DEVE APARECER NO GRID

Hoje TablePaymentPage._close() mostra:

Mesa fechada com sucesso.

e logo depois faz:

Navigator.of(context).pop(closed);

Isso não é o melhor local, porque o SnackBar pertence à rota que está sendo fechada.

Mover a responsabilidade visual para o grid.

Fluxo recomendado:

TablePaymentPage
→ retorna TableAttendance CLOSED

TableOrderPage
→ recebe CLOSED
→ retorna CLOSED

TablesPage
→ recebe CLOSED
→ _load()
→ mostra:
   "Mesa fechada com sucesso."

Assim a mensagem aparece no lugar correto:

GRID DE MESAS
13. TABLES PAGE DEVE CAPTURAR O RESULTADO

Hoje _TablesPageState._open() faz:

await Navigator.of(context).push(...)
if (mounted) await _load();

mas ignora o resultado.

Alterar conceitualmente para:

final result = await Navigator.push<TableAttendance>(...)
→ reload grid
→ se result.status == closed
   mostrar sucesso

Não precisa seguir exatamente essa implementação se existir solução melhor, mas o dono da mensagem final deve ser o grid.

14. NÃO DUPLICAR SNACKBAR

Depois dessa mudança, remover mensagem duplicada do TablePaymentPage.

Deve aparecer uma única vez:

Mesa fechada com sucesso.

já no grid.

15. IMPRESSÃO FINAL NÃO PODE SEGURAR NAVEGAÇÃO

Preservar:

fechar Mesa
→ TABLE_FINAL_RECEIPT

Mas impressão é efeito secundário.

Nunca fazer:

fechou Mesa
→ esperar impressora
→ só depois voltar ao grid

Correto:

backend confirmou CLOSED
→ volta imediatamente ao grid
→ PrintManager cuida do recibo

Se impressão falhar:

Mesa continua fechada.
16. REMOVER CÓDIGO MORTO DE MODAL FINAL SE NÃO TIVER USO

Ainda existe em TablePaymentPage:

_showFinalReceiptAction(...)

mesmo que o fluxo atual de _close() já não esteja chamando esse modal.

Revisar.

Se realmente não houver mais uso, remover para não voltar acidentalmente ao comportamento antigo de:

Mesa fechada
→ modal
→ operador precisa fechar modal
→ só depois navega
17. PRESERVAR AS CORREÇÕES DE IMPRESSÃO QUE ESTÃO NA MESMA MISSÃO

Ainda precisam ser corrigidos os problemas já identificados:

STATUS STALE

Quando documento/produção estiver:

PENDING
PROCESSING

a tela visível deve acompanhar o backend e atualizar para:

PRINTED
FAILED
UNCERTAIN

sem exigir sair e voltar.

Especialmente:

Conferência;
comprovante;
status da produção no resumo da Mesa.
18. FAILED BEFORE SEND DEVE DAR DIREITO A NOVA TENTATIVA

Hoje existe um bug:

startPrintDispatch()
→ physical_dispatch_started_at preenchido
→ Socket.connect falha antes de enviar qualquer byte
→ transport retorna failedBeforeSend
→ backend fica FAILED + physical_dispatch_started_at

Então:

retry_eligible = false
reprint_eligible = false

e o documento fica preso.

Corrigir mantendo segurança:

FAILED BEFORE SEND
→ TENTAR NOVAMENTE
→ não é reimpressão
→ sem tarja preta
UNCERTAIN
→ REIMPRIMIR explicitamente
→ tarja preta
PRINTED
→ REIMPRIMIR
→ tarja preta

Não permitir retry automático quando houver possibilidade de o papel ter sido enviado.

19. DATAS DOS CUPONS EM PADRÃO BRASILEIRO

Hoje alguns valores ISO chegam direto ao renderer.

Não imprimir:

2026-09-24T23:18:37.482193+00:00

nem:

2026-09-24 20:18

Padronizar:

24/09/2026 20:18

em todos os documentos térmicos.

Criar helper central no renderer.

Aplicar em:

Conferência;
recibo final;
comprovante de pagamento;
Ticket;
demais datas dos documentos térmicos.
20. CUPOM DEVE TER UMA ÚNICA LINHA DE DESCONTO

Hoje o snapshot da Mesa possui:

promotion_discount_total
item_discount_total
checkout_discount_total
discount_total

e discount_total já representa a soma.

O cupom não deve imprimir:

Promoções
Desconto por item
Desconto

como três linhas.

Usar:

Subtotal
Descontos
Taxa de serviço
TOTAL

onde:

Descontos = desconto total efetivo

Se desconto total for zero:

não imprimir a linha

Não alterar a matemática financeira.

É apenas apresentação do cupom.

21. SOLICITAR CONTA / CONFERÊNCIA

Preservar a regra definida:

SOLICITAR CONTA
→ TABLE_CONFERENCE
→ primeira impressão da Conferência

e a impressão/reimpressão manual continua somente pelo:

ícone de impressora
na tela Visualizar Conferência

Não recolocar:

IMPRIMIR CONFERÊNCIA
REIMPRIMIR CONFERÊNCIA

no menu da Mesa.

22. REIMPRESSÕES

Preservar a tarja preta global recém-implementada:

REIMPRESSAO #N

com fundo preto / texto branco.

Primeira impressão não recebe tarja.

Retry de FAILED BEFORE SEND também não recebe tarja porque não é reimpressão.

23. TICKETS

Preservar a correção recente que passou:

pos_device

para Ticket de:

Mesa;
Comanda;
Venda Rápida.

Não regredir PrintRouteOverride.TICKET.

24. RESULTADOS ESPERADOS
Venda Rápida
abrir Venda Rápida
→ carrinho vazio
→ não recuperar venda antiga
→ não mostrar "Venda em andamento recuperada"
Mesa vazia
Mesa aberta sem produto
→ Solicitar Conta
→ BLOQUEADO
→ "Adicione e envie pelo menos um produto antes de solicitar a conta."
Mesa com item apenas no carrinho
produto não enviado
→ Solicitar Conta
→ BLOQUEADO
→ "Envie os itens novos antes de solicitar a conta."
Mesa com produto confirmado
produto enviado
→ Solicitar Conta
→ permitido
→ Conferência
Fechamento
último pagamento
→ FECHAR MESA
→ backend CLOSED
→ retorna direto ao grid
→ grid atualiza
→ Mesa aparece livre
→ "Mesa fechada com sucesso."
25. ARQUIVOS A REVISAR

No mínimo:

pos/lib/sales/quick_sale_page.dart
pos/lib/core/app_controller.dart

pos/lib/attendance/table_attendance_page.dart
pos/lib/attendance/attendance_pages.dart
pos/lib/payments/table_payment_page.dart

backend/apps/attendance/services.py

pos/lib/printing/print_document_polling.dart
pos/lib/printing/print_manager.dart
pos/lib/printing/production_ticket_renderer.dart

backend/apps/production/services.py
backend/apps/production/serializers.py

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

o que foi removido da recuperação automática da Venda Rápida;
quais mecanismos de idempotência/reconciliação foram preservados;
como ficou checkout abandonado;
como o backend bloqueia Solicitar Conta em Mesa sem produto;
como a UI bloqueia Mesa vazia;
como ficou a navegação após fechar Mesa;
onde a mensagem "Mesa fechada com sucesso." passa a ser exibida;
se removeu _showFinalReceiptAction() caso estivesse morto;
como corrigiu atualização viva dos estados de impressão;
como corrigiu FAILED BEFORE SEND;
como ficaram as datas dos cupons;
como consolidou os descontos em uma linha;
se preservou Conferência, tarja de reimpressão e Tickets;
arquivos backend alterados;
arquivos Flutter alterados;
migrations criadas — não deveria precisar;
pontos restantes para teste manual.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.

Depois pare.