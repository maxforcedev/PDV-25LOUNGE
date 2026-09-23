TRABALHE NO HEAD ATUAL DA MAIN:

`80ed72d0003db68dd5497fce8903cb8024fd1b0d`

OBJETIVO DESTA MISSÃO:

Fechar a impressão no estado atual do CORE PDV para:

* MESAS;
* VENDA RÁPIDA;
* PRODUTOS / DESTINOS DE PRODUÇÃO;
* CONTA;
* CONFERÊNCIA;
* RECIBO;
* COMPROVANTE;
* TICKET;
* REIMPRESSÃO;
* ROTEAMENTO CONFIGURÁVEL DE IMPRESSÃO;
* CORREÇÃO DO LAYOUT ESC/POS.

NÃO IMPLEMENTAR AGORA:

* Stone Integrated Printer;
* USB real;
* Bluetooth real;
* Print Agent;
* fiscal;
* delivery;
* comanda;
* KDS.

A infraestrutura deve ficar preparada, mas esta missão é somente NETWORK + Mesa + Venda Rápida.

==================================================
REGRA CRÍTICA
=============

NÃO EXECUTE TESTES.

NÃO EXECUTE:

* pytest;
* flutter test;
* flutter analyze;
* npm test;
* npm build;
* npm lint;
* backend suites;
* frontend suites;
* build Android;
* build web;
* makemigrations --check;
* qualquer validação pesada;
* qualquer comando de teste automático.

EU FAREI A VALIDAÇÃO FUNCIONAL MANUALMENTE.

Pode criar migrations se forem necessárias para a implementação.

NÃO gaste tempo/créditos executando testes.

==================================================

1. PRESERVAR O BLOCO 1 JÁ IMPLEMENTADO
   ==================================================

NÃO quebrar nem reescrever sem necessidade:

* ProductionJob;
* PrintJob;
* claim;
* lease;
* physical_dispatch_started_at;
* UNCERTAIN;
* LocalPrintLedger;
* dispatch;
* reconcile;
* retry;
* reprint;
* PrintManager;
* TCP network printing;
* proteção contra impressão duplicada;
* impressão de produção de Mesa;
* impressão de produção de Venda Rápida;
* cancelamento de produção.

A infraestrutura segura do Bloco 1 deve continuar sendo usada como base de execução física.

==================================================
2. CONCEITO CENTRAL: PRODUÇÃO != DOCUMENTO
==========================================

Existem DOIS tipos diferentes de roteamento.

PRODUÇÃO:

Produto
→ ProductionDestination
→ PrinterDevice(s)

Exemplos:

X-Bacon
→ Cozinha
→ Impressora Cozinha

Caipirinha
→ Bar
→ Impressora Bar

DOCUMENTOS:

Tipo do documento
→ regra de impressão
→ PrinterDevice(s)

Exemplos:

TABLE_BILL
→ Impressora Caixa

TABLE_CONFERENCE
→ Impressora Atendimento

QUICK_SALE_RECEIPT
→ Impressora Balcão

NÃO usar ProductionDestination para representar conta, recibo, conferência ou comprovante.

NÃO mandar conta para impressora de cozinha apenas porque os produtos imprimem lá.

==================================================
3. CRIAR ROTEAMENTO CONFIGURÁVEL POR FINALIDADE
===============================================

Criar uma arquitetura genérica equivalente a:

PrintRoute / PrintPolicy

com escopo de FILIAL.

Deve permitir configurar por tipo de documento:

* habilitado/desabilitado;
* manual/automático;
* uma ou mais PrinterDevice;
* número de cópias;
* formato quando aplicável.

Tipos iniciais:

TABLE_BILL
TABLE_CONFERENCE
TABLE_FINAL_RECEIPT
QUICK_SALE_RECEIPT
PAYMENT_RECEIPT
TICKET

Deixar preparado para tipos futuros sem redesenhar a arquitetura:

REPORT
FISCAL_RECEIPT
LABEL
DELIVERY_ORDER
CASH_CLOSING
CASH_OPENING

NÃO precisa implementar os futuros agora.

