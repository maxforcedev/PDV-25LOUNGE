# MISSÃO PAY-2.0.1 — FECHAMENTO DO ADAPTER CIELO

HEAD atual analisado:

`0a98819adb2821eff5b953514a277a4c2f997c2a`

O PAY-2.0 criou corretamente:

* adapter registry provider-neutral;
* `CieloSmartAdapter`;
* provider Cielo via migration;
* secrets via `env_or_file()` / Docker Secrets;
* Deep Link encapsulado;
* mapping de PaymentMethod → paymentCode;
* amount em centavos;
* reference por PaymentAttempt;
* parser de callback;
* ProviderPaymentResult;
* integração com `resolve_payment_attempt()`.

Porém a auditoria encontrou 3 bloqueadores e 2 ajustes de contrato antes do PAY-2.1.

Corrigir SOMENTE os pontos abaixo.

NÃO implementar Flutter.
NÃO mexer no AndroidManifest.
NÃO abrir Deep Link real.
NÃO implementar recovery.
NÃO implementar reversal.
NÃO mexer em Mesa.
NÃO mexer em Comandas.
NÃO alterar o motor PAY-1.

---

# 1. CORRIGIR OS CÓDIGOS DE ERRO CIELO

Hoje o parser trata:

```text
responsecode = 1
responsecode = 2
responsecode = 3
responsecode = 4
```

como:

```text
1 → CANCELLED
2 → ERROR
3 → ERROR
4 → ERROR
```

Isso está incompleto.

Na Cielo Smart, cenários de erro podem retornar:

```text
responsecode=0
```

enquanto o conteúdo Base64 de:

`response`

decodifica para JSON como:

```json
{
  "code": 1,
  "reason": "CANCELADO PELO USUÁRIO"
}
```

Ou equivalente para codes 2, 3 e 4.

Portanto:

o parser precisa PRIMEIRO interpretar corretamente o `response`.

---

# 2. ORDEM CORRETA DO PARSER

Implementar fluxo defensivo:

```text
parse_payment_callback()

1. validar Attempt pertence à Cielo
2. interpretar responsecode
3. tentar decodificar response Base64
4. interpretar JSON
5. identificar se JSON é:
   a) erro Cielo
   b) Order/payment
6. normalizar ProviderPaymentResult
```

Não assumir que:

`responsecode`

sozinho representa o erro financeiro.

---

# 3. JSON DE ERRO CIELO

Se o JSON decodificado possuir estrutura de erro:

```text
code
reason
```

mapear:

```text
code = 1
→ PaymentAttempt CANCELLED

code = 2
→ PaymentAttempt ERROR

code = 3
→ PaymentAttempt ERROR

code = 4
→ PaymentAttempt ERROR
```

Preservar:

```text
provider_status_code = code
provider_message = reason sanitizado
```

`reason` deve passar pelo mesmo mecanismo de sanitização já existente.

Não persistir resposta raw.

---

# 4. RESPONSECODE NÃO PODE SOBRESCREVER O JSON REAL

Exemplo:

```text
responsecode = 0

response decoded:
{
    "code": 1,
    "reason": "CANCELADO PELO USUÁRIO"
}
```

Resultado:

```text
CANCELLED
```

NÃO:

```text
UNKNOWN
APPROVED
ERROR GENÉRICO
```

O JSON decodificado é a evidência principal nesse cenário.

---

# 5. RESPONSECODE DE ERRO SEM RESPONSE UTILIZÁVEL

Se existir `responsecode` conhecido de erro e não houver `response` decodificável suficiente:

pode continuar utilizando o mapping seguro de `responsecode`.

Mas NÃO permitir que um `responsecode` aparentemente neutro ignore um JSON de erro válido.

---

# 6. TESTES DE ERRO REAL CIELO

Adicionar fixtures como:

```text
responsecode = 0

response = Base64(
    {
        "code": 1,
        "reason": "CANCELADO PELO USUÁRIO"
    }
)
```

Esperado:

```text
CANCELLED
provider_status_code = "1"
```

Também:

```text
code 2 → ERROR
code 3 → ERROR
code 4 → ERROR
```

Testar reason sanitizado.

---

# 7. PARSER DEVE VALIDAR O PROVIDER DO ATTEMPT

Hoje:

`build_payment_command()`

valida que a connection é Cielo.

Porém:

`parse_payment_callback()`

não valida.

Isso permite conceitualmente:

```text
Attempt Stone
↓
CieloSmartAdapter.parse_payment_callback(...)
↓
APPROVED
```

Isso não pode acontecer.

No início do parser validar:

```text
attempt.provider_connection.provider.code == "cielo"
```

e:

```text
integration_type == "local_deep_link"
```

