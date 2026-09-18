FAÇA UMA REVISÃO E CORREÇÃO COMPLETA, MAS ESTRITAMENTE FOCADA, DO MÓDULO VENDA RÁPIDA + CARRINHO + PAGAMENTOS DO CORE POS.

PARTA DO HEAD ATUAL DO PROJETO.

IMPORTANTE SOBRE ESCOPO:

NÃO mexer em Comanda legado.
O módulo legado de Comanda ainda será removido/substituído pelo novo módulo de Mesas.

NÃO mexer em Platform Admin nesta missão.

NÃO mexer em:

* Stone;
* Cielo;
* PagBank;
* Android;
* Gradle;
* fiscal;
* impressão;
* outros módulos não relacionados.

FOCO EXCLUSIVO:

* Venda Rápida;
* carrinho;
* recovery;
* QuickSaleCheckout;
* pagamentos da Venda Rápida;
* cancelamento/descarte;
* finalização;
* estado persistido;
* UI/UX dessas telas;
* testes Flutter relacionados.

NÃO fazer refatoração geral.

==================================================

1. CORRIGIR RECOVERY QUE APAGA STORAGE EM QUALQUER HTTP < 500
   ==================================================

BUG JÁ CONFIRMADO EM:

`pos/lib/core/app_controller.dart`

Hoje `recoverQuickSaleCheckout()` possui comportamento equivalente a:

```dart
on PosApiException catch (error) {
  if (error.statusCode < 500) {
    await _writeQuickCheckoutState({});
  }
}
```

ISSO É ERRADO.

Um:

* 401;
* 403;
* 409;
* 422;
* 429;

não prova que o checkout deixou de existir.

Isso pode gerar:

checkout ainda OPEN no backend
+
reserva de estoque ativa
+
storage local apagado
=====================

checkout órfão.

CORRIGIR.

O estado local do checkout só pode ser descartado automaticamente quando houver prova autoritativa de que ele não deve mais ser recuperado.

Exemplos aceitáveis:

A) backend retornou o checkout e ele está terminal:

* CANCELLED;
* FINALIZED.

B) endpoint de recovery/detail retornou 404 que realmente representa ausência daquele checkout naquele escopo.

NÃO usar mais genericamente:

`statusCode < 500`

para apagar o QuickSaleCheckoutState.

Em:

* 401;
* 403;
* 409;
* 422;
* 429;
* 5xx;
* erro de rede;

PRESERVAR o estado local.

Mostrar o erro, mas NÃO esquecer a venda.

Não alterar indiscriminadamente a semântica das intents de pagamento já existente.
Esta regra é especificamente sobre esquecer o CHECKOUT persistido.

==================================================
2. CANCELAMENTO SÓ PODE LIMPAR STORAGE SE BACKEND CONFIRMAR CANCELLED
=====================================================================

Hoje `cancelQuickSaleCheckout()` faz aproximadamente:

```dart
await _api.cancelQuickSaleCheckout(...);
await _writeQuickCheckoutState({});
return true;
```

Isso confia apenas no HTTP success.

CORRIGIR.

Capturar o `QuickSaleCheckout` retornado pela API.

Só considerar cancelamento concluído se o backend retornar estado terminal esperado:

`cancelled`

Se resposta vier com:

* editing;
* partial;
* paid;
* qualquer estado não cancelado;

NÃO limpar storage.

NÃO retornar sucesso.

NÃO limpar carrinho.

Informar erro de inconsistência ao operador.

Fluxo obrigatório:

POST cancel
-> resposta oficial
-> checkout.status == cancelled
-> limpar storage
-> retornar true

Caso contrário:

-> preservar storage
-> retornar false.

==================================================
3. TESTE COMPLETO DO BUG ORIGINAL
=================================

O teste atual de discard NÃO é suficiente.

O fake atual chega a devolver um checkout ainda `editing` em:

`cancelQuickSaleCheckout()`

e mesmo assim o teste considera o descarte bem-sucedido.

CORRIGIR ESSE TESTE.

O fake/backend simulado deve realmente mudar:

editing
-> cancelled

Adicionar teste Widget/integrado Flutter reproduzindo exatamente:

Produto A
-> criar Checkout A
-> abrir Pagamento
-> voltar
-> APAGAR CARRINHO
-> backend confirma CANCELLED
-> sair da Venda Rápida
-> entrar novamente em Venda Rápida

RESULTADO OBRIGATÓRIO:

* Produto A não reaparece;
* carrinho vazio;
* checkout A não é recuperado;
* Pagamento não abre;
* storage do operador não possui checkout A;
* checkout A foi realmente cancelado;
* nova venda poderá gerar Checkout B.

Este teste deve usar `QuickSaleCheckoutStateStore` real em memória.

==================================================
4. BUG REAL — RECOVERY COM TOTAL CORRETO E 0 ITENS
==================================================

BUG REPRODUZIDO NO APP:

1. adiciono produto;
2. checkout é criado;
3. saio da Venda Rápida;
4. entro novamente;
5. aparece:

"Venda em andamento recuperada."

e o valor correto, por exemplo:

R$ 22,00

PORÉM:

* aparece "0 itens";
* ao tocar no carrinho ele está vazio;
* não aparece menu superior do carrinho;
* não consigo avançar novamente para Pagamento.

A CAUSA FOI IDENTIFICADA.

Em:

`pos/lib/sales/quick_sale_page.dart`

`_restoreCheckoutDraft()` monta:

```dart
final productsById = {
  for (final product in _allCatalog) product.id: product
};
```

e depois:

```dart
final product = productsById[...];

if (product == null) continue;
```

ISSO NÃO É ACEITÁVEL PARA RECOVERY.

O checkout persistido é a fonte oficial daquela venda.

Recovery NÃO pode depender de o produto ainda aparecer no catálogo operacional atual.

Um produto pode não estar no `_allCatalog` porque:

* a própria reserva do checkout consumiu a disponibilidade;
* `show_out_of_stock_products` está false;
* condição operacional mudou;
* filtro de catálogo;
* produto deixou de ser exibido;
* catálogo falhou parcialmente.

Mesmo assim o checkout continua contendo o item.

NÃO DESCARTAR SILENCIOSAMENTE O ITEM.

==================================================
5. CHECKOUT RECUPERADO DEVE SER AUTOSSUFICIENTE
===============================================

Corrigir a arquitetura do recovery.

Quando recuperamos `QuickSaleCheckout`, precisamos possuir dados suficientes para reconstruir visualmente os itens da venda SEM depender da lista atual do catálogo.

Não resolver com:

```dart
if (product == null) continue;
```

Não resolver inventando produto incompleto se isso puder perder:

* preço;
* unidade;
* modificadores;
* nomes dos modificadores;
* código;
* snapshots;
* regras necessárias para continuar a venda.

Use a solução mais coerente com a arquitetura atual.

É aceitável, por exemplo:

* enriquecer o payload oficial de `QuickSaleCheckout.items`;
* incluir snapshot de produto necessário ao recovery;
* ou implementar resolução específica dos produtos pertencentes ao checkout que não dependa do filtro normal do catálogo.

PRESERVAR snapshots históricos.

O carrinho recuperado deve refletir exatamente o checkout oficial.

==================================================
6. RECOVERY NÃO PODE MUDAR O FINANCEIRO
=======================================

Ao recuperar:

* não recalcular preço automaticamente;
* não reaplicar promoção atual;
* não mudar desconto;
* não mudar taxa;
* não mudar total.

O `financial_snapshot` oficial do checkout continua sendo a fonte de verdade.

Exemplo:

antes de sair:

1 Coca
Total R$ 22,00

depois de voltar:

1 Coca
Total R$ 22,00

Mesmo que preço ou promoção do catálogo tenham mudado.

==================================================
7. CONTADOR DO CARRINHO DEVE VOLTAR CORRETAMENTE
================================================

Hoje o usuário reproduziu:

Venda recuperada
R$ 22,00
0 itens

Isso não pode acontecer.

Após recovery:

* `_cart` deve possuir os itens oficiais;
* `MobileCartBar` deve ser atualizado;
* contador deve refletir o carrinho restaurado;
* carrinho deve abrir com os produtos;
* botão de Pagamento deve continuar disponível se permitido.

NÃO usar `preview.items` como fonte de quantidade do carrinho.