==================================================
4. UMA FINALIDADE PODE TER VÁRIAS IMPRESSORAS
=============================================

A arquitetura NÃO pode assumir uma impressora única.

Exemplo válido:

TABLE_BILL
→ Impressora Caixa
→ Impressora Recepção

Cada destino físico deve gerar execução separada.

==================================================
5. HERANÇA FILIAL -> DEVICE
===========================

Preservar a estratégia já definida no CORE:

FILIAL
→ configuração padrão

POS DEVICE
→ override opcional

Exemplo:

Filial:

TABLE_BILL
→ Caixa 1

TABLE_CONFERENCE
→ Caixa 1

QUICK_SALE_RECEIPT
→ Caixa 1

POS Recepção:

TABLE_BILL
→ Recepção

Somente essa finalidade deve ser sobrescrita.

Não exigir configuração em 50 POS individualmente.

Criar estrutura compatível com overrides futuros por POSDevice.

==================================================
6. MIGRAR O CONCEITO ANTIGO DE receipt_printer
==============================================

Hoje existem:

BranchPOSSettings:

* receipt_printer
* sale_confirmation_print
* receipt_print_mode
* receipt_format
* paper_width
* copies

POSDeviceSettings:

* mesmos campos / overrides

Não apagar sem análise.

Migrar de forma segura para a nova arquitetura de PrintRoute/PrintPolicy.

Evitar manter duas fontes da verdade conflitantes.

Se campos antigos precisarem permanecer temporariamente por compatibilidade:

* documentar no código;
* fazer a nova arquitetura ser a fonte oficial;
* evitar comportamento ambíguo.

==================================================
7. PRODUTOS — CORRIGIR BUG ATUAL
================================

Hoje existe um bug real.

O frontend chama algo equivalente a:

`http.getAll<PrinterDevice>(
  products/<id>/production-printers/?available=true
)`

Mas `http.getAll()` espera resposta paginada:

{
results: [],
next: null
}

e o endpoint de production-printers devolve ARRAY DIRETO.

Isso faz a tela não listar impressoras mesmo existindo impressora ativa.

CORRIGIR.

Porém NÃO consolidar uma arquitetura errada Produto → Impressora.

A arquitetura oficial deve permanecer:

Produto
→ ProductionDestination
→ PrinterDevice(s)

Portanto na tela de Produto:

preferir configurar:

“Destino / Setor de produção”

Exemplos:

* Cozinha
* Bar
* Copa

e mostrar, como informação derivada:

Cozinha
→ Impressora Cozinha 01
→ Impressora Cozinha Backup

Se houver UI atual chamada “Imprimir em”, ajustar para não esconder a arquitetura real.

A associação persistida deve continuar sendo:

ProductProductionDestination

NÃO criar vínculo direto Product → PrinterDevice como fonte primária.

==================================================
8. IMPRESSÃO DE PRODUÇÃO DA MESA
================================

Preservar o comportamento existente.

Ao tocar ENVIAR PEDIDO:

itens novos confirmados
→ create_table_production_jobs()
→ ProductProductionDestination
→ ProductionDestination
→ PrinterDevice
→ PrintJob
→ CORE POS local
→ TCP

Somente itens novos.

Não reimprimir pedido anterior.

==================================================
9. NOVO PEDIDO NA MESMA MESA
============================

Exemplo:

Mesa 10:

Pedido 1:
2x X-Bacon

já impresso.

Depois:

Pedido 2:
1x Batata

Ao enviar Pedido 2:

imprimir SOMENTE Batata.

Não repetir X-Bacon.

==================================================
10. CANCELAMENTO DE ITEM/PEDIDO DE MESA
=======================================

Preservar lógica existente.

Se item já foi enviado para produção e depois cancelado:

gerar documento/ticket de CANCELAMENTO para as MESMAS impressoras que receberam o original.

NÃO resolver novamente pela configuração atual do produto.

Usar o histórico original.

Exemplo:

******** CANCELAMENTO ********

MESA 10

2x X-BACON

Motivo:
CLIENTE DESISTIU

