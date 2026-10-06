Use o **estado atual do GitHub como fonte da verdade**.

HEAD funcional validado:

```text
aed9f43c4809459a457ea49c2e9fc216247046d4
```

A parte crítica de SaaS/capabilities já foi corrigida e o CI ficou verde.

NÃO refaça essa arquitetura.

Agora vamos fechar somente as pendências que ficaram da missão inicial.

IMPORTANTE:

**NÃO RODE TESTES.  
NÃO RODE BUILD.  
NÃO RODE LINT.  
NÃO RODE npm ci/install/audit.  
NÃO RODE suíte Django.  
NÃO RODE Flutter.**

Faça por análise estática e implementação.

Pode criar migration necessária, mas **não execute migrations localmente**.

Ao final:
- commit;
- push;
- informe SHA;
- liste alterações;
- não faça deploy;
- não mexa na VPS.

---

# 1. BRANDING DO CORE: PARAR DE USAR URL E PASSAR A USAR ANEXO

Hoje `GlobalSaaSSettings` ainda possui campos como:

```python
logo_url
compact_logo_url
favicon_url
logo_light_url
logo_dark_url
compact_logo_light_url
compact_logo_dark_url
```

e a Platform Admin pede URLs.

Isso NÃO é o comportamento desejado.

## Regra desejada

O sistema deve possuir os assets oficiais do CORE já dentro do frontend como fallback.

Devem existir versões padrão para:

- logo em fundo claro;
- logo em fundo escuro;
- logo compacta;
- logo compacta clara/escura se necessário;
- favicon oficial.

Fluxo:

```text
Nenhum asset customizado pela API
→ frontend usa asset oficial embarcado no projeto

Asset enviado pela Platform Admin
→ backend armazena o arquivo
→ API passa a devolver o asset atual
→ frontend usa automaticamente o override

Asset removido
→ frontend volta para o asset oficial local
```

NÃO depender de URL externa.

## Platform Admin

Trocar campos de URL por upload/anexo.

Quero algo como:

```text
Logo para fundo claro
[ selecionar arquivo ]

Logo para fundo escuro
[ selecionar arquivo ]

Logo compacta
[ selecionar arquivo ]

Favicon
[ selecionar arquivo ]
```

Mostrar preview do arquivo atual.

Permitir substituir/remover.

Aceitar formatos adequados, como:

```text
PNG
WEBP
SVG se nossa política de upload permitir de forma segura
ICO para favicon se necessário
```

Definir tamanho máximo razoável.

Não permitir upload arbitrário inseguro.

## Backend

Implementar armazenamento interno usando o padrão de media/private media já existente no projeto, sem inventar serviço externo.

Pode manter campos URL antigos temporariamente como legado de compatibilidade se necessário para migration segura, mas:

- eles não devem mais aparecer na UI;
- novos uploads não devem depender deles;
- novo comportamento deve priorizar arquivos internos.

API pública de branding deve devolver URL interna segura/resolvida do arquivo quando existir.

Preservar fallback local do frontend.

---

# 2. FAVICON DINÂMICO COM FALLBACK LOCAL

Mesmo conceito da logo.

O frontend deve possuir o favicon oficial do CORE dentro do próprio projeto.

Sem customização:

```text
favicon oficial local
```

Com favicon enviado pelo Platform Admin:

```text
favicon customizado da API
```

Se removido ou indisponível:

```text
fallback local novamente
```

Não deixar o carregamento da aplicação dependente da API para possuir favicon básico.

---

# 3. LINKS INSTITUCIONAIS: REMOVER JSON DA INTERFACE

Hoje existe na Platform Admin:

```text
Links institucionais (JSON)
```

com textarea semelhante a:

```json
{
  "termos": "...",
  "privacidade": "..."
}
```

Isso NÃO deve aparecer dessa forma para usuário administrativo.

Trocar por campos normais da interface.

Exemplo:

```text
Termos de Uso
[________________]

Política de Privacidade
[________________]

Site institucional
[________________]

Central de Ajuda / Suporte
[________________]
```

Se outros links institucionais já forem realmente usados pelo sistema, criar campos próprios também.

O backend pode internamente continuar utilizando estrutura organizada/JSON se isso for útil e compatível.

A exigência é:

```text
USUÁRIO NÃO EDITA JSON
```

Validar URL individualmente.

---

# 4. PLANO: NÃO EXIGIR CÓDIGO TÉCNICO MANUAL

Hoje o código já é gerado automaticamente pelo nome, porém a tela ainda apresenta:

```text
Código técnico (avançado)
```

