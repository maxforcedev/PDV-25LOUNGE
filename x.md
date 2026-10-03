MISSÃO PAY-2.1.4 — CORRIGIR CALLBACK CIELO: SUCESSO, CANCELAMENTO E ERRO

Contexto atual:

A abertura da Cielo já está funcionando corretamente.

O package Android já foi corrigido para:

br.com.cielosmart.orderservice

O fluxo atual está assim:

CORE POS
→ cria PaymentIntent / PaymentAttempt
→ gera lio://payment
→ abre Cielo
→ Cielo deve retornar para:

corepdv://cielo-payment-response

→ CieloResponseActivity
→ CieloPaymentBridge.deliverCallback()
→ Flutter
→ endpoint de resolução do pagamento
→ backend Cielo parser
→ APPROVED / CANCELLED / ERROR / UNKNOWN
→ aplicação financeira no CORE quando aprovado.

Nos testes reais atuais temos 3 problemas:

CANCELAMENTO

Ao cancelar a operação na Cielo, a cobrança aparentemente é encerrada corretamente, porém o CORE não apresenta de forma clara e persistente:

Pagamento cancelado pelo usuário.

O backend já possui tratamento de cancelamento no adapter Cielo.

Não quero apenas um SnackBar rápido.

Quando a Cielo confirmar cancelamento, o estado da cobrança precisa ser atualizado corretamente e a interface deve apresentar de forma persistente que aquela tentativa foi cancelada.

Depois disso o operador deve conseguir iniciar uma nova tentativa de pagamento normalmente, respeitando as regras financeiras existentes.

Não criar automaticamente outra cobrança.

ERRO

Quando simulamos erro na Cielo, a mensagem aparece no CORE mas desaparece muito rápido.

Corrigir isso.

Erros de provider relevantes não podem depender apenas de uma notificação transitória.

A área de pagamento deve conseguir mostrar de forma persistente o estado de erro da última tentativa enquanto aquele estado for relevante.

Exibir uma mensagem segura ao operador, sem expor payload sensível, credenciais ou dados de cartão.

Quando o estado permitir retry, mostrar a opção:

TENTAR NOVAMENTE

O retry precisa continuar usando o fluxo existente, sem criar duplicidade financeira.

SUCESSO — PROBLEMA CRÍTICO

Quando simulamos pagamento aprovado na Cielo:

Cielo fica/processa a operação;

voltamos para o CORE;

o CORE permanece em PROCESSING;

o pagamento não chega corretamente a APPROVED/APPLIED.

Esse é o principal problema desta missão.

NÃO inventar aprovação no frontend.

NÃO alterar PROCESSING para APPROVED manualmente.

A aprovação só pode acontecer a partir do retorno real da Cielo processado pelo backend.

Precisamos descobrir exatamente onde o callback de sucesso está sendo perdido.

Investigar o fluxo completo:

Cielo
→ callback URI
→ CieloResponseActivity
→ CieloPaymentBridge.deliverCallback()
→ pendingCallback
→ MethodChannel paymentCallback
→ Flutter CieloPaymentCallback
→ _receiveCieloCallback
→ _drainPendingProviderCallback
→ resolveQuickSaleProviderPayment
→ endpoint backend
→ parse_payment_callback
→ resolve_quick_sale_payment_attempt
→ APPROVED
→ apply_approved_quick_sale_payment_intent
→ APPLIED

ATENÇÃO ESPECIAL:

Hoje existe:

val attemptId = activeAttemptId ?: return

em CieloPaymentBridge.deliverCallback().

Portanto, se activeAttemptId estiver nulo, o callback é descartado silenciosamente.

Verificar se isso ocorre no retorno real da Cielo.

Não remover a proteção cegamente.

Precisamos preservar a associação correta entre callback e tentativa, mas o retorno não pode desaparecer sem diagnóstico.

ARQUIVOS PRINCIPAIS A REVISAR

Android:

pos/android/app/src/main/kotlin/com/corepdv/pos/CieloPaymentBridge.kt

pos/android/app/src/main/kotlin/com/corepdv/pos/CieloResponseActivity.kt

pos/android/app/src/main/AndroidManifest.xml

Flutter:

pos/lib/payments/cielo_payment_bridge.dart

pos/lib/payments/shared_payment_page.dart

pos/lib/core/app_controller.dart

pos/lib/sales/sale_models.dart

Backend:

backend/apps/pos/views.py

backend/apps/pos/provider_payments.py

backend/apps/payment_integrations/providers/cielo.py

e serviços/modelos financeiros envolvidos no PaymentIntent / PaymentAttempt.

DIAGNÓSTICO TEMPORÁRIO

Adicionar logs seguros, suficientes para descobrir exatamente onde o fluxo está quebrando.

Android:

Ao CieloResponseActivity receber o Intent, registrar apenas:

