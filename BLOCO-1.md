<role>
Você é o engenheiro principal responsável pelo PATCH FINAL DE ESTABILIZAÇÃO do CORE PDV.

Use o código atual do repositório e todo o contexto desta sessão como fonte primária da verdade.

ANTES de alterar:
- confirme cada problema diretamente no código;
- preserve tudo que está correto dos blocos anteriores;
- investigue a causa raiz;
- não implemente novas funcionalidades fora deste escopo.
</role>

<mission>
Corrigir exclusivamente os blockers técnicos conhecidos antes das próximas evoluções funcionais.
</mission>

<tasks>

1. FRONTEND PACKAGE-LOCK

Corrija a inconsistência entre package.json e package-lock.json do frontend.

O npm ci atualmente apresenta inconsistências envolvendo, entre outras dependências:
- @emnapi/runtime;
- @emnapi/core.

Regere corretamente o lockfile usando o package.json atual.

NÃO atualize a major do npm apenas por causa do aviso de nova versão.

Valide:
- npm ci;
- npm run lint;
- npm run build.

---

2. RBAC DE PREÇOS POR FILIAL

Implementar exatamente:

branch_prices.view
→ visualizar preços da Branch atual.

branch_prices.change
→ alterar preços da Branch atual.

branch_prices.view_company
→ visualizar/comparar preços de todas as Branches da mesma Company.

branch_prices.change_company
→ alterar preços de todas as Branches da mesma Company.

Outra Company:
→ sempre negar.

reports.view_prices:
→ somente relatório;
→ nunca deve conceder edição operacional.

Audite:
- catálogo de permissões;
- permission handlers;
- serializers;
- ViewSets;
- queries;
- frontend;
- rotas autorizadas;
- perfis existentes;
- migrations necessárias.

---

3. SCOPE EXPLÍCITO DE PERMISSÕES

O sistema não deve depender exclusivamente de inferência por prefixo/módulo para decidir COMPANY ou BRANCH.

Crie uma definição explícita de scope para permissões funcionais:

- COMPANY;
- BRANCH.

Use uma fonte consistente no backend.

Atualize o frontend para não depender de listas manuais divergentes como OPERATING_MODULES quando essa informação puder ser derivada da definição correta.

Preserve compatibilidade com permissões/perfis existentes.

Não faça refatoração ampla além do necessário.

---

4. COMMANDS × FEATURE GATE

Impedir:

uses_commands = false

quando a Branch possuir alguma Command OPEN.

Retornar erro de domínio amigável informando que existem Comandas abertas e que elas precisam ser encerradas antes de desativar o recurso.

Não faça auto-finalização.
Não faça auto-cancelamento.
Não deixe operações abertas presas por Feature Gate.

---

5. commands/add-items

O endpoint batch deve ser ALL-OR-NOTHING.

Se qualquer item falhar:
→ nenhum item daquela requisição deve permanecer criado.

Use transaction.atomic no escopo do lote inteiro.

Preserve locks, validações, RBAC e idempotência existentes.

---

6. CATEGORIAS

Corrija a inconsistência atual entre Category model, serializer e ViewSet.

Confirme no código a intenção dos campos:

- available_counter;
- available_table;
- available_command;
- participates_in_service_fee;
- participates_in_commission.

Esses campos são utilizados pela configuração da Categoria e pelo apply-config de Products.

Deixe:
Model ↔ Serializer ↔ View ↔ Frontend
coerentes.

Crie migration nova quando necessário.

Não altere migration histórica.

---

7. AUDITORIA DE Category.apply-config

O BEFORE precisa ser capturado ANTES de alterar Product.

Hoje não pode ocorrer:

before = valor já alterado
after = valor alterado

Garanta auditoria real:

before → estado anterior
after → estado novo.

---

8. MODIFICADORES — DINHEIRO

Corrija o caso em que:

R$ 2,00
é exibido como
R$ 0,02.

Audite modifier-picker e helpers monetários.

Não misture representação "reais" e "centavos".

Valide pelo menos:

2.00 → R$ 2,00
0.50 → R$ 0,50
10.25 → R$ 10,25

Backend continua sendo autoridade do cálculo financeiro.

---

9. commands/add-item

Erros de domínio conhecidos nunca devem virar HTTP 500.

Trate corretamente pelo menos:

- Product inexistente;
- Product de outra Company;
- Product inativo;
- Product indisponível na Branch;
- Product indisponível no canal Command.

Retorne 4xx apropriado com mensagem amigável.

Não permita Product.DoesNotExist escapar como 500.

---

10. PURCHASE ORDER 400

Investigue o POST /purchase-orders/ que retorna 400.

NÃO presuma a causa.

Reproduza o fluxo real.

Capture:
- request;
- serializer;
- service;
- corpo completo da resposta.

Corrija somente a causa comprovada.

A interface deve futuramente conseguir exibir a validação real.

</tasks>

<validation>
Execute testes direcionados para tudo que foi alterado.

Depois execute:
- manage.py check;
- makemigrations --check --dry-run;
- python compileall;
- npm ci;
- npm run lint;
- npm run build;
- git diff --check.

Não precisa executar ainda a grande bateria final dos próximos blocos.
</validation>

<rules>
- Preserve multi-tenant.
- Preserve RBAC.
- Preserve estoque.
- Preserve financeiro.
- Preserve Feature Gates.
- Preserve auditoria.
- Não implemente pagamento parcial.
- Não mexa funcionalmente no Platform Admin.
- Não implemente novas features.
- Não faça commit.
- Não avance para o BLOCO 2.
</rules>

<final_response>
Informe objetivamente:

- problemas confirmados;
- causa raiz;
- arquivos alterados;
- migrations criadas;
- RBAC final de branch_prices;
- modelo final de permission scope;
- correções de Categories;
- correção de Modifiers;
- resultado de commands/add-items;
- resultado de commands/add-item;
- causa real do PurchaseOrder 400;
- testes/checks executados;
- failures restantes.

Finalize com:

BLOCO 1 APROVADO
ou
BLOCO 1 NÃO APROVADO.
</final_response>