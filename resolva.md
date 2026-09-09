HOTFIX POS-4 — FECHAMENTO DO VALIDADOR + UI DE CUPOM + CICLO DA CÂMERA + RELATÓRIO + BARCODE NO VENDA RÁPIDA

Leia novamente a seção POS-4 do arquivo local `missao.md` antes de alterar qualquer código.

IMPORTANTE:

- NÃO alterar `missao.md`.
- NÃO adicionar `missao.md` ao Git.
- NÃO avançar para POS-5.
- NÃO iniciar POS-6.
- NÃO implementar impressão física agora.
- NÃO reimplementar o scanner, pois a câmera real já está funcionando.
- NÃO trocar a biblioteca de scanner sem motivo técnico real.
- NÃO reescrever backend de Ticket sem necessidade.
- Trabalhar incrementalmente sobre o POS-4 já implementado.
- Preservar tudo que já está funcionando.

O scanner REAL já está funcionando.

Os problemas/pendências atuais são:

1. a UI solicitada de Ticket/Cupom ainda NÃO foi implementada corretamente;
2. depois de escanear uma vez, a câmera não volta para a próxima validação sem sair para o menu;
3. no Home o Validador de Ticket ainda aparece como "Em breve";
4. números de Ticket precisam ter apresentação mínima de 4 dígitos;
5. status precisam aparecer em PT-BR;
6. quantidades como 1.000 precisam aparecer como 1;
7. precisamos garantir experiência adequada de Ticket USED/CANCELLED/PARTIALLY_USED;
8. precisamos de relatório operacional de Tickets no Backoffice;
9. aproveitar esta rodada para adicionar busca por código de barras no Venda Rápida.

==================================================
1. BUG — CÂMERA NÃO REABRE
==================================================

Cenário atual:

1. abre Validador de Ticket;
2. câmera aparece;
3. escaneia QR;
4. Ticket é localizado;
5. operador valida;
6. toca para validar outro Ticket / volta ao estado inicial;
7. a área da câmera NÃO aparece ou scanner não volta a funcionar.

Se sair pelo menu e entrar novamente:
→ câmera volta.

Isso prova que a inicialização funciona, mas o lifecycle/reset interno da página está errado.

NÃO resolver recriando a rota inteira.

O mesmo módulo precisa suportar:

scan
→ consultar
→ confirmar
→ sucesso
→ NOVO SCAN
→ consultar
→ confirmar
→ sucesso

quantas vezes forem necessárias.

==================================================
2. STATE MACHINE DO VALIDADOR
==================================================

Revisar o estado atual da página.

Quero estados conceituais claros:

SCANNING
LOOKING_UP
REVIEWING
VALIDATING
SUCCESS
ERROR

Fluxo:

SCANNING
↓ QR detectado
pausa câmera
↓
LOOKING_UP
↓
REVIEWING
↓ confirmação
VALIDATING
↓
SUCCESS
↓
[ VALIDAR OUTRO TICKET ]
↓
RESET COMPLETO
↓
SCANNING
↓
CÂMERA ATIVA NOVAMENTE

Não deixar múltiplos booleans criarem combinações impossíveis.

Não é obrigatório criar enum se a arquitetura atual não justificar, mas o comportamento precisa seguir esse fluxo.

==================================================
3. AO LER UM QR
==================================================

Quando detectar código:

- bloquear novas leituras temporariamente;
- pausar scanner/câmera;
- manter o validation_code lido;
- realizar SOMENTE lookup;
- abrir Ticket para revisão.

A câmera NÃO deve consumir/validar Ticket automaticamente.

Fluxo obrigatório:

QR detectado
→ lookup
→ mostrar Ticket
→ operador confere
→ operador escolhe quantidade
→ operador confirma
→ validate

Isso já está funcionando em parte.

PRESERVAR.

==================================================
4. AO TOCAR "VALIDAR OUTRO TICKET"
==================================================

Esse botão precisa executar RESET COMPLETO da operação anterior.

Limpar:

- Ticket carregado;
- resultado do lookup;
- mensagem de sucesso;
- mensagem de erro anterior;
- quantidade selecionada;
- manual input;
- validation_code anterior;
- contexto scan/manual;
- flags de processing;
- flags de lookup;
- flags de validating;
- debounce/trava de leitura;
- resultado da operação anterior.

Idempotência:

Se a operação foi CONFIRMADA com sucesso:
→ limpar idempotency key anterior.

