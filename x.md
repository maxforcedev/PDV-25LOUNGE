Confie no estado atual do projeto e **não reverta as correções já feitas nos commits `464ef3d` e `e9124e7`**.

A análise do GitHub mostrou que a missão crítica está praticamente concluída. Restam somente **duas pendências objetivas** para fecharmos essa etapa.

Não faça refactor amplo, não redesenhe telas e não altere arquitetura já validada.

# 1. CORRIGIR O ÚNICO TESTE QUE ESTÁ QUEBRANDO O CI

Estado atual do GitHub Actions no commit:

`e9124e7f01a264ee6880b710066a5ed96c70a43f`

Resultado:

- Platform Admin lint/build ✅
- Frontend lint/build ✅
- Backend system check ✅
- Migrations check ✅
- Backend tests 🔴
- 487 testes executados
- somente 1 failure

Teste quebrado:

`apps.pos.tests.test_foundation.POSFoundationIntegrationTests.test_bootstrap_reports_fixed_and_flexible_cash_state_without_fake_selection`

O teste atualmente espera que, no modo FLEXIBLE, a lista de caixas contenha apenas:

- `Bar`
- `Pista`

Porém agora toda nova filial recebe corretamente o caixa provisionado automaticamente:

`Caixa principal`

Portanto o bootstrap POS retorna corretamente:

- `Caixa principal`
- `Bar`
- `Pista`

O teste antigo ficou incompatível com a nova regra de provisionamento.

## Corrigir o teste, NÃO a produção

Atualizar o teste para considerar o `Caixa principal` como caixa real, válido e elegível no modo FLEXIBLE.

Não:

- filtrar `Caixa principal` do bootstrap;
- esconder o caixa padrão do POS;
- remover o provisionamento automático;
- alterar `ensure_default_cash_register`;
- enfraquecer a nova regra apenas para satisfazer o teste.

A regra correta permanece:

`nova empresa -> Matriz -> Caixa principal`

`nova filial -> Caixa principal`

O teste é que precisa acompanhar a arquitetura nova.

---

# 2. FECHAR RACE CONDITION RESTANTE EM MODIFICADORES

O bug principal de Modificadores já foi corrigido.

Hoje `load()` e `loadOptions()` usam corretamente o contexto:

`companyId:branchId`

e descartam respostas antigas.

Porém ainda existe uma condição de corrida nas mutations de opções.

Arquivo:

`frontend/src/app/(private)/modificadores/page.tsx`

Fluxos afetados:

- `saveOption`
- `deleteOption`
- `reorderOptions`

## Cenário do problema

Exemplo:

1. usuário está na Filial A;
2. salva uma opção;
3. request ainda está em andamento;
4. usuário troca para Filial B;
5. o `useEffect` limpa corretamente:
   - `viewingGroup`
   - `groupOptions`
   - modal;
6. a request antiga da Filial A termina;
7. o callback ainda pode executar `openOptions(viewingGroup)` usando o grupo antigo;
8. isso pode reabrir estado da Filial A dentro do contexto da Filial B.

`loadOptions()` já impede que a resposta antiga altere `groupOptions`, mas o próprio `openOptions()` ainda pode alterar:

- `viewingGroup`;
- `optionsModalOpen`;

antes da proteção interna do request.

## Corrigir

Nas operações assíncronas que fazem mutation, capturar o contexto antes da request:

`const token = context.current`

Depois de cada `await` relevante e antes de alterar novamente o estado da interface ou chamar `openOptions`, validar:

`if (context.current !== token) return`

Aplicar isso de forma consistente em:

- salvar opção;
- excluir opção;
- reordenar opção.

Se houver o mesmo padrão em criação/edição/exclusão/reordenação de grupos, revisar e corrigir somente onde necessário.

Não remover a proteção de contexto já existente.

Não simplificar removendo o controle de race condition.

O comportamento esperado é:

`response da Filial A chegando depois que usuário foi para Filial B`
→ resposta é ignorada
→ modal antigo não reabre
→ estado da Filial B permanece intacto.

---

# 3. ADICIONAR TESTE/COBERTURA PARA A NOVA REGRA DO CAIXA

Além de corrigir o teste antigo, garantir que exista cobertura clara para:

- nova empresa recebe exatamente um `Caixa principal`;
- nova filial recebe exatamente um `Caixa principal`;
- chamada repetida de `ensure_default_cash_register` não cria duplicata;
- POS FLEXIBLE lista o `Caixa principal` junto aos outros caixas ativos;
- POS FIXED continua respeitando o caixa definido no `BranchPOSSettings`.

Não mudar a regra de produção.

---

# 4. NÃO ALTERAR O CMV

A implementação atual de CMV foi revisada e está aprovada.

Não mexer em:

- `_reconcile_modifier_component_costs`;
- snapshot de custo;
- `product_input`;
- `component_substitution`;
- `SaleItem.unit_cost`;
- `OrderItem.unit_cost`;
- `AttendanceOrderItem.unit_cost`;
- custo médio por filial;
- movimentações de estoque;
- cancelamento;
- transferências proporcionais;
- snapshot histórico.

O estado atual está correto:

- custo usa estoque da filial;
- `average_unit_cost` com fallback para `product.cost`;
- adicional entra no CMV;
- substituição troca contribuição de custo;
- quantidade > 1 não multiplica duas vezes o CMV unitário;
- custo histórico permanece congelado.

Não refatore essa parte nesta missão.

---

# 5. NÃO ALTERAR AS OUTRAS CORREÇÕES CRÍTICAS

Preservar integralmente:

### Reset de senha

- `/esqueci-senha` público;
- `/redefinir-senha` público;
- resposta neutra para e-mail existente/inexistente;
- rate limit;
- token Django;
- UID inválido retorna erro controlado;
- sem enumeração de contas.

### POS web

Manter:

`/pdv -> /dashboard`

O Backoffice não deve voltar a vender.

### CORE POS

Manter:

`POS_API_BASE_URL`

obrigatório.

Debug pode usar HTTP/IP local.

Release continua exigindo HTTPS.

### SMTP

Manter a arquitetura atual:

- credenciais via env/secret;
- Docker Secret para senha;
- `docker-stack.smtp.yml`;
- validação TLS/SSL;
- console backend em desenvolvimento.

Não colocar segredo no repositório.

---

# 6. PRINCÍPIOS

Não enfraquecer produção para fazer teste passar.

O teste deve refletir a regra nova.

Não remover proteção de contexto de Modificadores.

Não alterar entitlement/RBAC.

Não fazer mudanças fora deste escopo.

Não criar migrations desnecessárias.

Não alterar comportamento financeiro já validado.

---

# 7. EXECUÇÃO

Faça somente essas correções.

Atualize os testes necessários.

**Não execute testes, builds, Flutter ou suíte localmente. O GitHub Actions fará a validação após o push.**

Ao concluir:

1. faça commit;
2. faça push;
3. informe o SHA;
4. liste os arquivos alterados;
5. explique a correção do teste do POS;
6. explique como fechou a race de Modificadores;
7. confirme explicitamente que não alterou a lógica de CMV;
8. não considere concluído deixando workaround ou TODO.

O objetivo final é deixar o GitHub Actions totalmente verde sem modificar as regras corretas já implementadas.