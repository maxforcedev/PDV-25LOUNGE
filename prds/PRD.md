# PRD — CORE PDV — Preparação do Projeto para Produção

> **Versão:** 1.0
> **Projeto:** CORE PDV / PDV 25 Lounge
> **Objetivo:** transformar o código atual, executado em desenvolvimento local, em um projeto preparado para execução em produção
> **Escopo:** somente alterações dentro do repositório
> **Fora do escopo:** preparação/configuração da VPS
> **Backend:** Django + Django REST Framework + PostgreSQL
> **Frontend:** Next.js + React
> **Runtime backend de produção:** Gunicorn
> **Runtime frontend de produção:** Next.js Standalone
> **Containerização:** Docker
> **Produção prevista:** Docker Swarm
> **Domínio previsto:** `corepdv.com`
> **API prevista:** `api.corepdv.com`

---

# 1. Objetivo

Preparar o repositório atual do CORE PDV para que ele possa posteriormente ser implantado em uma VPS de produção sem precisar modificar o código novamente no servidor.

Ao concluir este PRD, o projeto deverá possuir dois comportamentos claramente separados:

```text
DESENVOLVIMENTO
docker compose
Django runserver
Next.js dev
hot reload
volumes locais
configuração local
```

e:

```text
PRODUÇÃO
Docker images imutáveis
Django + Gunicorn
Next.js build standalone
DEBUG=False
sem volumes de código
sem servidores de desenvolvimento
variáveis externas
secrets externos
healthchecks
docker-stack.yml
```

A VPS será preparada posteriormente por outro PRD/script.

---

# 2. Princípio fundamental

O projeto deve ser:

> **desenvolvido localmente como hoje e executado em produção sem alteração manual de código.**

Não deverão existir modificações feitas diretamente na VPS para fazer a aplicação funcionar.

Configuração de ambiente deve entrar por:

* environment variables;
* Docker Secrets quando apropriado;
* parâmetros de build quando necessário.

---

# 3. Limite deste PRD

Este PRD PODE alterar ou criar arquivos como:

```text
.gitignore
.env.production.example
docker-compose.yml
docker-stack.yml

backend/
├── Dockerfile
├── entrypoint.sh
├── requirements.txt
├── .dockerignore
├── .env.example
└── core/settings.py

frontend/
├── Dockerfile
├── .dockerignore
├── .env.example
└── next.config.ts

scripts/
└── ...

.github/
└── workflows/
    └── ...
```

Este PRD NÃO deve:

* instalar Docker na VPS;
* inicializar Docker Swarm na VPS;
* instalar Traefik;
* configurar firewall;
* configurar SSH;
* criar usuário Linux;
* instalar Fail2ban;
* configurar Cloudflare;
* emitir certificados;
* modificar DNS;
* criar diretórios globais da VPS;
* configurar outros projetos;
* executar deploy real.

Essas tarefas pertencem ao PRD de preparação da VPS.

---

# 4. Preservação obrigatória do projeto

O projeto atual possui desenvolvimento funcional já realizado.

Antes de qualquer alteração:

* inspecionar o estado atual do repositório;
* executar `git status`;
* preservar arquivos modificados;
* não sobrescrever regras funcionais existentes;
* não reescrever migrations existentes sem necessidade;
* não realizar limpeza destrutiva.

É proibido executar automaticamente:

```bash
git reset --hard
git clean -fd
git restore .
```

ou equivalente.

O objetivo desta sprint é alterar **runtime e infraestrutura do projeto**, não regras de negócio.

---

# 5. Estado atual identificado

## 5.1 Backend

Atualmente existe:

```text
Python 3.13
Django 6.1
Django REST Framework
PostgreSQL
psycopg
django-environ
django-cors-headers
Gunicorn
```

O projeto já possui:

```text
backend/Dockerfile
backend/entrypoint.sh
backend/.dockerignore
backend/.env.example
backend/requirements.txt
```

O Dockerfile atual termina com:

```text
python manage.py runserver 0.0.0.0:8000
```

Isso é adequado para desenvolvimento, mas proibido como runtime de produção.

Gunicorn já está instalado no projeto.

## 5.2 Frontend

Atualmente existe:

```text
Node 22
Next.js 16
React 19
TypeScript
Tailwind
```

O `next.config.ts` já utiliza:

```ts
output: 'standalone'
```

Portanto a imagem de produção deve aproveitar o output standalone.

O Dockerfile atual inicia:

```text
npm run dev
```

Isso deve permanecer apenas no desenvolvimento.

## 5.3 Banco

O projeto utiliza:

```text
PostgreSQL 16
```

O PostgreSQL continuará sendo o banco oficial de produção.

SQLite não deverá ser introduzido como fallback de produção.

## 5.4 Serviços inexistentes

Não foram identificados requisitos atuais para:

* Redis;
* RabbitMQ;
* Celery;
* Celery Beat;
* workers;
* filas.

Portanto:

> NÃO adicionar esses serviços.

---

# 6. Desenvolvimento local deve continuar funcionando

