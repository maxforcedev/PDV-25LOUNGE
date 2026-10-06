Trabalhe em cima do commit atual:

```text
d07b619 fix: close SaaS capability enforcement gaps
```

OBJETIVO:

Fechar os últimos gaps de capabilities e corrigir a infraestrutura dos testes antigos para que o GitHub CI volte a ficar verde.

ESTA MISSÃO É CIRÚRGICA.

## REGRA DE CRÉDITOS / TESTES — OBRIGATÓRIA

NÃO rode localmente:

- suíte completa do backend;
- os ~461 testes;
- E2E completo;
- bateria ampla de POS;
- bateria ampla de reports;
- builds repetidos sem necessidade.

O GitHub Actions será a única validação completa.

Localmente rode apenas testes DIRETAMENTE relacionados ao que você alterar.

Se um teste direcionado estiver demorando anormalmente, interrompa e investigue.

---

# 1. INTEGRAR O HELPER SaaS AOS TESTES OPERACIONAIS ANTIGOS

Já foi criado:

```python
backend/apps/saas/tests/helpers.py
```

com helpers como:

```python
create_complete_test_plan()
create_operational_test_tenant()
```

A ideia está correta, mas eles ainda não foram integrados de verdade às suítes antigas.

Hoje vários testes continuam fazendo apenas:

```python
create_company_with_matrix(...)
```

e esperam que o tenant opere.

Isso não é mais válido.

Resultado atual no CI:

```text
tenant_not_operational
UNMAPPED
```

NÃO relaxar o runtime SaaS.

Corrigir os testes.

---

# 2. POS TEST FOUNDATION

Principal problema atual:

```text
backend/apps/pos/tests/test_foundation.py
```

O `setUp()` cria empresa, filial e usuário, mas NÃO cria assinatura operacional.

Por isso dezenas de testes estão morrendo já no pareamento com:

```text
403 tenant_not_operational
```

Ajustar o setup dessa suíte para utilizar plano/assinatura operacional completa.

O plano usado pelos testes POS deve possuir as capabilities necessárias para o comportamento legado da suíte, incluindo pelo menos:

```text
core.enabled
pos.enabled
pos.devices.max
feature.counter
feature.cash_register
feature.tables
feature.commands
feature.consumption
feature.production
feature.products
feature.customers
```

e demais módulos realmente usados nessa suíte.

Não adicionar entitlement manualmente em dezenas de testes.

Centralizar no helper.

---

# 3. COMMANDS / TABLES TESTS

Os testes antigos de Mesas estão retornando:

```text
O plano não permite a funcionalidade Mesas.
```

Exemplos:

```text
CommandConsumptionLimitTests
TableDeletionTests
```

Esses testes não estão testando ausência de plano.

Portanto seus fixtures devem criar tenant operacional com:

```text
feature.tables=True
feature.commands=True
feature.cash_register=True
```

Lembrar da regra existente:

```text
commands depende de cash_register
```

Não modificar essa regra para fazer teste passar.

---

# 4. SUPPLIERS / PURCHASES / INVENTORY / PRODUCTION

O CI ainda mostra testes antigos com:

```text
UNMAPPED
```

em módulos como:

- Suppliers
- Purchases
- Inventory
- Production
- Companies

Revisar apenas os setups/factories que criam tenants operacionais nesses testes.

Quando o teste NÃO estiver verificando bloqueio SaaS, criar assinatura operacional e capabilities adequadas.

Exemplos:

Supplier tests:

```text
feature.suppliers=True
```

Purchases:

```text
feature.purchases=True
feature.suppliers=True
```

Inventory:

```text
feature.inventory=True
feature.products=True
```

Production:

```text
feature.production=True
feature.products=True
```

Não exagerar habilitando módulos arbitrariamente se o teste não precisa.

Mas preferir helper reutilizável a repetição.

---

# 5. NÃO ALTERAR TESTES DE NEGATIVA SaaS

Testes criados especificamente para validar:

```text
tenant sem assinatura
assinatura vencida
feature desligada
POS desligado
limite atingido
TRIAL_EXPIRED
```

devem CONTINUAR sem helper operacional quando isso fizer parte do cenário.

Não transformar testes negativos em tenants operacionais.

---

# 6. CORRIGIR TESTE DO DASHBOARD

O CI mostra:

```text
KeyError: 'commands'
```

em:

```text
test_dashboard_empty_command_and_table_counts_do_not_error
test_dashboard_counts_open_commands_and_table_attendances_separately
```

O fixture habilitou:

```text
feature.commands
feature.tables
```

