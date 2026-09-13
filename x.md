OPENCODE — MESA 1.9.3
FECHAMENTO FINAL DA ETAPA DE PEDIDOS DA MESA
ANTES DE PAGAMENTOS

IMPORTANTE:
A FONTE DA VERDADE É O ESTADO ATUAL DO GITHUB.

HEAD ANALISADO:
8d10281a7bc258688cb3db815aa6b7b3ed6367ae
MESA 1.9.2 FIX

OBJETIVO DESTA MISSÃO:

FECHAR DEFINITIVAMENTE O FLUXO PRÉ-PAGAMENTO DE MESAS.

Depois desta missão vamos revisar o GitHub e testar manualmente.

SOMENTE SE FOR APROVADO:
→ começaremos MESA 2.0 — PAGAMENTOS / DIVISÕES.

NÃO COMEÇAR PAGAMENTOS NESTA MISSÃO.

==================================================
REGRAS CRÍTICAS
==================================================

NÃO modificar:

pos/lib/sales/quick_sale_page.dart

Venda Rápida está aprovada.

NÃO alterar:

- Android
- Gradle
- AGP
- Kotlin
- AndroidManifest
- SDK
- configuração de build Android

NÃO criar testes.

NÃO executar testes manualmente.

NÃO executar builds completos.

NÃO criar:
- execute.md
- gg.md
- qualquer arquivo de prompt/instrução no repositório

Checks leves permitidos:

flutter analyze
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check

==================================================
1. NÃO REGREDIR O QUE O FIX JÁ CORRIGIU
==================================================

O HEAD atual já corrigiu pontos importantes.

PRESERVAR:

- /tables/availability/ agora recebe client_item_id;
- payload de availability separado do payload de saveTableOrder;
- client_item_id estável;
- Mesa livre abre direto;
- Mesa ocupada abre direto;
- catálogo é tela operacional principal;
- SALVAR E ENVIAR não sai mais da Mesa;
- após salvar:
  → refresh TableAttendance
  → limpa draft
  → continua na mesma Mesa;
- tap com modificador opcional adiciona direto;
- obrigatório abre editor;
- long press/lote;
- UNIT bloqueia fração;
- persisted + draft aparecem no resumo;
- backend envia line_total;
- customer/customer_id foi corrigido;
- conferência inicial existe;
- gg.md foi removido.

NÃO refazer isso sem necessidade.

==================================================
2. BLOCKER — ÍNDICE ERRADO DO DRAFT NO RESUMO
==================================================

Existe bug real no código atual.

O resumo monta:

[persistidos]
+
[draft]

Para renderizar o draft está correto:

final item = cart[index - persisted.length];

PORÉM depois chama:

onEdit(index)
onRemove(index)

Isso usa índice GLOBAL.

Exemplo:

4 itens persistidos
1 draft

primeiro draft:
index global = 4

mas no carrinho:

_cart[0]

Ao editar:

_edit(4)
→ _cart[4]
→ RangeError

Ao remover:
pode não remover porque index >= _cart.length.

CORRIGIR.

Dentro da parte do draft:

final draftIndex = index - persisted.length;

usar:

onEdit(draftIndex)
onRemove(draftIndex)

Garantir que:

- editar funciona;
- remover funciona;
- nenhuma ação do draft usa índice dos itens persistidos.

==================================================
3. BARRA INFERIOR — PRECISA MOSTRAR PREÇO
==================================================

Hoje Mesa chama:

MobileCartBar(
    itemCount: _itemCount,
    preview: null,
    showTotal: false,
    actionLabel: 'VER RESUMO',
)

Por isso NÃO aparece preço.

Isso está diferente da experiência aprovada da Venda Rápida.

QUERO PREÇO SEMPRE VISÍVEL NA BARRA INFERIOR.

Exemplo:

R$ 124,30                  VER RESUMO

Quando estiver recalculando:

Atualizando...             VER RESUMO

Depois:

R$ 132,30                  VER RESUMO

==================================================
4. O PREÇO DA BARRA DEVE ATUALIZAR EM TEMPO REAL
==================================================

Atualizar quando:

- adicionar produto;
- tocar várias vezes;
- adicionar em lote;
- alterar quantidade;
- adicionar modificador;
- remover modificador;
- alterar quantidade de modificador;
- editar observação quando isso afetar snapshot;
- remover item;
- mesclar itens;
- salvar/enviar pedido;
- cancelar item confirmado;
- cancelar pedido;
- aplicar desconto;
- remover desconto;
- desconto por item;
- remover/restaurar taxa;
- transferir item quando o total da Mesa mudar.

Não quero:

