OPENCODE — PADRONIZAÇÃO COMPLETA DO MÓDULO DE MESAS
REUTILIZAR A MESMA UI/UX DA VENDA RÁPIDA

OBJETIVO PRINCIPAL

Quero que TODO o fluxo operacional de MESAS use a MESMA aparência, estrutura visual, componentes e padrões de interação já aprovados em VENDA RÁPIDA.

Não quero apenas "parecido".

Quero REUTILIZAÇÃO real dos componentes visuais quando tecnicamente possível.

A regra de negócio continua sendo a da Mesa.

Ou seja:

MESMA UI/UX
+
REGRAS/BACKEND DE MESA

A Venda Rápida é a referência visual oficial do POS.

==================================================
1. PRINCÍPIO DE ARQUITETURA DE UI
==================================================

Sempre que Venda Rápida e Mesa precisarem representar a mesma coisa visualmente:

- item;
- carrinho/resumo;
- desconto;
- cliente;
- taxa;
- totais;
- menu;
- modal;
- dialog;
- bottom sheet;
- badge;
- botão;
- campo;
- lista;

preferir UM COMPONENTE COMPARTILHADO.

NÃO criar cópias independentes só porque uma tela é Mesa e a outra é Venda Rápida.

Exemplo RUIM:

QuickSaleDiscountDialog
TableDiscountDialog
TableDiscountDialogV2

Exemplo desejado:

SharedDiscountDialog

Venda Rápida:
→ injeta estado/callbacks/regras da Venda Rápida

Mesa:
→ injeta estado/callbacks/regras da Mesa

VISUALMENTE:
→ mesmo componente

REGRAS:
→ permanecem separadas.

==================================================
2. VENDA RÁPIDA É REFERÊNCIA E ESTÁ APROVADA
==================================================

Arquivo principal de referência:

pos/lib/sales/quick_sale_page.dart

A Venda Rápida NÃO deve ser redesenhada.

NÃO modificar comportamento aprovado para adaptar à Mesa.

Se algum componente privado precisar ser extraído para reutilização:

- preservar 100% a aparência atual da Venda Rápida;
- preservar 100% o comportamento atual;
- preservar callbacks;
- preservar regras;
- não causar regressão.

Mesa deve se adaptar ao padrão da Venda Rápida.

NÃO o contrário.

==================================================
3. OBJETIVO VISUAL DO FLUXO DE MESA
==================================================

Hoje o módulo Mesa tem aparência mais administrativa:

- muitos Cards;
- muitos botões;
- vários menus de três pontos;
- checkboxes permanentes;
- ações espalhadas;
- blocos grandes;
- informações técnicas visíveis demais.

Quero aparência operacional de POS.

A experiência deve parecer uma continuação natural da Venda Rápida.

==================================================
4. FLUXO GERAL DE MESA
==================================================

HOME
→ MESAS
→ selecionar Mesa
→ abrir catálogo operacional

Catálogo de Mesa:
→ mesmo padrão visual do catálogo da Venda Rápida

Resumo da Mesa:
→ mesmo padrão visual do Carrinho da Venda Rápida

Modais:
→ mesmos componentes visuais

Menus:
→ mesmo padrão

Itens:
→ mesma apresentação

Totais:
→ mesma apresentação

==================================================
5. TELA DE CATÁLOGO DA MESA
==================================================

O catálogo da Mesa deve reutilizar o mesmo componente do catálogo da Venda Rápida sempre que possível.

Ideal:

ProductCatalogPanel

ou componente compartilhado equivalente.

A Mesa deve continuar passando:

- catálogo de Mesa;
- canal TABLE;
- draft da Mesa;
- callbacks da Mesa.

Mas visualmente deve ser o mesmo.

Manter:

- busca;
- categorias;
- favoritos;
- scanner;
- fotos;
- cards;
- badges de quantidade selecionada;
- long press;
- seleção de produto;
- estados de estoque.

==================================================
6. BADGE DE QUANTIDADE NO PRODUTO
==================================================

Venda Rápida e Mesa devem usar o MESMO componente visual de card/badge.

Badge:

- canto superior direito;
- Primary #3454D1;
- texto branco;
- pequeno;
- proporcional;
- não deslocar layout.

Venda Rápida:
→ quantidade do carrinho atual.

Mesa:
→ quantidade SOMENTE do draft ainda não enviado.

Itens já confirmados na Mesa NÃO entram no badge.