Depois:

→ mudar para SCANNING;
→ garantir scanner/câmera ativo novamente;
→ preview da câmera aparece.

IMPORTANTE:

- não exigir Navigator.pop + push;
- não exigir voltar ao Home;
- não recriar AppController inteiro;
- não destruir sessão do operador.

==================================================
5. REINICIAR O SCANNER DE VERDADE
==================================================

Verificar o controller da biblioteca atualmente instalada.

Provavelmente existe algum:

stop/pause

após a primeira leitura, mas não está ocorrendo:

start/resume

quando o fluxo volta para SCANNING.

Corrigir de acordo com a API REAL da versão instalada.

NÃO inventar método.

Ao entrar em SCANNING:

- scanner iniciado;
- preview visível;
- leitura habilitada.

Ao sair de SCANNING para REVIEWING:

- pausar/stop temporariamente;
- impedir duplicidade de leitura.

Ao voltar para SCANNING:

- start/resume novamente.

Ao sair definitivamente da página:

- dispose correto.

==================================================
6. NÃO CRIAR CONTROLLERS A CADA REBUILD
==================================================

Não fazer:

build()
→ cria novo scanner controller
→ rebuild
→ perde controller anterior

O controller deve ter lifecycle estável.

Dispose somente quando a página for realmente destruída.

==================================================
7. TRATAR TODOS OS CAMINHOS DE RETORNO À CÂMERA
==================================================

Testar:

A)
QR válido
→ consulta
→ cancelar/voltar
→ câmera volta.

B)
QR inexistente
→ erro
→ tentar novamente
→ câmera volta.

C)
erro de rede
→ tentar novamente
→ câmera utilizável.

D)
Ticket USED
→ visualizar
→ validar outro
→ câmera volta.

E)
Ticket CANCELLED
→ visualizar
→ validar outro
→ câmera volta.

F)
Ticket PARTIALLY_USED
→ entrega
→ sucesso
→ validar outro
→ câmera volta.

G)
Ticket ISSUED
→ entrega
→ sucesso
→ validar outro
→ câmera volta.

NENHUM desses fluxos pode exigir sair pelo menu.

==================================================
8. HOME — REMOVER "EM BREVE"
==================================================

Hoje o módulo:

Validador de Ticket

já está funcional, mas o card continua mostrando:

"Em breve"

Isso está errado.

Trocar por algo operacional.

Sugestão:

Validador de Ticket
"Escaneie e registre retiradas"

ou:

Validador de Ticket
"Leitura e entrega de tickets"

NÃO mostrar "Em breve" em módulo implementado.

==================================================
9. UI SOLICITADA NÃO FOI FEITA
==================================================

A UI atual continua parecendo formulário/card administrativo.

ISSO NÃO ATENDE AO PEDIDO.

Não quero somente:

- mudar cor;
- alterar padding;
- arredondar Card;
- trocar fonte;
- mudar label.

Quero ALTERAÇÃO VISUAL REAL.

A apresentação do Ticket precisa parecer um CUPOM/TICKET DE RETIRADA.

==================================================
10. NOVA UI — TELA DO SCANNER
==================================================

Tela inicial conceitual:

             CORE PDV
        VALIDAR TICKET

┌────────────────────────────┐
│                            │
│                            │
│       PREVIEW CÂMERA       │
│                            │
│          ┌──────┐          │
│          │      │          │
│          └──────┘          │
│                            │
│   Aponte para o QR Code    │
│                            │
└────────────────────────────┘

          ou digite

[ Número do ticket          ]

[ BUSCAR TICKET ]

A câmera deve ser o elemento principal da página.

Entrada manual continua sendo fallback obrigatório.

==================================================
11. NOVA UI — TICKET COMO CUPOM
==================================================

Depois do scan:

- pausar/esconder câmera;
- mostrar o Ticket;
- Ticket precisa ter aparência de CUPOM.

