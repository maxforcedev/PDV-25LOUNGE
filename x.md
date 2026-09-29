# MISSÃO PAY-2.0 — CIELO SMART ADAPTER BACKEND

HEAD BASE:

`8e126a816773d6f169455854df0206aedd099fa8`

O bridge provider-neutral PAY-0 → PAY-1.4 está ENCERRADO e aprovado.

Agora vamos implementar o primeiro provider real:

`CIELO SMART`

Nesta missão implementar SOMENTE a camada backend/provider adapter.

NÃO mexer em Flutter.
NÃO mexer no AndroidManifest.
NÃO abrir Deep Link real.
NÃO chamar emulador.
NÃO implementar estorno ainda.
NÃO implementar recovery ainda.
NÃO mexer em Mesa.
NÃO mexer em Comandas.
NÃO alterar o motor financeiro.

---

# 1. PRINCÍPIO

A Cielo NÃO cria outro motor de pagamento.

Fluxo permanece:

```text
QuickSaleCheckout
↓
PaymentIntent
↓
PaymentAttempt
↓
Cielo Adapter
↓
resultado Cielo
↓
resolve_payment_attempt()
↓
APPROVED
↓
apply_approved_quick_sale_payment_intent()
↓
QuickSalePayment
↓
sales.Payment
```

Não criar:

* CieloPayment;
* CieloTransaction financeira;
* CieloSale;
* CieloQuickSalePayment.

Toda evidência externa continua em:

`PaymentAttempt`.

---

# 2. CRIAR ARQUITETURA DE ADAPTERS DE PROVIDER

Criar estrutura provider-neutral, por exemplo:

```text
payment_integrations/
    providers/
        __init__.py
        base.py
        registry.py
        cielo.py
```

Criar interface/contrato para adapters.

Exemplo conceitual:

```text
PaymentProviderAdapter
    provider_code
    build_payment_command(...)
    parse_payment_callback(...)
```

Não espalhar:

```python
if provider.code == "cielo":
```

pelos services financeiros.

Utilizar registry:

```text
provider.code
↓
adapter registry
↓
CieloSmartAdapter
```

Preparar para:

* Stone;
* Getnet;
* Rede;
* Mercado Pago;
* futuros providers.

---

# 3. PROVIDER CIELO

Criar provider global:

```text
code = cielo
name = Cielo Smart
integration_type = local_deep_link
```

Capabilities seguras:

```text
payment = true
reversal = true
recovery = true
enabled_products = true
terminal_info = true
```

Pode incluir métodos conhecidos:

* credit_card;
* debit_card;
* pix;
* food_voucher;
* meal_voucher.

Não afirmar que todos estão habilitados para todos os estabelecimentos.

Isso será descoberto futuramente via:

`lio://enabledproducts`.

Criar DATA MIGRATION incremental para garantir o provider Cielo.

NÃO excluir provider no reverse da migration se isso puder quebrar histórico.

---

# 4. CREDENCIAIS CIELO NÃO VÃO PARA O BANCO

A documentação Cielo exige:

* Client-ID;
* Access Token.

Esses dados NÃO podem entrar em:

* PaymentProvider.configuration;
* PaymentProviderConnection.configuration;
* PaymentTerminal.metadata;
* PaymentAttempt metadata;
* AuditLog;
* logs;
* responses administrativas.

O CORE já possui:

`env_or_file()`

com suporte a Docker Secrets.

Usar isso.

Adicionar configurações opcionais:

```text
CIELO_SMART_CLIENT_ID
CIELO_SMART_ACCESS_TOKEN
```

com suporte automático:

```text
CIELO_SMART_CLIENT_ID_FILE
CIELO_SMART_ACCESS_TOKEN_FILE
```

IMPORTANTE:

a aplicação NÃO pode deixar de subir caso Cielo não esteja configurada.

As credenciais só são obrigatórias quando o adapter Cielo realmente for utilizado.