==================================================
11. SOLICITAR CONTA
===================

Hoje:

set_table_bill_requested()

apenas grava:

bill_requested_at
bill_requested_by

Isso está incompleto.

Ao solicitar conta, quando a rota TABLE_BILL estiver configurada como AUTOMATIC:

1. validar que não existem itens ainda não enviados;
2. persistir bill_requested;
3. gerar snapshot da conta;
4. criar documento imprimível TABLE_BILL;
5. criar PrintJob(s) para as impressoras configuradas;
6. usar o mesmo executor seguro do PrintManager;
7. imprimir automaticamente.

Se TABLE_BILL estiver MANUAL:

solicitar conta deve apenas marcar a solicitação e deixar disponível “IMPRIMIR CONTA”.

Se estiver DISABLED:

não gerar impressão física.

==================================================
12. VISUALIZAR CONFERÊNCIA
==========================

Hoje `_TableConferencePage` já existe.

O conteúdo já mostra:

* mesa;
* horário;
* atendente;
* produtos;
* quantidades;
* modificadores;
* observações;
* resumo financeiro;
* cliente.

Hoje o botão Imprimir é PLACEHOLDER:

“Impressão estará disponível em breve.”

REMOVER O PLACEHOLDER.

O botão deve funcionar de verdade.

Ao entrar em:

VISUALIZAR CONFERÊNCIA

não imprimir automaticamente apenas por abrir a tela.

Deve existir botão:

IMPRIMIR

ou:

REIMPRIMIR

conforme histórico daquele snapshot.

==================================================
13. TABLE_BILL E TABLE_CONFERENCE
=================================

São finalidades diferentes e DEVEM poder apontar para impressoras diferentes.

Exemplo:

TABLE_BILL
→ Impressora 1

TABLE_CONFERENCE
→ Impressora 3

Mesmo que visualmente possam usar layout semelhante.

Não acoplar uma finalidade à outra.

==================================================
14. SNAPSHOT / VERSÃO DO DOCUMENTO
==================================

Impressão de conta/conferência deve possuir identidade de snapshot.

Exemplo:

Mesa estava em R$ 100.
Conferência foi impressa.

Depois foi adicionado R$ 20.

Agora a conferência atual é de R$ 120.

O sistema deve entender:

snapshot antigo
→ já impresso

snapshot novo
→ ainda não impresso

Portanto o botão deve voltar para:

IMPRIMIR

Não:

REIMPRIMIR

Criar uma forma robusta de identificar a versão do documento.

Pode ser:

* hash determinístico;
* version;
* snapshot persistido;
* outra solução sólida.

O snapshot deve considerar pelo menos o que muda o documento:

* itens;
* quantidades;
* status/cancelamentos;
* modificadores;
* observações;
* descontos;
* taxa de serviço;
* cliente;
* subtotal;
* total;
* demais informações financeiras relevantes.

==================================================
15. REGRA IMPRIMIR x REIMPRIMIR
===============================

Primeira execução física de determinado snapshot:

IMPRIMIR

A partir da segunda:

REIMPRIMIR

Reimpressão deve ser explícita.

NÃO tratar retry técnico como reimpressão.

Preservar a regra já adotada:

retry = falha técnica comprovada
reprint = nova cópia solicitada conscientemente

==================================================
16. REIMPRESSÃO DE DOCUMENTOS
=============================

Toda reimpressão deve:

* preservar histórico;
* registrar número da reimpressão;
* registrar quem solicitou;
* registrar quando;
* registrar em qual PrinterDevice;
* deixar claro no papel que é REIMPRESSÃO.

Exemplo:

******** REIMPRESSÃO ********

CONFERÊNCIA
MESA 10

...

Não sobrescrever a impressão original.

==================================================
17. PAGAMENTO PARCIAL NA MESA
=============================

NÃO imprimir automaticamente cada pagamento parcial.

Mas no histórico de pagamentos deve existir opção:

IMPRIMIR COMPROVANTE

Após a primeira impressão:

REIMPRIMIR COMPROVANTE

Usar tipo:

PAYMENT_RECEIPT

Exemplo:

COMPROVANTE DE PAGAMENTO

Mesa 10
Pagamento #...
Forma: PIX
Valor: R$ 50,00
Data/hora
Operador

==================================================
18. ESTORNO DE PAGAMENTO
========================

Não precisa imprimir automaticamente.

Pode disponibilizar comprovante de estorno se o histórico/estrutura atual permitir sem criar gambiarra.

Se implementar:

deve ser documento explícito de ESTORNO.

Não misturar com comprovante original.

==================================================
19. FECHAR MESA
===============

Quando a Mesa for fechada:

close_table_attendance()
→ Sale materializada

NÃO gerar produção novamente.

Isso já é regra crítica existente.

Depois do fechamento:

TABLE_FINAL_RECEIPT

deve ser tratado conforme PrintRoute.

Se AUTOMATIC:

fechou mesa com sucesso
→ gerar recibo
→ enfileirar impressão

Se MANUAL:

tela/retorno deve permitir:

IMPRIMIR RECIBO

Depois:

REIMPRIMIR RECIBO

Se DISABLED:

não imprimir.

==================================================
20. CONFERÊNCIA != RECIBO FINAL
===============================

São documentos diferentes.

CONFERÊNCIA:

antes do pagamento
“CONFERÊNCIA SEM VALOR FISCAL”

RECIBO FINAL:

depois do pagamento
“RECIBO NÃO FISCAL”

Recibo final deve incluir quando disponível:

* itens;
* subtotal;
* descontos;
* taxa;
* total;
* pagamentos;
* formas de pagamento;
* valor recebido;
* troco;
* cliente;
* mesa;
* atendente;
* operador;
* número da venda;
* data/hora.

Imprimir conferência anteriormente NÃO torna o recibo final uma reimpressão.

==================================================
21. VENDA RÁPIDA — PRODUÇÃO
===========================

Preservar comportamento atual.

Produção só nasce quando a venda é FINALIZADA.

Carrinho não imprime.

Abrir pagamento não imprime.

Pagamento parcial não envia para cozinha.

Ao finalizar:

Sale
→ create_sale_production_jobs()
→ produção por setor

==================================================
22. VENDA RÁPIDA — RECIBO
=========================

Hoje QuickSaleCompletedPage mostra apenas:

VENDA CONCLUÍDA
Venda #...
Total
Pedido enviado para produção
NOVA VENDA

Adicionar suporte ao:

QUICK_SALE_RECEIPT

Conforme PrintRoute:

AUTOMATIC:
finalizou venda
→ imprimir recibo automaticamente

MANUAL:
mostrar IMPRIMIR COMPROVANTE

Depois da primeira impressão:
mostrar REIMPRIMIR COMPROVANTE

DISABLED:
não imprimir.

==================================================
23. TICKET / emits_ticket
=========================

Hoje:

product.emits_ticket = true

gera Ticket lógico e a Venda Rápida mostra os números.

Mas isso NÃO significa impressão física.

Implementar rota:

TICKET

Quando um Ticket lógico for emitido:

se PrintRoute TICKET = AUTOMATIC:
→ gerar impressão física

se MANUAL:
→ permitir impressão pelo fluxo apropriado

se DISABLED:
→ manter Ticket lógico sem impressão.

Reimpressão deve funcionar sem criar novo Ticket lógico.

==================================================
24. TRANSPORTE FÍSICO
=====================

Por enquanto executar fisicamente apenas:

PrinterConnectionType.NETWORK

via CORE POS local.

NÃO criar implementação Stone/USB/Bluetooth/Print Agent agora.

Porém PrintRoute NÃO deve conhecer transporte.

Ela aponta para PrinterDevice.

O executor decide futuramente:

NETWORK
STONE_INTEGRATED
USB
BLUETOOTH
PRINT_AGENT

==================================================
25. REUTILIZAR PrintManager
===========================

Não criar um segundo sistema inseguro de socket.

Documentos devem reaproveitar o executor local existente.

Precisamos continuar tendo:

backend
→ PrintJob
→ claim
→ lease
→ dispatch boundary
→ POS
→ socket TCP
→ result
→ reconcile

Adaptar PrintJob de maneira limpa para suportar impressão que não possua ProductionJob.

Hoje PrintJob já permite `production_job=null` em alguns casos como teste.

Criar uma relação/documento apropriado sem abusar de ProductionJob.

Não inventar ProductionJob fake para recibo.

==================================================
26. MODELO DE DOCUMENTO DE IMPRESSÃO
====================================

Criar entidade genérica apropriada, algo equivalente a:

PrintDocument

Campos conceituais:

* company;
* branch;
* document_type;
* source_type;
* source_id/relação explícita quando possível;
* snapshot;
* snapshot_hash/version;
* created_by;
* created_at;
* original_document quando aplicável;
* metadata.

Pode ajustar nomes/modelagem conforme arquitetura do projeto.

A finalidade é:

PrintDocument
→ 1..N PrintJob
→ PrinterDevice(s)

ProductionJob continua sendo domínio de produção.

==================================================
27. PRINTJOB
============

Preservar segurança atual.

PrintJob deve conseguir apontar:

ProductionJob
OU
PrintDocument
OU teste

de maneira validada.

Não permitir origem ambígua.

Adicionar constraint coerente.

Não quebrar histórico existente.

==================================================
28. LAYOUT ESC/POS — CORRIGIR MARGENS
=====================================

Existe problema real na impressora física.

Hoje:

58mm → 32 colunas
80mm → 48 colunas

e o renderer praticamente usa toda a largura.

`_line()` não faz margem segura nem wrap adequado.

Além disso:

large: true

usa double width e pode ultrapassar a área física.

CORRIGIR.

Usar área segura aproximada:

58mm:
28 caracteres normais

80mm:
42 caracteres normais

Large/double width:

58mm:
aprox. 14

80mm:
aprox. 21

Pode ajustar tecnicamente, mas deve existir margem física segura.

==================================================
29. WRAPPING ESC/POS
====================

Implementar wrap real.

Produto longo:

2x X-BACON ARTESANAL ESPECIAL
DA CASA

Modificador:

* ADICIONAL DE QUEIJO
  CHEDDAR ESPECIAL

Observação:

OBS:
CLIENTE PEDIU SEM MOLHO E COM
A CARNE BEM PASSADA

Nenhuma linha deve simplesmente ultrapassar a área imprimível.

==================================================
30. CENTRALIZAÇÃO
=================

Centralizar usando printableWidth seguro.

Não usar largura física teórica.

Aplicar para:

CORE PDV
COZINHA
BAR
MESA
CONFERÊNCIA
CONTA
RECIBO
CANCELAMENTO
REIMPRESSÃO
TESTE DE IMPRESSÃO

==================================================
31. CORTE
=========

Adicionar feed seguro antes do corte.

Não cortar imediatamente depois da última informação.

Deixar espaço razoável sem desperdiçar papel.

==================================================
32. LAYOUT DE CONTA / CONFERÊNCIA
=================================

Modelo aproximado:

```
        NOME DA EMPRESA

         CONFERÊNCIA
      SEM VALOR FISCAL

           MESA 10
```

Data/hora
Atendente

---

2x X-BACON                 50,00

* Bacon extra            6,00

3x HEINEKEN                45,00

---

Subtotal                  101,00
Desconto                    0,00
Taxa de serviço            10,10
TOTAL                     111,10

Cliente: ...

Usar branding/nome existente disponível.

Não inventar dados.

==================================================
33. LAYOUT DE RECIBO
====================

Modelo aproximado:

```
         NOME DA EMPRESA

       RECIBO NÃO FISCAL
```

Venda #123
Mesa 10 / Venda rápida
Data/hora

---

Itens...

---

Subtotal
Desconto
Taxa
TOTAL

PAGAMENTOS

PIX                        50,00
DINHEIRO                   70,00
Recebido                   80,00
Troco                      10,00

Operador:
Cliente:

Se reimpressão:

******** REIMPRESSÃO ********

