OPENCODE — AUDITORIA E PADRONIZAÇÃO COMPLETA DO MÓDULO DE MESAS

IMPORTANTE:

Não fazer correções pontuais somente na tela que estamos vendo.

Quero revisar TODO o módulo de MESAS no Flutter e os contratos backend diretamente relacionados.

A fonte da verdade é o estado REAL atual do projeto.

HEAD analisado anteriormente:
3e226e8b0f77e7a7b576e6e4a3d9eb09c335a6c1

Confirme o HEAD novamente antes de trabalhar.

Não confiar em checkpoint.

==================================================
OBJETIVOS
==================================================

1. padronizar TODOS os números exibidos no módulo de Mesas;
2. dinheiro sempre com 2 casas decimais;
3. quantidade nunca mostrar zeros decimais desnecessários;
4. eliminar textos técnicos/em inglês da UI;
5. encontrar e corrigir telas antigas/inconsistentes dentro do módulo;
6. transformar seleção de itens para transferência em PÁGINA, não modal;
7. preservar a página de destino usando EXATAMENTE SharedTablesGrid;
8. revisar consistência da transferência parcial no backend;
9. não iniciar pagamentos.

==================================================
1. ESCOPO DA AUDITORIA
==================================================

Revisar pelo menos:

pos/lib/attendance/attendance_models.dart

pos/lib/attendance/attendance_pages.dart

pos/lib/attendance/table_attendance_page.dart

pos/lib/attendance/table_summary_widgets.dart

pos/lib/attendance/shared_tables_grid.dart

e componentes compartilhados chamados pelo fluxo de Mesa.

Também revisar no backend somente os pontos diretamente usados por:

- TableAttendance;
- TableOrder;
- TableOrderItem;
- transferência;
- produção/impressão;
- summary/preview.

==================================================
2. REGRA GLOBAL — DINHEIRO
==================================================

Em TODO o módulo de Mesas:

NÃO quero exibição:

0
0.0
10.5
20.1

Para VALORES MONETÁRIOS.

Quero sempre padrão monetário:

0.00
10.50
20.10

ou, quando estiver utilizando formatter monetário do POS:

R$ 0,00
R$ 10,50
R$ 20,10

conforme o componente/contexto atual.

A regra principal:

VALOR MONETÁRIO = SEMPRE 2 CASAS.

==================================================
3. NÃO FORMATAR DINHEIRO MANUALMENTE EM CADA TELA
==================================================

Não espalhar:

toStringAsFixed(2)

por dezenas de widgets.

Centralizar/reutilizar formatter já existente no POS.

Hoje já existe:

formatMoney(...)

Utilizar corretamente.

Se houver contexto onde precisamos apenas:

10.00

sem "R$":

criar/reutilizar helper visual único e claro.

Não alterar precisão armazenada no backend.

É apenas apresentação.

==================================================
4. AUDITAR TODO USO DE VALOR CRU
==================================================

Pesquisar no módulo de Mesas todos os lugares que exibem diretamente:

summary[...]

item.unitPrice

item.lineTotal

table.balance

table.total

checkoutDiscount

payment.amount

receivedAmount

changeAmount

preview[...]

ou qualquer String monetária recebida da API.

Nenhuma String monetária crua deve ir direto para Text() sem formatter adequado.

==================================================
5. REGRA GLOBAL — QUANTIDADE
==================================================

Quantidade NÃO é dinheiro.

Não quero:

1.000
2.000
5.000

Quero:

1
2
5

Se existir quantidade fracionada real:

1.500 → 1.5

2.250 → 2.25

0.750 → 0.75

Preservar no máximo a precisão necessária do domínio.

==================================================
6. USAR UM ÚNICO FORMATTER DE QUANTIDADE
==================================================

Hoje já existe:

_tableQuantityText(...)

que faz boa parte disso.

Generalizar/reutilizar em TODO o fluxo de Mesas.

Não quero:

${item.quantity}

diretamente em UI quando quantity vem como String decimal da API.

Exemplo ERRADO:

Text('${item.quantity}x ${item.productName}')

Exemplo correto conceitual:

Text('${formatQuantity(item.quantity)}x ${item.productName}')

==================================================
7. AUDITAR QUANTIDADES NO MÓDULO INTEIRO
==================================================

Verificar:

- resumo;
- detalhes do item;
- conferência;
- transferência;
- seletor de transferência;
- catálogo;
- badge;
- modificadores;
- telas antigas;
- histórico;
- mensagens;
- quantidade disponível;
- quantidade selecionada.

Todos devem obedecer ao mesmo formatter.

==================================================
8. TEXTOS EM INGLÊS / STATUS TÉCNICOS
==================================================

NENHUM status cru do backend deve aparecer diretamente na UI.

Não quero:

confirmed
CONFIRMED

