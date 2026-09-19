CORRIJA SOMENTE OS PONTOS AINDA PENDENTES DA VENDA RÁPIDA / PAGAMENTOS.

PARTA DO HEAD ATUAL.

NÃO refaça o módulo.
NÃO mexa no motor financeiro.
NÃO mexa na idempotência.
NÃO mexa em Mesa ainda.
NÃO mexa em Comanda legado.
NÃO mexa em Stone/Cielo/PagBank.
NÃO criar novos testes automatizados — o teste funcional será feito manualmente.

A missão é corrigir os bugs de UI/UX e NAVEGAÇÃO que ainda existem.

==================================================

1. REMOVER TEXTO "EDIÇÃO FINANCEIRA BLOQUEADA"
   ==================================================

Hoje, depois do primeiro pagamento, aparece na tela:

`Edição financeira bloqueada após o primeiro pagamento.`

REMOVER ESSA MENSAGEM DA UI.

IMPORTANTE:

NÃO remover a proteção financeira.

A regra atual do backend é correta:

após existir pagamento aplicado:

`can_edit_financials = false`

Continuar respeitando isso.

O que deve desaparecer é SOMENTE o texto ocupando espaço.

As ações financeiras que não puderem mais ser executadas devem:

* ficar desabilitadas;
* ou não estar disponíveis conforme a UX definida;

sem exibir aquela mensagem permanentemente.

==================================================
2. DIMINUIR O CARD FALTA / PAGO
===============================

Hoje o bloco:

`FALTA`
`R$ XX,XX`

está grande demais para uma tela operacional de POS.

Quero algo bem mais compacto.

Exemplo conceitual:

```text
FALTA            R$ 33,00
```

ou:

```text
FALTA
R$ 33,00
```

mas com altura bem menor que a atual.

Reduzir:

* padding vertical;
* tamanho exagerado da tipografia;
* espaço desperdiçado.

Continuar deixando o saldo como destaque visual.

Quando quitado:

```text
PAGO             R$ 47,00
```

NÃO perder destaque, apenas ficar compacto.

==================================================
3. DIMINUIR OS BOTÕES DE PAGAMENTO
==================================

Os botões de:

* DINHEIRO;
* DÉBITO;
* PIX;
* CRÉDITO;

estão grandes demais.

Diminuir altura e espaçamento para caber confortavelmente na tela da maquininha.

Eles ainda devem continuar:

* touch-friendly;
* fáceis de identificar;
* com ícone;
* com label.

Mas não precisam ocupar blocos enormes.

Objetivo aproximado:

2 colunas x 2 linhas compactas.

==================================================
4. CORRIGIR O GRID DE PAGAMENTO
===============================

BUG CONFIRMADO.

Hoje existe algo equivalente a:

```dart
SizedBox(
  height: rows * 76,
  child: GridView.count(
    crossAxisCount: 2,
    physics: NeverScrollableScrollPhysics(),
  ),
)
```

O problema é que `GridView.count` usa células com proporção padrão e a altura reservada não corresponde à altura real.

Na prática a primeira linha aparece:

```text
DINHEIRO     DÉBITO
```

e a segunda:

```text
PIX          CRÉDITO
```

pode ficar cortada.

Isso explica o comportamento observado de só aparecer:

* Dinheiro;
* Débito.

CORRIGIR ESTRUTURALMENTE.

NÃO apenas aumentar o `SizedBox` arbitrariamente.

Use uma solução com altura explícita das células, como:

* `SliverGridDelegateWithFixedCrossAxisCount` + `mainAxisExtent`;
* ou `Row/Column` para esse grid pequeno.

O resultado visual precisa ser:

```text
[ DINHEIRO ] [ DÉBITO  ]
[ PIX      ] [ CRÉDITO ]
```

todos completamente visíveis ao mesmo tempo.

==================================================
5. FORMAS DE PAGAMENTO DEVEM VIR DA API
=======================================

NÃO hardcodar IDs nem assumir que existem apenas quatro métodos.

O endpoint atual:

`sales/checkout-options/`

já retorna:

`payment_methods`

com TODOS os `PaymentMethod` ativos da empresa.

Continuar usando a API como fonte de verdade.

Os principais devem ser agrupados visualmente por:

* `kind`;
* `visual_group`;
* `code`.

Exibir:

* Dinheiro;
* Débito;
* PIX;
* Crédito.

Se existirem outros métodos ativos, como:

* VA;
* VR;
* vouchers;
* métodos customizados;

mostrar:

`OUTROS`

e dentro listar TODAS as demais formas retornadas pela API.

Nenhum método ativo recebido pela API pode simplesmente desaparecer da interface.

==================================================
6. NÃO CONFUNDIR MÉTODO AUSENTE NA API COM BUG DE UI
====================================================

O frontend deve renderizar tudo que recebeu.

Se a API retornar:

4 métodos

