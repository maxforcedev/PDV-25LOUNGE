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
- criar os dois Docker Secrets externos e o acesso de pull ao GHCR;
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
