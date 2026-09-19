ALTERE A UI/UX DA TELA DE PAGAMENTO DA VENDA RÁPIDA DO CORE POS.

PARTA DO HEAD ATUAL.

IMPORTANTE: ESTA MISSÃO É PRINCIPALMENTE DE UI/UX E NAVEGAÇÃO.

NÃO alterar a lógica financeira já existente.

NÃO alterar:

* idempotência;
* ledger de pagamentos;
* estornos;
* recovery financeiro;
* regras de pagamento;
* backend financeiro;
* Stone;
* Cielo;
* PagBank;
* Mesa/Comanda;
* estoque;
* impressão.

A ideia é REORGANIZAR a interface existente, reutilizando o motor atual.

==================================================

1. OBJETIVO PRINCIPAL
   ==================================================

A tela de pagamento atual exige rolagem vertical para encontrar:

* formas de pagamento;
* pagamentos realizados;
* total;
* saldo restante;
* finalizar.

ISSO NÃO É BOM PARA UM POS.

Quero uma tela de pagamento OPERACIONAL, FIXA e COMPACTA.

Na utilização normal, tudo importante deve estar disponível SEM PRECISAR DESCER O DEDO.

A referência conceitual é:

```text
┌──────────────────────────────────┐
│ ← PAGAMENTO      Cliente Dividir ⋮│
├──────────────────────────────────┤
│                                  │
│             FALTA                │
│           R$ 33,00               │
│                                  │
├────────────────┬─────────────────┤
│    DINHEIRO    │     DÉBITO      │
├────────────────┼─────────────────┤
│      PIX       │     CRÉDITO     │
├──────────────────────────────────┤
│ PAGAMENTOS REALIZADOS            │
│ ✓ Dinheiro             R$ 10,00  │
│ ✓ Pix                  R$ 15,00  │
├──────────────────────────────────┤
│ TOTAL                 R$ 47,00   │
│ PAGO                  R$ 25,00   │
│ FALTA                 R$ 22,00   │
├──────────────────────────────────┤
│       [ FINALIZAR VENDA ]        │
└──────────────────────────────────┘
```

NÃO copie literalmente esse desenho.

Adapte para a identidade visual atual do CORE POS.

==================================================
2. TELA NÃO DEVE DEPENDER DE SCROLL VERTICAL
============================================

A tela principal de pagamento deve ser montada pensando principalmente em:

* Stone/POS Android;
* celulares;
* tablets pequenos;
* uso rápido no balcão.

No estado normal, NÃO deve ser necessário usar `ListView` vertical para acessar as funções principais.

Priorizar:

* `Column`;
* áreas com tamanhos controlados;
* `Expanded`;
* `Flexible`;
* layout responsivo;
* footer fixo.

Se houver conteúdo excepcionalmente grande, como muitos pagamentos realizados, somente a SUBÁREA correspondente poderá possuir scroll interno.

A PÁGINA INTEIRA não deve ficar rolando.

==================================================
3. HEADER COMPACTO
==================

Topo fixo e baixo.

Esquerda:

`← PAGAMENTO`

Direita:

* Cliente
* Dividir
* menu `⋮`

Pode usar ícones + labels compactas conforme espaço disponível.

Não criar header gigante.

==================================================
4. CLIENTE
==========

A ação CLIENTE continua utilizando o seletor/cadastro já existente.

Não duplicar lógica.

Somente reposicionar essa ação no header.

Se já houver cliente:

mostrar de forma compacta que existe um cliente selecionado.

Exemplo:

`👤 João`

==================================================
5. DIVIDIR
==========

A ação DIVIDIR deve concentrar as funções existentes de divisão.

Ao tocar, abrir BottomSheet/Dialog compacto:

```text
DIVIDIR PAGAMENTO

[ DIVIDIR IGUAL ]
Dividir o saldo entre pessoas.

[ PAGAR POR ITENS ]
Escolher quais itens serão pagos.
```

Reutilizar as funcionalidades já existentes.

NÃO reimplementar o cálculo.

==================================================
6. MENU DE AÇÕES SECUNDÁRIAS
============================

