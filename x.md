TRABALHE SOMENTE NESTA CORREÇÃO NO HEAD ATUAL DA MAIN E DEPOIS PARE.

A última alteração em:

pos/lib/attendance/table_order_item_grouping.dart

melhorou corretamente a assinatura financeira ao remover `net_subtotal`, `promotion_benefit` e outros totais da linha.

PORÉM ainda existe um caso incorreto com desconto manual do tipo `amount`.

==================================================

1. PROBLEMA ATUAL
   ==================================================

Hoje a assinatura inclui diretamente:

manual_discount_intent

Exemplo:

Item A:

1x HEINEKEN R$ 20
manual_discount_intent:
{
"type": "amount",
"value": "10.00"
}

Resultado financeiro:

R$ 10 de desconto em 1 unidade
= R$ 10 de desconto por unidade.

Item B:

2x HEINEKEN R$ 20
manual_discount_intent:
{
"type": "amount",
"value": "10.00"
}

Resultado financeiro:

R$ 10 de desconto nas 2 unidades
= R$ 5 de desconto por unidade.

Hoje a assinatura financeira dos dois fica igual porque considera apenas:

type = amount
value = 10.00

Isso está errado.

Esses dois TableOrderItem NÃO são financeiramente equivalentes e NÃO devem ser agrupados.

==================================================
2. NÃO VOLTAR A USAR TOTAIS BRUTOS DA LINHA
===========================================

NÃO resolver recolocando simplesmente:

* net_subtotal;
* manual_discount;
* promotion_benefit;

brutos na chave.

Isso faria voltar o problema anterior:

1x HEINEKEN sem desconto
2x HEINEKEN sem desconto

não agruparem só porque o total da linha é diferente.

A assinatura precisa comparar CONDIÇÕES FINANCEIRAS POR UNIDADE, quando necessário.

==================================================
3. DESCONTO MANUAL `amount`
===========================

Para:

manual_discount_intent.type == "amount"

e valor diferente de zero:

a equivalência precisa levar em conta o desconto efetivo por unidade.

Exemplo:

A)

1x produto
desconto amount R$ 5

desconto unitário efetivo:
R$ 5

B)

2x produto
desconto amount R$ 10

desconto unitário efetivo:
R$ 5

Esses podem ser financeiramente equivalentes, se todas as demais condições também forem iguais.

Mas:

1x produto
desconto amount R$ 10

versus

2x produto
desconto amount R$ 10

não são equivalentes:

R$10/un
vs
R$5/un.

==================================================
4. QUAL VALOR USAR
==================

Use os dados reais disponíveis em:

TableOrderItem.quantity
TableOrderItem.financialSnapshot

Preferencialmente determine a condição financeira efetiva de maneira segura.

O snapshot possui atualmente campos como:

* manual_discount_intent;
* manual_discount;
* promotion;
* promotion_discount_type;
* promotion_discount_value;
* promotion_benefit;
* net_subtotal;
* participates_in_service_fee;
* participates_in_commission.

Para desconto `amount`, pode ser mais seguro derivar uma assinatura unitária usando o valor financeiro efetivamente aplicado dividido pela quantidade, desde que mantenha precisão monetária adequada.

Exemplo conceitual:

manual_discount_unit =
manual_discount / quantity

NÃO precisa usar exatamente essa implementação.

Mas a chave precisa distinguir corretamente os exemplos acima.

==================================================
5. DESCONTO `percentage`
========================

Para:

manual_discount_intent.type == "percentage"

a própria porcentagem representa a condição financeira.

Exemplo:

1x HEINEKEN
10%

2x HEINEKEN
10%

podem continuar sendo equivalentes caso:

* produto;
* preço unitário;
* promoção;
* modificadores;
* demais condições

também sejam iguais.

Não inclua quantidade apenas por existir desconto percentual.

==================================================
6. SEM DESCONTO
===============

Itens sem desconto devem continuar agrupando independentemente da quantidade da linha.

Exemplo:

1x HEINEKEN R$ 20
sem desconto

2x HEINEKEN R$ 20
sem desconto