A fonte é o carrinho restaurado a partir do checkout.

==================================================
8. TESTE OBRIGATÓRIO — PRODUTO AUSENTE DO CATÁLOGO NORMAL
=========================================================

Adicionar teste específico:

Checkout A contém Produto A.

Ao reabrir Venda Rápida:

o endpoint/lista normal de catálogo NÃO contém Produto A.

Porém o checkout recuperado contém Produto A.

RESULTADO:

* Produto A aparece no carrinho recuperado;
* contador não fica 0;
* nome correto;
* quantidade correta;
* total correto;
* não é descartado silenciosamente;
* é possível seguir para Pagamento quando as capabilities permitirem.

Esse teste é ESSENCIAL porque o teste atual só funciona quando o produto recuperado também existe no catálogo fake.

==================================================
9. REVISAR TODA FORMATAÇÃO DE QUANTIDADE
========================================

Hoje existem vários pontos que exibem valor bruto vindo do backend.

Exemplo errado:

`1.000`

para representar uma unidade.

O operador deve ver:

`1`

Outro exemplo:

`1.500`

deve ser exibido como:

`1,5`

no padrão visual brasileiro.

Criar/reutilizar uma função única de apresentação de quantidade.

Exemplos:

1.000 -> 1
2.000 -> 2
1.500 -> 1,5
0.500 -> 0,5
1.250 -> 1,25

Máximo de casas conforme precisão operacional necessária, removendo zeros à direita.

NÃO alterar o valor enviado para API.

Somente apresentação.

Aplicar em TODAS as superfícies da Venda Rápida/Pagamentos:

* `SharedCartItemTile`;
* Qtd. do carrinho;
* produto recuperado;
* modificadores;
* warnings de estoque;
* quantidade disponível;
* quantidade selecionada;
* pagamento por itens;
* desconto por item;
* scanner/carrinho;
* editor de quantidade;
* qualquer outra exibição encontrada.

==================================================
10. MODIFICADORES TAMBÉM NÃO PODEM MOSTRAR 1.000x
=================================================

Hoje `_itemDetails()` pode usar diretamente:

```dart
selected['quantity']
```

Podendo resultar em:

`1.000x Adicional`

Corrigir para:

`1x Adicional`

ou:

`1,5x ...`

quando fracionamento fizer sentido.

==================================================
11. PAGAMENTO POR ITENS DEVE USAR FORMATO PT-BR
===============================================

Hoje `_quantityValue()` do fluxo "Pagar por itens" produz decimal com `.`.

Exemplo:

`1.5`

Na UI brasileira deve aparecer:

`1,5`

Sem alterar o payload oficial enviado à API.

Separar:

valor canônico/API
de
valor de apresentação.

==================================================
12. BUG DE PRODUTOS FRACIONADOS NO EDITOR DO CARRINHO
=====================================================

Revisar:

`_EditCartItemDialog`

Hoje existem trechos equivalentes a:

```dart
int.tryParse(_item.quantity)
```

Isso é incorreto para produtos fracionados.

Exemplo:

quantidade = `1.500`

`int.tryParse()` falha.

O código cai em fallback e pode transformar incorretamente a quantidade em 1, 2 etc.

CORRIGIR.

Produtos:

* UN;
* KG;
* G;
* L;
* ML;
* qualquer unidade fracionável;

devem respeitar suas regras de quantidade.

UN continua exigindo inteiro quando essa for a regra oficial.

Não introduzir float impreciso para payload financeiro/quantidade oficial.

==================================================
13. NUNCA EXIBIR STATUS TÉCNICO EM INGLÊS
=========================================

Auditar TODA Venda Rápida e Pagamentos.

Nunca mostrar diretamente ao usuário:

* `cancelled`;
* `finalized`;
* `editing`;
* `partial`;
* `paid`;
* `applied`;
* `reversed`;
* ou outros enums técnicos.

Criar/reutilizar apresentação centralizada.

Exemplo:

`editing` -> `Em andamento`
`partial` -> `Pagamento parcial`
`paid` -> `Pago`
`finalized` -> `Finalizada`
`cancelled` -> `Cancelada`
`applied` -> `Confirmado`
`reversed` -> `Estornado`

Backend continua usando os valores canônicos em inglês.