como input obrigatório.

Melhorar a UX.

Na criação:

```text
Nome: CORE Pro
→ code automaticamente = core-pro
```

O usuário não deve precisar digitar código.

Pode:

- ocultar completamente na criação; ou
- mostrar como somente leitura/preview em área avançada.

O backend deve continuar sendo autoridade:

```python
slugify(code or name)
```

Depois que o plano já estiver sendo utilizado, preservar a proteção atual:

```text
code imutável
```

Não remover essa proteção.

---

# 5. PREÇOS POR FILIAL SOMENTE QUANDO EXISTIREM 2+ FILIAIS

Hoje, em Produtos, o botão:

```text
Preços por filial
```

aparece mesmo com somente uma filial.

Corrigir.

## Regra

Empresa com 1 filial ativa:

```text
não mostrar botão "Preços por filial"
não mostrar ações de preço multi-filial
rota /produtos/precos não deve operar como se houvesse cenário multi-filial
```

Empresa com 2+ filiais ativas:

```text
mostrar normalmente
```

A página `/produtos/precos` também deve se proteger.

Caso alguém acesse a URL diretamente com somente uma filial, apresentar estado adequado, por exemplo:

```text
Preços por filial ficam disponíveis quando a empresa possuir mais de uma filial ativa.
```

ou redirecionar de forma limpa para Produtos.

Não retornar erro 500.

Usar somente filiais ativas da empresa atual.

---

# 6. FOTO DO PRODUTO POR ANEXO

Hoje:

```python
Product.image = models.URLField(...)
```

e o frontend trabalha com:

```ts
image: string
```

Isso precisa mudar.

Quero foto de produto por arquivo/anexo.

## Fluxo

No cadastro/edição do produto:

```text
Foto do produto
[ selecionar imagem ]

preview
substituir
remover
```

Nada de pedir URL.

Backend deve armazenar internamente.

Usar padrão seguro de media do CORE.

Validar:

- formato de imagem permitido;
- limite de tamanho;
- nome/path seguro.

API deve devolver uma URL interna/resolvida para o frontend exibir.

## Compatibilidade

Não quebrar produtos existentes que eventualmente tenham valor antigo em `image`.

Se necessário:

- adicionar novo campo para arquivo;
- manter `image` legado temporariamente;
- preferir sempre o arquivo novo;
- deixar estrutura pronta para remoção futura do legado.

Não fazer migration destrutiva.

---

# 7. LEADS DO SITE DENTRO DA PLATFORM ADMIN

Hoje o formulário público envia para:

```text
POST /api/v1/public/leads/
```

e cria:

```python
CommercialLead
```

com informações como:

- nome;
- empresa;
- WhatsApp;
- e-mail;
- segmento;
- mensagem;
- plano de interesse;
- source_path;
- UTM source;
- UTM medium;
- UTM campaign;
- status.

Isso já deve continuar funcionando.

O problema é que NÃO existe uma tela na Platform Admin para visualizar esses leads.

Criar módulo/tela:

```text
Platform Admin
→ Leads
```

## Lista

Mostrar:

```text
Nome
Empresa
WhatsApp
E-mail
Segmento
Plano de interesse
Origem
Data
Status
```

Filtros:

```text
status
busca por nome/empresa/e-mail/WhatsApp
```

Status existentes:

```text
NEW
CONTACTED
QUALIFIED
CONVERTED
LOST
```

Usar labels amigáveis:

```text
Novo
Contatado
Qualificado
Convertido
Perdido
```

## Detalhe

Ao abrir lead:

- dados completos;
- mensagem;
- UTMs;
- página de origem;
- data;
- plano de interesse;
- status.

Permitir alterar status.

Auditar alteração de status.

## Permissão

Criar permission de Platform Admin adequada, preferencialmente:

```text
platform.leads.manage
```

Adicionar ao papel `super-admin` no bootstrap.

Não misturar isso com RBAC de tenant.

---

# 8. ENFORCEMENT SaaS: ALINHAR COM O COMPORTAMENTO REAL

Hoje existe uma inconsistência conceitual.

A Platform Admin diz algo equivalente a:

```text
Enforcement SaaS desabilitado
→ runtime ainda não bloqueia tenants por estado SaaS
```

Porém o runtime atual já usa:

```python
resolve_effective_status()
active_operational_companies()
active_operational_branches()
```

inclusive no login.

Ou seja:

```text
tenant sem assinatura
tenant vencido
trial expirado
assinatura inválida
```

já pode ser bloqueado independentemente da descrição atual da tela.