Reutilizar `_connection_configuration()` ou criar helper semântico melhor.

Se inválido:

```text
cielo_connection_invalid
```

Não retornar UNKNOWN.

É erro de domínio/chamada incorreta do adapter.

---

# 8. TESTE PARSER COM OUTRO PROVIDER

Criar Attempt/provider fake:

```text
provider.code = stone
```

Chamar:

```text
CieloSmartAdapter.parse_payment_callback(...)
```

Esperado:

```text
PaymentIntegrationConflict
code = cielo_connection_invalid
```

---

# 9. CORRIGIR TESTE DE INTEGRAÇÃO QUE DUPLICA PROVIDER CIELO

A migration:

`0004_cielo_smart_provider.py`

já cria:

```text
PaymentProvider(code="cielo")
```

Mas:

`CieloAdapterBridgeTests.setUp()`

faz novamente:

```python
PaymentProvider.objects.create(
    code='cielo',
    ...
)
```

`PaymentProvider.code` é UNIQUE.

Corrigir o teste para reutilizar o provider criado pela migration.

Usar algo como:

```text
PaymentProvider.objects.get(code='cielo')
```

ou `get_or_create()` apenas se houver razão forte.

Preferência:

`get(code='cielo')`

porque o objetivo do teste também deve provar que a migration realmente disponibiliza o provider.

Não mascarar migration ausente.

---

# 10. TESTE DA DATA MIGRATION

Adicionar teste ou garantia direcionada de que após migrations:

```text
PaymentProvider.objects.get(code='cielo')
```

possui:

```text
name = Cielo Smart
integration_type = local_deep_link
```

e capabilities esperadas.

Não criar segundo provider.

---

# 11. VALUE DEVE SEGUIR O CONTRATO OFICIAL CIELO

Hoje:

```python
"value": amount_cents
```

está sendo enviado como inteiro.

Alterar para:

```python
"value": str(amount_cents)
```

Exemplos:

```text
R$ 1,00
→ "100"

R$ 10,50
→ "1050"

R$ 100,00
→ "10000"
```

O helper interno:

```text
amount_to_cents()
```

pode continuar retornando `int`.

A conversão para string ocorre apenas no payload Cielo.

---

# 12. SAFE METADATA PODE CONTINUAR USANDO INTEGER

Em:

```text
safe_metadata.amount_cents
```

pode manter:

```text
1050
```

como inteiro.

Não há necessidade de alterar o contrato interno do CORE.

Apenas o payload Cielo usa string.

---

# 13. TESTE VALUE STRING

No teste que decodifica o Base64:

validar:

```python
payload['value'] == '1050'
```

e também:

```python
isinstance(payload['value'], str)
```

---

# 14. VALIDAR MERCHANTCODE

Hoje `merchant_code` aceita praticamente qualquer string sanitizada.

Restringir ao formato Cielo esperado:

```text
16 dígitos
```

Exemplo válido:

```text
1234567890123456
```

Rejeitar:

```text
abc
123
123456789012345
12345678901234567
1234-5678...
```

Se ausente:

continua válido.

---

# 15. NÃO CONVERTER MERCHANTCODE PARA INTEGER

Preservar como string.

Isso evita:

* perda de zero à esquerda;
* conversões inesperadas;
* mudança de contrato.

---

# 16. TESTES MERCHANTCODE

Adicionar:

```text
merchant_code ausente
→ payload sem merchantCode
```

```text
merchant_code 16 dígitos
→ aceito
```

```text
merchant_code inválido
→ cielo_configuration_invalid
```

---

# 17. NÃO REGREDIR PROTEÇÃO DE SECRETS

Preservar integralmente:

```text
ProviderLaunchCommand.uri
→ repr=False
```

e custom `__repr__`.

Garantir que:

* clientID;
* accessToken;
* Base64;
* URI completa;

não apareçam em:

* `safe_metadata`;
* logs;
* audit;
* exception messages;
* request_metadata;
* response_metadata.

---

# 18. NÃO PERSISTIR RESPONSE RAW

Mesmo após começar a interpretar JSON de erro:

NÃO salvar:

```text
response original
Base64
JSON completo
```

Salvar apenas whitelist:

```text
provider
provider_status
provider_status_code
provider_message sanitizado
order_id quando houver
reference quando houver
terminal quando houver
product quando houver
```

---

# 19. CALLBACK DE SUCESSO CONTINUA IGUAL

Preservar mapping atual:

```text
statusCode 0 → APPROVED
statusCode 1 → APPROVED
statusCode 2 → CANCELLED
```

E preservar:

```text
paymentFields.paymentTransactionId
→ provider_transaction_id
```