Criar resolver específico, por exemplo:

```text
get_cielo_credentials()
```

Se faltarem:

```text
cielo_credentials_missing
```

Nunca imprimir os valores.

---

# 5. CONFIGURAÇÃO NÃO SENSÍVEL DA CONNECTION

`PaymentProviderConnection.configuration`

pode armazenar SOMENTE opções não sensíveis da Cielo.

Suportar inicialmente, se necessário:

```text
merchant_code
credit_installment_mode
```

`merchant_code` deve permanecer opcional.

`credit_installment_mode` pode aceitar:

```text
store
administrator
bank
```

Mapeando para:

```text
store
→ CREDITO_PARCELADO_LOJA

administrator
→ CREDITO_PARCELADO_ADM

bank
→ CREDITO_PARCELADO_BNCO
```

Default inicial:

`store`.

Validar whitelist.

Não armazenar Client-ID/Access Token.

---

# 6. MAPEAMENTO PAYMENTMETHOD → PAYMENTCODE

Implementar no `CieloSmartAdapter`.

## Débito

CORE:

```text
DEBIT_CARD
```

Cielo:

```text
DEBITO_AVISTA
installments = 0
```

## Crédito à vista

CORE:

```text
CREDIT_CARD
installments ausente / 0 / 1
```

Cielo:

```text
CREDITO_AVISTA
installments = 0
```

## Crédito parcelado

CORE:

```text
CREDIT_CARD
installments > 1
```

Cielo conforme configuração:

```text
CREDITO_PARCELADO_LOJA
CREDITO_PARCELADO_ADM
CREDITO_PARCELADO_BNCO
```

## PIX

CORE:

```text
PIX
```

Cielo:

```text
PIX
installments = 0
```

## Vale alimentação

CORE:

```text
FOOD_VOUCHER
```

Cielo:

```text
VOUCHER_ALIMENTACAO
```

## Vale refeição

CORE:

```text
MEAL_VOUCHER
```

Cielo:

```text
VOUCHER_REFEICAO
```

## CASH

Nunca permitido.

Retornar conflito provider-specific claro.

---

# 7. NÃO ASSUMIR QUE PAYMENTCODE ESTÁ HABILITADO

O mapping acima representa o produto solicitado.

Não significa que o EC Cielo possui aquele produto habilitado.

PAY-2.0 apenas monta o request.

A validação contra:

`enabledproducts`

será implementada em etapa posterior.

Deixar arquitetura preparada para receber uma lista de produtos habilitados.

---

# 8. VALUE EM CENTAVOS

Criar helper rigoroso:

```text
Decimal('100.00')
→ 10000
```

Nunca usar float.

Rejeitar:

* valores <= 0;
* precisão inválida;
* arredondamento implícito inesperado.

O valor enviado à Cielo deve ser exatamente:

`PaymentAttempt.amount`.

---

# 9. REFERENCE CIELO

Usar referência determinística baseada no Attempt.

Sugestão:

```text
CORE-{PaymentAttempt.id}
```

Essa referência deve permitir correlacionar:

```text
CORE PaymentAttempt
↔
Cielo Order
```

Não usar:

* número sequencial local frágil;
* horário;
* random independente do Attempt.

A mesma tentativa sempre produz a mesma reference.

---

# 10. BUILD DO PAYMENT REQUEST

Implementar algo como:

```text
CieloSmartAdapter.build_payment_command(
    attempt,
    callback_url,
    items,
    installments=0,
)
```

O JSON Cielo deve conter:

```text
clientID
accessToken
reference
merchantCode se configurado
installments
items
paymentCode
value
```

Não adicionar campos inventados.

---

# 11. ITENS CIELO

Nesta missão NÃO tentar resolver ainda toda a projeção do catálogo Quick Sale → itens Cielo.

O adapter deve receber:

`items`

já normalizados.

Validar que:

* é lista;
* não está vazia;
* cada item possui:

  * name;
  * quantity;
  * sku;
  * unitOfMeasure;
  * unitPrice;
* valores são serializáveis;
* `unitPrice` usa centavos;
* quantity é positiva.

A documentação da Cielo exige itens no pedido.

A transformação real dos snapshots do Quick Sale para essa estrutura será feita quando integrarmos o fluxo POS.

Não criar item fake único `"Venda CORE"` nesta fase.

---

# 12. GERAR DEEP LINK

Gerar o comando Deep Link da Cielo:

```text
lio://payment
```

com:

```text
request=<JSON Base64>
urlCallback=<callback_url>
```

Usar encoding correto de query string.

Não concatenar valores sem escaping.

O JSON deve ser serializado deterministicamente antes do Base64 quando possível.

---

# 13. O DEEP LINK CONTÉM CREDENCIAL — PROIBIDO LOGAR

O URI gerado contém Base64 com:

* Client-ID;
* Access Token.

Portanto:

NUNCA registrar em:

* AuditLog;
* logger;
* exceptions;
* repr de objeto;
* response debug;
* metadata do Attempt.

Se criar objeto como:

```text
ProviderLaunchCommand
```

o `repr()` NÃO deve imprimir o URI secreto.

Pode retornar:

```text
operation = payment
uri = <secret-bearing>
safe_metadata = {
    provider: cielo,
    payment_code: ...,
    amount: ...,
    reference: ...
}
```

Apenas `safe_metadata` pode ser auditada.

---

# 14. NÃO PERSISTIR O REQUEST RAW

Não salvar:

* JSON Cielo contendo credenciais;
* Base64 request;
* URI completa.

No `PaymentAttempt.request_metadata` salvar apenas informações seguras, por exemplo:

```text
provider = cielo
payment_code
installments
reference
amount_cents
merchant_code_present = true/false
```

Nunca o merchant credential/token.

---

# 15. PARSER DO CALLBACK CIELO

Implementar:

```text
CieloSmartAdapter.parse_payment_callback(...)
```

Receber os valores do callback já capturados pelo app futuramente:

```text
response
responsecode
```

O campo:

`response`

vem em Base64.

Decodificar:

```text
Base64
→ UTF-8
→ JSON
```

Tratar defensivamente:

* Base64 inválido;
* UTF-8 inválido;
* JSON inválido;
* estrutura inesperada;
* resposta vazia.

Nunca lançar exceção não controlada que faça o caller assumir pagamento recusado.

Resposta não comprovável deve produzir resultado:

`UNKNOWN`

ou conflito provider-specific seguro.

---

# 16. ERROS CIELO

A documentação Deep Link define:

```text
code = 1
Cancelado pelo usuário

code = 2
Erro genérico

code = 3
Erro no pagamento

code = 4
Erro de autenticação
```

Mapear inicialmente:

```text
1 → PaymentAttempt CANCELLED

2 → ERROR
3 → ERROR
4 → ERROR
```

Não mapear automaticamente erro 3 para DECLINED sem evidência documental suficiente.

Preservar:

```text
provider_status_code
provider_message
```

de forma sanitizada.

---

# 17. CALLBACK DE SUCESSO

No callback de sucesso a Cielo retorna uma Order com:

```text
id
reference
payments[]
```

O Payment contém dados como:

```text
authCode
brand
cieloCode
externalId
installments
mask
terminal
paymentFields
```

E `paymentFields` possui, entre outros:

```text
paymentTransactionId
statusCode
productName
numberOfQuotas
bin
```

---

# 18. PROVIDER_TRANSACTION_ID CANÔNICO

Para Cielo usar prioritariamente:

```text
payment.paymentFields.paymentTransactionId
```

como:

`PaymentAttempt.provider_transaction_id`.

Não usar NSU como transaction ID.

Não usar authCode como transaction ID.

Para APPROVED exigir identificador canônico.