Somente UI deve traduzir.

PROCURAR os locais em que status bruto esteja chegando à interface.

==================================================
14. NÃO MISTURAR STATUS DE DOMÍNIO COM LABEL
============================================

NÃO trocar enums do backend para português.

Backend continua:

`cancelled`

Flutter usa:

`cancelled`

para lógica.

Somente quando for desenhar texto:

`Cancelada`.

==================================================
15. FINALIZAÇÃO DA VENDA ESTÁ COM UX ERRADA
===========================================

BUG REPRODUZIDO:

1. pago a Venda Rápida;
2. toco FINALIZAR VENDA;
3. backend conclui;
4. Flutter fecha a tela de Pagamento;
5. volta para o carrinho vazio;
6. não aparece nenhuma confirmação de venda.

Isso está confirmado no código atual.

Em:

`pos/lib/payments/shared_payment_page.dart`

`_finish()`:

* chama `finalizeQuickSaleCheckout`;
* chama `onCompleted`;
* faz `Navigator.pop()`.

Em `QuickSalePage`, `onCompleted` apenas limpa o draft/recarrega catálogo.

CORRIGIR.

==================================================
16. CRIAR TELA "VENDA CONCLUÍDA"
================================

Após `finalizeQuickSaleCheckout()` retornar SUCESSO OFICIAL do backend:

mostrar uma página/tela própria.

Layout esperado:

ícone de sucesso

VENDA CONCLUÍDA

Venda #XXXXXX

R$ XX,XX

Se houver produção:

"Pedido enviado para produção."

Se houver tickets, pode mostrar informação resumida dos tickets sem poluir.

Botão principal grande:

NOVA VENDA

Usar dados que JÁ EXISTEM em:

`QuickSaleResult`

* `saleNumber`;
* `total`;
* `ticketNumbers`;
* `productionJobCount`.

Não criar chamada extra desnecessária.

==================================================
17. BOTÃO "NOVA VENDA"
======================

Ao tocar:

NOVA VENDA

deve ir para o CATÁLOGO da Venda Rápida.

Estado esperado:

* carrinho vazio;
* checkout antigo removido do storage;
* nenhum pagamento antigo;
* nenhum pending antigo já reconciliado;
* cliente vazio;
* desconto zerado;
* service fee padrão;
* catálogo carregado;
* pronto para adicionar produto.

NÃO voltar para:

* Pagamento antigo;
* carrinho vazio isolado;
* tela de sucesso novamente.

==================================================
18. BACK DA TELA DE VENDA CONCLUÍDA
===================================

Pressionar voltar na tela de sucesso NÃO pode ressuscitar:

* checkout finalizado;
* Pagamento;
* carrinho anterior.

Pode ter o mesmo comportamento lógico de "NOVA VENDA", retornando ao catálogo limpo.

==================================================
19. SUCESSO SÓ APÓS BACKEND CONFIRMAR
=====================================

NÃO mostrar "VENDA CONCLUÍDA" antes de:

`finalizeQuickSaleCheckout()`

retornar `QuickSaleResult`.

Se ocorrer:

* timeout;
* erro de rede;
* 5xx;
* resposta incerta;

NÃO mostrar sucesso.

Preservar:

* pending finalize;
* idempotency key;
* checkout;
* mecanismo de recovery.

O operador nunca pode ver sucesso se ainda não sabemos se a venda foi concluída.

==================================================
20. FINALIZAÇÃO IDEMPOTENTE CONTINUA INTACTA
============================================

NÃO remover nem simplificar a lógica atual de:

* idempotency key de finalização;
* pending `finalize`;
* retry;
* recovery;
* ledger.

A correção aqui é UI/UX e lifecycle.

==================================================
21. REVISAR ESTADOS VAZIOS E BOTÕES BLOQUEADOS
==============================================

Auditar a Venda Rápida inteira para estados incoerentes como:

* total > 0 e carrinho com 0 itens;
* checkout possui itens e UI mostra carrinho vazio;
* carrinho possui itens e botão Pagamento não aparece sem motivo;
* menu "Apagar carrinho" desaparece apesar de checkout possuir itens;
* carrinho recuperado sem header/actions;
* botão de pagamento desabilitado por estado visual incorreto;
* checkout recuperado mas `_preview` não sincronizado;
* loading permanente;
* texto antigo depois de mutação;
* contadores desatualizados.

