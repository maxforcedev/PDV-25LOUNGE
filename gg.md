OPENCODE — MESA 1.9.2
CORREÇÃO URGENTE DE CLIENTE + NOVO FLUXO OPERACIONAL DE MESAS

IMPORTANTE:
A FONTE DA VERDADE É O GITHUB ATUAL.

HEAD ATUAL:
a4c95a196cb552b078329863901f02f4585263ad
MESA 1.9.1

O erro abaixo aconteceu EM EXECUÇÃO REAL.

NÃO CHUTAR.
NÃO tratar checkpoint anterior como fonte da verdade.

NÃO alterar Venda Rápida.
NÃO alterar Android / Gradle / Kotlin.
NÃO executar testes.
NÃO executar builds completos.
NÃO começar pagamentos.

==================================================
1. ERRO REAL — CLIENTE DA MESA RETORNANDO HTTP 500
==================================================

ERRO REAL:

POST
/api/v1/pos/table-attendances/2/customer/

HTTP 500

Traceback:

TypeError:
set_table_customer() missing 1 required keyword-only argument: 'customer_id'

Origem:

POSTableAttendanceCustomerView
→ serializer.validated_data
→ set_table_customer(...)
→ customer_id não chegou

O ESTADO ATUAL DO CÓDIGO CONFIRMA A CAUSA.

FLUTTER ATUAL ENVIA:

{
    "customer": customerId,
    "idempotency_key": "..."
}

BACKEND MESA 1.9.1 ALTEROU O SERIALIZER PARA:

customer_id

Então:

Flutter envia:
customer

Serializer espera:
customer_id

→ campo customer é ignorado
→ validated_data não contém customer_id
→ service exige customer_id
→ HTTP 500

==================================================
2. CORRIGIR O CONTRATO SEM ESPALHAR customer_id NA API
==================================================

Quero o contrato HTTP externo usando:

customer

NÃO customer_id.

Manter:

POST /table-attendances/<id>/customer/

{
    "customer": 123,
    "idempotency_key": "..."
}

Para remover:

{
    "customer": null,
    "idempotency_key": "..."
}

O service interno pode continuar usando:

customer_id

Portanto:

SERIALIZER:
customer

VIEW:
mapear explicitamente

customer_id = serializer.validated_data.get("customer")

SERVICE:

set_table_customer(
    ...,
    customer_id=customer_id,
    ...
)

NÃO fazer:

**serializer.validated_data

quando os nomes do contrato HTTP e do domínio forem diferentes.

==================================================
3. CORRIGIR TAMBÉM ABERTURA DA MESA
==================================================

Existe a mesma inconsistência no fluxo de abrir Mesa.

Flutter atualmente envia:

customer

open_table_attendance() internamente espera:

customer_id

Corrigir da mesma maneira.

Contrato HTTP:

{
    "customer": 123
}

VIEW:

customer_id = validated_data.get("customer")

SERVICE:

open_table_attendance(
    ...,
    customer_id=customer_id
)

Não deixar esse bug latente.

==================================================
4. NOVO FLUXO DE NAVEGAÇÃO DA MESA
==================================================

QUERO ALTERAR A UX OPERACIONAL.

Hoje o fluxo possui tela intermediária parecida com:

MESAS
→ selecionar Mesa
→ TableAttendancePage
→ NOVO PEDIDO
→ catálogo

NÃO quero mais isso.

Novo fluxo:

HOME
→ MESAS
→ selecionar a Mesa
→ ENTRAR DIRETO NO CATÁLOGO DA MESA

IMPORTANTE:

A seleção física da Mesa continua existindo porque precisamos saber qual Mesa
está sendo operada.

O que deve desaparecer do fluxo principal é a tela intermediária
TableAttendancePage antes do catálogo.

Fluxo:

Mesa livre:
selecionar Mesa
→ abrir TableAttendance
→ catálogo imediatamente

Mesa ocupada:
selecionar Mesa
→ recuperar TableAttendance aberto
→ catálogo imediatamente

