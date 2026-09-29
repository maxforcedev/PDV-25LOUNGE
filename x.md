# MISSÃO PAY-1.3 — FECHAMENTO FINAL PRÉ-CIELO

O PAY-1.2 corrigiu corretamente os bloqueadores anteriores.

HEAD atual analisado:

`01d0f3e24cb75d8f4fb82d55b05a235de3d7df6b`

Restaram SOMENTE 2 ajustes antes de liberar o PAY-2 / Cielo:

1. transições históricas/cancelamento não podem revalidar vínculo atual Terminal ↔ POS;
2. eliminar inversão de locks entre POSDevice e CashSession.

Corrigir SOMENTE estes pontos.

NÃO implementar Cielo.
NÃO implementar Stone.
NÃO mexer em Flutter.
NÃO integrar Mesa.
NÃO mexer em Comandas.

---

# 1. TERMINAL ↔ POS É VALIDAÇÃO OPERACIONAL, NÃO HISTÓRICA

Hoje o resultado de Attempt após PROCESSING já não revalida corretamente o vínculo atual:

`terminal.pos_device == intent.pos_device`

Isso está certo.

Porém `transition_payment_intent()` ainda chama `_save_intent_status()` com:

`validate_terminal_pos_binding=True`

por padrão.

Isso pode prender um Intent antigo.

Cenário:

```text
Intent READY
Terminal T → POS A

Backoffice reatribui:
Terminal T → POS B

operador tenta:
READY → CANCELLED
```

O cancelamento NÃO pode falhar porque o terminal foi reatribuído administrativamente.

Outro cenário:

```text
Attempt PROCESSING
Terminal muda POS A → POS B
Attempt → DECLINED

operador:
DECLINED → CANCELLED
```

Também deve funcionar.

REGRA DEFINITIVA:

A compatibilidade atual:

`terminal.pos_device_id IS NULL OR terminal.pos_device_id == intent.pos_device_id`

é obrigatória SOMENTE ao:

* criar novo PaymentIntent;
* criar novo PaymentAttempt;
* iniciar `CREATED → PROCESSING`.

Depois disso, o vínculo atual do terminal NÃO pode impedir transições históricas/administrativas.

Não revalidar Terminal ↔ POS em:

* CANCELLED;
* DECLINED;
* ERROR;
* UNKNOWN;
* APPROVED;
* reconciliação;
* demais persistências históricas de status.

Continuar SEMPRE validando integridade estrutural:

* terminal.connection == attempt/provider connection;
* terminal.branch == intent.branch;
* connection.company == intent.company;
* demais invariantes estruturais existentes.

Não relaxar essas validações.

---

# 2. AJUSTAR `_save_intent_status`

Revisar `_save_intent_status()`.

Hoje:

```python
def _save_intent_status(
    intent,
    status,
    *,
    validate_terminal_pos_binding=True,
)
```

Esse default é perigoso para transições históricas.

Escolher solução clara.

Preferência:

o vínculo Terminal ↔ POS deve ser explicitamente exigido SOMENTE nos pontos de início de operação, e não como default de qualquer mudança de status.

Pode mudar o default para:

```text
False
```

desde que os pontos de criação/start continuem validando explicitamente.

Ou preservar assinatura atual e passar `False` em TODAS as transições históricas.

O importante é deixar impossível que:

```text
terminal foi reatribuído
↓
cancelamento/reconciliação histórica trava
```

---

# 3. TESTES DO TERMINAL REATRIBUÍDO

Adicionar testes específicos.

## READY → CANCELLED

```text
Intent READY
Terminal inicialmente POS A
Terminal reatribuído POS B
cancel Intent
→ CANCELLED
```

deve funcionar.

## DECLINED → CANCELLED

```text
Attempt PROCESSING
Terminal A → B
Attempt DECLINED
Intent DECLINED
cancel Intent
→ CANCELLED
```

deve funcionar.

## ERROR → CANCELLED

Mesmo princípio.

## Nova operação

Depois da reatribuição:

```text
novo Intent/Attempt do POS A
usando Terminal agora ligado ao POS B
```

→ continua bloqueado.

Ou seja:

```text
operação histórica → conclui
operação nova incompatível → bloqueia
```

---

