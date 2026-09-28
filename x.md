# MISSÃO PAY-0 — PAYMENT PROVIDER FOUNDATION

Vamos iniciar a arquitetura de pagamentos integrados do CORE PDV.

OBJETIVO PRINCIPAL:

Criar uma camada GENÉRICA para integração com múltiplos provedores/adquirentes/maquininhas, preparada para:

* Cielo;
* Stone;
* Getnet;
* Rede;
* PagBank;
* Mercado Pago;
* outros providers futuros.

IMPORTANTE:

NÃO estamos criando um novo motor financeiro.

O motor financeiro atual do CORE continua sendo a fonte da verdade:

Venda Rápida:
`QuickSaleCheckout`
→ `QuickSalePayment`
→ `Sale`
→ `sales.Payment`

Mesa:
`TableAttendance`
→ `TablePayment`
→ `Sale`
→ `sales.Payment`

Comandas ficam FORA DE ESCOPO nesta missão.

A nova camada servirá exclusivamente para representar:

* intenção de cobrança;
* execução externa;
* tentativa;
* autorização;
* rejeição;
* cancelamento;
* estado desconhecido;
* dados retornados pela adquirente;
* terminal utilizado;
* rastreabilidade;
* futura reconciliação.

A MAQUININHA NÃO CRIA VENDA.
A MAQUININHA NÃO BAIXA ESTOQUE.
A MAQUININHA NÃO SUBSTITUI QuickSalePayment/TablePayment.
A MAQUININHA NÃO FINALIZA Sale diretamente.

---

# 1. CRIAR NOVO DOMÍNIO

Criar um app Django isolado para essa responsabilidade.

Sugestão de nome:

`backend/apps/payment_integrations/`

Evitar chamar simplesmente de `payments`, porque já existe o domínio financeiro de pagamentos dentro de `sales`, POS e attendance.

Adicionar corretamente ao projeto Django.

Criar estrutura limpa de:

* models;
* services;
* selectors, caso necessário;
* admin;
* migrations;
* testes direcionados do domínio.

NÃO criar endpoints públicos ainda se não forem necessários para PAY-0.

---

# 2. PAYMENT PROVIDER

Criar entidade global:

`PaymentProvider`

Ela representa o tipo/provider suportado pela plataforma.

Exemplos futuros:

`CIELO`
`STONE`
`GETNET`
`REDE`
`PAGBANK`

Mas NÃO implemente lógica específica desses providers nesta missão.

Campos conceituais:

* id;
* code;
* name;
* status;
* integration_type;
* capabilities;
* created_at;
* updated_at.

`code` deve ser único e estável.

Possíveis tipos de integração devem ser genéricos, por exemplo:

* LOCAL_DEEP_LINK;
* NATIVE_SDK;
* SERVER_API;
* HYBRID.

`capabilities` pode preparar recursos como:

* credit_card;
* debit_card;
* voucher;
* pix;
* installments;
* refund;
* reconciliation;
* local_app;
* native_sdk.

Não hardcodar comportamento Cielo/Stone no model.

---

# 3. PAYMENT PROVIDER CONNECTION

Criar:

`PaymentProviderConnection`

Representa uma configuração/contrato de um tenant com determinado provider.

Exemplo conceitual:

Empresa: 25 Lounge
Provider: Cielo
Environment: PRODUCTION
Status: ACTIVE

Campos mínimos:

* company;
* branch opcional, permitindo conexão válida para empresa inteira ou específica de filial;
* provider;
* name;
* environment;
* status;
* configuration JSON somente para dados NÃO sensíveis;
* capabilities override, se fizer sentido;
* created_at;
* updated_at.

Validar obrigatoriamente:

se `branch` existir, ela precisa pertencer à `company`.

Ambientes:

* SANDBOX;
* PRODUCTION.

Estados pelo menos:

* ACTIVE;
* INACTIVE.

IMPORTANTE:

NÃO armazenar nesta missão:

* client_secret em texto puro;
* access_token;
* senha;
* chave privada;
* qualquer segredo sensível.

A arquitetura segura de credentials será feita na missão específica de conexão do provider.

Não inventar criptografia improvisada.

---

# 4. PAYMENT TERMINAL

Criar:

`PaymentTerminal`