mas esqueceu:

```text
feature.cash_register
```

Como `commands` depende de Caixa, o estado efetivo fica desabilitado.

Corrigir o plano de teste adicionando:

```text
feature.cash_register=True
```

Não remover a dependência de Commands -> Cash Register.

---

# 7. CORRIGIR TESTES DE LIFECYCLE / TRIAL

Existem falhas como:

```text
TypeError: unsupported operand type(s) for +: 'NoneType' and 'datetime.timedelta'
```

em:

```text
test_trial_expiry_is_effective_before_cron
```

Isso aconteceu porque a nova semântica de `map_existing_company()` agora inicia ACTIVE por padrão.

Quando o teste precisa de TRIAL, deve informar explicitamente:

```python
initial_subscription_mode=Subscription.Status.TRIALING
```

Revisar testes antigos que assumiam Trial automático devido a `trial_days`.

A nova regra correta é:

```text
manual mapping default = ACTIVE
TRIAL somente explícito
```

Não voltar ao Trial automático.

Também corrigir testes de:

```text
extend-trial
end-trial
```

para garantir que criam uma assinatura TRIALING quando esse for o cenário esperado.

---

# 8. CORRIGIR TESTE DE ASSINATURA EXPIRADA COM PERÍODO INVÁLIDO

O CI mostrou:

```text
ValidationError:
current_period_end:
O fim do periodo deve ser posterior ao inicio.
```

em teste de contexto SaaS.

O teste está alterando apenas o `current_period_end` para uma data anterior ao `current_period_start`.

Isso viola corretamente a constraint do modelo.

Corrigir o fixture:

```text
current_period_start = passado mais antigo
current_period_end = passado mais recente
```

mantendo:

```text
start < end < agora
```

Não remover a validação do modelo.

---

# 9. FECHAR ENDPOINTS AUXILIARES DE RELATÓRIOS

O mapeamento principal:

```python
REPORT_FEATURES_BY_ROUTE_NAME
```

melhorou.

Mas endpoints auxiliares ainda podem vazar dados de módulos desabilitados.

Revisar especificamente:

```text
/reports/options/
/reports/purchase-options/
/reports/commercial-options/
```

## purchase-options

Ele pode consultar dados ligados a:

```text
purchases
suppliers
financial
```

Como possui `scope`, aplicar capability de acordo com o scope.

Exemplo:

```text
scope=purchases
→ reports + purchases

scope=suppliers
→ reports + suppliers

scope=payables
→ reports + purchases + financial
```

## commercial-options

Aplicar por scope:

```text
scope=promotions
→ reports + promotions

scope=modifiers
→ reports + products

scope=customers
→ reports + customers
```

Se os dados retornados exigirem Products/Categories também, garantir que o endpoint não vaze catálogo de produto quando `feature.products=False`.

Não retornar informações de módulo não contratado apenas porque `feature.reports=True`.

---

# 10. `/reports/options/`

Esse endpoint é compartilhado.

Ele hoje monta várias listas conforme permissões.

Também deve respeitar capabilities.

Exemplos:

Se:

```text
feature.inventory=False
```

não retornar opções de inventário/estoque.

Se:

```text
feature.cash_register=False
```

não retornar caixas/sessões.

Se:

```text
feature.products=False
```

não retornar produtos/categorias para relatórios que dependam do módulo Produtos.

Se:

```text
feature.consumption=False
```

não retornar opções exclusivas de consumação.

O endpoint pode continuar retornando dados compatíveis com outros relatórios permitidos.

Não bloquear o endpoint inteiro se apenas parte das opções não for permitida.

Filtrar o payload conforme features efetivas.

---

# 11. DASHBOARD DEVE SER CAPABILITY-AWARE

Hoje Commands/Mesas já foram corrigidos.

Falta aplicar o mesmo princípio aos demais widgets/blocos.

Revisar `DashboardView`.

Todo bloco deve exigir:

```text
RBAC
+
capability correspondente
```

Exemplos obrigatórios:

### Consumação

Só incluir:

```text
response['consumptions']
```

se:

```text
feature.consumption=True
```

### Sangrias

Só incluir withdrawals se:

```text
feature.cash_register=True
```

### Current Cash

Só incluir:

```text
response['current_cash']
```

se:

```text
feature.cash_register=True
```

### Estoque

Só incluir:

```text
response['inventory']
```

se:

```text
feature.inventory=True
```

### Operacional result

Analisar quais módulos alimentam o card e garantir que ele não exponha informações de módulos fora do plano.