# 4. PADRONIZAR ORDEM DE LOCKS POSDEVICE → CASHSESSION

A auditoria encontrou inversão de locks.

Hoje o pagamento integrado segue corretamente:

```text
POSDevice
→ CashSession
→ QuickSaleCheckout
→ PaymentIntent / Attempt
→ Ledger
```

Porém outros fluxos POS ainda podem fazer:

```text
CashSession
→ POSDevice
```

Isso permite deadlock.

Exemplo:

```text
Transação A
start payment
lock POSDevice
espera CashSession
```

simultaneamente:

```text
Transação B
troca/fecha caixa
lock CashSession
espera POSDevice
```

Resultado:

`DEADLOCK`

Padronizar mutações que mexem simultaneamente em:

* `POSDevice.active_cash_session`;
* `CashSession`;

para sempre seguir:

```text
POSDevice
→ CashSession
```

quando o contexto for uma operação do POS.

---

# 5. POS CASH SESSION SELECT

Revisar:

`POSCashSessionSelectView`

Hoje ele busca/trava CashSession antes do POSDevice.

Corrigir ordem.

Fluxo esperado:

```text
transaction.atomic
↓
lock POSDevice
↓
resolver/validar branch/configuração
↓
lock CashSession alvo
↓
validar OPEN/ACTIVE
↓
device.active_cash_session = session
```

Não utilizar `QuerySet.update()` de forma que perca o lock já obtido ou bypass de validações relevantes.

Preservar:

* FLEXIBLE somente;
* permissões;
* mesma branch;
* register ACTIVE;
* session OPEN;
* auditoria.

---

# 6. POS CASH SESSION OPEN / BIND

Revisar o endpoint que:

* abre CashSession;
* depois vincula ao `POSDevice.active_cash_session`.

Hoje ele pode fazer:

```text
open_session → lock CashSession/register
↓
lock POSDevice
```

Padronizar para evitar inversão.

Antes de iniciar o fluxo de abertura/vínculo pelo POS:

```text
lock POSDevice
```

Depois:

```text
open/lock CashSession e CashRegister
```

Garantir que não sejam criadas duas sessões/vínculos concorrentes por corrida.

Não alterar regras de `open_session()` fora do necessário.

---

# 7. POS CASH SESSION CLOSE

Revisar:

`POSCashSessionCloseView`

Hoje:

```text
close_session()
↓
depois limpa POSDevice.active_cash_session
```

e o `close_session()` começa travando CashSession.

Para chamada via POS precisamos manter:

```text
POSDevice
→ CashSession
```

Solução deve evitar alterar indevidamente os fluxos Backoffice que chamam `close_session()` sem POSDevice.

Pode criar wrapper POS específico ou adquirir lock do device no View antes do service.

Exemplo conceitual:

```text
transaction.atomic
↓
lock POSDevice
↓
close_session(...)
↓
limpar active_cash_session
```

Como o lock do device já está adquirido antes de `close_session()` travar sessão, a ordem fica consistente.

Preservar toda a lógica atual de fechamento.

---

# 8. LIMPEZA DE ACTIVE CASH SESSION

Ao fechar uma sessão pelo POS:

limpar `active_cash_session` somente dos dispositivos que realmente apontam para aquela sessão, preservando comportamento atual.

Se houver mais de um device apontando para a mesma sessão e isso for permitido pela arquitetura atual, não introduzir comportamento novo além do existente.

Mas garantir que qualquer lock de device usado seja feito ANTES do lock de CashSession quando ambos participarem da mesma transação.

---

# 9. NÃO CRIAR NOVA INVERSÃO

Auditar todos os pontos alterados nesta missão procurando sequências:

```text
CashSession select_for_update
→ POSDevice select_for_update
```

nos fluxos POS.

Dentro de operações POS envolvendo ambos, não deixar essa ordem.

Padrão oficial:

```text
POSDevice
→ CashSession
→ QuickSaleCheckout
→ PaymentIntent
→ PaymentAttempt
→ QuickSalePayment
```

Nem todo fluxo precisa travar todos.

Mas, se travar mais de um, respeitar essa ordem.

---

# 10. NÃO MUDAR O LOCK ORDER DE DOMÍNIOS QUE NÃO ENVOLVEM POSDEVICE

Não sair refatorando todo o sistema de Cash.