O atual:

```text
docker-compose.yml
```

continua sendo o ambiente de desenvolvimento.

O desenvolvedor deverá continuar podendo executar:

```bash
docker compose up -d --build
```

e receber:

```text
PostgreSQL local
Django desenvolvimento
Next.js desenvolvimento
hot reload
```

Produção não pode prejudicar esse fluxo.

---

# 7. Dockerfile do backend

Refatorar:

```text
backend/Dockerfile
```

para suportar runtime de produção.

## Requisitos

* usar Python 3.13;
* utilizar imagem `slim`;
* instalar somente dependências necessárias;
* copiar dependências antes do source para aproveitar cache;
* evitar arquivos desnecessários;
* executar processo como usuário não-root;
* possuir `PYTHONDONTWRITEBYTECODE=1`;
* possuir `PYTHONUNBUFFERED=1`;
* não armazenar cache do pip;
* expor somente a porta interna `8000`;
* utilizar entrypoint existente/refatorado.

Runtime de produção:

```bash
gunicorn core.wsgi:application
```

Não utilizar:

```bash
python manage.py runserver
```

em produção.

---

# 8. Gunicorn

Configurar execução do Gunicorn com valores configuráveis por environment.

Variáveis sugeridas:

```text
GUNICORN_WORKERS
GUNICORN_TIMEOUT
GUNICORN_GRACEFUL_TIMEOUT
GUNICORN_KEEP_ALIVE
```

Valores padrão devem ser conservadores.

Não assumir quantidade elevada de CPU/RAM.

Exemplo conceitual:

```text
gunicorn core.wsgi:application
--bind 0.0.0.0:8000
--workers ${GUNICORN_WORKERS}
--timeout ${GUNICORN_TIMEOUT}
```

Logs devem ir para:

```text
stdout
stderr
```

Não criar arquivos de log dentro do container como mecanismo principal.

---

# 9. EntryPoint do backend

Refatorar:

```text
backend/entrypoint.sh
```

sem remover a espera pelo PostgreSQL já existente.

Fluxo esperado:

```text
carregar configuração
        ↓
aguardar PostgreSQL
        ↓
executar tarefas de preparação permitidas
        ↓
exec do processo principal
```

O script deve terminar usando:

```bash
exec "$@"
```

para o processo receber corretamente sinais do Docker.

---

# 10. Migrations

O projeto deverá estar preparado para:

```bash
python manage.py migrate --noinput
```

em produção.

Para a primeira versão, com uma única réplica do backend, é aceitável executar migrations durante a inicialização controlada.

Porém deixar documentado:

> Quando o backend possuir múltiplas réplicas, migrations deverão sair do startup de cada container e virar uma etapa única de release.

Não executar:

```text
makemigrations
```

automaticamente em produção.

`makemigrations` pertence ao desenvolvimento.

---

# 11. Verificação de migrations

Adicionar aos checks do projeto:

```bash
python manage.py check
python manage.py makemigrations --check
```

Produção não pode depender de migration criada manualmente na VPS.

Todas as migrations necessárias devem estar versionadas.

---

# 12. Django settings para produção

Revisar:

```text
backend/core/settings.py
```

O mesmo settings principal pode continuar sendo utilizado.

Não criar arquitetura complexa de múltiplos settings sem necessidade.

Configurações devem variar por environment.

Produção obrigatoriamente:

```text
DEBUG=False
```

---

# 13. SECRET_KEY

`SECRET_KEY` nunca deve:

* possuir valor real versionado;
* possuir fallback inseguro em produção;
* ser gerada novamente a cada restart.

Se `DEBUG=False` e `SECRET_KEY` estiver ausente:

> a aplicação deve falhar imediatamente.

O projeto deve aceitar obtenção do segredo por environment e/ou Docker Secret.

---

# 14. Suporte a Docker Secrets

Preparar o backend para receber valores sensíveis por arquivos em:

```text
/run/secrets/
```