Exemplo conceitual:

        ┌───────────────────────┐
        │       CORE PDV        │
        │  TICKET DE RETIRADA   │
        │                       │
        │        #0048          │
        │       ● VÁLIDO        │
        │                       │
        │ - - - - - - - - - - │
        │                       │
        │ HEINEKEN LONG NECK    │
        │                       │
        │ Adicionais            │
        │ • Limão               │
        │ • Sem gelo            │
        │                       │
        │ Observação            │
        │ Entregar no bar       │
        │                       │
        │ - - - - - - - - - - │
        │                       │
        │ Emitido          5    │
        │ Já retirado      1    │
        │ Restante         4    │
        │                       │
        │ - - - - - - - - - - │
        │                       │
        │ QUANTO ENTREGAR?      │
        │                       │
        │ [ − ]    1    [ + ]   │
        │                       │
        │ [    ENTREGAR 1    ]  │
        │                       │
        │ [ ENTREGAR TODAS 4 ]  │
        └───────────────────────┘

Características:

- superfície branca;
- fundo externo Canvas CORE;
- largura limitada;
- visual vertical;
- divisórias tracejadas/pontilhadas;
- sombra discreta;
- cara de comprovante/ticket;
- número grande;
- status evidente;
- produto bem legível;
- modifiers;
- observação;
- quantidades;
- ações touch grandes.

NÃO fazer Card administrativo genérico.

==================================================
12. NÚMERO DO TICKET — MÍNIMO 4 DÍGITOS
==================================================

Ticket.number continua sendo numérico no banco.

NÃO transformar em string.
NÃO renumerar históricos.
NÃO alterar sequência.

Apenas apresentação visual.

Exemplos:

1 → #0001
9 → #0009
48 → #0048
999 → #0999
1000 → #1000
15234 → #15234

Mínimo visual:

4 dígitos.

Maior que 4 continua normalmente.

Busca manual:

0001

deve conseguir localizar Ticket.number = 1.

Aplicar em:

- POS;
- Backoffice;
- relatório;
- detalhe do Ticket.

==================================================
13. STATUS EM PT-BR
==================================================

Valores internos continuam:

ISSUED
PARTIALLY_USED
USED
CANCELLED

NÃO mudar enum/database por motivo visual.

Apresentação:

ISSUED
→ VÁLIDO

PARTIALLY_USED
→ PARCIALMENTE USADO

USED
→ USADO

CANCELLED
→ CANCELADO

Nunca mostrar:

USED
PARTIALLY_USED

na interface do operador.

==================================================
14. FORMATAÇÃO HUMANA DE QUANTIDADE
==================================================

Hoje aparecem valores como:

1.000

Quero:

1

Regras:

1.000 → 1
2.000 → 2
5.000 → 5
1.500 → 1,5
0.250 → 0,25
10.125 → 10,125

Remover zeros inúteis sem perder precisão.

Essa é formatação de APRESENTAÇÃO.

Backend/API continuam podendo trabalhar com Decimal canônico.

Aplicar em:

- Emitido;
- Já retirado;
- Restante;
- Cancelado;
- Entregue agora;
- relatório Backoffice;
- detalhe de Ticket.

==================================================
15. SELETOR DE QUANTIDADE
==================================================

Não usar TextField livre como principal UX.

Usar:

[ - ]    1    [ + ]

Regras:

mínimo permitido
≤ quantidade
≤ remaining

Não permitir selecionar acima do remaining.

Quando houver mais de uma unidade restante:

[ ENTREGAR TODAS AS 4 ]

Backend continua revalidando tudo.

IMPORTANTE:

Não quebrar suporte técnico a quantidade fracionária se o domínio permitir.

==================================================
16. TELA DE SUCESSO
==================================================

Depois de uma retirada bem-sucedida, mostrar feedback explícito.

Exemplo:

┌────────────────────────────┐
│             ✓              │
│                            │
│     ENTREGA REGISTRADA     │
│                            │
│        TICKET #0048        │
│                            │
│ HEINEKEN LONG NECK         │
│                            │
│ Entregue agora       1     │
│ Total retirado       2     │
│ Restante             3     │
│                            │
│ [ VALIDAR OUTRO TICKET ]   │
└────────────────────────────┘

Se consumiu tudo:

✓ TICKET TOTALMENTE UTILIZADO

Entregue agora: 3
Total retirado: 5
Restante: 0

[ VALIDAR OUTRO TICKET ]

Esse botão DEVE:

resetar operação
+
reativar câmera.

==================================================
17. TICKET USED
==================================================

Mostrar:

TICKET #0048
USADO

HEINEKEN LONG NECK

Emitido:      5
Já retirado:  5
Restante:     0

Este ticket já foi totalmente utilizado.

[ VALIDAR OUTRO TICKET ]

Não mostrar botão de entrega.

==================================================
18. TICKET CANCELLED
==================================================

