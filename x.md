# MISSÃO PAY-1 — PROVIDER PAYMENT ↔ QUICK SALE BRIDGE

A fundação PAY-0 foi auditada por completo e está aprovada.

HEAD atual analisado:

`e6e1d32c57afb941d8e643b8a697f1cca637d16e`

Agora vamos conectar a fundação provider-neutral ao motor financeiro REAL da Venda Rápida.

OBJETIVO:

```text
QuickSaleCheckout
        ↓
PaymentIntent
        ↓
PaymentAttempt
        ↓
APPROVED
        ↓
QuickSalePayment
        ↓
PaymentIntent APPLIED
        ↓
finalize_quick_checkout
        ↓
Sale
        ↓
sales.Payment
```

SEM criar segundo motor financeiro.

Não implementar Cielo.
Não implementar Stone.
Não mexer em Flutter.
Não integrar Mesa.
Não mexer em Comandas.

---

# 1. PRINCÍPIO CENTRAL

A camada `payment_integrations` NÃO substitui:

* `QuickSalePayment`;
* `QuickSalePaymentAllocation`;
* `sales.Payment`.

O provider apenas AUTORIZA/CAPTURA externamente.

O pagamento só entra no financeiro CORE quando virar:

`QuickSalePayment`

Portanto:

`APPROVED != APPLIED`

`APPROVED` = provider aprovou.

`APPLIED` = o pagamento aprovado foi gravado com sucesso no ledger CORE.

---

# 2. HARDENING DO QUICK SALE PAYMENT

Hoje `QuickSalePayment` é protegido via `.save()`/`.delete()`, mas ainda pode ser contornado via operações ORM em lote.

Criar QuerySet protegido para:

* `QuickSalePayment`;
* `QuickSalePaymentAllocation`.

Bloquear pelo menos:

* `update()`;
* `delete()`;
* `bulk_update()`;
* `bulk_create()`.

Registros financeiros históricos não podem contornar o fluxo de domínio.

Preservar criação normal via `.objects.create()` usada pelos services.

---

# 3. SOURCE TYPE DO QUICK SALE PAYMENT

Formalizar `QuickSalePayment.source_type`.

Criar choices:

* `MANUAL = 'manual'`;
* `PROVIDER = 'provider'`.

Pagamentos já existentes continuam `manual`.

Alterar label do status APPLIED para algo neutro, não “Manual aplicado”.

---

# 4. VINCULAR QUICK SALE PAYMENT AO ATTEMPT REAL APROVADO

Adicionar em `QuickSalePayment`:

`source_payment_attempt`

como `OneToOneField` para:

`payment_integrations.PaymentAttempt`

com:

* `PROTECT`;
* nullable para pagamentos manuais;
* related_name apropriado.

REGRA:

```text
source_type = MANUAL
→ source_payment_attempt = NULL

source_type = PROVIDER
→ source_payment_attempt obrigatório
```

Para provider payment validar:

* Attempt.status == APPROVED;
* Attempt.intent corresponde ao checkout;
* Intent.origin_type == QUICK_SALE;
* Intent.origin_id == checkout.id;
* Intent.payment_method == QuickSalePayment.payment_method;
* Attempt.amount == QuickSalePayment.amount;
* empresa/filial compatíveis.

Não copiar NSU, autorização, transaction ID etc. para `QuickSalePayment`.

Esses dados continuam no `PaymentAttempt`.

A cadeia será:

```text
QuickSalePayment
→ source_payment_attempt
→ PaymentAttempt
→ PaymentIntent
→ PaymentProviderConnection
→ Provider
```

---

# 5. PAYMENT INTENT PRECISA CONGELAR O CONTEXTO DE APLICAÇÃO

Adicionar no `PaymentIntent` um JSON provider-neutral como:

`application_context`

ou nome equivalente claro.

Ele deve ser estruturalmente imutável após criação.

Também deve fazer parte do fingerprint/idempotência.

Validar como metadata não sensível.

Para Quick Sale deverá congelar pelo menos:

## pagamento por valor

```text
mode = value
amount = 50.00
allocations = []
```

## restante

```text
mode = remaining
amount = saldo congelado naquele momento
allocations = []
```

## itens

```text
mode = items

allocations = [
  {
    item: ID,
    allocated_quantity: "...",
    amount: "..."
  }
]
```

Ordenar/normalizar allocations para fingerprint estável.

