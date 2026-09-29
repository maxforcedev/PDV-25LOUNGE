# MISSÃO PAY-2.1.1 — FECHAMENTO DE CALLBACK, START INCERTO E BRIDGE ANDROID

HEAD atual analisado:

`804532f518c82cfcf8efb4f2514ecc771f1cf97e`

O PAY-2.1 implementou corretamente a base do fluxo real:

* endpoints provider-neutral;
* resolução de Connection Cielo;
* Terminal vinculado ao POS;
* criação de Intent + Attempt;
* launch command;
* Manifest Cielo;
* callback Activity;
* foreground service;
* MethodChannel;
* Flutter bridge;
* callback → backend;
* APPROVED → APPLIED;
* retry/cancel/apply;
* proteção do `launch_uri`.

Porém a auditoria encontrou 3 bloqueadores antes do primeiro teste físico.

Corrigir SOMENTE estes pontos e completar os testes críticos.

NÃO implementar recovery Cielo via consulta.
NÃO implementar reversal.
NÃO mexer em Mesa.
NÃO mexer em Comandas.
NÃO alterar PAY-1.

---

# 1. CORRIGIR ERRO DE COMPILAÇÃO NO ANDROID

Hoje em:

`CieloPaymentBridge.kt`

existe algo equivalente a:

```kotlin
CieloPaymentForegroundService.stop(channel.context)
```

`MethodChannel` não possui `context`.

O próprio bridge já mantém:

```kotlin
private var appContext: Context? = null
```

Usar o contexto da aplicação.

Exemplo conceitual:

```kotlin
appContext?.let { context ->
    CieloPaymentForegroundService.stop(context)
}
```

Não depender de `channel.context`.

---

# 2. ACK DO CALLBACK

Ao receber:

```text
acknowledgeCallback
```

e o `attempt_id` corresponder ao callback pendente:

executar:

```text
pendingCallback = null
activeAttemptId = null
stop foreground service
```

usando `appContext`.

Se `appContext == null`:

não quebrar o MethodChannel.

Responder normalmente e preservar segurança.

---

# 3. CALLBACK NÃO PODE SER DESCARTADO POR `_working`

Hoje existe lógica:

```dart
if (_working || callback.attemptId != expectedAttempt) return;
```

Isso é incorreto para `_working`.

Se callback Cielo chegar enquanto outro trecho da tela ainda está trabalhando:

NÃO descartar.

Armazenar/serializar para processamento posterior.

Pode utilizar:

```text
_pendingCieloCallback
```

em memória Flutter.

---

# 4. DIFERENCIAR CALLBACK ERRADO DE CALLBACK TEMPORARIAMENTE BLOQUEADO

Se:

```text
callback.attemptId != expectedAttempt
```

NÃO processar financeiramente.

Mas também não dar ACK indevido.

Pode manter o callback nativo pendente.

Se:

```text
callback.attemptId == expectedAttempt
_working == true
```

guardar localmente para processamento assim que `_working` voltar para false.

---

# 5. DRENAR CALLBACK PENDENTE APÓS `_working`

Criar helper centralizado, por exemplo:

```text
_schedulePendingProviderCallback()
_drainPendingProviderCallback()
```

Ao finalizar qualquer operação relevante e `_working` voltar para `false`:

verificar:

1. callback Flutter guardado;
2. callback nativo via `getPendingCallback()`.

Se houver callback esperado:

reenviar ao backend.

Evitar loops/reentrância.

---

# 6. NÃO PROCESSAR O MESMO CALLBACK EM PARALELO

Adicionar flag específica, por exemplo:

```text
_resolvingProviderCallback
```

ou mecanismo equivalente.

Evitar:

```text
stream callback
+
getPendingCallback
```

processarem o mesmo payload simultaneamente.

Somente UMA chamada ao backend por vez.

Replay HTTP posterior continua permitido.

---

# 7. FALHA DE INTERNET DEPOIS DO CALLBACK

Cenário crítico:

```text
Cielo APPROVED
↓
callback chega ao Flutter
↓
POST result backend
↓
rede cai
```

Resultado correto:

```text
NÃO ACK
NÃO limpar callback
NÃO marcar ERROR
NÃO abrir Cielo novamente
```

Callback continua disponível para novo envio.

---

# 8. UI DE CALLBACK PENDENTE

Se existe:

```text
callback Cielo já recebido
```

mas ainda não confirmado pelo backend:

mostrar algo como:

```text
RETORNO DA CIELO RECEBIDO
AGUARDANDO CONFIRMAÇÃO NO CORE
```

Disponibilizar:

```text
TENTAR CONFIRMAR PAGAMENTO
```