NÃO pedir:

NOVO PEDIDO

antes de entrar no catálogo.

O catálogo passa a ser a TELA OPERACIONAL PRINCIPAL da Mesa.

==================================================
5. APP BAR DA MESA
==================================================

Na tela operacional da Mesa, menu superior simples.

Quero SOMENTE algo como:

<        MESA 12

ou o nome real cadastrado:

<        VARANDA 03

Não quero no AppBar:

- status ABERTA;
- cliente;
- responsável;
- número de pessoas;
- solicitar conta;
- separar grupo;
- outros botões operacionais.

Essas operações irão para o RESUMO / menu de 3 pontos.

O título deve usar:

tableName

Não mostrar texto desnecessário como:

"Novo pedido • Mesa 12"

A tela não é mais "Novo pedido".

É a operação da:

Mesa 12

==================================================
6. CATÁLOGO CONTINUA COMO VENDA RÁPIDA
==================================================

A área principal deve continuar no padrão aprovado da Venda Rápida:

- pesquisa;
- categorias;
- favoritos;
- fotos;
- scanner;
- produto sem estoque;
- configuração show_out_of_stock_products;
- toque;
- long press;
- modificadores;
- responsividade.

NÃO alterar:

pos/lib/sales/quick_sale_page.dart

Venda Rápida continua congelada.

==================================================
7. CORRIGIR REGRESSÃO DO TAP COM MODIFICADOR OPCIONAL
==================================================

No MESA 1.9.1 existe:

if (product.modifierGroups.isNotEmpty) {
    abrir editor
}

Isso está errado.

Produto possuir modificador OPCIONAL não significa abrir popup no toque.

Usar mesma regra da Venda Rápida:

TAP produto simples:
→ adiciona 1 direto

TAP produto com somente modificadores opcionais:
→ adiciona 1 direto

TAP produto com configuração obrigatória:
→ abre editor

Obrigatório quando existir regra como:

- required;
- minSelections > 0;
- minTotalQuantity > 0;
- requiredQuantity != null.

LONG PRESS continua podendo abrir fluxo de quantidade + modificadores.

NÃO alterar Venda Rápida.

==================================================
8. A MESA NÃO POSSUI MAIS "CARRINHO DE UM PEDIDO"
==================================================

Esse é um ponto importante da nova UX.

Na Mesa, o botão inferior:

VER RESUMO

NÃO deve mostrar somente o draft que ainda não foi enviado.

Quero:

VER RESUMO
→ mostrar TUDO QUE FOI PEDIDO NA MESA

Como se fosse o carrinho da Venda Rápida, porém representando o atendimento inteiro.

Ou seja:

TableAttendance
├── pedidos já enviados
│   ├── Pedido #1041
│   ├── Pedido #1058
│   └── ...
└── itens ainda não enviados / draft atual

O operador deve olhar o RESUMO e entender imediatamente tudo que está na Mesa.

==================================================
9. RESUMO DA MESA — EXPERIÊNCIA
==================================================

Quero visual parecido com carrinho da Venda Rápida.

Exemplo:

MESA 12

2x Heineken                         R$ 20,00

1x Hambúrguer                       R$ 35,00
   + Bacon                          R$ 5,00
   + Cheddar                        R$ 4,00
   Obs: sem cebola

1x Coca-Cola                        R$ 8,00

-------------------------------------------

Subtotal                            R$ 72,00
Descontos                            R$ 0,00
Taxa                                R$ 7,20
TOTAL                               R$ 79,20

Os valores oficiais dos itens JÁ ENVIADOS e do total da Mesa vêm do BACKEND.

Draft ainda não enviado pode ter total provisório para UX.

Não misturar cálculo provisório com financeiro oficial.

==================================================
10. DIFERENCIAR ITEM ENVIADO DE ITEM AINDA NÃO ENVIADO
==================================================

Visualmente deve ser simples, mas internamente precisamos distinguir.