==================================================
7. APPBAR DA MESA
==================================================

A tela operacional deve seguir o padrão enxuto.

Exemplo:

<   MESA 12                                  ⋮

Somente:

- botão voltar;
- nome/número da Mesa;
- um menu geral.

NÃO colocar vários ícones de ações no AppBar.

NÃO colocar:

- solicitar conta separado;
- separar grupo separado;
- refresh separado;
- ações duplicadas.

==================================================
8. UM ÚNICO MENU GERAL DA MESA
==================================================

Usar o MESMO padrão de PopupMenuButton da Venda Rápida.

Preferir componente compartilhado quando aplicável.

Menu geral da Mesa:

- Adicionar cliente
- Alterar cliente
- Remover cliente
- Aplicar desconto
- Alterar desconto
- Remover desconto
- Remover taxa de serviço
- Restaurar taxa
- Visualizar conferência
- Solicitar conta
- Cancelar solicitação de conta
- Transferir itens
- Separar mesa do grupo

Mostrar somente conforme:

- estado da Mesa;
- permissões;
- existência do cliente;
- existência do desconto;
- existência da taxa;
- grupo;
- contexto operacional.

==================================================
9. RESUMO DA MESA = MESMO PADRÃO DO CARRINHO
==================================================

Não quero Cards administrativos.

Usar o MESMO padrão visual do Carrinho da Venda Rápida.

Exemplo:

Redbull Tropical                          R$ 20,00
Qtd. 1

Coca-Cola                                 R$ 16,00
Qtd. 2

+ Limão
Obs: sem gelo


Subtotal                                  R$ 36,00
Promoções                                - R$ 0,00
Descontos por item                       - R$ 0,00
Desconto da mesa                         - R$ 0,00
Taxa de serviço                            R$ 3,60
TOTAL OFICIAL                             R$ 39,60

==================================================
10. COMPONENTE DE ITEM
==================================================

Venda Rápida e Mesa devem compartilhar o mesmo componente base de apresentação de item sempre que possível.

O componente deve receber parâmetros/contexto.

Exemplo conceitual:

SharedCartItemTile(
  name,
  quantity,
  price,
  modifiers,
  notes,
  status?,
  onTap?,
  onLongPress?,
)

Venda Rápida:
→ item do draft.

Mesa:
→ draft ou TableOrderItem confirmado.

Não duplicar layout.

==================================================
11. ITENS CONFIRMADOS DA MESA
==================================================

Mostrar de maneira limpa.

Não mostrar permanentemente:

- CANCELAR ITEM;
- TRANSFERIR ITEM;
- checkbox;
- três pontos;
- botões auxiliares.

Ao tocar/pressionar o item confirmado:

abrir o mesmo padrão de bottom sheet/modal de ação usado pelo POS.

Opções conforme permissão:

- Ver detalhes
- Aplicar desconto no item
- Alterar desconto no item
- Remover desconto no item
- Cancelar item
- Transferir item

==================================================
12. ITEM DO DRAFT
==================================================

Item ainda não enviado deve usar o mesmo componente visual da Venda Rápida.

Ao tocar/pressionar:

- editar quantidade;
- editar modificadores;
- observação;
- desconto do item, quando aplicável;
- remover.

Reutilizar o mesmo modal/editor da Venda Rápida sempre que possível.

NÃO criar editor duplicado para Mesa se o mesmo componente puder receber callbacks/contexto.

==================================================
13. MODAL DE EDIÇÃO DO ITEM
==================================================

Hoje já existem editores separados em partes do código.

Quero revisar isso.

Se SaleItemEditorDialog puder ser usado para Mesa:

→ transformar em componente compartilhado.

Venda Rápida e Mesa devem abrir o MESMO modal visual.

A diferença será apenas:

- origem;
- callbacks;
- permissões;
- persistência;
- backend utilizado.

==================================================
14. DESCONTO GERAL — MESMO MODAL
==================================================

OBRIGATÓRIO:

Mesa deve usar o MESMO componente visual do desconto da Venda Rápida.

Não criar modal "parecido".

Extrair/generalizar o modal existente se necessário.

Modal:

DESCONTO

[R$] [%]

Valor
[          ]

Exibir:

- tipo;
- valor;
- limite;
- validação;
- erro;
- autorização/PIN quando aplicável.

==================================================
15. REGRA DE DESCONTO CONTINUA SENDO DE MESA
==================================================

