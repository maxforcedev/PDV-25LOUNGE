MISSÃO PAY-2.1.7 — CORRIGIR ESTORNO CIELO REAL + RETORNO DE ERRO/CANCELAMENTO

Trabalhar sobre o HEAD:

`2b1f545b212c5a5748c7b3468f0755092737b316`
`Add Cielo provider reversals`

IMPORTANTE:

O PAGAMENTO CIELO NORMAL JÁ ESTÁ FUNCIONANDO.

NÃO REGREDIR:

Cielo pagamento
→ callback
→ APPROVED
→ APPLIED
→ QuickSalePayment
→ Pagamentos realizados.

O commit anterior também já:

- removeu a mensagem/painel antigo de CANCELLED/ERROR;
- colocou modal;
- removeu reimpressão individual;
- devolveu opção de estorno;
- criou `ProviderReversalOperation`.

MANTER tudo isso.

Agora corrigir especificamente o contrato REAL do estorno Cielo e o retorno de erro da Cielo.

==================================================
1. BUG NO REQUEST DE PAYMENT-REVERSAL
==================================================

Revisar:

`backend/apps/payment_integrations/providers/cielo.py`

Hoje `build_reversal_command()` está montando algo equivalente a:

```python
{
    "clientID": ...,
    "accessToken": ...,
    "orderId": ...,
    "cieloCode": ...,
    "authCode": ...,
    "value": "2000"
}
```

Isso NÃO corresponde ao contrato oficial do Cielo Smart.

O request correto do `lio://payment-reversal` usa:

```text
{
    "id": "ID DA ORDEM",
    "clientID": "...",
    "accessToken": "...",
    "cieloCode": "...",
    "authCode": "...",
    "value": 2000
}
```

CORRIGIR:

`orderId`

para:

`id`

E enviar:

`value`

como número inteiro em centavos, não string.

Portanto:

ERRADO:

```text
"orderId": "..."
"value": "2000"
```

CORRETO:

```text
"id": "..."
"value": 2000
```

Manter:

`lio://payment-reversal`

e:

`urlCallback=corepdv://cielo-payment-reversal-response`

==================================================
2. PARSER DE SUCESSO DO ESTORNO ESTÁ ERRADO
==================================================

Hoje `parse_reversal_callback()` espera um payload artificial semelhante a:

```text
{
    "statusCode": "0",
    "orderId": "..."
}
```

Isso NÃO representa o retorno real documentado pela Cielo Smart.

O retorno de sucesso do cancelamento é novamente o OBJETO DA ORDEM.

Estrutura conceitual:

```text
{
    "id": "ID DA ORDEM",
    ...
    "payments": [
        {
            ...
            "paymentFields": {
                "statusCode": "1",
                ...
            }
        },
        {
            ...
            "paymentFields": {
                "statusCode": "2",
                ...
            }
        }
    ]
}
```

REGRA OFICIAL:

`paymentFields.statusCode = 1`
→ transação de pagamento.

`paymentFields.statusCode = 2`
→ transação de CANCELAMENTO.

Portanto o parser de reversal deve:

1. decodificar o Base64;
2. obter o objeto da ordem;
3. validar:

`payload.id == source_attempt.provider_order_id`

4. garantir que `payments` é uma lista válida;
5. localizar a transação de CANCELAMENTO:
   `paymentFields.statusCode == 2`;
6. garantir que exista exatamente uma transação comprovável correspondente;
7. validar o valor do cancelamento contra `reversal.amount`;
8. validar vínculo com a transação original usando os identificadores disponíveis;
9. somente então retornar:

`ProviderReversalStatus.APPROVED`.

NÃO usar:

`statusCode 0/1 top-level`

como prova de estorno.

==================================================
3. CORRELACIONAR O ESTORNO COM O PAGAMENTO ORIGINAL
==================================================

O pagamento original já possui:

- `provider_order_id`;
- `authorization_code`;
- `nsu` / cieloCode;
- `provider_transaction_id`;
- amount.

Usar essas informações para comprovar que o cancelamento retornado pertence à transação correta.

Obrigatório validar:

- mesma order;
- mesmo valor;
- transação de cancelamento real (`statusCode=2`).

Quando o callback trouxer campos como:

`originalTransactionId`

ou outros identificadores da transação original, utilizá-los para reforçar a correlação com a operação aprovada original.

NÃO aprovar uma reversal apenas porque existe qualquer `payment` com statusCode 2.

Ambiguidade:

→ UNKNOWN.

Inconsistência:

→ UNKNOWN.

Nunca:

→ APPROVED por aproximação.

==================================================
4. RETORNO DE ERRO DA CIELO NÃO ESTÁ CHEGANDO/REFLETINDO NO CORE
==================================================

