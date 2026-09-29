# MISSÃO PAY-2.1 — CIELO SMART DEEP LINK NO CORE POS

HEAD BASE:

`44bbb9476b86b6111c9ccf9f05f36906293be980`

O PAY-2.0 está ENCERRADO.

Já temos:

```text
PaymentIntent
PaymentAttempt
Provider Registry
CieloSmartAdapter
Deep Link builder
Callback parser
UNKNOWN
APPROVED != APPLIED
QuickSale provider bridge
```

Agora implementar o primeiro fluxo REAL:

```text
CORE POS
↓
Backend
↓
PaymentIntent / PaymentAttempt PROCESSING
↓
Cielo launch command
↓
Android
↓
Cielo Smart
↓
callback Android
↓
Flutter
↓
Backend
↓
PaymentAttempt
↓
PaymentIntent
↓
QuickSalePayment
```

Nesta missão implementar SOMENTE pagamento Cielo via Deep Link na VENDA RÁPIDA.

NÃO integrar Mesa.

NÃO integrar Comandas.

NÃO implementar recovery Cielo ainda.

NÃO implementar reversal Cielo ainda.

NÃO alterar o motor PAY-1.

---

# 1. PRINCÍPIO FUNDAMENTAL

O Flutter NÃO decide se o pagamento foi aprovado.

O Android NÃO decide se o pagamento foi aprovado.

O callback Cielo NÃO pode virar pagamento local diretamente.

Fluxo obrigatório:

```text
callback raw da Cielo
↓
Flutter apenas encaminha
↓
backend
↓
CieloSmartAdapter.parse_payment_callback()
↓
ProviderPaymentResult
↓
resolve_quick_sale_payment_attempt()
↓
se APPROVED
apply_approved_quick_sale_payment_intent()
↓
QuickSalePayment
```

Não criar atalhos.

---

# 2. ENDPOINTS PROVIDER-NEUTRAL

Não criar endpoints chamados:

```text
/cielo/pay
/cielo/callback
```

Criar endpoints operacionais provider-neutral dentro do Quick Sale.

Sugestão:

```text
POST
/sales/checkouts/<checkout_id>/provider-payments/start/

POST
/sales/checkouts/<checkout_id>/provider-payments/attempts/<attempt_id>/result/

POST
/sales/checkouts/<checkout_id>/provider-payments/intents/<intent_id>/apply/

POST
/sales/checkouts/<checkout_id>/provider-payments/intents/<intent_id>/retry/

POST
/sales/checkouts/<checkout_id>/provider-payments/intents/<intent_id>/cancel/

POST
/sales/checkouts/<checkout_id>/provider-payments/attempts/<attempt_id>/launch-failed/
```

Podem ajustar nomes se houver padrão melhor no projeto.

Mas NÃO colocar Cielo no path.

---

# 3. START PROVIDER PAYMENT

Payload inicial:

```text
payment_method
mode
amount
allocations
idempotency_key
provider = cielo
```

Para PAY-2.1:

```text
installments = 1
```

para crédito.

Não implementar seletor avançado de parcelamento ainda.

Parcelamento completo + enabledproducts será fase posterior.

---

# 4. POS NÃO ESCOLHE CONNECTION NEM TERMINAL POR ID

O cliente NÃO deve poder mandar:

```text
provider_connection_id
terminal_id
```

e escolher uma conexão arbitrária.

O backend resolve isso.

Para Cielo LOCAL_DEEP_LINK:

```text
Provider.code = cielo
status ACTIVE

PaymentProviderConnection
company = checkout.company
status ACTIVE
branch = checkout.branch OU NULL
```

Preferência:

```text
connection específica da branch
↓
connection company-wide
```

Se houver mais de uma Connection elegível na mesma prioridade:

```text
payment_provider_connection_ambiguous
```

NÃO escolher `.first()` silenciosamente.

---

# 5. TERMINAL CIELO DO POS

Para integração local:

resolver:

```text
PaymentTerminal
connection = connection Cielo selecionada
branch = checkout.branch
pos_device = device atual
status ACTIVE
```

Para PAY-2.1 exigir vínculo EXATO:

```text
terminal.pos_device == POSDevice atual
```

Não usar terminal de outra máquina.

Não usar terminal `pos_device=NULL` como fallback automático.

Se não houver:

```text
payment_provider_terminal_unavailable
```

---

# 6. PAYMENT METHOD COMPATÍVEL

Usar capabilities/provider adapter para validar.

Cielo PAY-2.1 pode operar:

```text
credit_card → 1x
debit_card
pix
food_voucher
meal_voucher
```

Cash nunca.

Não criar PaymentMethod Cielo.

Continua:

```text
payment_method = credit_card
provider = cielo
```

---

# 7. CHECKOUT OPTIONS

Hoje:

`POSSaleCheckoutOptionsView`

retorna PaymentMethods apenas com metadata manual.

Adicionar metadata de captura SEM alterar o significado financeiro de PaymentMethod.

Exemplo:

```json
{
  "id": 3,
  "code": "credit_card",
  "name": "Cartão de crédito",
  "kind": "credit",
  "capture": {
    "mode": "provider",
    "provider": "cielo",
    "integration_type": "local_deep_link"
  }
}
```

Se Cielo não estiver disponível para aquele POS:

```text
capture.mode = manual
```

ou ausência de provider capture.

Não reaproveitar `source_type` do ledger para representar configuração operacional se isso gerar ambiguidade.

---

# 8. NÃO FAZER FALLBACK AUTOMÁTICO PARA MANUAL

Se Cielo estiver selecionada:

```text
Cielo falhou
```

NÃO fazer automaticamente:

```text
recordQuickSalePayment()
```

Isso pode duplicar cobrança.

Principalmente em:

```text
PROCESSING
UNKNOWN
APPROVED
```

Nunca converter falha integrada em pagamento manual automaticamente.

---

# 9. IDEMPOTÊNCIA DO START

O endpoint start deve ser idempotente.

Mesmo:

```text
checkout
payment data
idempotency_key
```

não pode criar:

```text
Intent #1
Intent #2
```

nem:

```text
Attempt #1
Attempt #2
```

por retry HTTP.

Se o mesmo start já criou:

```text
Intent
+
Attempt PROCESSING
```

retornar a mesma identidade operacional.

Não criar nova tentativa silenciosamente.

---

# 10. NÃO RELANÇAR CIELO AUTOMATICAMENTE EM RECOVERY LOCAL

Se o app reiniciar e existir:

```text
Attempt PROCESSING
```

NÃO reconstruir e abrir automaticamente:

```text
lio://payment
```

Isso poderia cobrar novamente.

Mostrar estado pendente.

Recovery real Cielo será PAY-2.2/PAY-2.3.

---

# 11. ITEMS CIELO

Agora precisamos transformar o checkout persistido em itens Cielo.

Criar helper dedicado.

Exemplo conceitual:

```text
cielo_items_from_quick_checkout(checkout)
```

Usar SOMENTE snapshots persistidos do checkout.

NÃO buscar preço atual do Product.

NÃO recalcular promoção atual.

NÃO recalcular modificadores atuais.

NÃO usar catálogo atual.

O checkout é a fonte.

---

# 12. TODOS OS ITENS REAIS

A Cielo trabalha com Order e exige itens.

Não criar:

```text
"Geral"
"Venda CORE"
"Pagamento CORE"
```

como item fake único.

Enviar os itens reais persistidos no QuickSaleCheckout.

Se algum item não puder ser convertido de forma segura:

retornar erro controlado.

NÃO fabricar valor.

---

# 13. CIELO ITEM

Cada item normalizado deve fornecer:

```text
name
quantity
sku
unitOfMeasure
unitPrice
```

Valores monetários em centavos exatos.

`sku`:

usar snapshot/internal_code quando disponível.

Fallback permitido:

```text
produto-{product_id}
```

desde que determinístico.

Nunca random.

---

# 14. VALORES CONGELADOS

Os itens enviados devem refletir o checkout congelado.

Não usar:

```text
Product.sale_price atual
```

depois que o checkout já foi criado.

Isso é importante porque:

```text
preço pode mudar
produto pode ser arquivado
promoção pode mudar
```

durante a cobrança.

---

# 15. START FLOW BACKEND

Fluxo:

```text
validar POS/device/operator
↓
resolver checkout
↓
resolver Provider Cielo
↓
resolver Connection
↓
resolver Terminal deste POS
↓
create_quick_sale_payment_intent()
↓
Intent READY
↓
start_quick_sale_payment_attempt()
↓
Attempt PROCESSING
↓
CieloSmartAdapter.build_payment_command()
↓
retornar launch command
```

Nunca gerar Deep Link antes do Attempt estar PROCESSING.

---

# 16. RESPONSE DO START

Retornar SOMENTE o necessário.

Exemplo:

```json
{
  "provider": "cielo",
  "intent_id": "...",
  "attempt_id": "...",
  "status": "processing",
  "operation": "payment",
  "launch_uri": "<secret-bearing URI>",
  "safe_metadata": {}
}
```

`launch_uri` é sensível.

Adicionar:

```text
Cache-Control: no-store
```

na resposta.

---

# 17. EXCEÇÃO CONTROLADA PARA O LAUNCH URI

PAY-2.0 definiu corretamente que secrets não entram em APIs administrativas.

PAY-2.1 terá UMA exceção operacional inevitável:

o endpoint autenticado do POS pode entregar:

```text
launch_uri
```

ao dispositivo que executará a Cielo.

Essa URI contém Client-ID / Access Token em Base64.

Portanto:

NÃO salvar no banco.

NÃO salvar no PaymentAttempt.

NÃO salvar em AuditLog.

NÃO logar.

NÃO incluir em exception.

NÃO incluir em debugPrint.

NÃO persistir no Flutter.

Passar diretamente:

```text
backend response
↓
memória Flutter
↓
MethodChannel
↓
Android
↓
Cielo
```

e descartar.

---

# 18. RESULT ENDPOINT

O cliente envia:

```text
response
responsecode
```

recebidos da Cielo.

E apenas isso relacionado ao resultado externo.

O cliente NÃO pode mandar:

```text
status=approved
provider_transaction_id
authCode
nsu
amount aprovado
```

como autoridade.

Backend:

```text
load Attempt
↓
get adapter pelo provider do Attempt
↓
parse_payment_callback()
↓
resolve_quick_sale_payment_attempt()
```

---

# 19. SCOPE DO ATTEMPT

Antes de processar callback validar:

```text
Attempt
→ Intent
→ checkout atual
→ company atual
→ branch atual
→ POSDevice atual
→ operator/context
```

Um POS não pode enviar callback para Attempt de:

* outro checkout;
* outro device;
* outra branch;
* outra empresa.

---

# 20. APPROVED

Se parser retornar:

```text
APPROVED
```

fazer:

```text
resolve_quick_sale_payment_attempt()
```

Depois:

```text
apply_approved_quick_sale_payment_intent()
```

Resultado:

```text
PaymentAttempt APPROVED
PaymentIntent APPLIED
QuickSalePayment PROVIDER
```

Retornar checkout atualizado.

---

# 21. APPROVED MAS APPLY FALHA

Cenário possível:

```text
Cielo APPROVED
↓
CORE registra Attempt APPROVED
↓
apply local falha
```

NUNCA tentar outra cobrança.

Preservar:

```text
Intent APPROVED
Attempt APPROVED
```

Responder algo como:

```text
provider_approved_apply_pending
```

A UI deve mostrar:

```text
PAGAMENTO APROVADO NA CIELO
AGUARDANDO REGISTRO NO CORE
```

e oferecer apenas:

```text
TENTAR REGISTRAR NOVAMENTE
```

Não:

```text
PAGAR NOVAMENTE
```

---

# 22. APPLY ENDPOINT

O endpoint:

```text
.../intents/<intent_id>/apply/
```

deve apenas chamar:

```text
apply_approved_quick_sale_payment_intent()
```

É idempotente.

Não conversa novamente com Cielo.

Não gera novo Attempt.

Não gera novo Deep Link.

---

# 23. CALLBACK CANCELLED

Cielo:

```text
code 1
```

ou pagamento status cancelado.

Resultado:

```text
Attempt CANCELLED
Intent CANCELLED
```

Não criar QuickSalePayment.

Checkout volta a permitir operação normal.

---

# 24. CALLBACK ERROR

Resultado:

```text
Attempt ERROR
Intent ERROR
```

Não criar QuickSalePayment.

Não registrar manualmente.

UI pode oferecer:

```text
TENTAR NOVAMENTE
CANCELAR COBRANÇA
```

---

# 25. RETRY

Retry usa o MESMO PaymentIntent.

Fluxo:

```text
Intent ERROR / DECLINED
↓
resolver Connection/Terminal atuais
↓
start_quick_sale_payment_attempt()
↓
novo PaymentAttempt
↓
PROCESSING
↓
novo launch command
```

Isso aproveita o fallback/retry que fechamos no PAY-1.4.

Não criar Intent novo.

---

# 26. CANCEL INTENT

Para:

```text
READY
ERROR
DECLINED
```

permitir endpoint operacional que chama:

```text
cancel_quick_sale_payment_intent()
```

Não criar bypass de status.

PROCESSING / UNKNOWN / APPROVED continuam protegidos pelo motor.

---

# 27. LAUNCH FAILED ANTES DE ABRIR CIELO

Se Android conseguir determinar com certeza:

```text
Cielo app não instalado
Intent não resolvível
startActivity falhou ANTES de abrir o provider
```

o Flutter pode avisar o backend através do endpoint:

```text
launch-failed
```

Backend pode resolver Attempt como:

```text
ERROR
```

com metadata segura:

```text
provider_status = launch_error
```

Sem inventar resultado Cielo.

---

# 28. NÃO MARCAR ERROR SE O LAUNCH FOI INCERTO

Se:

```text
Cielo abriu
```

mas:

```text
callback não voltou
app reiniciou
processo foi interrompido
```

NÃO marcar ERROR.

NÃO marcar DECLINED.

NÃO iniciar nova cobrança.

Manter:

```text
PROCESSING
```

ou usar UNKNOWN apenas quando houver fluxo explícito seguro para isso.

Recovery Cielo será próxima fase.

---

# 29. QUICK CHECKOUT PAYLOAD

Expandir:

```text
payment_integration
```

para recuperação de UI.

Hoje temos:

```text
intent_id
status
```

Adicionar de forma segura:

```text
intent_id
intent_status
attempt_id
attempt_status
provider
can_retry
can_cancel
can_apply
requires_recovery
```

Nunca:

```text
launch_uri
credentials
raw callback
```

---

# 30. ANDROID MANIFEST — PACKAGE VISIBILITY

Adicionar:

```xml
<queries>
    <package android:name="com.ads.lio.uriappclient" />
</queries>
```

Obrigatório para Android 11+ segundo Cielo.

---

# 31. ANDROID MANIFEST — CIELO INTEGRATION TYPE

Dentro de:

```xml
<application>
```

adicionar:

```xml
<meta-data
    android:name="cs_integration_type"
    android:value="uri" />
```

Não remover metadata Flutter existente.

---

# 32. CALLBACK URI

Usar contrato próprio e estável.

Sugestão:

```text
corepdv://cielo-payment-response
```

Registrar Activity específica:

```text
CieloResponseActivity
```

com:

```text
ACTION_VIEW
CATEGORY_DEFAULT
scheme = corepdv
host = cielo-payment-response
```

O MESMO callback deve ser usado no:

```text
urlCallback
```

do Deep Link.

---

# 33. NÃO USAR MAINACTIVITY COMO PARSER FINANCEIRO

A Activity Android não interpreta:

```text
APPROVED
ERROR
CANCELLED
```

Ela apenas captura:

```text
response
responsecode
```

e entrega ao Flutter.

Backend interpreta.

---

# 34. FOREGROUND SERVICE

A documentação Cielo alerta que Android pode matar o aplicativo integrador quando ele fica em background durante o pagamento.

Implementar:

```text
CieloPaymentForegroundService
```

ou nome equivalente.

Durante pagamento:

```text
startForeground()
↓
notificação ativa
↓
launch Cielo
↓
aguarda callback
```

Notificação simples:

```text
Pagamento em andamento
```

Não colocar:

* valor;
* nome cliente;
* cartão;
* token;
* NSU;
* URI.

---

# 35. FOREGROUND SERVICE E TARGET SDK

Adicionar permissões/declarations compatíveis com o targetSdk atual do projeto.

Não usar um foreground-service type semanticamente falso apenas para compilar.

Documentar no checkpoint qual tipo/permissão foi necessário para o target atual.

Manter compatibilidade com o ambiente Cielo Smart / Android 10.

---

# 36. LAUNCH CIELO

O Intent deve ser:

```text
Intent.ACTION_VIEW
Uri.parse(launchUri)
```

com:

```text
FLAG_ACTIVITY_CLEAR_TOP
```

e preferencialmente direcionado ao pacote:

```text
com.ads.lio.uriappclient
```

para não entregar uma URI com credenciais para aplicativo arbitrário.

Antes:

verificar se existe Activity compatível.

Se não existir:

```text
cielo_app_unavailable
```

---

# 37. METHODCHANNEL

O projeto já usa MethodChannel para scanner beep.

Criar canal separado:

```text
core_pos/cielo_payment
```

Não misturar com:

```text
core_pos/scanner_beep
```

Contrato conceitual:

```text
Flutter → Android:
launchPayment

Android → Flutter:
paymentCallback

Flutter → Android:
getPendingCallback
```

Pode adaptar nomes mantendo responsabilidades claras.

---

# 38. PAYLOAD FLUTTER → ANDROID

Enviar somente:

```text
attempt_id
launch_uri
```

Não enviar:

* Client-ID separado;
* Access Token separado;
* PaymentMethod;
* amount para Android decidir;
* status esperado.

Android apenas executa URI.

---

# 39. CALLBACK ANDROID → FLUTTER

Retornar:

```text
attempt_id
response
responsecode
```

Não retornar status financeiro calculado pelo Android.

---

# 40. RESPONSE ACTIVITY

`CieloResponseActivity` deve:

```text
receber Intent ACTION_VIEW
↓
ler URI
↓
obter response
↓
obter responsecode
↓
entregar ao bridge/service
↓
retornar o usuário ao CORE POS
↓
finish()
```

Não logar URI inteira.

Não logar `response`.

---

# 41. RESULTADO PENDENTE NATIVO

Como existe foreground service, manter em memória o callback até o Flutter consumi-lo.

Se Flutter estiver temporariamente sem listener:

```text
getPendingCallback
```

deve recuperá-lo.

Após ACK/consumo:

limpar.

Não persistir launch URI.

Se processo inteiro morrer:

não inventar resultado.

O backend continuará com Attempt PROCESSING para futura reconciliação.

---

# 42. FLUTTER SERVICE

Criar camada isolada, por exemplo:

```text
payments/provider_payment_bridge.dart
payments/cielo_payment_bridge.dart
```

Não colocar MethodChannel diretamente dentro da UI.

Responsabilidades:

```text
launch()
callback stream/result
pending callback
```

---

# 43. API FLUTTER

Adicionar em:

```text
PosApi
HttpPosApi
```

operações:

```text
startQuickSaleProviderPayment()
resolveQuickSaleProviderPayment()
retryQuickSaleProviderPayment()
cancelQuickSaleProviderPayment()
applyQuickSaleProviderPayment()
reportProviderLaunchFailed()
```

Criar models específicos.

Não usar Maps soltos em toda UI.

---

# 44. NÃO LOGAR LAUNCH URI NO HTTP CLIENT

Hoje o POS tem logs de erro HTTP.

Garantir que endpoint provider não faça:

```text
debugPrint(response.body)
```

se o body puder conter `launch_uri`.

Em qualquer erro relacionado ao start:

sanitizar.

Nenhum log pode conter:

```text
clientID
accessToken
lio://payment?...request=
```

---

# 45. PAYMENT ENTRY UI

Reutilizar:

```text
SharedPaymentPage
PaymentEntryPage
```