O valor autorizado externamente deve ser exatamente o valor que será aplicado depois.

Nunca decidir as allocations somente depois do provider aprovar.

---

# 6. SOMENTE UM INTENT DE PAGAMENTO EXTERNO ABERTO POR QUICK SALE

Criar proteção de banco + service para impedir dois intents concorrentes para o mesmo checkout.

Para QUICK_SALE considerar estados ainda abertos/bloqueantes:

* CREATED;
* READY;
* PROCESSING;
* DECLINED;
* ERROR;
* UNKNOWN;
* APPROVED.

Não considerar bloqueantes:

* CANCELLED;
* APPLIED;
* REVERSED.

Criar `UniqueConstraint` condicional apropriada somente para:

`origin_type = QUICK_SALE`

Não impor ainda semântica de Mesa/Comanda.

Motivo:

não podemos permitir:

```text
Intent A → Cielo R$100
Intent B → Stone R$100
```

simultaneamente para o mesmo saldo.

---

# 7. CORRIGIR SEMÂNTICA DE CANCELLED

Hoje `create_payment_attempt()` aceita retry de Intent CANCELLED.

Corrigir.

CANCELLED deve significar:

> fluxo abandonado definitivamente.

Nova tentativa somente pode partir, conforme aplicável, de:

* READY;
* DECLINED;
* ERROR.

Não permitir retry de:

* CANCELLED;
* UNKNOWN;
* APPROVED;
* APPLIED;
* REVERSED.

Permitir cancelamento explícito de Intent nos estados seguros:

* CREATED;
* READY;
* DECLINED;
* ERROR.

`DECLINED` e `ERROR` continuam podendo receber retry OU serem cancelados.

---

# 8. CRIAR SERVIÇO QUICK SALE → PAYMENT INTENT

Criar um service específico provider-neutral, por exemplo:

`create_quick_sale_payment_intent(...)`

Não usar endpoint Cielo.

Esse service deve:

1. seguir a ordem de locks já usada no Quick Sale:

   * CashSession;
   * QuickSaleCheckout;
   * PaymentIntent quando aplicável;

2. validar:

   * checkout OPEN;
   * cash session OPEN;
   * POS/branch/operator coerentes;
   * PaymentMethod pertencente à empresa;
   * PaymentMethod ACTIVE neste momento;
   * método não ser CASH;
   * saldo restante;
   * inexistência de outro Intent bloqueante;

3. usar as MESMAS regras financeiras existentes do Quick Sale;

4. calcular/congelar:

   * mode;
   * amount;
   * allocations;

5. validar a reserva de estoque antes de iniciar;

6. criar PaymentIntent:

   * origin_type QUICK_SALE;
   * origin_id checkout.id;
   * amount exato;
   * payment_method;
   * provider_connection;
   * terminal;
   * application_context;
   * idempotency;

7. deixar o Intent em READY.

Replay com mesma chave + mesmo fingerprint deve retornar o mesmo Intent.

---

# 9. CRIAR SERVICE PARA INICIAR ATTEMPT DO QUICK SALE

Criar algo como:

`start_quick_sale_payment_attempt(...)`

Esse é o caminho que futuros adapters Cielo/Stone deverão usar para Quick Sale.

Deve fazer atomicamente:

```text
lock CashSession
lock QuickSaleCheckout
lock Intent
↓
validar contexto
↓
proteger reserva de estoque
↓
create_payment_attempt()
↓
Attempt CREATED
↓
Attempt PROCESSING
```

Antes de PROCESSING:

* Provider ACTIVE;
* Connection ACTIVE;
* Terminal ACTIVE, quando existir;
* PaymentMethod ACTIVE;
* cash session OPEN;
* checkout OPEN.

Permitir provider fallback:

Intent originalmente Cielo

Attempt #2 pode usar Stone.

O provider real continua sendo o `PaymentAttempt.provider_connection`.

---

# 10. RESERVA DE ESTOQUE DURANTE COBRANÇA EXTERNA

Este ponto é CRÍTICO.

A reserva padrão expira.

Não podemos:

```text
provider APPROVED
↓
reserva expirou
↓
CORE não consegue aplicar pagamento
```

Ao iniciar efetivamente o Attempt (`PROCESSING`):

validar a reserva.

Se ainda não existe nenhum pagamento aplicado:

pode renovar se necessário.