Existe outro problema real durante o teste:

Quando selecionamos ERRO na Cielo, o CORE não está recebendo/apresentando corretamente a resposta.

Investigar o fluxo COMPLETO de ERRO, tanto em:

PAGAMENTO

quanto em:

ESTORNO.

A Cielo retorna erro/cancelamento pelo callback configurado.

O parâmetro:

`response`

contém Base64.

Depois de decodificado:

```text
{
    "code": 1,
    "reason": "CANCELADO PELO USUÁRIO"
}
```

ou:

```text
{
    "code": 2,
    "reason": "..."
}
```

etc.

Mapeamento:

`code = 1`
→ CANCELLED

`code = 2`
→ ERROR genérico

`code = 3`
→ ERROR no pagamento

`code = 4`
→ ERROR de autenticação.

ATENÇÃO:

O `responsecode` externo pode continuar sendo `0`.

Portanto:

NÃO interpretar:

`responsecode == 0`

como sucesso automaticamente.

O conteúdo Base64 de `response` precisa ter prioridade.

==================================================
5. TRAÇAR ONDE O ERRO ESTÁ SENDO PERDIDO
==================================================

Verificar:

Cielo
→ callback URI
→ `CieloResponseActivity`
→ `CieloPaymentBridge.deliverCallback`
→ `pendingCallback`
→ MethodChannel
→ Flutter `CieloPaymentCallback`
→ `_receiveCieloCallback`
→ `_drainPendingProviderCallback`
→ endpoint backend
→ parser
→ status ERROR/CANCELLED
→ modal.

Precisamos descobrir exatamente onde o retorno de ERRO está parando.

Adicionar/manter logs SANITIZADOS para:

Android:

```text
CIELO_CALLBACK_ACTIVITY
operation=payment|reversal
scheme
host
query_names
response_present
response_length
responsecode_present
active_operation_present
```

Bridge:

```text
CIELO_CALLBACK_RECEIVED
CIELO_CALLBACK_PENDING_CREATED
CIELO_CALLBACK_CHANNEL
CIELO_CALLBACK_ACK
```

Flutter:

```text
callback_received
operation
operation_id
response_present
response_length
resolve_started
resolve_returned
resolved_status
ack_sent
modal_opened
```

Backend:

Pagamento:

```text
provider_result_received
provider_result_parsed
```

Reversal:

```text
provider_reversal_result_received
provider_reversal_result_parsed
```

Se parser retornar error:

registrar apenas:

```text
provider_status=error
provider_status_code
```

NUNCA logar:

- Base64 completo;
- accessToken;
- clientID;
- PAN;
- URI completa;
- payload bruto;
- dados sensíveis do cartão.

==================================================
6. ANDROID DEVE PRESERVAR O CALLBACK DE ERRO
==================================================

A correção existente de:

`callbackParameter(uri, "response")`

deve permanecer.

NÃO voltar para:

`uri.getQueryParameter("response")`

porque já corrigimos a preservação do Base64 contendo:

`+`
`/`
`=`
CR/LF.

Garantir que essa mesma leitura seja utilizada tanto para:

`payment`

quanto para:

`reversal`.

==================================================
7. NÃO DESCARTAR CALLBACK DE ERROR
==================================================

Revisar este comportamento:

```text
if pendingCallback != null
    CIELO_CALLBACK_DUPLICATE
    return
```

Garantir que um callback antigo/stale não consiga fazer o callback novo de ERROR ser descartado incorretamente.

A correlação deve ser:

`operation + operation_id`.

ACK de PAYMENT limpa somente PAYMENT correspondente.

ACK de REVERSAL limpa somente REVERSAL correspondente.

Não deixar callback anterior impedir o resultado da operação atual.

==================================================
8. MODAL DE ERRO DE PAGAMENTO
==================================================

Quando a Cielo retornar:

```text
{
    "code": 3,
    "reason": "..."
}
```

o pagamento deve resultar em:

`ERROR`

e o POS deve abrir:

Título:

`Erro no pagamento`

Mensagem:

`reason` sanitizado retornado pela Cielo.

Ações:

`FECHAR`

e:

`TENTAR NOVAMENTE`

quando `canRetry == true`.

Depois de fechar:

NÃO deixar painel antigo de erro.

==================================================
9. MODAL DE CANCELAMENTO DE PAGAMENTO
==================================================

Quando:

`code = 1`

abrir:

`Pagamento cancelado`

Mensagem:

`Cancelado pelo usuário.`

ou `reason` sanitizado da Cielo.

Após OK:

- modal fecha;
- nenhum pagamento é criado;
- checkout continua aberto;
- operador pode escolher uma nova forma de pagamento;
- nenhum painel antigo fica na tela.

