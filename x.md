# MISSÃO PAY-1.2 — FECHAMENTO DEFINITIVO PRÉ-PROVIDER

O PAY-1.1 corrigiu grande parte dos bloqueadores, mas a auditoria encontrou 4 pontos que ainda precisam ser resolvidos ANTES de qualquer integração real com Cielo/Stone.

HEAD analisado:

`003dc3a26554371f4fad946c94810ff2af51213a`

Objetivo desta missão:

FECHAR DEFINITIVAMENTE o bridge backend de pagamentos externos antes do PAY-2.

Corrigir SOMENTE os pontos abaixo.

NÃO implementar Cielo.
NÃO implementar Stone.
NÃO mexer em Flutter.
NÃO integrar Mesa.
NÃO mexer em Comandas.

---

# 1. TERMINAL REATRIBUÍDO APÓS PROCESSING NÃO PODE BLOQUEAR RESULTADO

Hoje `PaymentTerminal.pos_device` é mutável, o que está correto operacionalmente.

Porém `PaymentIntent.clean()` / `PaymentAttempt.clean()` verificam:

`terminal.pos_device_id == intent.pos_device_id`

inclusive quando estamos persistindo resultado de uma tentativa que JÁ entrou em PROCESSING.

Cenário crítico:

```text
10:00
Terminal T vinculado ao POS A
Attempt → PROCESSING

10:01
Backoffice reatribui Terminal T → POS B

10:02
Provider retorna APPROVED
```

O CORE NÃO pode rejeitar o APPROVED porque o vínculo administrativo atual do terminal mudou.

REGRA:

A compatibilidade:

`terminal.pos_device_id IS NULL OR terminal.pos_device_id == intent.pos_device_id`

deve ser obrigatória:

* na criação do Intent;
* na criação do Attempt;
* no início `CREATED → PROCESSING`.

Depois que o Attempt estiver PROCESSING:

NÃO revalidar vínculo operacional atual do `terminal.pos_device` para registrar:

* APPROVED;
* DECLINED;
* ERROR;
* CANCELLED;
* UNKNOWN;
* reconciliação de UNKNOWN.

A tentativa já iniciada deve preservar seu fato histórico.

IMPORTANTE:

Continuar validando SEMPRE a integridade estrutural:

* terminal pertence à connection da tentativa;
* terminal pertence à branch correta;
* connection pertence à empresa correta.

Apenas o vínculo OPERACIONAL atual `pos_device` deixa de bloquear após PROCESSING.

Adicionar teste:

```text
Terminal → POS A
Attempt PROCESSING
Terminal é reatribuído → POS B
resolve APPROVED
→ deve funcionar
```

Também testar UNKNOWN → APPROVED nesse cenário.

---

# 2. CANCEL_SESSION DEVE BLOQUEAR QUALQUER CHECKOUT ABERTO COM VALOR PAGO

`cancel_session()` agora bloqueia checkout parcialmente pago:

`paid > 0 AND remaining > 0`

Isso não é suficiente.

Cenário crítico:

```text
Checkout R$100
↓
Provider APPLIED R$100
↓
paid = 100
remaining = 0
↓
checkout continua OPEN aguardando finalize
```

Hoje o caixa pode ser CANCELLED.

Depois `finalize_quick_checkout()` não consegue materializar a Sale porque CashSession CANCELLED não é aceita.

Resultado:

dinheiro recebido sem Sale final.

REGRA:

Para `cancel_session()`:

qualquer QuickSaleCheckout OPEN com:

`paid > 0`

deve bloquear o cancelamento da CashSession.

Não importa se:

* pagamento parcial;
* pagamento total;
* manual;
* provider;
* combinação dos dois.

Portanto:

```text
OPEN checkout
paid > 0
→ cash session NÃO pode ser CANCELLED
```

`close_session()` mantém a lógica atual.

Diferença:

CLOSED pode permitir materialização posterior do checkout pago.

CANCELLED NÃO.

Adicionar testes:

1. checkout parcial pago → cancel bloqueado;
2. checkout 100% pago manual → cancel bloqueado;
3. checkout 100% pago provider → cancel bloqueado;
4. checkout sem pagamento/intents → cancel continua permitido.

