Analise o estado ATUAL do `main` antes de alterar qualquer coisa.

O HEAD analisado está no commit:

`f1efc6cf693ab880ca1fb6353e0594a3f966f03e`

A limpeza principal do Mesas legado foi feita corretamente, porém ainda existem inconsistências importantes nas bordas do sistema.

OBJETIVO DESTA MISSÃO:

Finalizar a separação entre MESAS e COMANDAS, remover referências operacionais restantes do modelo antigo e deixar Backend, Backoffice, POS, RBAC e testes coerentes com a arquitetura atual.

NÃO faça deploy.
NÃO mexa na VPS.
NÃO redesenhe o módulo de Comandas.
NÃO apague migrations históricas.
NÃO remova dados históricos sem migration segura.
NÃO reintroduza o Mesas antigo.

---

# ARQUITETURA ATUAL CORRETA

A operação de Mesa deve ser:

`commands.Table`
→ `TableAttendance`
→ `TableOrder`
→ `TableOrderItem`
→ `TablePayment`
→ fechamento/venda

`commands.Table` continua sendo a entidade física da mesa.

Ela NÃO é legado para remoção.

A ocupação/operação financeira da mesa pertence exclusivamente a:

`TableAttendance`

Comandas devem funcionar de forma independente de Mesa.

---

# 1. BACKOFFICE DE COMANDAS ESTÁ INCOMPATÍVEL COM O BACKEND

Este é o principal problema atual.

O backend já deixou de aceitar Mesa nas operações de Comanda.

Porém:

`frontend/src/app/(private)/comandas/page.tsx`

ainda possui lógica semelhante a:

```ts
if (selectedTable) payload.table = Number(selectedTable);
```

e envia isso para:

`commands/open/`

O backend atual rejeita explicitamente `table`.

Portanto:

REMOVA do fluxo de abertura de Comanda:

- seleção de Mesa;
- `selectedTable`;
- envio de `table`;
- qualquer texto que sugira que uma Comanda precisa estar vinculada a uma Mesa.

A criação de Comanda deve ser independente.

---

# 2. REMOVER TRANSFERÊNCIA DE COMANDA PARA MESA DO BACKOFFICE

Em:

`frontend/src/app/(private)/comandas/[id]/page.tsx`

ainda existe operação:

`transfer`

que chama:

`commands/<id>/transfer/`

Essa rota foi removida do backend.

Também ainda existe modal:

“Transferir mesa”

e seleção de mesa de destino.

Isso precisa ser removido.

NÃO recrie a rota backend.

NÃO reintroduza:

`transfer_command_table`

NÃO faça fallback.

A operação Comanda → Mesa deixou de existir.

Preserve somente operações atuais válidas de Comandas, como:

- transferência de itens entre comandas;
- merge;
- split;
- pagamentos;
- fechamento;
- cliente;
- demais funcionalidades que ainda pertencem ao domínio de Comandas.

---

# 3. SPLIT DE COMANDA NÃO DEVE MAIS RECEBER MESA

Hoje o Backoffice ainda envia no split:

```json
{
  "items": [...],
  "table": ...,
  "identifier": ...
}
```

O backend atual já removeu `table` dessa operação.

Corrija o frontend.

Ao dividir uma Comanda:

- cria-se nova Comanda independente;
- não escolher Mesa;
- não enviar `table`;
- não exibir “Mesa da nova comanda”.

Preserve identificador e itens.

---

# 4. TIPOS FRONTEND DE COMANDA

Hoje:

`frontend/src/types/index.ts`

ainda expõe em `Command`:

```ts
table: number | null
table_name?: string
```

Analise todos os consumidores.

Como novas Comandas não podem mais possuir Mesa, retire esses campos do contrato operacional atual caso não sejam necessários para histórico.

IMPORTANTE:

se algum endpoint histórico ainda precisar entregar esses valores por compatibilidade de leitura, NÃO quebre o backend sem necessidade.

A preferência é:

- UI operacional atual não depende deles;
- histórico pode continuar existindo internamente enquanto houver dados antigos.

Não manter campo morto apenas porque “sempre esteve ali”.

---

# 5. POS FLUTTER — COMANDA AINDA CARREGA MESA

Em:

`pos/lib/attendance/attendance_models.dart`

`AttendanceCommand` ainda possui:

- `tableId`
- `tableName`
- `isPrimary`

A API atual de Comandas novas não utiliza mais isso operacionalmente.

Em:

`pos/lib/attendance/attendance_pages.dart`

a lista ainda exibe:

```dart
command.tableName.isEmpty
    ? 'Sem mesa'
    : command.tableName
```

Isso não faz mais sentido para Comandas novas.

Corrija o modelo e UI operacional.