```text
Order.id
→ provider_order_id
```

```text
Order.reference
→ provider_reference
```

```text
authCode
→ authorization_code
```

```text
cieloCode
→ nsu
```

Não regredir isso.

---

# 20. CALLBACK APPROVED CONTINUA EXIGINDO IDENTIDADE

Preservar:

```text
statusCode 0/1
+
provider_transaction_id vazio
→ UNKNOWN
```

Nunca aprovar sem identidade externa canônica.

---

# 21. VALIDAR REFERENCE

Preservar:

```text
reference ausente
→ pode continuar avaliação conforme contrato atual

reference presente e diferente
→ UNKNOWN
```

Não associar callback de outra tentativa.

---

# 22. VALIDAR AMOUNT

Preservar:

```text
payment.amount
==
PaymentAttempt.amount em centavos
```

Se divergir:

```text
UNKNOWN
```

Não alterar `Attempt.amount`.

---

# 23. RESULTADO AMBÍGUO

Preservar:

```text
mais de um payment candidato válido
→ UNKNOWN
```

Não selecionar `payments[0]`.

---

# 24. CARD MASK

Preservar proteção contra PAN completo.

Não alterar `_safe_mask()` de forma que permita salvar número completo de cartão.

---

# 25. REGISTRY

Não alterar arquitetura provider-neutral.

Continuar:

```text
provider.code
↓
registry
↓
adapter
```

Não adicionar `if cielo` em services financeiros.

---

# 26. MIGRATION 0004

NÃO editar migration já criada se ela já foi commitada.

Se precisar corrigir alguma característica persistida do provider Cielo:

criar `0005`.

Mas os bloqueadores descritos nesta missão não parecem exigir alteração de schema/provider data.

Portanto:

provavelmente nenhuma migration nova.

---

# 27. NÃO ALTERAR MOTOR FINANCEIRO

NÃO mexer em:

* PaymentIntent machine;
* PaymentAttempt machine;
* QuickSalePayment;
* sales.Payment;
* apply bridge;
* provider fallback;
* provider transaction uniqueness;
* Cash;
* estoque;
* lock order.

---

# 28. NÃO IMPLEMENTAR PAY-2.1

Ainda NÃO criar:

* endpoint POS Cielo;
* endpoint callback;
* Flutter code;
* Android bridge;
* MethodChannel;
* Intent Android;
* Manifest;
* foreground service;
* custom scheme real.

---

# 29. NÃO IMPLEMENTAR RECOVERY

Ainda não implementar:

```text
lio://order
```

---

# 30. NÃO IMPLEMENTAR REVERSAL

Ainda não implementar:

```text
lio://payment-reversal
```

---

# 31. TESTES DIRECIONADOS OBRIGATÓRIOS

Executar somente testes relacionados a:

```text
payment_integrations
test_cielo_adapter
```

Garantir cobertura de:

```text
provider Cielo da migration
registry
credentials missing
secret-safe repr
paymentCode
value string
merchantCode
Deep Link
callback APPROVED
callback PIX
callback CANCELLED statusCode 2
JSON error code 1
JSON error code 2
JSON error code 3
JSON error code 4
responsecode fallback
invalid Base64
invalid JSON
amount mismatch
reference mismatch
missing transaction id
ambiguous payments
parser with non-Cielo Attempt
bridge resolve_payment_attempt
QuickSalePayment não criado automaticamente
```

---

# 32. NÃO EXECUTAR

NÃO executar:

* suíte completa;
* Flutter;
* build;
* analyze;
* lint global.

---

# CHECKPOINT FINAL

Ao terminar informe:

1. como passou a interpretar JSON `{code, reason}`;
2. precedência entre `response` e `responsecode`;
3. mapping final codes 1/2/3/4;
4. como parser valida provider Cielo;
5. como corrigiu teste que duplicava `code='cielo'`;
6. confirmação de que provider da migration é reutilizado;
7. como `value` é serializado;
8. validação de `merchantCode`;
9. confirmação de que secrets continuam protegidos;
10. confirmação de que response raw não é persistido;
11. testes adicionados/ajustados;
12. resultado dos testes direcionados;
13. arquivos alterados;
14. migrations criadas, se houver;
15. confirmação de que NÃO alterou PAY-1;
16. confirmação de que NÃO alterou Cash;
17. confirmação de que NÃO alterou Mesa;
18. confirmação de que NÃO alterou Comandas;
19. confirmação de que NÃO alterou Flutter;
20. confirmação de que NÃO implementou recovery;
21. confirmação de que NÃO implementou reversal;
22. confirmação de que NÃO abriu Deep Link real.

Depois PARE.

NÃO avance para PAY-2.1.
