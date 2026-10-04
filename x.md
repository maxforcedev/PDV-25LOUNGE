CORRIGIR OS BLOQUEIOS DA EXECUÇÃO GITHUB ACTIONS #188 PARA LIBERAR A PUBLICAÇÃO DAS IMAGENS DE PRODUÇÃO.

HEAD analisado:

`bb68f71717150531b28cb16f538226bc2a4b4105`

Workflow:

`Publish production images`

Run:

`#188`

Os três jobs de validação falharam SOMENTE no audit de dependências.

NÃO alterar regras do workflow para ignorar vulnerabilidades.

NÃO remover `pip-audit`.

NÃO remover `npm audit`.

NÃO usar `continue-on-error`.

Precisamos corrigir as dependências vulneráveis.

==================================================
1. BACKEND — DJANGO
==================================================

Arquivo:

`backend/requirements.txt`

Hoje:

```text
Django==6.1
```

O `pip-audit` reportou:

```text
django 6.1
CVE-2026-15830
Fix: 6.1.1
```

Atualizar para:

```text
Django==6.1.1
```

Não alterar versão principal.

Continuamos em Django 6.1.x.

==================================================
2. BACKEND — PYPDF
==================================================

Hoje:

```text
pypdf==6.16.2
```

O audit encontrou 8 advisories:

```text
PYSEC-2026-4153
PYSEC-2026-4154
PYSEC-2026-4160
PYSEC-2026-4159
PYSEC-2026-4156
PYSEC-2026-4155
PYSEC-2026-4158
PYSEC-2026-4157
```

As versões de correção chegam até:

```text
6.19.0
```

Portanto atualizar para:

```text
pypdf==6.19.0
```

Não alterar lógica de PDFs do CORE.

Somente atualizar a dependência.

==================================================
3. FRONTEND — NEXT.JS
==================================================

Arquivo:

`frontend/package.json`

Hoje:

```json
"next": "16.3.4"
```

O GitHub Actions encontrou vulnerabilidade CRITICAL:

```text
Next.js: Remote Code Execution in next/og ImageResponse
GHSA-vcvr-r3jv-pc5j
```

Faixa vulnerável reportada:

```text
16.2.0 - 16.3.5
```

O próprio audit aponta:

```text
next@16.3.8
```

Atualizar:

```json
"next": "16.3.8"
```

Atualizar também:

`frontend/package-lock.json`

para refletir exatamente essa versão.

Revisar se vale alinhar:

```text
eslint-config-next
```

com a versão 16.3.8 para manter compatibilidade com o Next usado pelo projeto.

Não fazer alterações funcionais no frontend.

==================================================
4. PLATFORM ADMIN — NEXT.JS
==================================================

Arquivo:

`platform-admin/package.json`

Hoje:

```json
"next": "16.3.4"
```

É a mesma vulnerabilidade CRITICAL.

Atualizar para:

```json
"next": "16.3.8"
```

Atualizar também:

`platform-admin/package-lock.json`.

Alinhar `eslint-config-next` se necessário para manter o conjunto Next consistente.

Não alterar funcionalidades do Platform Admin.

==================================================
5. NÃO MASCARAR O CI
==================================================

Manter exatamente a intenção atual de:

```text
python -m pip_audit -r requirements.txt
```

e:

```text
npm audit --omit=dev --audit-level=high
```

Eles estão fazendo o papel correto de impedir deploy com vulnerabilidade crítica.

Não alterar:

`.github/workflows/ci.yml`

só para a pipeline ficar verde.

Não diminuir `audit-level`.

Não adicionar exceção para esses advisories.

==================================================
6. NÃO MEXER NO RESTANTE
==================================================

Não aproveitar esta correção para refatorar:

- Cielo;
- pagamentos;
- PIX;
- estorno;
- cancelamento de venda;
- Mesa;
- Comanda;
- impressão;
- estoque;
- autenticação;
- Docker;
- workflow de deploy.

Essa missão é exclusivamente para corrigir as dependências que bloqueiam a publicação das imagens.

==================================================
7. SOBRE OS WARNINGS
==================================================

O frontend apresentou:

```text
61 problems
0 errors
61 warnings
```

O lint passou.

Não fazer limpeza geral desses warnings nesta missão.

Também existe aviso do GitHub:

```text
Node.js 20 is deprecated
```

relacionado às próprias GitHub Actions.

Isso NÃO foi o causador da falha #188.

Não misturar essa atualização agora.

==================================================
RESULTADO ESPERADO
==================================================

Backend:

```text
Django 6.1.1
pypdf 6.19.0
```

Frontend:

```text
Next 16.3.8
```

Platform Admin:

```text
Next 16.3.8
```

Lockfiles atualizados corretamente.

Depois do push, deixar o GitHub Actions validar novamente e seguir para os próximos estágios:

```text
Django checks
migrations
frontend build
platform-admin build
production container builds
publish GHCR
```

Não fazer commit.
Não rodar testes.