Depois deixar a reserva sem expiração enquanto houver uma cobrança externa em estado que possa resultar em dinheiro.

Na prática, usar corretamente os primitives existentes:

* `validate_checkout_reservation`;
* `restore_checkout_reservation_expiry`.

Durante:

* PROCESSING;
* UNKNOWN;
* APPROVED;

a reserva deve permanecer protegida.

Se resultado for:

* DECLINED;
* ERROR;
* CANCELLED;

e o checkout NÃO possuir nenhum pagamento APPLIED:

restaurar TTL normal da reserva.

Se já houver pagamento parcial aplicado:

NÃO restaurar expiração, porque o checkout já possui dinheiro comprometido.

---

# 11. RESOLUÇÃO DO ATTEMPT DO QUICK SALE

Criar wrapper provider-neutral, por exemplo:

`resolve_quick_sale_payment_attempt(...)`

Ele usa o `resolve_payment_attempt()` existente.

Não duplicar a state machine.

Para:

* APPROVED;
* DECLINED;
* CANCELLED;
* ERROR;
* UNKNOWN.

Depois aplicar as regras específicas da reserva do Quick Sale descritas acima.

UNKNOWN continua:

* bloqueando novas cobranças;
* bloqueando edição;
* mantendo reserva;
* exigindo reconciliação.

---

# 12. BLOQUEAR ALTERAÇÕES DO CHECKOUT DURANTE INTENT ABERTO

Enquanto existir Intent bloqueante para aquele checkout, impedir:

* `update_quick_checkout`;
* pagamento manual;
* reverse de pagamento manual;
* cancelamento do checkout;
* finalização;
* qualquer alteração de itens/financeiro.

Retornar conflito claro, por exemplo:

`payment_intent_in_progress`

ou equivalente.

Motivo:

não podemos ter:

```text
provider cobrando R$100
```

e simultaneamente:

```text
operador altera produtos
```

ou:

```text
operador registra outros R$100
```

---

# 13. DECLINED / ERROR CONTINUAM BLOQUEANDO ATÉ DECISÃO

Como o Intent possui `application_context` congelado:

após:

* DECLINED;
* ERROR;

o checkout NÃO deve ser liberado automaticamente para edição/manual payment enquanto aquele Intent continuar reutilizável.

O operador poderá:

### opção A

retry do mesmo Intent;

ou

### opção B

cancelar explicitamente o Intent.

Somente após CANCELLED o checkout volta a aceitar fluxo normal.

Isso evita:

```text
Intent R$100 DECLINED
↓
checkout muda
↓
alguém tenta retry do Intent antigo R$100
```

---

# 14. APPLY DO APPROVED NO LEDGER CORE

Criar serviço:

`apply_approved_quick_sale_payment_intent(...)`

ou nome equivalente.

Esse é o ÚNICO caminho de:

```text
PaymentIntent APPROVED
→ APPLIED
```

para Quick Sale.

Deve executar atomicamente:

```text
lock CashSession
lock QuickSaleCheckout
lock approved PaymentAttempt
lock PaymentIntent
lock QuickSalePayment ledger
↓
validar origem/contexto/saldo
↓
criar QuickSalePayment
↓
criar allocations congeladas
↓
vincular approved Attempt
↓
Intent APPLIED
```

Se qualquer etapa falhar:

ROLLBACK de tudo.

Não pode existir:

```text
Intent APPLIED
```

sem um `QuickSalePayment` correspondente.

---

# 15. IDEMPOTÊNCIA DO APPLY

O apply deve ser completamente idempotente.

Sugestão segura:

usar o próprio:

`PaymentIntent.id`

como base da idempotency key do `QuickSalePayment`.

Replay deve:

* encontrar o pagamento provider já criado;
* validar que pertence ao mesmo approved Attempt;
* retornar o mesmo pagamento;
* NÃO criar duplicado.

Constraint OneToOne do `source_payment_attempt` também deve ajudar.

Adicionar teste concorrente/idempotente se razoável.

---

# 16. NÃO PERMITIR TRANSIÇÃO GENÉRICA APPROVED → APPLIED

Após PAY-1:

`transition_payment_intent()` NÃO deve permitir:

`APPROVED -> APPLIED`

genericamente.

Também NÃO permitir genericamente:

`APPLIED -> REVERSED`

Não queremos alguém mudar status sem executar o efeito financeiro real.