Usar `⋮` para ações que não precisam ocupar espaço permanente.

Exemplos conforme permissões/capabilities existentes:

* aplicar desconto;
* editar/remover cliente;
* remover taxa de serviço;
* entrada de caixa;
* sangria/retirada;
* cancelar venda.

NÃO inventar permissões novas.

Respeitar o RBAC atual.

Se uma ação não estiver implementada/permitida nesse fluxo, não criar artificialmente só para preencher menu.

==================================================
7. DESTAQUE PRINCIPAL = SALDO RESTANTE
======================================

O maior destaque visual da tela deve ser o estado financeiro atual.

Enquanto houver saldo:

```text
FALTA
R$ 33,00
```

Quando saldo for zero:

```text
PAGO
R$ 47,00
```

Usar `remainingAmount` e valores oficiais do checkout.

Não calcular saldo paralelo na UI.

==================================================
8. FORMAS DE PAGAMENTO EM GRID FIXO
===================================

Mostrar os meios principais em grid 2x2:

```text
DINHEIRO      DÉBITO

PIX           CRÉDITO
```

Cada botão deve ser:

* grande o suficiente para toque;
* visualmente identificável;
* rápido de localizar;
* consistente com a paleta CORE.

Usar os `paymentMethods` atuais.

Não hardcodar IDs.

Classificar usando os atributos existentes:

* `kind`;
* `visualGroup`;
* `code`.

Se houver outros meios:

mostrar botão:

`OUTROS`

e abrir uma lista/modal com os demais.

==================================================
9. NÃO ESCONDER O FLUXO DE PAGAMENTO PARCIAL
============================================

Depois de aplicar um pagamento:

o usuário deve permanecer na mesma tela.

Exemplo:

Total: R$ 47,00

Dinheiro: R$ 10,00

Então a tela imediatamente muda para:

```text
FALTA
R$ 37,00
```

e permite escolher outro meio.

Isso já existe no motor atual.

Somente melhorar a apresentação.

==================================================
10. PAGAMENTOS REALIZADOS
=========================

Criar uma área compacta:

`PAGAMENTOS REALIZADOS`

Mostrar os pagamentos aplicados.

Exemplo:

```text
✓ Dinheiro               R$ 10,00
  Confirmado                  ↩

✓ Pix                    R$ 15,00
  Confirmado                  ↩
```

O botão/ícone de estorno deve permanecer acessível quando permitido.

NÃO apagar pagamentos estornados da história.

Pagamento estornado deve aparecer como:

`Estornado`

e não desaparecer.

==================================================
11. MUITOS PAGAMENTOS
=====================

Se houver muitos pagamentos, NÃO aumentar infinitamente a tela.

A área `PAGAMENTOS REALIZADOS` deve ter altura máxima.

Se ultrapassar:

scroll somente nessa área

OU

mostrar os mais recentes +:

`VER TODOS (N)`

e abrir modal/bottom sheet.

Escolha a solução mais coerente com a estrutura atual.

A tela principal continua fixa.

==================================================
12. RESUMO INFERIOR COMPACTO
============================

No rodapé da área de conteúdo sempre mostrar pelo menos:

```text
Total       R$ XX,XX
Pago        R$ XX,XX
Falta       R$ XX,XX
```

Usar os valores oficiais.

Não recalcular.

Se for necessário mostrar:

* subtotal;
* promoções;
* desconto;
* taxa de serviço;

não ocupar a tela inteira.

Criar uma expansão compacta:

`VER DETALHES`

ou seta.

Exemplo recolhido:

```text
TOTAL    R$ 47,00
PAGO     R$ 25,00
FALTA    R$ 22,00          ⌃
```

Expandido:

```text
Subtotal                 R$ 50,00
Promoções               - R$ 3,00
Desconto                - R$ 2,00
Taxa de serviço           R$ 2,00

Total                     R$ 47,00
Pago                      R$ 25,00
Falta                     R$ 22,00
```

==================================================
13. CTA PRINCIPAL FIXO
======================

No final da tela deve existir área fixa para ação principal.

Enquanto ainda houver saldo:

o operador continua escolhendo pagamentos.

