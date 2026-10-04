AGORA TEMOS A CAUSA COMPROVADA DO CONFLITO CIELO.

Log real:

```text
current_amount=65.00
current_reference_present=True
current_reference_matches=True

conflicting_amount=2.58

same_intent=False
same_origin=False
same_order=False
same_reference=False
same_amount=False

conflicting_attempt_status=approved
conflicting_intent_status=applied
conflicting_payment_exists=True
conflicting_intent_applied=True

transaction_fingerprint=939f2965eff4
```

CONCLUSÃO:

O Emulador/SANDBOX da Cielo está reutilizando o mesmo `paymentTransactionId` em operações completamente diferentes.

A operação antiga:

- outro checkout;
- outro intent;
- outra order;
- outra reference;
- outro valor;
- já foi APPLIED.

A operação atual:

- R$ 65,00;
- nova order;
- nova reference;
- `current_reference_matches=True`.

Portanto o callback atual pertence corretamente à tentativa atual.

O conflito atual é FALSO POSITIVO causado pela regra:

```text
(provider_connection, provider_transaction_id) UNIQUE
```

aplicada também ao ambiente SANDBOX/EMULADOR.

==================================================
1. NÃO IGNORAR O CONFLITO GLOBALMENTE
==================================================

NÃO simplesmente remover a proteção contra duplicidade.

Em PRODUÇÃO ainda precisamos impedir que a mesma transação externa seja aplicada duas vezes.

A correção deve diferenciar:

PRODUCTION

e

SANDBOX.

==================================================
2. IDENTIDADE DA TRANSAÇÃO CIELO
==================================================

`paymentTransactionId` isoladamente não pode ser usado como identidade absoluta no Emulador Cielo, porque acabamos de comprovar reutilização entre orders diferentes.

Para Cielo SANDBOX, considerar a identidade composta da operação.

No mínimo:

```text
provider_connection
+
provider_order_id
+
provider_transaction_id
```

E utilizar também:

```text
provider_reference
```

como correlação entre callback e PaymentAttempt.

A referência que enviamos é:

```text
CORE-{attempt.id}
```

Se o callback retornar reference:

```text
reference == CORE-{attempt.id}
```

isso comprova vínculo com a tentativa atual.

==================================================
3. REGRA PARA SANDBOX CIELO
==================================================

Quando:

```text
provider = cielo
connection.environment = SANDBOX
```

e aparecer outro PaymentAttempt com o mesmo:

```text
provider_transaction_id
```

NÃO considerar conflito automaticamente.

Comparar:

```text
provider_order_id
provider_reference
origin
amount
```

Se:

```text
same_order = False
same_reference = False
```

e o callback atual possui:

```text
current_reference_matches = True
```

então são operações externas distintas do emulador.

Nesse caso o transaction ID repetido NÃO deve impedir o processamento do pagamento atual.

Fluxo esperado:

Cielo SUCCESS
→ reference corresponde ao attempt atual
→ order atual é diferente da operação antiga
→ valor corresponde ao intent atual
→ callback é aceito
→ attempt APPROVED
→ intent APPROVED
→ QuickSalePayment
→ APPLIED.

==================================================
4. PRODUÇÃO CONTINUA FORTE
==================================================

Quando:

```text
environment = PRODUCTION
```

não flexibilizar essa proteção sem evidência real de comportamento igual em produção.

Em produção, transaction ID duplicado continua sendo evento crítico.

Portanto:

PRODUCTION:
→ proteção forte.

CIELO SANDBOX:
→ permitir transaction ID repetido somente quando a operação estiver comprovadamente associada a outra order/reference.

==================================================
5. REVER A CONSTRAINT DO BANCO
==================================================

A constraint atual:

```text
(provider_connection, provider_transaction_id)
```

não é compatível com o comportamento comprovado do Cielo SANDBOX.

Não resolver apenas na camada Python porque o banco continuará rejeitando o INSERT/UPDATE.

Redesenhar a constraint para preservar deduplicação sem gerar falso conflito.

