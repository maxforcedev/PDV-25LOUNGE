# MISSÃO — Corrigir fluxo de Mesa + Conferência + Impressão + Comprovante de pagamento

Trabalhe no **HEAD mais recente da main**.

Na última revisão, o HEAD era:

`e794dbfdaf16160f0a05065b390c8327156d8031`

Antes de alterar, confira o HEAD atual.

Temos vários erros reais encontrados em uso manual do CORE POS e precisamos corrigir todos nesta missão.

---

# REGRA CRÍTICA

NÃO EXECUTE TESTES.

NÃO execute:

- flutter analyze
- flutter test
- flutter build
- flutter run
- pytest
- npm test
- npm build
- npm lint
- suites
- makemigrations --check

Eu farei o build e os testes manualmente.

---

# PROBLEMAS ENCONTRADOS

## 1. Erro ao visualizar Conferência

Ao abrir a tela:

```text
Mesa
→ Conferência

a visualização não está funcionando corretamente.

A tela atual está em:

pos/lib/attendance/table_attendance_page.dart

classe:

_TableConferencePage

Ela atualmente recebe um objeto attendance já existente e monta a conferência diretamente dele.

Não depender apenas de um snapshot possivelmente antigo da Mesa.

2. Quantidade na impressão de produção aparece errada

Na impressão de produção está saindo:

1.000x PRODUTO

quando deveria sair:

1x PRODUTO

O backend mantém quantidade com precisão decimal, o que está correto.

O problema é SOMENTE de apresentação.

Hoje o renderer usa diretamente:

'${item['quantity']}x ${item['product_name']}'

em:

pos/lib/printing/production_ticket_renderer.dart

Isso faz um Decimal como:

1.000

ser impresso literalmente.

3. Depois de imprimir continua "Aguardando impressão"

A impressão física ocorre, mas a UI continua exibindo algo equivalente a:

Aguardando impressão

O problema é que PrintDocumentResult recebido logo após a emissão contém:

queued = true

e depois o PrintManager processa o PrintJob em background.

Porém a tela continua usando o estado antigo do documento.

Precisamos atualizar o estado do documento após a execução física.

4. Solicitar conta ainda permite adicionar produtos

Depois de:

SOLICITAR CONTA

a Mesa NÃO deve aceitar novos produtos.

Hoje save_table_order() verifica apenas:

attendance.status == OPEN

e não verifica:

bill_requested

Portanto o backend ainda aceita um novo pedido mesmo depois da conta ter sido solicitada.

Isso precisa ser bloqueado no BACKEND e no FLUTTER.

5. Solicitar conta deve imprimir CONFERÊNCIA NÃO FISCAL

Ao clicar:

SOLICITAR CONTA

deve ser emitida a conferência da mesa:

CONFERÊNCIA
SEM VALOR FISCAL

Não é cupom fiscal.

Não é recibo final.

É a conferência da conta atual da mesa.

Hoje set_table_bill_requested() dispara:

PrintDocumentType.TABLE_BILL

com:

trigger = table_bill_requested

Revisar essa semântica.

Para o fluxo do CORE POS que estamos definindo:

SOLICITAR CONTA
→ marca bill_requested
→ bloqueia novos pedidos
→ emite/imprime a CONFERÊNCIA NÃO FISCAL

Usar o documento:

TABLE_CONFERENCE

para essa impressão.

O renderer já possui:

CONFERENCIA
SEM VALOR FISCAL

para TABLE_CONFERENCE.

NÃO criar outro tipo de documento.

NÃO criar impressão paralela duplicada.

6. Mesa fecha mas permanece na tela

Ao pagar totalmente e clicar para fechar a Mesa:

Mesa fechada

o backend fecha corretamente, porém o POS permanece na tela da mesa/pagamento.

O comportamento correto deve ser:

FECHAR MESA
→ backend confirma fechamento
→ mostrar mensagem "Mesa fechada com sucesso"
→ sair da tela de pagamento
→ sair da tela da Mesa
→ voltar para o grid de Mesas
→ atualizar o grid imediatamente

Não permanecer dentro de uma Mesa já fechada.

7. Imprimir comprovante da forma de pagamento não funciona

Na tela de pagamentos existe ação para imprimir o comprovante daquele pagamento.

Fluxo esperado:

Pagamento realizado
→ botão imprimir
→ PAYMENT_RECEIPT
→ source_type = table_payment
→ source_id = ID do TablePayment
→ PrintDocument
→ PrintJob
→ PrintManager
→ impressora

Hoje o botão/fluxo não está funcionando corretamente em uso real.

Corrigir.

PARTE 1 — CORRIGIR VISUALIZAÇÃO DA CONFERÊNCIA

Ao abrir _TableConferencePage, buscar o estado ATUAL da Mesa pelo backend.

Usar:

tableAttendanceDetail(attendance.id)

ou o fluxo equivalente já existente.

Não renderizar exclusivamente widget.attendance.

A tela precisa ter estados claros:

loading
loaded
error

Se houver erro de API:

não quebrar a página;
mostrar mensagem compreensível;
permitir voltar;
permitir tentar novamente se apropriado.

Quando carregada, usar o objeto atualizado para:

nome da mesa;
atendente;
itens confirmados;
quantidades;
valores;
descontos;
taxa;
total;
documento de impressão atual.
PARTE 2 — CONFERÊNCIA NÃO PODE ALTERAR A MESA

Abrir Conferência é somente leitura.

NÃO:

criar PrintDocument automaticamente ao abrir;
adicionar item;
alterar desconto;
solicitar conta;
registrar pagamento;
fechar Mesa.

Abrir Conferência:

GET/read-only

Imprimir Conferência:

ação explícita
PARTE 3 — CORRIGIR QUANTIDADE 1.000x

Criar/reutilizar um formatter de quantidade adequado para impressão.

Exemplos esperados:

1.000  → 1
2.000  → 2
1.500  → 1,5
0.500  → 0,5
2.250  → 2,25
10.000 → 10

Não arredondar quantidade fracionária válida.

Não alterar o Decimal no backend.

Não alterar precisão de banco.

É apenas apresentação.

Aplicar pelo menos em:

Production Ticket
Document Items
Ticket quantity

onde quantidades são exibidas fisicamente.

Não deixar diferentes formatos inconsistentes em cada documento.

Preferir helper compartilhado no renderer.

PARTE 4 — PRODUÇÃO

Hoje existe no renderer algo equivalente a:

_line(
  bytes,
  '${item['quantity'] ?? ''}x ${item['product_name'] ?? ''}',
)

Substituir o valor cru pelo formatter.

Resultado:

1x COCA COLA

e não:

1.000x COCA COLA
PARTE 5 — DOCUMENTOS COMERCIAIS

Também revisar _documentItems().

Hoje ele usa diretamente:

final quantity = _first(item, ['quantity']) ?? '';

Não deixar Conferência/Conta/Recibo imprimir:

1.000x

Usar o mesmo formatter.

PARTE 6 — STATUS "AGUARDANDO IMPRESSÃO" ESTÁ STALE

Não alterar a regra correta de:

PENDING
PROCESSING
PRINTED
FAILED
UNCERTAIN

O problema é de atualização da UI.

Após:

requestPrintDocument()

é esperado que o primeiro response possa retornar:

queued = true

porque o PrintManager ainda vai imprimir.

Depois da impressão física, o backend passa o PrintJob para:

PRINTED

A tela precisa obter esse estado atualizado.

PARTE 7 — ATUALIZAÇÃO DO STATUS DE IMPRESSÃO

Implementar atualização controlada enquanto houver:

awaitingInitialPrint == true

Pode ser:

refresh do attendance;
refresh do ledger;
consulta de documento;
mecanismo central equivalente.

Preferir reutilizar APIs já existentes.

Não criar polling infinito.

Pode fazer polling curto e limitado, por exemplo:

consultar
→ aguardar pequeno intervalo
→ consultar novamente
→ parar quando terminal

Estados terminais:

PRINTED
FAILED
UNCERTAIN

Também atualizar ao voltar para a tela.

PARTE 8 — CONFERÊNCIA APÓS IMPRESSÃO

Cenário:

IMPRIMIR CONFERÊNCIA
→ PrintJob PENDING
→ PrintManager imprime
→ backend PRINTED

A UI deve mudar automaticamente de:

AGUARDANDO IMPRESSÃO

para:

REIMPRIMIR

quando o documento estiver elegível.

Não exigir fechar e abrir a Mesa para atualizar.

PARTE 9 — NÃO CONFUNDIR RETRY E REPRINT

Preservar as regras existentes:

FAILED antes do physical dispatch
→ retry

PRINTED
→ reprint

UNCERTAIN
→ pode permitir reprint explícito conforme regra existente

PENDING/PROCESSING
→ aguardar

Não criar segunda cópia automaticamente só porque a UI demorou para atualizar.

PARTE 10 — SOLICITAR CONTA BLOQUEIA NOVOS PRODUTOS

Quando:

attendance.bill_requested_at != null

a Mesa continua OPEN para:

pagamento;
estorno permitido;
fechamento;
consulta;
impressão;
limpar solicitação de conta, se permitido.

Mas não pode receber novos pedidos.

PARTE 11 — BACKEND DEVE BLOQUEAR NOVOS PEDIDOS

Em:

save_table_order()

adicionar proteção depois de carregar a Mesa com lock.

Se:

bill_requested_at != null

retornar conflito de domínio.

Exemplo de code:

table_bill_requested

Mensagem:

A conta desta mesa já foi solicitada. Libere a conta antes de adicionar novos produtos.

Não depender somente do Flutter.

Isso protege contra:

cliente stale;
request duplicado;
outro POS;
concorrência.
PARTE 12 — PREVIEW DE NOVOS ITENS

Se a conta já foi solicitada, não permitir que o fluxo de inclusão continue como se a Mesa estivesse editável.

Revisar:

preview_table_order
save_table_order
UI do catálogo
botão enviar pedido

O servidor é a autoridade.

PARTE 13 — FLUTTER DEVE BLOQUEAR CATÁLOGO

Quando:

attendance.billRequested == true

na tela da Mesa:

não permitir adicionar produto;
não permitir alterar quantidade de draft;
não permitir enviar novo pedido;
indicar claramente que a conta foi solicitada.

Pode desabilitar a área de catálogo ou os controles de inclusão.

Mensagem sugerida:

Conta solicitada. Novos produtos estão bloqueados.
PARTE 14 — ITENS LOCAIS NÃO ENVIADOS

Não permitir solicitar conta se houver produtos ainda no carrinho/draft local.

Cenário:

carrinho possui novos itens não enviados
→ operador toca SOLICITAR CONTA

Resultado:

bloquear ação
→ "Envie os itens novos antes de solicitar a conta."

Não perder o draft silenciosamente.

PARTE 15 — LIMPAR SOLICITAÇÃO DE CONTA

Se existe ação para:

LIBERAR/REMOVER SOLICITAÇÃO DE CONTA

e ela é concluída com sucesso:

bill_requested_at = null

então a Mesa volta a poder receber produtos.

Preservar esse comportamento.

PARTE 16 — SOLICITAR CONTA IMPRIME CONFERÊNCIA

Alterar o efeito secundário atual.

Hoje existe:

PrintDocumentType.TABLE_BILL
metadata={'trigger': 'table_bill_requested'}

Para o fluxo definido agora, Solicitar Conta deve usar:

PrintDocumentType.TABLE_CONFERENCE

com origem:

source_type = table_attendance
source_id = attendance.id

e metadata coerente, por exemplo:

trigger = table_bill_requested
PARTE 17 — DOCUMENTO DA SOLICITAÇÃO

O papel deve ser:

CONFERÊNCIA
SEM VALOR FISCAL

MESA X
data/hora
atendente

1x Produto A
2x Produto B

Subtotal
Descontos
Taxa de serviço
TOTAL

Cliente, se houver

NÃO escrever:

RECIBO FISCAL
CUPOM FISCAL
NFC-e
PARTE 18 — ROTA DE IMPRESSÃO DA CONFERÊNCIA

A impressão deve respeitar:

effective_print_route(
    branch,
    TABLE_CONFERENCE,
    pos_device
)

Portanto:

override do POS
→ se existir, usar override

senão
→ regra da filial

Não apontar IP diretamente no código da Mesa.

PARTE 19 — SOLICITAR CONTA E MODO DA ROTA

Se a rota efetiva de TABLE_CONFERENCE estiver:

AUTOMATIC

Solicitar Conta deve enfileirar automaticamente.

Se estiver:

MANUAL

a solicitação de conta continua registrada, e a Conferência deve poder ser impressa manualmente pela ação existente.

Se estiver:

DISABLED

não causar 500.

Registrar/mostrar situação adequadamente.

NÃO desfazer a solicitação de conta só porque uma impressora falhou.

Impressão é efeito secundário.

PARTE 20 — NÃO DUPLICAR CONFERÊNCIA

Se Solicitar Conta criar/imprimir a conferência do snapshot atual, e depois o operador abrir Conferência:

o sistema deve reconhecer o mesmo:

document_type
source
snapshot_hash

e não criar documento inicial duplicado.

Mesma fotografia da Mesa:

mesmo PrintDocument

Uma segunda cópia explícita:

REPRINT
PARTE 21 — MUDANÇA DE SNAPSHOT

Se a solicitação de conta for liberada:

bill_requested = false

e novos itens forem adicionados,

o snapshot da Mesa muda.

Nova solicitação:

novo snapshot
→ nova versão de TABLE_CONFERENCE
→ primeira impressão desse novo snapshot

Não tratar como reprint da versão anterior.

PARTE 22 — FECHAR MESA DEVE VOLTAR AO GRID

Corrigir o fluxo completo de navegação.

Hoje temos:

TableAttendancePage
→ abre TablePaymentPage
→ fecha Mesa

Ao backend retornar:

attendance.status == closed

não permanecer em nenhuma das duas telas.

Fluxo obrigatório:

TablePaymentPage recebe CLOSED
→ encerra tela de pagamento

TableAttendancePage recebe CLOSED
→ encerra detalhe da Mesa

Grid de Mesas reaparece
→ reload das mesas
PARTE 23 — MENSAGEM DE SUCESSO

Ao voltar para o grid, mostrar:

Mesa fechada com sucesso.

Preferir feedback não bloqueante do padrão do CORE POS.

Não exigir que o usuário feche um modal para voltar ao grid.

PARTE 24 — IMPRESSÃO NÃO DEVE BLOQUEAR NAVEGAÇÃO DE FECHAMENTO

Se ao fechar a Mesa houver:

TABLE_FINAL_RECEIPT

automático:

a impressão deve seguir como efeito secundário.

Não deixar o usuário preso na tela de Mesa esperando impressão.

Não manter um modal obrigatório de recibo final antes de voltar ao grid.

Fechamento confirmado:

→ voltar ao grid

Impressão continua pelo PrintManager.

PARTE 25 — NÃO DUPLICAR POP/NAVEGAÇÃO

Organizar responsabilidade.

Preferencialmente:

TablePaymentPage
→ retorna TableAttendance CLOSED

TableAttendancePage
→ recebe
→ retorna CLOSED para grid

Grid
→ atualiza
→ mostra mensagem

Evitar múltiplos Navigator.pop() espalhados provocando:

tela errada;
pop a mais;
pop a menos;
race condition.
PARTE 26 — GRID DE MESAS

Ao retornar de uma Mesa fechada:

recarregar imediatamente o estado do grid.

A mesa deve aparecer como:

LIVRE

ou estado operacional equivalente.

Não esperar próximo polling manual.

PARTE 27 — COMPROVANTE DE PAGAMENTO DA MESA

Corrigir:

IMPRIMIR COMPROVANTE

para TablePayment.

Fluxo oficial:

PrintDocumentType.PAYMENT_RECEIPT
source_type = table_payment
source_id = payment.id

O backend já suporta essa origem.

Preservar.

PARTE 28 — SNAPSHOT DO PAGAMENTO

O comprovante deve usar dados do pagamento real:

Mesa
Forma de pagamento
Valor
Valor recebido
Troco
Data/hora
Operador

Não recalcular pagamento no Flutter.

Não criar novo pagamento.

É somente impressão do pagamento existente.

PARTE 29 — ROTA PAYMENT_RECEIPT

Usar:

effective_print_route(
    branch,
    PAYMENT_RECEIPT,
    pos_device
)

Respeitando:

filial
→ override opcional do POS

Quando o usuário clicar explicitamente em imprimir:

MANUAL

deve enfileirar normalmente.

AUTOMATIC também é uma rota válida.

DISABLED deve retornar erro claro para a UI.

PARTE 30 — NÃO ENGOLIR ERROS DO COMPROVANTE

Hoje, se requestPrintDocument() retornar erro, não deixar parecer que o botão "não fez nada".

Mostrar a mensagem técnica convertida para mensagem operacional.

Exemplos:

A rota de comprovante de pagamento está desabilitada.
Nenhuma impressora NETWORK ativa está configurada.
O pagamento não está mais ativo.

Não esconder 400/409 silenciosamente.

PARTE 31 — STATUS DO COMPROVANTE TAMBÉM PRECISA ATUALIZAR

Mesmo problema da Conferência:

botão imprimir
→ response PENDING
→ impressão física ocorre
→ UI não atualiza

Após impressão:

IMPRIMIR COMPROVANTE

deve virar:

REIMPRIMIR COMPROVANTE

quando o backend confirmar PRINTED/estado elegível.

Atualizar o ledger/document state.

PARTE 32 — NÃO BLOQUEAR PARA SEMPRE COM awaitingInitialPrint

Hoje existem trechos:

if (document?.awaitingInitialPrint == true) {
    ...
    return;
}

Isso está correto somente se o estado estiver realmente atualizado.

Não deixar um objeto stale impedir nova ação para sempre.

Antes de afirmar:

A impressão inicial ainda está pendente.

quando houver possibilidade do PrintManager já ter concluído, atualizar o estado no backend.

PARTE 33 — CENTRALIZAR REFRESH DE DOCUMENTO SE POSSÍVEL

Temos o mesmo problema em:

Conferência;
Conta;
Recibo final;
Comprovante de pagamento;
Venda rápida.

Evitar vários loops diferentes.

Se possível, criar mecanismo pequeno/reutilizável para atualizar o estado de PrintDocument.

Não criar arquitetura gigantesca.

PARTE 34 — VISUAL DA CONFERÊNCIA

A tela de visualização deve mostrar as mesmas quantidades formatadas corretamente.

Exemplo:

1x Heineken
2x Coca-Cola
1,5x Produto vendido por quantidade fracionária

Não:

1.000x
2.000x

Usar o formatter já existente:

formatAttendanceQuantity

ou centralizar sem duplicar lógica.

PARTE 35 — ITENS CANCELADOS

Na Conferência NÃO contabilizar itens cancelados como ativos.

Usar somente itens que fazem parte do estado financeiro atual da Mesa.

Não alterar histórico/auditoria.

PARTE 36 — VALORES DA CONFERÊNCIA

A conferência deve refletir exatamente table_summary():

subtotal;
promoções;
desconto por item;
desconto da conta;
taxa de serviço;
total;
pago, se fizer sentido na visualização;
saldo, se fizer sentido.

Não fazer cálculo paralelo no Flutter.

PARTE 37 — CABEÇALHO

Revisar também o snapshot de documentos.

Hoje o renderer tenta:

company_name
branch_name
branch

mas _table_snapshot() pode não estar fornecendo esses dados.

Garantir que Conferência/Recibo/Comprovante tenham cabeçalho coerente com:

empresa;
filial;
mesa;
data/hora;
atendente.

Sem quebrar snapshot imutável.

PARTE 38 — NÃO REGREDIR PRODUÇÃO

Mesa continua imprimindo produção quando:

pedido é enviado/confirmado

Solicitar conta NÃO pode reenviar produção.

Abrir Conferência NÃO pode reenviar produção.

Fechar Mesa NÃO pode reenviar produção.

Imprimir comprovante NÃO pode reenviar produção.

PARTE 39 — PRODUÇÃO DE NOVOS PEDIDOS

Antes de solicitar conta:

Mesa aberta
→ adicionar item
→ enviar pedido
→ imprime somente item novo

Depois de solicitar conta:

nenhum novo pedido permitido

Se liberar a solicitação:

novos pedidos voltam a ser permitidos
PARTE 40 — NÃO MEXER NO ESTOQUE AO IMPRIMIR

Impressões comerciais não alteram:

estoque;
Sale;
TablePayment;
TableOrderItem;
caixa.

São somente documentos.

PARTE 41 — PRESERVAR SEGURANÇA DE IMPRESSÃO

Não alterar:

claim;
lease;
physical_dispatch_started_at;
UNCERTAIN;
retry seguro;
reprint explícito;
idempotência;
multiple printers;
multiple copies;
PrintDocumentRequest;
generated_jobs;
PrintJob;
PrintManager;
impressão NETWORK local.
PARTE 42 — RETRY != REPRINT

Preservar:

erro técnico confirmado antes do envio
→ RETRY

documento já impresso
→ REPRINT

resultado incerto
→ NÃO retry automático
PARTE 43 — NÃO CRIAR NOVAS ENTIDADES SEM NECESSIDADE

Não precisamos de novo model para resolver estes bugs.

Usar:

TableAttendance;
TableOrder;
TableOrderItem;
TablePayment;
PrintDocument;
PrintRoute;
PrintRouteOverride;
PrintJob.

Migration não deveria ser necessária.

CENÁRIO MANUAL 1 — PRODUÇÃO
Adicionar 1 unidade
→ enviar pedido
→ ticket deve mostrar:

1x PRODUTO

e NÃO:

1.000x PRODUTO
CENÁRIO MANUAL 2 — CONFERÊNCIA
Mesa com itens
→ abrir Conferência
→ visualização carrega sem erro
→ mostra dados atuais da Mesa
→ tocar IMPRIMIR
→ PrintJob criado
→ imprime
→ UI atualiza
→ botão/status passa para REIMPRIMIR
CENÁRIO MANUAL 3 — SOLICITAR CONTA
Mesa com pedidos enviados
→ SOLICITAR CONTA
→ bill_requested = true
→ Conferência sem valor fiscal emitida conforme rota
→ catálogo fica bloqueado
→ backend rejeita novos pedidos
CENÁRIO MANUAL 4 — DRAFT PENDENTE
Adicionar item no carrinho
→ não enviar
→ SOLICITAR CONTA

Resultado:

bloquear
"Envie os itens novos antes de solicitar a conta."
CENÁRIO MANUAL 5 — LIBERAR CONTA
Conta solicitada
→ liberar solicitação
→ bill_requested = false
→ inclusão de novos produtos volta a funcionar
CENÁRIO MANUAL 6 — PAGAMENTO
Registrar pagamento
→ clicar IMPRIMIR COMPROVANTE
→ PAYMENT_RECEIPT
→ PrintJob
→ impressão física
→ status atualizado
→ ação passa a REIMPRIMIR COMPROVANTE
CENÁRIO MANUAL 7 — FECHAR MESA
Mesa totalmente paga
→ FECHAR MESA
→ backend CLOSED
→ mensagem "Mesa fechada com sucesso"
→ sair do pagamento
→ sair da Mesa
→ voltar para grid
→ grid atualizado
→ mesa livre
CENÁRIO MANUAL 8 — IMPRESSÃO AUTOMÁTICA NÃO PRENDE TELA
Fechar Mesa
→ Sale finalizada
→ recibo automático entra na fila
→ usuário volta ao grid imediatamente

Falha de impressão não deve fazer Mesa voltar a OPEN.

REVISAR OS ARQUIVOS RELACIONADOS

No mínimo revisar:

pos/lib/attendance/table_attendance_page.dart
pos/lib/attendance/attendance_models.dart
pos/lib/attendance/table_order_item_grouping.dart
pos/lib/payments/table_payment_page.dart
pos/lib/printing/production_ticket_renderer.dart
pos/lib/printing/models.dart
pos/lib/printing/print_manager.dart
pos/lib/core/app_controller.dart
pos/lib/network/pos_api.dart

backend/apps/attendance/services.py
backend/apps/attendance/models.py
backend/apps/pos/views.py
backend/apps/production/services.py
backend/apps/production/serializers.py

Alterar somente o necessário.

NÃO INICIAR OUTROS MÓDULOS

NÃO mexer agora em:

Cielo;
Stone refund;
TEF;
fiscal;
NFC-e;
Print Agent;
USB;
Bluetooth;
KDS;
Delivery;
Comandas antigas.
CHECKPOINT FINAL

Ao terminar informe:

causa do erro ao visualizar Conferência;
como a Conferência passou a carregar dados atualizados;
como corrigiu 1.000x para 1x;
qual formatter de quantidade foi utilizado;
como resolveu o estado stale de "Aguardando impressão";
como a UI descobre que o PrintJob virou PRINTED;
como ficou o bloqueio de novos produtos após Solicitar Conta;
qual conflito o backend retorna se tentarem adicionar item com conta solicitada;
como Solicitar Conta passou a usar TABLE_CONFERENCE;
como evitou impressão duplicada da mesma conferência;
como ficou o fluxo para liberar a solicitação da conta;
como corrigiu o retorno para o grid após fechar Mesa;
como o grid é atualizado após fechamento;
como corrigiu PAYMENT_RECEIPT de TablePayment;
como passou a atualizar o estado do comprovante depois da impressão;
se corrigiu o cabeçalho empresa/filial dos documentos;
arquivos backend alterados;
arquivos Flutter alterados;
migrations criadas — não deveria precisar;
qualquer ponto que ainda dependa de teste manual.

NÃO EXECUTE TESTES.

NÃO EXECUTE FLUTTER ANALYZE.

NÃO EXECUTE BUILD.

NÃO EXECUTE FLUTTER RUN.

Depois pare.