---

# 3. DUPLICIDADE DE PROVIDER_TRANSACTION_ID NÃO PODE VAZAR INTEGRITYERROR

A constraint criada está correta:

```text
(provider_connection, provider_transaction_id)
UNIQUE
quando provider_transaction_id != ''
```

Manter essa constraint.

Porém o service NÃO deve deixar `IntegrityError` bruto chegar ao caller.

Hoje o teste aceita:

`assertRaises(IntegrityError)`

Isso não é aceitável para provider real.

Cenário:

```text
Attempt A
provider_transaction_id = TX123
```

Depois:

```text
Attempt B
mesma connection
provider_transaction_id = TX123
```

Resultado esperado:

`PaymentIntegrationConflict`

com código explícito, por exemplo:

`provider_transaction_conflict`

ou:

`duplicate_provider_transaction`

NÃO retornar erro bruto de banco.

A operação deve permanecer atômica.

Se a tentativa duplicada estava PROCESSING:

após falha, deve continuar no estado anterior coerente por rollback.

Não marcar Intent como APPROVED.

Não persistir parcialmente result_data.

Adicionar testes:

* duplicate ID na mesma Connection → conflito de domínio;
* Attempt/Intent não avançam;
* mesma string em Connection diferente → permitido.

---

# 4. SALES.PAYMENT COM SOURCE QUICK SALE TAMBÉM DEVE SER SERVICE-ONLY

O caminho oficial de `finalize_sale()` agora valida corretamente que os sources pertencem ao QuickSaleCheckout correto.

Porém ainda existe bypass por criação direta de `sales.Payment`.

Hoje alguém internamente poderia fazer algo equivalente a:

```python
Payment.objects.create(
    sale=sale_b,
    source_quick_sale_payment=payment_checkout_a,
    ...
)
```

e, se empresa/filial/método/valor coincidirem e `checkout.sale` ainda estiver NULL, a validação pode aceitar.

Isso não pode acontecer.

REGRA:

Quando:

`source_quick_sale_payment != NULL`

a criação de `sales.Payment` deve ser permitida SOMENTE pelo fluxo oficial:

`finalize_sale()`.

Usar mecanismo service-only equivalente ao utilizado para provider QuickSalePayment.

Exemplo conceitual:

`_allow_quick_sale_source_creation`

ou mecanismo equivalente.

Fluxos normais SEM `source_quick_sale_payment` continuam inalterados.

Mesa/Comanda continuam funcionando normalmente.

Adicionar teste:

```text
QuickSalePayment do Checkout A
+
Payment.objects.create direto para Sale B
→ bloqueado
```

E:

```text
finalize_quick_checkout()
→ cria sales.Payment normalmente
```

---

# 5. PAYMENT CLEAN CONTINUA VALIDANDO PROVENIÊNCIA

Além do service-only, preservar as validações atuais:

* mesma company;
* mesma branch;
* payment method;
* amount;
* received amount;
* source APPLIED;
* source não estornado;
* apenas uma proveniência por Payment.

Não remover essas proteções.

Service-only é uma camada ADICIONAL.

---

# 6. LOCK ORDER DO START QUICK SALE ATTEMPT

Revisar `start_quick_sale_payment_attempt()`.

Hoje precisamos manter ordem de locks consistente para evitar deadlock com troca de caixa do POS.

O padrão financeiro do POS já usa:

```text
POSDevice
→ active CashSession
→ checkout
→ ledger
```

Garanta que o start do pagamento integrado não faça ordem inversa problemática como:

```text
CashSession
→ Checkout
→ POSDevice
→ CashSession
```

Preferir resolver/bloquear `current_pos_cash_session(..., for_update=True)` ANTES de bloquear checkout/session, seguindo o mesmo princípio usado no pagamento manual.

Depois validar:

`active_session.pk == checkout.cash_session_id`

Não relaxar a segurança.

Adicionar teste concorrencial simples se a suíte permitir; caso não, pelo menos teste funcional de troca de caixa.

---

# 7. TESTES OBRIGATÓRIOS — CASH SESSION