Quando:

`remainingAmount == 0`

mostrar com destaque:

`FINALIZAR VENDA`

Esse botão deve permanecer visível sem necessidade de scroll.

==================================================
14. VALOR RECEBIDO / TROCO
==========================

Dinheiro continua abrindo o fluxo existente de:

* valor do pagamento;
* valor recebido;
* troco.

Não alterar regras.

Melhorar somente apresentação se necessário para combinar com a nova UI.

Depois da confirmação:

voltar para a TELA FIXA DE PAGAMENTO atualizada.

==================================================
15. CRÉDITO / DÉBITO / PIX
==========================

Hoje podem ser pagamentos manuais.

Manter exatamente o comportamento atual.

A UI deve ficar preparada para futuramente o mesmo botão chamar:

* Stone;
* Cielo;
* outro provider;

sem redesenhar a tela.

NÃO implementar adquirente nesta missão.

==================================================
16. STATUS SEM TEXTO TÉCNICO
============================

Continuar utilizando a apresentação em português já adicionada.

Nunca exibir:

* applied;
* reversed;
* cancelled;
* editing;
* paid;
* partial;
* finalized.

Mostrar labels amigáveis:

* Confirmado;
* Estornado;
* Cancelada;
* Em andamento;
* Pago;
* Pagamento parcial;
* Finalizada.

==================================================
17. QUANTIDADES
===============

Continuar usando o formatter visual já criado.

Não voltar a exibir:

`1.000`

quando é:

`1`

ou:

`1.500`

quando deve aparecer:

`1,5`.

==================================================
18. CORRIGIR VALIDAÇÃO DE CASAS DECIMAIS
========================================

Existe uma validação incorreta encontrada anteriormente.

Trechos semelhantes a:

```dart
text.split(RegExp(r'[,.]')).last.length <= 3
```

tratam:

`1000`

como se tivesse 4 casas decimais.

CORRIGIR.

A validação deve limitar somente a PARTE DECIMAL quando realmente existir separador.

Exemplos:

```text
1        válido
100      válido
1000     válido
100000   válido dentro dos limites de domínio

1,1      válido
1,12     válido
1,123    válido
1,1234   inválido
```

Corrigir onde isso existir na Venda Rápida/componentes compartilhados.

==================================================
19. APAGAR CARRINHO — NAVEGAÇÃO OBRIGATÓRIA
===========================================

BUG ATUAL:

ao apagar o carrinho, a interface pode continuar na página de carrinho vazia.

NÃO QUERO ISSO.

Fluxo obrigatório:

```text
Carrinho
↓
APAGAR CARRINHO
↓
confirma
↓
backend confirma CANCELLED
↓
storage limpo
↓
draft limpo
↓
CATÁLOGO DA VENDA RÁPIDA
```

Após apagar:

* não permanecer no carrinho;
* não abrir Pagamento;
* não mostrar tela vazia de carrinho.

O destino deve ser o CATÁLOGO.

==================================================
20. NOVA VENDA — NAVEGAÇÃO OBRIGATÓRIA
======================================

BUG ATUAL:

na tela:

`VENDA CONCLUÍDA`

ao tocar:

`NOVA VENDA`

o sistema ainda pode retornar para a página do carrinho.

NÃO QUERO.

Fluxo obrigatório:

```text
VENDA CONCLUÍDA
↓
NOVA VENDA
↓
CATÁLOGO DA VENDA RÁPIDA
```

Estado:

* carrinho vazio;
* checkout anterior finalizado;
* storage do checkout anterior limpo;
* sem cliente antigo;
* sem desconto antigo;
* sem Pagamento aberto;
* catálogo visível;
* pronto para adicionar novo produto.

==================================================
21. VOLTAR NA TELA VENDA CONCLUÍDA
==================================

O botão físico/back do Android nessa tela também não deve levar para o carrinho antigo/vazio.

Deve retornar ao CATÁLOGO limpo.

`NOVA VENDA` e `BACK` após conclusão possuem o mesmo destino operacional:

CATÁLOGO.

==================================================
22. ESTADO PRINCIPAL DO MÓDULO
==============================