Visual igual.

Regra NÃO igual.

Venda Rápida:
→ desconto da venda atual.

Mesa:
→ checkout_discount persistente no TableAttendance.

Percentual da Mesa deve permanecer percentual.

Exemplo:

Mesa = R$ 100
Desconto = 10%

→ R$ 10

Entra novo pedido:

Mesa = R$ 200

→ desconto passa a R$ 20.

NÃO congelar o valor em R$ 10.

==================================================
16. DESCONTO POR ITEM
==================================================

Usar o MESMO componente visual de desconto por item da Venda Rápida.

Mesa:

→ chama regras/endpoints de TableOrderItem.

Venda Rápida:

→ mantém fluxo atual.

Visualmente deve ser idêntico.

==================================================
17. AUTORIZAÇÃO/PIN
==================================================

Se o usuário não possuir permissão:

usar o MESMO padrão visual de autorização da Venda Rápida.

Não criar modal de PIN diferente para Mesa.

Pode reutilizar componente visual compartilhado.

A lógica/endpoint de autorização pode ser diferente conforme contexto.

==================================================
18. CLIENTE
==================================================

Mesa e Venda Rápida devem usar o mesmo padrão visual para:

- pesquisar cliente;
- selecionar cliente;
- cadastrar;
- remover;
- trocar;
- exibir cliente selecionado.

Se já existir picker/dialog reutilizável:

generalizar.

Não criar duas experiências visuais diferentes.

==================================================
19. TAXA DE SERVIÇO
==================================================

A ação deve usar o mesmo padrão visual da Venda Rápida:

- remover taxa;
- restaurar taxa;
- autorização se necessário.

Não criar botões separados grandes na Mesa.

Fica no menu geral.

==================================================
20. PEDIDOS ANTERIORES
==================================================

Mesa possui conceito que Venda Rápida não possui:

Pedido #35
Pedido #37
Pedido #40

Isso continua existindo.

Mas deve ser apresentado de forma leve.

Exemplo:

PEDIDO #37
─────────────────
Redbull Tropical              R$ 20,00
Qtd. 1

PEDIDO #35
─────────────────
Coca-Cola                     R$ 16,00
Qtd. 2

Nada de Cards gigantes.

Nada de vários menus visíveis.

==================================================
21. AÇÕES DO PEDIDO
==================================================

Ao pressionar o cabeçalho:

PEDIDO #37

abrir bottom sheet/modal de ações.

Exemplo:

Cancelar pedido

Somente conforme:

- status;
- permissão;
- regras existentes.

Não mostrar botão permanente.

==================================================
22. DRAFT ATUAL
==================================================

Separar visualmente:

PEDIDO ATUAL

dos pedidos confirmados.

Exemplo:

PEDIDO ATUAL
─────────────────
Coca-Cola
Qtd. 2

Batata
Qtd. 1

SALVAR E ENVIAR PEDIDO

Depois de enviar:

- draft limpa;
- pedido vira histórico;
- usuário continua na mesma Mesa.

==================================================
23. BOTÃO PRINCIPAL
==================================================

Usar o mesmo padrão de botão primário da Venda Rápida.

Na Mesa:

SALVAR E ENVIAR PEDIDO

Não iniciar pagamento nesta missão.

Não colocar:

IR PARA PAGAMENTO

ainda.

==================================================
24. TOTAIS
==================================================

Usar o MESMO componente visual dos totais da Venda Rápida.

Se possível:

SharedTotalsPanel

Receber dados por propriedades.

Venda Rápida:
→ QuickSalePreview.

Mesa:
→ Table summary/preview.

Não calcular regra financeira no componente.

Somente apresentar valores vindos do backend.

==================================================
25. CAMPOS FINANCEIROS
==================================================

Na Mesa mostrar, conforme disponíveis:

Subtotal

Promoções

Descontos por item

Desconto da mesa

Taxa de serviço

TOTAL OFICIAL

Quando futuramente pagamentos entrarem:

Pago

Saldo

Mas nesta missão NÃO começar UI de pagamento.

==================================================
26. CONFERÊNCIA
==================================================

Conferência continua sendo função específica de Mesa.

Abrir por menu geral.

Visual deve seguir a mesma linguagem do restante do POS.

Não precisa copiar fluxo de Venda Rápida porque não existe equivalente direto.

Mas:

- mesma tipografia;
- mesmos espaçamentos;
- mesmos botões;
- mesma paleta;
- mesmos componentes base.

