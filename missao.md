# CORE PLATFORM ADMIN — MVP FUNCIONAL

**Projeto:** CORE PDV  
**Produto:** CORE Platform Admin  
**Objetivo:** deixar o painel administrativo da CORE simples, confiável e suficiente para administrar os primeiros clientes sem depender de banco, shell ou Django Admin.

> Este documento é a fonte de verdade do **MVP do Platform Admin**.
>
> O OpenCode deve implementar somente o necessário para tornar o painel funcional para os primeiros clientes.
>
> Não adicionar funcionalidades avançadas que não estejam neste documento.
>
> Prioridade:
>
> 1. corrigir o que já existe;
> 2. tornar os fluxos principais confiáveis;
> 3. permitir administrar clientes, planos, módulos, assinaturas e cobrança;
> 4. manter auditoria mínima;
> 5. parar quando o MVP estiver funcional.

---

# 1. OBJETIVO DO MVP

O critério principal é:

> **Se amanhã entrarem 10 clientes pagando, eu consigo administrar todos pelo Platform Admin sem abrir o banco e sem usar Django Admin?**

Se a resposta for sim, o MVP está pronto.

---

# 2. O QUE O PLATFORM ADMIN MVP PRECISA FAZER

O MVP deve permitir:

- login seguro;
- visualizar o estado geral do SaaS;
- listar clientes;
- criar cliente manualmente;
- abrir detalhes de um cliente;
- aprovar/rejeitar cadastro;
- visualizar Owner;
- transferir Owner;
- visualizar filiais;
- visualizar usuários;
- suspender/reativar tenant;
- arquivar tenant;
- criar planos;
- criar versões de plano;
- definir preço;
- definir trial;
- selecionar módulos do plano;
- definir limites básicos;
- atribuir plano a cliente;
- trocar plano;
- definir billing mode;
- registrar pagamento manual;
- visualizar pagamentos;
- identificar inadimplência;
- restringir/suspender financeiramente;
- reativar após regularização;
- configurar dados básicos da plataforma;
- usar Support Session existente;
- consultar auditoria básica.

---

# 3. O QUE NÃO ENTRA AGORA

Não implementar neste MVP:

```text
CRM
Leads
Pipeline comercial
Health Score
Churn Risk
Acompanhamento crítico
Automações
Campaigns
Notification Hub
Feature Flags avançadas
Rollout percentual
Kill Switch avançado
Inventário global de Devices
Integrações globais
Equipe CORE complexa
Papéis customizados avançados
Add-ons comerciais
Overage
Overrides complexos
Analytics SaaS avançado
Status Page
Observabilidade avançada
LGPD workflow completo
Break Glass
Bulk Actions
Sandbox
```

Esses recursos podem vir depois conforme a base de clientes crescer.

---

# 4. MENU DO PLATFORM ADMIN MVP

```text
CORE PLATFORM

Dashboard

CLIENTES
├── Clientes
└── Assinaturas

PRODUTO
├── Planos
└── Módulos

FINANCEIRO
└── Cobrança

OPERAÇÃO
├── Suporte
└── Auditoria

SISTEMA
└── Configurações
```

---

# 5. DASHBOARD

O dashboard deve ser simples.

## Cards principais

```text
Clientes totais
Clientes ativos
Trials ativos
Inadimplentes
Suspensos
MRR
Novos clientes no mês
```

Não criar gráficos complexos agora.

---

# 6. CLIENTES / TENANTS

Tela principal:

```text
Clientes
```

## Lista

Colunas:

```text
Cliente
CNPJ
Owner
Plano
Billing mode
Status
Filiais
Usuários
Criado em
```

## Busca

Pesquisar por:

```text
Nome fantasia
Razão social
CNPJ
E-mail
Owner
ID
```

## Filtros

```text
Ativo
Trial
Inadimplente
Restrito
Suspenso
Arquivado
FREE
PAID
INTERNAL
Plano
```