Não criar uma tela de pagamento Cielo totalmente separada.

Se método possuir:

```text
capture.mode = provider
provider = cielo
```

o botão final deixa de ser:

```text
CONFIRMAR PAGAMENTO MANUAL
```

e passa a ser algo como:

```text
PAGAR NA CIELO
```

---

# 46. PAY-2.1 SEM PARCELAMENTO AVANÇADO

Nesta missão:

```text
credit_card
→ 1x
```

Débito/PIX/vouchers podem usar seus mappings já existentes.

Não criar interface de:

```text
2x
3x
...
```

ainda.

Parcelamento + enabledproducts virá depois.

---

# 47. START NO FLUTTER

Fluxo após operador confirmar valor:

```text
API start provider payment
↓
recebe intent_id / attempt_id / launch_uri
↓
guarda IDs operacionais
↓
NÃO persiste launch_uri
↓
chama native bridge
↓
Cielo abre
```

---

# 48. CALLBACK NO FLUTTER

Quando callback chegar:

```text
working = true
↓
POST result backend
↓
backend parse/resolve/apply
↓
recebe checkout atualizado
↓
_replaceCheckout()
```

Se pagamento zerou saldo:

NÃO finalizar venda automaticamente.

Manter botão:

```text
FINALIZAR VENDA
```

e fluxo atual.

---

# 49. UX PROCESSING

Enquanto provider estiver PROCESSING:

bloquear:

* novo pagamento;
* edição financeira;
* cancelamento do checkout;
* saída destrutiva.

Mostrar estado claro:

```text
PAGAMENTO EM PROCESSAMENTO NA CIELO
```

Não mostrar botão para cobrar novamente.

---

# 50. UX ERROR

Se Intent ERROR:

mostrar:

```text
Não foi possível concluir o pagamento na Cielo.
```

Ações:

```text
TENTAR NOVAMENTE
CANCELAR COBRANÇA
```

Retry usa mesmo Intent.

---

# 51. UX CANCELLED

Se Cielo retornar cancelamento:

```text
Pagamento cancelado.
```

Checkout volta ao estado operacional.

Não criar pagamento.

---

# 52. UX APPROVED/APPLY PENDING

Se provider aprovou mas apply local não concluiu:

mostrar claramente:

```text
PAGAMENTO APROVADO NA CIELO
```

e:

```text
TENTAR REGISTRAR NO CORE
```

Não disponibilizar:

```text
PAGAR NOVAMENTE
```

---

# 53. APP RESTART

Ao reabrir checkout:

usar:

```text
payment_integration
```

do backend.

Se status:

```text
PROCESSING
UNKNOWN
```

não lançar Cielo novamente.

Mostrar:

```text
Pagamento aguardando confirmação.
```

Recovery será fase seguinte.

---

# 54. NÃO USAR `url_launcher` PARA CIELO

Mesmo que já exista:

```text
url_launcher
```

no projeto, NÃO usar para pagamento Cielo.

Precisamos:

* foreground service;
* package targeting;
* callback Activity;
* bridge controlado.

Usar bridge nativo.

---

# 55. SEGURANÇA DO CALLBACK

Callback custom URI pode ser invocado por outro aplicativo.

Portanto nunca confiar no Android como origem financeira.

Proteções permanecem no backend:

```text
Attempt esperado
reference
amount
provider
provider_transaction_id
state machine
```

O Android apenas transporta o payload.

---

# 56. TESTES BACKEND OBRIGATÓRIOS

Cobrir:

```text
Cielo disponível no checkout-options
Cielo indisponível sem terminal
connection branch > company
connection ambígua bloqueia
terminal de outro POS bloqueia
cash não usa provider
start cria Intent + PROCESSING Attempt
start idempotente
start não cria QuickSalePayment
launch_uri não persiste
result APPROVED → APPLIED
result replay → mesmo QuickSalePayment
CANCELLED → nenhum payment
ERROR → nenhum payment
apply retry não gera nova cobrança
retry cria novo Attempt no mesmo Intent
attempt de outro checkout/device rejeitado
client não controla status financeiro
```

---

# 57. TESTES DE SEGREDOS