## Regra de produto definitiva

O CORE deve ser **FAIL CLOSED SEMPRE**.

Não quero:

```text
enforcement_enabled=False
→ empresa sem plano consegue operar
```

A segurança SaaS NÃO deve depender desse toggle.

Portanto:

### Auditar usos de `enforcement_enabled`

Qualquer código que atualmente permita operação sem plano somente porque:

```python
enforcement_enabled == False
```

deve ser revisto.

Exemplo já identificado:

```python
assert_resource_limit()
```

não deve simplesmente liberar tenant sem assinatura porque o cutover está desligado.

Regra:

```text
empresa sem assinatura corrente válida
→ não opera
```

independentemente do flag.

### Reinterpretar o botão

`enforcement_enabled` pode continuar existindo como:

```text
marco de cutover da base legada / validação de migração / auditoria
```

mas NÃO como chave de segurança que liga/desliga o SaaS.

Alterar o texto da Platform Admin para deixar isso claro.

Não mostrar mais algo como:

```text
"O runtime ainda não bloqueia tenants por estado SaaS"
```

se isso não for verdade.

Pode renomear visualmente para algo como:

```text
Cutover SaaS
Validação da base legada
```

Mantendo o evento auditável e irreversível, se isso ainda tiver utilidade arquitetural.

NÃO enfraquecer nenhum bloqueio atual.

---

# 9. CORS LOCAL DA PLATFORM ADMIN

No ambiente local descobrimos que:

```text
Platform Admin = localhost:3001
```

estava presente em `CSRF_TRUSTED_ORIGINS`, mas ausente de:

```text
CORS_ALLOWED_ORIGINS
```

A alteração local que funcionou foi incluir:

```text
http://localhost:${PLATFORM_ADMIN_PORT:-3001}
http://127.0.0.1:${PLATFORM_ADMIN_PORT:-3001}
```

em `CORS_ALLOWED_ORIGINS`.

Verifique o estado atual do arquivo.

Se essa correção ainda não estiver no GitHub, inclua-a no commit.

Não duplicar caso já esteja presente.

---

# 10. NÃO REGREDIR O QUE JÁ FOI CORRIGIDO

Preservar integralmente:

- Plan → Subscription → Capabilities;
- fail-closed;
- login SaaS;
- expiração imediata;
- PAST_DUE;
- multiempresa;
- Owner existente;
- ACTIVE por padrão em criação manual;
- Trial explícito;
- PlanVersion;
- proteção do código de plano depois de utilizado;
- limits;
- POS capability;
- reports capability;
- dashboard capability;
- products;
- inventory;
- purchases;
- suppliers;
- customers;
- promotions;
- financial;
- audit;
- Mesas;
- Comandas;
- Balcão;
- Consumação;
- Produção;
- RBAC;
- pagamentos;
- Cielo;
- Stone;
- PagBank;
- impressão;
- motor financeiro;
- motor de estoque;
- arquitetura de vendas.

NÃO redesenhar Mesas/Comandas.

---

# 11. MIGRATIONS

Essa missão provavelmente exigirá migration por causa de:

- assets de branding;
- favicon;
- foto de produto.

Faça migration segura e compatível.

NÃO apagar dados existentes.

NÃO depender de banco zerado para a migration funcionar.

Se mantiver campos antigos como legado, documente claramente no código qual é o campo novo prioritário.

Não execute a migration local.

---

# 12. SEM VALIDAÇÃO LOCAL PESADA

Reforçando:

NÃO executar:

```text
python manage.py test
python manage.py check
python manage.py migrate
python manage.py makemigrations
npm test
npm run lint
npm run build
npm ci
npm install
npm audit
flutter test
flutter build
```

Se migration for necessária, escreva o arquivo de migration manualmente e de forma coerente com os models.

Faça somente análise estática.

---

# ENTREGA

Ao terminar:

1. faça commit;
2. faça push;
3. informe SHA;
4. liste arquivos alterados;
5. informe migrations criadas;
6. explique objetivamente:

```text
- como funciona o fallback local de logo/favicon;
- como funciona o upload de branding;
- como os links institucionais deixaram de usar JSON na UI;
- como o código do plano passou a ser automático;
- como "Preços por filial" foi limitado a 2+ filiais;
- como funciona upload da foto do produto;
- onde os Leads aparecem na Platform Admin;
- como ficou a semântica definitiva de Enforcement SaaS;
- se o CORS da porta 3001 entrou no GitHub.
```

NÃO faça deploy.
NÃO mexa na VPS.
NÃO execute testes/builds locais.