cancelled
CANCELLED

pending

processing

printed

failed

occupied

free

open

closed

applied

etc.

quando forem exibidos ao operador.

==================================================
9. CENTRALIZAR TRADUÇÕES DE STATUS
==================================================

Criar/reutilizar funções de apresentação.

Exemplo:

confirmed → Confirmado
cancelled → Cancelado
pending → Pendente

printed → Impresso
processing → Impressão em andamento
failed → Falha na impressão

occupied → Ocupada
free → Livre

open → Aberta
closed → Fechada

Não fazer:

status.toUpperCase()

para mostrar código técnico.

==================================================
10. STATUS NORMAIS PODEM NEM SER MOSTRADOS
==================================================

Principalmente no resumo:

não mostrar "Confirmado" se esse é o estado normal.

Mostrar status apenas quando acrescenta informação.

Exemplo:

normal:
2x Coca-Cola       R$ 16,00
✓ Impresso

cancelado:
fundo vermelho claro
2x Coca-Cola       R$ 16,00
CANCELADO

==================================================
11. AUDITAR MENSAGENS DE ERRO E FEEDBACK
==================================================

Revisar também:

SnackBars
dialogs
tooltips
empty states
erros tratados no Flutter

do módulo de Mesas.

Se estiver mostrando:

código técnico
status técnico
mensagem interna em inglês

traduzir/adaptar para linguagem operacional em português.

NÃO traduzir payload/código interno.

Somente UI.

==================================================
12. ENCONTREI UMA TELA ANTIGA NO MESMO MÓDULO
==================================================

Existe ainda:

TableAttendancePage

com UI antiga.

Ela ainda possui coisas como:

Pedido #...
Status: ${order.status.toUpperCase()}
${item.quantity}x ...
${item.status}

e vários Cards/ações antigas.

Isso conflita com a UI nova de TableOrderPage.

==================================================
13. INVESTIGAR SE TableAttendancePage AINDA É USADA
==================================================

Pesquisar TODAS as referências de:

TableAttendancePage

Antes de decidir.

Se NÃO for mais acessível pelo fluxo atual:

remover código morto com segurança.

Se ainda for acessível:

ela deve ser padronizada para não apresentar uma experiência antiga diferente.

NÃO deixar duas UIs concorrentes para a mesma Mesa.

==================================================
14. NÃO REMOVER SEM INVESTIGAR
==================================================

Não apagar TableAttendancePage apenas porque parece antiga.

Primeiro:

- localizar callers;
- rotas;
- imports;
- navegação;
- referências.

Depois decidir:

A) consolidar no fluxo atual;

ou

B) remover se realmente estiver morta.

Relatar no checkpoint.

==================================================
15. COMPONENTES DUPLICADOS ANTIGOS
==================================================

Fazer a mesma auditoria para:

_TableCustomerPicker
_TableCustomerCreate
_TableAttendancePicker
_TableItemTransferPicker antigo
helpers antigos
dialogs antigos

ou quaisquer widgets privados duplicados.

Se foram substituídos por shared:

remover somente quando sem referência.

==================================================
16. TRANSFERÊNCIA — NÃO QUERO MODAL DE ITENS
==================================================

Hoje:

Transferir itens
→ AlertDialog com seleção dos itens e quantidades
→ página de destino

Isso precisa mudar.

Quero:

Transferir itens
→ PÁGINA DE SELEÇÃO DE ITENS
→ PÁGINA DE SELEÇÃO DA MESA
→ confirmação
→ retorno à Mesa.

==================================================
17. NOVA PÁGINA — SELECIONAR ITENS
==================================================

Criar uma página real.

AppBar:

<   TRANSFERIR ITENS

Conteúdo:

Selecionar todos
Desmarcar todos

Lista dos produtos confirmados.

Cada linha:

[checkbox]

Produto

Quantidade disponível

Quantidade a transferir

Exemplo:

☑ Coca-Cola
Disponível: 5

      [-] 3 [+]

☑ Redbull
Disponível: 2

      [-] 2 [+]

==================================================
18. NÃO USAR AlertDialog PARA ESSA ETAPA
==================================================

Remover uso de:

showDialog<List<_TableItemTransferSelection>>

para a seleção principal dos itens.

Usar:

Navigator.push

com página.

A tela precisa respirar em celular/Stone.

==================================================
19. SELECIONAR TODOS
==================================================

Botão:

SELECIONAR TODOS

deve:

- marcar todos os itens elegíveis;
- iniciar quantidade de transferência com a quantidade máxima de cada linha.

Botão:

DESMARCAR TODOS

deve limpar seleção.

==================================================
20. QUANTIDADE DA TRANSFERÊNCIA
==================================================

Quantidade exibida também deve usar formatter global.

Nunca:

5.000