Se callback aparentemente aprovado não possuir identidade externa suficiente:

→ NÃO marcar APPROVED.

Retornar:

`UNKNOWN`

para recovery posterior.

---

# 19. MAPEAMENTO CIELO → PAYMENTATTEMPT

Mapear:

```text
Cielo Order.id
→ provider_order_id

Cielo Order.reference
→ provider_reference

paymentFields.paymentTransactionId
→ provider_transaction_id

payment.authCode
→ authorization_code

payment.cieloCode
→ nsu

payment.brand
→ card_brand

payment.mask ou paymentFields.bin
→ card_mask

payment.installments / numberOfQuotas
→ installments

payment.terminal
→ terminal_external_id

paymentFields.productName
→ payment_product

paymentFields.statusCode
→ provider_status_code
```

`provider_status` pode receber classificação Cielo normalizada.

`provider_message` apenas texto seguro e limitado.

---

# 20. STATUSCODE CIELO

A documentação informa:

```text
statusCode 0 = pagamento PIX
statusCode 1 = pagamento autorizado
statusCode 2 = cancelamento
```

Portanto:

```text
0 → APPROVED
1 → APPROVED
2 → CANCELLED
```

Mas antes de APPROVED validar:

* amount;
* reference;
* transaction ID;
* estrutura.

---

# 21. VALIDAR AMOUNT

O pagamento Cielo escolhido precisa possuir:

```text
payment.amount == PaymentAttempt.amount em centavos
```

Se for diferente:

NÃO aprovar.

Retornar conflito de integridade ou UNKNOWN conforme arquitetura escolhida.

Nunca ajustar o valor do CORE com base no callback.

CORE continua sendo fonte da verdade do valor esperado.

---

# 22. VALIDAR REFERENCE

Quando a Cielo retornar:

`Order.reference`

e ela existir:

deve ser exatamente a reference esperada daquele Attempt.

Se apontar para outra tentativa:

NÃO aprovar.

Retornar:

`cielo_reference_mismatch`

ou equivalente.

Isso protege contra callback associado ao Attempt errado.

---

# 23. SELEÇÃO DO PAYMENT CORRETO

`payments` é lista.

Não assumir cegamente:

```text
payments[0]
```

Selecionar de forma determinística.

Para um callback de pagamento, localizar candidato compatível com:

* amount esperado;
* statusCode de pagamento;
* identidade externa válida.

Se houver:

```text
0 candidatos
```

→ UNKNOWN/error controlado.

Se houver:

```text
mais de 1 candidato indistinguível
```

→ UNKNOWN/ambiguous result.

Nunca adivinhar.

---

# 24. PROVIDER RESULT OBJECT

Criar retorno provider-neutral, por exemplo:

```text
ProviderPaymentResult
```

com:

```text
status
result_data
safe_metadata
```

`result_data` deve ser compatível com:

`resolve_payment_attempt(... result_data=...)`.

Exemplo APPROVED:

```text
status = APPROVED

result_data = {
    provider_transaction_id,
    provider_order_id,
    provider_reference,
    terminal_external_id,
    authorization_code,
    nsu,
    card_brand,
    card_mask,
    installments,
    payment_product,
    provider_status,
    provider_status_code,
    provider_message
}
```

Nunca incluir segredo.

---

# 25. NÃO CHAMAR `resolve_payment_attempt()` DENTRO DO PARSER

Separar responsabilidades.

Adapter:

```text
Cielo callback
↓
parse
↓
ProviderPaymentResult
```

Bridge/domain:

```text
ProviderPaymentResult
↓
resolve_payment_attempt()
```

Assim o adapter é testável isoladamente.

---

# 26. NORMALIZAÇÃO DE METADATA

Não salvar o JSON completo da Cielo em `response_metadata`.

Ele pode conter dados que não precisamos persistir.

Salvar apenas whitelist sanitizada.

Pode manter:

* order id;
* reference;
* status;
* product;
* status code;
* terminal;
* provider error code/reason.

