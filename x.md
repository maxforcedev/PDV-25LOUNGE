Precisamos corrigir TODOS os bloqueios atuais do pipeline `Publish production images` para voltarmos a gerar as imagens Docker/GHCR e só depois atualizar a VPS.

Analise o estado ATUAL do projeto antes de alterar qualquer coisa.

NÃO faça correções artificiais apenas para deixar testes verdes.
NÃO desative testes.
NÃO coloque `continue-on-error`.
NÃO remova `npm audit` ou `pip-audit`.
NÃO reduza a segurança das validações.
NÃO reverta versões apenas para esconder vulnerabilidades.
NÃO reintroduza código legado de Mesas que já foi removido.
NÃO altere regras de negócio atuais sem antes identificar se a falha é realmente regressão ou somente teste antigo.

O último workflow `Publish production images` do `main` está falhando na validação de Backend, Frontend e Platform Admin.

OBJETIVO FINAL:

1. Frontend verde.
2. Platform Admin verde.
3. Backend verde.
4. Production container builds verdes.
5. Workflow `Publish production images` apto a publicar backend, frontend e platform-admin no GHCR.
6. Imagens Docker de produção realmente completas e prontas para a VPS.

---

## 1. FRONTEND E PLATFORM ADMIN — PACKAGE LOCK QUEBRADO

Atualmente `npm ci` falha nos dois projetos com:

`package.json and package-lock.json are not in sync`

e aponta principalmente:

- Missing: `@emnapi/runtime@1.11.3`
- Missing: `@emnapi/core@1.11.3`

O último ajuste atualizou:

Next 16.3.4 -> 16.3.8

Essa atualização foi necessária porque o `npm audit` anterior bloqueava Next 16.3.4 por vulnerabilidade crítica de RCE.

PORTANTO:

NÃO faça downgrade do Next para 16.3.4.

Mantenha Next 16.3.8.

Corrija corretamente:

- `frontend/package.json`
- `frontend/package-lock.json`
- `platform-admin/package.json`
- `platform-admin/package-lock.json`

Regere/reconcilie os lockfiles em ambiente limpo compatível com o Node 22 utilizado pelo CI.

Não edite package-lock manualmente.

Depois valide obrigatoriamente em diretório limpo:

`npm ci`
`npm run lint`
`npm audit --omit=dev --audit-level=high`
`npm run build`

nos dois projetos.

Investigue também a utilização de `next/image`.

No frontend institucional há uso real de `next/image`. Como usamos `output: "standalone"`, garanta que o runtime de produção tenha suporte correto ao image optimizer, incluindo `sharp` explicitamente se necessário para o Next 16.3.8/standalone.

Não resolva isso com `unoptimized: true` global apenas para contornar o problema.

---

## 2. FRONTEND DOCKER — PUBLIC NÃO ESTÁ NA IMAGEM FINAL

Existe um problema adicional no:

`frontend/Dockerfile`

O estágio de produção atualmente copia:

`/app/.next/standalone`
`/app/.next/static`

mas NÃO copia:

`/app/public`

Nosso site público depende diretamente de assets como:

`public/site/images/hero-operation.webp`
`public/site/images/payment-device-01.webp`
`public/site/images/payment-device-02.webp`
`public/site/images/payment-device-03.webp`
`public/site/images/segments-operation.webp`

e:

`public/site/screenshots/core-pos-venda.webp`
`public/site/screenshots/backoffice-dashboard.webp`
`public/site/screenshots/auditoria.webp`
etc.

Como usamos Next standalone, a pasta `public` precisa existir no runtime final.

Corrija o Dockerfile para que a imagem final possua a pasta `public` no local esperado pelo `server.js` standalone.

Depois adicione verificação no CI/container check para garantir que a regressão nunca volte.

Por exemplo, a validação da imagem de frontend deve confirmar ao menos que existem dentro do container arquivos reais de:

- `public/site/images/hero-operation.webp`
- `public/site/screenshots/core-pos-venda.webp`