Adicionar testes específicos:

## close_session

* Intent PROCESSING → bloqueado;
* Intent UNKNOWN → bloqueado;
* Intent APPROVED não APPLIED → bloqueado.

## cancel_session

* Intent PROCESSING → bloqueado;
* Intent UNKNOWN → bloqueado;
* Intent APPROVED → bloqueado;
* checkout parcialmente pago → bloqueado;
* checkout totalmente pago → bloqueado;
* provider APPLIED + checkout OPEN → bloqueado.

---

# 8. TESTES OBRIGATÓRIOS — CASH CONTEXT

Cenário:

```text
Checkout criado no Caixa A
POS muda para Caixa B
start_quick_sale_payment_attempt
```

→ bloqueado.

Depois testar:

```text
Checkout Caixa A
Attempt PROCESSING
POS muda para Caixa B
provider APPROVED
```

→ resultado deve ser aceito.

Apply deve continuar usando o CashSession ORIGINAL do checkout.

---

# 9. TESTES OBRIGATÓRIOS — TERMINAL LIFECYCLE

Testar:

```text
Terminal ligado POS A
Intent POS A
Attempt PROCESSING
Terminal reatribuído POS B
APPROVED
```

→ permitido.

E:

```text
novo Attempt POS A usando Terminal agora POS B
```

→ bloqueado.

Isso prova a diferença entre:

* iniciar operação nova;
* concluir operação histórica existente.

---

# 10. TESTES OBRIGATÓRIOS — APPLICATION CONTEXT

Adicionar cobertura direta para:

* mode inválido;
* `value` com allocations;
* `remaining` com allocations;
* item externo;
* item duplicado;
* quantidade <= 0;
* quantidade excedida;
* amount de allocation adulterado;
* soma diferente do Intent.amount.

Nenhum deles pode criar `QuickSalePayment`.

---

# 11. TESTE UNKNOWN COMPLETO

Fluxo obrigatório:

```text
Attempt PROCESSING
↓
UNKNOWN
↓
checkout bloqueado
↓
close_session bloqueado
↓
cancel_session bloqueado
↓
reserva continua protegida
↓
reconcile APPROVED
↓
apply
↓
Intent APPLIED
↓
QuickSalePayment PROVIDER
```

Também validar:

`UNKNOWN → nova tentativa`

continua bloqueado.

---

# 12. TESTE CRASH / RECOVERY

Simular:

```text
Attempt PROCESSING
↓
APPROVED
↓
Intent APPROVED
↓
nenhum QuickSalePayment ainda
```

Depois:

```text
apply_approved_quick_sale_payment_intent()
```

deve criar payment.

Replay:

```text
apply novamente
```

deve retornar o MESMO payment.

Validar exatamente 1 `QuickSalePayment`.

---

# 13. TESTE PARTIAL PAYMENT

Cenário obrigatório:

```text
Checkout R$100
↓
Manual R$30
↓
Provider Intent R$70
↓
APPROVED
↓
APPLIED
```

Resultado:

```text
paid = 100
remaining = 0
```

Validar:

* reserva continua protegida;
* finalização gera 2 `sales.Payment`;
* provider source aponta para o Attempt correto;
* manual source continua manual.

---

# 14. PAYMENTMETHOD DESATIVADO APÓS PROCESSING

Teste:

```text
PaymentMethod ACTIVE
↓
Attempt PROCESSING
↓
PaymentMethod INACTIVE
↓
APPROVED
↓
apply
↓
finalize
```

Tudo deve funcionar.

`sales.Payment.payment_method_name/code`

devem usar os snapshots históricos do `QuickSalePayment`.

Novo pagamento usando esse método INACTIVE continua proibido.

---

# 15. PROVIDER REVERSAL

Adicionar teste direto:

```text
QuickSalePayment source_type=PROVIDER
↓
reverse_quick_checkout_payment()
```

→ conflito:

`provider_reversal_required`

Pagamento manual continua reversível.

---

# 16. CHECKOUT BLOCKING

Adicionar testes para Intent:

* READY;
* PROCESSING;
* DECLINED;
* ERROR;
* UNKNOWN;
* APPROVED.

