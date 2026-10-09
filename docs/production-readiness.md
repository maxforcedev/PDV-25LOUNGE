# CORE PDV - Production Readiness

## Baseline anterior as alteracoes

Data: 2026-08-20

Branch analisada: `dev` (`50d36a4`, sincronizada com `origin/dev`). A branch
`main` estava um commit atras da `dev` e sincronizada com `origin/main`.

Estado funcional confirmado:

- `docker compose ps`: PostgreSQL, backend e frontend saudaveis;
- `python manage.py check`: sem erros, com um check conhecido silenciado;
- `python manage.py makemigrations --check --dry-run`: nenhuma alteracao;
- `npm ci`: lockfile valido e nenhuma vulnerabilidade reportada;
- `npm run build`: build concluido, com 44 rotas geradas;
- `GET http://127.0.0.1:18000/health/`: backend e banco disponiveis;
- `GET http://127.0.0.1:3000/login`: frontend disponivel.

Higiene confirmada:

- nenhum `.env`, certificado ou chave privada esta versionado;
- nao ha historico Git para os caminhos locais conhecidos de `.env`;
- `.venv`, `node_modules` e `.next` nao estao versionados;
- nao existem `FileField` ou `ImageField`, portanto o projeto nao requer
  armazenamento persistente de media nesta etapa.

Problemas existentes antes da preparacao:

- backend de desenvolvimento executava `runserver` como root;
- frontend de desenvolvimento executava `next dev` como root;
- imagem frontend nao possuia build multi-stage/standalone;
- `STATIC_ROOT` e servico de static files de producao nao estavam configurados;
- Docker Secrets e hardening de proxy/HTTPS ainda nao estavam implementados;
- `docker-stack.yml`, contrato de ambiente de producao e workflows de CI/GHCR
  ainda nao existiam.

Comandos reproduziveis, executados a partir da raiz do projeto:

```bash
git status --short
docker compose ps
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
cd frontend && npm ci && npm run build
```

Este documento sera complementado com as instrucoes e validacoes finais de
producao. Secrets reais, configuracao de VPS e credenciais nao pertencem a ele.

## Backend production-ready

Validacoes executadas apos a Sprint 13.2:

- build Docker limpo concluido;
- 157 arquivos static coletados e 453 pos-processados;
- runtime `DEBUG=False` iniciado por Gunicorn 26;
- master e workers executados como `corepdv` (UID 999);
- `/health/` e `/static/admin/css/base.css` responderam com sucesso;
- `SECRET_KEY_FILE` e `POSTGRES_PASSWORD_FILE` validados com arquivos
  efemeros, sem incluir os valores na imagem;
- `manage.py check` e `makemigrations --check --dry-run` aprovados;
- Compose local preservado com `runserver` explicito.

## Seguranca Django

O `check --deploy --fail-level WARNING` passou com o perfil final de HSTS
habilitado. O primeiro deploy deve manter `SECURE_HSTS_SECONDS=0`,
`SECURE_HSTS_INCLUDE_SUBDOMAINS=False` e `SECURE_HSTS_PRELOAD=False` ate DNS,
TLS e todos os subdominios estarem validados. O warning `security.W004` e
esperado somente durante essa fase reversivel; depois, elevar os valores,
habilitar include-subdomains/preload quando aplicavel e repetir o check.

O backend so deve confiar em `X-Forwarded-Proto` e `X-Forwarded-For` quando
`TRUST_PROXY_HEADERS=True`, sem porta publicada e atras do proxy controlado.
O desenvolvimento define essa opcao e o redirect HTTPS como `False`.

## Frontend production-ready

A imagem de producao foi reconstruida sem cache com a API publica e validada:

- 44 rotas compiladas;
- output Next Standalone com aproximadamente 82 MB;
- runtime `node server.js` em porta 3000;
- usuario `node` (UID 1000);
- `/` e `/login` responderam com sucesso e o healthcheck ficou saudavel;
- a URL `https://api.corepdv.com/api/v1` foi encontrada no bundle;
- source, lockfile e dependencias de desenvolvimento nao foram copiados para a
  imagem final;
- build com URL de loopback falhou, conforme esperado;
- target `development` recomposto e saudavel com `next dev` no Compose local.

## Higiene e ambientes

- `.venv`, `venv`, `node_modules`, `.next`, `.env*`, logs, caches e backups
  locais sao ignorados conforme o tipo de artefato;
- `.dockerignore` impede que environments locais entrem nos tres contextos;
- `.env.production.example` documenta dominios, imagens, tag, database,
  hardening, Gunicorn, build publico e caminhos de Docker Secrets;
- os exemplos de backend e dos dois frontends continuam sendo exclusivos de dev;
- `.gitattributes` garante LF em scripts shell;
- imagens inspecionadas nao contem `.env`, ambientes virtuais ou source local
  indevido, e a varredura nao encontrou formatos conhecidos de credencial.

## Contrato do stack

`docker-stack.yml` declara PostgreSQL 16, backend, Backoffice e Platform Admin
como servicos independentes. Nao ha portas publicadas. PostgreSQL e os anexos
privados de compras usam volumes persistentes; as aplicacoes usam a rede
externa do proxy apenas quando necessario.

Validacao sem deploy:

```bash
export RELEASE_TAG=<full-commit-sha>
docker stack config --compose-file docker-stack.yml >/dev/null
```

Dependencias externas que deverao existir antes do deploy na VPS:

- rede overlay `traefik_public`;
- secrets `corepdv_django_secret_key` e `corepdv_postgres_password`;
- imagens backend/frontend/platform-admin no GHCR com a mesma tag SHA;
- acesso do Swarm ao GHCR quando os pacotes forem privados;
- proxy central com entrypoint `websecure` e suporte aos hosts declarados.

O backend usa `stop-first` porque migrations ainda podem rodar no startup de
uma unica replica. Quando houver mais replicas, definir `MIGRATE_ON_START=False`
e mover `migrate --noinput` para uma etapa unica de release.

## Integracao continua

`.github/workflows/ci.yml` executa em push para `dev`, em pull request para
`main` e por chamada reutilizavel. Ele valida Django, migrations, deployment
settings, static files, Backoffice, lint/build do Platform Admin, Compose, stack
e as tres imagens finais. O job tambem falha se uma imagem rodar como root ou
usar comandos de desenvolvimento.

A CI possui apenas `contents: read` e nao autentica em registry, nao publica
imagem, nao acessa a VPS e nao executa deploy.

Os arquivos `ci.yml` e `ghcr.yml` estao versionados em `.github/workflows/` e
nao sao ignorados. A validacao local deve analisar ambos sempre que a matriz de
imagens ou o contrato de deploy mudar.

## Imagens no GHCR

Push aprovado em `main` executa `.github/workflows/ghcr.yml` somente depois da
CI e publica:

```text
ghcr.io/maxforcedev/core-pdv-backend:<full-commit-sha>
ghcr.io/maxforcedev/core-pdv-frontend:<full-commit-sha>
ghcr.io/maxforcedev/core-pdv-platform-admin:<full-commit-sha>
```

`latest` tambem e publicado como conveniencia, mas `RELEASE_TAG` no stack deve
sempre receber o SHA completo. Os dois frontends sao compilados com
`https://api.corepdv.com/api/v1`; o Platform Admin tambem recebe
`https://corepdv.com` como URL publica do Backoffice. O workflow usa apenas
`GITHUB_TOKEN` para o GHCR e nao possui dados ou comandos de acesso a servidor.

As imagens base e as Actions estao fixadas por digest/commit. Antes de publicar,
o workflow consulta a tag SHA no GHCR e se recusa a sobrescreve-la. Falhas de
autenticacao ou rede tambem interrompem a publicacao; apenas uma resposta
confirmada de tag inexistente permite o primeiro push.