Não criar regra excessivamente restritiva sem necessidade.

### Produtos

Se houver ranking/cards dependentes de produtos/catálogo e `feature.products=False`, eles não devem aparecer.

Regra geral:

**Capability OFF significa que o Dashboard também não exibe KPI daquele módulo.**

---

# 12. RELATÓRIOS — PROTEGER URL DIRETA NO FRONTEND

A Central de Relatórios já filtra cards por `requiredFeatures`.

Mas páginas individuais como:

```text
/relatorios/compras
/relatorios/mesas-comandas
/relatorios/clientes
/relatorios/caixa
```

podem montar diretamente e só descobrir a restrição quando a API responder 403.

Adicionar proteção frontend equivalente.

Não precisa duplicar lógica em cada página de forma desorganizada.

Pode:

- colocar `AdminGuard` nas rotas;
- ou centralizar no componente do relatório se fizer sentido.

Mapeamento:

```text
Compras → reports + purchases
Fornecedores → reports + suppliers
Contas a pagar → reports + purchases + financial
Estoque → reports + inventory
Caixa → reports + cash_register
Sangrias → reports + cash_register
Consumação → reports + consumption
Mesas/Comandas → reports + tables + commands
Promoções → reports + promotions
Modificadores → reports + products
Clientes → reports + customers
Tickets → reports + production
```

O backend continua sendo autoridade.

O frontend é defesa de UX.

---

# 13. TESTES DIRECIONADOS NOVOS

Adicionar/ajustar somente os testes necessários para:

1. `purchase-options?scope=purchases` bloqueado sem purchases.
2. `purchase-options?scope=suppliers` bloqueado sem suppliers.
3. `purchase-options?scope=payables` exige purchases + financial.
4. `commercial-options?scope=customers` bloqueia sem customers.
5. `commercial-options?scope=promotions` bloqueia sem promotions.
6. `/reports/options/` não retorna dados de módulo desligado.
7. Dashboard não retorna inventory quando inventory OFF.
8. Dashboard não retorna current_cash quando cash_register OFF.
9. Dashboard não retorna consumptions quando consumption OFF.
10. Dashboard continua retornando os widgets quando feature ON.
11. Fixture POS operacional permite pareamento normalmente.
12. Teste Trial explícito continua TRIALING.
13. Mapping manual sem parâmetro continua ACTIVE.

---

# 14. NÃO RODAR A SUÍTE COMPLETA LOCALMENTE

Reforçando:

NÃO execute:

```bash
python manage.py test
```

sozinho.

NÃO rode:

```bash
python manage.py test apps
```

NÃO rode todos os testes POS.

NÃO rode todos os 461 testes.

Use somente classes/módulos diretamente tocados.

Exemplos aceitáveis:

```bash
python manage.py test apps.saas.tests.test_feature_resolution
```

ou classes específicas.

Para POS, rode apenas os testes de setup/pareamento afetados, não `test_foundation.py` inteiro se ele for muito grande.

O GitHub CI fará a suíte completa uma única vez depois do push.

---

# 15. VALIDAÇÃO RÁPIDA

Pode executar localmente:

```text
python manage.py check
python manage.py makemigrations --check
```

Frontend/Platform Admin somente se houve alteração relevante:

```text
npm run lint
npm run build
```

Não repetir build que não seja necessário.

---

# 16. NÃO MEXER

Não alterar:

- regra fail-closed;
- vencimento imediato;
- Plan -> Subscription -> Entitlements;
- `pos.enabled`;
- RBAC;
- multiempresa;
- reuse de Owner por e-mail;
- Trial manual ACTIVE por padrão;
- cadastro público;
- pagamentos;
- Cielo;
- Stone;
- PagBank;
- impressão;
- vendas;
- caixa;
- arquitetura Mesas/Comandas;
- migrations antigas.

Não criar migration sem necessidade.

---

# ENTREGA

Ao terminar:

1. listar arquivos alterados;
2. explicar quais fixtures antigas foram adaptadas;
3. informar quais gaps de reports/dashboard foram fechados;
4. listar testes DIRECIONADOS executados;
5. NÃO executar suíte completa localmente;
6. fazer commit e push;
7. informar SHA do commit.

Critério de aceite:

```text
Tenant operacional continua funcionando.
Tenant sem assinatura continua bloqueado.
Capability OFF não vaza por menu, URL, API, relatório, options ou Dashboard.
Testes antigos recebem assinatura válida quando não estão testando SaaS.
```

Depois do push, deixe o GitHub Actions executar a suíte completa.

Não faça deploy na VPS.