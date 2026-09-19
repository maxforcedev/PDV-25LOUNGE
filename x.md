VAMOS RETOMAR O NOVO MÓDULO DE MESAS.

PELO ESTADO ATUAL DO PROJETO, A PARTE OPERACIONAL DE MESAS JÁ ESTÁ IMPLEMENTADA E O PRÓXIMO PASSO É CONCLUIR A PARTE DE PAGAMENTOS.

IMPORTANTE:

A TELA DE PAGAMENTOS DE MESA NÃO DEVE SER UMA NOVA IMPLEMENTAÇÃO PARALELA.

ELA DEVE REUTILIZAR OS MESMOS ELEMENTOS, COMPONENTES E COMPORTAMENTOS QUE JÁ CRIAMOS E VALIDAMOS NA VENDA RÁPIDA.

PARTA DO HEAD ATUAL.

==================================================

1. OBJETIVO
   ==================================================

Implementar o fluxo completo de PAGAMENTO DO NOVO MÓDULO DE MESAS reutilizando a estrutura criada na Venda Rápida.

A arquitetura desejada é:

```text
                    CORE PAYMENT UI
                           │
             ┌─────────────┴─────────────┐
             │                           │
       VENDA RÁPIDA                    MESA
             │                           │
   QuickSale Adapter              Table Adapter
             │                           │
             └──── Shared Payment ───────┘
```

NÃO criar duas experiências diferentes.

Dinheiro, PIX, Crédito, Débito, Outros, histórico, estorno, divisão, pagamento por itens, resumo e confirmação devem usar OS MESMOS elementos.

==================================================
2. NÃO CRIAR UMA CÓPIA DA TELA
==============================

NÃO quero algo como:

`TablePaymentPage`

copiando todo o conteúdo de:

`SharedPaymentPage`.

Evitar duplicação.

Hoje já existem elementos compartilhados como:

* `PaymentBalanceCard`
* `PaymentMethodButton`
* `PaymentHistoryItem`
* `PaymentFinancialSummary`
* `PaymentReversalDialog`
* fluxo de autorização por PIN
* seletor de formas
* entrada de valor
* dinheiro/troco
* divisão

Refatorar apenas o necessário para que esses componentes possam trabalhar tanto com:

`QuickSaleCheckout`

quanto com:

`TableAttendance / TablePayment`.

==================================================
3. CRIAR UM CONTRATO/ADAPTER DE PAGAMENTO
=========================================

Hoje parte do Shared Payment ainda depende diretamente de:

* `QuickSaleCheckout`
* `QuickSaleCheckoutPayment`

Desacoplar a camada visual do domínio da Venda Rápida.

Criar uma abstração equivalente a:

```text
PaymentState / PaymentContext / PaymentAdapter
```

O nome fica a critério da arquitetura.

Esse contrato deve fornecer para a UI:

* total;
* valor pago;
* valor restante;
* status;
* cliente;
* formas de pagamento;
* pagamentos realizados;
* capabilities;
* possibilidade de editar financeiro;
* possibilidade de registrar pagamento;
* possibilidade de pagar por itens;
* possibilidade de finalizar;
* estorno;
* atualização;
* finalização.

E operações como:

```text
recordPayment()
reversePayment()
refresh()
finalize()
updateFinancialContext()
```

NÃO colocar regra financeira dentro desse adapter.

Ele apenas traduz o domínio para a UI compartilhada.

==================================================
4. QUICK SALE NÃO PODE REGREDIR
===============================

Criar um adapter para a Venda Rápida usando o comportamento atual.

Exemplo conceitual:

```text
QuickSalePaymentAdapter
        ↓
SharedPaymentPage
```

A Venda Rápida deve continuar exatamente com:

* pagamento parcial;
* Dinheiro;
* PIX;
* Crédito;
* Débito;
* Outros;
* troco;
* divisão;
* pagamento por itens;
* estorno;
* autorização de estorno;
* motivo opcional;
* histórico;
* finalização;
* navegação já corrigida;
* idempotência;
* recovery.

NÃO alterar comportamento funcional validado da Venda Rápida só para encaixar Mesa.

==================================================
5. CRIAR ADAPTER DA MESA
========================

Criar equivalente a:

```text
TablePaymentAdapter
       ↓
SharedPaymentPage
```

A origem financeira da Mesa deve ser:

* `TableAttendance`
* `TablePayment`
* `TablePaymentAllocation`
* `table_summary()`
* endpoints existentes de Mesa.

A UI NÃO deve fingir que Mesa é um `QuickSaleCheckout`.

Adaptar corretamente os dois domínios.