Deixar:

```text
APPROVED
```

sem transição pública genérica.

APPLIED deve acontecer somente pelo bridge de aplicação financeira.

REVERSED ficará para futura missão de estorno provider.

---

# 17. PROVIDER PAYMENT NÃO PODE SER DINHEIRO

Provider-integrated payment não deve usar:

`PaymentMethodCode.CASH`.

Dinheiro continua no fluxo manual CORE.

Provider pode futuramente atender:

* PIX;
* CREDIT_CARD;
* DEBIT_CARD;
* FOOD_VOUCHER;
* MEAL_VOUCHER;
* outros métodos compatíveis.

A compatibilidade exata por provider ficará para adapters/capabilities futuros.

---

# 18. REVERSÃO LOCAL DE PROVIDER PAYMENT DEVE SER BLOQUEADA

Hoje:

`reverse_quick_checkout_payment()`

faz reversão local.

Para:

`source_type = PROVIDER`

NÃO permitir reversão local nesta etapa.

Retornar conflito claro, por exemplo:

`provider_reversal_required`

Motivo:

não podemos:

```text
CORE estorna localmente
```

sem:

```text
Cielo/Stone estornar dinheiro externo
```

Estorno provider será implementado depois.

Pagamento MANUAL continua usando fluxo atual normalmente.

---

# 19. CASH SESSION NÃO PODE FECHAR COM PAGAMENTO EXTERNO PENDENTE

Modificar `close_session()` de forma cuidadosa.

Além das verificações existentes, identificar Quick Sale PaymentIntents bloqueantes vinculados aos checkouts daquela sessão.

Bloquear fechamento especialmente quando houver:

* PROCESSING;
* UNKNOWN;
* APPROVED;
* CREATED;
* READY;
* DECLINED;
* ERROR;

enquanto o Intent ainda não tiver sido CANCELLED/APPLIED/REVERSED.

Usar locks consistentes.

Não criar deadlock com Quick Sale.

Preservar ordem existente:

CashSession → QuickSaleCheckout → registros financeiros relacionados.

Adicionar audit metadata do bloqueio.

---

# 20. PROVENIÊNCIA ATÉ SALES.PAYMENT

Adicionar em:

`sales.Payment`

um campo:

`source_quick_sale_payment`

como `OneToOneField`:

* `pos.QuickSalePayment`;
* `PROTECT`;
* null/blank para outros fluxos.

Assim teremos:

```text
Sale
↓
sales.Payment
↓
source_quick_sale_payment
↓
QuickSalePayment
↓
source_payment_attempt
↓
PaymentAttempt
↓
PaymentIntent
↓
Provider
```

---

# 21. FINALIZE QUICK SALE DEVE PASSAR OS SOURCES

Hoje `finalize_quick_checkout()` transforma os QuickSalePayments em payload simples.

Alterar para também passar ao `finalize_sale()` a lista ordenada dos QuickSalePayments de origem.

Adicionar parâmetro específico:

`quick_sale_payment_sources`

ou equivalente.

Não reutilizar `payment_sources` de Command.

Validar:

* mesmo tamanho;
* mesma ordem;
* payment_method igual;
* amount igual;
* received_amount igual;
* checkout/company/branch coerentes;
* status APPLIED;
* não ser reversal.

---

# 22. PAYMENT METHOD DESATIVADO DEPOIS DO PAGAMENTO

Hoje `_prepare_payments()` e `sales.Payment.clean()` exigem método ACTIVE.

Isso é correto para PAGAMENTO NOVO.

Mas não pode impedir materialização de histórico já pago.

Cenário:

```text
Cartão ACTIVE
↓
provider APPROVED
↓
QuickSalePayment APPLIED
↓
admin desativa Cartão
↓
finalize checkout
```

A finalização deve funcionar.

Permitir método inativo SOMENTE quando existir `source_quick_sale_payment` histórico válido.

Não transformar isso em bypass genérico.

Pagamento novo continua exigindo ACTIVE.

---

# 23. SNAPSHOT HISTÓRICO DO PAYMENT METHOD

Quando `sales.Payment` vier de `QuickSalePayment`:

usar os snapshots históricos já existentes:

* `QuickSalePayment.payment_method_name`;
* `QuickSalePayment.payment_method_code`.

Não sobrescrever esses snapshots com nome atual do PaymentMethod se ele mudou depois.