action;

scheme;

host;

nomes dos query parameters recebidos;

presença ou ausência de response;

presença ou ausência de responsecode;

tamanho do campo response;

existência ou ausência de activeAttemptId.

Em deliverCallback() registrar:

callback recebido;

attempt encontrado ou ausente;

pending callback criado;

envio via MethodChannel;

ACK posterior.

Flutter:

Registrar somente:

callback recebido;

attempt_id;

callback guardado em memória;

início da resolução;

retorno do backend;

ACK enviado;

falha de rede/API.

Backend:

Registrar de forma segura:

endpoint /result/ recebido;

attempt;

provider;

presença/tamanho da response;

responsecode;

resultado do parser:

APPROVED

CANCELLED

ERROR

UNKNOWN

se houve tentativa de APPLY;

se terminou em APPLIED ou apply pending.

NÃO LOGAR:

accessToken

clientID

launch URI completa

Base64 completa

PAN/cartão completo

credenciais

payload sensível completo.

CALLBACK URL

Confirmar que o pagamento enviado para a Cielo contém corretamente:

urlCallback=corepdv://cielo-payment-response

Verificar encoding da URL dentro do lio://payment.

Confirmar que o Android resolve:

scheme:
corepdv

host:
cielo-payment-response

e que CieloResponseActivity realmente é chamada nos três cenários:

aprovado;

cancelado;

erro.

FORMATO DO CALLBACK

Não assumir que sucesso, erro e cancelamento possuem exatamente o mesmo formato.

Capturar de forma segura a estrutura real enviada pelo emulador/Cielo.

O código atual lê somente:

response

e

responsecode

Validar se estes são realmente os parâmetros utilizados no retorno real de:

sucesso;

cancelamento;

erro.

Se existirem outros parâmetros necessários, adaptar a bridge de maneira compatível.

BACKEND CIELO

O parser atual já trata:

erro/cancelamento;

Base64;

payments;

paymentFields;

statusCode;

paymentTransactionId;

valor;

referência;

APPROVED/CANCELLED/UNKNOWN.

Não flexibilizar validações financeiras apenas para fazer o teste passar.

Se o callback real diferir do formato esperado, adaptar com base no retorno real observado, mantendo validação de:

attempt;

provider;

valor;

referência quando disponível;

transaction ID;

status.

Ambiguidade deve continuar virando UNKNOWN, nunca aprovação presumida.

INTERFACE

Adicionar tratamento visual persistente para os estados da integração.

Exemplos esperados:

CANCELADO:

PAGAMENTO CANCELADO

Pagamento cancelado pelo usuário.

Deve permitir nova tentativa quando o backend disser que é seguro.

ERRO:

ERRO NO PAGAMENTO

Mostrar a mensagem sanitizada do provider/backend.

Se permitido:

TENTAR NOVAMENTE

PROCESSING:

PAGAMENTO EM PROCESSAMENTO NA CIELO

Não permitir gerar nova cobrança enquanto existir tentativa bloqueante.

CALLBACK RECEBIDO MAS AINDA NÃO RESOLVIDO:

RETORNO DA CIELO RECEBIDO

AGUARDANDO CONFIRMAÇÃO NO CORE

Botão:

TENTAR CONFIRMAR PAGAMENTO

APPROVED MAS APPLY PENDENTE:

PAGAMENTO APROVADO NA CIELO

O pagamento foi aprovado, mas ainda precisa ser registrado no CORE.

Botão:

TENTAR REGISTRAR NO CORE

APPLIED:

seguir o fluxo financeiro normal existente.

IMPORTANTE SOBRE MENSAGENS

Hoje QuickSalePaymentIntegration possui essencialmente:

intentStatus

attemptStatus

provider

canRetry

canCancel

canApply

requiresRecovery

Se necessário, incluir no payload/modelo uma mensagem sanitizada do provider, como provider_message, para a interface conseguir apresentar o motivo real de CANCELLED/ERROR de forma persistente.

Não depender exclusivamente de showTransientMessage() ou SnackBar para estados financeiros.

REGRAS QUE NÃO PODEM SER QUEBRADAS

Não mexer em Mesas.

Não implementar Comandas.

Não alterar PAY-1.

Não criar CieloPayment ou outro modelo financeiro paralelo.

Continuar usando:

PaymentIntent
→ PaymentAttempt
→ ledger existente.

Não criar pagamento duplicado.

Não liberar nova cobrança enquanto houver tentativa PROCESSING ou estado bloqueante.

Não transformar callback ausente em falha automaticamente.

Não transformar UNKNOWN em aprovado.

Não confiar somente no frontend.

Não marcar pagamento como aprovado sem evidência da Cielo.

Não apagar histórico financeiro.

TESTES

NÃO rodar suíte completa.

Não gastar tempo/crédito rodando centenas de testes não relacionados.