Pelo menos:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
```

A implementação pode utilizar convenção:

```text
SECRET_KEY_FILE
POSTGRES_PASSWORD_FILE
```

ou helper central equivalente.

Não duplicar a lógica de leitura de secrets em diversos módulos.

Não imprimir segredos em logs.

---

# 15. Database URL

O backend deverá continuar utilizando:

```text
DATABASE_URL
```

ou mecanismo equivalente consolidado.

Produção deverá suportar PostgreSQL através do hostname interno Docker.

Exemplo conceitual:

```text
postgresql://corepdv:***@db:5432/corepdv
```

Nenhuma credencial real deve ser incluída em:

```text
Dockerfile
docker-stack.yml
GitHub
README
PRD
```

---

# 16. Proxy HTTPS

Como futuramente o backend ficará atrás de reverse proxy, configurar suporte a:

```python
SECURE_PROXY_SSL_HEADER = (
    'HTTP_X_FORWARDED_PROTO',
    'https',
)
```

de forma apropriada para produção.

Isso é configuração da aplicação.

A configuração do Traefik em si não pertence a este PRD.

---

# 17. Segurança Django de produção

Adicionar/configurar suporte a:

```text
SESSION_COOKIE_SECURE
CSRF_COOKIE_SECURE
SECURE_SSL_REDIRECT
SECURE_HSTS_SECONDS
SECURE_HSTS_INCLUDE_SUBDOMAINS
SECURE_CONTENT_TYPE_NOSNIFF
```

As configurações devem depender do ambiente.

Desenvolvimento local não pode ser forçado a HTTPS.

---

# 18. HSTS

HSTS deve ser configurável.

Não hardcodar imediatamente um valor agressivo impossível de reverter.

Exemplo:

```text
SECURE_HSTS_SECONDS=0
```

durante primeira validação.

Após HTTPS estar comprovadamente correto, poderá ser elevado no ambiente de produção.

---

# 19. ALLOWED_HOSTS

O projeto deve aceitar configuration externa.

Produção prevista:

```text
corepdv.com
api.corepdv.com
```

Também permitir hostname necessário ao healthcheck interno quando justificável.

Não utilizar:

```text
ALLOWED_HOSTS=*
```

em produção.

---

# 20. CORS

Produção prevista:

```text
https://corepdv.com
```

Não utilizar wildcard.

O projeto atual utiliza autenticação com credenciais, portanto preservar:

```text
CORS_ALLOW_CREDENTIALS = True
```

quando aplicável.

---

# 21. CSRF

Configuração prevista:

```text
https://corepdv.com
https://*.corepdv.com
```

O frontend e backend permanecem em origens diferentes:

```text
corepdv.com
api.corepdv.com
```

Portanto a configuração CSRF deverá ser validada em produção.

Não remover proteção CSRF para "resolver" erro de deploy.

---

# 22. Autenticação

Não alterar a estratégia de autenticação existente apenas por causa do deploy.

Preservar o comportamento atual.

Se atualmente a aplicação utilizar sessão/cookies:

* manter sessão;
* manter cookies;
* manter CSRF;
* configurar corretamente os atributos seguros.

Não migrar para JWT nesta sprint.

---

# 23. Static files do Django

O backend precisa estar apto a executar:

```bash
python manage.py collectstatic --noinput
```

Definir:

```text
STATIC_ROOT
```

adequadamente.

Como existe Django Admin, seus assets precisam funcionar em produção.

Utilizar solução simples.

É permitido adicionar WhiteNoise se essa for a opção mais adequada.

Não adicionar Nginx ao projeto somente para static files.

---

# 24. Media

Antes de implementar qualquer infraestrutura de media:

1. verificar se o projeto realmente utiliza upload persistente;
2. verificar models com `FileField`/`ImageField`;
3. somente então criar persistência.

Não criar S3, MinIO ou volume de media sem necessidade atual comprovada.

---

# 25. Healthcheck backend

Preservar:

```text
GET /health/
```

A rota deve continuar:

* leve;
* pública;
* apropriada para container healthcheck;
* retornar sucesso com aplicação/banco saudáveis;
* retornar falha quando dependência crítica não estiver disponível.

Não adicionar autenticação ao `/health/`.

---

# 26. Dockerfile do frontend

Refatorar:

```text
frontend/Dockerfile
```

para imagem multi-stage.

Estrutura recomendada:

```text
deps
builder
runner
```

---

# 27. Build frontend

Build:

```bash
npm ci
npm run build
```

O projeto já utiliza:

```ts
output: 'standalone'
```

A imagem final deverá copiar somente os artefatos necessários.

Exemplo conceitual:

```text
.next/standalone
.next/static
public
```

quando existentes.

Não copiar `node_modules` completo de desenvolvimento para o runtime final.

---

# 28. Runtime frontend

Produção NÃO executa:

```bash
npm run dev
```

Deverá executar o servidor gerado pelo Next standalone, por exemplo:

```bash
node server.js
```

ou mecanismo oficial equivalente da versão instalada.

Porta interna:

```text
3000
```

---

# 29. Usuário não-root frontend

O processo Node deve executar com usuário sem privilégios administrativos.

A imagem final não deve rodar como root.

---

# 30. NEXT_PUBLIC_API_URL

O frontend atual utiliza:

```text
NEXT_PUBLIC_API_URL
```

Esse valor é público e é incorporado durante o build.

Produção prevista:

```text
https://api.corepdv.com/api/v1
```

O Dockerfile deve receber esse valor durante o build.

Exemplo:

```text
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
```

A imagem final de produção nunca pode estar compilada apontando para:

```text
localhost
127.0.0.1
```

---

# 31. Healthcheck frontend

Criar healthcheck simples para o runtime de produção.

Pode validar:

```text
/
```

ou:

```text
/login
```

Não criar healthcheck pesado.

O healthcheck deve considerar respostas abaixo de 500 como aplicação disponível, quando apropriado.

---

# 32. .dockerignore backend

Garantir que não entrem na imagem:

```text
.env
.venv
venv
__pycache__
*.pyc
.git
*.log
tests temporários/artefatos quando aplicável
```

Não copiar segredo local para imagem Docker.

---

# 33. .dockerignore frontend

Garantir:

```text
node_modules
.next
.git
.env
.env.local
*.log
```

O build deve ser reproduzível a partir de:

```text
package.json
package-lock.json
source
```

---

# 34. .gitignore

Atualizar o `.gitignore` garantindo:

```gitignore
# Python
.venv/
venv/
backend/.venv/
__pycache__/
*.py[cod]