E, caso `sharp` seja necessário/instalado explicitamente, validar também que ele consegue ser carregado no container de produção.

Não adicionar workaround de CDN. Hoje esses assets pertencem ao próprio frontend.

---

## 3. BACKEND — ENTITLEMENTS DOS TESTES DESATUALIZADOS

A suíte atualmente termina aproximadamente com:

`FAILED (failures=15, errors=72)`

Mas grande parte é consequência da mesma causa.

Cerca de 49 erros têm:

`Entitlements obrigatorios ausentes: pos.devices.max, pos.enabled`

Hoje:

`CAPABILITY_CATALOG`

inclui corretamente:

- `core.enabled`
- `users.max`
- `branches.max`
- `pos.enabled`
- `pos.devices.max`
- features...

e `REQUIRED_CAPABILITY_CODES` considera os capabilities não-feature obrigatórios.

NÃO remova `pos.enabled` e `pos.devices.max` dos requirements somente para os testes passarem.

Localize os helpers/factories/fixtures antigos dos testes SaaS que ainda criam PlanVersion somente com:

- core.enabled
- users.max
- branches.max

e atualize a fundação de testes para criar planos válidos de acordo com o catálogo atual.

Evite corrigir 49 testes individualmente se todos dependem do mesmo helper central.

Garanta também casos explícitos de teste para:

- POS habilitado;
- POS desabilitado;
- limite de devices;
- ausência intencional de entitlement quando o teste realmente precisa validar esse erro.

Preserve a regra de produção.

---

## 4. MESAS — TESTES AINDA IMPORTAM O SERVIÇO LEGADO

Existem erros de import em:

`backend/apps/commands/tests/test_v2_8_block6.py`

e:

`backend/apps/pos/tests/test_pos5_attendance.py`

porque ainda fazem referência/import a:

`open_table`

de:

`apps.attendance.services`

O serviço atual não possui mais `open_table`.

O domínio novo possui:

`open_table_attendance`

e demais serviços atuais de TableAttendance.

IMPORTANTE:

NÃO reintroduza `open_table`.
NÃO recrie compatibilidade com o Mesas antigo.
NÃO traga o domínio legado de volta só para satisfazer teste antigo.

Nós removemos o fluxo antigo de Mesas intencionalmente.

Atualize os testes para o contrato atual do novo Mesas/TableAttendance ou remova somente trechos de teste comprovadamente pertencentes ao legado que já não existe.

Sobre COMANDAS:

NÃO faça refatoração ampla em Comandas nesta missão.
Só ajuste algo se for estritamente necessário para corrigir referência de teste quebrada causada pela remoção do Mesas legado.

---

## 5. CIELO — CALLBACK INVÁLIDO NÃO PODE QUEBRAR NO LOG

Em:

`backend/apps/payment_integrations/providers/cielo.py`

`parse_payment_callback()`

ao capturar callback Base64/JSON inválido, o logger usa diretamente:

`attempt.pk`

Os testes de adapter utilizam `SimpleNamespace`, que não possui `.pk`.

Resultado:

`AttributeError: 'types.SimpleNamespace' object has no attribute 'pk'`

Isso está mascarando o resultado correto do callback e gera 6 erros na suíte.

Corrija de forma defensiva.

O logging não pode derrubar o parser.

Use identificação segura do attempt quando `pk` não existir.

Não altere por causa disso as regras da Cielo para:

- aprovado;
- recusado;
- erro;
- cancelado;
- unknown;
- callback não comprovável.

Principal regra de segurança:

callback inválido/não comprovável NUNCA pode virar APPROVED.

---

## 6. PAYMENT INTENT — TESTE DE IDEMPOTÊNCIA

Existe falha em:

`test_idempotency_replays_only_matching_request`

O helper do teste gera um novo `origin_id` automaticamente a cada chamada.

O teste faz duas chamadas com a mesma `idempotency_key`, mas com `origin_id` diferente.

