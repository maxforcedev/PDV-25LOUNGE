## MISSÃO PAY-2.1.3 — CORRIGIR PACKAGE DO CIELO SMART

### Contexto

O CORE POS está retornando:

> "O aplicativo Cielo não está disponível."

Investigamos diretamente no aparelho Android que possui o Cielo Smart Emulator instalado.

O Android confirmou que o Deep Link `lio://payment` é resolvido corretamente para:

```text
br.com.cielosmart.orderservice/com.cielo.lio.uriappclient.activities.CheckoutActivity
```

Comando executado:

```powershell
adb shell cmd package resolve-activity --brief -a android.intent.action.VIEW -d "lio://payment"
```

Resultado:

```text
priority=0 preferredOrder=0 match=0x308000 specificIndex=-1 isDefault=true
br.com.cielosmart.orderservice/com.cielo.lio.uriappclient.activities.CheckoutActivity
```

Também confirmamos que o package instalado no usuário principal é:

```text
br.com.cielosmart.orderservice
```

Portanto, o package atualmente hardcoded no CORE está incorreto:

```text
com.ads.lio.uriappclient
```

---

## Objetivo

Corrigir exclusivamente a identificação do aplicativo Cielo Smart no Android para que o CORE POS consiga abrir o Deep Link:

```text
lio://payment
```

usando o package correto:

```text
br.com.cielosmart.orderservice
```

---

## 1. CieloPaymentBridge.kt

Arquivo:

```text
pos/android/app/src/main/kotlin/com/corepdv/pos/CieloPaymentBridge.kt
```

Alterar o package alvo de:

```kotlin
private const val cieloPackage = "com.ads.lio.uriappclient"
```

para:

```kotlin
private const val cieloPackage = "br.com.cielosmart.orderservice"
```

Manter:

```kotlin
Intent.ACTION_VIEW
```

e:

```kotlin
Uri.parse(launchUri)
```

Não alterar a arquitetura financeira.

---

## 2. AndroidManifest.xml

Arquivo:

```text
pos/android/app/src/main/AndroidManifest.xml
```

Atualizar a declaração de package visibility.

Substituir:

```xml
<queries>
    <package android:name="com.ads.lio.uriappclient" />
</queries>
```

por:

```xml
<queries>
    <package android:name="br.com.cielosmart.orderservice" />
</queries>
```

Não remover a configuração existente necessária para o Deep Link.

Não alterar o callback `corepdv://cielo-payment-response` nesta missão.

---

## 3. NÃO alterar o fluxo financeiro

Esta missão é exclusivamente de integração Android/Deep Link.

NÃO modificar:

* PaymentIntent;
* PaymentAttempt;
* QuickSaleCheckout;
* QuickSalePayment;
* ledger;
* finalização de pagamento;
* `resolveQuickSaleProviderPayment`;
* callback financeiro;
* idempotência;
* retry financeiro;
* backend Cielo adapter;
* migrations;
* Mesa;
* Comanda;
* PAY-1.

O fato de conseguir abrir o aplicativo Cielo NÃO significa que o pagamento foi aprovado.

---

## 4. Manter o diagnóstico de erro no POS

Não voltar ao comportamento silencioso anterior.

Se o Android não conseguir abrir o aplicativo, o CORE deve continuar conseguindo distinguir pelo menos:

```text
cielo_app_unavailable
cielo_launch_invalid
cielo_launch_failed
```

e o POS deve receber uma mensagem sanitizada útil para diagnóstico.

Não exibir:

* Client ID;
* Access Token;
* launch URI completo;
* credentials;
* dados sensíveis.

---

## 5. Atenção ao Foreground Service

Ao revisar o método `launch()`, verificar também a ordem atual:

```kotlin
activeAttemptId = attemptId
CieloPaymentForegroundService.start(context)
try {
    ...
    context.startActivity(intent)
}
```

Se `CieloPaymentForegroundService.start(context)` estiver fora do `try`, avaliar se ele também deve ficar protegido para que uma eventual exceção não escape sem um `PlatformException` estruturado.

Não faça uma refatoração ampla. Apenas garanta que uma falha nessa etapa também seja diagnosticável pelo POS.

---

## 6. Validação obrigatória

Depois da alteração, fazer somente verificações direcionadas.

Não executar suíte completa do projeto.

Executar pelo menos:

```bash
flutter analyze
```

apenas se o custo/tempo for aceitável.

E principalmente:

```bash
flutter build apk --debug
```

ou o build Android equivalente já utilizado pelo projeto.

Não executar testes completos do backend nem suítes grandes.

---

## 7. Verificação do Intent

O comportamento esperado no Android é equivalente a:

```text
ACTION_VIEW
lio://payment...
```

resolvendo para:

```text
br.com.cielosmart.orderservice/com.cielo.lio.uriappclient.activities.CheckoutActivity
```

Não adicionar uma Activity própria para substituir a Cielo.

Não criar fallback fake.

Não remover `setPackage()` sem justificativa técnica.

---

## Critérios de aceite

A missão só está concluída se:

1. O package utilizado pelo CORE for:

```text
br.com.cielosmart.orderservice
```

2. O Manifest declarar esse mesmo package em `<queries>`.

3. O CORE conseguir resolver o aplicativo Cielo Smart instalado no aparelho.

4. O `lio://payment` for enviado para:

```text
com.cielo.lio.uriappclient.activities.CheckoutActivity
```

através do aplicativo:

```text
br.com.cielosmart.orderservice
```

5. O POS não exibir mais falsamente:

> "O aplicativo Cielo não está disponível"

quando o aplicativo está instalado.

6. O erro continuar sendo apresentado ao POS caso a abertura realmente falhe.

7. Nenhuma regra financeira seja alterada.

8. Nenhuma alteração seja feita em Mesa/Comanda.

9. Não sejam adicionadas dependências desnecessárias.

10. O APK debug seja compilável para podermos instalar no aparelho e testar o fluxo real.

### Resultado esperado do teste manual

No aparelho:

```text
CORE POS
→ iniciar pagamento Cielo
→ Android abre Cielo Smart Emulator
→ tela de pagamento Cielo aparece
```

Neste ponto, parar a missão de integração de abertura.

Não considerar o pagamento aprovado apenas porque o aplicativo abriu.

### Entrega

Ao finalizar, informar:

* arquivos alterados;
* commit criado;
* resultado do build;
* eventual erro encontrado;
* confirmação do package final utilizado.

Não fazer nenhuma alteração fora deste escopo.