---

# 7. CRIAR CLIENTE

A equipe CORE deve poder criar um tenant manualmente.

## Campos mínimos

```text
Nome fantasia
Razão social
CNPJ
E-mail
Telefone

Owner
- Nome
- E-mail

Plano
Billing mode
Trial quando aplicável
```

## Ao criar

O backend deve criar automaticamente:

```text
Company
Filial principal
Owner
Membership do Owner
Subscription
TenantSaaSState
```

Tudo deve ocorrer de forma transacional.

Não deixar tenant parcialmente criado.

---

# 8. TENANT 360 — MVP

A rota atual pode continuar:

```text
/tenants/{id}
```

O Tenant 360 do MVP terá apenas:

```text
Visão geral
Assinatura
Filiais
Usuários
Pagamentos
Suporte
Auditoria
```

---

# 9. TENANT 360 — VISÃO GERAL

Mostrar:

```text
Nome fantasia
Razão social
CNPJ
Tenant ID
Owner
E-mail
Telefone

Status efetivo
Operação liberada/bloqueada

Plano atual
Billing mode
Trial
Renovação
MRR

Quantidade de filiais
Quantidade de usuários
```

## Ações

```text
Aprovar
Rejeitar
Suspender administrativamente
Reativar
Transferir Owner
Arquivar
```

Ações críticas exigem:

```text
Motivo
+
Reautenticação
+
Auditoria
```

---

# 10. OWNER

O Owner é especial.

Regras:

- tenant deve possuir Owner;
- Owner não pode ser removido acidentalmente;
- transferência precisa ser atômica;
- novo Owner deve pertencer à empresa ou ser criado pelo fluxo correto;
- transferência exige motivo;
- auditoria obrigatória.

---

# 11. FILIAIS

No Tenant 360:

```text
Nome
CNPJ
Matriz?
Status
Usuários
```

O Platform Admin não precisa duplicar toda a tela operacional do Backoffice.

Objetivo aqui é visão administrativa.

---

# 12. USUÁRIOS

No Tenant 360:

```text
Nome
E-mail
Status
Owner?
Perfil
Filiais
```

O Platform Admin não deve virar o painel normal de gestão de usuários do cliente.

É apenas visão e ações administrativas críticas quando necessário.

---

# 13. PLANOS

O modelo comercial continua:

```text
Plan
→ PlanVersion
```

## Plan

Representa o nome comercial.

Exemplo:

```text
Essencial
Gestão
Food
Enterprise
```

## PlanVersion

Representa uma versão contratual.

Exemplo:

```text
Food v1
Food v2
```

Mudança relevante cria nova versão.

---

# 14. PLAN VERSION É IMUTÁVEL QUANDO USADA

Se uma versão já possui assinaturas:

```text
não editar preço
não editar módulos
não editar limites
não editar trial
```

Criar nova versão.

Exemplo:

```text
Food v1 = R$ 199
Food v2 = R$ 249
```

Clientes antigos podem permanecer na v1.

---

# 15. TELA DE PLANOS

Lista:

```text
Plano
Status
Versão atual
Preço
Clientes
```

Ações:

```text
Criar plano
Criar nova versão
Visualizar versões
Desativar para novos clientes
```

---

# 16. EDIÇÃO DA VERSÃO DO PLANO

A tela deve ser visual e simples.

Exemplo:

```text
CORE FOOD — v2

Preço mensal
R$ 249,00

Trial
7 dias

MÓDULOS

[✓] Cadastros
[✓] Venda Rápida
[✓] Caixa
[✓] Mesas & Comandas
[✓] Estoque
[✓] Compras
[✓] Produção
[✓] Financeiro
[✓] Relatórios
[✓] CORE POS
[ ] Fiscal
[ ] WhatsApp
[ ] Integrações
[ ] IA CORE

LIMITES

Usuários: 10
Filiais: 2
CORE POS: 3
```