O serviço atual inclui `origin_id` no request fingerprint.

Portanto, duas requisições estruturalmente diferentes com a mesma chave DEVEM gerar conflito.

Não remova `origin_id` do fingerprint para fazer o teste passar.

Corrija o teste para:

- usar a mesma idempotency key;
- usar o mesmo origin_id;
- confirmar replay quando toda a requisição é igual;
- confirmar `idempotency_key_conflict` quando algum dado estrutural realmente muda.

---

## 7. OUTRAS FALHAS DA SUÍTE

Depois de eliminar as causas-raiz acima, rode novamente a suíte e trate SOMENTE os erros restantes.

Já existem sinais de expectativas antigas em testes, como:

- 200 esperado e contrato atual retornando 201;
- UUID objeto comparado com UUID serializado/string;
- contrato antigo de beneficiário de movimento de caixa;
- resposta antiga da listagem de beneficiaries;
- regras antigas de POS device/admin;
- fornecedor soft-deleted e reutilização de CPF/CNPJ;
- produto/impressora em contexto incorreto;
- regra de observação em perdas;
- estados de PaymentAttempt;
- comportamento de retry de impressão.

Para CADA falha restante:

1. identifique qual é o contrato atual do sistema;
2. verifique histórico e código consumidor atual;
3. classifique como:
   - regressão real do código; ou
   - teste legado/desatualizado;
4. corrija a camada certa.

NÃO altere comportamento correto de produção apenas para atender expectativa antiga do teste.

Especial atenção para pagamentos, estoque, POS e impressão: não enfraquecer invariantes financeiras, idempotência ou segurança.

---

## 8. DEPENDÊNCIAS DE SEGURANÇA

As versões atuais atualizadas incluem:

- Django 6.1.1
- pypdf 6.19.0
- Next 16.3.8

Essas atualizações vieram para corrigir bloqueios reais dos audits.

NÃO reverta para:

- Django 6.1;
- pypdf 6.16.2;
- Next 16.3.4.

Faça as correções mantendo as versões seguras ou versão superior compatível somente se houver motivo técnico comprovado.

---

## 9. VALIDAÇÃO FINAL

Ao final execute o equivalente ao pipeline real.

BACKEND:

- instalação limpa das requirements;
- `pip-audit`;
- `python manage.py check`;
- `python manage.py makemigrations --check --dry-run`;
- suíte completa de testes;
- `python manage.py check --deploy --fail-level WARNING`;
- `collectstatic`.

FRONTEND:

- `npm ci`;
- lint;
- `npm audit --omit=dev --audit-level=high`;
- build.

PLATFORM ADMIN:

- `npm ci`;
- lint;
- `npm audit --omit=dev --audit-level=high`;
- build.

CONTAINERS:

- validar `docker compose config`;
- validar `docker stack config`;
- build da imagem backend;
- build da imagem frontend;
- build da imagem platform-admin;
- confirmar usuário não-root;
- confirmar comandos finais;
- confirmar metadados de release;
- confirmar assets `public` dentro da imagem frontend;
- confirmar funcionamento do runtime necessário para `next/image`.

Não considere a missão concluída enquanto o mesmo conjunto de validações do GitHub Actions continuar vermelho.

---

## 10. ENTREGA

Ao terminar, me informe:

1. causa-raiz de cada grupo de erros;
2. arquivos alterados;
3. quais testes estavam realmente quebrados;
4. quais testes estavam apenas desatualizados;
5. correções feitas em produção;
6. correções feitas somente nos testes;
7. resultado de cada suíte;
8. resultado de lint/build/audits;
9. resultado dos 3 Docker builds;
10. confirmação de que `public` está presente no frontend standalone;
11. se o projeto está efetivamente pronto para um push que gere as imagens GHCR;
12. qualquer risco restante antes de atualizar a VPS.

NÃO faça deploy na VPS nesta missão.

Primeiro precisamos deixar a origem e as imagens de produção 100% validadas.