Usar corretamente a quantidade cancelada/não retirada.

Exemplo:

Venda/Ticket:
emitido = 5
retirado antes do cancelamento = 1
cancelado = 4

Mostrar:

TICKET #0048
CANCELADO

HEINEKEN LONG NECK

Emitido:      5
Já retirado:  1
Cancelado:    4

Este ticket não pode mais ser utilizado.

[ VALIDAR OUTRO TICKET ]

Não mostrar somente:

Restante: 0

porque isso esconde o fato de que 4 unidades foram canceladas.

Preservar TicketRedemptions anteriores.

==================================================
19. RESPONSIVIDADE
==================================================

STONE / MOBILE:

- usar quase toda largura útil;
- SafeArea;
- sem overflow;
- botões grandes;
- câmera adequada;
- cupom rolável quando necessário;
- ação sempre alcançável.

TABLET / DESKTOP:

- conteúdo centralizado;
- largura limitada;
- não esticar Ticket pela tela inteira;
- scanner com tamanho racional.

==================================================
20. RELATÓRIO DE TICKETS NO BACKOFFICE
==================================================

Adicionar relatório operacional REAL de Tickets no Backoffice.

NÃO criar domínio paralelo.

Fonte da verdade:

Ticket
TicketRedemption

Reutilizar serviços/endpoints/serializers existentes quando possível.

Página:

RELATÓRIOS
→ TICKETS

ou localização equivalente coerente com a navegação existente.

Permissão:

tickets.view

Não exigir tickets.validate apenas para consultar relatório.

==================================================
21. FILTROS DO RELATÓRIO
==================================================

Filtros server-side:

- período;
- número do Ticket;
- status;
- produto;
- operador que retirou;
- dispositivo;
- origem;
- método de validação.

Origem:

Venda
Comanda

Método:

Scanner
Manual

Atalhos:

Todos
Emitidos
Parcialmente usados
Usados
Cancelados
Validados

Validados = Ticket com pelo menos um TicketRedemption.

Não carregar banco inteiro no frontend.

==================================================
22. RESUMO DO RELATÓRIO
==================================================

Para os filtros atuais, mostrar:

- Tickets emitidos;
- Tickets validados;
- Tickets parcialmente usados;
- Tickets totalmente usados;
- Unidades emitidas;
- Unidades retiradas;
- Unidades ainda disponíveis;
- Unidades canceladas sem retirada.

É relatório OPERACIONAL.

Não misturar faturamento.

==================================================
23. TABELA DO RELATÓRIO
==================================================

Colunas sugeridas:

Ticket
Produto
Emitido
Retirado
Restante
Status
Origem
Última retirada
Operador
Dispositivo

Exemplo:

#0048
Heineken Long Neck
5
2
3
PARCIALMENTE USADO
Venda #00125
09/09/2026 22:31
João
Stone Bar 01

Quantidades formatadas humanamente.

Nunca mostrar:

2.000

quando é:

2.

==================================================
24. DETALHE DO TICKET
==================================================

Ao abrir Ticket:

TICKET #0048

Produto
Status
Emitido
Retirado
Restante
Data de emissão
Origem
Modifiers
Observação

HISTÓRICO DE RETIRADAS

22:10
João
Stone Bar 01
Scanner
Quantidade: 1

22:31
Carlos
Stone Bar 02
Scanner
Quantidade: 2

Mostrar também cancelamento quando houver.

Não exibir idempotency_key crua ao usuário comum.

==================================================
25. PERFORMANCE DO RELATÓRIO
==================================================

Evitar N+1.

Usar:

- select_related;
- Prefetch quando necessário;
- annotate;
- Sum;
- paginação server-side;
- filtros no banco.

Não fazer:

Ticket.objects.all()
→ mandar tudo
→ filtrar em JavaScript.

==================================================
26. SEGURANÇA DO RELATÓRIO
==================================================

Empresa e filial devem continuar dentro do contexto autorizado.

Não permitir company/branch arbitrária ignorando membership.

`tickets.view`
→ visualiza.

`tickets.validate`
→ entrega mercadoria.

São responsabilidades diferentes.

Não expor validation_code na listagem geral sem necessidade.

O código do QR é um identificador operacional sensível e não precisa aparecer no relatório.

==================================================
27. VENDA RÁPIDA — BUSCA POR CÓDIGO DE BARRAS
==================================================