Garantir fidelidade histórica.

---

# 24. PAYMENT CLEAN — VALIDAR SOURCE QUICK SALE

Quando houver:

`source_quick_sale_payment`

validar:

* source pertence à mesma empresa/filial da Sale;
* payment_method corresponde;
* amount corresponde;
* received_amount corresponde;
* source.status == APPLIED;
* source não é reversal;
* provenance OneToOne;
* nenhuma inconsistência financeira.

Não permitir múltiplas proveniências simultâneas no mesmo `sales.Payment`.

Um Payment não deve apontar simultaneamente para:

* CommandPayment;
* AttendancePayment;
* TablePayment;
* QuickSalePayment.

---

# 25. PAYLOAD BACKEND DO QUICK CHECKOUT

Sem mexer no Flutter, preparar payload backend.

Para cada QuickSalePayment expor claramente:

* `source_type`;
* se for provider, identificador do Attempt ou informação não sensível suficiente para rastreio.

Não expor:

* secrets;
* credentials;
* tokens.

Também expor estado do PaymentIntent bloqueante do checkout de forma simples, por exemplo:

```text
payment_integration:
  intent_id
  status
```

Isso será usado futuramente pelo POS para recovery/UI.

Não criar tela Flutter agora.

---

# 26. CANCELAMENTO DE INTENT QUICK SALE

Criar service específico:

`cancel_quick_sale_payment_intent(...)`

Permitido somente quando seguro:

* CREATED;
* READY;
* DECLINED;
* ERROR.

Não cancelar:

* PROCESSING;
* UNKNOWN;
* APPROVED;
* APPLIED.

Ao cancelar:

* Intent → CANCELLED;
* checkout deixa de ficar bloqueado;
* restaurar TTL da reserva quando não houver nenhum pagamento aplicado.

Audit obrigatório.

---

# 27. ORM HARDENING FINAL DO PAYMENT_INTEGRATIONS

A auditoria também mostrou que os QuerySets do PAY-0 bloqueiam `update()`, mas `bulk_create`/`bulk_update` ainda podem contornar `.save()`.

Endurecer:

* PaymentProvider;
* PaymentProviderConnection;
* PaymentTerminal;
* PaymentIntent;
* PaymentAttempt.

Bloquear quando aplicável:

* `bulk_create`;
* `bulk_update`.

Preservar fluxos normais atuais.

Adicionar testes.

---

# 28. NÃO ALTERAR MESA NESTA MISSÃO

NÃO mexer em:

* TableAttendance;
* TablePayment;
* TablePaymentAllocation;
* `record_table_payment`;
* `reverse_table_payment`;
* `close_table_attendance`.

A auditoria identificou hardening futuro para Mesa, mas isso será outra fase.

---

# 29. NÃO ALTERAR COMANDAS

Não mexer em:

* Command;
* AttendanceCommand;
* CommandPayment;
* AttendancePayment;
* fluxos de fechamento;
* telas/endpoints.

Alterações em `sales.Payment` / `finalize_sale` devem preservar os caminhos atuais de Comanda e Mesa sem mudança de comportamento.

---

# 30. NÃO IMPLEMENTAR PROVIDER REAL

Ainda NÃO adicionar:

* Cielo;
* Stone;
* Cielo LIO;
* Deep Link;
* SDK;
* Client ID;
* Access Token;
* callback Android;
* Intent Android;
* Flutter platform channel.

PAY-1 é 100% backend/provider-neutral.

---

# 31. MIGRATIONS

Criar migrations incrementais.

Provavelmente haverá alterações em:

* `payment_integrations`;
* `pos`;
* `sales`.

NÃO editar migrations antigas aplicadas.

Respeitar dependências entre apps.

---

# 32. TESTES OBRIGATÓRIOS

Criar testes direcionados cobrindo pelo menos:

### Provider → Quick Sale

1. criar checkout;
2. criar Intent QUICK_SALE;
3. Intent READY;
4. iniciar Attempt;
5. Attempt PROCESSING;
6. resolver APPROVED;
7. Intent APPROVED;
8. ainda não existe QuickSalePayment;
9. aplicar Intent;
10. cria exatamente 1 QuickSalePayment PROVIDER;
11. Intent APPLIED.

### Idempotência

* repetir apply;
* retorna mesmo QuickSalePayment;
* não duplica ledger.

### Provider fallback