==================================================
6. BACKEND DE MESA JÁ EXISTE
============================

ANTES DE CRIAR NOVA ROTA OU NOVA REGRA:

REUTILIZE O BACKEND EXISTENTE.

Já existem estruturas para:

* `TableAttendance`
* `TablePayment`
* `TablePaymentAllocation`
* pagamento parcial;
* pagamento por valor;
* pagamento do saldo;
* pagamento por itens;
* divisão igual;
* dinheiro/troco;
* estorno append-only;
* fechamento da Mesa;
* consolidação final em Sale.

NÃO duplicar lógica financeira no Flutter.

==================================================
7. OPÇÕES DE PAGAMENTO DA MESA
==============================

Já existe endpoint equivalente a:

`tables/checkout-options/`

Ele já retorna:

* `payment_methods`
* `cash_sessions`
* `cash_binding_mode`
* `fixed_register`
* `cash_required`
* `fixed_cash_available`

e já usa o mesmo:

`payment_method_presentation()`

da Venda Rápida.

Portanto os mesmos grupos devem funcionar:

```text
DINHEIRO
DÉBITO
PIX
CRÉDITO
OUTROS
```

Nenhum ID hardcodado.

Tudo vindo da API.

==================================================
8. TELA VISUAL DEVE SER A MESMA
===============================

A tela de Mesa deve ter a mesma experiência operacional criada para Venda Rápida:

```text
← PAGAMENTO          CLIENTE / DIVIDIR / ⋮

FALTA                     R$ XX,XX

[ DINHEIRO ] [ DÉBITO  ]
[ PIX      ] [ CRÉDITO ]
[ OUTROS ]

PAGAMENTOS REALIZADOS

✓ Dinheiro                 R$ XX,XX
✓ Crédito                  R$ XX,XX

TOTAL
PAGO
FALTA

[ FINALIZAR / FECHAR MESA ]
```

Sem criar outro design.

Pode mudar somente textos específicos do contexto.

==================================================
9. SEM SCROLL GLOBAL
====================

Preservar a decisão atual da UI:

A tela principal de Pagamento NÃO deve depender de scroll vertical global.

Continuar usando:

* header compacto;
* saldo compacto;
* grid de meios;
* histórico com scroll interno;
* resumo fixo;
* CTA.

==================================================
10. PAGAMENTO POR VALOR
=======================

Mesa já suporta:

`mode = value`

Usar a mesma experiência da Venda Rápida.

Exemplo:

```text
FALTA R$ 100

Dinheiro
↓
Valor aplicado:
R$ 30

Confirmar
```

Resultado:

```text
PAGO  R$ 30
FALTA R$ 70
```

Sem fechar a Mesa.

==================================================
11. PAGAR SALDO
===============

Mesa já suporta:

`mode = remaining`

Quando fizer sentido na UI, permitir pagar exatamente o saldo restante.

Reutilizar o comportamento visual existente.

==================================================
12. PAGAMENTO PARCIAL
=====================

Mesa precisa aceitar múltiplos pagamentos.

Exemplo:

```text
Total      R$ 100
Dinheiro   R$ 20
PIX        R$ 30
Crédito    R$ 50
```

A Mesa só poderá ser fechada quando:

`remaining_balance == 0`

segundo o backend.

==================================================
13. DINHEIRO / TROCO
====================

Reutilizar a MESMA entrada de Dinheiro da Venda Rápida.

Mostrar:

* valor aplicado;
* valor recebido;
* troco.

Exemplo:

```text
VALOR APLICADO
R$ 40

VALOR RECEBIDO
R$ 50

TROCO
R$ 10
```

Mesa já possui:

* `received_amount`
* `change_amount`
* `cash_session`

NÃO recalcular regra financeira no Flutter.

==================================================
14. DIVIDIR IGUAL
=================

Mesa já possui suporte de backend específico para:

`mode = equal_people`

e possui:

* `people_count`
* `equal_split_total`
* `equal_split_people_count`
* `equal_split_cycle`
* `person_number`

A ação:

`DIVIDIR`

deve reutilizar a mesma entrada visual da Venda Rápida.

Para Mesa, quando escolher:

`DIVIDIR IGUAL`

usar o motor oficial da Mesa.

Exemplo:

Mesa R$ 100 / 4 pessoas:

```text
Pessoa 1     R$ 25
Pessoa 2     R$ 25
Pessoa 3     R$ 25
Pessoa 4     R$ 25
```

Respeitar o estado retornado por:

`table_summary()['equal_split']`

Não manter contagem paralela apenas no Flutter.

==================================================
15. PAGAMENTO POR ITENS
=======================