Backoffice e services genéricos podem continuar com suas regras existentes desde que não façam depois um lock de POSDevice na mesma transação.

A missão é corrigir especificamente a interseção:

`POSDevice ↔ CashSession`

---

# 11. TESTES DE LOCK ORDER FUNCIONAL

Não precisamos criar teste artificial de deadlock com threads se isso tornar a suíte frágil.

Mas adicionar testes funcionais que garantam:

## Select

```text
POSDevice
Caixa A ativo
selecionar Caixa B
→ vínculo atualizado corretamente
```

## Start provider vs cash context

Preservar:

```text
checkout Caixa A
POS troca para B
start Attempt
→ cash_context_changed
```

## Close

```text
POS vinculado Caixa A
close Caixa A
→ session CLOSED
→ device.active_cash_session = NULL
```

## Provider PROCESSING

```text
Attempt PROCESSING no Caixa A
tentativa de fechar caixa
→ continua bloqueada
```

Não quebrar os testes PAY-1.2 existentes.

---

# 12. TESTES DE REGRESSÃO OBRIGATÓRIOS

Preservar todos estes comportamentos:

* Terminal reatribuído pós-PROCESSING → APPROVED funciona;
* UNKNOWN → APPROVED funciona;
* Provider/Connection/Terminal INACTIVE pós-PROCESSING não bloqueiam resultado;
* PaymentMethod INACTIVE pós-PROCESSING não bloqueia resultado;
* cancel_session bloqueia checkout pago;
* provider_transaction conflict faz rollback;
* provider payment service-only;
* sales.Payment Quick Sale source service-only;
* partial payment;
* provider fallback;
* reversal provider bloqueado;
* application_context protegido;
* callback replay.

---

# 13. NÃO ALTERAR PAYMENT FLOW

Não mexer na semântica de:

* PaymentIntent;
* PaymentAttempt;
* QuickSalePayment;
* APPROVED;
* APPLIED;
* provider_transaction_id;
* application_context;
* fallback;
* reversal.

Exceto o necessário para retirar a revalidação histórica Terminal ↔ POS.

---

# 14. NÃO ALTERAR MESA

NÃO mexer em:

* TableAttendance;
* TablePayment;
* TablePaymentAllocation;
* services/endpoints/telas de Mesa.

---

# 15. NÃO ALTERAR COMANDAS

NÃO mexer em:

* Command;
* AttendanceCommand;
* CommandPayment;
* AttendancePayment;
* services/endpoints/telas de Comanda.

---

# 16. NÃO IMPLEMENTAR PROVIDER REAL

Ainda NÃO implementar:

* Cielo;
* Stone;
* Deep Link;
* SDK;
* Client ID;
* Access Token;
* callback Android;
* Flutter;
* platform channel.

---

# 17. MIGRATIONS

Esses ajustes não parecem exigir schema change.

NÃO criar migration sem necessidade real.

NÃO editar migrations existentes.

---

# 18. TESTES PERMITIDOS

Pode executar SOMENTE testes direcionados relacionados a:

* `payment_integrations`;
* Quick Sale;
* POS cash session;
* cash/session;
* sales finalization afetada.

NÃO executar:

* suíte completa;
* Flutter;
* build;
* analyze;
* lint global.

---

# CHECKPOINT FINAL

Ao terminar, informe:

1. como Terminal ↔ POS passou a ser apenas validação de início de operação;
2. como READY → CANCELLED funciona após reatribuição;
3. como DECLINED/ERROR → CANCELLED funcionam após reatribuição;
4. como novas operações continuam bloqueando Terminal incompatível;
5. qual passou a ser a ordem oficial de locks;
6. quais endpoints POS foram ajustados;
7. como `POSCashSessionSelectView` ficou;
8. como abertura/vínculo de caixa ficou;
9. como fechamento via POS ficou;
10. testes adicionados;
11. resultados dos testes direcionados;
12. arquivos alterados;
13. migrations criadas, se houver;
14. confirmação de que NÃO alterou Mesa;
15. confirmação de que NÃO alterou Comandas;
16. confirmação de que NÃO alterou Flutter;
17. confirmação de que NÃO implementou Cielo nem Stone.

Depois PARE.

NÃO avance para PAY-2.