Não persistir:

* accessKey;
* PAN completo;
* documentos do EC;
* endereços;
* dados desnecessários;
* qualquer credential.

---

# 27. CARD MASK

Nunca armazenar PAN completo.

Aceitar apenas valores mascarados/tokenizados retornados nos campos documentados:

* `mask`;
* `bin` mascarado/tokenizado.

Se o valor aparentar PAN completo:

sanitizar/rejeitar.

Não introduzir armazenamento PCI desnecessário.

---

# 28. INSTALLMENTS

Normalizar:

Cielo à vista:

```text
0
```

CORE PaymentAttempt pode persistir de forma coerente como:

```text
1
```

ou `0`, conforme contrato atual.

Escolher UMA semântica interna clara.

Preferência:

CORE:

```text
1 = à vista
2+ = parcelado
```

Cielo:

```text
0 = à vista
2+ = parcelado
```

Fazer conversão somente no adapter.

Não deixar `0` espalhar para o restante do domínio se a semântica interna for 1 parcela.

---

# 29. PROVIDER CONNECTION VALIDATION

Ao utilizar `CieloSmartAdapter`:

exigir:

```text
connection.provider.code == cielo
connection.provider.integration_type == local_deep_link
```

E validar configuração Cielo.

Não permitir usar adapter Cielo com connection Stone/genérica.

---

# 30. SEM ENDPOINT POS AINDA

Nesta missão NÃO criar endpoint para Flutter disparar Cielo.

Não criar ainda:

```text
POST /cielo/pay
```

Isso será PAY-2.1.

PAY-2.0 é infraestrutura/provider adapter.

---

# 31. SEM RECOVERY AINDA

Não implementar chamada:

```text
lio://order
```

nesta missão.

Mas organizar o adapter para adicionar depois:

```text
build_recovery_command()
parse_recovery_callback()
```

sem refatoração grande.

---

# 32. SEM ESTORNO AINDA

Não implementar:

```text
lio://payment-reversal
```

agora.

Mas preservar no adapter arquitetura para:

```text
build_reversal_command()
parse_reversal_callback()
```

PAY-2 posterior.

---

# 33. TESTES OBRIGATÓRIOS — CREDENTIALS

Testar:

* Client-ID ausente → conflito controlado;
* Access Token ausente → conflito controlado;
* credenciais via settings funcionam;
* credenciais NÃO aparecem no safe metadata;
* credenciais NÃO aparecem em repr do launch command.

Não imprimir segredo no resultado de teste.

---

# 34. TESTES — PAYMENTCODE

Cobrir:

```text
debit_card
→ DEBITO_AVISTA

credit_card 1x
→ CREDITO_AVISTA

credit_card 2x store
→ CREDITO_PARCELADO_LOJA

credit_card 2x administrator
→ CREDITO_PARCELADO_ADM

credit_card 2x bank
→ CREDITO_PARCELADO_BNCO

pix
→ PIX

food_voucher
→ VOUCHER_ALIMENTACAO

meal_voucher
→ VOUCHER_REFEICAO

cash
→ bloqueado
```

---

# 35. TESTES — CENTAVOS

Cobrir:

```text
1.00 → 100
10.50 → 1050
100.00 → 10000
```

E rejeitar valores inválidos.

---

# 36. TESTES — BUILD PAYMENT

Validar:

* URI começa com `lio://payment`;
* possui `request`;
* possui `urlCallback`;
* Base64 decodifica para JSON esperado;
* reference corresponde ao Attempt;
* amount corresponde exatamente;
* paymentCode correto;
* installments correto;
* items preservados;
* merchantCode somente quando configurado.

Não snapshotar/printar Access Token em falhas.

---

# 37. TESTES — CALLBACK APPROVED

Criar fixture baseada no formato oficial Cielo.

Testar:

```text
statusCode = 1
→ APPROVED

statusCode = 0
→ APPROVED PIX
```