==================================================
27. CONTA SOLICITADA
==================================================

Não colocar no AppBar.

Mostrar badge/status discreto no resumo.

Exemplo:

CONTA SOLICITADA

A ação:

Solicitar conta
Cancelar solicitação

fica no menu superior.

==================================================
28. TRANSFERÊNCIA
==================================================

Não mostrar checkbox permanentemente.

Fluxo:

Menu geral
→ Transferir itens
→ entrar em modo seleção

ou:

pressionar item
→ Transferir item

Modo de seleção pode mostrar checkbox temporariamente.

Ao sair do modo:

→ desaparecem.

==================================================
29. SEPARAR GRUPO
==================================================

Não colocar ícone fixo no AppBar.

Fica no menu geral.

Só aparece se:

- Mesa estiver em grupo;
- operador possuir permissão.

==================================================
30. REFRESH
==================================================

Não quero botão de refresh ocupando AppBar.

Se atualização manual ainda for útil:

usar:

pull-to-refresh

ou mecanismo discreto.

Manter consistência com POS.

==================================================
31. COMPONENTES COMPARTILHADOS
==================================================

Antes de implementar, identificar no quick_sale_page.dart quais componentes privados podem ser extraídos.

Possíveis candidatos:

- ProductCatalogPanel
- card do produto
- badge de quantidade
- cart item tile
- cart/resumo
- totals panel
- DiscountDialog
- item discount dialog
- customer picker
- authorization/PIN dialog
- PopupMenu/padrão de menu
- MobileCartBar
- SaleItemEditorDialog

NÃO extrair tudo cegamente.

Extrair quando existir uso real em Mesa e Venda Rápida.

==================================================
32. ONDE COLOCAR COMPONENTES COMPARTILHADOS
==================================================

Organizar em arquivos claros.

Exemplo conceitual:

pos/lib/sales/widgets/
ou
pos/lib/shared/pos/

Não criar arquitetura exagerada.

O objetivo é:

- reutilização;
- manutenção;
- consistência.

==================================================
33. NÃO MISTURAR DOMÍNIO COM UI
==================================================

Componentes compartilhados NÃO podem saber:

"isto é Mesa"
"isto é Venda Rápida"

Preferir receber:

- callbacks;
- modelos de apresentação;
- flags;
- valores.

Exemplo:

onDiscount()
onCustomer()
onRemove()
onEdit()

e não chamar diretamente:

tableApi
quickSaleApi

de dentro do widget compartilhado.

==================================================
34. BACKEND
==================================================

Não alterar backend nesta missão só por causa da padronização visual.

Usar contratos existentes.

Se realmente faltar algum dado necessário:

PARE e relate antes de criar endpoint/serializer.

Não inventar contrato novo silenciosamente.

==================================================
35. REGRAS DE MESA QUE DEVEM PERMANECER
==================================================

Não alterar:

TableAttendance

TableOrder

TableOrderItem

save_table_order()

cancel_table_order()

cancel_table_item()

transfer_table_items()

set_table_checkout_context()

set_table_item_discount()

set_table_bill_requested()

estoque

produção

tickets

auditoria

idempotência

==================================================
36. REGRAS DE VENDA RÁPIDA QUE DEVEM PERMANECER
==================================================

Não alterar comportamento de:

- carrinho;
- preview;
- desconto;
- item discount;
- cliente;
- taxa;
- disponibilidade;
- estoque;
- finalização;
- pagamento;
- venda;
- scanner.

A Venda Rápida apenas pode passar a consumir componentes compartilhados.

==================================================
37. MOBILE / STONE
==================================================

Prioridade visual:

- celular;
- Stone;
- telas compactas.

Evitar:

- textos apertados;
- menus duplicados;
- botões pequenos demais;
- elementos administrativos;
- Card dentro de Card.

Manter área de toque confortável.

==================================================
38. DESKTOP/TABLET
==================================================

Em telas maiores:

pode continuar existir layout lado a lado catálogo + resumo.

Mas usar os MESMOS componentes compartilhados.

Não criar outro design completamente diferente.

==================================================
39. CORES
==================================================

Usar identidade atual do CORE:

Primary:
#3454D1

Primary dark:
#2945B6

Texto:
#283C50

Surface:
#FFFFFF

Muted:
#64748B

Border:
#E2E8F0

Success:
#17C666

Warning:
#FFA21D

