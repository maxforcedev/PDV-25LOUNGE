# CORREÇÃO — ESTADO INICIAL DA VENDA RÁPIDA

Foi identificado um problema no POS durante a validação do ambiente Cielo.

Ao abrir uma **Venda Rápida nova, sem nenhum produto/venda existente**, a interface está exibindo informação equivalente a:

> venda anterior com pagamento aplicado

Isso é incorreto.

Neste momento do projeto, **NÃO existe recuperação de vendas anteriores na Venda Rápida**.

Portanto uma nova Venda Rápida nunca pode iniciar carregando ou exibindo estado financeiro de uma venda anterior.

---

# REGRA OFICIAL

Uma Venda Rápida nova deve começar completamente limpa:

```text
checkout = novo / inexistente
itens = 0
subtotal = 0
total = 0

PaymentIntent = inexistente
PaymentAttempt = inexistente
QuickSalePayment = inexistente
pagamento aplicado = false

provider payment state = none
```

Não existe:

```text
APPROVED
APPLIED
PROCESSING
CANCELLED
ERROR
```

sem que exista um checkout correspondente criado pelo fluxo atual.

---

# 1. INVESTIGAR A ORIGEM DO ESTADO

Descobrir exatamente de onde a UI está obtendo o estado de:

```text
pagamento aplicado
venda anterior
payment status
provider payment
```

Verificar especialmente:

* estado persistido do `QuickSaleCheckout`;
* `SharedPaymentPage`;
* `SaleModels`;
* `AppController`;
* cache local;
* estado restaurado pelo Flutter;
* provider payment state;
* checkout carregado no startup;
* dados mantidos após finalizar uma venda anterior;
* `SharedPreferences`;
* qualquer singleton/controller global;
* qualquer objeto `_checkout` reutilizado indevidamente.

Não assumir a origem.

Encontrar a fonte real.

---

# 2. NÃO IMPLEMENTAR RECUPERAÇÃO DE VENDA

IMPORTANTE:

NÃO criar:

* recuperação de venda;
* consulta de venda anterior;
* histórico automático;
* restauração de checkout anterior;
* sincronização retroativa de venda.

Esse problema NÃO deve ser resolvido adicionando recuperação.

A regra atual é:

> Venda Rápida aberta pelo operador é uma nova operação.

---

# 3. NOVA VENDA RÁPIDA DEVE LIMPAR O ESTADO

Ao iniciar uma nova Venda Rápida:

```text
checkout = null
paymentIntegration = null
providerPaymentState = none
```

ou o equivalente arquitetural correto.

Qualquer estado financeiro anterior deve ser descartado quando a operação anterior tiver sido encerrada.

---

# 4. NÃO USAR ESTADO FINANCEIRO SEM CHECKOUT

Qualquer código equivalente a:

```dart
paymentIntegration.intentStatus
paymentIntegration.attemptStatus
paymentIntegration.canApply
paymentIntegration.canRetry
paymentIntegration.provider
```

deve primeiro exigir:

```text
checkout != null
```

e, principalmente, que o checkout seja o checkout atualmente ativo.

Se não existe checkout:

```text
paymentIntegration = null
```

---

# 5. PAGAMENTO APLICADO

A UI só pode mostrar:

```text
PAGAMENTO APLICADO
```

quando existir um pagamento pertencente ao checkout atual.

Não utilizar:

```text
último pagamento conhecido
último QuickSalePayment
último PaymentIntent
último estado da sessão
```

como fallback.

---

# 6. PAYMENT INTENT

Um `PaymentIntent` anterior não pode aparecer automaticamente em uma Venda Rápida nova.

Só carregar Intent quando ele estiver associado ao:

```text
QuickSaleCheckout
```

que está atualmente aberto no POS.

Se não há checkout:

```text
não carregar PaymentIntent
```

---

# 7. QUICK SALE PAYMENT

Da mesma forma, `QuickSalePayment` histórico não deve ser usado para preencher o estado da nova Venda Rápida.