Definir claramente:

O estado base da Venda Rápida é:

`CATÁLOGO`

Não:

`CARRINHO`.

Carrinho é uma visualização temporária da venda atual.

Portanto:

```text
entrada no módulo
→ catálogo

nova venda
→ catálogo

apagar carrinho
→ catálogo

venda finalizada + nova venda
→ catálogo
```

==================================================
23. PREPARAR COMPONENTES PARA MESAS
===================================

IMPORTANTE.

Depois desta missão vamos voltar para o NOVO MÓDULO DE MESAS.

A tela de pagamento de Mesa deve reutilizar OS MESMOS ELEMENTOS desta tela.

Então NÃO crie widgets excessivamente específicos de QuickSale onde não for necessário.

Extrair/reutilizar componentes visuais coerentes, por exemplo:

* PaymentHeader
* RemainingAmountCard
* PaymentMethodGrid
* PaymentHistory
* PaymentHistoryItem
* PaymentFinancialSummary
* PaymentPrimaryAction
* PaymentSplitSelector

Os nomes exatos ficam a critério da arquitetura encontrada.

NÃO refatorar todo motor agora.

Mas deixe os COMPONENTES VISUAIS reutilizáveis.

==================================================
24. IMPORTANTE SOBRE SHARED PAYMENT
===================================

Hoje existe:

`SharedPaymentPage`

Ela ainda é bastante ligada a:

`QuickSaleCheckout`.

NÃO precisa refatorar toda arquitetura para Mesa nesta missão.

Mas:

* não duplicar componentes;
* não criar uma nova tela paralela;
* manter os blocos visuais separados da regra específica da Venda Rápida quando possível.

Na próxima etapa vamos adaptar esses mesmos componentes ao fluxo de Mesa.

==================================================
25. RESPONSIVIDADE
==================

Essa UI precisa funcionar principalmente em orientação/tela de POS.

Usar `LayoutBuilder`/constraints conforme necessário.

Em tela mais larga pode aproveitar espaço lateral.

Em tela estreita deve continuar SEM scroll da página principal.

Não usar tamanhos fixos absurdos que só funcionem no aparelho atual.

==================================================
26. IDENTIDADE VISUAL CORE
==========================

Manter identidade atual.

Primary:

`#3454D1`

Não redesenhar o aplicativo inteiro.

Usar:

* surfaces claras;
* bordas suaves;
* hierarquia tipográfica forte;
* botões touch-friendly;
* espaçamento compacto;
* estados semânticos existentes.

Tela operacional, não dashboard administrativo.

==================================================
27. NÃO CRIAR TESTES AUTOMATIZADOS NOVOS
========================================

O teste funcional dessa UI será feito manualmente pelo proprietário do projeto.

NÃO gastar esta missão criando novos testes Widget/integrados.

Pode ajustar algum teste existente se a mudança estrutural quebrar compilação, mas NÃO criar nova bateria de testes.

==================================================
28. CHECKS
==========

Executar somente o necessário para garantir integridade da alteração Flutter:

* `flutter analyze`
* `git diff --check`

NÃO rodar Android/Gradle.

NÃO fazer alterações extras para perseguir problemas fora deste escopo.

==================================================
29. CHECKPOINT FINAL
====================

Ao terminar informar:

1. arquivos alterados;
2. como ficou o layout estático;
3. como evitou scroll da página principal;
4. como ficou o header;
5. como ficou o card FALTA/PAGO;
6. como ficou o grid de pagamentos;
7. como ficou pagamentos realizados;
8. como ficou resumo financeiro;
9. como ficou CTA FINALIZAR VENDA;
10. correção de `1000` na validação decimal;
11. comportamento após APAGAR CARRINHO;
12. comportamento após NOVA VENDA;
13. comportamento do botão voltar após venda concluída;
14. quais componentes visuais foram deixados reutilizáveis para Mesa;
15. resultado do `flutter analyze`;
16. resultado do `git diff --check`;
17. resumo objetivo do diff.

DEPOIS PARE.

NÃO mexa em Mesa ainda.

NÃO mexa no motor financeiro.

NÃO mexa na idempotência.