==================================================
10. MODAL DE ERRO DO ESTORNO
==================================================

Quando ERRO ocorrer no `payment-reversal`:

→ ProviderReversalOperation = ERROR

→ NÃO criar QuickSalePayment de reversal;

→ pagamento original continua APPLIED;

→ paid_amount continua inalterado;

→ abrir modal:

`Erro no estorno`

com o `reason` retornado pela Cielo.

Botão:

`OK`

Se decidirmos permitir nova tentativa de reversal depois do ERROR, ela deve criar/reutilizar operação de forma idempotente e segura.

==================================================
11. CANCELAMENTO DO ESTORNO
==================================================

Se o usuário cancelar o fluxo na própria Cielo:

`code = 1`

→ ProviderReversalOperation = CANCELLED

→ pagamento original continua ativo;

→ nenhum reversal local;

→ modal:

`Estorno cancelado`

`Estorno cancelado pelo usuário.`

==================================================
12. SUCCESS DO ESTORNO
==================================================

Fluxo correto:

operador toca ESTORNAR
→ autorização quando necessária
→ cria ProviderReversalOperation
→ PROCESSING
→ abre:

`lio://payment-reversal`

→ Cielo confirma
→ callback contém objeto completo da ordem
→ parser encontra transação:
`paymentFields.statusCode = 2`
→ valida ordem + valor + correlação
→ ProviderReversalOperation APPROVED
→ `apply_approved_provider_quick_checkout_reversal`
→ cria QuickSalePayment de reversal
→ ProviderReversalOperation APPLIED
→ original aparece ESTORNADO
→ paid_amount diminui
→ remaining_amount aumenta.

O PaymentAttempt original CONTINUA:

`APPROVED`.

Não alterar histórico da captura original.

==================================================
13. FALHA AO ABRIR A CIELO NO ESTORNO
==================================================

Existe outro problema no código atual.

Hoje:

`startQuickSaleProviderReversal`

cria:

ProviderReversalOperation
→ PROCESSING

Depois Flutter tenta abrir a Cielo.

Se `_cieloBridge.launch()` gerar `PlatformException`, atualmente só aparece uma mensagem.

A operação pode ficar eternamente:

`PROCESSING`.

CORRIGIR.

Criar tratamento equivalente ao:

`provider payment launch-failed`

mas para REVERSAL.

Exemplo de endpoint conceitual:

```text
provider-reversals/{operation_id}/launch-failed/
```

Só usar quando for comprovado que a Cielo NÃO foi aberta.

Nesse caso:

PROCESSING
→ ERROR

provider_status:

`launch_error`

provider_message:

`Não foi possível iniciar o estorno na Cielo.`

Liberar o checkout de maneira segura para tentar novamente.

NÃO marcar launch-failed se existe possibilidade de a Cielo ter sido aberta.

==================================================
14. CIELO ABRIU MAS NÃO RETORNOU CALLBACK
==================================================

Situação diferente:

Android conseguiu abrir a Cielo.

Depois não recebemos callback.

NÃO fazer:

PROCESSING → ERROR automaticamente.

Ausência de callback NÃO prova falha.

Nesse caso manter:

`PROCESSING`

ou:

`UNKNOWN`

conforme a política atual de recuperação.

Mostrar ao operador algo como:

`ESTORNO AGUARDANDO CONFIRMAÇÃO DA CIELO`

e bloquear novo estorno conflitante.

Nunca criar reversal local sem confirmação externa.

==================================================
15. BLOQUEAR NOVO PAGAMENTO DURANTE REVERSAL
==================================================

Hoje `_quick_checkout_payload()` considera `blocking_reversal` para:

- editar;
- finalizar;
- estornar.

Porém revisar:

`can_record_payment`.

Durante:

ProviderReversalOperation:

`CREATED`
`PROCESSING`
`UNKNOWN`
`APPROVED`

NÃO deve ser possível iniciar um novo pagamento conflitante.

Portanto:

`can_record_payment`

também deve considerar:

`not blocking_reversal`.

A interface não deve oferecer uma ação que o backend posteriormente rejeitará.

==================================================
16. TESTE DE SUCCESS ATUAL ESTÁ ARTIFICIAL
==================================================

Hoje o teste do reversal simula:

```text
{
    "statusCode": "0",
    "orderId": "..."
}
```

REMOVER essa suposição.

Criar fixture realista baseada na estrutura oficial.

Exemplo conceitual:

```text
{
    "id": "cielo-order-reversal-1",
    "payments": [
        {
            "amount": 2000,
            "authCode": "...",
            "cieloCode": "...",
            "paymentFields": {
                "statusCode": "1",
                ...
            }
        },
        {
            "amount": 2000,
            "authCode": "...",
            "cieloCode": "...",
            "paymentFields": {
                "statusCode": "2",
                ...
            }
        }
    ]
}
```