Danger:
#EA4D4D

Não inventar nova paleta.

==================================================
40. ALERTAS
==================================================

Manter padrão de feedback já aprovado do POS.

Não criar AlertDialogs genéricos desnecessários se já existir padrão de feedback.

Alertas transitórios:
aproximadamente 5 segundos conforme padrão existente.

==================================================
41. NÃO ALTERAR ANDROID
==================================================

NÃO mexer em:

Gradle
AGP
Kotlin
AndroidManifest
SDK
applicationId
MainActivity

==================================================
42. NÃO COMEÇAR PAGAMENTOS
==================================================

Ainda NÃO implementar pagamento de Mesa.

Primeiro vamos aprovar:

- catálogo;
- draft;
- envio;
- resumo;
- cliente;
- desconto;
- taxa;
- cancelamento;
- transferência;
- conferência;
- conta solicitada.

Depois tratamos pagamento.

==================================================
43. NÃO CRIAR TESTES
==================================================

NÃO criar testes automatizados.

NÃO alterar testes existentes.

NÃO executar testes automatizados.

==================================================
44. NÃO EXECUTAR BUILD COMPLETO
==================================================

NÃO executar:

flutter build

gradle build

APK build

Docker build

build completo.

Permitido:

flutter analyze

git diff --check

==================================================
45. NÃO FAZER REFACTOR GIGANTE SEM NECESSIDADE
==================================================

Quero reutilização, mas não quero uma reescrita total do POS.

Fazer extração incremental e segura.

Priorizar componentes usados de verdade por:

Venda Rápida + Mesa.

==================================================
46. CRITÉRIO DE SUCESSO
==================================================

Ao abrir:

Venda Rápida → Carrinho

e:

Mesa → Resumo

o usuário deve perceber que são partes do MESMO sistema.

Itens:
→ mesma aparência.

Desconto:
→ mesmo modal.

Cliente:
→ mesmo modal.

Taxa:
→ mesmo padrão.

Menu:
→ mesmo padrão.

Totais:
→ mesmo padrão.

Botões:
→ mesmo padrão.

Tipografia:
→ mesma.

Espaçamento:
→ mesmo.

Somente as ações específicas de Mesa devem diferenciar o contexto.

==================================================
47. CHECKPOINT FINAL
==================================================

Ao terminar, PARE.

Informe:

1. arquivos alterados;

2. quais componentes foram extraídos da Venda Rápida para compartilhamento;

3. quais componentes continuam exclusivos da Venda Rápida e por quê;

4. quais componentes continuam exclusivos da Mesa e por quê;

5. confirmação de que o catálogo de Mesa usa o mesmo componente visual da Venda Rápida;

6. confirmação de que cards de produto usam o mesmo componente;

7. confirmação de que badge de quantidade usa o mesmo componente;

8. confirmação de que itens do resumo usam o mesmo componente visual;

9. confirmação de que o modal de edição do item é compartilhado ou explique por que tecnicamente não pôde ser;

10. confirmação de que o modal de desconto geral é o MESMO componente visual;

11. confirmação de que R$ / % é o mesmo componente;

12. confirmação de que desconto por item usa o mesmo componente visual;

13. confirmação de que autorização/PIN usa o mesmo padrão visual;

14. confirmação de que cliente usa o mesmo picker/modal;

15. confirmação de que taxa usa o mesmo padrão;

16. confirmação de que existe somente UM menu geral superior na Mesa;

17. confirmação de que não existem três-pontinhos espalhados nos itens;

18. confirmação de que item confirmado abre ações por toque/press;

19. confirmação de que Pedido abre ações por toque/press;

20. confirmação de que checkboxes de transferência só aparecem em modo de seleção;

21. confirmação de que totais usam componente compartilhado ou mesma estrutura visual;

22. confirmação de que percentual da Mesa continua persistente como percentual;

23. confirmação de que não alterou regras financeiras;

24. confirmação de que não alterou backend;

25. confirmação de que não alterou comportamento da Venda Rápida;

26. confirmação de que não iniciou pagamentos de Mesa;

27. resultado de flutter analyze;

28. resultado de git diff --check;

29. confirmação de que não executou testes;

30. confirmação de que não executou builds completos.

DEPOIS PARE.

IMPORTANTE:

Nós vamos aprovar visualmente no aparelho antes de qualquer nova etapa.

A fonte da verdade é o estado real do projeto.
Não confiar em checkpoint anterior.