Representa a maquininha/terminal externo que pode executar uma transação.

Isso precisa suportar múltiplas maquininhas por filial.

Exemplo:

Filial Duque de Caxias
→ CORE POS Caixa 01
→ Cielo Caixa 01

Outra:

Filial Duque de Caxias
→ CORE POS Bar
→ Stone Bar

Campos:

* connection;
* branch;
* pos_device opcional;
* name;
* external_id opcional;
* status;
* capabilities;
* metadata NÃO sensível;
* created_at;
* updated_at.

Validações:

1. branch deve pertencer à mesma empresa da connection;
2. se connection possuir branch específica, terminal obrigatoriamente pertence àquela branch;
3. se existir `pos_device`, ele deve pertencer à mesma branch;
4. não assumir relação 1:1 entre POS e terminal.

Um POS poderá futuramente possuir mais de um terminal/provider disponível.

Não criar dependência:

`device_type == STONE_POS`

para decidir provider.

Provider de pagamento e tipo do dispositivo são conceitos separados.

---

# 5. PAYMENT INTENT

Criar:

`PaymentIntent`

Essa será a entidade central da nova arquitetura.

Ela representa:

“o CORE pretende cobrar este valor por meio de um provider externo”.

Utilizar UUID como PK.

Campos conceituais:

* id UUID;
* company;
* branch;
* pos_device;
* operator;
* origin_type;
* origin_id;
* payment_method;
* amount;
* provider_connection;
* terminal opcional;
* status;
* idempotency_key;
* request_fingerprint;
* created_at;
* updated_at;
* approved_at opcional;
* applied_at opcional;
* cancelled_at opcional.

Tipos de origem preparados:

* QUICK_SALE;
* TABLE;
* COMMAND;
* OTHER, somente se realmente necessário.

ATENÇÃO:

COMMAND pode existir apenas como enum/preparação arquitetural.

NÃO integrar Comandas agora.

`origin_id` deve permitir representar IDs UUID ou inteiros sem criar GenericForeignKey frágil.

Pode utilizar string normalizada.

---

# 6. ESTADOS DO PAYMENT INTENT

Preparar pelo menos:

`CREATED`
`READY`
`PROCESSING`
`APPROVED`
`DECLINED`
`CANCELLED`
`ERROR`
`UNKNOWN`
`APPLIED`
`REVERSED`

Semântica importante:

`APPROVED`

significa:

provedor informou que o pagamento foi aprovado.

NÃO significa que o pagamento já foi aplicado no ledger financeiro do CORE.

`APPLIED`

significa:

o CORE conseguiu vincular/aplicar aquela autorização ao pagamento interno.

Essa separação é obrigatória.

---

# 7. UNKNOWN É ESTADO DE PRIMEIRA CLASSE

Nunca assumir:

“não recebi callback = pagamento falhou”.

Cenário:

CORE
→ solicita R$ 100
→ adquirente aprova
→ app fecha/perde callback

Nesse caso poderemos terminar com:

`UNKNOWN`

e posteriormente consultar/reconciliar.

Não converter automaticamente `UNKNOWN` para `DECLINED` ou `ERROR`.

---

# 8. IDEMPOTÊNCIA

PaymentIntent deve possuir idempotência própria.

Criar:

* `idempotency_key`;
* `request_fingerprint`.

Sugestão:

unicidade por empresa + idempotency_key.

Uma repetição com mesma chave e mesmo fingerprint:

→ retorna/reutiliza o mesmo intent.

Mesma chave com payload diferente:

→ conflito de idempotência.

Seguir o padrão seguro já utilizado pelo CORE em Venda Rápida e Sale.

Não criar uma implementação completamente diferente se pudermos reutilizar os princípios já existentes.

---

# 9. PAYMENT ATTEMPT

Criar:

`PaymentAttempt`

Uma intenção poderá ter uma ou várias tentativas.

Exemplo:

PaymentIntent R$ 200 crédito

Attempt 1:
Cielo
DECLINED

Attempt 2:
Cielo
CANCELLED

Attempt 3:
Stone
APPROVED

Campos conceituais:

* id UUID;
* intent;
* attempt_number;
* status;
* amount;

identificadores genéricos:

* provider_transaction_id;
* provider_order_id;
* provider_reference;
* terminal_external_id;