Mostrar:

5

Controle:

[-] quantidade [+]

Se quantidade disponível:

5

permitir:

1, 2, 3, 4, 5

ou decimal se a unidade realmente suportar quantidade decimal.

==================================================
21. CAMPO MANUAL DE QUANTIDADE
==================================================

Se mantiver TextField:

formatar/validar corretamente.

Não deixar o campo ficar visualmente:

1.000

após edição.

Ao perder foco/confirmar:

normalizar.

==================================================
22. BOTÃO CONTINUAR
==================================================

Na parte inferior:

CONTINUAR

Somente habilitado quando existir ao menos um item selecionado com quantidade válida.

==================================================
23. DESTINO CONTINUA SENDO PÁGINA
==================================================

Após CONTINUAR:

abrir:

_TableTransferDestinationPage

ou componente/página equivalente.

Ela já usa:

SharedTablesGrid

MANTER.

==================================================
24. MESMA UI DO HOME DE MESAS
==================================================

TablesPage e seleção de destino devem continuar usando:

SharedTablesGrid
SharedTableCard

Não recriar cards.

Não copiar código.

Não fazer "parecido".

MESMO componente.

==================================================
25. CONFIRMAÇÃO FINAL
==================================================

Depois de selecionar Mesa destino:

pode haver uma confirmação final simples.

Essa confirmação pode ser dialog pequeno porque é apenas CONFIRMAÇÃO.

Exemplo:

TRANSFERIR PARA MESA 12?

3x Coca-Cola
1x Batata

CANCELAR | TRANSFERIR

O que NÃO pode ser modal é o fluxo completo de seleção dos itens.

==================================================
26. ITEM ÚNICO
==================================================

Quando usuário tocar:

item
→ Transferir item

Pode abrir diretamente a PÁGINA de transferência já com aquele item marcado.

Não abrir modal.

A página começa com:

item já selecionado
quantidade padrão = total disponível

e usuário pode ajustar.

==================================================
27. STATUS DE IMPRESSÃO
==================================================

Continuar usando o estado REAL exposto pelo backend.

Hoje print_status vem de:

production_jobs
→ print_jobs

Não inventar.

Mas padronizar todos os labels em português.

==================================================
28. SEM PRINT JOB
==================================================

Hoje:

print_status = null

faz a UI não mostrar nada.

Definir representação operacional coerente.

Por exemplo:

"Não enviado para impressão"

SOMENTE se semanticamente `null` realmente significar que não existe print job.

Confirmar no domínio primeiro.

Não tratar null como erro ou pending sem verificar.

==================================================
29. REVISAR TRANSFERÊNCIA PARCIAL — IMPORTANTE
==================================================

A implementação atual passou a permitir transferência parcial de item confirmado.

Ela:

- reduz quantity do TableOrderItem original;
- cria novo TableOrderItem no destino;
- divide financial_snapshot.

Antes de considerar pronto, auditar TODOS os vínculos do item original.

==================================================
30. VÍNCULOS QUE PRECISAM SER REVISADOS
==================================================

Verificar pelo menos:

StockMovement

ProductionJob

PrintJob

tickets

auditoria

allocations futuras

ou qualquer FK/OneToOne/ManyToMany relacionada ao TableOrderItem.

Problema possível:

item original tinha quantidade 5.

Transfere 3.

original vira quantidade 2.

novo item destino vira quantidade 3.

Mas movimentos/jobs/tickets históricos podem continuar apontando apenas para item original e representar as 5 unidades.

Isso precisa ficar semanticamente consistente.

==================================================
31. NÃO CORRIGIR TRANSFERÊNCIA PARCIAL NO ESCURO
==================================================

Primeiro mapear todas as relações de:

TableOrderItem

e explicar a estratégia.

Se a implementação atual já estiver consistente:
demonstrar por quê.

Se não:
corrigir preservando:

- estoque;
- produção;
- impressão;
- tickets;
- auditoria;
- idempotência;
- financeiro.

Não fazer gambiarra.

==================================================
32. PREÇOS NO RESUMO
==================================================

Manter:

quantidade
produto
valor da linha

Sempre formatado.

Exemplo:

1x Coca-Cola                         R$ 8,00

NUNCA:

1.000x Coca-Cola                     8.0

==================================================
33. TOTAIS
==================================================

Todos:

Subtotal
Promoções
Descontos por item
Desconto da Mesa
Taxa
Total

sempre com formatter monetário.

Não expor:

0.0

em nenhuma hipótese.

==================================================
34. CONFERÊNCIA
==================================================

Aplicar as mesmas regras:

quantidade:
1 e não 1.000

dinheiro:
R$ 10,00 / 10,00 conforme padrão visual

status:
português

não mostrar código técnico.

==================================================
35. MAPA/HOME DE MESAS
==================================================