Confirmar que:

```text
launch_uri
clientID
accessToken
```

não aparecem em:

* AuditLog;
* PaymentAttempt.request_metadata;
* PaymentAttempt.response_metadata;
* checkout payload;
* exceptions;
* safe metadata.

Apenas o response operacional start contém `launch_uri`.

---

# 58. TESTES FLUTTER DIRECIONADOS

Cobrir somente componentes afetados:

```text
parse capture metadata
parse provider launch response
provider method não chama recordQuickSalePayment manual
callback chama result endpoint
APPROVED atualiza checkout
ERROR mostra retry
PROCESSING bloqueia nova cobrança
APPROVED apply-pending não relança Cielo
restart com PROCESSING não relança
```

---

# 59. ANDROID TEST / CONTRATO

Se houver estrutura simples para teste Kotlin, pode testar parser de URI/bridge.

Não criar instrumentação pesada nesta missão.

Não precisa executar emulador automaticamente.

---

# 60. NÃO IMPLEMENTAR RECOVERY CIELO

Ainda NÃO chamar:

```text
lio://order
lio://orders
```

Nenhuma consulta de pedido nesta missão.

Se callback se perder:

```text
PROCESSING
```

permanece protegido.

---

# 61. NÃO IMPLEMENTAR REVERSAL

Ainda NÃO chamar:

```text
lio://payment-reversal
```

O bloqueio atual de provider reversal continua.

---

# 62. NÃO ALTERAR MESA

NÃO mexer em:

```text
TableAttendance
TablePayment
Mesa UI
Mesa endpoints
```

---

# 63. NÃO ALTERAR COMANDAS

NÃO mexer em:

```text
Command
AttendanceCommand
AttendancePayment
Comanda UI
```

---

# 64. NÃO ALTERAR MOTOR PAY-1

Preservar:

```text
PaymentIntent
PaymentAttempt
UNKNOWN
APPROVED
APPLIED
provider fallback
transaction uniqueness
cash context
lock ordering
QuickSalePayment
sales.Payment
```

Cielo deve usar o motor.

Não modificar o motor para adaptar a Cielo.

---

# 65. MIGRATIONS

Não há schema change obrigatório esperado.

Não criar migration sem necessidade real.

NÃO editar migrations existentes.

---

# 66. TESTES PERMITIDOS

Pode executar SOMENTE testes direcionados relacionados a:

```text
payment_integrations Cielo
POS Quick Sale provider endpoints
Flutter payment/provider components
```

NÃO executar:

* suíte completa;
* flutter analyze global;
* flutter build;
* build APK;
* testes de Mesa;
* testes de Comandas.

---

# CHECKPOINT FINAL

Ao terminar informar:

1. endpoints criados;
2. como Connection Cielo é resolvida;
3. como Terminal Cielo é resolvido por POS;
4. como provider aparece no checkout options;
5. como itens Cielo são montados;
6. idempotência do start;
7. formato do start response;
8. como launch_uri é protegido;
9. contrato MethodChannel;
10. alterações no AndroidManifest;
11. package visibility Cielo;
12. `cs_integration_type=uri`;
13. callback scheme/host;
14. ResponseActivity;
15. ForegroundService;
16. permissões/tipo de foreground service usados;
17. como Cielo é lançada;
18. como callback chega ao Flutter;
19. como callback chega ao backend;
20. como APPROVED vira APPLIED;
21. como apply-pending funciona;
22. comportamento CANCELLED;
23. comportamento ERROR;
24. retry;
25. comportamento quando callback se perde;
26. recuperação do estado após restart;
27. alterações na SharedPaymentPage;
28. testes backend;
29. testes Flutter;
30. resultado dos testes direcionados;
31. arquivos alterados;
32. migrations criadas, se houver;
33. confirmação de que secrets não foram persistidos/logados;
34. confirmação de que NÃO alterou Mesa;
35. confirmação de que NÃO alterou Comandas;
36. confirmação de que NÃO implementou recovery Cielo;
37. confirmação de que NÃO implementou reversal Cielo.

Depois PARE.

NÃO avance para PAY-2.2.