Esse botão:

* NÃO abre Cielo;
* NÃO cria Attempt;
* NÃO cria Intent;
* NÃO faz retry provider.

Apenas reenvia o MESMO callback ao backend.

---

# 9. CALLBACK PENDENTE NÃO É RECOVERY CIELO

Importante:

isso NÃO é:

```text
lio://order
```

Nós já possuímos o callback.

Estamos apenas reenviando ao backend.

Portanto implementar isso nesta missão.

---

# 10. ACK SOMENTE DEPOIS DE BACKEND CONFIRMAR

Somente chamar:

```dart
acknowledgeCallback(attemptId)
```

depois que:

```text
resolveQuickSaleProviderPayment()
```

retornar checkout válido.

Se houver:

* timeout;
* network error;
* 5xx;
* resposta inválida;

NÃO ACK.

---

# 11. CALLBACK CANCELLED / ERROR TAMBÉM PRECISA DE ACK

Se backend confirmar corretamente:

```text
CANCELLED
ERROR
APPROVED/APPLIED
```

então ACK pode ser feito.

ACK significa:

```text
backend recebeu e registrou o resultado
```

não significa APPROVED.

---

# 12. START INCERTO

Hoje:

```text
POST provider-payments/start
↓
timeout / rede cai
↓
launch == null
```

pode deixar servidor com:

```text
Intent PROCESSING
Attempt PROCESSING
```

e Flutter com checkout antigo.

Isso precisa ser corrigido.

---

# 13. APÓS START INCERTO, RECARREGAR CHECKOUT

Se:

```text
startQuickSaleProviderPayment()
```

não retornar resultado por:

* timeout;
* network exception;
* erro incerto 5xx;

o POS deve imediatamente tentar:

```text
GET checkout atual
```

antes de liberar a UI.

---

# 14. SE SERVIDOR MOSTRAR PROCESSING

Se o checkout atualizado retornar:

```text
payment_integration.intent_status = processing
```

ou:

```text
unknown
approved
```

NÃO permitir nova cobrança.

Atualizar a tela para o estado oficial do backend.

Não chamar Cielo automaticamente.

---

# 15. SE START REALMENTE NÃO EXISTE NO SERVIDOR

Se reload comprovar:

```text
payment_integration == null
```

e:

```text
can_record_payment == true
```

a UI pode voltar a permitir nova tentativa.

---

# 16. NÃO RELANÇAR URI DE START INCERTO

Se servidor já tem Attempt PROCESSING mas o cliente não recebeu a URI:

NÃO tentar reconstruir URI.

NÃO abrir Cielo.

NÃO criar novo Attempt.

Mostrar:

```text
PAGAMENTO AGUARDANDO CONFIRMAÇÃO
```

Até recovery futuro ou ação segura.

---

# 17. IDEMPOTÊNCIA DO START CONTINUA

Preservar:

```text
mesma idempotency_key
→ mesmo Intent
→ mesmo Attempt
```

Mas não usar replay HTTP para relançar automaticamente a Cielo.

A existência do Attempt PROCESSING deve ser tratada como operação potencialmente iniciada.

---

# 18. NÃO EXPOR NOVAMENTE LAUNCH_URI AUTOMATICAMENTE

Reavaliar comportamento atual:

```text
start idempotent replay
→ retorna launch_uri novamente
```

Isso pode ser perigoso se o primeiro response chegou e a Cielo já foi aberta.

Para PAY-2.1.1:

se request for replay idempotente de um Attempt PROCESSING já existente:

NÃO incentivar o cliente a abrir novamente.

Preferência:

retornar estado operacional sem URI reutilizável, por exemplo:

```json
{
  "provider": "cielo",
  "intent_id": "...",
  "attempt_id": "...",
  "status": "processing",
  "replayed": true,
  "launch_available": false
}
```

OU retornar conflito seguro como:

```text
payment_attempt_already_processing
```

desde que o Flutter então recupere o checkout.

O objetivo é simples:

**replay de START nunca pode causar segunda abertura da mesma cobrança.**

---

# 19. PRIMEIRO START CONTINUA RETORNANDO URI

A primeira criação real:

```text
novo Intent
novo Attempt PROCESSING
```

continua retornando:

```text
launch_uri
```

com:

```text
Cache-Control: no-store
```

Somente replay posterior deve ser tratado com cautela.

---

# 20. AJUSTAR MODEL FLUTTER DE START

Se necessário, permitir:

```text
launch_uri nullable
```

e campos como:

```text
replayed
launch_available
```

Não obrigar o Flutter a receber URI em todo replay.

---

