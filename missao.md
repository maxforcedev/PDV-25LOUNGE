CONTINUE O BLOCO 7 E RESOLVA EXCLUSIVAMENTE OS BLOCKERS RESTANTES.

NÃO implemente novas funcionalidades.
NÃO avance para outro bloco.
NÃO faça commit.
NÃO reabra auditorias já concluídas sem necessidade.

O relatório atual terminou como NÃO APROVADO PARA CHECKPOINT pelos seguintes blockers:

1. suíte backend PostgreSQL completa não concluída;
2. frontend npm ci / Docker build falhando por package-lock inconsistente no contexto Docker;
3. check --deploy ainda não validado com configuração produtiva apropriada.

Resolva esses pontos até obter uma conclusão definitiva.

==================================================
1. PACKAGE-LOCK / NPM CI / DOCKER
==================================================

Existe divergência no lockfile do frontend no contexto Docker.

O build relata ausência de:

- @emnapi/runtime@1.11.3
- @emnapi/core@1.11.3

Investigue a CAUSA REAL.

Compare:
- frontend/package.json;
- frontend/package-lock.json;
- versão de Node/npm local;
- versão de Node/npm usada no Dockerfile;
- arquivos efetivamente copiados para o contexto Docker;
- .dockerignore;
- estágio dependencies do Dockerfile.

Não faça workaround usando npm install dentro da imagem.

A homologação exige:

npm ci

funcionando a partir de instalação limpa.

Corrija/regere o package-lock corretamente com a versão compatível com o ambiente usado pelo projeto.

Depois valide obrigatoriamente:

- remover node_modules quando necessário;
- npm ci local;
- npm run lint;
- npm run build;
- docker compose build frontend SEM depender de cache antigo.

Não atualize Node/npm major sem causa comprovada.

==================================================
2. SUÍTE POSTGRESQL COMPLETA
==================================================

A suíte foi interrompida/bloqueada por test_corepdv preexistente.

Investigue esse blocker.

NÃO classifique automaticamente como "preexistente" e siga adiante.

Determine:

- qual banco/schema ficou bloqueando;
- por que test_corepdv existe;
- se é resíduo de execução anterior;
- se o test runner deveria criar/destruir esse banco;
- se existe conexão/processo segurando o database;
- se existe configuração inadequada no ambiente Docker.

Resolva o ambiente de testes de forma segura.

NÃO apague banco de desenvolvimento/produção.

Depois execute a SUÍTE BACKEND COMPLETA em PostgreSQL real.

Informe exatamente:

TOTAL
PASSED
FAILED
SKIPPED

Qualquer failure deve ser investigado pela causa raiz.

Não aceite uma suíte parcial como homologação.

==================================================
3. TESTES CRÍTICOS QUE AINDA NÃO FORAM EFETIVAMENTE EXECUTADOS
==================================================

Durante a suíte PostgreSQL, confirme cobertura/execução dos cenários críticos desta rodada, especialmente:

- RBAC/cross-tenant;
- Branch Prices;
- reorder;
- Inventory/Loss attachment;
- Purchases;
- Commands;
- consumption limit;
- concorrência em Commands;
- limites agregados por Table;
- estoque/Command sem baixa dupla;
- cancelamento sem estorno duplo.

Não crie dezenas de testes redundantes se eles já existem.

Primeiro identifique os testes atuais e execute-os.

Somente adicione teste se existir uma lacuna crítica real.

==================================================
4. CHECK --DEPLOY
==================================================

O check --deploy anterior foi executado com configuração local e acusou:

- DEBUG;
- console email backend;
- secret inseguro;
- cookies;
- SSL/HSTS.

Isso não deve ser "corrigido" enfraquecendo o ambiente local.

Execute manage.py check --deploy com uma configuração efêmera equivalente à produção, seguindo os padrões já existentes no projeto.

Não coloque secrets reais no repositório.

O objetivo é comprovar que a configuração de produção satisfaz os checks.

Se algum warning continuar mesmo com configuração produtiva:
→ investigue.

==================================================
5. MIGRATIONS / ARQUIVOS NÃO RASTREADOS
==================================================

Confirme que as migrations identificadas como necessárias realmente pertencem aos BLOCOs executados:

- companies 0036;
- demais migrations 0003 / 0007 citadas no relatório;
- rotas dedicadas de produtos/usuários.

Não remova arquivos necessários.

Execute:

manage.py makemigrations --check --dry-run

e confirme zero migrations pendentes.

==================================================
6. PRODUCT / USER / PRESETS — REGRESSÕES JÁ CORRIGIDAS
==================================================

Preserve as correções já feitas no BLOCO 7:

- seletor obrigatório de atendente no PDV;
- /produtos/novo;
- /usuarios/novo;
- lote de mesas;
- detach/substituição de PresentationPreset;
- edição divergente do preset.

Não refatore novamente sem failure real.

==================================================
7. WARNINGS
==================================================

Os warnings atuais de lint NÃO são blocker automaticamente.

Não faça refatoração ampla de hooks/no-unused-vars apenas para zerar warnings nesta fase.

Registre-os como dívida técnica se continuarem sem erro.

==================================================
8. orthers.txt
==================================================

Não delete nem altere automaticamente.

Apenas determine:

- se faz parte do produto;
- se é documentação/prompt;
- se é temporário;
- se deve ou não entrar futuramente no checkpoint.

Não deixe esse arquivo impedir a homologação técnica se não fizer parte da aplicação.

==================================================
9. VALIDAÇÃO FINAL
==================================================

Depois das correções, execute obrigatoriamente:

BACKEND
- suíte completa PostgreSQL;
- manage.py check;
- manage.py check --deploy com config produtiva apropriada;
- makemigrations --check --dry-run;
- compileall.

FRONTEND
- instalação limpa com npm ci;
- npm run lint;
- npm run build.

PLATFORM ADMIN
- npm ci;
- npm run lint;
- npm run build.

DOCKER
- docker compose config;
- docker compose build frontend sem depender de cache inconsistente;
- builds afetados;
- healthchecks/configs relevantes.

PROJETO
- git diff --check;
- git status.

==================================================
CRITÉRIO FINAL
==================================================

Só marque:

APROVADO PARA CHECKPOINT

se:

- suíte PostgreSQL completa concluir sem blocker crítico;
- npm ci limpo passar;
- frontend Docker build passar;
- migrations estiverem coerentes;
- check --deploy passar em configuração produtiva apropriada;
- nenhum regression blocker permanecer.

Warnings não críticos podem ser relatados como ressalvas.

Não faça commit.

No relatório final informe:

1. causa do problema do package-lock;
2. correção aplicada;
3. resultado do npm ci;
4. resultado do Docker build;
5. causa do bloqueio test_corepdv;
6. resultado completo da suíte PostgreSQL;
7. total/passed/failed/skipped;
8. check --deploy;
9. migrations;
10. frontend;
11. Platform Admin;
12. Docker;
13. warnings restantes;
14. riscos residuais;
15. classificação final.