Mesa já possui:

`mode = items`

e:

`TablePaymentAllocation`.

Implementar usando o MESMO fluxo visual de:

`PAGAR POR ITENS`

já existente na Venda Rápida.

Mas os dados vêm dos itens confirmados da Mesa.

Exemplo:

```text
☑ 2x Coca
☑ 1x Pizza
☐ 1x Água
```

Backend deve calcular o valor oficial.

NÃO somar preços manualmente no Flutter para definir valor financeiro final.

==================================================
16. ITENS JÁ PAGOS / PARCIALMENTE PAGOS
=======================================

Respeitar alocações existentes.

Não permitir pagar quantidade superior à disponível.

O backend já possui proteção de:

`table_item_overallocated`

A UI deve refletir quantidade ainda disponível de forma amigável.

==================================================
17. CLIENTE
===========

A Mesa já pode ter cliente.

A tela compartilhada deve mostrar Cliente da mesma forma que Venda Rápida.

Reutilizar:

`SharedCustomerDialog`

quando aplicável.

Não duplicar seletor de cliente.

==================================================
18. DESCONTO / TAXA
===================

Mesa possui contexto financeiro próprio:

* `checkout_discount`
* `checkout_discount_type`
* `checkout_service_fee_waived`

Já existe:

`table-attendances/{id}/checkout-context/`

Usar isso.

Antes do primeiro pagamento:

permitir alterar conforme permissões/autorização.

Depois do primeiro pagamento aplicado:

o contexto financeiro fica bloqueado.

NÃO mostrar mensagem gigante permanente de "edição financeira bloqueada".

Manter a mesma UX da Venda Rápida:

ação indisponível/desabilitada.

==================================================
19. AUTORIZAÇÃO DE DESCONTO/TAXA
================================

Reutilizar o mesmo:

`SharedAuthorizationDialog`

com PIN POS.

Não criar outro modal.

Respeitar as permissões existentes:

* `sales.apply_discount`
* `sales.waive_service_fee`

e o mecanismo de autorização já usado pela Venda Rápida.

==================================================
20. HISTÓRICO DE PAGAMENTOS
===========================

Usar o MESMO componente visual:

`PaymentHistoryItem`

ou sua abstração compartilhada após refatoração.

Exemplo:

```text
PAGAMENTOS REALIZADOS

✓ Dinheiro             R$ 20,00
  Confirmado

✓ PIX                  R$ 30,00
  Confirmado
```

Mostrar:

* método;
* valor;
* recebido/troco quando relevante;
* status;
* estorno;
* motivo quando existir.

==================================================
21. ESTORNO DE MESA
===================

Mesa possui:

`tables.payments.reverse`

O fluxo deve ser O MESMO da Venda Rápida.

Pagamento aplicado:

```text
✓ Dinheiro             R$ 20,00
                           ↩
```

Ao tocar:

```text
ESTORNAR PAGAMENTO?

Dinheiro
R$ 20,00

Motivo (opcional)

[ VOLTAR ]
[ ESTORNAR PAGAMENTO ]
```

==================================================
22. ESTORNO COM PERMISSÃO
=========================

Se operador possui:

`tables.payments.reverse`

executar diretamente após confirmação.

Motivo opcional.

==================================================
23. ESTORNO SEM PERMISSÃO
=========================

NÃO esconder o botão.

Fazer igual à Venda Rápida:

```text
ESTORNAR
↓
não possui permissão
↓
AUTORIZAÇÃO NECESSÁRIA
↓
autorizador
↓
PIN de 6 dígitos
↓
estorno
```

Reutilizar:

* `eligible_pos_authorizers()`
* `validate_pos_authorization()`
* `SharedAuthorizationDialog`
* rate limit;
* auditoria.

A permissão requerida nesse contexto é:

`tables.payments.reverse`

==================================================
24. SE NECESSÁRIO, AJUSTAR BACKEND DO ESTORNO DE MESA
=====================================================

Hoje o endpoint de Mesa aparentemente exige diretamente:

`tables.payments.reverse`

Se necessário, aplicar o mesmo padrão de autorização delegada que acabamos de implementar em:

`sales.payments.reverse`.

NÃO duplicar a infraestrutura.

Generalizar/reutilizar a solução.

==================================================
25. MOTIVO DO ESTORNO
=====================

Motivo continua OPCIONAL.

Se existir:

mostrar no histórico.

Se vazio:

não mostrar linha de motivo.

Mesa já possui:

`reversal_reason`.

Garantir que o model Flutter também carregue isso.

==================================================
26. LEDGER APPEND-ONLY
======================