# 21. UI NÃO ABRE CIELO SE URI AUSENTE

Se resposta representar replay já PROCESSING:

```text
launchUri == null
```

Flutter:

```text
NÃO chama MethodChannel
↓
recarrega checkout
↓
mostra estado PROCESSING
```

---

# 22. APPROVED / APPLY PENDING — MENSAGEM EXPLÍCITA

Quando:

```text
intent_status = approved
can_apply = true
```

mostrar claramente:

```text
PAGAMENTO APROVADO NA CIELO
```

e abaixo:

```text
O pagamento foi aprovado, mas ainda precisa ser registrado no CORE.
```

Botão:

```text
TENTAR REGISTRAR NO CORE
```

Não mostrar botão de cobrar novamente.

---

# 23. PROCESSING SEM CALLBACK

Se:

```text
Attempt PROCESSING
```

e não existe callback pendente:

mostrar:

```text
PAGAMENTO EM PROCESSAMENTO NA CIELO
```

Sem ações de retry.

Recovery externo continua futuro.

---

# 24. PROCESSING COM CALLBACK PENDENTE

Se existe callback local pendente:

mostrar:

```text
RETORNO DA CIELO RECEBIDO
AGUARDANDO CONFIRMAÇÃO NO CORE
```

Botão:

```text
TENTAR CONFIRMAR PAGAMENTO
```

---

# 25. FOREGROUND SERVICE

Foreground service deve continuar ativo enquanto callback não foi confirmado/ACKado.

Quando backend receber resultado com sucesso:

```text
ACK
↓
stop service
```

Se POST result falhar:

serviço continua.

---

# 26. RESPONSE ACTIVITY

Preservar:

```text
ACTION_VIEW
↓
response
responsecode
↓
pendingCallback
↓
MainActivity
```

Não interpretar estado financeiro no Android.

---

# 27. NÃO LOGAR CALLBACK RAW

Preservar:

NÃO logar:

```text
response
responsecode completo se contiver payload sensível
callback URI
launch URI
```

---

# 28. TESTE KOTLIN / COMPILAÇÃO DE CONTRATO

Adicionar teste simples se houver infraestrutura, ou pelo menos garantir código compilável.

Corrigir explicitamente:

```text
channel.context
```

Não deixar referência inexistente.

---

# 29. TESTES BACKEND — START REPLAY

Adicionar teste:

```text
primeiro start
→ PROCESSING
→ possui launch_uri

segundo start mesma idempotency key
→ mesmo Intent
→ mesmo Attempt
→ NÃO oferece URI que possa ser relançada automaticamente
```

Validar:

```text
Intent count = 1
Attempt count = 1
```

---

# 30. TESTE BACKEND — START TIMEOUT SIMULADO / RECOVERY STATE

Não precisa simular rede real.

Provar via endpoints:

```text
start cria PROCESSING
↓
GET checkout
↓
payment_integration mostra:
intent_status=processing
attempt_status=processing
requires_recovery=true
can_retry=false
```

---

# 31. TESTE BACKEND — CALLBACK REPLAY

Preservar teste:

```text
POST result
POST mesmo result
```

Esperado:

```text
1 QuickSalePayment
```

---

# 32. TESTE BACKEND — CANCELLED

Adicionar callback Cielo cancelado.

Esperado:

```text
Attempt CANCELLED
Intent CANCELLED
QuickSalePayment count = 0
checkout liberado
```

---

# 33. TESTE BACKEND — ERROR

Adicionar:

```text
{code: 3}
```

ou equivalente.

Esperado:

```text
Attempt ERROR
Intent ERROR
QuickSalePayment = 0
can_retry = true
can_cancel = true
```

---

# 34. TESTE BACKEND — CONNECTION PRIORITY

Cobrir:

```text
Connection branch
+
Connection company-wide
```

Esperado:

```text
branch vence
```

---

# 35. TESTE BACKEND — AMBIGUIDADE

Duas Connections da mesma prioridade:

```text
payment_provider_connection_ambiguous
```

Não escolher primeira.

---

# 36. TESTE BACKEND — TERMINAL OUTRO POS

Terminal Cielo:

```text
pos_device = outro device
```

Esperado:

```text
payment_provider_terminal_unavailable
```

---

# 37. TESTE BACKEND — SCOPE

Callback de Attempt pertencente a:

* outro checkout;
* outro POS;
* outra branch;

deve falhar.

---

# 38. TESTES FLUTTER — CALLBACK DURANTE WORKING

Criar teste para:

```text
_working = true
callback chega
```

Esperado:

```text
callback não é descartado
```

Depois:

```text
_working = false
↓
callback é processado
```