==================================================
34. LAYOUT DE TICKET
====================

Para product.emits_ticket:

```
         NOME DA EMPRESA

          TICKET #123
```

Produto
Quantidade

Código/validação quando aplicável

Não confundir com ticket de produção.

==================================================
35. PERMISSÕES
==============

Usar RBAC existente.

Não hardcodar autorização no POS.

Criar/reutilizar permissões granulares se necessário para:

* imprimir documento;
* reimprimir documento;
* configurar rotas de impressão.

Evitar criar dezenas de permissões desnecessárias.

Reimpressão deve ser uma ação auditável.

==================================================
36. AUDITORIA
=============

Registrar pelo menos:

* criação do PrintDocument;
* impressão;
* reimpressão;
* alteração de PrintRoute;
* alteração de override por device;
* PrinterDevice utilizado;
* operador/usuário;
* origem;
* document_type;
* snapshot/version;
* reprint_number;
* motivo se a política atual exigir.

Não registrar secrets.

==================================================
37. BACKOFFICE — ROTEAMENTO
===========================

Criar/ajustar UI em Configurações / Impressão para administrar:

TIPO DE DOCUMENTO

Conta da Mesa
Conferência
Recibo Final da Mesa
Recibo Venda Rápida
Comprovante de Pagamento
Ticket

Para cada um:

Modo:

* Desabilitado
* Manual
* Automático

Impressoras:

* multi-select de PrinterDevice ativos da filial

Cópias

Formato quando aplicável

Mostrar claramente a filial ativa.

==================================================
38. DEVICE OVERRIDE
===================

Na configuração de máquina/POS:

permitir herdar regra da filial.

Exemplo visual conceitual:

Conta da Mesa
[ Herdar da filial ]

ou:

[ Sobrescrever ]
→ Impressora Recepção

Não obrigar override.

==================================================
39. IMPRESSORA LOCAL FUTURA
===========================

Não implementar Stone agora.

Mas NÃO criar validações que impeçam no futuro:

PrinterDevice:
connection_type = stone_integrated

PrintRoute:
TABLE_BILL → Stone local

A arquitetura deve aceitar isso futuramente.

==================================================
40. AÇÕES QUE NÃO DEVEM IMPRIMIR AUTOMATICAMENTE
================================================

NÃO imprimir automaticamente ao:

* abrir Mesa;
* adicionar item no carrinho sem enviar;
* editar item antes de enviar;
* abrir catálogo;
* visualizar conferência;
* abrir tela de pagamento;
* registrar pagamento parcial;
* alterar cliente;
* alterar desconto;
* retirar/restaurar taxa;
* transferir item;
* agrupar/separar mesa;
* abrir Venda Rápida;
* adicionar item no carrinho;
* cancelar checkout não finalizado.

==================================================
41. MUDANÇA DE CONTA APÓS IMPRESSÃO
===================================

Se uma conta/conferência foi impressa e depois houve alteração:

* novo item;
* cancelamento;
* desconto;
* taxa;
* cliente;
* outra mudança financeira relevante;

o novo snapshot deve voltar a ser:

IMPRIMIR

Não REIMPRIMIR.

A versão antiga continua no histórico.

==================================================
42. HISTÓRICO
=============

Precisamos conseguir responder:

* qual documento foi impresso;
* quando;
* por quem;
* em qual PrinterDevice;
* quantas vezes;
* quais foram reimpressões;
* qual snapshot estava sendo representado.

Não apagar histórico quando rota/configuração mudar.

==================================================
43. IMPRESSORA ALTERADA DEPOIS
==============================

Exemplo:

Ontem:

TABLE_CONFERENCE
→ Impressora 3

Hoje:

TABLE_CONFERENCE
→ Impressora 7

Histórico antigo deve continuar mostrando Impressora 3.

Nova impressão usa configuração atual.

Não reescrever histórico antigo.

==================================================
44. PRODUTO COM VÁRIOS DESTINOS
===============================

Preservar suporte:

Produto
→ Cozinha
→ Bar

se configurado.

Cada destino cria sua execução normal.