Não apagar pagamentos.

Estorno gera reversão vinculada por:

`reversal_of`.

Pagamento original continua no histórico.

Manter:

* imutabilidade;
* auditoria;
* idempotência.

==================================================
27. IDEMPOTÊNCIA DE PAGAMENTO DE MESA
=====================================

Preservar:

* `idempotency_key`
* `request_fingerprint`
* proteção de replay.

IMPORTANTE:

O Flutter deve manter a idempotency key durante retry de uma MESMA tentativa.

Não gerar nova chave automaticamente depois de timeout se o resultado for incerto.

Adotar o mesmo padrão robusto que usamos na Venda Rápida.

==================================================
28. ESTADO INCERTO / RETRY
==========================

Mesa deve ter comportamento seguro para:

* timeout;
* queda de conexão;
* resposta 5xx;
* retry.

NUNCA assumir que pagamento falhou apenas porque a resposta não chegou.

Se necessário, criar persistência/recovery equivalente ao padrão da Venda Rápida.

NÃO permitir duplicidade financeira.

==================================================
29. RESUMO FINANCEIRO
=====================

Usar os dados oficiais de:

`table_summary()`

como fonte.

Ele já retorna:

* subtotal;
* promotion_discount_total;
* item_discount_total;
* checkout_discount_total;
* discount_total;
* service_fee_base;
* service_fee_total;
* total_due;
* paid_total;
* remaining_balance;
* equal_split.

A UI deve mostrar de forma compacta:

```text
Total       R$ XX
Pago        R$ XX
Falta       R$ XX
```

E detalhes expansíveis se necessário.

==================================================
30. NÃO RECALCULAR FINANCEIRO NO FLUTTER
========================================

REGRA IMPORTANTE:

O Flutter não é fonte da verdade financeira.

Nunca criar cálculo paralelo de:

* desconto;
* taxa;
* total;
* saldo;
* rateio financeiro;
* pagamento por itens.

Usar resultados oficiais do backend.

==================================================
31. FINALIZAR / FECHAR MESA
===========================

Quando:

`remaining_balance == 0`

habilitar CTA:

`FECHAR MESA`

ou equivalente coerente com a UX.

Usar endpoint existente de fechamento da Mesa.

O fechamento já consolida:

`TableAttendance → Sale`

Não criar nova venda manualmente no Flutter.

==================================================
32. CAIXA NA FINALIZAÇÃO
========================

Respeitar a regra existente de:

`cash_session`.

Se os pagamentos em dinheiro já determinarem a sessão, usar a lógica oficial.

Se o backend solicitar uma sessão para consolidar a venda, usar as opções retornadas.

Não criar regra nova.

==================================================
33. RESULTADO DO FECHAMENTO
===========================

Depois do backend confirmar fechamento:

* atualizar Mesa;
* status CLOSED;
* sair da tela de pagamento;
* voltar para a visão/lista de Mesas;
* atualizar grid de Mesas;
* Mesa deve aparecer disponível conforme estado oficial.

Não voltar para uma tela financeira antiga.

==================================================
34. NAVEGAÇÃO
=============

A navegação de Mesa deve ser responsabilidade do módulo de Mesa.

`SharedPaymentPage` não deve saber que precisa ir para Catálogo ou Lista de Mesas.

Exemplo:

```text
SharedPaymentPage
      ↓
PaymentResult
      ↓
Table module decide destino
```

Venda Rápida:

```text
finalizou
→ Venda concluída
→ Catálogo
```

Mesa:

```text
fechou
→ Mesas
```

==================================================
35. NÃO MISTURAR MESA COM COMANDA LEGADO
========================================

Usar SOMENTE o novo domínio:

`TableAttendance`

NÃO implementar pagamento usando:

* legacy Command;
* AttendanceCommand antigo;
* fluxo de Comanda legado.

Não tocar no módulo legado nesta missão.

==================================================
36. NÃO DUPLICAR API ANTIGA DE COMANDA
======================================

Já existem endpoints antigos de:

`commands/.../payments`

Não usar isso para o novo fluxo de Mesa.

Mesa nova usa:

`TableAttendance`
+
`TablePayment`.

==================================================
37. CAPABILITIES / PERMISSÕES
=============================

Respeitar:

* `tables.payments.view`
* `tables.payments.record`
* `tables.payments.reverse`
* `tables.close`
* permissões financeiras existentes;
* entitlements da filial/tenant.

A UI deve apresentar/desabilitar ações coerentemente.

Não confiar somente na UI.

Backend continua validando.

==================================================
38. COMPONENTES COMPARTILHADOS
==============================

