# MISSÃO PAY-2.0.2 — FECHAMENTO HISTÓRICO DO ADAPTER CIELO

HEAD atual analisado:

`216d8b0783403352c4c48f25f2397e8b91a42ba3`

O PAY-2.0.1 corrigiu corretamente:

* JSON de erro `{code, reason}`;
* precedência sobre `responsecode`;
* parser rejeitando provider não-Cielo;
* reutilização do provider da migration;
* `value` como string;
* `merchantCode` com 16 dígitos;
* preservação de secrets;
* mapping APPROVED/PIX/CANCELLED.

Restaram SOMENTE 2 ajustes antes de liberar o PAY-2.1:

1. callback histórico não pode depender da configuração administrativa atual da Connection;
2. corrigir o teste bridge para respeitar `CREATED → PROCESSING → APPROVED`.

Corrigir SOMENTE estes pontos.

NÃO implementar Flutter.
NÃO mexer em AndroidManifest.
NÃO abrir Deep Link real.
NÃO implementar recovery.
NÃO implementar reversal.
NÃO mexer em Cash.
NÃO mexer em Mesa.
NÃO mexer em Comandas.
NÃO alterar o motor PAY-1.

---

# 1. PROBLEMA: PARSER DEPENDE DA CONFIGURAÇÃO ATUAL DA CONNECTION

Hoje:

```python
parse_payment_callback(...)
```

chama:

```python
self._connection_configuration(attempt)
```

Isso valida não apenas identidade Cielo, mas também configuração operacional atual como:

```text
merchant_code
credit_installment_mode
whitelist de keys
```

Isso não pode acontecer ao registrar resultado de uma tentativa já iniciada.

Exemplo crítico:

```text
10:00
Attempt Cielo PROCESSING

Connection.configuration:
{
    "credit_installment_mode": "store"
}

↓
10:01
Admin altera configuração da Connection

↓
10:02
Cielo retorna APPROVED
```

O CORE NÃO pode rejeitar o callback porque a configuração administrativa mudou depois do PROCESSING.

---

# 2. SEPARAR VALIDAÇÃO OPERACIONAL DE VALIDAÇÃO HISTÓRICA

Criar duas responsabilidades claras.

## Operação nova

Para:

```text
build_payment_command()
```

continuar usando validação COMPLETA da configuração atual:

* provider code;
* integration_type;
* merchant_code;
* credit_installment_mode;
* chaves permitidas.

Algo como:

```python
_connection_configuration(attempt)
```

pode continuar existindo para isso.

---

# 3. CALLBACK HISTÓRICO

Para:

```python
parse_payment_callback()
```

criar helper separado, por exemplo:

```python
_assert_cielo_attempt(attempt)
```

ou equivalente.

Ele deve validar apenas a identidade histórica necessária do Attempt.

No mínimo:

```text
attempt.provider_connection.provider.code == "cielo"
```

A `provider_connection` do PaymentAttempt já é estruturalmente imutável.

Não usar a configuração administrativa atual para decidir se um callback histórico pode ser interpretado.

---

# 4. NÃO REVALIDAR CONFIGURAÇÃO ATUAL NO CALLBACK

O parser NÃO deve depender de:

```text
connection.configuration atual
merchant_code atual
credit_installment_mode atual
novas keys adicionadas depois
status atual da connection
status atual do provider
status atual do terminal
PaymentMethod.status atual
terminal.pos_device atual
```

para interpretar o retorno de uma operação já PROCESSING.

Esse comportamento precisa seguir o mesmo princípio já adotado no PAY-1:

```text
início da operação
→ valida recursos/configuração atuais

resultado histórico
→ registra fato da operação que já começou
```

---

# 5. INTEGRATION_TYPE

Não fazer o callback histórico depender de mudança administrativa de `integration_type` se isso puder impedir resultado já iniciado.

Hoje esse campo é estrutural do PaymentProvider e pode não mudar na prática, mas a regra deve ser conceitualmente correta.

Para callback:

o principal vínculo é:

```text
attempt.provider_connection.provider.code == cielo
```

Não transformar mudança administrativa futura em bloqueador de callback histórico.

---

# 6. TESTE: CONFIGURAÇÃO MUDA DEPOIS DE PROCESSING

Adicionar teste:

```text
Connection Cielo válida

↓
PaymentAttempt PROCESSING

↓
alterar PaymentProviderConnection.configuration
```

Por exemplo:

```text
credit_installment_mode:
store → administrator
```

ou outra alteração válida.

Depois:

```text
callback Cielo APPROVED
```

Esperado:

```text
parse_payment_callback()
→ APPROVED
```

E depois:

```text
resolve_payment_attempt()
→ Attempt APPROVED
→ Intent APPROVED
```

---

# 7. TESTE: CONFIGURAÇÃO FICA INVÁLIDA PARA NOVA COBRANÇA

Simular cenário ainda mais forte.

Depois do Attempt estar PROCESSING:

alterar `configuration` de forma que seria considerada inválida pelo builder.

Se o próprio model impedir persistência dessa config inválida, usar uma alteração administrativa válida que demonstre a independência histórica.

O objetivo do teste é provar:

```text
callback não chama _connection_configuration()
```

ou equivalente.

Nova cobrança:

```text
build_payment_command()
```

deve continuar validando a configuração atual normalmente.

---

# 8. PARSER AINDA DEVE REJEITAR ATTEMPT DE OUTRO PROVIDER

Preservar teste:

```text
Attempt provider = stone

CieloSmartAdapter.parse_payment_callback(...)
```

Esperado:

```text
PaymentIntegrationConflict
code = cielo_connection_invalid
```

Não relaxar isso.

---

# 9. CORRIGIR TESTE BRIDGE CREATED → APPROVED

Hoje o teste:

```text
test_parse_then_resolve_approves_attempt_without_creating_quick_sale_payment
```

faz conceitualmente:

```text
create_payment_attempt()
→ CREATED

↓
resolve_payment_attempt(APPROVED)
```

Isso viola o contrato do motor.

A sequência correta é:

```text
create_payment_attempt()
↓
PaymentAttempt CREATED

↓
transition_payment_attempt(
    status=PROCESSING
)

↓
parse callback Cielo

↓
resolve_payment_attempt(
    status=APPROVED
)
```

---

# 10. IMPORTAR TRANSITION_PAYMENT_ATTEMPT NO TESTE

No teste bridge, usar o service oficial:

```python
transition_payment_attempt(
    attempt=attempt,
    status=PaymentAttemptStatus.PROCESSING,
)
```

Não alterar o status diretamente via ORM.

Não criar bypass só para o teste.

---

# 11. TESTE BRIDGE FINAL DEVE PROVAR

Fluxo completo:

```text
PaymentIntent CREATED
↓
READY
↓
PaymentAttempt CREATED
↓
PROCESSING
↓
Cielo callback APPROVED
↓
ProviderPaymentResult APPROVED
↓
resolve_payment_attempt()
↓
PaymentAttempt APPROVED
↓
PaymentIntent APPROVED
```

E confirmar:

```text
QuickSalePayment NÃO existe
```

porque:

```text
APPROVED != APPLIED
```

O adapter não pode aplicar automaticamente.

---

# 12. TESTE CALLBACK HISTÓRICO + CONFIG CHANGE

Criar teste de integração ou adapter apropriado:

```text
Attempt PROCESSING
↓
Connection.configuration muda
↓
parse callback APPROVED
↓
resolve
```

Resultado:

```text
Attempt APPROVED
Intent APPROVED
```

Isso é obrigatório antes de PAY-2.1.

---

# 13. PRESERVAR BUILD PAYMENT

Não alterar o comportamento aprovado de:

```text
build_payment_command()
```

Ele continua validando:

* provider Cielo;
* configuração atual;
* merchantCode;
* installment mode;
* paymentCode;
* credentials;
* items;
* amount;
* callback URL.

---

# 14. PRESERVAR PARSER DE ERROS

Não regredir:

```text
Base64 {code:1}
→ CANCELLED

code 2
→ ERROR

code 3
→ ERROR

code 4
→ ERROR
```

E:

```text
responsecode fallback
```

quando `response` não for utilizável.

---

# 15. PRESERVAR SUCCESS CALLBACK

Não alterar sem necessidade:

```text
statusCode 0 → APPROVED PIX
statusCode 1 → APPROVED
statusCode 2 → CANCELLED
```

Preservar:

* transaction ID;
* order ID;
* reference;
* auth code;
* NSU;
* brand;
* mask;
* installments;
* product;
* terminal.

---

# 16. PRESERVAR UNKNOWN

Continuar retornando UNKNOWN para:

* Base64 inválido;
* JSON inválido;
* payments ausente;
* amount divergente;
* reference divergente;
* transaction ID ausente em APPROVED;
* resultado ambíguo.

Não transformar dúvida em DECLINED.

---

# 17. NÃO ALTERAR SECRETS

Continuar:

```text
clientID/accessToken
→ settings/env_or_file/Docker Secrets
```

Nunca persistir/logar:

* Client-ID;
* Access Token;
* URI Deep Link;
* Base64 request.

---

# 18. NÃO ALTERAR PROVIDER MIGRATION

A migration:

```text
0004_cielo_smart_provider.py
```

já está correta.

NÃO editar.

NÃO criar nova migration para estes ajustes.

---

# 19. NÃO ALTERAR PAY-1

NÃO mexer em:

* PaymentIntent machine;
* PaymentAttempt machine;
* resolve semantics;
* UNKNOWN semantics;
* QuickSalePayment;
* sales.Payment;
* provider fallback;
* cash session;
* estoque;
* lock ordering.

O teste deve se adaptar ao motor existente.

Não o contrário.

---

# 20. NÃO IMPLEMENTAR PAY-2.1

Ainda NÃO criar:

* endpoints POS Cielo;
* Flutter;
* Android Intent;
* MethodChannel;
* callback Activity;
* Manifest;
* foreground service;
* custom scheme final.

---

# 21. NÃO IMPLEMENTAR RECOVERY

Ainda não criar:

```text
lio://order
```

---

# 22. NÃO IMPLEMENTAR REVERSAL

Ainda não criar:

```text
lio://payment-reversal
```

---

# 23. TESTES DIRECIONADOS

Executar SOMENTE:

```text
test_cielo_adapter
payment_integrations tests diretamente relacionados
```

Não executar suíte completa.

---

# 24. TESTES OBRIGATÓRIOS

Garantir pelo menos:

```text
build exige configuração Cielo válida
callback de Attempt Cielo não depende da config atual
callback de provider não-Cielo é rejeitado
CREATED → PROCESSING → APPROVED bridge
QuickSalePayment não é criado no APPROVED
JSON errors continuam funcionando
APPROVED callback continua funcionando
UNKNOWN continua funcionando
```

---

# CHECKPOINT FINAL

Ao terminar informe:

1. qual helper passou a validar callback histórico;
2. diferença entre validação do build e validação do parser;
3. confirmação de que callback não depende de `connection.configuration`;
4. teste de config alterada após PROCESSING;
5. como corrigiu o teste `CREATED → PROCESSING → APPROVED`;
6. confirmação de que `transition_payment_attempt()` oficial foi usado;
7. confirmação de que QuickSalePayment não é criado automaticamente;
8. testes adicionados/ajustados;
9. resultado dos testes direcionados;
10. arquivos alterados;
11. migrations criadas — esperado: nenhuma;
12. confirmação de que NÃO alterou PAY-1;
13. confirmação de que NÃO alterou Cash;
14. confirmação de que NÃO alterou Mesa;
15. confirmação de que NÃO alterou Comandas;
16. confirmação de que NÃO alterou Flutter;
17. confirmação de que NÃO implementou recovery;
18. confirmação de que NÃO implementou reversal;
19. confirmação de que NÃO abriu Deep Link real.

Depois PARE.

NÃO avance para PAY-2.1.