---

# 17. PRINCÍPIO DOS MÓDULOS

Tudo que aparece como funcionalidade relevante para o cliente deve poder ser controlado pelo plano.

Não considerar que:

```text
“é básico, então sempre aparece”
```

Se o cliente não contratou/não usa, não deve poluir a interface.

---

# 18. REGRA DE VISIBILIDADE

```text
Plano
  ↓
Módulos habilitados
  ↓
Capabilities internas
  ↓
Permissões do usuário
  ↓
Menu e ações disponíveis
```

Se o plano não possui o módulo:

```text
o módulo não aparece
```

Não mostrar desabilitado/cinza por padrão.

---

# 19. INFRAESTRUTURA INVISÍVEL

Alguns elementos são obrigatórios para o sistema existir, mas não precisam ser tratados como módulo comercial visível.

Exemplos:

```text
Company
Branch
Usuários
RBAC
Assinatura
Auditoria mínima
Configurações básicas
Segurança
```

Esses são infraestrutura da plataforma.

---

# 20. CATÁLOGO COMERCIAL DE MÓDULOS

O MVP terá os seguintes módulos comerciais.

---

# 21. MÓDULO — CADASTROS

Código conceitual:

```text
catalog
```

Inclui:

- produtos;
- categorias;
- clientes;
- formas de pagamento básicas;
- configurações comerciais relacionadas.

Este módulo serve como base funcional para outros módulos.

---

# 22. MÓDULO — VENDA RÁPIDA

Código conceitual:

```text
quick_sale
```

Inclui:

- venda direta;
- balcão;
- carrinho;
- pagamentos;
- descontos;
- cancelamentos;
- promoções quando disponíveis;
- taxa de serviço quando aplicável.

Backend continua usando:

```text
counter
```

quando esse for o canal técnico.

---

# 23. MÓDULO — CAIXA

Código conceitual:

```text
cash
```

Inclui:

- caixas;
- abertura;
- fechamento;
- sangria;
- suprimento;
- sessões;
- conferência.

---

# 24. MÓDULO — MESAS & COMANDAS

Código conceitual:

```text
tables_commands
```

Inclui:

- mesas;
- comandas;
- pedidos;
- itens;
- transferência;
- merge;
- split;
- pagamentos parciais;
- fechamento.

---

# 25. MÓDULO — ESTOQUE

Código conceitual:

```text
inventory
```

Inclui:

- posição de estoque;
- entrada;
- saída;
- ajustes;
- perdas;
- inventário;
- histórico;
- estoque mínimo;
- transferências entre filiais.

---

# 26. MÓDULO — COMPRAS

Código conceitual:

```text
purchases
```

Inclui:

- fornecedores;
- pedidos de compra;
- entrada direta;
- recebimento parcial;
- custos;
- rateios;
- contas a pagar originadas de compra.

---

# 27. MÓDULO — PRODUÇÃO

Código conceitual:

```text
production
```

Inclui:

- setores;
- destinos de produção;
- impressoras;
- tickets de cozinha/bar/copa;
- ProductionJob;
- PrintJob;
- fila de impressão;
- reimpressão;
- tickets operacionais relacionados.

---

# 28. MÓDULO — FINANCEIRO

Código conceitual:

```text
financial
```

Inclui futuramente/gradualmente:

- contas a pagar;
- contas a receber;
- despesas;
- receitas;
- fluxo financeiro;
- visão de resultado;
- conciliação quando implementada.

No MVP do Platform Admin, o módulo pode existir no catálogo mesmo que parte das funcionalidades do Backoffice ainda esteja em desenvolvimento.

---

# 29. MÓDULO — RELATÓRIOS

Código conceitual:

```text
reports
```

Inclui:

- relatórios de vendas;
- caixa;
- estoque;
- produtos;
- equipe;
- descontos;
- cancelamentos;
- resultado operacional;
- indicadores.