Uma possibilidade conceitual:

```text
provider_connection
+
provider_order_id
+
provider_transaction_id
```

para identificação externa.

Mas revisar a arquitetura antes de aplicar, porque precisamos preservar comportamento dos demais providers futuros.

Não criar regra Cielo espalhada pelo domínio financeiro se puder modelar uma identidade externa composta de forma genérica.

==================================================
6. NÃO ALTERAR O IDENTIFICADOR RECEBIDO
==================================================

NÃO fazer:

```text
transaction_id = transaction_id + UUID
```

NÃO inventar identificador.

NÃO modificar o valor retornado pela Cielo.

O `provider_transaction_id` deve continuar representando exatamente o valor retornado pelo provider.

Se for necessário um identificador interno de deduplicação, criar um conceito separado, por exemplo:

```text
provider_operation_key
```

ou equivalente genérico.

Não corromper o dado original do provider.

==================================================
7. REFERÊNCIA É NOSSA PROVA FORTE
==================================================

Para o pagamento atual temos:

```text
current_reference_matches=True
```

Isso significa que a Cielo devolveu exatamente:

```text
CORE-{attempt atual}
```

Logo esse callback não pertence à operação antiga de R$ 2,58.

Essa informação deve ser usada explicitamente para evitar o falso UNKNOWN.

Se reference estiver presente e for diferente:

→ UNKNOWN.

Se reference corresponder:

→ continuar as demais validações.

==================================================
8. VALIDAÇÕES QUE CONTINUAM OBRIGATÓRIAS
==================================================

Mesmo em SANDBOX, só aceitar SUCCESS quando:

- reference corresponde ao attempt atual quando presente;
- amount corresponde ao amount atual;
- order existe;
- payment válido existe;
- statusCode representa aprovação;
- provider é o esperado;
- callback pertence à conexão correta.

Transaction ID repetido sozinho NÃO pode invalidar a transação quando:

```text
order diferente
reference diferente da operação antiga
reference atual correta
amount atual correto
```

==================================================
9. REPROCESSAR O FLUXO ATUAL
==================================================

Depois dessa correção, um cenário como o log real:

```text
CURRENT
R$ 65,00
reference correta
order nova

OLD
R$ 2,58
reference diferente
order diferente
APPLIED

transaction ID igual
```

deve resultar em:

```text
CURRENT → APPROVED → APPLIED
```

e NÃO:

```text
CURRENT → UNKNOWN
```

==================================================
10. CORRIGIR AUDITORIA
==================================================

Existe ainda uma inconsistência encontrada no código.

Em:

`resolve_quick_sale_payment_attempt()`

o audit log usa:

```text
'status': status
```

Esse `status` é o resultado original recebido do parser.

Se internamente a resolução mudar o estado para outro valor, a auditoria pode registrar valor incorreto.

Usar:

```text
resolved_attempt.status
```

como estado efetivamente persistido.

A auditoria deve registrar o que realmente ficou no banco.

==================================================
11. NÃO MEXER
==================================================

Não mexer novamente em:

- callback Android;
- Base64;
- callbackParameter;
- CieloResponseActivity;
- parser SUCCESS;
- parser ERROR;
- reversal;
- modal;
- impressão;
- Mesa;
- Comanda.

O callback e o parser estão funcionando.

O problema agora é exclusivamente a estratégia de identidade/deduplicação do provider.

==================================================
RESULTADO ESPERADO
==================================================

Para o cenário REAL comprovado:

```text
transaction ID repetido
same_order=False
same_reference=False
same_origin=False
same_intent=False
same_amount=False
current_reference_matches=True
provider=Cielo
environment=SANDBOX
```

o CORE deve reconhecer:

`São duas operações diferentes do Emulador Cielo.`

E processar a atual normalmente:

```text
APPROVED
→ APPLIED
→ QuickSalePayment
```

sem duplicar a operação antiga.

Em PRODUCTION, manter a proteção forte contra reaproveitamento indevido de transação externa.

Não fazer commit.
Não rodar testes.