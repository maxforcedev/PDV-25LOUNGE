```text
OPENCODE — NOVO FLUXO COMPARTILHADO DE PAGAMENTOS DO CORE POS — FASE 1: VENDA RÁPIDA

OBJETIVO

Refazer o fluxo de pagamento da Venda Rápida para se tornar a base compartilhada de pagamentos do CORE POS.

Essa experiência será reutilizada futuramente por:

- Venda Rápida
- Mesas
- Comandas cashless/pós-pagas
- Comandas pré-pagas, reaproveitando os componentes de cobrança, mas com regra de crédito própria

NESTA MISSÃO:
- implementar e integrar PRIMEIRO na Venda Rápida;
- estruturar componentes realmente compartilháveis;
- NÃO integrar em Mesas ainda;
- NÃO criar Comandas ainda.

O estado atual do projeto é a fonte da verdade.

Antes de alterar qualquer coisa:
1. confirme o HEAD atual;
2. inspecione o fluxo atual de checkout/pagamentos da Venda Rápida;
3. inspecione as APIs/backend atuais de:
   - formas de pagamento;
   - caixa;
   - finalização da Venda Rápida;
   - pagamentos;
   - Stone/Cielo/providers, se já existirem;
   - descontos;
   - taxa de serviço;
4. preserve regras financeiras existentes;
5. não invente cálculos no Flutter que já pertencem ao backend.

==================================================
REGRA CENTRAL DO NOVO PAGAMENTO
==================================================

NÃO queremos o modelo:

montar vários pagamentos
→ depois clicar em finalizar
→ só então cobrar todos em sequência.

Queremos:

escolher forma
→ informar o valor
→ cobrar AGORA
→ aprovado
→ registrar AGORA
→ atualizar pago/saldo
→ continuar na mesma tela para o próximo pagamento.

Exemplo:

Conta: R$ 100,00

Cliente 1:
R$ 30,00 no débito
→ cobrar imediatamente
→ aprovado
→ PAGO R$ 30,00
→ FALTA R$ 70,00

Cliente 2:
R$ 20,00 no Pix
→ cobrar imediatamente
→ aprovado
→ PAGO R$ 50,00
→ FALTA R$ 50,00

Cliente 3:
R$ 50,00 no crédito
→ cobrar imediatamente
→ aprovado
→ PAGO R$ 100,00
→ FALTA R$ 0,00

Não criar uma fila de pagamentos pendentes para cobrar depois.

Uma tentativa recusada/cancelada NÃO pode aumentar o valor pago.

==================================================
1. TELA PRINCIPAL DE PAGAMENTO
==================================================

Criar uma experiência de pagamento em tela própria.

Exemplo conceitual:

<  PAGAMENTO — VENDA RÁPIDA                      ⋮

FORMAS DE PAGAMENTO

[ DINHEIRO ] [ CARTÃO ] [ PIX ] [ OUTROS ]

PAGAMENTOS REALIZADOS

✓ Débito
  R$ 30,00
  18:42

✓ Pix
  R$ 20,00
  18:45

RESUMO

Subtotal                         R$ 100,00
Promoções                        -R$ 10,00
Desconto                          R$ 0,00
Taxa                              R$ 9,00

TOTAL                             R$ 99,00
PAGO                              R$ 50,00

FALTA                             R$ 49,00

A informação mais importante durante o recebimento é:

FALTA
R$ xx,xx

Dar destaque visual a ela.

==================================================
2. FORMAS DE PAGAMENTO NO TOPO
==================================================

As formas de pagamento devem ficar FIXAS NA PARTE SUPERIOR da tela.

Elas NÃO devem ser hardcoded.

Usar SOMENTE as formas disponíveis retornadas pela API/configuração da filial/caixa.

REGRA DO GRID:

grid com até 4 opções principais.

Se existirem até 4 grupos relevantes:
→ mostrar os 4 diretamente.

Exemplo:

DINHEIRO | CARTÃO | PIX | VR

Se houver mais de 4 possibilidades:
→ priorizar os grupos principais:

DINHEIRO | CARTÃO | PIX | OUTROS

Mas SOMENTE se cada grupo existir na API.

Exemplo:
se Pix não estiver disponível, NÃO mostrar Pix apenas para preencher espaço.

Não mostrar forma desabilitada.

"OUTROS" deve existir apenas quando houver formas disponíveis que não caibam nas opções principais.

==================================================
3. AGRUPAMENTO DE CARTÃO
==================================================

No topo, Crédito/Débito/VA/VR NÃO precisam ocupar quatro cards separados quando fizer sentido agrupá-los.

Mostrar:

[ CARTÃO ]

Ao tocar em CARTÃO:

abrir seletor com SOMENTE os tipos disponíveis via API:

[ CRÉDITO ]
[ DÉBITO ]
[ VA ]
[ VR ]

Se só houver Crédito e Débito:

[ CRÉDITO ]
[ DÉBITO ]

Não mostrar VA ou VR inexistente.

Não inventar subtipos.

Após escolher, por exemplo:

DÉBITO

abrir entrada de valor em tela grande.

==================================================
4. ENTRADA DE VALOR — TELA GRANDE
==================================================

Dinheiro, Pix, Crédito, Débito, VA, VR e demais formas monetárias devem reutilizar o MESMO componente de entrada de valor.

NÃO usar pequeno AlertDialog para digitação.

Usar página/área de tela cheia preservando o menu superior/AppBar.

Exemplo:

< DÉBITO

FALTA
R$ 190,00

VALOR A PAGAR

        R$ 30,00


[ R$ 5 ] [ R$ 10 ] [ R$ 20 ] [ R$ 50 ]


┌───────┬───────┬───────┐
│   1   │   2   │   3   │
├───────┼───────┼───────┤
│   4   │   5   │   6   │
├───────┼───────┼───────┤
│   7   │   8   │   9   │
├───────┼───────┼───────┤
│  00   │   0   │   ⌫   │
└───────┴───────┴───────┘

[ PAGAR SALDO R$ 190,00 ]

[ COBRAR R$ 30,00 ]

==================================================
5. ATALHOS DE VALOR
==================================================

O teclado numérico deve possuir atalhos fixos:

R$ 5
R$ 10
R$ 20
R$ 50

Ao tocar:
- preencher o valor correspondente;
- permitir editar depois pelo teclado.

Esses atalhos devem ser componentes configuráveis/reutilizáveis, mesmo que inicialmente sejam:

5 / 10 / 20 / 50.

Também ter ação:

PAGAR SALDO R$ xx,xx

que preenche o saldo restante exato.

==================================================
6. DINHEIRO
==================================================

Fluxo:

DINHEIRO
→ entrada de valor em tela grande
→ confirmar
→ registrar pagamento imediatamente
→ atualizar histórico/PAGO/FALTA
→ voltar para a tela principal de pagamento.

Se houver fluxo de "valor recebido/troco" já existente ou suportado pelo backend, preservar.

Não quebrar regra de caixa.

O fluxo deve ficar preparado para:

Valor a pagar: R$ 30,00
Recebido: R$ 50,00
Troco: R$ 20,00

Mas não inventar nova regra financeira se o backend atual não suportar.

==================================================
7. PIX
==================================================

Fluxo:

PIX
→ teclado numérico em tela grande
→ valor
→ CONFIRMAR/COBRAR
→ iniciar cobrança Pix
→ aguardar resultado do provider quando integrado
→ somente após aprovação registrar como pago
→ retornar à tela principal.

==================================================
8. CARTÃO
==================================================

Fluxo:

CARTÃO
→ selecionar subtipo disponível:

Crédito
Débito
VA
VR
etc.

→ teclado numérico em tela grande
→ informar valor
→ cobrar imediatamente
→ aguardar provider/maquininha
→ aprovado = registrar
→ recusado/cancelado = não registrar valor pago
→ voltar para a tela principal.

A integração deve ficar desacoplada da UI.

Não criar UI específica Stone dentro do componente compartilhado.

A camada de pagamento deve trabalhar com provider/capability.

==================================================
9. OUTROS
==================================================

Se houver mais formas retornadas pela API:

OUTROS
→ abrir página/seletor grande
→ mostrar somente formas realmente ativas.

Exemplo possível, APENAS se existirem:

VA
VR
Voucher
Convênio
Cortesia
Outras formas cadastradas

Após selecionar uma forma monetária:
→ reutilizar SharedPaymentNumericEntry.

==================================================
10. PAGAMENTOS REALIZADOS
==================================================

Logo abaixo do grid superior mostrar os pagamentos já EFETIVAMENTE APLICADOS.

Exemplo:

PAGAMENTOS REALIZADOS

✓ Dinheiro
  R$ 30,00
  18:52

✓ Débito
  R$ 50,00
  18:54

✓ Pix
  R$ 20,00
  18:56

Mostrar informações disponíveis e seguras:
- forma;
- valor;
- horário;
- eventualmente operador.

Não mostrar tentativa recusada como pagamento efetuado.

A arquitetura deve permitir futuramente abrir detalhes:
- provider;
- NSU;
- autorização;
- operador;
- estorno;
- itens alocados.

Não precisa implementar tudo isso nesta fase se o backend ainda não disponibilizar.

==================================================
11. RESUMO FINANCEIRO
==================================================

Depois de "Pagamentos realizados", mostrar:

Subtotal
Promoções
Descontos
Taxa de serviço
Total
Pago
Falta

Usar sempre valores oficiais retornados/calculados pelo backend.

Não recalcular regras comerciais complexas no Flutter.

Money sempre no padrão oficial do POS.

==================================================
12. MENU SUPERIOR — AÇÕES FINANCEIRAS
==================================================

As ações de preço/financeiro que foram retiradas do catálogo devem ficar no menu superior da TELA DE PAGAMENTO.

Exemplo:

⋮

Aplicar desconto
Alterar desconto
Remover desconto

Desconto por item
(quando aplicável e permitido)

Isentar taxa de serviço
Restaurar taxa de serviço

Outras ações financeiras já existentes e pertinentes.

IMPORTANTE:

- não devolver essas ações ao catálogo;
- catálogo serve para lançamento de produtos;
- Pagamento concentra ajustes financeiros.

Reutilizar:
- SharedDiscountDialog;
- SharedAuthorizationDialog;
- demais componentes já aprovados.

Não criar modal visual diferente desnecessariamente.

Permissões continuam respeitadas.

==================================================
13. PAGAR POR VALOR / POR ITENS / DIVIDIR IGUAL
==================================================

A arquitetura do pagamento compartilhado deve suportar modos:

POR VALOR
POR ITENS
DIVIDIR IGUAL

Na primeira integração com Venda Rápida, implementar o que for seguro com o domínio atual.

O importante é NÃO acoplar a forma de pagamento ao tipo de divisão.

Conceito:

O QUE ESTOU PAGANDO?
↓
COMO ESTOU PAGANDO?

Exemplo:

POR ITENS
↓
seleciona itens
↓
total selecionado = R$ 20,00
↓
escolhe DINHEIRO / CARTÃO / PIX
↓
cobra imediatamente R$ 20,00.

==================================================
14. PAGAMENTO POR ITENS
==================================================

Exemplo:

Coca lata                 R$ 8,00
Black Label             R$ 200,00
Biscoito                  R$ 12,00

Selecionar apenas:

[x] Biscoito              R$ 12,00

TOTAL SELECIONADO         R$ 12,00

ou:

[x] Coca                  R$ 8,00
[x] Biscoito             R$ 12,00

TOTAL SELECIONADO        R$ 20,00

==================================================
15. QUANTIDADE NO PAGAMENTO POR ITENS
==================================================

Se houver:

5x Coca lata
R$ 8,00 cada

deve ser possível pagar parte da quantidade:

Disponível para pagamento: 5

[-] 2 [+]

Selecionado:
2x Coca
R$ 16,00

Isso é ALOCAÇÃO DE PAGAMENTO.

NÃO dividir fisicamente o TableOrderItem nem criar lógica semelhante à transferência parcial.

Pagamento por quantidade e transferência parcial são problemas diferentes.

==================================================
16. TAXA DE SERVIÇO NO PAGAMENTO POR ITENS
==================================================

REQUISITO IMPORTANTE:

Quando a venda/mesa/comanda possuir taxa de serviço aplicável, o pagamento POR ITENS deve incluir a parcela correta da taxa correspondente aos itens selecionados.

Exemplo simples:

Biscoito                      R$ 12,00
Taxa aplicável: 10%

Selecionou Biscoito para pagar:

Itens                         R$ 12,00
Taxa correspondente            R$ 1,20

TOTAL A PAGAR                 R$ 13,20

IMPORTANTE:
NÃO implementar cálculo ingênuo fixo de "item x 10%" no Flutter.

A taxa oficial, base elegível, descontos, promoções, arredondamentos, itens não elegíveis, isenções e demais regras devem continuar sendo responsabilidade do backend/motor financeiro.

O frontend deve pedir/receber o valor oficial para a seleção de itens.

Se o backend atual NÃO possuir contrato suficiente para calcular uma seleção parcial de itens + taxa corretamente:

PARE nessa parte e informe no checkpoint:
- qual contrato está faltando;
- qual endpoint/model/serviço atual existe;
- qual mudança backend mínima é necessária.

NÃO inventar resultado local.

O mesmo vale para descontos/proporções financeiras associados à seleção.

==================================================
17. POR VALOR NÃO "QUITA" ITENS AUTOMATICAMENTE
==================================================

Regra obrigatória:

Pagamento POR VALOR não deve inventar quais itens foram pagos.

Exemplo:

TOTAL                         R$ 220,00
Pago por itens                 R$ 20,00
Pago por valor                 R$ 30,00

PAGO                           R$ 50,00
FALTA                         R$ 170,00

Somente pagamentos POR ITENS geram alocação explícita em itens.

==================================================
18. DIVIDIR IGUAL
==================================================

Deixar arquitetura preparada para:

SALDO R$ 300,00

DIVIDIR ENTRE
[-] 3 [+]

R$ 100,00 POR PARTE

A cobrança continua sendo imediata:

primeira parte
→ cobra R$ 100
→ aprovado
→ atualiza saldo
→ próxima parte.

Não criar:
Pessoa 1
Pessoa 2
Pessoa 3

como entidades obrigatórias.

Não criar comandas escondidas.

É uma ferramenta de cálculo/alocação de pagamento.

==================================================
19. COMPONENTES COMPARTILHADOS
==================================================

Estruturar para reutilização real.

Exemplo conceitual, adapte aos padrões atuais do projeto:

payments/
  shared_payment_page.dart
  shared_payment_method_grid.dart
  shared_payment_numeric_entry.dart
  shared_payment_history.dart
  shared_payment_summary.dart
  shared_payment_item_selector.dart
  shared_card_type_selector.dart

NÃO é obrigatório usar esses nomes.

Mas a responsabilidade deve ficar separada.

Não criar futuramente:

QuickSalePaymentUI
TablePaymentUI
CommandPaymentUI

com três cópias.

Queremos uma fonte visual compartilhada.

==================================================
20. CONTEXTO DE PAGAMENTO
==================================================

Preparar contrato neutro para o componente saber:

- origem;
- total;
- pago;
- saldo;
- itens elegíveis;
- formas disponíveis;
- capacidades;
- permissões;
- taxa;
- descontos;
- ações disponíveis.

Exemplo conceitual:

PaymentContext

sourceType:
- QUICK_SALE
- TABLE
- COMMAND

Mas NÃO colocar lógica de Mesa/Comanda dentro do widget compartilhado.

Nesta fase só QUICK_SALE será integrado.

==================================================
21. PONTO CRÍTICO — VENDA RÁPIDA ATUAL
==================================================

Audite cuidadosamente o fluxo atual.

Se hoje a Venda Rápida só cria/finaliza a venda quando recebe uma lista completa de payments, isso NÃO atende o novo requisito.

Precisamos permitir:

checkout/venda em andamento
→ pagamento 1 aplicado
→ ainda existe saldo
→ pagamento 2 aplicado
→ ainda existe saldo
→ ...
→ saldo zero
→ finalizar venda.

NÃO faça gambiarra mantendo pagamentos apenas em memória no Flutter se uma cobrança real já ocorreu.

Uma cobrança aprovada precisa ter persistência/idempotência/auditoria compatíveis com o backend.

Antes de alterar o domínio, identifique:
- modelo atual;
- endpoint atual;
- como pagamentos são persistidos;
- quando estoque/venda/tickets são efetivados;
- como evitar cobrança aprovada sem registro da venda;
- como recuperar o fluxo após fechamento/crash do app;
- idempotência.

Se for necessária uma mudança de domínio/backend maior, implemente de forma coerente com a arquitetura existente e relate claramente.

NÃO simular o novo fluxo apenas visualmente.

==================================================
22. ESTADOS DE COBRANÇA
==================================================

O fluxo compartilhado precisa suportar visualmente:

PRONTO
PROCESSANDO
APROVADO
RECUSADO
CANCELADO
ERRO

Textos exibidos ao operador sempre em português.

Exemplo:

Aguardando pagamento na maquininha...

Pagamento aprovado.

Pagamento não aprovado.
Nenhum valor foi registrado.

==================================================
23. CONCORRÊNCIA / DUPLO CLIQUE
==================================================

Enquanto uma cobrança estiver sendo enviada:

- bloquear novo CONFIRMAR;
- impedir duplo envio;
- preservar idempotency key;
- não permitir duas cobranças concorrentes acidentais;
- deixar claro visualmente que está processando.

==================================================
24. VENDA SÓ CONCLUI COM SALDO ZERO
==================================================

Venda Rápida:

saldo > 0
→ permanecer no pagamento.

saldo = 0
→ permitir/concluir finalização da venda conforme regra oficial.

Não permitir finalizar Venda Rápida com saldo devedor, salvo se existir uma regra explícita já suportada para isso.

==================================================
25. NÃO MEXER EM MESAS AGORA
==================================================

Não integrar esse novo Payment Flow em Mesas nesta missão.

Não alterar:
- fluxo operacional de Mesas;
- transferência;
- conferência;
- resumo de Mesa;
- pedidos Mesa.

Apenas desenhar os componentes compartilhados para que Mesa possa usá-los depois.

==================================================
26. NÃO MEXER EM COMANDAS AGORA
==================================================

Não implementar Comanda nesta missão.

Somente deixar arquitetura desacoplada.

==================================================
27. NÃO ALTERAR ANDROID
==================================================

Não tocar em:

- Gradle;
- AGP;
- Kotlin;
- AndroidManifest sem necessidade direta;
- configuração de build Android.

==================================================
28. TESTES / BUILDS
==================================================

NÃO criar testes automatizados.

NÃO alterar testes existentes.

NÃO executar:
- flutter test;
- pytest;
- suíte automatizada;
- flutter build;
- APK;
- Gradle build;
- build completo.

Validações permitidas:

- flutter analyze;
- python manage.py check;
- python manage.py makemigrations --check --dry-run, se backend for alterado;
- git diff --check.

==================================================
29. NÃO FAZER REFACTOR FORA DO ESCOPO
==================================================

Não aproveitar a missão para reestruturar módulos sem relação direta.

Não alterar a Venda Rápida além do necessário para o novo pagamento.

Preservar:
- catálogo aprovado;
- ProductCatalogPanel;
- ProductCard;
- editor compartilhado de item;
- scanner;
- estoque;
- modificadores;
- carrinho;
- visual aprovado fora da área de pagamento.

==================================================
30. CHECKPOINT FINAL OBRIGATÓRIO
==================================================

Ao terminar, informe:

1. HEAD usado.
2. Arquivos alterados.
3. Como funcionava o pagamento antigo da Venda Rápida.
4. Como ficou o novo fluxo imediato.
5. Onde ficaram os componentes compartilhados.
6. Como as formas de pagamento são obtidas da API.
7. Como funciona a regra dos 4 cards.
8. Como CARTÃO agrupa Crédito/Débito/VA/VR.
9. Como OUTROS é montado.
10. Como funciona o teclado numérico.
11. Confirmação dos atalhos R$5 / R$10 / R$20 / R$50.
12. Como funciona PAGAR SALDO.
13. Como Dinheiro funciona.
14. Como Pix funciona.
15. Como Cartão/provider funciona.
16. Como pagamentos aprovados são persistidos imediatamente.
17. Como recusados/cancelados são tratados.
18. Como PAGO/FALTA são recalculados.
19. Como o histórico de pagamentos é exibido.
20. Como descontos/taxa foram movidos para o menu superior do pagamento.
21. Como ficou pagamento POR ITENS.
22. Como quantidade parcial de item é alocada.
23. Como a taxa de serviço é calculada/alocada no pagamento por itens.
24. Se foi necessária mudança de backend para item + taxa.
25. Como POR VALOR permanece sem alocação automática de item.
26. Estado de DIVIDIR IGUAL nesta fase.
27. Como idempotência e duplo clique foram protegidos.
28. Como recuperação após erro/crash funciona quando já houve cobrança aprovada.
29. Confirmação de que Mesas não foi integrada ainda.
30. Confirmação de que Comandas não foi implementada.
31. Resultado do flutter analyze, se executado.
32. Resultado dos checks Django, se executados.
33. Resultado do git diff --check.
34. Confirmação de que nenhum teste automatizado foi criado, alterado ou executado.
35. Confirmação de que nenhum build completo foi executado.
36. Qualquer bloqueio de domínio que ainda precise de decisão nossa.

Depois do checkpoint:

PARE.

Não iniciar integração em Mesas.
Não iniciar Comandas.
Não continuar para outra fase sem aprovação.
```