---

# 39. TESTE FLUTTER — RESULT NETWORK FAILURE

Callback:

```text
backend resolve falha
```

Esperado:

```text
acknowledgeCallback NÃO chamado
callback preservado
```

Depois operador toca:

```text
TENTAR CONFIRMAR PAGAMENTO
```

e o mesmo callback é reenviado.

---

# 40. TESTE FLUTTER — ACK

Backend resolve com sucesso:

Esperado:

```text
acknowledgeCallback chamado uma vez
```

e callback local limpo.

---

# 41. TESTE FLUTTER — START INCERTO

`startQuickSaleProviderPayment()` falha por network/timeout.

Esperado:

```text
recarrega checkout
```

Se checkout retorna PROCESSING:

```text
não abre Cielo
não permite nova cobrança
```

---

# 42. TESTE FLUTTER — REPLAY SEM URI

Resposta de replay:

```text
processing
launchUri = null
```

Esperado:

```text
não chama native bridge
```

---

# 43. TESTE FLUTTER — APPLY PENDING

Checkout:

```text
intent_status = approved
can_apply = true
```

Esperado:

texto:

```text
PAGAMENTO APROVADO NA CIELO
```

e botão:

```text
TENTAR REGISTRAR NO CORE
```

Sem opção de pagar novamente.

---

# 44. TESTE FLUTTER — PROCESSING RESTART

Abrir tela com:

```text
payment_integration.processing
```

Esperado:

```text
não chama start
não chama retry
não abre Cielo
```

Se houver callback nativo pendente:

processa o callback.

Se não houver:

mantém estado pendente.

---

# 45. NÃO IMPLEMENTAR RECOVERY CIELO

NÃO chamar:

```text
lio://order
lio://orders
```

Ainda.

---

# 46. NÃO IMPLEMENTAR REVERSAL

NÃO chamar:

```text
lio://payment-reversal
```

Ainda.

---

# 47. NÃO ALTERAR MESA

NÃO mexer em:

```text
TableAttendance
TablePayment
Mesa UI
Mesa endpoints
```

---

# 48. NÃO ALTERAR COMANDAS

NÃO mexer em:

```text
Command
AttendanceCommand
AttendancePayment
Comanda UI
```

---

# 49. NÃO ALTERAR PAY-1

NÃO mexer nas state machines de:

```text
PaymentIntent
PaymentAttempt
QuickSalePayment
sales.Payment
```

Usar o motor atual.

---

# 50. MIGRATIONS

Nenhuma migration esperada.

NÃO criar migration sem necessidade real.

---

# 51. TESTES PERMITIDOS

Pode executar SOMENTE testes direcionados relacionados a:

```text
Cielo adapter
POS provider payment endpoints
Flutter provider payment flow
```

Pode compilar/testar somente o módulo Android necessário para confirmar que o Kotlin alterado compila, se isso for indispensável para validar a correção do `channel.context`.

NÃO executar:

* suíte completa backend;
* Flutter analyze global;
* Flutter build global;
* testes Mesa;
* testes Comandas.

---

# CHECKPOINT FINAL

Ao terminar informar:

1. como corrigiu `channel.context`;
2. como o foreground service é encerrado no ACK;
3. como callback durante `_working` é preservado;
4. como callbacks pendentes são drenados;
5. como evita processamento paralelo do mesmo callback;
6. comportamento quando POST result falha por rede;
7. como funciona "TENTAR CONFIRMAR PAGAMENTO";
8. quando ACK acontece;
9. como START incerto recupera checkout;
10. comportamento quando servidor já possui PROCESSING;
11. como replay do START evita relançar Cielo;
12. formato novo do start replay, se alterado;
13. comportamento de launch_uri nullable;
14. mensagem APPROVED/APPLY pending;
15. testes CANCELLED;
16. testes ERROR;
17. teste Connection branch > company;
18. teste Connection ambígua;
19. teste terminal de outro POS;
20. teste scope outro checkout/device;
21. testes Flutter de callback pendente;
22. testes Flutter de start incerto;
23. resultado dos testes direcionados;
24. confirmação de compilação do bridge Android alterado, se executada;
25. arquivos alterados;
26. migrations criadas — esperado: nenhuma;
27. confirmação de que secrets não são persistidos/logados;
28. confirmação de que NÃO alterou PAY-1;
29. confirmação de que NÃO alterou Mesa;
30. confirmação de que NÃO alterou Comandas;
31. confirmação de que NÃO implementou recovery Cielo;
32. confirmação de que NÃO implementou reversal Cielo.

Depois PARE.

NÃO avance para PAY-2.2.