Aproveitar esta rodada para adicionar uma melhoria pequena e isolada no módulo VENDA RÁPIDA.

Hoje a busca precisa localizar produto também pelo CÓDIGO DE BARRAS.

NÃO redesenhar Venda Rápida.
NÃO alterar regras financeiras.
NÃO mexer em pagamentos.
NÃO alterar preview/finalização.
NÃO criar domínio paralelo.

Apenas ampliar a busca existente.

==================================================
28. CAMPO DE BUSCA DO VENDA RÁPIDA
==================================================

O campo precisa aceitar:

- nome;
- código interno;
- código de barras.

Exemplos:

HEINEKEN
→ nome.

1234
→ código interno.

7891234567890
→ barcode.

Placeholder:

"Produto, código ou código de barras"

ou equivalente curto.

==================================================
29. MATCH EXATO DE BARCODE TEM PRIORIDADE
==================================================

Se a entrada corresponder EXATAMENTE ao barcode de um produto disponível:

→ priorizar esse produto.

Exemplo:

Heineken Long Neck
barcode = 7891234567890

Busca:

7891234567890

→ localizar Heineken Long Neck imediatamente.

==================================================
30. LEITOR DE CÓDIGO DE BARRAS COMO TECLADO
==================================================

Também suportar leitor físico HID/teclado.

Fluxo:

leitor envia:
7891234567890
+
Enter

→ Venda Rápida processa o barcode.

Não criar integração específica com marca de leitor.

==================================================
31. BARCODE EXATO + ENTER = ADICIONAR AO CARRINHO
==================================================

Para operação rápida de PDV:

barcode exato
+
Enter

→ produto identificado
→ adicionar 1 unidade ao carrinho.

Exemplo:

scan 7891234567890
→ Heineken +1

scan novamente:
→ quantidade 2

scan novamente:
→ quantidade 3

Isso deve acontecer SOMENTE para match exato e único de barcode.

==================================================
32. NÃO ADICIONAR ENQUANTO USUÁRIO ESTÁ DIGITANDO
==================================================

Não fazer:

usuário digita:

7
78
789
7891

e algum match parcial adiciona produto sozinho.

Busca textual continua mostrando resultados.

Auto-add apenas com confirmação adequada, preferencialmente:

barcode exato + Enter.

==================================================
33. REGRAS DO CATÁLOGO CONTINUAM VALENDO
==================================================

Barcode NÃO ignora regras existentes.

Produto ainda precisa respeitar:

- empresa;
- filial;
- device;
- ativo;
- não arquivado;
- ProductBranchConfig;
- disponibilidade;
- canal COUNTER/Venda Rápida;
- categoria;
- estoque;
- show_out_of_stock;
- allow_negative_stock;
- regras já existentes.

Barcode NÃO é bypass.

==================================================
34. PRODUTO SEM ESTOQUE
==================================================

Se barcode localizar produto que não pode ser vendido:

NÃO adicionar silenciosamente.

Mostrar a mesma mensagem amigável da Venda Rápida.

Exemplo:

HEINEKEN LONG NECK

Sem estoque disponível.

Não criar semântica nova de estoque para barcode.

==================================================
35. BARCODE INEXISTENTE
==================================================

Se barcode não existir:

mostrar:

"Produto não encontrado para este código de barras."

Depois manter o caixa pronto para próximo scan.

Não deixar loading infinito.

==================================================
36. BARCODE DUPLICADO
==================================================

Revisar regra atual de unicidade.

Se houver dois produtos válidos com mesmo barcode:

NÃO escolher aleatoriamente.

Não auto-adicionar.

Retornar erro operacional/candidatos conforme arquitetura existente.

Não criar migration de unicidade sem antes revisar o domínio atual.

==================================================
37. PERFORMANCE DA BUSCA POR BARCODE
==================================================

Não fazer:

baixar catálogo inteiro
→ procurar barcode no Flutter.

Busca exata deve ser resolvida de forma eficiente.

Preferência:

backend/query indexada.

Para barcode exato confirmado por Enter, não esperar debounce textual desnecessário.

==================================================
38. NÃO CONFUNDIR OS DOIS SCANNERS
==================================================

VALIDADOR DE TICKET:

QR
→ validation_code
→ Ticket
→ TicketRedemption.

VENDA RÁPIDA:

código de barras comercial
→ Product.barcode
→ Product
→ carrinho.

NÃO misturar endpoints.
NÃO misturar identifiers.
NÃO usar Ticket validation_code como Product barcode.