ITEM JÁ ENVIADO:
→ TableOrderItem persistido
→ confirmado
→ estoque já movimentado
→ produção/ticket já gerados

ITEM NOVO:
→ ainda pertence ao draft local
→ ainda NÃO foi enviado

Pode existir indicação discreta:

NOVO

ou seção:

A ENVIAR

Não quero uma UX poluída.

Mas NÃO permitir editar silenciosamente um item já confirmado como se ainda fosse draft.

Item enviado:

→ cancelar
→ aplicar ações permitidas do item
→ transferir

Item não enviado:

→ editar quantidade
→ modificadores
→ observação
→ remover

==================================================
11. BOTÃO INFERIOR
==================================================

No mobile / Stone:

barra inferior sempre no padrão visual aprovado:

[ quantidade / indicador ]        [ VER RESUMO ]

VER RESUMO deve abrir o resumo completo da MESA.

Não apenas o carrinho local.

Se houver draft novo, o resumo também deve mostrar esses itens.

==================================================
12. SALVAR E ENVIAR NOVOS ITENS
==================================================

Dentro do resumo, quando existirem itens NOVOS ainda não enviados:

mostrar:

[ SALVAR E ENVIAR PEDIDO ]

Esse botão envia SOMENTE O DRAFT NOVO.

NÃO reenviar pedidos anteriores.

Fluxo:

Mesa já possui:
Pedido #100
Pedido #101

Operador adiciona:
2x Coca
1x Pizza

VER RESUMO:

mostra:
itens dos pedidos #100/#101
+
2x Coca NOVO
1x Pizza NOVO

SALVAR E ENVIAR

→ cria somente um NOVO TableOrder
→ Coca + Pizza
→ refresh TableAttendance
→ esses itens deixam de ser NOVO
→ aparecem como pedido confirmado

NÃO consolidar/regravar pedidos anteriores.

==================================================
13. RESUMO DEVE SER O CENTRO DE OPERAÇÕES DA MESA
==================================================

No canto superior direito do RESUMO:

⋮

Adicionar menu de três pontos.

Esse menu será o centro das ações gerais da Mesa.

Exemplo:

⋮
├── Cliente
├── Desconto
├── Remover taxa / Restaurar taxa
├── Visualizar conferência
├── Solicitar conta / Cancelar solicitação
├── Transferir itens
├── Separar mesa do grupo (quando aplicável)
└── outras ações gerais que pertençam à Mesa

NÃO colocar pagamentos ainda.

==================================================
14. CLIENTE NO MENU DE 3 PONTOS
==================================================

Opção:

CLIENTE

Ao tocar:

se não houver:
[ PESQUISAR / ADICIONAR CLIENTE ]

se houver:

João da Silva
telefone/documento quando disponível

[ TROCAR ]
[ REMOVER ]

Respeitar:

tables.set_customer
customers.view
customers.add
customers.change

CORRIGIR PRIMEIRO O HTTP 500 descrito nesta missão.

==================================================
15. DESCONTO NO MENU
==================================================

O backend do MESA 1.9.1 já possui:

POST
/table-attendances/<id>/checkout-context/

NÃO criar outro endpoint.

Conectar Flutter a ele.

Opção:

DESCONTO

Quando não há:

[ APLICAR DESCONTO ]

Quando há:

Desconto atual: R$ XX,XX
[ ALTERAR ]
[ REMOVER ]

Backend continua fonte da verdade.

Respeitar:

sales.apply_discount

e autorização por usuário/PIN quando necessário.

==================================================
16. REMOVER / RESTAURAR TAXA
==================================================

No menu de 3 pontos:

se taxa está ativa:

REMOVER TAXA

se checkout_service_fee_waived == true:

RESTAURAR TAXA

Usar o checkout-context já criado.

NÃO alterar:

service_fee_rate_snapshot

NÃO calcular taxa no Flutter.

Resumo sempre usa:

table_summary()

==================================================
17. VISUALIZAR CONFERÊNCIA
==================================================

Adicionar opção:

VISUALIZAR CONFERÊNCIA

Isso deve abrir uma tela/modal que represente a CONTA DA MESA,
como se fosse a conferência/conta impressa para o cliente.

NÃO É NOTA FISCAL.

NÃO É PAGAMENTO.

NÃO É FECHAMENTO.

Exemplo visual:

--------------------------------
CORE / NOME DA LOJA
Mesa 12
13/09/2026 17:10
--------------------------------

2x Heineken              R$ 20,00
1x Hambúrguer            R$ 35,00
   + Bacon                R$ 5,00
1x Coca-Cola              R$ 8,00

--------------------------------
Subtotal                  R$ 68,00
Descontos                  R$ 0,00
Taxa                       R$ 6,80
TOTAL                     R$ 74,80
--------------------------------

Cliente: João
Atendente: Felipe

Conferência sem valor fiscal.

Usar dados OFICIAIS do TableAttendance / table_summary.

A conferência deve considerar SOMENTE itens já enviados/persistidos.

Se houver draft ainda não enviado, pode:

A) mostrar seção claramente como "NÃO ENVIADO"

OU, preferencialmente:

B) informar:
"Existem itens ainda não enviados. Envie o pedido antes de gerar a conferência."

Escolher uma UX segura.

NÃO misturar draft como se já fosse consumo confirmado.

==================================================
18. SOLICITAR CONTA NO MENU
==================================================

Mover a ação operacional para o menu de 3 pontos.

Quando não solicitada:

SOLICITAR CONTA

Quando solicitada:

CANCELAR SOLICITAÇÃO DE CONTA

Preservar backend atual:

request-bill
clear-bill

Na tela do catálogo pode haver apenas uma indicação discreta quando a conta estiver solicitada.

Exemplo:

MESA 12 • CONTA SOLICITADA

Mas o título principal deve continuar limpo.

==================================================
19. TRANSFERIR ITENS
==================================================

A opção geral pode ficar no menu:

TRANSFERIR ITENS

Ao entrar:

mostrar itens CONFIRMADOS elegíveis da Mesa
→ selecionar
→ escolher destino
→ confirmar

Usar backend existente.

Não permitir draft local entrar nessa transferência.

Draft pode ser removido/editado normalmente antes de enviar.

==================================================
20. CANCELAMENTO DE ITEM
==================================================

No resumo, item JÁ ENVIADO pode ter menu próprio:

⋮

com:

CANCELAR ITEM

e, quando fizer sentido:

TRANSFERIR

Não colocar cancelamento de item no menu geral da Mesa.

Motivo obrigatório continua.

Preservar:

cancel_table_item()
→ estoque reverso
→ ticket cancelado
→ ProductionJob CANCEL
→ PrintJob nas impressoras originais

==================================================
21. CANCELAMENTO DE PEDIDO INTEIRO
==================================================

Pode aparecer no agrupamento visual do pedido:

PEDIDO #1058                         ⋮

→ CANCELAR PEDIDO

Preservar arquitetura transacional atual.

Não cancelar enviando N requests pelo Flutter.

==================================================
22. DESCONTO POR ITEM
==================================================

Continua pendente do MESA 1.9.2 anterior.

Implementar corretamente no backend.

Não apenas visualmente.

Deve ser:

TableOrderItem
→ desconto persistido
→ autorização sales.apply_item_discount
→ auditoria
→ idempotência
→ table_summary atualizado
→ preservado na consolidação futura da Sale

Criar serviço de domínio próprio.

Não editar financial_snapshot aleatoriamente em view.

Se exigir migration:
criar migration NOVA.

==================================================
23. ITENS ENVIADOS NÃO DEVEM SER "EDITADOS"
==================================================

Importante:

Depois que SALVAR E ENVIAR ocorreu:

TableOrderItem está CONFIRMED.

Não permitir:

clicar e simplesmente trocar quantidade/modificador/observação
como se ainda fosse carrinho.

Isso quebraria:

- estoque;
- produção;
- ticket;
- financeiro;
- auditoria.