## Operacao de release

O servidor deve receber imagens prontas do GHCR. Nao executar `pip install`,
`npm install`, `npm run build` ou `docker build` como fluxo normal de release.

Variaveis minimas para renderizar o stack:

```bash
export BACKEND_IMAGE=ghcr.io/maxforcedev/core-pdv-backend
export FRONTEND_IMAGE=ghcr.io/maxforcedev/core-pdv-frontend
export PLATFORM_ADMIN_IMAGE=ghcr.io/maxforcedev/core-pdv-platform-admin
export FRONTEND_DOMAIN=corepdv.com
export PLATFORM_ADMIN_DOMAIN=admin.corepdv.com
export ALLOWED_HOSTS=api.corepdv.com,corepdv.com,admin.corepdv.com,127.0.0.1
export CSRF_TRUSTED_ORIGINS=https://corepdv.com,https://admin.corepdv.com,https://*.corepdv.com
export CORS_ALLOWED_ORIGINS=https://corepdv.com,https://admin.corepdv.com
export RELEASE_TAG=<full-commit-sha>
docker stack config --compose-file docker-stack.yml >/dev/null
```

Depois que a infraestrutura externa e os secrets existirem, o futuro processo
de deploy podera aplicar o arquivo versionado com `docker stack deploy`. Um
rollback deve repetir o deploy usando o SHA completo da release anterior, nunca
apenas `latest`.

Logs de Django, Gunicorn e Next sao emitidos em stdout/stderr. O projeto nao
grava logs em volume. Os volumes `postgres_data` e `private_media` requerem
persistencia e backup; anexos privados nunca sao publicados diretamente pelo
proxy e trafegam apenas pelos endpoints autenticados do backend.

## Limite de confianca do proxy

`TRUST_PROXY_HEADERS=True` e `GUNICORN_FORWARDED_ALLOW_IPS=*` sao adequados
somente porque o backend nao publica porta e deve compartilhar
`traefik_public` exclusivamente com workloads controlados. A VPS deve impedir
workloads nao confiaveis nessa rede e o Traefik deve substituir/sanitizar
`X-Forwarded-Proto` e `X-Forwarded-For`. Se a infraestrutura fornecer enderecos
estaveis do proxy, restringir `GUNICORN_FORWARDED_ALLOW_IPS` por environment.

## Regras operacionais pre-POS

- `CommandPayment` e um ledger imutavel. Enquanto houver pagamento aplicado,
  transferir itens, dividir ou mesclar comandas e bloqueado antes de alterar
  pedidos; o operador deve estornar os pagamentos primeiro.
- Transferir apenas a mesa permanece permitido, pois nao move itens nem altera
  o total financeiro.
- Um `OrderItem` confirmado somente pode ser transferido integralmente. A
  transferencia parcial e bloqueada para preservar os movimentos de estoque,
  snapshots e estornos vinculados ao item original.
- Producao e impressao sao controladas por `feature.production`, independente
  de `feature.commands`, porque vendas diretas tambem podem emitir producao.

## Pendencias do projeto

- executar os workflows no GitHub apos o push para confirmar permissoes do
  pacote e a primeira publicacao no GHCR;
- validar o fluxo completo de sessao, CORS e CSRF pelos dominios publicos depois
  que DNS/TLS existirem;
- apos validar HTTPS em todos os subdominios, elevar HSTS e repetir
  `manage.py check --deploy --fail-level WARNING`;
- quando o backend tiver mais de uma replica, retirar migrations do startup e
  criar uma etapa unica de release.

## Pendencias da VPS