# Node / Next
node_modules/
frontend/node_modules/
.next/
frontend/.next/

# Environment
.env
.env.*
!.env.example
!.env.production.example

backend/.env
frontend/.env
frontend/.env.local

# Backups
*.sql
*.dump
backups/
```

Não remover regras válidas já existentes.

---

# 35. Environment example de desenvolvimento

Preservar:

```text
backend/.env.example
frontend/.env.example
```

como exemplos do ambiente local.

Não transformar os exemplos locais em produção.

---

# 36. Environment example de produção

Criar na raiz:

```text
.env.production.example
```

Esse arquivo é documentação de contrato.

Não contém segredo real.

Exemplo:

```env
DEBUG=False

DOMAIN=corepdv.com
API_DOMAIN=api.corepdv.com

ALLOWED_HOSTS=corepdv.com,api.corepdv.com
CSRF_TRUSTED_ORIGINS=https://corepdv.com,https://*.corepdv.com
CORS_ALLOWED_ORIGINS=https://corepdv.com

TIME_ZONE=America/Sao_Paulo
LANGUAGE_CODE=pt-br

POSTGRES_DB=corepdv
POSTGRES_USER=corepdv
POSTGRES_HOST=db
POSTGRES_PORT=5432

GUNICORN_WORKERS=3
GUNICORN_TIMEOUT=60

