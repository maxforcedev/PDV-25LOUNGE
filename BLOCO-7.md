<role>
Você é responsável pela homologação final dos BLOCOs 1 a 6 desta rodada do CORE PDV.

NÃO implemente novas funcionalidades.

Agora a missão é:

- testar;
- encontrar regressões;
- corrigir causa raiz quando estiver dentro do escopo;
- retestar;
- declarar objetivamente se o projeto está pronto para avançar.
</role>

<phase name="AUDIT">

Revise primeiro o git diff completo produzido pelos BLOCOs 1 a 6.

Confirme:

- migrations;
- models;
- serializers;
- services;
- views;
- permissions;
- routes;
- components;
- API clients;
- tests.

Procure implementações incompletas, código morto e inconsistências frontend/backend.
</phase>

<phase name="TARGETED_TESTS">

Garanta cobertura pelo menos para:

RBAC:
- COMPANY/BRANCH scope;
- branch_prices.view;
- branch_prices.change;
- branch_prices.view_company;
- branch_prices.change_company;
- cross-tenant.

Commands:
- open Commands × Feature Gate;
- add-items atomic;
- add-item domain errors;
- múltiplas Commands/Table;
- limite Command;
- limite Table;
- concorrência.

Categories:
- GET;
- POST;
- PATCH;
- reorder;
- apply-config;
- Audit before/after.

Modifiers:
- Group reorder;
- Option reorder;
- ProductModifierGroup reorder;
- dinheiro;
- cross-tenant.

Inventory:
- contagem completa;
- saldo zero;
- parcial;
- residual vazio;
- revisão/captura;
- confirmação;
- perdas;
- attachments;
- movimentos.

Purchases:
- Supplier sem razão social;
- produto sem vínculo Supplier;
- apresentação;
- compra multilinha;
- recebimento;
- parcelas;
- centavos;
- vencimentos;
- pagamento;
- custos.

Sales/PDV:
- service fee;
- promoção;
- pagamentos múltiplos;
- divisão por pessoa;
- engine financeira sem regressão.

Errors:
- 400;
- 403;
- 404;
- 409;
- 500 sanitizado;
- fields no frontend.

Users/Products/Reports/Branding:
- rotas;
- RBAC;
- ausência de regressão.
</phase>

<phase name="CRITICAL_REGRESSIONS">

Revalide também invariantes dos blocos anteriores:

- multi-tenant;
- seller;
- commission;
- feature gates;
- Product/Modifiers;
- Cash;
- Command financial preview;
- Command finalization;
- Inventory baixa uma vez;
- cancelamento estorna uma vez;
- traceability;
- idempotência;
- Purchases/recebimento parcial.

Não considere "fora desta rodada" se uma mudança dos BLOCOs 1-6 quebrou comportamento anteriormente aprovado.
</phase>

<phase name="POSTGRESQL">

Execute a SUÍTE BACKEND COMPLETA utilizando PostgreSQL real.

Não use SQLite para homologação final.

Informe:

- total;
- passed;
- failed;
- skipped.

Qualquer failure deve ser investigado.

Não classifique automaticamente como "preexistente" sem comprovação.
</phase>

<phase name="DJANGO">

Execute:

- manage.py check;
- manage.py check --deploy com configuração de produção apropriada;
- makemigrations --check --dry-run;
- compileall.

Confirme que todas as migrations novas fazem parte do estado atual.
</phase>

<phase name="FRONTEND">

Frontend principal:

- remover node_modules quando necessário para validar instalação limpa;
- npm ci;
- npm run lint;
- npm run build.

Não aceite npm install como substituto de npm ci para homologação.
</phase>

<phase name="PLATFORM_ADMIN">

Se alterado pelo Branding:

- npm ci;
- npm run lint;
- npm run build.

Confirme que nenhuma funcionalidade administrativa foi alterada indevidamente.
</phase>

<phase name="DOCKER">

Valide:

- docker compose config;
- stack/prod config existente;
- build das imagens afetadas;
- startup quando ambiente permitir;
- healthchecks relevantes.

Confirme especialmente que o frontend agora constrói a partir de npm ci limpo.
</phase>

<phase name="SECURITY">

Confirme:

- cross-tenant;
- authorization backend;
- CSRF/session;
- secrets não expostos;
- uploads de perdas autorizados;
- erros 500 sanitizados;
- nenhum novo endpoint de reorder/batch sem RBAC;
- nenhuma alteração que permita frontend substituir backend como barreira de segurança.
</phase>

<phase name="WORKTREE">

Execute:

git status
git diff --stat
git diff --check

Classifique arquivos não rastreados em:

A) código/testes/migrations necessários;
B) prompts/documentação;
C) temporários/lixo;
D) duvidosos.

NÃO delete.
NÃO reset.
NÃO faça commit.
</phase>

<bug_fix_rules>
Se encontrar bug:

1. determine causa raiz;
2. corrija somente se estiver diretamente ligado aos BLOCOs 1–6 ou for regressão causada por eles;
3. não enfraqueça teste;
4. não enfraqueça RBAC;
5. não remova validação apenas para passar;
6. reexecute teste específico;
7. reexecute suíte relevante.

Se exigir grande mudança arquitetural fora do escopo:
→ documente;
→ não improvise.
</bug_fix_rules>

<final_response>
Entregue relatório final com:

1. quantidade total de testes;
2. passed/failed/skipped;
3. RBAC/multi-tenant;
4. Branch Prices;
5. Categories;
6. ordering;
7. error handling;
8. Inventory;
9. Losses;
10. Purchases;
11. PDV;
12. Promotions;
13. Tables/Commands;
14. consumption limits;
15. Product detail;
16. User detail;
17. Reports;
18. Branding;
19. Django checks;
20. migrations;
21. frontend npm ci/lint/build;
22. Platform Admin;
23. Docker;
24. segurança;
25. bugs encontrados e corrigidos;
26. failures restantes;
27. riscos residuais;
28. arquivos duvidosos do worktree.

Classifique SOMENTE como:

APROVADO PARA CHECKPOINT

APROVADO COM RESSALVAS

NÃO APROVADO PARA CHECKPOINT

NÃO faça commit.
</final_response>