Para item enviado:

ações possíveis devem ser operações de domínio:

- cancelar;
- desconto;
- transferir;
- futuras operações explicitamente definidas.

Para item em draft:

- editar;
- remover;
- quantidade;
- modificadores;
- observação.

==================================================
24. TELA TableAttendancePage ATUAL
==================================================

Hoje TableAttendancePage é uma tela de detalhe/intermediária.

Ela NÃO deve continuar sendo a principal entrada operacional.

Pode:

A) ser absorvida pela nova tela operacional;

OU

B) continuar existindo internamente, mas não ser aberta no fluxo normal.

Preferência:

UMA tela operacional de Mesa que concentre:

- catálogo
- draft atual
- resumo completo
- operações

Evitar:

TableAttendancePage
+
TableOrderPage
+
outra página de resumo

com estados duplicados.

Não quero três telas disputando o mesmo atendimento.

==================================================
25. FONTE ÚNICA DE ESTADO
==================================================

A nova tela operacional deve possuir:

TableAttendance atualizado do backend
+
draft local ainda não enviado

Conceito:

TableAttendance = verdade persistida
draft = intenção ainda não enviada

Resumo:

persistido + draft

Após SALVAR E ENVIAR:

→ backend confirma
→ refresh TableAttendance
→ limpa draft
→ renderiza novamente

Não manter cópia paralela dos pedidos confirmados.

==================================================
26. ABRIR MESA LIVRE
==================================================

Ao selecionar Mesa LIVRE:

→ abrir atendimento
→ entrar diretamente no catálogo

Pode manter modal mínimo de abertura SOMENTE se realmente necessário para:

- número de pessoas;
- responsável;
- observação;
- cliente opcional.

Mas não obrigar informações que não sejam obrigatórias.

Depois de abrir:

→ catálogo imediatamente.

Se não houver nenhum dado obrigatório:

abrir direto.

==================================================
27. MESA OCUPADA
==================================================

Ao selecionar Mesa OCUPADA:

→ NÃO abrir "detalhes"
→ entrar direto na tela operacional catálogo

Carregar:

- TableAttendance atual;
- pedidos existentes;
- summary;
- cliente;
- conta solicitada;
- agrupamento.

Tudo acessível pelo VER RESUMO.

==================================================
28. HOME / VOLTAR
==================================================

Voltar da tela operacional:

→ retorna à lista de Mesas

NÃO fecha atendimento.

NÃO perde pedidos já enviados.

Se houver DRAFT NÃO ENVIADO e usuário tentar voltar:

mostrar confirmação:

"Existem itens ainda não enviados."

[ DESCARTAR ]
[ CONTINUAR PEDIDO ]

Não enviar automaticamente.

==================================================
29. NÃO FECHAR MESA COM SALDO ZERO
==================================================

Preservar regra:

saldo == 0

NÃO fecha automaticamente.

Fechar Mesa será ação explícita no fluxo de pagamento futuro.

Não implementar fechamento agora.

==================================================
30. NÃO IMPLEMENTAR PAGAMENTO
==================================================

NÃO adicionar neste momento:

- pagar por valor;
- pagar por itens;
- dividir pessoas;
- PIX;
- cartão;
- dinheiro;
- Stone;
- Cielo;
- troco;
- fechar Mesa.

Mesmo que o menu de 3 pontos fique pronto.

Pagamento será MESA 2.

==================================================
31. NÃO ALTERAR VENDA RÁPIDA
==================================================

PROIBIDO MODIFICAR:

pos/lib/sales/quick_sale_page.dart

Venda Rápida está aprovada.

A Mesa deve copiar/adaptar o padrão,
não alterar Venda Rápida para atender Mesa.

==================================================
32. NÃO ALTERAR ANDROID
==================================================

NÃO mexer em:

- Gradle;
- Kotlin;
- AGP;
- AndroidManifest;
- SDK;
- build configs Android.

==================================================
33. NÃO EXECUTAR TESTES / BUILDS
==================================================