Pode haver relatórios básicos sempre necessários para funcionamento interno, mas a área de relatórios do cliente deve respeitar o módulo comercial.

---

# 30. MÓDULO — CORE POS

Código conceitual:

```text
core_pos
```

Inclui:

- app CORE POS;
- Android;
- Stone;
- tablets;
- devices licenciados;
- operação dos módulos disponíveis no plano.

O CORE POS não concede outros módulos sozinho.

Exemplo:

```text
Plano possui CORE POS
+
Venda Rápida
+
Caixa
```

No app aparecem:

```text
Venda Rápida
Caixa
```

Se também possuir:

```text
Mesas & Comandas
```

o POS passa a exibir esse recurso.

---

# 31. MÓDULO — FISCAL

Código conceitual:

```text
fiscal
```

Status inicial:

```text
EM BREVE
```

Inclui futuramente:

- NFC-e;
- NF-e;
- documentos fiscais;
- contingência;
- configurações fiscais.

Não implementar fiscal agora.

---

# 32. MÓDULO — WHATSAPP

Código conceitual:

```text
whatsapp
```

Status inicial:

```text
EM BREVE
```

Inclui futuramente:

- atendimento;
- reservas;
- comunicação;
- campanhas;
- automações;
- promoções.

---

# 33. MÓDULO — INTEGRAÇÕES

Código conceitual:

```text
integrations
```

Status inicial:

```text
EM BREVE
```

Inclui futuramente:

- iFood;
- Anota AI;
- API pública;
- webhooks;
- providers externos.

---

# 34. MÓDULO — IA CORE

Código conceitual:

```text
core_ai
```

Status inicial:

```text
EM BREVE
```

Inclui futuramente:

- assistente;
- análise;
- automações inteligentes;
- criação de conteúdo;
- flyers;
- insights.

---

# 35. STATUS DO MÓDULO

Cada módulo comercial deve possuir:

```text
ACTIVE
COMING_SOON
INACTIVE
```

## ACTIVE

Pode ser usado em planos.

## COMING_SOON

Aparece no Platform Admin como futuro, mas não pode ser habilitado em plano comercial ativo sem autorização explícita.

## INACTIVE

Não disponível para novas versões.

Histórico de planos antigos deve continuar resolvível.

---

# 36. TELA DE MÓDULOS

Rota conceitual:

```text
/modules
```

Mostrar:

```text
Nome
Código
Descrição
Status
Dependências
Quantidade de planos usando
```

---

# 37. CADASTRAR MÓDULO

Campos:

```text
Nome
Código
Descrição
Status
Ordem
Ícone opcional
```

Código deve ser estável.

Não permitir mudar código de módulo usado sem migration/fluxo específico.

---

# 38. DEPENDÊNCIAS DE MÓDULOS

O sistema deve suportar dependências simples.

---

# 39. DEPENDÊNCIAS INICIAIS

```text
Venda Rápida
→ requer Cadastros

Caixa
→ pode ser usado junto de Venda Rápida
→ pode ser requerido por canais financeiros

Mesas & Comandas
→ requer Cadastros
→ requer Caixa quando houver fechamento financeiro

Estoque
→ requer Cadastros

Compras
→ requer Estoque

Produção
→ requer Cadastros
→ requer ao menos um canal que gere pedidos

CORE POS
→ não libera regra de negócio sozinho
→ consome os módulos habilitados no mesmo plano

Fiscal
→ requer Venda Rápida ou outro canal de venda

Financeiro
→ pode consumir dados de Venda/Compras
```

---

# 40. UX DE DEPENDÊNCIA

Se marcar:

```text
Compras
```

e Estoque estiver desligado:

```text
Compras requer Estoque.

[ Ativar Estoque também ]
[ Cancelar ]
```

Não ativar silenciosamente.

---

# 41. CAPABILITIES INTERNAS