Não limitar produto a somente uma impressora/setor.

==================================================
45. IMPRESSORA COM VÁRIOS DESTINOS
==================================

Preservar também:

Cozinha
→ Printer 1

Bar
→ Printer 1

quando uma loja pequena usa a mesma impressora física.

==================================================
46. NÃO DUPLICAR PRODUÇÃO AO FECHAR MESA
========================================

REGRA CRÍTICA.

TableOrderItem já gerou produção no envio.

Ao fechar Mesa e materializar Sale:

NÃO gerar novamente:

create_sale_production_jobs()

para aqueles itens.

A proteção existente:

confirmed_order_items

deve continuar intacta.

==================================================
47. NÃO MISTURAR TICKET LÓGICO COM PRINTJOB DE PRODUÇÃO
=======================================================

Ticket lógico de `emits_ticket` é uma entidade comercial/validação.

Ticket de produção é outra coisa.

Não misturar.

==================================================
48. ERROS DE IMPRESSÃO DE DOCUMENTOS
====================================

Usar os mesmos estados seguros:

PENDING
PROCESSING
PRINTED
FAILED
UNCERTAIN

FAILED comprovadamente antes do envio:
→ pode permitir retry

UNCERTAIN:
→ NÃO imprimir automaticamente de novo

Usuário pode escolher REIMPRIMIR conscientemente.

==================================================
49. UX DE ERRO
==============

Se impressão automática falhar depois da operação financeira já ter sido concluída:

NÃO desfazer:

* venda;
* pagamento;
* fechamento de Mesa.

A venda continua válida.

Mostrar algo como:

“Venda concluída. Não foi possível confirmar a impressão do recibo.”

e disponibilizar ação segura conforme estado.

Nunca repetir operação financeira só para tentar imprimir.

==================================================
50. TESTE DE IMPRESSORA
=======================

Melhorar ticket de teste para ajudar validação física.

Incluir:

CORE PDV
TESTE DE IMPRESSÃO

Nome da impressora
IP/host
58mm ou 80mm
Data/hora

linha visual respeitando área segura.

Servirá para eu verificar margens manualmente.

==================================================
51. NÃO COMEÇAR BLOCO 3
=======================

NÃO implementar nesta missão:

* SDK Stone;
* impressora integrada Stone;
* Print Agent;
* USB;
* Bluetooth;
* descoberta de impressora;
* Android USB;
* fiscal.

Somente deixar a arquitetura pronta.

==================================================
52. NÃO EXECUTAR TESTES
=======================

REFORÇO:

NÃO execute testes.

NÃO execute analyzer.

NÃO execute build.

NÃO execute lint.

NÃO faça validação automática pesada.

Implemente e pare.

==================================================
CHECKPOINT FINAL
================

Ao terminar, informe EXATAMENTE:

1. migrations criadas;
2. models novos/alterados;
3. como ficou PrintDocument;
4. como ficou PrintRoute/PrintPolicy;
5. como funciona herança filial -> POS;
6. como Produto configura ProductionDestination;
7. como corrigiu o bug da lista vazia de impressoras/produtos;
8. como funciona Enviar Pedido da Mesa;
9. como funciona cancelamento de produção;
10. como funciona Solicitar Conta;
11. como funciona Visualizar Conferência;
12. como funciona IMPRIMIR x REIMPRIMIR;
13. como snapshot/versionamento foi resolvido;
14. como funciona recibo final da Mesa;
15. como funciona recibo da Venda Rápida;
16. como funciona comprovante de pagamento;
17. como funciona ticket de `emits_ticket`;
18. como ficaram as rotas configuráveis;
19. como funciona múltiplas impressoras por finalidade;
20. como ficou o layout ESC/POS 58mm;
21. como ficou o layout ESC/POS 80mm;
22. como ficou word wrapping;
23. como ficou feed/corte;
24. arquivos backend alterados;
25. arquivos frontend alterados;
26. arquivos Flutter alterados;
27. o que ficou explicitamente para o Bloco 3.

NÃO execute testes depois do checkpoint.

DEPOIS PARE.