- preparar Ubuntu, Docker Engine, Swarm e usuario de deploy;
- configurar firewall, SSH e estrutura operacional em `/opt`;
- criar e controlar a rede overlay externa `traefik_public`;
- instalar/configurar o Traefik central, DNS Cloudflare e certificados TLS;
- apontar `admin.corepdv.com` para o proxy central existente;
- criar os Docker Secrets externos obrigatorios e o acesso de pull ao GHCR;
- configurar backups e restauracao do volume PostgreSQL;
- executar o primeiro deploy, smoke remoto, teste de rollback e observacao de
  logs/healthchecks.

## Validacao local V2.2

Resultado da revisao da infraestrutura V2.2:

- `npm ci --dry-run --ignore-scripts` do Platform Admin: aprovado;
- `npm run lint` do Platform Admin: aprovado;
- imagem `runner` do Platform Admin: build aprovado, com 10 rotas;
- runtime da imagem: usuario `operator`, `node server.js`, porta 3100 e
  healthcheck estrito em `/login`;
- bundle final contem `https://api.corepdv.com/api/v1` e
  `https://corepdv.com`, sem URLs HTTP de loopback;
- `docker compose config` e `docker stack config` com valores placeholder:
  aprovados;
- sintaxe dos dois workflows, sintaxe POSIX e ShellCheck do smoke test:
  aprovados;
- `git diff --check` nos arquivos desta entrega: aprovado.

## Platform Admin V2.2

O Platform Admin possui servico, imagem, healthcheck e router Traefik proprios.
Em desenvolvimento ele usa `http://localhost:3001`; em producao o router atende
`https://admin.corepdv.com` no mesmo entrypoint `websecure` e resolver
`letsencrypt` dos servicos existentes. Nenhum proxy ou mecanismo adicional de
certificado faz parte deste stack.

O backend aceita somente as origens explicitas dos dois frontends. Em producao:

```env
CSRF_TRUSTED_ORIGINS=https://corepdv.com,https://admin.corepdv.com,https://*.corepdv.com
CORS_ALLOWED_ORIGINS=https://corepdv.com,https://admin.corepdv.com
```

O wildcard e exclusivo da confianca CSRF prevista no PRD. CORS autenticado
permanece restrito aos dois origins concretos.

O smoke remoto inclui `${PLATFORM_ADMIN_BASE_URL:-https://admin.corepdv.com}/login`.
Para validacao local, sobrescrever as tres URLs publicas quando os servicos de
desenvolvimento estiverem ativos:

```bash
API_BASE_URL=http://127.0.0.1:18000 \
FRONTEND_BASE_URL=http://127.0.0.1:3000 \
PLATFORM_ADMIN_BASE_URL=http://127.0.0.1:3001 \
scripts/smoke-test.sh
```

O fato de `platform-admin/` ainda estar nao rastreado no worktree atual nao e
falha de codigo nem bloqueio tecnico da imagem; o diretorio deve integrar o
mesmo commit da infraestrutura antes da publicacao.

## Atualizacao de producao - outubro de 2026

Esta secao substitui o estado operacional anterior para a release aprovada
`31497e31e7630e1d644c209740180f6b6d92fe26`. A CI desta release foi aprovada,
incluindo backend, 437 testes, migrations, `check --deploy`, Frontend, Platform
Admin, imagens de container e publicacao no GHCR. Isso nao valida a VPS: nenhum
deploy ou acesso ao servidor foi executado como parte desta preparacao.

As tres imagens devem usar a mesma tag SHA completa:

```text
ghcr.io/maxforcedev/core-pdv-backend:<RELEASE_TAG>
ghcr.io/maxforcedev/core-pdv-frontend:<RELEASE_TAG>
ghcr.io/maxforcedev/core-pdv-platform-admin:<RELEASE_TAG>
```

O stack Swarm e `corepdv`, com atualizacao in-place e volumes persistentes.
Nunca usar `docker stack rm corepdv`, `docker volume rm` ou `docker system prune
--volumes` como parte de uma atualizacao normal.

### Contrato de secrets e SMTP

