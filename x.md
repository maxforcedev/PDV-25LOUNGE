Continue no HEAD atual.

Na última revisão, o HEAD era:

`6946139a7a3e6f692f6f24866d71c7e2f1c7f19c`

Antes de alterar, confira o HEAD atual.

Precisamos fechar estes pontos que ainda ficaram pendentes no fluxo de impressão do CORE POS.

---

# 1. SOLICITAR CONTA DEVE EMITIR UMA CONFERÊNCIA NO MESMO PADRÃO VISUAL DO CUPOM FINAL

Hoje:

```text
Solicitar conta
→ TABLE_CONFERENCE
→ automatic_only=True

e o renderer ainda usa o layout antigo:

CONFERENCIA
SEM VALOR FISCAL
MESA...
itens...
totais...

Quero mudar.

Ao solicitar conta, o documento deve continuar sendo:

TABLE_CONFERENCE

mas o layout precisa ficar no mesmo estilo do recibo final que foi implementado agora.

Referência estrutural:

EMPRESA
FILIAL

CONFERENCIA DA CONTA
RELATORIO GERENCIAL
*** NAO E DOCUMENTO FISCAL ***

Endereco
Telefone

MESA X
Atendimento: ...
Aberta em: ...
Impresso em: ...
Atendente: ...
Cliente: ...

----------------------------

ITENS

1x PRODUTO            39,90
  modificador
  OBS: ...

----------------------------

SUBTOTAL
DESCONTOS
TAXA DE SERVICO
TOTAL
TOTAL PAGO
SALDO A PAGAR

----------------------------

PAGAMENTOS JA REALIZADOS
PIX                    20,00
CARTAO                 10,00

----------------------------

A Mesa continua aberta.

NÃO colocar:

Fechada em

na Conferência.

2. SOLICITAR CONTA DEVE DISPARAR A PRIMEIRA IMPRESSÃO

A ação:

SOLICITAR CONTA

deve ser o gatilho normal da primeira impressão da Conferência, conforme a rota configurada.

Se a rota TABLE_CONFERENCE estiver configurada para emissão automática:

Solicitar conta
→ cria/encontra PrintDocument
→ cria PrintJob inicial
→ PrintManager imprime

Preservar a arquitetura atual de:

PrintDocument
PrintRoute
PrintRouteOverride
PrintJob

Não criar impressão direta pela UI.

3. REMOVER IMPRIMIR / REIMPRIMIR CONFERÊNCIA DO MENU DA MESA

Hoje o menu ainda possui:

Visualizar conferência
Solicitar conta
IMPRIMIR CONFERÊNCIA / REIMPRIMIR CONFERÊNCIA

Remover completamente:

IMPRIMIR CONFERÊNCIA
REIMPRIMIR CONFERÊNCIA

do PopupMenuButton.

Também remover o fluxo duplicado relacionado, como:

_printBill()
case 'print_bill'

se não existir outro uso necessário.

O menu da Mesa deve ficar com:

Visualizar conferência
Solicitar conta / Cancelar solicitação de conta
...
4. IMPRESSÃO DA CONFERÊNCIA FICA SOMENTE NO VISUALIZAR CONFERÊNCIA

Na tela:

Visualizar conferência

já existe o ícone:

🖨

Esse deve ser o ÚNICO ponto manual para:

IMPRIMIR
REIMPRIMIR

a Conferência.

Não duplicar ação no menu da Mesa.

5. REGRA FORTE: UMA ÚNICA PRIMEIRA IMPRESSÃO

Não permitir duas impressões iniciais do mesmo documento/snapshot.

Fluxo obrigatório:

PrintDocument novo
→ PRIMEIRA IMPRESSÃO

já possui impressão inicial
→ não pode gerar outra impressão inicial

se quiser outra cópia
→ REPRINT

Preservar a proteção atual de:

initial_jobs = document.print_jobs.filter(reprint_of__isnull=True)

if initial_jobs:
    return initial_jobs

ou equivalente.

Não criar um novo PrintDocument só para conseguir outra cópia do mesmo snapshot.

6. SNAPSHOT NOVO PODE GERAR NOVA VERSÃO

Exemplo correto:

Solicitar conta
→ Conferência v1
→ imprime

Cancelar solicitação
→ adicionar novos produtos
→ solicitar conta novamente
→ snapshot mudou
→ Conferência v2
→ primeira impressão da v2

Isso é correto.

Mas:

mesmo snapshot
→ apertar imprimir novamente

NÃO pode criar nova primeira impressão.

Deve ser:

REPRINT
7. TODA REIMPRESSÃO DO CORE DEVE TER TARJA PRETA

Hoje já existe helper central:

_reprintBanner(...)

mas ele só imprime texto em negrito:

*** REIMPRESSAO #1 ***

Quero alterar isso.

Toda reimpressão física deve ter uma tarja preta evidente com texto branco:

████████████████████████████
        REIMPRESSAO #1
████████████████████████████

Não precisa desenhar blocos manualmente se ESC/POS suportar modo reverso.

Preferir comando ESC/POS de reverse/inverse printing:

fundo preto
texto branco

ocupando a largura imprimível.

8. A TARJA DEVE SER GLOBAL

Não implementar documento por documento.

Centralizar no helper existente:

_reprintBanner()

ou equivalente.

Assim a regra vale para TODAS as reimpressões:

TABLE_CONFERENCE;
TABLE_FINAL_RECEIPT;
PAYMENT_RECEIPT;
QUICK_SALE_RECEIPT;
TICKET;
TABLE_BILL legado;
reimpressão de produção quando aplicável.
9. PRIMEIRA IMPRESSÃO NÃO TEM TARJA

Somente:

reprint_number > 0

ou reprint explícito.

Nunca mostrar tarja de reimpressão na impressão inicial.

10. TICKET — PROBLEMA IDENTIFICADO

Hoje o sistema cria Ticket corretamente quando:

product.emits_ticket = true

Na Mesa:

_confirm_table_item()
→ create_table_production_jobs()
→ create_table_order_item_ticket()

Então o registro comercial do Ticket é criado.

O problema está na emissão física.

Hoje _create_ticket() faz:

issue_print_document(
    branch=branch,
    document_type=PrintDocumentType.TICKET,
    source_type='ticket',
    source_id=ticket.pk,
    user=user,
    automatic_only=True,
)

SEM:

pos_device
11. ISSO FAZ O TICKET IGNORAR OVERRIDE DO POS

Quando pos_device=None:

effective_print_route(...)

resolve apenas a rota da filial.

Então:

POS X
TICKET = AUTOMATIC
Impressora Y

como override específico do POS pode ser ignorado.

Na Venda Rápida já existe um segundo fluxo:

_issue_ticket_documents(sale, operator, device)

que conhece o device.

Mesa e Comanda precisam ficar coerentes.

12. CORRIGIR TICKET DE MESA

Quando confirmar item de Mesa com:

emits_ticket = true

o fluxo deve ser:

confirmar item
→ criar Ticket uma única vez
→ emitir PrintDocument TICKET
→ passar POSDevice de origem
→ resolver PrintRoute / PrintRouteOverride
→ se rota TICKET automática
→ criar PrintJob
→ PrintManager imprime

Não emitir novamente no fechamento da Mesa.

Ticket da Mesa deve sair no momento em que o item entra no fluxo operacional.

13. CORRIGIR TICKET DE COMANDA

Mesma regra:

confirmar item da Comanda
→ se emits_ticket
→ criar Ticket
→ emitir com pos_device correto

Não esperar fechamento da Comanda.

14. VENDA RÁPIDA

Revisar a Venda Rápida para garantir que não está emitindo o mesmo Ticket duas vezes.

Hoje existe:

create_sale_tickets()

e depois:

_issue_ticket_documents(sale, operator, device)

Confirmar que:

Ticket comercial

é criado uma única vez e que:

PrintDocument TICKET

também mantém apenas uma impressão inicial.

Não criar dois PrintJob iniciais.

15. TICKET DEVE RESPEITAR ROTA

A impressão física do Ticket deve obedecer:

PrintRoute.TICKET

e:

PrintRouteOverride.TICKET

com prioridade normal:

sem override
→ filial

inherit_branch=true
→ filial

inherit_branch=false
→ override do POS
16. ROTA TICKET AUTOMATIC

Como Ticket operacional deve sair no momento do evento, o comportamento esperado é:

TICKET = automatic
→ imprime automaticamente

Se estiver:

manual

não imprimir automaticamente.

Se estiver:

disabled

não imprimir.

O registro Ticket pode continuar existindo mesmo sem impressão.

17. NÃO DUPLICAR TICKET

Mesmo Ticket:

ticket_id X
→ PrintDocument TICKET X
→ primeira impressão

não pode gerar outra impressão inicial.

Nova cópia:

REPRINT
→ tarja preta
18. CANCELAMENTO DE TICKET

Preservar o comportamento atual de:

cancel_ticket_for_source(...)

Não misturar cancelamento de Ticket comercial com reimpressão.

Não apagar Ticket histórico.

19. CUPOM FINAL DA MESA

Preservar o que já foi implementado no commit atual:

TABLE_FINAL_RECEIPT

com:

RECIBO DE FECHAMENTO DA MESA
RELATORIO GERENCIAL
*** NAO E DOCUMENTO FISCAL ***

e:

empresa;
filial;
endereço;
telefone;
mesa;
atendimento;
abertura;
fechamento;
itens;
modificadores;
observações;
totais;
pagamentos;
operador.
20. CONFERÊNCIA E RECIBO FINAL DEVEM TER O MESMO ESTILO

A diferença principal deve ser de contexto.

Conferência
CONFERENCIA DA CONTA
RELATORIO GERENCIAL
*** NAO E DOCUMENTO FISCAL ***

Mesa ainda aberta.

Fechamento
RECIBO DE FECHAMENTO DA MESA
RELATORIO GERENCIAL
*** NAO E DOCUMENTO FISCAL ***

Mesa já fechada.

Compartilhar helpers de layout quando fizer sentido.

Evitar dois renderers completamente diferentes com código duplicado.

21. NÃO REGREDIR O QUE JÁ ESTÁ CERTO

Preservar:

cupom final da Mesa;
pagamentos APPLIED e não estornados;
branch_address;
branch_phone;
hash + fallback legado;
polling de produção;
polling de PrintDocument;
UNCERTAIN;
retry != reprint;
physical_dispatch_started_at;
claim/lease;
idempotência;
quantidade formatada;
retorno da Mesa para o grid;
bloqueio após Solicitar Conta;
PrintRoute / PrintRouteOverride;
impressão NETWORK local.
22. RESULTADO ESPERADO — SOLICITAR CONTA
Mesa aberta
→ itens enviados
→ SOLICITAR CONTA
→ bill_requested = true
→ TABLE_CONFERENCE
→ impressão inicial
→ cupom no modelo gerencial
23. RESULTADO ESPERADO — VISUALIZAR CONFERÊNCIA
Mesa
→ Visualizar conferência

Na tela:

🖨

Se nunca imprimiu:

IMPRIMIR

Se já imprimiu:

REIMPRIMIR

Não existe mais impressão no menu anterior.

24. RESULTADO ESPERADO — REIMPRESSÃO
documento já PRINTED
→ operador pede nova cópia
→ REPRINT
→ novo PrintJob reprint
→ papel sai com TARJA PRETA

Exemplo:

████████████████████████
      REIMPRESSAO #1
████████████████████████
25. RESULTADO ESPERADO — TICKET MESA
Produto:
emits_ticket = true

Mesa:
enviar item

→ cria TableOrderItem
→ confirma
→ cria Ticket
→ resolve rota TICKET com POS atual
→ PrintJob
→ papel sai
26. RESULTADO ESPERADO — TICKET COM OVERRIDE
Filial:
TICKET = disabled

POS A:
override TICKET = automatic
Impressora Ticket

Produto emits_ticket
→ venda/mesa/comanda no POS A
→ deve imprimir Ticket

Isso hoje pode falhar porque o pos_device não chega em alguns fluxos.

CORRIGIR.

27. RESULTADO ESPERADO — SEM DUPLICAÇÃO
mesmo Ticket
→ uma impressão inicial

mesma Conferência/snapshot
→ uma impressão inicial

mesmo recibo final
→ uma impressão inicial

Qualquer nova cópia física:

REPRINT
28. ARQUIVOS A REVISAR

No mínimo:

backend/apps/attendance/services.py
backend/apps/production/services.py
backend/apps/pos/views.py
backend/apps/sales/services.py

pos/lib/attendance/table_attendance_page.dart
pos/lib/printing/production_ticket_renderer.dart
pos/lib/printing/models.dart

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

como ficou o layout da TABLE_CONFERENCE;
se Solicitar Conta continua sendo o gatilho da primeira impressão;
se removeu IMPRIMIR/REIMPRIMIR CONFERÊNCIA do menu;
se a impressão manual ficou somente no ícone da tela de Conferência;
como garantiu uma única impressão inicial;
como ficou a tarja preta global de reimpressão;
quais tipos de documento usam essa tarja;
qual era a causa do Ticket não imprimir corretamente;
como o pos_device passou a chegar ao Ticket da Mesa;
como o pos_device passou a chegar ao Ticket da Comanda;
se a Venda Rápida continua sem duplicar Ticket;
como a rota TICKET respeita override do POS;
arquivos backend alterados;
arquivos Flutter alterados;
migrations criadas — não deveria precisar;
pontos restantes para teste manual.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.

Depois pare.