Módulo é linguagem comercial.

Capability é linguagem técnica.

Exemplo:

```text
Módulo: Estoque

Capabilities:
inventory.enabled
inventory.transfers
inventory.counts
inventory.losses
```

O Platform Admin deve mostrar principalmente:

```text
Estoque
```

e não obrigar o administrador a gerenciar cada capability técnica no MVP.

---

# 42. COMPATIBILIDADE COM CAPABILITIES ATUAIS

Já existem conceitos como:

```text
core.enabled
users.max
branches.max
feature.tables
feature.commands
feature.counter
feature.consumption
feature.cash_register
feature.production
```

O OpenCode deve mapear os módulos comerciais sobre essas capabilities sempre que possível.

Não duplicar capability sem necessidade.

---

# 43. MAPA INICIAL DE MÓDULO → CAPABILITY

Conceitualmente:

```text
Cadastros
→ core.enabled

Venda Rápida
→ feature.counter

Caixa
→ feature.cash_register

Mesas & Comandas
→ feature.tables
→ feature.commands

Produção
→ feature.production

CORE POS
→ nova capability específica quando necessário
```

Estoque, Compras, Financeiro e Relatórios devem ser mapeados para capabilities existentes ou novas somente após auditoria.

---

# 44. LIMITES BÁSICOS DO PLANO

No MVP, controlar somente limites realmente importantes:

```text
users.max
branches.max
core_pos.devices.max
```

Outros limites podem entrar depois.

---

# 45. LIMITE ILIMITADO

Suportar:

```text
unlimited = true
```

Não usar números mágicos como:

```text
999999
```

---

# 46. EXEMPLO — PLANO BALCÃO

```text
CORE BALCÃO

✓ Cadastros
✓ Venda Rápida
✓ Caixa
✓ Estoque
✓ Relatórios

✗ Mesas & Comandas
✗ Compras
✗ Produção
✗ Financeiro
✗ CORE POS
✗ Fiscal
✗ WhatsApp
✗ Integrações
✗ IA CORE

Usuários: 3
Filiais: 1
```

O cliente não vê Mesas/Comandas.

---

# 47. EXEMPLO — PLANO FOOD

```text
CORE FOOD

✓ Cadastros
✓ Venda Rápida
✓ Caixa
✓ Mesas & Comandas
✓ Estoque
✓ Compras
✓ Produção
✓ Relatórios
✓ CORE POS

✗ Fiscal
✗ WhatsApp
✗ Integrações
✗ IA CORE

Usuários: 10
Filiais: 2
CORE POS: 3
```

---

# 48. EXEMPLO — CASA DE EVENTOS

```text
CORE EVENTOS

✓ Cadastros
✓ Venda Rápida
✓ Caixa
✓ Estoque
✓ Produção
✓ CORE POS
✓ Relatórios

✗ Mesas & Comandas
✗ Compras
✗ Financeiro
```

Pode utilizar:

```text
Product.emits_ticket
+
Validador de Ticket
```

sem precisar contratar Mesas & Comandas.

---

# 49. BACKOFFICE DEVE RESPEITAR MÓDULOS

Exemplo:

Plano sem Compras:

```text
não mostrar Compras
não mostrar Fornecedores se fornecedor estiver exclusivamente dentro do módulo Compras
```

Plano sem Mesas & Comandas:

```text
não mostrar Mesas
não mostrar Comandas
```

Plano sem Produção:

```text
não mostrar Produção
não mostrar Impressoras de produção
```

---

# 50. RBAC CONTINUA EXISTINDO

Módulo habilitado não significa que todos os usuários podem usar.

Regra:

```text
Módulo contratado
        ∩
Permissão do usuário
        =
Ação disponível
```

Exemplo:

Plano possui Estoque.

Usuário sem:

```text
inventory.view
```

não vê Estoque.

---