Não mascarar estado inconsistente.

Se checkout oficial possui item, a UI deve representar o mesmo item.

==================================================
22. REVISAR UI/UX DA VENDA RÁPIDA/PAGAMENTO
===========================================

Faça busca estática pelas telas relacionadas e corrija inconsistências comprovadas de apresentação, incluindo:

* zeros desnecessários;
* decimal usando ponto;
* status em inglês;
* pluralização errada;
* contador desatualizado;
* valor bruto do backend;
* botões que desaparecem por estado derivado incorreto;
* páginas vazias sem ação possível;
* mensagem de sucesso ausente;
* loading sem término;
* labels técnicas.

NÃO redesenhar o módulo inteiro.

Manter identidade visual atual do CORE.

==================================================
23. TESTES OBRIGATÓRIOS
=======================

Adicionar/corrigir testes para:

A)
Recovery normal:

Produto A
-> sair
-> entrar

Resultado:

Produto A restaurado;
contador correto;
total correto;
Pagamento não abre automaticamente.

B)
Recovery com Produto A ausente do catálogo normal.

Resultado:

Produto A NÃO desaparece.

C)
Pagamento
-> voltar
-> apagar
-> cancelar backend
-> sair
-> entrar.

Resultado:

não recupera venda.

D)
backend responde ao cancelamento com estado diferente de `cancelled`.

Resultado:

storage permanece;
carrinho permanece;
descarte retorna false.

E)
recovery recebe 401/403/409/429.

Resultado:

storage permanece.

F)
recovery recebe condição autoritativa de checkout terminal/ausente.

Resultado:

storage é limpo conforme a regra definida.

G)
quantidade:

`1.000` -> UI `1`
`1.500` -> UI `1,5`

H)
produto fracionado permanece com quantidade correta ao editar.

I)
finalização:

backend retorna:

saleNumber = V000123
total = 22.00

Resultado:

exibe:

VENDA CONCLUÍDA
Venda #V000123
R$ 22,00
NOVA VENDA

J)
tocar NOVA VENDA:

volta ao catálogo;
nenhum checkout anterior é recuperado.

K)
finalização com erro/rede incerta:

NÃO mostra tela de sucesso;
preserva retry/idempotência.

==================================================
24. NÃO ALTERAR
===============

NÃO mexer em:

* Comanda legado;
* novo módulo de Mesa fora do necessário;
* Platform Admin;
* estoque estrutural;
* regras financeiras;
* Stone;
* Cielo;
* PagBank;
* API fiscal;
* impressão;
* permissões gerais.

NÃO substituir a idempotência existente.

NÃO apagar storage inteiro.

NÃO apagar estado de outro operador.

NÃO apagar ledger.

NÃO apagar reversal.

NÃO transformar recovery em "começar nova venda sempre".

==================================================
25. CHECKS
==========

Executar:

* `flutter analyze`
* `flutter test` dos testes relacionados a Venda Rápida/Pagamentos
* `git diff --check`

NÃO rodar build Android/Gradle.

==================================================
26. CHECKPOINT FINAL
====================

No final informar:

1. causa do storage ser apagado em 4xx;
2. regra nova para esquecer checkout;
3. como cancelamento agora confirma `cancelled`;
4. causa exata do "R$ 22,00 / 0 itens";
5. como o recovery deixou de depender do catálogo normal;
6. como preserva snapshot financeiro;
7. como ficou contador após recovery;
8. formatter único de quantidade;
9. locais corrigidos de `1.000`;
10. status técnicos traduzidos;
11. correção de produtos fracionados;
12. implementação da tela VENDA CONCLUÍDA;
13. comportamento do botão NOVA VENDA;
14. comportamento do botão voltar após sucesso;
15. garantia de que sucesso só aparece após confirmação backend;
16. testes adicionados;
17. resultado do `flutter analyze`;
18. resultado dos testes;
19. resultado do `git diff --check`;
20. arquivos alterados;
21. resumo objetivo do diff.

DEPOIS PARE.

NÃO aproveite para mexer em módulos fora do escopo.