```text
Intent inicial → Provider A
Attempt #1 A → DECLINED
Attempt #2 B → APPROVED
```

QuickSalePayment deve apontar para:

`Attempt #2`

e portanto para Provider B.

### Bloqueios

Com Intent bloqueante:

* update checkout → bloqueado;
* manual payment → bloqueado;
* reverse → bloqueado;
* cancel checkout → bloqueado;
* finalize → bloqueado.

### Declined / Error

* continuam bloqueando;
* retry permitido;
* após cancel explícito, checkout é liberado.

### CANCELLED

* não aceita novo Attempt.

### UNKNOWN

* checkout bloqueado;
* reserva permanece;
* nova cobrança bloqueada;
* reconciliação funciona.

### Estoque

* reserva é protegida ao iniciar PROCESSING;
* DECLINED sem pagamento aplicado restaura TTL;
* ERROR sem pagamento aplicado restaura TTL;
* UNKNOWN mantém reserva;
* APPROVED mantém reserva;
* se já existe pagamento parcial, não restaurar expiração.

### PaymentMethod

* inativo antes da cobrança → bloqueia;
* inativo depois de PROCESSING → resultado APPROVED continua;
* apply continua;
* finalização da Sale continua usando source histórico.

### Proveniência

Após finalizar:

`sales.Payment.source_quick_sale_payment == QuickSalePayment`

e:

`QuickSalePayment.source_payment_attempt == approved Attempt`.

### Reversal

* manual QuickSalePayment continua reversível;
* provider QuickSalePayment → `provider_reversal_required`.

### Concorrência

* dois Intents ativos para o mesmo QuickSaleCheckout → segundo bloqueado;
* duas idempotency keys diferentes não criam duas cobranças concorrentes.

### ORM

* update/bulk update/bulk create indevidos são bloqueados nos históricos relevantes.

---

# 33. TESTE END-TO-END DE DOMÍNIO SEM CIELO

Criar um teste que simule exatamente:

```text
QuickSaleCheckout = R$100
↓
create QuickSale PaymentIntent
↓
READY
↓
Attempt
↓
PROCESSING
↓
APPROVED simulado
↓
Intent APPROVED
↓
apply
↓
QuickSalePayment R$100 PROVIDER
↓
Intent APPLIED
↓
finalize_quick_checkout
↓
Sale FINALIZED
↓
sales.Payment R$100
```

Validar a cadeia inteira:

```text
sales.Payment
→ QuickSalePayment
→ PaymentAttempt
→ PaymentIntent
```

Esse teste é o aceite principal do PAY-1.

---

# 34. AUDITORIA

Registrar eventos importantes:

* quick sale payment intent criado;
* attempt iniciado;
* result recebido;
* intent cancelado;
* provider payment aplicado no QuickSalePayment;
* fechamento de caixa bloqueado por provider payment pendente.

Para operações críticas do bridge, manter o audit dentro da mesma transação externa quando possível.

Não persistir secrets.

---

# 35. TESTES PERMITIDOS

Pode executar SOMENTE testes direcionados relacionados a:

* `payment_integrations`;
* Quick Sale / quick checkout;
* sales finalization afetada por Quick Sale;
* cash close relacionado a Quick Sale/provider.

NÃO executar:

* suíte backend completa;
* Flutter;
* build;
* analyze;
* lint global.

---

# CHECKPOINT FINAL

Ao terminar, informe:

1. models alterados;
2. migrations criadas;
3. services novos;
4. como ficou `application_context`;
5. quais estados bloqueiam o checkout;
6. como funciona retry/cancel;
7. como a reserva de estoque fica protegida;
8. como APPROVED vira QuickSalePayment;
9. como garante idempotência do apply;
10. como ficou `source_type`;
11. como QuickSalePayment aponta para PaymentAttempt;
12. como sales.Payment aponta para QuickSalePayment;
13. como método inativo histórico é tratado;
14. como fechamento de caixa detecta provider pendente;
15. como provider reversal foi bloqueado;
16. testes executados e resultado;
17. arquivos alterados;
18. confirmação explícita de que NÃO alterou Mesa;
19. confirmação explícita de que NÃO alterou Comandas;
20. confirmação explícita de que NÃO alterou Flutter;
21. confirmação explícita de que NÃO implementou Cielo nem Stone.

Depois PARE.

Não avance para PAY-2.