produto entra
→ barra continua com preço antigo.

==================================================
5. NÃO USAR TOTAL FINANCEIRO FAKE NO FLUTTER
==================================================

IMPORTANTE:

Flutter NÃO deve virar fonte da verdade financeira.

O total da Mesa envolve:

- preço;
- modificadores;
- promoções;
- desconto por item;
- desconto geral;
- taxa;
- produtos que participam ou não da taxa;
- arredondamentos;
- snapshots financeiros.

Portanto:

NÃO simplesmente fazer:

attendance.total + soma local

e considerar isso o total oficial.

==================================================
6. PREVIEW FINANCEIRO DA MESA
==================================================

Precisamos de preview parecido com Venda Rápida, mas usando:

SalesChannel.TABLE

e as regras reais da Mesa.

Primeiro LEIA os serviços existentes.

Reutilizar motor financeiro canônico.

Preferência:

criar/reutilizar um endpoint de PREVIEW sem persistência.

Exemplo conceitual:

POST
/api/v1/pos/table-attendances/<id>/preview/

Payload:

{
    "items": [
        {
            "client_item_id": "...",
            "product": 123,
            "quantity": "2",
            "modifiers": [...],
            "notes": "..."
        }
    ]
}

O endpoint deve considerar:

1. itens CONFIRMADOS já existentes na TableAttendance;
2. draft ainda não enviado;
3. checkout_discount atual;
4. checkout_service_fee_waived atual;
5. service_fee_rate_snapshot;
6. commission_rate_snapshot;
7. promoções/regras canônicas;
8. participação de cada produto na taxa;
9. SalesChannel.TABLE.

Retornar algo equivalente a:

{
    "subtotal": "...",
    "discount_total": "...",
    "service_fee_total": "...",
    "total_due": "...",
    ...
}

SEM:

- criar TableOrder;
- movimentar estoque;
- gerar ticket;
- gerar produção;
- persistir item;
- alterar atendimento.

É SOMENTE PREVIEW.

==================================================
7. NÃO DUPLICAR MOTOR FINANCEIRO
==================================================

NÃO implementar um segundo cálculo financeiro específico para esse endpoint.

Reutilizar:

calculate_table_preview
calculate_order_items_preview
ou serviço canônico equivalente existente.

Se for necessário criar uma camada pequena que converta draft raw → estrutura de preview,
faça isso internamente.

Não persistir objeto temporário só para calcular preview.

==================================================
8. COMPORTAMENTO DA BARRA QUANDO NÃO HÁ DRAFT
==================================================

Se NÃO existem itens novos:

usar o valor oficial atual:

attendance.summary['total_due']

Exemplo:

Mesa já consumiu R$ 184,50

barra:

R$ 184,50                 VER RESUMO

==================================================
9. COMPORTAMENTO DA BARRA QUANDO HÁ DRAFT
==================================================

Quando draft mudar:

→ marcar estado de preview como atualizando;
→ chamar preview backend;
→ receber projected total;
→ atualizar barra.

Exemplo:

Mesa:
R$ 184,50

adicionou:
2x Coca

durante request:

Atualizando...            VER RESUMO

backend responde:

R$ 200,50                 VER RESUMO

==================================================
10. NÃO PISCAR R$ 0,00
==================================================

Enquanto recalcula:

NÃO substituir o valor por:

R$ 0,00

Mostrar:

Atualizando...

ou manter último valor válido acompanhado de indicador.

Se preview falhar:

- manter último valor conhecido;
- mostrar feedback de erro;
- não fingir que o total é zero.

==================================================
11. APÓS SALVAR E ENVIAR
==================================================

Fluxo obrigatório:

draft preview:
R$ 200,50

SALVAR E ENVIAR

→ POST TableOrder
→ refresh TableAttendance
→ summary oficial agora = R$ 200,50
→ limpa draft
→ preview deixa de ser provisório
→ barra continua R$ 200,50

Não pode:

salvar
→ zerar barra
→ esperar próxima navegação.

==================================================
12. BARRA DE MESA NÃO PRECISA USAR QuickSalePreview
==================================================

MobileCartBar atual foi pensado para QuickSalePreview.

NÃO alterar QuickSalePage para acomodar Mesa.

Pode criar:

TableSummaryBar

ou componente equivalente exclusivo da Mesa,

mantendo identidade visual do MobileCartBar aprovado.

Exemplo:

[ carrinho ]   R$ 200,50              VER RESUMO

Opcionalmente:

2 novos • R$ 200,50                   VER RESUMO

Prioridade é:

PREÇO VISÍVEL.

==================================================
13. CONTADOR NÃO PODE SER ENGANOSO
==================================================