NEXT_PUBLIC_API_URL=https://api.corepdv.com/api/v1
```

Secrets devem aparecer apenas como indicação:

```text
SECRET_KEY=<docker-secret>
POSTGRES_PASSWORD=<docker-secret>
```

Nunca com valor real.

---

# 37. Docker Compose de desenvolvimento

O arquivo atual:

```text
docker-compose.yml
```

permanece exclusivamente para desenvolvimento.

Deve continuar tendo:

```text
db
backend
frontend
```

Volumes de source podem continuar existindo nesse ambiente.

Portas locais podem continuar publicadas somente em loopback.

Não utilizar esse arquivo como stack oficial de produção.

---

# 38. Artefato de produção

Criar:

```text
docker-stack.yml
```

Esse arquivo pertence ao projeto, embora sua execução aconteça futuramente na VPS.

Sua função é declarar **como o CORE PDV roda em produção**.

Ele NÃO configura a VPS.

---

# 39. Serviços do docker-stack.yml

O stack contém somente:

```text
db
backend
frontend
```

Não colocar:

```text
Traefik
Nginx
Redis
RabbitMQ
Celery
Portainer
Prometheus
Grafana
```

---

# 40. PostgreSQL de produção

Configurar:

```text
postgres:16-alpine
```

Requisitos:

* volume persistente;
* healthcheck `pg_isready`;
* nenhuma porta publicada;
* password via secret;
* rede interna do projeto.

O banco pertence exclusivamente ao CORE PDV.

---

# 41. Backend no stack

O backend deve receber:

* imagem por variável;
* tag da release;
* configuração não sensível;
* secrets;
* rede interna;
* rede externa do reverse proxy;
* healthcheck;
* restart policy;
* update policy;
* rollback policy.

Não publicar porta `8000` no host.

---

# 42. Frontend no stack

Frontend deve receber:

* imagem por variável;
* tag da release;
* rede externa do reverse proxy;
* healthcheck;
* restart policy;
* update policy;
* rollback policy.

Não publicar porta `3000` no host.

---

# 43. Redes esperadas pelo projeto

O projeto poderá declarar uma rede interna própria, por exemplo:

```text
corepdv_internal
```

Também deverá ser capaz de consumir uma rede externa já existente:

```text
traefik_public
```

IMPORTANTE:

> O projeto apenas declara que depende dessa rede externa.

Criar essa rede pertence ao PRD da VPS.

---

# 44. Integração futura com Traefik

O `docker-stack.yml` poderá conter labels de roteamento para o Traefik porque essas labels fazem parte da definição do serviço.

Hosts previstos:

```text
corepdv.com
api.corepdv.com
```

Porém este projeto NÃO deve:

* instalar Traefik;
* subir Traefik;
* armazenar token Cloudflare;
* criar ACME;
* criar certificado;
* criar rede pública compartilhada.

Ele apenas se conecta à infraestrutura que o próximo PRD criará.

---

# 45. Imagens Docker

Preparar o projeto para possuir duas imagens:

```text
core-pdv-backend
core-pdv-frontend
```

Registry previsto:

```text
GHCR
```

Cada versão de produção deve aceitar tag imutável.

Preferência:

```text
SHA do commit
```

Exemplo conceitual:

```text
backend:abc1234
frontend:abc1234
```

`latest` pode existir como conveniência, mas não deverá ser a única referência disponível para rollback.

---

# 46. Build reproduzível

O mesmo commit deverá produzir uma imagem funcional sem depender:

* de `venv` local;
* de `node_modules` local;
* da pasta `.next` local;
* de arquivos não versionados;
* de software instalado manualmente na VPS.

Isso significa que os artefatos abaixo podem ser apagados localmente:

```text
.venv
venv
node_modules
.next
```

e reconstruídos.

---

# 47. CI — validação do projeto

Criar workflow de CI no repositório.

Arquivo sugerido:

```text
.github/workflows/ci.yml
```

Deve validar pelo menos:

## Backend

```bash
python manage.py check
python manage.py makemigrations --check
```

## Frontend

```bash
npm ci
npm run build
```

## Containers

```text
build da imagem backend
build da imagem frontend
```

O CI não executa deploy nesta etapa.

---

# 48. Branch de desenvolvimento

Fluxo definido:

```text
dev
```

é desenvolvimento.

Push em `dev` poderá executar CI.

Push em `dev` NÃO poderá executar deploy de produção.

---

# 49. Branch de produção

```text
main
```

representa código aprovado para produção.

Neste PRD, deixar o projeto preparado para posteriormente disparar deploy a partir de `main`.

A implementação efetiva da comunicação com a VPS poderá ser finalizada depois que o PRD da VPS definir o contrato exato.

---

# 50. Workflow de build das imagens

É permitido já criar workflow que:

```text
checkout
↓
backend check
↓
frontend build
↓
Docker build backend
↓
Docker build frontend
↓
publicação no GHCR
```

desde que credenciais/endereço da VPS não sejam inventados.

O deploy remoto só deve ser ativado depois da infraestrutura da VPS estar definida.

---

# 51. Não misturar build com servidor

A VPS não deverá ser utilizada para executar:

```text
npm install
npm run build
pip install
docker build
```

como fluxo normal de release.

O projeto deve estar preparado para:

```text
GitHub
↓
build
↓
registry
↓
VPS faz pull
```

---

# 52. Logs

Aplicações devem emitir logs em:

```text
stdout
stderr
```

Não criar sistema complexo de observabilidade nesta etapa.

Garantir que:

* erros Django apareçam nos logs;
* Gunicorn escreva access/error log adequadamente;
* Next.js escreva logs no container;
* secrets não sejam registrados.

---

# 53. Erros de produção

Com:

```text
DEBUG=False
```

a API não pode devolver:

* traceback;
* SQL;
* variáveis de ambiente;
* segredo;
* caminho sensível desnecessário.

Preservar o contrato de erro já existente do CORE PDV.

---

# 54. Dependências

Não atualizar bibliotecas arbitrariamente durante esta sprint.

Atualização de versão só deve ocorrer se necessária para corrigir incompatibilidade de produção.

Preservar atualmente:

```text
Python 3.13
Django 6.1
PostgreSQL 16
Node 22
Next.js 16
React 19
```

Não transformar a sprint de deploy em sprint de atualização de stack.

---

# 55. Banco e dados

Não realizar nesta sprint:

* limpeza automática do banco;
* migração de dados local → produção;
* criação de seed fictício;
* remoção de migrations;
* squash de migrations;
* alteração funcional de models sem necessidade.

Produção começará com banco próprio.

Migração eventual de dados será decisão posterior.

---

# 56. Superusuário

O projeto deve permitir executar normalmente:

```bash
python manage.py createsuperuser
```

dentro do container de produção.

Não criar usuário administrativo com senha hardcoded.

---

# 57. Scripts do projeto

Se necessário, criar:

```text
scripts/
├── check-production.sh
└── smoke-test.sh
```

O objetivo é validar o projeto.

Não criar ainda neste PRD um script que:

* formata a VPS;
* instala pacotes Linux;
* configura firewall;
* instala Traefik;
* cria usuário deploy.

---

# 58. Smoke test do projeto

Preparar validações para posteriormente testar:

Backend:

```text
/health/
```

Frontend:

```text
/
/login
```

Após infraestrutura pronta, deverão resultar conceitualmente em:

```text
https://api.corepdv.com/health/
https://corepdv.com/
https://corepdv.com/login
```

---

# 59. Verificações locais antes de considerar concluído

Executar as verificações tecnicamente possíveis.

## Backend

```bash
python manage.py check
python manage.py makemigrations --check
```

## Frontend

```bash
npm ci
npm run build
```

## Docker desenvolvimento

```bash
docker compose config
docker compose up -d --build
```

Validar:

* banco saudável;
* backend saudável;
* frontend saudável;
* login carregando;
* API acessível.

---

# 60. Teste das imagens de produção

Além do Compose de desenvolvimento, testar localmente as imagens finais de produção.

Validar que o backend realmente executa:

```text
Gunicorn
```

e não:

```text
runserver
```

Validar que o frontend executa build de produção e não:

```text
next dev
```

---

# 61. Verificação de usuário do container

Executar inspeção da imagem/container e confirmar:

```text
backend != root
frontend != root
```

Esse é critério de conclusão.

---

# 62. Verificação de segredo

Construir imagens e inspecionar para garantir que não contenham:

```text
backend/.env
frontend/.env.local
senhas
SECRET_KEY real
token Cloudflare
chave SSH
```

---

# 63. Arquivos obrigatórios ao final

A implementação deve deixar pelo menos:

```text
PDV-25LOUNGE/
├── .gitignore
├── .env.production.example
├── docker-compose.yml
├── docker-stack.yml
│
├── backend/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── entrypoint.sh
│   ├── requirements.txt
│   └── core/
│       └── settings.py
│
├── frontend/
│   ├── Dockerfile
│   ├── .dockerignore
│   └── next.config.ts
│
├── scripts/
│   └── smoke-test.sh
│
└── .github/
    └── workflows/
        └── ci.yml