a UI deve disponibilizar os 4.

Se a API retornar:

2 métodos

a UI deve disponibilizar os 2.

NÃO inventar método no Flutter.

Mas revisar o backend atual porque existe:

`ensure_default_payment_methods()`

e os métodos padrão são:

* cash;
* pix;
* credit_card;
* debit_card.

Se um método padrão já existir como INATIVO, a função atual aparentemente não o reativa.

NÃO faça alteração destrutiva automaticamente sem entender o domínio.

Mas informe no checkpoint se:

* os quatro defaults estão garantidos como ativos;
  OU
* apenas são criados quando inexistentes e um método inativo permanece inativo.

Não mascarar isso no Flutter.

==================================================
7. HEADER SUPERIOR PRECISA SER SEMPRE ESTÁVEL
=============================================

BUG OBSERVADO:

o menu superior da tela de pagamento às vezes aparece completo e às vezes muda/desaparece.

A causa atual inclui ações condicionais.

Especialmente:

`CLIENTE`

só aparece quando:

`canEditFinancials == true`.

Quando ocorre o primeiro pagamento:

`canEditFinancials = false`

e o botão desaparece.

NÃO QUERO O HEADER MUDANDO DE ESTRUTURA.

O header deve manter sempre o mesmo layout.

Em tela estreita:

```text
← PAGAMENTO                👤   ⇄   ⋮
```

Ações:

* Cliente;
* Dividir;
* menu.

Se uma ação estiver proibida pelo estado atual:

MANTER o ícone no mesmo lugar, porém desabilitado quando necessário.

Não remover o elemento e fazer o AppBar mudar de tamanho/disposição.

==================================================
8. HEADER RESPONSIVO
====================

Na maquininha/celular:

usar prioritariamente ÍCONES.

Exemplo:

```text
← PAGAMENTO        👤  ⇄  ⋮
```

Com:

* tooltip;
* semantics.

Em telas maiores pode usar:

```text
← PAGAMENTO    👤 CLIENTE    ⇄ DIVIDIR    ⋮
```

Usar `LayoutBuilder` ou largura disponível.

Não deixar:

`PAGAMENTO | CLIENTE | DIVIDIR | ⋮`

espremido numa tela pequena.

==================================================
9. CANCELAR VENDA NÃO PODE VOLTAR PARA CARRINHO
===============================================

BUG CONFIRMADO.

No mobile, a pilha atual pode ficar:

```text
CATÁLOGO
↓
CARRINHO
↓
PAGAMENTO
```

Ao cancelar:

```text
Navigator.pop()
```

faz:

```text
PAGAMENTO
↓
CARRINHO
```

ISSO ESTÁ ERRADO.

Resultado obrigatório após cancelamento confirmado:

```text
PAGAMENTO
↓
cancelamento backend confirmado
↓
checkout CANCELLED
↓
storage limpo
↓
draft limpo
↓
CATÁLOGO
```

Não voltar para Carrinho.

==================================================
10. NOVA VENDA NÃO PODE VOLTAR PARA CARRINHO
============================================

BUG CONFIRMADO.

Hoje pode existir:

```text
CATÁLOGO
↓
CARRINHO
↓
PAGAMENTO
↓
VENDA CONCLUÍDA
```

E `NOVA VENDA` faz apenas:

```dart
Navigator.pop()
```

voltando ao Carrinho.

CORRIGIR.

Resultado obrigatório:

```text
VENDA CONCLUÍDA
↓
NOVA VENDA
↓
CATÁLOGO
```

Com:

* carrinho vazio;
* checkout anterior finalizado;
* storage limpo;
* cliente zerado;
* desconto zerado;
* nenhuma tela de pagamento anterior;
* catálogo pronto para uso.

==================================================
11. BACK DA VENDA CONCLUÍDA TAMBÉM VAI PARA CATÁLOGO
====================================================

O botão físico/back do Android na tela:

`VENDA CONCLUÍDA`

deve ter o mesmo destino operacional de:

`NOVA VENDA`.

Ou seja:

CATÁLOGO.

Nunca:

* Carrinho;
* Pagamento;
* checkout antigo.

==================================================
12. CORRIGIR A NAVEGAÇÃO ESTRUTURALMENTE
========================================

NÃO quero uma sequência frágil de vários:

`Navigator.pop()`

ou `popUntil()` tentando adivinhar rotas.

O problema nasce porque no mobile o Pagamento é aberto enquanto o Carrinho continua abaixo dele.

A arquitetura deve ficar coerente.

Uma solução aceitável:

```text
CATÁLOGO
↓
CARRINHO
↓
IR PARA PAGAMENTO
↓
FECHA CARRINHO
↓
ABRE PAGAMENTO
```

Assim a pilha fica:

```text
CATÁLOGO
↓
PAGAMENTO
```

E então:

```text
Cancelar
→ CATÁLOGO
```

e:

```text
Finalizar
→ Venda concluída
→ Nova venda
→ CATÁLOGO
```

automaticamente.

Escolha a implementação mais segura para a arquitetura atual, mas corrija A CAUSA da pilha errada.

==================================================
13. APAGAR CARRINHO CONTINUA INDO PARA CATÁLOGO
===============================================

A correção atual de:

```text
CARRINHO
→ APAGAR
→ CANCELLED
→ CATÁLOGO
```

deve permanecer.

NÃO regredir isso ao alterar a navegação.

==================================================
14. O ESTADO BASE DA VENDA RÁPIDA É O CATÁLOGO
==============================================

Regra definitiva:

```text
entrar na Venda Rápida
→ CATÁLOGO

apagar carrinho
→ CATÁLOGO

cancelar venda
→ CATÁLOGO

finalizar + Nova Venda
→ CATÁLOGO

Back após Venda Concluída
→ CATÁLOGO
```

Carrinho é uma subtela temporária.

Não é destino pós-operação.

==================================================
15. TELA PRINCIPAL CONTINUA SEM SCROLL GLOBAL
=============================================

Preservar o conceito da mudança anterior.

A página principal de Pagamento NÃO deve voltar a usar scroll vertical global.

Continuar com:

* header;
* saldo compacto;
* grid compacto;
* histórico;
* resumo;
* CTA.

Somente o histórico pode ter scroll interno se necessário.

==================================================
16. PAGAMENTOS REALIZADOS
=========================

Manter a área compacta.

Não deixar ela crescer infinitamente.

Histórico pode usar:

`Expanded + ListView`

dentro da própria região.

Continuar mostrando:

* método;
* valor;
* status;
* estorno.

Não alterar ledger nem lógica de estorno.

==================================================
17. RESUMO
==========

Manter:

* Total;
* Pago;
* Falta.

Compactos.

Detalhes adicionais continuam expansíveis.

Não aumentar novamente a altura do rodapé.

==================================================
18. FINALIZAR VENDA
===================

Manter o botão:

`FINALIZAR VENDA`

fixo e acessível quando:

`canFinalize == true`.

Não precisa rolar.

Não alterar a lógica de finalização/idempotência.

==================================================
19. PREPARAÇÃO PARA MESAS
=========================

NÃO implementar pagamentos de Mesa agora.

Mas preservar os componentes:

`shared_payment_widgets.dart`

e evitar novos componentes específicos de QuickSale quando não for necessário.

Estamos prestes a voltar para o novo módulo de Mesas.

Mesa deverá usar OS MESMOS componentes visuais de pagamento.

Portanto:

* PaymentMethodButton;
* PaymentHistoryItem;
* resumo;
* saldo;
* grid;
* header visual;

devem continuar reutilizáveis.

Não duplicar uma futura UI de pagamento para Mesa.

==================================================
20. NÃO ALTERAR
===============

NÃO mexer em:

* idempotência;
* payment attempts;
* pending finalize;
* recovery financeiro;
* ledger;
* reversal;
* regras de pagamento;
* backend financeiro além da análise pontual dos métodos ativos;
* Mesa;
* Comanda legado;
* Stone;
* Cielo;
* PagBank;
* fiscal;
* impressão;
* estoque.

==================================================
21. TESTES
==========

NÃO criar novos testes automatizados nesta missão.

O teste funcional será feito manualmente.

Pode apenas corrigir testes existentes caso alguma mudança necessária faça um teste atual não compilar.

==================================================
22. CHECKS
==========

Executar:

* `flutter analyze`
* `git diff --check`

Não rodar Gradle/Android build.

==================================================
23. CHECKPOINT FINAL
====================

Ao terminar informar objetivamente:

1. por que a mensagem "Edição financeira bloqueada" aparecia;
2. confirmar que o texto foi removido sem remover a proteção;
3. como reduziu FALTA/PAGO;
4. como reduziu os botões;
5. causa do PIX/Crédito não aparecerem;
6. como o grid foi corrigido;
7. quais métodos estão chegando da API;
8. se os defaults inativos permanecem inativos ou são reativados;
9. como ficou OUTROS;
10. causa do header desaparecer/mudar;
11. como tornou o header estável;
12. comportamento do header em tela estreita;
13. causa estrutural de Cancelar voltar para Carrinho;
14. causa estrutural de Nova Venda voltar para Carrinho;
15. como ficou a pilha de navegação;
16. destino após Cancelar Venda;
17. destino após Apagar Carrinho;
18. destino após Nova Venda;
19. destino do Back após Venda Concluída;
20. confirmar que a tela principal continua sem scroll global;
21. componentes preservados para futuro uso em Mesa;
22. resultado do `flutter analyze`;
23. resultado do `git diff --check`;
24. arquivos alterados;
25. resumo objetivo do diff.

DEPOIS PARE.

NÃO INICIE O MÓDULO DE MESAS AINDA.