Hoje _itemCount conta linhas:

6x Heineken
→ 1

Isso pode ficar estranho como:

1 item

Não quero semântica errada.

Para a Mesa:

priorizar preço.

Pode usar:

R$ 132,30              VER RESUMO

ou:

2 novos • R$ 132,30    VER RESUMO

Não precisa somar unidades de:

- KG
- L
- fracionados

como se fossem peças.

==================================================
14. RESUMO — MENU DE 3 PONTOS COMPLETO
==================================================

Hoje dentro:

RESUMO DA MESA
⋮

existe SOMENTE:

VISUALIZAR CONFERÊNCIA

Isso está incompleto.

O menu do RESUMO deve ser o centro de operações da Mesa.

Adicionar conforme permissões:

⋮
├── CLIENTE
├── DESCONTO
├── REMOVER TAXA / RESTAURAR TAXA
├── VISUALIZAR CONFERÊNCIA
├── SOLICITAR CONTA / CANCELAR SOLICITAÇÃO
├── TRANSFERIR ITENS
├── SEPARAR MESA DO GRUPO
└── demais operações gerais que pertençam à Mesa

NÃO adicionar pagamento ainda.

==================================================
15. CLIENTE NO RESUMO
==================================================

Mover/expor no fluxo operacional novo.

Menu:

CLIENTE

Se não houver:

Nenhum cliente
[ PESQUISAR ]
[ ADICIONAR ]

Se houver:

João da Silva
[ VER ]
[ TROCAR ]
[ REMOVER ]

Respeitar:

tables.set_customer
customers.view
customers.add
customers.change

Backend customer já foi corrigido.
Não quebrar novamente.

==================================================
16. DESCONTO GERAL NO RESUMO
==================================================

Usar endpoint existente:

POST
table-attendances/<id>/checkout-context/

No menu:

DESCONTO

Sem desconto:

[ APLICAR DESCONTO ]

Com desconto:

Desconto atual: R$ XX,XX
[ ALTERAR ]
[ REMOVER ]

Depois:

→ backend recalcula;
→ atualizar attendance;
→ atualizar preview/barra/resumo.

==================================================
17. AUTORIZAÇÃO DE DESCONTO
==================================================

Ainda precisamos do fluxo por autorizador/PIN quando operador não possui:

sales.apply_discount

Não simplesmente esconder a função.

Fluxo:

operador toca DESCONTO
→ não tem permissão
→ escolher autorizador elegível
→ PIN
→ backend valida
→ aplica

NÃO:

- salvar PIN;
- logar PIN;
- confiar só no Flutter.

Reutilizar infraestrutura existente do POS.

==================================================
18. REMOVER / RESTAURAR TAXA
==================================================

Menu:

taxa ativa:
REMOVER TAXA

taxa removida:
RESTAURAR TAXA

Usar:

checkout_service_fee_waived

NÃO alterar:

service_fee_rate_snapshot

Atualizar:

summary
preview
barra inferior.

==================================================
19. AUTORIZAÇÃO PARA TAXA
==================================================

Se operador não tiver:

sales.waive_service_fee

permitir fluxo de autorização por PIN conforme sistema existente.

Backend já suporta autorização no checkout-context.

Conectar UI a isso.

==================================================
20. DESCONTO POR ITEM — AINDA FALTA
==================================================

Essa funcionalidade ainda não existe no HEAD atual.

Implementar ANTES de pagamentos.

Item CONFIRMADO deve permitir ação:

DESCONTO DO ITEM

Persistência precisa ser backend.

NÃO fazer desconto local apenas na UI.

Criar/reutilizar serviço de domínio:

set_table_item_discount(...)

com:

- Mesa OPEN;
- item CONFIRMED;
- autorização sales.apply_item_discount;
- auditoria;
- idempotência;
- bloqueio quando pagamentos tornarem alteração ambígua;
- recalcular summary;
- preservar até Sale final.

==================================================
21. ITEM CONFIRMADO — MENU PRÓPRIO
==================================================

No RESUMO, itens já enviados não podem ser `enabled: false` sem ações.

Adicionar menu discreto:

2x Heineken                       ⋮

Ações conforme estado/permissão:

- CANCELAR ITEM
- TRANSFERIR
- DESCONTO DO ITEM

Não permitir:

EDITAR QUANTIDADE
EDITAR MODIFICADORES
EDITAR OBSERVAÇÃO

de item já confirmado.

Isso exigiria efeitos de estoque/produção/ticket.

==================================================
22. CANCELAR PEDIDO
==================================================

No agrupamento visual do pedido:

PEDIDO #1058                     ⋮

Ação:

CANCELAR PEDIDO

Usar endpoint transacional existente.

Não fazer N requests por item.

Motivo obrigatório.

==================================================
23. TRANSFERIR ITENS
==================================================

Adicionar pelo novo RESUMO.

Selecionar somente:

TableOrderItem CONFIRMED elegível.

NÃO transferir draft.

Backend continua bloqueando:

- outra filial;
- pagamento alocado;
- estados incompatíveis.

Após transferir:

→ refresh attendance;
→ atualizar barra/preço;
→ atualizar resumo.

==================================================
24. SOLICITAR CONTA
==================================================

Colocar no menu do RESUMO.

Sem solicitação:

SOLICITAR CONTA

Com solicitação:

CANCELAR SOLICITAÇÃO

Não fechar a Mesa.

No AppBar principal eu quero limpeza.

Preferência:

<      MESA 12

Sem botões operacionais.

Se quiser indicar conta solicitada, fazer de forma mínima/discreta,
mas NÃO adicionar menu de operações no AppBar.

==================================================
25. SEPARAR MESA AGRUPADA
==================================================

Quando fizer parte de grupo e houver:

tables.merge

menu do resumo pode mostrar:

SEPARAR DO GRUPO

Usar backend existente.

==================================================
26. NÃO USAR TableAttendancePage COMO SEGUNDA CENTRAL
==================================================

Hoje ainda existe uma TableAttendancePage antiga com:

- cliente;
- desconto;
- taxa;
- pedidos;
- cancelamentos;
- transferências;
- NOVO PEDIDO.

Ela não deve continuar sendo necessária para o fluxo normal.

O operador deve conseguir fazer tudo pré-pagamento através de:

TableOrderPage
+
VER RESUMO.

Pode manter TableAttendancePage temporariamente como código legado interno,
mas:

NÃO deve ser rota necessária para executar as operações da Mesa.

Evitar duas centrais operacionais concorrentes.

==================================================
27. CONFERÊNCIA — CORRIGIR ITENS CANCELADOS
==================================================

A conferência existe, porém atualmente itera todos os itens:

for order
  for item

sem filtrar status.

Isso pode exibir item CANCELADO como parte da conta.

CORRIGIR.

Conferência financeira deve usar somente itens ativos/confirmados.

Item cancelado:

NÃO compõe a conta.

Se quiser mostrar histórico cancelado:
mostrar em seção separada claramente como CANCELADO,
sem somar ao valor.

Preferência para cliente:
não mostrar cancelados na conferência padrão.

==================================================
28. CONFERÊNCIA — MELHORAR CONTEÚDO
==================================================

Formato:

CONFERÊNCIA SEM VALOR FISCAL

Mesa 12
Data/Hora
Atendente

2x Hambúrguer              R$ XX,XX
   + Bacon
   + Cheddar
   Obs: sem cebola

1x Coca                    R$ XX,XX

Subtotal                   R$ XX,XX
Descontos                  R$ XX,XX
Taxa                       R$ XX,XX
TOTAL                      R$ XX,XX

Cliente: João

Usar:

TableAttendance
TableOrder
TableOrderItem
table_summary

Valores confirmados = backend.

==================================================
29. BLOQUEAR CONFERÊNCIA COM DRAFT
==================================================

Manter comportamento atual:

se existem itens ainda não enviados:

"Existem itens ainda não enviados. Envie o pedido antes de gerar a conferência."

Isso é mais seguro.

==================================================
30. CORRIGIR TÍTULO DUPLICADO
==================================================

No resumo mobile existe:

Text('Mesa ${_attendance.tableName}')

Se tableName já for:

Mesa 12

resultado:

Mesa Mesa 12

CORRIGIR.

Usar somente:

_attendance.tableName

==================================================
31. APP BAR PRINCIPAL
==================================================

Quero:

<      MESA 12

ou nome real.

Nada de:

"Novo pedido • ..."
"Operações da Mesa"
botões operacionais.

Catálogo é a tela operacional.

==================================================
32. PERSISTIDOS + DRAFT
==================================================

VER RESUMO continua mostrando:

ITENS CONFIRMADOS
+
NOVOS ITENS

Visual simples.

Draft:

- editar;
- remover.

Confirmado:

- cancelar;
- transferir;
- desconto item.

Não misturar os dois conceitos.

==================================================
33. SALVAR E ENVIAR
==================================================

Manter comportamento já corrigido:

SALVAR E ENVIAR
→ envia SOMENTE draft;
→ não reenvia pedidos anteriores;
→ refresh TableAttendance;
→ limpa draft;
→ fica na Mesa;
→ barra atualiza para valor oficial;
→ pode continuar adicionando outro pedido.