Todos os secrets abaixo sao externos ao stack e precisam existir antes de
`docker stack deploy`; o stack referencia nomes, mas nao cria nenhum secret.

- `corepdv_django_secret_key` (configuravel por `DJANGO_SECRET_NAME`)
- `corepdv_postgres_password` (configuravel por `POSTGRES_PASSWORD_SECRET_NAME`)
- `corepdv_cielo_smart_client_id` (configuravel por `CIELO_SMART_CLIENT_ID_SECRET_NAME`)
- `corepdv_cielo_smart_access_token` (configuravel por `CIELO_SMART_ACCESS_TOKEN_SECRET_NAME`)
- `corepdv_smtp_password` (configuravel por `SMTP_PASSWORD_SECRET_NAME`, somente com SMTP habilitado)

O backend le Cielo pelos arquivos de secret `/run/secrets/cielo_smart_client_id`
e `/run/secrets/cielo_smart_access_token`, compativeis com `env_or_file()`.
Nenhum valor de Cielo deve ser colocado em `.env.production` ou Git.

SMTP e opcional nesta fase. O stack base nao monta `smtp_password`, nao aponta
para `/run/secrets/smtp_password` e usa o backend console padrao do Django. Para
habilitar SMTP, definir `SMTP_ENABLED=True` e implantar os dois arquivos:

```bash
docker stack deploy --with-registry-auth \
  --compose-file docker-stack.yml \
  --compose-file docker-stack.smtp.yml corepdv
```

O overlay SMTP exige `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`DEFAULT_FROM_EMAIL`, `SALES_LEAD_EMAIL` e o secret SMTP. `EMAIL_USE_TLS` e
`EMAIL_USE_SSL` devem ser coerentes e nunca ambos verdadeiros. A ausencia do
secret deve bloquear SMTP, nao ser substituida por uma senha dummy.
`production-preflight.sh` ignora todos esses requisitos quando
`SMTP_ENABLED=False`; com `SMTP_ENABLED=True`, exige os campos, o secret e
rejeita TLS e SSL simultaneamente ativos. `EMAIL_USE_TLS=True`,
`EMAIL_USE_SSL=False` e `EMAIL_TIMEOUT=10` sao os defaults do overlay.
Tambem bloqueia os placeholders documentados `smtp.example.invalid`,
`replace-with-smtp-user` e `sales@example.invalid`; substitua-os por dados
reais antes de habilitar SMTP.

`SALES_LEAD_EMAIL` e o destinatario das notificacoes do formulario comercial.
O lead e persistido antes do envio; uma falha SMTP e registrada no servidor,
mas nao descarta o lead nem altera a resposta publica ao visitante.

### Ambiente, banco e POS

Use `.env.production.example` como o contrato publico completo do deploy. No
modo Swarm, `POSTGRES_HOST`, `POSTGRES_PORT` e `DATABASE_URL` nao devem ser
definidos: `docker-stack.yml` monta a conexao interna como
`postgresql://${POSTGRES_USER}@db:5432/${POSTGRES_DB}` e recebe a senha apenas
do secret `postgres_password`.

`FRONTEND_URL` e obrigatorio e deve conter a origem HTTPS publica do
Backoffice. O backend usa essa origem para links de redefinicao de senha e de
configuracao/reset de PIN do POS. A redefinicao aponta para
`/redefinir-senha` e os links de PIN para `/pos/pin`. O pareamento inicial do
dispositivo envia um OTP por email e nao usa um link baseado em `FRONTEND_URL`.
A redefinicao usa o backend de email configurado e falhas de entrega nao
revelam se o email possui uma conta.

O CORE POS recebe a URL da API no build do aplicativo, nunca como variavel
runtime do backend nem como segredo no APK:

```bash
flutter build apk --release \
  --dart-define=POS_API_BASE_URL=https://api.corepdv.com
```

