O SUCCESS REAL DA CIELO ESTÁ CHEGANDO.

Agora temos este comportamento:

```text
POST /provider-payments/attempts/83440027-29d0-449f-aefa-9008783190db/result/
→ HTTP 409
```

Na tela aparece algo como:

`Não foi possível verificar a unicidade com a Cielo`

Isso significa que o callback SUCCESS foi recebido e parseado, mas o `provider_transaction_id` retornado já pertence a outra `PaymentAttempt`.

NÃO mexer novamente no callback Cielo.

NÃO remover a UniqueConstraint.

NÃO considerar aprovado automaticamente.

Precisamos corrigir a CAUSA do conflito.

==================================================
1. IDENTIFICAR O REGISTRO CONFLITANTE
==================================================

No momento em que:

`resolve_payment_attempt()`

detectar:

`provider_transaction_conflict`

localizar a `PaymentAttempt` que já possui:

```text
provider_connection = current.provider_connection
provider_transaction_id = transaction_id recebido
```

Comparar:

TENTATIVA ATUAL:
- attempt id;
- intent id;
- origin_id / checkout;
- attempt_number;
- amount;
- status;
- provider_order_id;
- provider_reference.

TENTATIVA CONFLITANTE:
- attempt id;
- intent id;
- origin_id;
- attempt_number;
- amount;
- status;
- intent status;
- provider_order_id;
- provider_reference;
- se existe QuickSalePayment ligada;
- se o intent já está APPLIED.

Não expor `provider_transaction_id` completo em log.

Usar apenas fingerprint/hash curto.

==================================================
2. PRECISAMOS SABER QUAL DESTES CASOS É
==================================================

CASO A — MESMA OPERAÇÃO / REPLAY

Se o registro conflitante representa na verdade a mesma operação financeira já processada:

→ tratar como replay idempotente;
→ retornar o estado atual;
→ não criar pagamento novo;
→ não retornar 409 ao operador.

CASO B — OUTRA TENTATIVA DO MESMO INTENT

Analisar se ocorreu retry e a Cielo devolveu a mesma transação externa.

Se for comprovadamente a mesma cobrança:

→ não duplicar;
→ reconciliar de forma idempotente com a operação já existente.

CASO C — OUTRO CHECKOUT / OUTRO INTENT

Se o transaction ID pertence de verdade a outra venda:

→ NÃO aplicar na venda atual;
→ NÃO retornar SUCCESS;
→ NÃO permitir nova cobrança às cegas.

A tentativa atual deve ficar em estado financeiro seguro, preferencialmente UNKNOWN se não houver prova suficiente.

CASO D — EMULADOR REUTILIZANDO IDENTIFICADOR

Confirmar pelos dados antes de criar qualquer exceção.

Se duas operações realmente diferentes do Emulador Cielo estiverem retornando o mesmo `paymentTransactionId`, isso precisa ser tratado como particularidade de SANDBOX/EMULADOR.

NÃO afrouxar a regra de produção.

==================================================
3. A REFERÊNCIA CORE É FUNDAMENTAL
==================================================

Nós enviamos para a Cielo:

```text
reference = CORE-{attempt.id}
```

No SUCCESS, quando o retorno possuir `reference`, ela precisa corresponder exatamente à tentativa atual.

Se:

```text
reference != CORE-{attempt.id}
```

→ callback não pertence a essa tentativa;
→ UNKNOWN/conflito controlado.

Se a resposta não trouxer `reference`, registrar isso de forma sanitizada:

```text
reference_present=false
```

Isso é importante para descobrir se o emulador está devolvendo um objeto antigo ou uma transação nova com identificador repetido.

==================================================
4. NÃO DEIXAR 409 EM LOOP
==================================================

Hoje ocorreu:

SUCCESS Cielo
→ 409
→ GET checkout
→ callback continua pendente.

Se o usuário tocar `TENTAR CONFIRMAR PAGAMENTO`:

→ mesmo callback;
→ mesmo conflito;
→ mesmo 409.

Isso não resolve nada.

Depois de classificar um conflito determinístico:

NÃO continuar oferecendo simplesmente `TENTAR CONFIRMAR PAGAMENTO`.

Retry de confirmação deve existir apenas para:

- falha de internet;
- timeout;
- backend temporariamente indisponível.

Um conflito de identidade não é erro transitório.

==================================================
5. MELHORAR A MENSAGEM
==================================================

Não mostrar ao operador:

`Não foi possível verificar a unicidade com a Cielo`

porque a Cielo já respondeu.

Para conflito ainda não reconciliado, usar algo operacional como:

`Pagamento aguardando verificação`

`A Cielo retornou a transação, mas o CORE encontrou um conflito com um registro anterior. Não realize uma nova cobrança até a verificação ser concluída.`

Isso deve ser estado financeiro persistente, não apenas SnackBar.

==================================================
6. NÃO TRANSFORMAR CONFLITO EM ERROR
==================================================

Esse ponto é importante.

A Cielo acabou de informar SUCCESS.

Então se existe conflito de identidade:

NÃO marcar simplesmente:

`ERROR`

porque isso poderia liberar o operador para cobrar novamente quando talvez já exista uma cobrança real.

Quando não conseguirmos reconciliar com segurança:

→ UNKNOWN.

==================================================
7. LOG QUE EU QUERO VER
==================================================

Quando acontecer novamente, registrar algo assim:

```text
CIELO_TRANSACTION_CONFLICT

current_attempt_id=
current_intent_id=
current_origin_id=
current_attempt_number=
current_status=
current_amount=
current_reference_present=
current_reference_matches=

conflicting_attempt_id=
conflicting_intent_id=
conflicting_origin_id=
conflicting_attempt_number=
conflicting_attempt_status=
conflicting_intent_status=
conflicting_amount=
conflicting_payment_exists=
conflicting_intent_applied=

same_intent=
same_origin=
same_amount=
same_order=
same_reference=

transaction_fingerprint=
```

Sem dados sensíveis.

==================================================
8. MUITO IMPORTANTE
==================================================

Não mexer em:

- callbackParameter;
- Base64;
- CieloResponseActivity;
- SUCCESS parser;
- ERROR parser;
- reversal;
- regra provider-first;
- UniqueConstraint.

O callback já está chegando.

O problema atual é exclusivamente:

`identidade da transação externa x PaymentAttempt já existente`.

==================================================
9. RESULTADO ESPERADO
==================================================

Depois da correção:

Se for transaction ID novo:

Cielo SUCCESS
→ APPROVED
→ APPLIED
→ QuickSalePayment
→ aparece normalmente em Pagamentos realizados.

Se for replay da mesma operação:

→ reconhece replay;
→ não duplica pagamento;
→ retorna estado atual.

Se pertencer a outra operação:

→ UNKNOWN/controlado;
→ não 500;
→ não duplica;
→ não permite nova cobrança irresponsavelmente.

E principalmente:

descobrir e informar na própria execução QUAL PaymentAttempt está causando o conflito e por quê.

Não fazer commit.
Não rodar testes.