==================================================
34. AVAILABILITY
==================================================

Manter correção atual:

Availability:

{
    client_item_id,
    product,
    quantity,
    modifiers,
    notes
}

Save order:

{
    product,
    quantity,
    modifiers,
    notes
}

NÃO remover client_item_id do serializer global.

==================================================
35. NÃO IMPLEMENTAR PAGAMENTOS AINDA
==================================================

PROIBIDO nesta missão:

- pagar valor;
- pagar item;
- pagar saldo;
- dividir pessoas;
- cartão;
- dinheiro;
- PIX;
- Stone;
- Cielo;
- troco;
- estorno de pagamento;
- fechamento da Mesa.

Esta é a última revisão de:

PEDIDOS + OPERAÇÕES PRÉ-PAGAMENTO.

==================================================
36. CHECKLIST FINAL PARA APROVAR ANTES DO MESA 2
==================================================

CATÁLOGO:
[ ] abre direto
[ ] favoritos
[ ] categorias
[ ] fotos
[ ] scanner
[ ] tap simples
[ ] modificador opcional sem popup
[ ] obrigatório com editor
[ ] long press
[ ] estoque TABLE

DRAFT:
[ ] adicionar
[ ] merge
[ ] quantidade
[ ] modificadores
[ ] observação
[ ] remover
[ ] sem bug de índice
[ ] sem race

BARRA INFERIOR:
[ ] preço sempre visível
[ ] preço muda ao adicionar
[ ] preço muda ao editar
[ ] preço muda ao remover
[ ] mostra Atualizando...
[ ] nunca pisca R$0 indevidamente
[ ] usa preview backend
[ ] após salvar usa summary oficial
[ ] VER RESUMO permanece

RESUMO:
[ ] itens confirmados
[ ] draft
[ ] valores
[ ] modificadores
[ ] observações
[ ] total
[ ] menu de 3 pontos completo

CLIENTE:
[ ] pesquisar
[ ] cadastrar
[ ] trocar
[ ] remover
[ ] permissões

FINANCEIRO:
[ ] desconto geral
[ ] remover desconto
[ ] autorização desconto
[ ] remover taxa
[ ] restaurar taxa
[ ] autorização taxa
[ ] desconto por item persistido
[ ] summary backend
[ ] preview backend

OPERAÇÕES:
[ ] cancelar item
[ ] cancelar pedido
[ ] transferir item
[ ] solicitar/cancelar conta
[ ] separar grupo

CONFERÊNCIA:
[ ] somente itens válidos
[ ] cancelados fora da conta
[ ] modificadores
[ ] observações
[ ] valores oficiais
[ ] subtotal
[ ] desconto
[ ] taxa
[ ] total
[ ] não fiscal

NAVEGAÇÃO:
[ ] salvar não sai da Mesa
[ ] voltar com draft pede confirmação
[ ] voltar sem draft retorna lista de Mesas

ESCOPO:
[ ] quick_sale_page.dart NÃO alterado
[ ] Android NÃO alterado
[ ] pagamentos NÃO implementados
[ ] Comandas NÃO alteradas
[ ] nenhum arquivo de prompt criado

==================================================
37. AO FINAL
==================================================

PARE.

NÃO começar MESA 2.

Me entregue checkpoint com:

1. HEAD inicial;
2. arquivos alterados;
3. correção do índice do draft;
4. implementação da barra inferior com preço;
5. origem do total exibido;
6. endpoint/serviço usado para preview;
7. como funciona estado "Atualizando...";
8. comportamento depois de salvar;
9. menu completo do resumo;
10. cliente;
11. desconto geral;
12. autorização desconto;
13. taxa;
14. autorização taxa;
15. desconto por item;
16. cancelamento item;
17. cancelamento pedido;
18. transferência;
19. solicitar conta;
20. separar grupo;
21. conferência;
22. filtro de cancelados na conferência;
23. arquivos antigos/rotas que deixaram de ser necessários;
24. flutter analyze;
25. python manage.py check;
26. makemigrations --check --dry-run;
27. git diff --check;
28. confirmação de que NÃO executou testes manualmente;
29. confirmação de que NÃO executou builds manualmente;
30. confirmação de que NÃO alterou quick_sale_page.dart;
31. confirmação de que NÃO alterou Android/Gradle/Kotlin;
32. confirmação de que NÃO implementou pagamentos.

DEPOIS PARE.

Nós vamos conferir o estado REAL DO GITHUB.

SOMENTE SE ESSA ETAPA FOR APROVADA:
→ iniciaremos MESA 2.0 — PAGAMENTOS E DIVISÕES.