O parser deve escolher a transação de CANCELAMENTO:

`statusCode = 2`.

==================================================
17. TESTES DE ERRO REAIS
==================================================

Adicionar testes para callback Cielo exatamente no formato:

CANCELADO:

```text
Base64({
    "code": 1,
    "reason": "CANCELADO PELO USUÁRIO"
})
```

ERROR:

```text
Base64({
    "code": 3,
    "reason": "ERRO NO PAGAMENTO"
})
```

com:

`responsecode = 0`.

Provar que:

responsecode 0 + payload code 3

resulta em:

ERROR

e NÃO APPROVED.

Mesma lógica para reversal.

==================================================
18. TESTES DIRECIONADOS
==================================================

NÃO rodar suíte completa.

Executar somente testes cirúrgicos:

1. request reversal utiliza `id`, não `orderId`;
2. `value` é número inteiro;
3. success realista com order + payments + statusCode 2;
4. transação statusCode 1 NÃO é confundida com reversal;
5. order diferente → UNKNOWN;
6. valor diferente → UNKNOWN;
7. mais de um candidato ambíguo → UNKNOWN;
8. ERROR `{code:3, reason:...}` → ERROR;
9. CANCEL `{code:1, reason:...}` → CANCELLED;
10. `responsecode=0` não mascara `code=3`;
11. ERROR não cria reversal local;
12. CANCELLED não cria reversal local;
13. SUCCESS cria exatamente UM reversal;
14. replay de callback não duplica;
15. launch-failed libera operação corretamente;
16. blocking reversal desabilita novo pagamento;
17. pagamento Cielo normal continua funcionando;
18. modal de ERROR aparece uma vez;
19. modal de CANCELLED aparece uma vez.

==================================================
19. TESTE MANUAL OBRIGATÓRIO NO EMULADOR
==================================================

ESTORNO — SUCCESS:

→ tocar ESTORNAR
→ Cielo abre tela de cancelamento
→ escolher sucesso
→ CORE recebe callback
→ pagamento fica ESTORNADO
→ saldo é restaurado.

ESTORNO — CANCELADO:

→ tocar ESTORNAR
→ cancelar na Cielo
→ CORE recebe callback
→ modal `Estorno cancelado`
→ pagamento continua ativo.

ESTORNO — ERRO:

→ tocar ESTORNAR
→ selecionar ERRO na Cielo
→ CORE PRECISA RECEBER O CALLBACK
→ modal `Erro no estorno`
→ mostrar reason
→ pagamento continua ativo.

PAGAMENTO — ERRO:

→ iniciar novo pagamento
→ selecionar ERRO
→ CORE PRECISA RECEBER O CALLBACK
→ modal `Erro no pagamento`
→ reason retornado pela Cielo.

Se ERROR continuar sem retornar:

NÃO mascarar.

Capturar logs sanitizados de:

CieloResponseActivity
CieloPaymentBridge
Flutter
backend

e informar exatamente em qual camada o callback deixou de existir.

==================================================
20. NÃO FAZER
==================================================

NÃO:

- mexer novamente no sucesso do pagamento normal;
- aprovar pelo frontend;
- considerar ausência de callback como ERROR;
- estornar CORE antes da Cielo;
- apagar PaymentAttempt original;
- criar CieloReversal financeiro paralelo;
- afrouxar idempotência;
- executar suíte completa;
- mexer em Mesa;
- mexer em Comanda;
- mexer em impressão;
- mexer em estoque.

==================================================
CRITÉRIO FINAL
==================================================

Só fechar essa missão quando existirem quatro fluxos comprovados:

1. PAGAMENTO SUCCESS
   → continua funcionando.

2. PAGAMENTO ERROR
   → Cielo retorna ao CORE
   → modal mostra erro.

3. REVERSAL SUCCESS
   → Cielo confirma cancelamento
   → CORE aplica reversal.

4. REVERSAL ERROR/CANCELLED
   → Cielo retorna ao CORE
   → modal correspondente
   → pagamento original permanece ativo.

Ao finalizar informar:

1. causa exata do ERROR não retornar;
2. URI de callback utilizada, sem secrets;
3. formato sanitizado observado do callback ERROR;
4. formato sanitizado observado do reversal SUCCESS;
5. correção feita no request `payment-reversal`;
6. correção feita no parser;
7. correção do launch-failed;
8. correção de `can_record_payment`;
9. arquivos alterados;
10. testes direcionados executados;
11. resultado dos 4 testes manuais;
12. hash do commit.

Não considere concluído apenas porque os testes sintéticos passam.

Quero confirmação real no emulador da Cielo.