Ao final, quero algo próximo a:

```text
payments/
    shared_payment_page.dart
    shared_payment_widgets.dart
    payment_contract.dart
    quick_sale_payment_adapter.dart
    table_payment_adapter.dart
```

OS NOMES NÃO SÃO OBRIGATÓRIOS.

O importante é a separação.

Não criar arquitetura artificialmente complexa.

==================================================
39. NÃO IMPLEMENTAR PROVIDERS AGORA
===================================

Stone/Cielo/PagBank continuam fora desta missão.

Os botões continuam pagamentos manuais.

Mas a arquitetura compartilhada deve permanecer preparada para providers futuros.

==================================================
40. NÃO ALTERAR
===============

NÃO mexer desnecessariamente em:

* Venda Rápida fora da refatoração necessária;
* estoque;
* impressão;
* produção;
* tickets;
* fiscal;
* Stone;
* Cielo;
* PagBank;
* Platform Admin;
* Comanda legado;
* SaaS;
* billing.

==================================================
41. NÃO CRIAR TESTES AUTOMATIZADOS NOVOS
========================================

O teste funcional será feito manualmente pelo proprietário do projeto.

NÃO gastar esta missão criando bateria de testes Widget/E2E.

Pode ajustar algum teste existente caso a refatoração faça ele deixar de compilar.

==================================================
42. CHECKS
==========

Executar no mínimo:

* `flutter analyze`
* `git diff --check`

Como haverá integração com backend de Mesa:

executar também os checks backend necessários para garantir:

* serializers;
* migrations;
* system check;
* integridade das rotas modificadas.

NÃO fazer alterações aleatórias para corrigir dívidas antigas fora desta missão.

==================================================
43. CENÁRIOS QUE PRECISAM FICAR POSSÍVEIS
=========================================

Ao terminar, a implementação deve permitir manualmente:

### Cenário 1

```text
Mesa R$ 100
↓
Dinheiro R$ 30
↓
PIX R$ 70
↓
Pago R$ 100
↓
Fecha Mesa
```

### Cenário 2

```text
Mesa R$ 100
4 pessoas
↓
Dividir igual
↓
4 pagamentos de R$ 25
↓
Fecha Mesa
```

### Cenário 3

```text
Pizza R$ 60
Coca R$ 10
Coca R$ 10

Pagar por itens
↓
Pizza
↓
R$ 60
↓
Saldo R$ 20
```

### Cenário 4

```text
Pagamento R$ 50 incorreto
↓
Estornar
↓
operador tem permissão
↓
Confirma
↓
saldo volta
```

### Cenário 5

```text
Pagamento R$ 50 incorreto
↓
operador NÃO tem tables.payments.reverse
↓
seleciona autorizador
↓
PIN
↓
estorno
```

### Cenário 6

```text
Dinheiro R$ 40
Recebido R$ 50
↓
Troco R$ 10
```

### Cenário 7

```text
muitos meios de pagamento ativos
↓
OUTROS
↓
lista rolável
↓
seleciona método
```

==================================================
44. CHECKPOINT FINAL
====================

Ao concluir informar:

1. arquitetura usada para compartilhar Pagamentos;
2. qual contrato/adapter foi criado;
3. como Venda Rápida foi adaptada sem regressão;
4. como Mesa foi adaptada;
5. endpoints de Mesa utilizados;
6. como opções de pagamento são carregadas;
7. funcionamento de Dinheiro;
8. funcionamento de PIX;
9. funcionamento de Débito;
10. funcionamento de Crédito;
11. funcionamento de Outros;
12. pagamento parcial;
13. pagar saldo;
14. divisão igual;
15. pagar por itens;
16. histórico;
17. estorno com permissão;
18. estorno com autorização por PIN;
19. motivo opcional;
20. tratamento de `reversal_reason`;
21. idempotência dos pagamentos de Mesa;
22. comportamento em retry/estado incerto;
23. contexto financeiro/desconto/taxa;
24. quando financeiro é bloqueado;
25. resumo Total/Pago/Falta;
26. fechamento da Mesa;
27. destino após fechar Mesa;
28. componentes efetivamente compartilhados;
29. confirmação de que Comanda legado não foi alterado;
30. arquivos alterados;
31. `flutter analyze`;
32. `git diff --check`;
33. checks backend;
34. resumo objetivo do diff.

DEPOIS PARE.

NÃO INICIE STONE/CIELO/PAGBANK.

NÃO INICIE OUTRA FASE.

QUERO PRIMEIRO TESTAR MANUALMENTE O PAGAMENTO DE MESA COMPLETO.