==================================================
39. NÃO REGREDIR O QUE JÁ FUNCIONA
==================================================

Já funciona:

- câmera real;
- leitura QR;
- lookup;
- validate;
- TicketRedemption;
- venda rápida;
- catálogo;
- carrinho;
- preview;
- finalização;
- pagamentos.

NÃO reescrever esses núcleos.

Essa rodada é:

A. lifecycle da câmera;
B. UI Ticket/Cupom;
C. apresentação;
D. relatório Backoffice;
E. busca por barcode no Venda Rápida.

==================================================
40. TESTE MANUAL OBRIGATÓRIO — CÂMERA
==================================================

SEM SAIR DO MÓDULO:

1. abrir Validador;
2. câmera aparece;
3. escanear Ticket A;
4. validar;
5. sucesso;
6. clicar VALIDAR OUTRO TICKET;
7. câmera aparece novamente;
8. escanear Ticket B;
9. validar;
10. clicar VALIDAR OUTRO TICKET;
11. câmera aparece novamente;
12. escanear Ticket C.

Fazer pelo menos 3 scans consecutivos.

Se precisar voltar ao menu:

BUG NÃO RESOLVIDO.

==================================================
41. TESTES DO VENDA RÁPIDA / BARCODE
==================================================

Validar:

1. busca por nome continua funcionando;

2. código interno continua funcionando;

3. barcode exato encontra produto;

4. barcode inexistente retorna mensagem amigável;

5. barcode + Enter funciona;

6. barcode exato único adiciona +1;

7. segundo scan do mesmo barcode aumenta quantidade;

8. produto sem disponibilidade não entra;

9. produto arquivado não entra;

10. produto inativo não entra;

11. produto de outra filial não entra;

12. estoque zero continua respeitando as regras;

13. busca parcial não auto-adiciona produto por engano.

==================================================
42. TESTES DO RELATÓRIO
==================================================

Validar:

- paginação;
- filtro de período;
- filtro de status;
- busca por Ticket;
- filtro de produto;
- filtro de operador;
- filtro de device;
- Validados;
- resumo;
- Ticket com múltiplos redemptions;
- Ticket PARTIALLY_USED;
- USED;
- CANCELLED;
- empresa/filial;
- permission tickets.view;
- sem N+1 óbvio.

==================================================
43. GATES FOCADOS
==================================================

Após as alterações:

- python manage.py check;
- makemigrations --check;
- testes focados afetados;
- testes POS-4;
- testes relatório;
- testes barcode;
- dart analyze;
- Flutter tests focados;
- git diff --check.

Como a câmera já está funcional, NÃO trocar dependência ou fazer mudanças grandes desnecessárias.

==================================================
44. NÃO IMPLEMENTAR AGORA
==================================================

NÃO implementar:

- impressão física;
- POS-6;
- Stone pagamento;
- POS-7;
- POS-5;
- Mesas/Comandas Flutter;
- refund;
- devolução;
- fiscal;
- offline de Ticket;
- Print Agent.

==================================================
45. CHECKPOINT FINAL
==================================================

Ao terminar, informar:

1. causa raiz da câmera não retornar;
2. como o controller passou a ser retomado;
3. confirmação de 3 scans consecutivos sem sair do módulo;
4. arquivos alterados;
5. confirmação de que a UI antiga foi substituída pelo Ticket/Cupom;
6. descrição da nova UI;
7. Home sem "Em breve";
8. padrão #0001;
9. status em PT-BR;
10. quantidade sem .000 inútil;
11. comportamento USED;
12. comportamento CANCELLED;
13. comportamento PARTIALLY_USED;
14. relatório de Tickets criado;
15. filtros do relatório;
16. resumo do relatório;
17. detalhe e ledger;
18. permissões do relatório;
19. como a busca por barcode foi integrada;
20. comportamento barcode + Enter;
21. confirmação de scans repetidos adicionando quantidade;
22. confirmação de que regras de estoque/disponibilidade continuam válidas;
23. testes executados;
24. migrations criadas, se houver;
25. confirmação de que backend de Ticket não foi reescrito sem necessidade;
26. confirmação de que missao.md não entrou no Git;
27. confirmação de que POS-5/POS-6/POS-7 não foram iniciados.

Somente quando tudo acima estiver concluído, escrever:

"POS-4 concluído e pronto para auditoria."

PARE.