Uma Comanda não precisa exibir “Sem mesa”.

Pode exibir, por exemplo:

- identificador;
- número;
- cliente quando houver;
- quantidade de pessoas, se aplicável;
- status.

NÃO transforme isso em redesign visual amplo.

Apenas retire a semântica Mesa da Comanda.

---

# 6. `AttendanceCommand` — CAMPOS HISTÓRICOS

No backend:

`backend/apps/attendance/models.py`

`AttendanceCommand` ainda possui:

- `table`
- `is_primary`
- `table_name_snapshot`

O próprio comentário atual já informa:

“table fields are retained for historical records only.”

Isso é aceitável TEMPORARIAMENTE.

NÃO faça migration destrutiva nesta missão apenas para apagar esses campos.

Porém:

nenhum fluxo operacional novo deve:

- preencher `table`;
- preencher `is_primary`;
- usar `table_name_snapshot`;
- consultar Mesa através desses campos;
- tomar decisão operacional por esses campos.

Analise o código inteiro e confirme isso.

O serializer operacional atual também ainda retorna:

- `table`
- `table_name`
- `is_primary`

Se não houver consumidor legítimo atual, remova esses campos da resposta operacional do POS.

Preserve os dados no banco.

---

# 7. `commands.Command` — CAMPOS HISTÓRICOS

O model:

`backend/apps/commands/models.py`

também ainda possui:

- `table`
- `table_name_snapshot`

A camada de serviço nova já parou de preencher isso.

Trate-os como histórico legado temporário.

NÃO apague fisicamente nesta missão.

Mas retire a dependência operacional atual de:

- serializers;
- views;
- frontend;
- filtros;
- labels;
- operações novas.

Caso algum relatório histórico precise desses valores, pode continuar lendo snapshots históricos.

O que não pode acontecer é Comanda NOVA voltar a depender de Mesa.

---

# 8. RBAC ÓRFÃO — `commands.transfer`

Hoje ainda existe:

`commands.transfer`

com descrição semelhante a:

“Transferir uma comanda aberta entre mesas.”

Verifique:

`backend/apps/companies/rbac.py`

`backend/apps/commands/permissions.py`

`frontend/src/lib/permissions.ts`

e todos os outros consumidores.

Essa permissão ficou órfã porque a operação Comanda → Mesa foi removida.

REMOVA o uso operacional dessa permissão.

Isso inclui:

- catálogo funcional atual;
- mapeamentos de actions;
- frontend;
- POS;
- perfis/defaults futuros.

CUIDADO:

se `FunctionalPermission` já estiver persistida em produção, não precisa necessariamente deletar fisicamente o registro nesta missão.

Pode:

- deixar de criar/conceder;
- arquivar/desativar via migration segura se o modelo permitir;
- preservar auditoria/histórico.

Não faça delete destrutivo sem analisar impacto.

MANTER:

`commands.transfer_items`

porque transferência de ITENS entre comandas continua válida.

---

# 9. `CommandOperationType.TRANSFER`

Em:

`backend/apps/commands/models.py`

ainda existe:

`TRANSFER = 'transfer'`

Isso foi usado historicamente para transferência entre mesas.

Como pode haver `CommandOperation` persistida com esse tipo, NÃO remova cegamente o choice se isso quebrar leitura histórica.

Mas:

- não pode haver nova operação criada com esse tipo;
- não deve existir endpoint atual gerando `TRANSFER`;
- não deve existir botão atual usando isso.

Se permanecer, documente claramente como HISTÓRICO.

---

# 10. RELATÓRIO “MESAS E COMANDAS”

Hoje o relatório ainda mistura o modelo antigo.

Em:

`backend/apps/reports/views.py`

`CommandsReportView`

ainda usa:

- `command.table_id`;
- `_command_table_name`;
- filtro por Mesa dentro de Command;
- `opened_tables` derivado historicamente de command em alguns pontos;
- operações `CommandOperationType.TRANSFER`;
- labels “Transferência entre mesas”.

No frontend:

`frontend/src/components/commands-report.tsx`

ainda existem:

- filtro “Mesa” baseado em Comanda;
- coluna “Mesa” em Comandas;
- coluna Mesa nos itens;
- Mesa nos pagamentos;
- Mesa nos cancelamentos;
- origem/destino com Mesa;
- seção de “Transferências” com semântica antiga.

Precisamos separar o que é:

A) HISTÓRICO LEGADO

de:

B) OPERAÇÃO ATUAL.

Não apague informação histórica legítima.

Mas NÃO represente isso como comportamento atual.

Minha direção:

- Comandas atuais devem ser relatório de Comandas;
- Mesas atuais devem vir de `TableAttendance`;
- snapshots históricos de Comanda → Mesa podem aparecer somente quando realmente existem em registros antigos;
- filtros novos de Mesa não devem depender de `Command.table_id`.

Se for necessário um refactor maior para fazer um relatório completo unificado novo de Mesas + Comandas, NÃO faça nesta missão.

Neste momento:

1. retire dependências operacionais incorretas;
2. mantenha histórico legível;
3. não invente uma nova tela complexa.

No mínimo, não permita que o relatório atual sugira que Comandas novas continuam vinculadas a Mesas.

---

# 11. DASHBOARD

Já foi corrigido um ponto corretamente:

Mesas abertas agora são contadas através de:

`TableAttendance`

e não de `Command.table`.

Preserve isso.

Audite outros KPIs e cards para confirmar que nenhuma métrica atual de Mesa ainda depende de:

- `Command.table`;
- `AttendanceCommand.table`;
- `is_primary`.

Mesa operacional = `TableAttendance`.

---

# 12. AGRUPAMENTO DE MESAS

Em:

`apps.attendance.services`

ainda existem:

- `group_tables`
- `separate_table_from_group`
- `AttendanceTableGroup`
- `AttendanceTableGroupMembership`

Isso NÃO é automaticamente legado.

O agrupamento de mesas continua sendo funcionalidade válida do domínio novo, desde que opere em:

`TableAttendance`

e/ou mesas físicas atuais.

Analise o comportamento.

Garanta que agrupamento NÃO dependa de:

- AttendanceCommand;
- comanda primária;
- `is_primary`.

Se estiver independente, MANTER.

---

# 13. RECUPERAR COBERTURA DE TESTES DO MESAS NOVO

A limpeza removeu muitos testes do antigo:

`backend/apps/pos/tests/test_pos5_attendance.py`

Isso foi correto para testes que validavam o motor Mesa → Comanda antigo.

Porém NÃO queremos perder cobertura de funcionalidades que continuam existindo.

Hoje:

`test_pos5_attendance.py`

ficou basicamente focado em Comandas independentes.

Já existe:

`test_table_attendance_regression.py`

com cobertura de fechamento/pagamentos.

Analise a cobertura do novo `TableAttendance` e crie/ajuste testes para funcionalidades atuais que ficaram sem cobertura.

No mínimo verificar:

- abrir mesa via `open_table_attendance`;
- não permitir duas ocupações abertas para a mesma mesa;
- salvar pedido;
- confirmação/estoque;
- solicitar conta;
- liberar solicitação de conta;
- pagamento parcial;
- reversão;
- transferência de itens entre mesas;
- agrupamento de mesas;
- separação de mesa de grupo;
- fechamento de mesa;
- fechamento vazio sem criar venda;
- fechamento pago criando venda corretamente;
- idempotência;
- histórico/auditoria;
- impedir exclusão da mesa física quando existe TableAttendance aberta.

NÃO copie testes antigos trocando apenas o nome das classes.

Teste o contrato novo.

---

# 14. `OPEN_TABLE` E OUTROS OPERATION TYPES HISTÓRICOS

Em:

`AttendanceOperationType`

ainda existem:

- `OPEN_TABLE`
- `TRANSFER_COMMAND`

e possivelmente outros tipos usados somente pelo motor antigo.

Faça levantamento completo.

Se houver registros históricos persistidos que dependem deles:

MANTER como valor histórico.

Mas coloque comentário claro de:

“historical only / no new writes”.

Garanta por busca de código que nenhuma operação atual escreve esses tipos.

---

# 15. MIGRATIONS ANTIGAS

NÃO delete migrations como:

`attendance/0001...`
`0004_pos55_table_groups...`
etc.

Migrations representam histórico do schema.

O mesmo vale para migrations de `commands`.

Não “limpe” migrations aplicadas.

---

# 16. MIGRATION `0011_preserve_existing_pos_entitlements.py`

Existe atualmente:

`backend/apps/saas/migrations/0011_preserve_existing_pos_entitlements.py`

Ela adiciona aos PlanVersions existentes:

`pos.enabled = true`

e:

`pos.devices.max = unlimited`

quando ainda não existem.

ANALISE COM MUITO CUIDADO.

Isso pode ter impacto comercial importante.

O objetivo original era impedir que planos existentes passassem a ser inválidos após POS virar capability obrigatória.

Porém não queremos conceder acidentalmente licença ilimitada de CORE POS para todo plano histórico se isso não for necessário.

Antes de mudar:

- analise como os planos existentes eram tratados;
- analise tenants atuais;
- analise enforcement;
- analise defaults de planos novos.

Se a migration for necessária apenas para preservar operação de clientes existentes durante o cutover, documente.