O backend recebe `POS_CURRENT_VERSION`, `POS_LATEST_VERSION`,
`POS_MINIMUM_SUPPORTED_VERSION` e `POS_OPERATOR_SESSION_MINUTES` pelo stack.
Os defaults atuais sao respectivamente `1.0.0`, `1.0.0`, `1.0.0` e `480`.
Para imagens web, `NEXT_PUBLIC_API_URL` e `NEXT_PUBLIC_BACKOFFICE_URL` sao
argumentos de build definidos pelo workflow de publicacao; exporta-los no
servidor Swarm nao altera imagens ja publicadas.

### Preflight e migrations

No servidor, exporte as variaveis publicas de `.env.production` para o ambiente
do shell antes de executar scripts. O preflight nao cria, altera ou revela
secrets, banco, stack ou servidor:

```bash
scripts/production-preflight.sh
```

Ele exige Docker e Swarm ativos, `RELEASE_TAG` SHA de 40 caracteres, rede
`TRAEFIK_NETWORK` (padrao `traefik_public`), dominios e variaveis essenciais,
secrets externos, imagens GHCR na mesma tag e configuracao valida do stack.

O backend permanece com `MIGRATE_ON_START=True` enquanto existir apenas uma
replica. Nesta topologia, nao ha um job pre-deploy seguro e simples para executar
`showmigrations` ou `migrate --plan` contra a imagem alvo: um `docker run` comum
nao recebe Docker Secrets Swarm, e executar contra o backend atual inspeciona a
imagem anterior, nao a release alvo. Nao usar esse ultimo atalho como validacao
da release.

O preflight valida a imagem alvo e o stack; o backup obrigatorio protege a
atualizacao cujo backend unico executara migrations no startup. Apos o deploy,
inspecione o backend da release com `python manage.py showmigrations` e
`python manage.py migrate --plan` se for necessaria confirmacao operacional.
Rollback Swarm reverte aplicacao/container, nunca o schema PostgreSQL.

### Backup e release controlado

Antes de atualizar, execute o backup no manager Swarm:

```bash
BACKUP_DIR=/var/backups/corepdv scripts/backup-postgres.sh
```

O script encontra a task PostgreSQL ativa de `corepdv`, gera `pg_dump` em formato
custom com timestamp para um arquivo `.partial`, valida tamanho e `pg_restore
--list`, aplica permissao `0600` e so entao renomeia atomicamente para `.dump`.
Em falha, remove apenas o `.partial` criado por essa execucao; nunca remove um
backup completo existente nem imprime senha. Para restauracao de emergencia, com
o servico PostgreSQL parado ou em banco de recuperacao separado, use `pg_restore
--clean --if-exists --no-owner --dbname=<database> <arquivo.dump`. Restauracao
automatica nao faz parte do fluxo de release.

Para atualizar a release existente:

```bash
RELEASE_TAG=<sha-completo> scripts/release-production.sh
```

O script executa preflight, mostra imagens atuais e alvo, valida o stack, cria
backup (ou aceita `BACKUP_FILE` existente e nao vazio), executa `docker stack
deploy --with-registry-auth` e so continua quando backend, Frontend e Platform
Admin possuem a imagem alvo e update Swarm concluido. Rollback iniciado/concluido,
update pausado, task antiga ou imagem divergente falham o release. O smoke test
ocorre depois disso e exige que `/health/` reporte `release.commit` igual ao
`RELEASE_TAG`; HTTP 200 da release anterior nao e aceito.

O script nao inicializa servidor, nao recria secrets/volumes e nao faz rollback
destrutivo de banco. Falha de smoke test requer investigacao; reimplantar imagem
anterior tambem nao desfaz migrations.

`SECURE_HSTS_SECONDS` continua inicialmente em `0`. Apos DNS, HTTPS e todos os
subdominios serem validados publicamente, habilitar HSTS gradualmente, considerar
include-subdomains/preload somente quando apropriado e repetir `check --deploy`.