# 51. MÓDULO DESABILITADO SUPERA PERMISSÃO

Se usuário possui:

```text
inventory.view
```

mas plano não possui Estoque:

```text
não pode acessar
```

---

# 52. ASSINATURAS

Tela:

```text
Assinaturas
```

Filtros:

```text
Trial
Ativa
Inadimplente
Restrita
Suspensa
Cancelada
PAID
FREE
INTERNAL
```

Colunas:

```text
Cliente
Plano
Versão
Billing mode
Status
Início do período
Fim do período
Valor
```

---

# 53. BILLING MODE

Manter:

```text
PAID
FREE
INTERNAL
```

---

# 54. PAID

Cliente pagante.

Entra em MRR.

---

# 55. FREE

Cortesia/parceiro.

Não entra em MRR.

---

# 56. INTERNAL

Uso interno/teste.

Não entra em MRR.

---

# 57. STATUS DE ASSINATURA

Manter os estados existentes:

```text
TRIALING
ACTIVE
PAST_DUE
RESTRICTED
SUSPENDED_FINANCIAL
TRIAL_EXPIRED
CANCELLED
SUPERSEDED
```

Não criar estados equivalentes.

---

# 58. TROCAR PLANO

No MVP:

```text
admin CORE escolhe nova PlanVersion
→ preview
→ confirma
→ assinatura nova/substituição conforme domínio atual
```

Preservar histórico.

---

# 59. DOWNGRADE

No MVP, antes de confirmar mostrar:

```text
Plano atual
Plano novo

Módulos perdidos
Limites reduzidos
Usuários acima do limite
Filiais acima do limite
CORE POS acima do limite
```

Não apagar nada automaticamente.

---

# 60. COBRANÇA

Tela:

```text
Cobrança
```

Resumo:

```text
MRR
Recebido no mês
Inadimplentes
Restritos
Suspensos
```

---

# 61. PAGAMENTOS

Registrar manualmente:

```text
Cliente
Assinatura
Valor
Data
Forma de pagamento
Competência
Observação
Comprovante/referência
```

---

# 62. PAGAMENTO É APPEND-ONLY

Não editar nem apagar pagamento registrado.

Se houver erro, criar processo corretivo depois.

---

# 63. MRR

No MVP:

```text
soma do valor mensal normalizado das assinaturas PAID ativas
```

FREE e INTERNAL:

```text
R$ 0 no MRR
```

Annual futuramente:

```text
valor / 12
```

---

# 64. INADIMPLÊNCIA

Usar política global existente.

Fluxo:

```text
ACTIVE
→ PAST_DUE
→ RESTRICTED
→ SUSPENDED_FINANCIAL
```

---

# 65. SUSPENSÃO ADMINISTRATIVA

Separada da financeira.

Pagamento não remove suspensão administrativa.

---

# 66. REATIVAÇÃO FINANCEIRA

Pagamento válido pode reativar conforme regra atual.

Não reativar se houver:

```text
admin suspension
archive
ou outra restrição
```

---

# 67. SUPORTE

Manter Support Session existente.

Tela:

```text
Suporte
```

Mostrar:

```text
Cliente
Ator
Modo
Motivo
Usuário impersonado
Criada em
Expira em
Status
```

---

# 68. MODOS

```text
READ_ONLY
READ_WRITE
```

---

# 69. INICIAR SUPPORT SESSION

Exigir:

```text
Cliente
Modo
Motivo
Reautenticação
Usuário impersonado opcional
```

---

# 70. AUDITORIA

Tela simples:

```text
Auditoria
```

Filtros:

```text
Data
Cliente
Usuário CORE
Ação
```

---

# 71. AÇÕES QUE DEVEM SER AUDITADAS

No mínimo:

```text
tenant criado
tenant aprovado
tenant rejeitado
tenant suspenso
tenant reativado
tenant arquivado

Owner transferido

plano criado
versão criada
plano atribuído
plano alterado

pagamento registrado

Support Session iniciada
Support Session encerrada

configuração global alterada
```