Enquanto bloqueante:

impedir:

* update checkout;
* manual payment;
* reverse;
* cancel checkout;
* finalize.

Depois:

`Intent CANCELLED`

→ checkout volta ao fluxo normal.

---

# 17. PROVIDER FALLBACK

Preservar e testar:

```text
Intent Provider A
↓
Attempt #1 Provider A → DECLINED
↓
Attempt #2 Provider B → APPROVED
↓
QuickSalePayment
```

O source deve apontar para Attempt #2 / Provider B.

Nunca para a Connection original apenas por estar no Intent.

---

# 18. CALLBACK REPLAY

Preservar comportamento novo:

```text
APPROVED + TX123
↓
APPROVED + TX123 novamente
```

→ replay seguro.

Pode enriquecer campos vazios posteriores.

Não pode trocar:

* provider_transaction_id;
* provider_order_id;
* provider_reference;
* authorization_code;
* nsu.

Resultado final diferente continua conflito.

---

# 19. RESULTADO DE CALLBACK NÃO DEVE REVALIDAR RECURSOS OPERACIONAIS ATUAIS

Além do Terminal/POS, garantir que mudanças depois de PROCESSING em:

* Provider status;
* Connection status;
* Terminal status;
* PaymentMethod status;
* terminal.pos_device;

não impeçam registro do resultado histórico.

Estrutura histórica ainda deve ser coerente.

---

# 20. PAYLOAD

Preservar:

```text
source = provider
source_type = provider
```

para provider payment.

Manual:

```text
source = manual
source_type = manual
```

Não reintroduzir inconsistência.

---

# 21. NÃO ALTERAR MESA

NÃO mexer em:

* TableAttendance;
* TablePayment;
* TablePaymentAllocation;
* serviços/endpoints/telas de Mesa.

---

# 22. NÃO ALTERAR COMANDAS

NÃO mexer em:

* Command;
* AttendanceCommand;
* CommandPayment;
* AttendancePayment;
* serviços/endpoints/telas de Comanda.

Alterações genéricas em `sales.Payment` devem preservar totalmente esses fluxos.

---

# 23. NÃO IMPLEMENTAR PROVIDER REAL

Ainda NÃO adicionar:

* Cielo;
* Stone;
* Deep Link;
* SDK;
* Client ID;
* Access Token;
* callback Android;
* platform channel;
* Flutter.

PAY-1.2 continua backend/provider-neutral.

---

# 24. MIGRATIONS

A migration `0003_paymentattempt_provider_transaction_unique.py` deve ser preservada.

Criar nova migration SOMENTE se realmente necessário.

Não editar migrations já criadas.

---

# 25. TESTES PERMITIDOS

Pode executar SOMENTE testes direcionados relacionados a:

* `payment_integrations`;
* Quick Sale;
* Cash Session afetada pelo bridge;
* sales finalization de Quick Sale.

NÃO executar:

* suíte completa;
* Flutter;
* build;
* analyze;
* lint global.

---

# CHECKPOINT FINAL

Ao terminar, informar:

1. como terminal reatribuído pós-PROCESSING deixou de bloquear resultado;
2. como cancel_session trata checkout 100% pago;
3. como duplicate provider_transaction_id virou conflito de domínio;
4. como sales.Payment com Quick Sale source virou service-only;
5. como ficou a ordem de locks no start do Attempt;
6. testes de close_session;
7. testes de cancel_session;
8. testes de cash context;
9. testes de terminal lifecycle;
10. testes de application_context;
11. teste UNKNOWN;
12. teste crash/recovery;
13. teste partial payment;
14. teste PaymentMethod inativo;
15. teste provider reversal;
16. teste checkout blocking;
17. teste provider fallback;
18. teste callback replay;
19. arquivos alterados;
20. migrations criadas;
21. resultados dos testes direcionados;
22. confirmação explícita de que NÃO alterou Mesa;
23. confirmação explícita de que NÃO alterou Comandas;
24. confirmação explícita de que NÃO alterou Flutter;
25. confirmação explícita de que NÃO implementou Cielo nem Stone.

Depois PARE.

NÃO avance para PAY-2.