```

Arquivos adicionais podem ser criados quando tecnicamente justificados.

---

# 64. O que NÃO criar

Não criar nesta etapa:

```text
nginx.conf
docker-compose.traefik.yml
traefik.yml
acme.json
cloudflare.env
install-docker.sh
setup-vps.sh
fail2ban config
UFW config
SSH config
Portainer
Redis
RabbitMQ
Celery
Kubernetes
Helm
```

---

# 65. Sprint 13.1 — Diagnóstico e proteção

* [x] Ler este PRD integralmente antes de alterar arquivos.
* [x] Executar `git status`.
* [x] Registrar estado atual.
* [x] Não descartar modificações existentes.
* [x] Validar `.gitignore`.
* [x] Confirmar ausência de secrets versionados.
* [x] Executar baseline de backend.
* [x] Executar baseline de frontend.
* [x] Registrar problemas existentes antes da alteração.

Diagnóstico reproduzível registrado em `docs/production-readiness.md` antes das
alterações de runtime. O baseline confirmou os três serviços locais saudáveis,
checks Django e migrations sem erros, build das 44 rotas do frontend e ausência
de secrets reais versionados.

---

# 66. Sprint 13.2 — Backend production-ready

* [x] Refatorar `backend/Dockerfile`.
* [x] Remover `runserver` do runtime de produção.
* [x] Configurar Gunicorn.
* [x] Criar usuário não-root.
* [x] Preservar espera pelo PostgreSQL.
* [x] Revisar migrations no entrypoint.
* [x] Implementar suporte seguro a Docker Secrets.
* [x] Configurar static files.
* [x] Validar Django Admin static quando aplicável.
* [x] Revisar healthcheck.
* [x] Executar `manage.py check`.
* [x] Executar `makemigrations --check`.

### Critério de aceite

Uma imagem Docker limpa deve conseguir iniciar o backend com:

```text
DEBUG=False
Gunicorn
PostgreSQL
```

sem arquivos locais de desenvolvimento.

Validado em imagem limpa com `DEBUG=False`, Gunicorn 26, PostgreSQL, usuário
`corepdv` (UID 999), healthcheck saudável e Admin static servido pelo
WhiteNoise. A leitura por `SECRET_KEY_FILE` e `POSTGRES_PASSWORD_FILE` foi
verificada com arquivos efêmeros montados somente para o smoke test. O Compose
de desenvolvimento mantém `runserver` por override explícito.

---

# 67. Sprint 13.3 — Segurança Django

* [x] Revisar `SECRET_KEY`.
* [x] Revisar `ALLOWED_HOSTS`.
* [x] Revisar `CSRF_TRUSTED_ORIGINS`.
* [x] Revisar `CORS_ALLOWED_ORIGINS`.
* [x] Configurar `SECURE_PROXY_SSL_HEADER`.
* [x] Configurar `SECURE_SSL_REDIRECT`.
* [x] Configurar cookies secure.
* [x] Configurar HSTS por environment.
* [x] Configurar `SECURE_CONTENT_TYPE_NOSNIFF`.
* [x] Garantir comportamento diferente entre dev e produção.

### Critério de aceite

Com `DEBUG=False`, o projeto deve passar em:

```bash
python manage.py check --deploy
```

Analisar cada warning e corrigir ou documentar tecnicamente qualquer exceção intencional.

`check --deploy --fail-level WARNING` passou sem issues com HSTS progressivo
habilitado (`SECURE_HSTS_SECONDS=300`, include-subdomains e preload). Para o
primeiro deploy, o contrato mantém HSTS em `0` até HTTPS ser validado; nesse
estado, somente `security.W004` é uma exceção temporária e intencional. Dev
permanece em HTTP e não confia em headers de
proxy; produção confia apenas porque a porta do backend não será publicada e o
acesso ocorrerá pela rede controlada do reverse proxy.

---

# 68. Sprint 13.4 — Frontend production-ready

* [x] Refatorar Dockerfile para multi-stage.
* [x] Utilizar `npm ci`.
* [x] Executar `npm run build`.
* [x] Utilizar Next standalone.
* [x] Não executar `npm run dev`.
* [x] Criar usuário não-root.
* [x] Configurar build argument `NEXT_PUBLIC_API_URL`.
* [x] Criar healthcheck adequado.
* [x] Reduzir conteúdo da imagem final.
* [x] Validar runtime em porta 3000.

### Critério de aceite

Imagem limpa deve executar o frontend sem:

```text
node_modules local
.next local
source mount
npm run dev
```

Imagem limpa validada com `NEXT_PUBLIC_API_URL=https://api.corepdv.com/api/v1`,
44 rotas, output standalone de aproximadamente 82 MB, processo `node server.js`
como UID 1000 e healthcheck saudável em `/login`. O build rejeita URL ausente ou
de loopback. O target separado `development` preserva `next dev` somente no
Compose local, que foi reconstruído e permaneceu saudável.