Validar mappings para:

* transaction ID;
* order ID;
* reference;
* authCode;
* cieloCode/NSU;
* brand;
* mask;
* installments;
* product;
* terminal.

---

# 38. TESTES — CALLBACK ERRORS

Cobrir:

```text
code 1 → CANCELLED
code 2 → ERROR
code 3 → ERROR
code 4 → ERROR
```

Preservar reason sanitizado.

---

# 39. TESTES — RESULTADO INSEGURO

Testar:

* Base64 inválido;
* JSON inválido;
* payment ausente;
* transaction ID ausente;
* amount divergente;
* reference divergente;
* múltiplos payments ambíguos.

Nenhum desses pode resultar em APPROVED.

Preferir UNKNOWN para cenários em que não é possível provar o estado financeiro.

---

# 40. TESTE DE INTEGRAÇÃO COM O BRIDGE GENÉRICO

Sem Cielo real.

Criar:

```text
PaymentIntent
↓
PaymentAttempt PROCESSING
↓
fixture callback Cielo APPROVED
↓
CieloSmartAdapter.parse_payment_callback()
↓
ProviderPaymentResult APPROVED
↓
resolve_payment_attempt()
```

Validar:

```text
Attempt = APPROVED
Intent = APPROVED
```

E confirmar:

```text
QuickSalePayment ainda NÃO existe
```

Porque o adapter não pode aplicar dinheiro automaticamente.

---

# 41. NÃO MEXER NO MOTOR PAY-1

Não alterar sem necessidade:

* PaymentIntent state machine;
* PaymentAttempt state machine;
* QuickSalePayment;
* apply_approved_quick_sale_payment_intent;
* sales.Payment;
* cash session;
* inventory reservation;
* lock order;
* reversal rules;
* UNKNOWN semantics;
* provider fallback.

Cielo deve se adaptar ao motor existente.

Não o contrário.

---

# 42. DOCUMENTAÇÃO INTERNA

Criar documentação curta no próprio módulo explicando:

```text
Cielo Deep Link
→ adapter
→ ProviderPaymentResult
→ resolve_payment_attempt
→ Quick Sale bridge
```

Também documentar explicitamente:

**Deep Link URI contém credenciais em Base64 e nunca pode ser logado.**

---

# 43. TESTES PERMITIDOS

Pode executar SOMENTE testes direcionados de:

* payment_integrations;
* adapter Cielo;
* bridge Cielo → PaymentAttempt.

NÃO executar:

* suíte completa;
* Flutter;
* build;
* analyze;
* lint global.

---

# CHECKPOINT FINAL

Ao terminar informar:

1. arquivos criados;
2. migration criada;
3. como Cielo foi registrada como provider;
4. arquitetura do adapter registry;
5. como Client-ID/Access Token são carregados;
6. confirmação de que secrets não vão para banco/log/audit;
7. configuração permitida em PaymentProviderConnection;
8. mapping CORE → paymentCode;
9. conversão para centavos;
10. formato da reference;
11. formato do launch command;
12. como o Deep Link é construído;
13. como callback Base64 é parseado;
14. mapping Cielo → PaymentAttempt;
15. tratamento dos códigos 1/2/3/4;
16. validação de amount;
17. validação de reference;
18. tratamento de resultado ambíguo;
19. sanitização de card mask/metadata;
20. testes adicionados;
21. resultado dos testes;
22. confirmação de que não alterou QuickSalePayment/sales.Payment;
23. confirmação de que NÃO alterou Cash;
24. confirmação de que NÃO alterou Mesa;
25. confirmação de que NÃO alterou Comandas;
26. confirmação de que NÃO alterou Flutter;
27. confirmação de que NÃO implementou recovery;
28. confirmação de que NÃO implementou reversal;
29. confirmação de que NÃO abriu Deep Link real.

Depois PARE.

NÃO avance para PAY-2.1.