---

# 72. CONFIGURAÇÕES

Tela:

```text
Configurações
```

Separar em:

```text
Plataforma
Suporte
Regras SaaS
```

---

# 73. PLATAFORMA

```text
Nome
Logo
Logo compacta
Favicon
Cor principal
```

---

# 74. SUPORTE

```text
E-mail
Telefone
WhatsApp
Duração padrão Support Session
```

---

# 75. REGRAS SAAS

```text
Autoaprovar cadastro
Dias para PAST_DUE
Dias para RESTRICTED
Billing mode do signup público
```

Não adicionar políticas complexas agora.

---

# 76. LOGIN

O login atual precisa estar estável.

Prioridades:

- autenticação;
- sessão;
- logout;
- mensagens de erro;
- proteção de rotas;
- permission guard.

MFA pode vir depois se ainda for somente um administrador interno.

Não bloquear o MVP por MFA.

---

# 77. PERMISSÕES DA PLATAFORMA

No MVP, manter as existentes:

```text
platform.dashboard.view
platform.tenants.manage
platform.plans.manage
platform.settings.manage
platform.billing.manage
platform.support.manage
```

Criar novas somente se a separação for realmente necessária.

---

# 78. ERROS ATUAIS

Antes de adicionar novas funções, o OpenCode deve auditar o Platform Admin atual.

Verificar:

```text
login
sessão
dashboard
tenants
tenant detail
plans
billing
support
settings

API errors
loading states
empty states
double submit
dados incorretos
ações que quebram
permissions
responsive
build
lint
```

---

# 79. PRIMEIRA ETAPA — PA-MVP-0

## Objetivo

Corrigir e estabilizar tudo que já existe.

## Escopo

```text
Login
Navegação
Dashboard
Tenants
Tenant detail
Plans
Billing
Support
Settings
API client
Types
Loading/error states
Permissions
Build
Tests focados
```

## Não adicionar grandes módulos novos ainda.

---

# 80. CRITÉRIOS PA-MVP-0

- [ ] Login funciona.
- [ ] Logout funciona.
- [ ] Rotas privadas protegidas.
- [ ] Dashboard carrega.
- [ ] Lista de tenants funciona.
- [ ] Tenant detail funciona.
- [ ] Planos funcionam.
- [ ] Billing funciona.
- [ ] Support funciona.
- [ ] Settings funciona.
- [ ] Não há erro fatal de UI.
- [ ] Build verde.
- [ ] Backend relacionado verde.

---

# 81. SEGUNDA ETAPA — PA-MVP-1

## Objetivo

Administrar cliente e produto comercial.

## Escopo

```text
Criar tenant
Tenant 360 básico
Owner
Filiais
Usuários
Planos
PlanVersion
Módulos comerciais
Dependências
Limites
Atribuir/trocar plano
```

---

# 82. CRITÉRIOS PA-MVP-1

- [ ] Criar tenant completo.
- [ ] Criar filial principal automaticamente.
- [ ] Criar Owner.
- [ ] Criar assinatura.
- [ ] Tenant 360 funcional.
- [ ] Criar plano.
- [ ] Criar versão.
- [ ] Selecionar módulos.
- [ ] Dependências validadas.
- [ ] Limites salvos.
- [ ] Versão usada imutável.
- [ ] Trocar plano.
- [ ] Preview de downgrade.

---

# 83. TERCEIRA ETAPA — PA-MVP-2

## Objetivo

Dinheiro e controle.

## Escopo

```text
Cobrança manual
Pagamentos
MRR básico
Inadimplência
Suspensão/restrição
Reativação
Auditoria básica
```

---

# 84. CRITÉRIOS PA-MVP-2