Resultado:

3x HEINEKEN

==================================================
7. PROMOÇÕES
============

Preservar a lógica atual da promoção.

O backend trata promoção fixa como benefício por unidade:

promotion.discount_value * item.quantity

Então NÃO é necessário recolocar:

promotion_benefit total

na assinatura apenas para distinguir quantidades.

Continuar considerando os campos estruturais da promoção, como atualmente:

* promotion;
* promotion_name;
* promotion_discount_type;
* promotion_discount_value.

==================================================
8. ASSINATURA FINAL
===================

A assinatura financeira deve representar condições comparáveis por unidade.

Continuar considerando corretamente:

* promotion;
* promotion_name;
* promotion_discount_type;
* promotion_discount_value;
* manual discount de forma semanticamente correta;
* participates_in_service_fee;
* participates_in_commission.

E continuar ignorando totais de linha que mudam exclusivamente pela quantidade.

NÃO inventar campos no modelo/API.

==================================================
9. CENÁRIOS OBRIGATÓRIOS
========================

A)

1x HEINEKEN R$20 sem desconto
2x HEINEKEN R$20 sem desconto

Resultado:
3x HEINEKEN

---

B)

1x HEINEKEN
amount R$10

2x HEINEKEN
amount R$10

Resultado:
DOIS grupos

porque:

R$10/un
vs
R$5/un.

---

C)

1x HEINEKEN
amount R$5

2x HEINEKEN
amount R$10

Resultado:

podem agrupar se o desconto efetivo for:

R$5/un
em ambos

e todas as demais condições forem equivalentes.

---

D)

1x HEINEKEN
percentage 10%

2x HEINEKEN
percentage 10%

Resultado:
podem agrupar.

---

E)

1x HEINEKEN
percentage 10%

1x HEINEKEN
amount R$10

Resultado:
DOIS grupos.

---

F)

mesmo produto e desconto, mas promoções diferentes

Resultado:
DOIS grupos.

---

G)

mesmo produto e financeiro, mas modificadores diferentes

Resultado:
DOIS grupos.

==================================================
10. NÃO ALTERAR
===============

NÃO mexer em:

* distribuição de PaymentAllocationSource;
* Pagar por itens;
* availableQuantity;
* IDs reais;
* Transferir itens;
* seleção de entradas;
* backend de transferência;
* fechamento da Mesa;
* normalize_discount_intent;
* TablePayment ledger;
* CashSession;
* Comanda legado;
* impressão;
* Stone/Cielo/PagBank;
* fiscal.

Essa correção deve ficar concentrada na equivalência financeira compartilhada.

==================================================
11. ALTERAÇÕES FORA DO ESCOPO
=============================

No commit anterior também apareceram alterações em:

frontend/next-env.d.ts
frontend/src/components/sales-pdv.tsx

NÃO faça novas alterações nesses arquivos nesta missão.

Também NÃO reverta automaticamente trabalho que possa pertencer a outra tarefa.

Esta missão deve alterar apenas o necessário para corrigir a equivalência financeira do agrupamento.

==================================================
12. VALIDAÇÃO
=============

Rodar:

flutter analyze
git diff --check

Não criar nova suíte pesada.

Se existir uma forma simples de validar os cenários acima sem introduzir infraestrutura nova, pode fazê-lo.

==================================================
13. CHECKPOINT FINAL
====================

Ao terminar informe:

1. por que `manual_discount_intent.value` puro era insuficiente para `amount`;
2. como passou a determinar equivalência do desconto fixo;
3. confirmação de que 1x/R$10 e 2x/R$10 ficam separados;
4. confirmação de que 1x/R$5 e 2x/R$10 podem agrupar quando equivalem a R$5 por unidade;
5. confirmação de que percentual continua independente da quantidade;
6. confirmação de que itens sem desconto com quantidades diferentes agrupam;
7. confirmação de que promoções diferentes continuam separadas;
8. arquivos alterados;
9. flutter analyze;
10. git diff --check.

DEPOIS PARE.

NÃO INICIE OUTRA TAREFA.