autorização:

* authorization_code;
* nsu;

cartão:

* card_brand;
* card_mask;

operação:

* installments;
* payment_product;
* payment_product_detail;

retorno provider:

* provider_status;
* provider_status_code;
* provider_message;

tempos:

* started_at;
* completed_at;

snapshots técnicos:

* request_metadata;
* response_metadata;

created_at;
updated_at.

Não criar:

* cielo_nsu;
* stone_nsu;
* cielo_transaction_id;
* stone_transaction_id.

Todos os campos precisam ser provider-neutral.

---

# 10. SEGURANÇA DOS METADADOS

`request_metadata` e `response_metadata` NÃO podem virar depósito de segredo.

Não persistir:

* access_token;
* client_secret;
* passwords;
* credentials completas;
* chave privada;
* Authorization header.

Adicionar comentário/documentação explícita sobre isso.

Se for simples e seguro, criar função central de sanitização/redaction para metadata técnico.

Não inventar sistema complexo de secrets nesta etapa.

---

# 11. TENTATIVAS E CONCORRÊNCIA

A criação de `PaymentAttempt` deve ser transacional.

`attempt_number` deve ser sequencial por intent:

1
2
3
...

Criar constraint:

`intent + attempt_number` único.

Evitar condição de corrida ao gerar o número da tentativa.

Usar lock no PaymentIntent quando necessário.

---

# 12. TRANSIÇÕES DE ESTADO

Não espalhar:

`intent.status = ...`

pelo sistema inteiro.

Criar serviço central para transições.

Algo conceitualmente como:

`transition_payment_intent(...)`

e, se necessário:

`transition_payment_attempt(...)`

Definir transições permitidas.

Não permitir coisas absurdas como:

`DECLINED -> APPLIED`

sem nova tentativa/aprovação válida.

Não criar uma state machine excessivamente complexa, mas centralizar as regras.

Toda alteração relevante deve ser auditável.

---

# 13. INTEGRIDADE

PaymentIntent deve validar:

* amount > 0;
* payment_method pertence à company;
* payment_method está ativo quando o intent é criado;
* branch pertence à company;
* POSDevice pertence à branch;
* provider_connection pertence à mesma company;
* provider_connection ativa;
* se connection tem branch específica, deve ser a mesma branch;
* terminal pertence à connection;
* terminal pertence à branch;
* terminal ativo.

PaymentAttempt:

* amount > 0;
* pertence ao intent;
* tentativa não pode apontar para terminal/provider incompatível.

---

# 14. PAYMENT METHOD CONTINUA SENDO FORMA FINANCEIRA

NÃO criar métodos como:

`cielo_credit_card`
`stone_credit_card`
`cielo_debit`
`stone_debit`

Continuamos usando:

`cash`
`pix`
`credit_card`
`debit_card`
`food_voucher`
`meal_voucher`

Provider é OUTRA dimensão.

Exemplo:

PaymentMethod:
`credit_card`

Provider:
`CIELO`

Terminal:
`Cielo Caixa 01`

Isso é obrigatório.

---

# 15. NÃO ALTERAR OS LEDGERS EXISTENTES

PAY-0 NÃO deve alterar comportamento de:

`QuickSaleCheckout`

`QuickSalePayment`

`QuickSalePaymentAllocation`

`TableAttendance`

`TablePayment`

`TablePaymentAllocation`

`sales.Sale`

`sales.Payment`

`CommandPayment`

`AttendancePayment`

Não adicionar ainda lógica de provider dentro desses services.

Não mudar:

`record_quick_checkout_payment()`

`reverse_quick_checkout_payment()`

`record_table_payment()`

`reverse_table_payment()`

`finalize_quick_checkout()`

`finalize_sale()`

Nesta missão estamos construindo a FUNDAÇÃO isolada.

---

# 16. NÃO MEXER EM COMANDAS

Não alterar:

* endpoints de Commands;
* models de Commands;
* CommandPayment;
* AttendanceCommand;
* telas de Comanda;
* fluxo de fechamento de Comanda.

O suporte futuro a COMMAND pode ficar apenas preparado no enum `origin_type`.

---

# 17. NÃO IMPLEMENTAR CIELO AINDA

Não adicionar ainda:

* Deep Link Cielo;
* Client ID;
* Access Token;
* callback Android;
* intents Android;
* SDK Cielo;
* classes `CieloPaymentAdapter`.

Também não implementar Stone.

PAY-0 é 100% provider-neutral.

---

# 18. NÃO ALTERAR FLUTTER NESTA MISSÃO

Ainda não criar:

`PaymentProviderAdapter` no Flutter.

Não modificar Venda Rápida.

Não modificar Mesa.

Primeiro consolidar o domínio backend.

Flutter entrará no PAY-1/PAY-2.

---

# 19. AUDITORIA

Usar o sistema de auditoria existente do CORE.

Registrar pelo menos:

* payment_intent.created;
* mudança relevante de status;
* payment_attempt.created;
* mudança relevante de status.

Nunca registrar secrets.

Metadata de auditoria pode conter IDs e estados, mas não credenciais.

---

# 20. SOFT DELETE / HISTÓRICO

Transações financeiras e intents não devem ser apagados fisicamente como fluxo normal.

`PaymentIntent` e `PaymentAttempt` são históricos operacionais.

Não implementar delete operacional desses registros.

ProviderConnection/Terminal podem utilizar status INACTIVE em vez de exclusão quando já possuírem histórico relacionado.

Usar `PROTECT` nas relações financeiras importantes.

---

# 21. ADMIN

Registrar os novos models no Django Admin para conseguirmos inspecionar durante desenvolvimento.

No admin:

* IDs;
* empresa;
* filial;
* provider;
* terminal;
* amount;
* status;
* timestamps;
* referências externas.

Não mostrar segredo porque PAY-0 nem deve armazená-los.

---

# 22. MIGRATIONS

Nesta missão MIGRATIONS SÃO ESPERADAS.

Criar migrations normais do novo domínio.

Não fazer migration destrutiva em models existentes.

Não alterar dados financeiros históricos.

---

# 23. TESTES DIRECIONADOS

Pode criar e executar SOMENTE testes backend direcionados para o novo domínio `payment_integrations`.

Cobrir principalmente:

* criação válida de PaymentIntent;
* amount <= 0 bloqueado;
* company/branch incompatível bloqueado;
* POS de outra filial bloqueado;
* provider connection incompatível bloqueado;
* terminal incompatível bloqueado;
* idempotência;
* conflito de fingerprint;
* tentativa sequencial;
* concorrência lógica do attempt_number, se viável;
* transições válidas;
* transições inválidas;
* UNKNOWN preservado;
* APPROVED não vira APPLIED automaticamente.

NÃO rode suíte global.

NÃO rode Flutter.

NÃO rode build do app.

---

# 24. CRITÉRIO DE SUCESSO DO PAY-0

Ao final precisamos conseguir representar, SEM Cielo/Stone específicas:

Empresa A
↓
Filial X
↓
PaymentProviderConnection
↓
PaymentTerminal
↓
PaymentIntent R$ 100 CREDIT_CARD
↓
Attempt #1 DECLINED
↓
Attempt #2 APPROVED

mantendo:

`PaymentIntent = APPROVED`

sem criar:

`QuickSalePayment`

sem criar:

`TablePayment`

sem criar:

`Sale`

porque a aplicação financeira será feita somente nas próximas missões.

---

# 25. NÃO ANTECIPAR PAY-1

Não conecte a nova arquitetura à Venda Rápida ainda.

Não tente “aproveitar e já deixar funcionando”.

Quero revisar a fundação antes.

---

# CHECKPOINT OBRIGATÓRIO

Ao terminar, informe:

1. arquitetura criada;
2. models criados;
3. campos principais;
4. constraints;
5. regras de estado;
6. mecanismo de idempotência;
7. mecanismo de geração de attempts;
8. como protegeu metadata sensível;
9. arquivos alterados;
10. migrations criadas;
11. testes direcionados criados/executados e resultado;
12. confirmação explícita de que NÃO alterou:

* QuickSalePayment;
* TablePayment;
* sales.Payment;
* finalize_quick_checkout;
* finalize_sale;
* Comandas;
* Flutter;

13. qualquer decisão arquitetural que precisou tomar e não estava especificada acima.

Depois PARE.

Não avance para Cielo.
Não avance para Stone.
WSLNão avance para PAY-1.