- [ ] Registrar pagamento.
- [ ] Histórico de pagamentos.
- [ ] Append-only.
- [ ] MRR.
- [ ] PAID/FREE/INTERNAL corretos.
- [ ] PAST_DUE.
- [ ] RESTRICTED.
- [ ] SUSPENDED_FINANCIAL.
- [ ] Reativação.
- [ ] Admin suspension preservada.
- [ ] Auditoria.

---

# 85. ORDEM OFICIAL

```text
PA-MVP-0
Corrigir o que já existe
        ↓
PA-MVP-1
Clientes + Planos + Módulos
        ↓
PA-MVP-2
Cobrança + Auditoria
        ↓
PLATFORM ADMIN MVP PRONTO
```

Depois disso:

```text
voltar para CORE POS
```

Novas funções do Platform Admin entram conforme clientes e necessidades reais crescerem.

---

# 86. REGRAS PARA O OPENCODE

Não:

- reescrever o SaaS;
- apagar models existentes;
- quebrar PlanVersion;
- criar catálogo paralelo de capabilities;
- misturar módulo comercial com permission;
- hardcodar menu por plano;
- criar CRM;
- criar Health Score;
- criar Feature Flags;
- criar Devices;
- criar Integrações;
- criar add-ons;
- criar overrides;
- adicionar arquitetura desnecessária;
- usar Redis/Kafka apenas “para preparar futuro”;
- criar microserviços.

---

# 87. MÓDULO COMERCIAL X CAPABILITY X PERMISSION

Reforço final:

```text
MÓDULO
= produto comercial que o cliente contrata
```

```text
CAPABILITY
= chave técnica que habilita comportamento/limite
```

```text
PERMISSION
= o que aquele usuário pode fazer
```

Exemplo:

```text
Plano possui Estoque
        ↓
capability inventory habilitada
        ↓
usuário possui inventory.view
        ↓
Estoque aparece
```

---

# 88. VISIBILIDADE FINAL

Para uma entrada de menu aparecer:

```text
Módulo/Capability habilitado no tenant
        ∩
Permissão do usuário
        =
Menu disponível
```

Se módulo não está no plano:

```text
não mostrar
```

---

# 89. RESULTADO ESPERADO DO MVP

Ao final:

```text
CORE PLATFORM
│
├── Dashboard
├── Clientes
│   └── Tenant 360
├── Assinaturas
├── Planos
├── Módulos
├── Cobrança
├── Suporte
├── Auditoria
└── Configurações
```

E você consegue:

```text
criar cliente
atribuir plano
escolher módulos
controlar limites
acompanhar assinatura
registrar pagamento
suspender
reativar
prestar suporte
ver histórico
```

Sem entrar no banco.

---

# 90. PRIMEIRA INSTRUÇÃO PARA O OPENCODE

> Leia integralmente `CORE_PLATFORM_ADMIN_MVP.md`.
>
> Este documento define somente o MVP funcional do Platform Admin.
>
> Não implemente funcionalidades futuras.
>
> Antes de alterar qualquer arquivo:
>
> 1. audite o `platform-admin`;
> 2. audite `/api/v1/platform/`;
> 3. audite `apps.saas`;
> 4. liste bugs e inconsistências atuais;
> 5. liste quais partes do PA-MVP-0 já funcionam;
> 6. liste o que precisa ser corrigido.
>
> Execute SOMENTE o **PA-MVP-0 — Corrigir o que já existe**.
>
> Não inicie PA-MVP-1.
>
> Não crie ainda catálogo de módulos se PA-MVP-0 ainda não estiver estável.
>
> Corrija backend/frontend relacionados sem enfraquecer regras de domínio existentes.
>
> Use testes focados.
>
> Ao terminar, entregue:
>
> - resumo;
> - bugs corrigidos;
> - arquivos alterados;
> - endpoints alterados;
> - testes;
> - build;
> - pendências.
>
> E PARE.

---

**FIM — CORE PLATFORM ADMIN MVP**