Não consultar:

```text
último QuickSalePayment
```

para determinar:

```text
payment applied
```

---

# 8. FINALIZAÇÃO DA VENDA ANTERIOR

Verificar o que acontece quando uma Venda Rápida anterior é finalizada.

Depois de:

```text
APPROVED
→ APPLIED
→ finalize checkout
```

o estado da operação anterior deve deixar de ser o checkout ativo.

A próxima:

```text
Nova Venda Rápida
```

deve começar limpa.

---

# 9. CANCELAMENTO / ABANDONO

Também verificar:

```text
Venda Rápida aberta
↓
operador abandona/cancela
↓
nova Venda Rápida
```

A nova operação não pode herdar:

```text
PROCESSING
APPROVED
APPLIED
ERROR
CANCELLED
```

da anterior.

---

# 10. NÃO APAGAR HISTÓRICO DO BANCO

IMPORTANTE:

Não deletar:

```text
QuickSalePayment
PaymentIntent
PaymentAttempt
Sale
```

históricos.

O problema é somente **estado ativo do POS**.

Histórico continua no banco.

---

# 11. NÃO ALTERAR MODELOS FINANCEIROS

Não modificar:

```text
PaymentIntent
PaymentAttempt
QuickSalePayment
sales.Payment
```

sem necessidade.

A princípio isso parece ser um problema de estado/UI/checkout ativo, não de modelo financeiro.

---

# 12. TESTE MANUAL PRINCIPAL

Sem executar suíte grande.

Validar manualmente:

### Cenário A

Abrir POS.

```text
Venda Rápida
```

Esperado:

```text
0 itens
nenhum pagamento
nenhum status financeiro
nenhuma venda anterior
```

---

### Cenário B

Adicionar produto.

Esperado:

```text
produto aparece
total correto
nenhum pagamento aplicado
```

---

### Cenário C

Fechar uma venda normalmente.

Depois abrir:

```text
Nova Venda Rápida
```

Esperado:

```text
0 itens
0 pagamento
nenhum status da venda anterior
```

---

### Cenário D

Se existir uma venda anterior no banco:

```text
Venda A
```

abrir uma nova:

```text
Venda B
```

Venda B NÃO pode mostrar qualquer estado financeiro da Venda A.

---

# 13. CIELO

Essa correção não deve quebrar PAY-2.1.

Em uma Venda Rápida nova:

```text
nenhum checkout
↓
nenhuma cobrança
```

Depois que o operador criar a venda e chegar ao pagamento:

```text
checkout criado
↓
backend determina disponibilidade Cielo
↓
PAGAR NA CIELO
```

Somente então o estado Cielo pode existir.

---

# 14. NÃO CRIAR WORKAROUND

Não resolver simplesmente escondendo o texto:

```text
Pagamento aplicado
```

A origem do estado deve ser corrigida.

Queremos:

```text
estado inexistente
```

e não:

```text
estado existente mas invisível
```

---

# 15. TESTES

NÃO executar suíte completa.

NÃO executar:

* backend completo;
* Flutter completo;
* testes Cielo completos;
* Mesa;
* Comandas.

Se for necessário adicionar teste, criar apenas um teste cirúrgico que garanta:

```text
novo Quick Sale
→ sem checkout anterior
→ sem payment integration anterior
→ sem pagamento aplicado
```

Pode fazer apenas revisão estática + teste manual direcionado.

---

# CHECKPOINT

Informar:

1. origem exata do estado financeiro indevido;
2. arquivo responsável;
3. por que uma nova Venda Rápida estava recebendo esse estado;
4. correção aplicada;
5. como o estado do checkout anterior é encerrado;
6. confirmação de que histórico do banco NÃO foi apagado;
7. confirmação de que recuperação de vendas NÃO foi implementada;
8. confirmação de que PAY-1 não foi alterado;
9. confirmação de que PAY-2.1 não foi quebrado;
10. teste direcionado executado, se houver;
11. resultado.

Depois PARE.