---

# 69. Sprint 13.5 — Ambientes e higiene do repositório

* [x] Atualizar `.gitignore`.
* [x] Garantir `.venv` ignorada.
* [x] Garantir `node_modules` ignorado.
* [x] Garantir `.next` ignorado.
* [x] Garantir `.env` real ignorado.
* [x] Revisar `.dockerignore` backend.
* [x] Revisar `.dockerignore` frontend.
* [x] Criar `.env.production.example`.
* [x] Preservar exemplos de desenvolvimento.
* [x] Garantir ausência de segredo em imagens.

Regras de ignore e contextos Docker foram verificadas com `git check-ignore` e
inspeção das imagens. Os únicos arquivos de ambiente versionáveis são contratos
de exemplo; `.env.production.example` usa referências a secrets externos, sem
valores reais. `backend/.env.example` e `frontend/.env.example` permanecem
dedicados ao desenvolvimento. Scripts shell são normalizados para LF.

---

# 70. Sprint 13.6 — Stack de produção do projeto

* [x] Criar `docker-stack.yml`.
* [x] Declarar `db`.
* [x] Declarar `backend`.
* [x] Declarar `frontend`.
* [x] Criar volume persistente PostgreSQL.
* [x] Criar rede interna.
* [x] Declarar dependência da rede externa do proxy.
* [x] Não criar o proxy.
* [x] Não publicar PostgreSQL.
* [x] Não publicar portas backend/frontend diretamente.
* [x] Configurar healthchecks.
* [x] Configurar restart policies.
* [x] Configurar update policies.
* [x] Configurar rollback policies.
* [x] Preparar uso de secrets.
* [x] Preparar tag imutável de imagens.

### Critério de aceite

O arquivo deve poder ser validado sem efetivamente possuir a VPS pronta.

Validado localmente com `docker stack config` e `docker compose config`, usando
uma tag SHA de teste. O stack contém exatamente os três serviços, não publica
portas e apenas declara a rede externa `traefik_public` e os secrets externos.
Enquanto `MIGRATE_ON_START=True`, o backend permanece com uma réplica e update
`stop-first`; múltiplas réplicas exigirão migration única de release.

Toda dependência externa deve estar documentada.

---

# 71. Sprint 13.7 — CI

* [x] Criar `.github/workflows/ci.yml`.
* [x] Executar backend check.
* [x] Executar migration check.
* [x] Executar frontend build.
* [x] Executar Docker build backend.
* [x] Executar Docker build frontend.
* [x] Configurar execução em `dev`.
* [x] Configurar execução em pull request para `main`.
* [x] Push em `dev` não pode executar deploy.

Workflow reutilizável criado e validado sintaticamente. Os mesmos checks e
builds foram executados localmente; no GitHub, os jobs rodam em push para `dev`
e pull request para `main`, com permissão somente de leitura. Não há etapa de
login, publicação, SSH ou deploy na CI.

Revalidação de entrega: `ci.yml` e `ghcr.yml` existem em `.github/workflows/`,
não são ignorados e passaram em `yaml-lint` e `actionlint`. A divergência da
entrega anterior ocorreu porque o diretório `.github/` permaneceu não rastreado
no working tree do commit `50d36a4`; os dois arquivos devem obrigatoriamente ser
incluídos no mesmo commit dos demais artefatos deste PRD.

---

# 72. Sprint 13.8 — Build/Registry

* [x] Preparar build das duas imagens.
* [x] Preparar autenticação GHCR.
* [x] Utilizar commit SHA como tag.
* [x] Permitir `latest` adicional sem depender dele.
* [x] Passar `NEXT_PUBLIC_API_URL` correto durante build frontend.
* [x] Não incluir secrets nas layers.
* [x] Documentar nomes finais das imagens.

Esta sprint prepara artefatos.

Não executar conexão SSH/deploy na VPS antes do PRD de infraestrutura estar fechado.

