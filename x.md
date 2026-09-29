# MISSÃO PAY-1.4 — ÚLTIMO AJUSTE DO FALLBACK MULTI-PROVIDER

HEAD atual analisado:

`50b88686830384506c3a3d3b952ad5b755a5a287`

O PAY-1.3 corrigiu corretamente:

* transições históricas após reatribuição de Terminal;
* cancelamento de Intent;
* ordem de locks `POSDevice → CashSession`;
* abertura, seleção e fechamento de caixa no POS.

Restou SOMENTE um caso funcional antes de liberar o PAY-2 / Cielo:

**retry/fallback usando outro provider/terminal após o terminal original do Intent ter sido reatribuído.**

Corrigir SOMENTE esse ponto.

NÃO implementar Cielo.
NÃO implementar Stone.
NÃO mexer em Flutter.
NÃO mexer em Mesa.
NÃO mexer em Comandas.

---

# 1. PROBLEMA ATUAL

Hoje `create_payment_attempt()` faz:

```python
_save_intent_status(
    intent,
    PaymentIntentStatus.PROCESSING,
    validate_terminal_pos_binding=True,
)
```

antes de criar o novo `PaymentAttempt`.

Isso revalida:

`PaymentIntent.terminal`

ou seja, o terminal ORIGINAL armazenado no Intent.

Porém um retry pode usar:

* outro provider;
* outra connection;
* outro terminal;
* ou nenhum terminal.

Cenário:

```text
Intent
Provider inicial = Cielo
Terminal original = Cielo T1
POS = A

↓
Attempt #1
Cielo T1
DECLINED

↓
administrativamente
Cielo T1 é reatribuído para POS B

↓
retry/fallback
Provider = Stone
Terminal = Stone T2
POS = A
```

Stone T2 é perfeitamente válido para POS A.

Porém, antes de criar Attempt #2, o sistema tenta mover o Intent para PROCESSING e revalida o terminal histórico T1.

Como T1 agora pertence ao POS B:

```text
Intent → PROCESSING
↓
valida T1
↓
falha
```

O fallback válido nunca é criado.

---

# 2. REGRA CORRETA

`PaymentIntent.terminal` representa a configuração inicial/original do Intent.

O terminal OPERACIONAL de cada tentativa é:

`PaymentAttempt.terminal`.

Portanto:

ao iniciar uma NOVA tentativa, a validação Terminal ↔ POS deve ser feita sobre o terminal que efetivamente será usado pelo novo `PaymentAttempt`.

Não sobre o terminal histórico original do Intent.

---

# 3. AJUSTAR `create_payment_attempt()`

Ao mover:

```text
READY / DECLINED / ERROR
→ PROCESSING
```

não revalidar o terminal histórico do Intent.

Ou seja, conceitualmente:

```python
_save_intent_status(
    intent,
    PaymentIntentStatus.PROCESSING,
    validate_terminal_pos_binding=False,
)
```

Depois criar:

```python
attempt = PaymentAttempt(
    ...
    terminal=terminal_real_da_tentativa,
)
```

E deixar:

`PaymentAttempt.clean() / save()`

validar o terminal efetivamente selecionado.

---

# 4. NÃO RELAXAR A VALIDAÇÃO DA NOVA TENTATIVA

O novo `PaymentAttempt` continua obrigatoriamente validando:

* provider connection pertence à company;
* connection é válida para branch;
* provider ACTIVE no início;
* connection ACTIVE no início;
* terminal ACTIVE no início;
* terminal pertence à connection;
* terminal pertence à branch;
* se `terminal.pos_device != NULL`:
  `terminal.pos_device == intent.pos_device`;
* PaymentMethod ACTIVE no início;
* amount == Intent.amount.

Nada disso deve ser removido.

---

# 5. TRANSAÇÃO DEVE FAZER ROLLBACK SE O NOVO TERMINAL FOR INVÁLIDO

O fluxo deve continuar atômico.

Exemplo:

```text
Intent DECLINED
↓
tenta novo Attempt
↓
Intent temporariamente → PROCESSING
↓
novo terminal é inválido
↓
PaymentAttempt.save() falha
↓
ROLLBACK
```

Resultado final:

```text
Intent continua DECLINED
nenhum Attempt novo criado
```

Adicionar teste explícito para isso.

---

# 6. FALLBACK VÁLIDO DEVE FUNCIONAR

Adicionar teste:

```text
Intent inicial:
Provider A
Terminal A1
POS A

↓
Attempt #1
DECLINED

↓
Terminal A1 é reatribuído → POS B

↓
criar Attempt #2:
Provider B
Terminal B1
POS A
```

B1 pertence corretamente ao POS A.

Resultado esperado:

```text
Attempt #2 CREATED
↓
PROCESSING
↓
APPROVED
```

e depois:

```text
QuickSalePayment
→ source_payment_attempt = Attempt #2
```

Provider real do pagamento:

`Provider B`.

---

# 7. RETRY USANDO O TERMINAL ORIGINAL AGORA INVÁLIDO DEVE CONTINUAR BLOQUEADO

Cenário:

```text
Intent original:
Terminal T1 / POS A

↓
Attempt #1 DECLINED

↓
T1 é reatribuído → POS B

↓
retry sem passar outro terminal
```

Como `_UNSET` reutiliza o terminal original T1:

o novo `PaymentAttempt` deve falhar.

Isso é correto.

Validar:

```text
Intent permanece DECLINED
Attempt #2 NÃO existe
```

---

# 8. FALLBACK SEM TERMINAL DEVE FUNCIONAR QUANDO O PROVIDER PERMITIR

Preservar a semântica já existente:

```python
terminal=None
```

deve significar explicitamente:

**esta tentativa não usa terminal vinculado.**

Não confundir com `_UNSET`.

Teste:

```text
Intent inicial com Terminal T1
Attempt #1 DECLINED
T1 depois incompatível
↓
Attempt #2 com outra Connection
terminal=None
```

Se todas as outras regras forem válidas:

→ deve criar a tentativa normalmente.

---

# 9. PRESERVAR `_UNSET`

A diferença deve continuar sendo:

```text
terminal=_UNSET
→ reutiliza intent.terminal

terminal=None
→ tentativa explicitamente sem terminal

terminal=T2
→ utiliza T2
```

Não alterar esse contrato.

---

# 10. TESTE PROVIDER FALLBACK COMPLETO

Adicionar ou ampliar o teste existente para provar:

```text
Intent Provider A
Terminal A1

Attempt #1 A
→ DECLINED

A1 reatribuído para outro POS

Attempt #2 Provider B
Terminal B1 válido
→ APPROVED

apply
↓
QuickSalePayment
→ Attempt #2
→ Provider B
```

Não deve apontar para:

* Provider A;
* Terminal A1;
* connection original apenas porque está no Intent.

---

# 11. NÃO ALTERAR RESULTADOS HISTÓRICOS

Preservar tudo que PAY-1.3 já corrigiu:

depois de PROCESSING:

mudanças administrativas em:

* Provider.status;
* Connection.status;
* Terminal.status;
* PaymentMethod.status;
* Terminal.pos_device;

não podem impedir:

* APPROVED;
* DECLINED;
* ERROR;
* UNKNOWN;
* reconciliação.

---

# 12. NÃO ALTERAR LOCK ORDER

Preservar exatamente a ordem corrigida:

```text
POSDevice
→ CashSession
→ QuickSaleCheckout
→ PaymentIntent
→ PaymentAttempt
→ QuickSalePayment
```

Não mexer novamente em:

* POSCashSessionOpenView;
* POSCashSessionSelectView;
* POSCashSessionCloseView;

a menos que seja estritamente necessário por regressão comprovada.

Esta missão NÃO é sobre Cash.

---

# 13. NÃO ALTERAR OUTROS COMPONENTES

NÃO mexer em:

* QuickSalePayment;
* sales.Payment;
* application_context;
* provider_transaction_id;
* callback replay;
* reversal;
* CashSession rules;
* estoque/reservas;
* Mesa;
* Comandas;
* Flutter.

---

# 14. MIGRATIONS

Não há alteração de schema esperada.

NÃO criar migration sem necessidade real.

NÃO editar migrations anteriores.

---

# 15. TESTES PERMITIDOS

Pode executar SOMENTE testes direcionados de:

* `payment_integrations`;
* Quick Sale provider bridge.

NÃO executar:

* suíte completa;
* Flutter;
* build;
* analyze;
* lint global.

---

# CHECKPOINT FINAL

Ao terminar informe:

1. como `create_payment_attempt()` deixou de validar o terminal histórico do Intent;
2. onde o terminal REAL da tentativa continua sendo validado;
3. teste de fallback com outro provider + outro terminal;
4. teste de retry com terminal original incompatível;
5. teste de `terminal=None`;
6. confirmação de rollback quando novo terminal é inválido;
7. confirmação de que QuickSalePayment aponta para o Attempt aprovado correto;
8. arquivos alterados;
9. migrations criadas, se houver;
10. resultado dos testes direcionados;
11. confirmação de que NÃO alterou Cash;
12. confirmação de que NÃO alterou Mesa;
13. confirmação de que NÃO alterou Comandas;
14. confirmação de que NÃO alterou Flutter;
15. confirmação de que NÃO implementou Cielo nem Stone.

Depois PARE.

NÃO avance para PAY-2.