Se existir solução melhor que preserve validade sem transformar todo plano histórico em POS ilimitado, implemente de forma segura.

NÃO quebre tenants já existentes.

NÃO faça migration destrutiva.

No relatório final explique exatamente a decisão.

---

# 17. NÃO MEXER NA ARQUITETURA DE COMANDAS AGORA

Temos atualmente:

`apps.commands.Command`

e:

`apps.attendance.AttendanceCommand`

Isso ainda é uma duplicidade arquitetural a resolver.

NÃO tente unificar esses dois motores nesta missão.

Isso será uma missão separada de COMANDAS.

Agora só queremos:

- Comanda independente de Mesa;
- Mesas usando TableAttendance;
- ausência de endpoints/UI mortos;
- ausência de permissões órfãs;
- testes coerentes.

---

# 18. BUSCAS OBRIGATÓRIAS AO FINAL

Pesquise no projeto inteiro por:

`open_table`

`OPEN_TABLE`

`TRANSFER_COMMAND`

`transfer_command`

`transfer_command_table`

`commands.transfer`

`is_primary`

`table_name_snapshot`

`command.table`

`AttendanceCommand.table`

`tableId`

`tableName`

`"Sem mesa"`

`"Transferir mesa"`

`"Mesa da nova comanda"`

`Legacy`

`legacy`

Para CADA ocorrência restante, informe:

- arquivo;
- linha/função;
- motivo pelo qual permanece;
- se é histórico ou operacional.

Nenhuma ocorrência operacional Mesa → Comanda deve permanecer.

---

# 19. VALIDAÇÃO FRONTEND

Depois das alterações:

Frontend:

```bash
npm ci
npm run lint
npm audit --omit=dev --audit-level=high
npm run build
```

Platform Admin, caso tocado:

```bash
npm ci
npm run lint
npm audit --omit=dev --audit-level=high
npm run build
```

Não ignore erros de TypeScript que mostrem contrato antigo.

---

# 20. VALIDAÇÃO BACKEND

Execute:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py check --deploy --fail-level WARNING
```

Preserve:

- Django 6.1.1;
- pypdf 6.19.0;
- regras atuais de segurança;
- entitlements atuais;
- idempotência;
- invariantes financeiras.

---

# 21. VALIDAÇÃO POS

Execute análise/testes disponíveis do Flutter.

Confirme especialmente que:

- Mesas não usam AttendanceCommand;
- Comandas não mostram mais semântica de Mesa;
- não existe chamada ao endpoint removido `commands/<id>/transfer/`;
- não existe parâmetro `tableId` na abertura da Comanda;
- Checkout de Comanda continua funcionando;
- transferência de itens entre Comandas continua funcionando.

---

# 22. CI / DOCKER

Não desfaça as correções recentes já feitas.

Preserve:

- Next 16.3.8;
- `sharp`;
- lockfiles atuais corrigidos;
- `frontend/public` copiado no standalone;
- checks de assets dentro do container;
- npm audit;
- pip-audit.

Se o backend ficar verde, deixe o pipeline seguir normalmente.

NÃO faça deploy.

Precisamos primeiro ver:

Backend ✅
Frontend ✅
Platform Admin ✅
Production container builds ✅
Publish GHCR ✅

---

# ENTREGA FINAL

Ao concluir, me entregue um relatório objetivo contendo:

1. referências de Mesa removidas do Backoffice de Comandas;
2. endpoints mortos removidos da UI;
3. campos operacionais de Mesa retirados dos contratos de Comanda;
4. campos históricos mantidos e motivo;
5. permissões órfãs removidas/desativadas;
6. situação de `commands.transfer`;
7. situação de `CommandOperationType.TRANSFER`;
8. situação de `AttendanceOperationType.OPEN_TABLE`;
9. situação de `TRANSFER_COMMAND`;
10. ajustes nos relatórios;
11. testes novos/reescritos do TableAttendance;
12. resultado completo do backend;
13. resultado frontend;
14. resultado POS;
15. resultado dos containers;
16. decisão tomada sobre a migration `0011_preserve_existing_pos_entitlements.py`;
17. lista de todas as ocorrências restantes de legado e justificativa;
18. confirmação se existe QUALQUER caminho operacional atual Comanda → Mesa;
19. confirmação se existe QUALQUER caminho operacional atual Mesa → Command;
20. riscos restantes antes da VPS.

REGRA FINAL:

Após esta missão, a resposta para:

“Qual entidade controla a operação de uma Mesa?”

deve ser somente:

`TableAttendance`.

E a resposta para:

“Uma Comanda nova pertence a uma Mesa?”

deve ser:

NÃO.

Não conclua a missão enquanto Backend, Backoffice e POS ainda discordarem sobre isso.