`.github/workflows/ghcr.yml` publica, após a CI, as imagens
`ghcr.io/maxforcedev/core-pdv-backend` e
`ghcr.io/maxforcedev/core-pdv-frontend`. Cada build recebe a tag do SHA completo;
`latest` é apenas adicional. Somente a URL pública da API é build arg. O workflow
usa `GITHUB_TOKEN`, não recebe secrets de aplicação e não contém deploy remoto.

---

# 73. Sprint 13.9 — Validação final local

* [x] Recriar backend do zero.
* [x] Recriar frontend do zero.
* [x] Não utilizar `.venv`.
* [x] Não utilizar `node_modules` local.
* [x] Não utilizar `.next` local.
* [x] Build backend concluído.
* [x] Build frontend concluído.
* [x] Backend executa Gunicorn.
* [x] Frontend executa produção.
* [x] Backend não roda como root.
* [x] Frontend não roda como root.
* [x] PostgreSQL persiste.
* [x] `/health/` funciona.
* [x] login abre.
* [x] comunicação frontend/backend funciona.
* [x] desenvolvimento local continua funcional.

As imagens foram reconstruídas duas vezes sem cache após as revisões finais,
usando contextos de aproximadamente 12 KB (backend) e 9 KB (frontend). Smokes
confirmaram Gunicorn/UID 999, Next Standalone/UID 1000, secrets por arquivo,
static files, healthchecks, CORS/CSRF e API pública no bundle. Um registro de
prova sobreviveu à recriação do container PostgreSQL e foi removido em seguida.
O Compose completo foi recomposto, os três serviços ficaram saudáveis e
`scripts/smoke-test.sh` passou em `/health/`, `/` e `/login`.

---

# 74. Gate final

O OpenCode NÃO pode declarar esta etapa concluída enquanto qualquer item abaixo falhar:

* [x] `docker compose` de desenvolvimento continua funcional.
* [x] backend de produção não usa `runserver`.
* [x] frontend de produção não usa `next dev`.
* [x] Gunicorn funciona.
* [x] Next standalone funciona.
* [x] `DEBUG=False` funciona.
* [x] `manage.py check --deploy` foi analisado.
* [x] static files funcionam.
* [x] healthcheck funciona.
* [x] containers de aplicação não rodam como root.
* [x] `.env` não entra nas imagens.
* [x] `.venv` não entra no Git.
* [x] `node_modules` não entra no Git/imagem final.
* [x] `.next` local não entra no Git/imagem de build.
* [x] production environment está documentado.
* [x] `docker-stack.yml` existe.
* [x] PostgreSQL não publica porta.
* [x] projeto não contém Traefik próprio.
* [x] projeto não contém Nginx próprio.
* [x] projeto não contém Redis/Celery/RabbitMQ.
* [x] CI valida `dev`.
* [x] nenhuma alteração funcional existente foi descartada.

Gate revisado após code review adicional. Bases e Actions foram fixadas por
digest/commit, o workflow GHCR não sobrescreve tag SHA e o target backend de
desenvolvimento preserva escrita em bind mounts Linux. A confiança em headers
encaminhados continua explicitamente condicionada ao isolamento da rede externa
e à sanitização pelo proxy, responsabilidade documentada para a VPS.

---

# 75. Entrega final obrigatória do OpenCode

Ao finalizar, responder com relatório contendo:

## Arquivos modificados

Lista completa.

## Arquivos criados

Lista completa.

## Decisões tomadas

Explicar decisões importantes, especialmente:

```text
Gunicorn
Next standalone
static files
Docker Secrets
migrations
Docker stack
```

## Verificações executadas

Informar resultado de:

```text
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check
npm run build
Docker build backend
Docker build frontend
docker compose config
```

## Pendências

Separar claramente:

```text
PENDÊNCIAS DO PROJETO
```

de:

```text
PENDÊNCIAS DA VPS
```

Não tentar resolver itens da VPS nesta sprint.

---

# 76. Definition of Done

Esta etapa termina quando o repositório passa a possuir tudo que precisa para ser levado a um ambiente de produção sem editar código diretamente no servidor.

O resultado esperado é:

```text
CORE PDV REPOSITÓRIO
│
├── Desenvolvimento
│   └── docker-compose.yml
│       ├── PostgreSQL
│       ├── Django runserver
│       └── Next dev
│
└── Produção
    ├── Backend image
    │   └── Django + Gunicorn
    │
    ├── Frontend image
    │   └── Next standalone
    │
    ├── PostgreSQL 16
    │
    ├── docker-stack.yml
    │
    ├── healthchecks
    │
    ├── secrets-ready
    │
    └── environment-ready
```

Depois que ESTE PRD estiver concluído:

> o próximo trabalho será exclusivamente preparar a VPS para receber projetos nesse padrão.

Esse próximo PRD deve cuidar da infraestrutura universal:

```text
Ubuntu
Docker
Swarm
usuário deploy
segurança
firewall
Traefik central
Cloudflare
Let's Encrypt
estrutura /opt
rede traefik_public
GHCR
backups/base operacional
```

sem voltar a modificar a arquitetura funcional do CORE PDV.