NÃO executar testes.

NÃO criar testes.

NÃO alterar testes existentes.

NÃO executar:

python manage.py test
pytest
flutter test
npm test

NÃO executar:

flutter build
npm run build
docker build
gradle build

Checks leves permitidos:

flutter analyze

python manage.py check

python manage.py makemigrations --check --dry-run

python -m compileall apps

git diff --check

==================================================
34. CHECKLIST DE ACEITE
==================================================

BUG:
[ ] customer HTTP 500 corrigido
[ ] contrato externo customer
[ ] service recebe customer_id
[ ] abertura com customer também corrigida

NAVEGAÇÃO:
[ ] selecionar Mesa livre → abre atendimento → catálogo
[ ] selecionar Mesa ocupada → catálogo
[ ] sem TableAttendancePage intermediária
[ ] AppBar mostra somente nome/número da Mesa

CATÁLOGO:
[ ] categorias
[ ] favoritos
[ ] fotos
[ ] scanner
[ ] estoque
[ ] tap direto quando não obrigatório
[ ] opcional não abre popup
[ ] obrigatório abre editor
[ ] long press/lote

RESUMO:
[ ] VER RESUMO mostra TUDO que foi pedido na Mesa
[ ] pedidos persistidos
[ ] draft atual
[ ] diferença clara persistido x não enviado
[ ] produto
[ ] quantidade
[ ] modificadores
[ ] observação
[ ] valores
[ ] subtotal/desconto/taxa/total backend

MENU 3 PONTOS:
[ ] cliente
[ ] desconto
[ ] remover/restaurar taxa
[ ] visualizar conferência
[ ] solicitar/cancelar conta
[ ] transferir itens
[ ] separar grupo quando aplicável

CONFERÊNCIA:
[ ] formato de conta/recibo visual
[ ] não fiscal
[ ] somente dados confirmados
[ ] usa valores oficiais backend

PEDIDO:
[ ] SALVAR E ENVIAR envia somente draft novo
[ ] não reenviam pedidos anteriores
[ ] após salvar refresh TableAttendance
[ ] draft é limpo
[ ] estoque/produção/ticket exatamente uma vez

ITEM CONFIRMADO:
[ ] não pode ser editado como draft
[ ] cancelar
[ ] transferir
[ ] desconto item
[ ] operações de domínio

FINANCEIRO:
[ ] checkout-context conectado ao Flutter
[ ] desconto geral
[ ] remover desconto
[ ] remover/restaurar taxa
[ ] autorizações
[ ] desconto por item persistido

ESCOPO:
[ ] Venda Rápida não alterada
[ ] Android não alterado
[ ] pagamentos não implementados
[ ] Comandas não alteradas
[ ] execute.md não recriado

==================================================
35. AO FINAL
==================================================

PARE.

Não começar MESA 2.

Entregar checkpoint contendo:

1. HEAD inicial;
2. arquivos alterados;
3. migrations novas;
4. causa exata e correção do HTTP 500 de customer;
5. contrato final do customer;
6. novo fluxo de navegação;
7. como Mesa livre entra no catálogo;
8. como Mesa ocupada entra no catálogo;
9. estrutura final da tela operacional;
10. comportamento do VER RESUMO;
11. como persisted orders + draft são combinados visualmente;
12. menu de 3 pontos;
13. conferência;
14. cliente;
15. desconto/taxa;
16. desconto por item;
17. solicitar conta;
18. transferência;
19. cancelamentos;
20. resultado de flutter analyze;
21. python manage.py check;
22. makemigrations --check --dry-run;
23. git diff --check;
24. confirmação de que NÃO rodou testes;
25. confirmação de que NÃO rodou builds;
26. confirmação de que quick_sale_page.dart NÃO foi alterado;
27. confirmação de que Android/Gradle/Kotlin NÃO foram alterados;
28. confirmação de que pagamentos NÃO foram implementados.

A conclusão será validada pelo ESTADO REAL DO GITHUB.