Revisar:

saldo
total
status
conta solicitada
grupo

Saldo deve sempre ter duas casas monetárias.

Status deve estar em português.

==================================================
36. DETALHE DO ITEM
==================================================

No detalhe:

Quantidade: 1

não:

Quantidade: 1.000

Status traduzido.

Status de impressão traduzido.

Preço, se exibido:
sempre duas casas.

==================================================
37. BACKEND PODE MANTER DECIMAL NORMAL
==================================================

Não alterar banco/model DecimalField apenas para estética.

Exemplo:

backend pode serializar:
"1.000"

Flutter apresenta:
"1"

backend pode serializar:
"10.00"

Flutter apresenta:
"R$ 10,00"

Separar domínio de apresentação.

==================================================
38. NÃO ALTERAR VENDA RÁPIDA
==================================================

Venda Rápida está aprovada.

Não fazer mudanças visuais/funcionais nela por causa desta auditoria.

Helpers realmente genéricos podem ser compartilhados SOMENTE se não causarem regressão.

==================================================
39. NÃO INICIAR PAGAMENTOS
==================================================

Ainda não criar tela de:

pagamento
divisão
formas
saldo parcial
fechamento.

==================================================
40. NÃO ALTERAR ANDROID
==================================================

Não mexer:

Gradle
AGP
Kotlin
AndroidManifest
SDK
MainActivity
applicationId

==================================================
41. SEM TESTES AUTOMATIZADOS
==================================================

NÃO criar testes.

NÃO alterar testes.

NÃO executar testes automatizados.

==================================================
42. SEM BUILD COMPLETO
==================================================

NÃO executar:

flutter build
APK build
Gradle build
Docker build

Permitido:

flutter analyze

python manage.py check

python manage.py makemigrations --check --dry-run
se backend for alterado

git diff --check

==================================================
43. AUDITORIA FINAL OBRIGATÓRIA
==================================================

Antes de terminar, fazer busca no módulo de Mesas por padrões como:

.status
status.toUpperCase
quantity
unitPrice
lineTotal
summary[
balance
total
showDialog
AlertDialog
toStringAsFixed
'0.0'
"0.0"

e revisar cada ocorrência que chega à interface.

Não fazer substituição cega.

Entender contexto de cada ocorrência.

==================================================
44. CRITÉRIO DE SUCESSO VISUAL
==================================================

No módulo de Mesas inteiro:

NUNCA quero ver:

1.000
2.000

para unidades inteiras.

NUNCA quero ver:

0.0
10.5

para dinheiro.

NUNCA quero ver:

confirmed
cancelled
pending
processing
printed
failed
open
closed

como textos técnicos para operador.

==================================================
45. CHECKPOINT
==================================================

Ao terminar, PARE e informe:

1. HEAD trabalhado;

2. todos os arquivos auditados;

3. todos os arquivos alterados;

4. helper único usado para quantidade;

5. exemplos:
   1.000 → 1
   1.500 → 1.5
   2.250 → 2.25;

6. formatter monetário usado;

7. confirmação:
   0.0 → 0.00
   10.5 → 10.50
   onde for valor monetário;

8. todos os status em inglês encontrados na UI;

9. traduções aplicadas;

10. todas as exibições diretas de status removidas;

11. resultado da investigação de TableAttendancePage;

12. se TableAttendancePage foi removida, consolidada ou mantida e por quê;

13. componentes mortos removidos;

14. como ficou a nova página TRANSFERIR ITENS;

15. confirmação de que o seletor de itens não é mais AlertDialog;

16. como funciona selecionar todos;

17. como funciona quantidade parcial;

18. como item único entra nessa página já selecionado;

19. confirmação de que seleção de Mesa destino continua usando SharedTablesGrid;

20. confirmação de que Home Mesas também usa o mesmo SharedTablesGrid;

21. resultado da auditoria da transferência parcial;

22. todas as relações encontradas de TableOrderItem relevantes à transferência;

23. como StockMovement fica correto após transferência parcial;

24. como ProductionJob fica correto;

25. como PrintJob fica correto;

26. como tickets ficam corretos;

27. como auditoria/idempotência ficam corretas;

28. comportamento de print_status null;

29. confirmação de que Conferência usa os mesmos formatters;

30. confirmação de que Resumo usa os mesmos formatters;

31. confirmação de que mapa de Mesas usa os mesmos formatters;

32. confirmação de que não iniciou pagamentos;

33. confirmação de que não alterou Venda Rápida;

34. resultado de flutter analyze;

35. resultado de python manage.py check, se backend mudou;

36. resultado de makemigrations --check --dry-run, se aplicável;

37. resultado de git diff --check;

38. confirmação de que não criou/executou testes;

39. confirmação de que não executou build completo.

DEPOIS PARE.