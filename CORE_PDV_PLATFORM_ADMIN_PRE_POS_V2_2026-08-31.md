# CORE PDV — PLATFORM ADMIN PRÉ-POS
**Data:** 31/08/2026  
**Escopo:** somente decisões e funcionalidades definidas para o Platform Admin antes do início do CORE POS.

---

# 1. Objetivo do Platform Admin

O Platform Admin deve deixar de ser apenas um painel para visualizar tenants, planos e cobranças.

Ele deve se tornar o **Control Plane do CORE PDV**.

Princípio:

> Toda gestão normal de um cliente CORE deve ser possível pelo Platform Admin, sem precisar acessar banco, Django Admin, VPS, terminal ou executar SQL/scripts manualmente.

Banco e terminal ficam reservados para incidentes técnicos excepcionais.

Antes do POS, o Platform Admin deve permitir controlar:

- tenants/clientes;
- filiais;
- usuários dos clientes;
- equipe CORE;
- planos;
- assinatura;
- módulos;
- limites;
- overrides;
- devices;
- acesso de suporte;
- feature flags;
- kill switch;
- auditoria;
- diagnóstico;
- estado operacional.

---

# 2. Tenant 360 como Control Center

A tela do cliente deve se tornar o principal ponto de operação da equipe CORE.

Exemplo:

```text
25 LOUNGE                                      ● ATIVO

Plano PRO              R$ 299/mês
3 filiais              14 usuários
4/5 POS                Billing OK
Última venda           2 min atrás
Devices online         5/6

[ Entrar como cliente ]
[ Enviar comunicação ]
[ Alterar assinatura ]
[ Mais ações ▼ ]
```

## Abas planejadas

```text
Visão Geral
Assinatura
Módulos e Limites
Filiais
Usuários
Dispositivos
Pagamentos
Suporte
Integrações
Timeline
Auditoria
Notas Internas
```

---

# 3. Controles CORE por cliente

Criar uma seção clara para controles administrativos internos:

```text
CONTROLES CORE

Estado da conta          ACTIVE
Billing                  PAID
Operação                 NORMAL
Overrides                3 ativos
Feature Flags            2 customizadas
Suspensão administrativa NÃO
Acesso de suporte        PERMITIDO
Tenant experimental      NÃO
```

Separar estados financeiros de estados administrativos/operacionais.

Exemplos:

```text
ACTIVE
PAST_DUE
RESTRICTED
SUSPENDED_FINANCIAL
SUSPENDED_ADMIN
MAINTENANCE
SECURITY_LOCK
```

---

# 4. Gestão de dados do cliente

Pelo Platform Admin, permitir alterar ou administrar:

- nome da empresa;
- razão social;
- CNPJ;
- dados cadastrais;
- responsável;
- Owner;
- transferência de propriedade;
- timezone;
- moeda;
- configurações administrativas permitidas;
- status do tenant.

Toda ação sensível deve ter auditoria.

---

# 5. Gestão de filiais pelo Platform Admin

Não apenas visualizar filiais.

Permitir:

- criar filial;
- editar;
- ativar;
- suspender;
- arquivar;
- consultar usuários;
- consultar devices;
- consultar módulos/licenças;
- consultar status operacional;
- consultar consumo do plano.

Exemplo:

```text
Filiais

3 / 5 utilizadas

Beira-Mar     ATIVA      2 POS
Pavuna        ATIVA      2 POS
Rio Centro    ATIVA      1 POS
```

---

# 6. Gestão de usuários dos clientes

Na aba Usuários:

```text
João       Administrador       Ativo
Maria      Estoquista          Ativo
Pedro      Caixa               Bloqueado
```

Permitir:

- visualizar acessos;
- visualizar memberships;
- visualizar roles/permissões;
- bloquear;
- desbloquear;
- suspender;
- revogar acesso à empresa;
- encerrar sessões;
- visualizar última atividade;
- transferir Owner quando aplicável.

Não usar senha em texto claro.

Recuperação de acesso deve usar convite/reset seguro.

---

# 7. Equipe CORE administrável pelo próprio Platform Admin

Hoje não devemos depender permanentemente de management command para administrar a equipe.

Criar área:

```text
Equipe CORE
├── Usuários
├── Roles
├── Permissões
├── Sessões
├── MFA
└── Auditoria
```

Permitir:

- convidar usuário CORE;
- ativar/desativar;
- atribuir role;
- remover role;
- bloquear acesso;
- revogar sessões;
- acompanhar MFA.

O bootstrap via CLI permanece apenas para instalação ou emergência.

---

# 8. RBAC granular da equipe CORE

Não concentrar ações críticas em poucas permissões amplas.

Preparar permissões conceitualmente semelhantes a:

```text
platform.tenants.view
platform.tenants.create
platform.tenants.edit
platform.tenants.suspend
platform.tenants.archive

platform.owner.transfer

platform.users.view
platform.users.manage

platform.branches.view
platform.branches.manage

platform.plans.view
platform.plans.manage

platform.billing.view
platform.billing.payment.create
platform.billing.subscription.change

platform.entitlements.view
platform.entitlements.override

platform.support.view
platform.support.session.readonly
platform.support.session.write
platform.support.session.terminate_any

platform.devices.view
platform.devices.manage

platform.feature_flags.view
platform.feature_flags.manage

platform.audit.view
platform.settings.manage
```

Roles futuras:

```text
Super Admin
Administrador
Suporte N1
Suporte N2
Financeiro
Comercial
Customer Success
Operações
```

---

# 9. MFA obrigatório no Platform Admin

O Platform Admin terá poderes críticos.

MFA deve ser obrigatório.

Arquitetura deve permitir evolução para:

```text
PASSWORD
WHATSAPP_OTP
TOTP
PASSKEY
RECOVERY_CODE
```

Requisitos:

- MFA obrigatório para equipe CORE;
- recovery seguro;
- MFA recente para ações críticas;
- revogação de fator;
- auditoria;
- encerramento de sessões comprometidas.

---

# 10. Support Sessions

A funcionalidade já planejada deve ser fortalecida.

Modos:

```text
READ_ONLY
READ_WRITE
```

Toda Support Session deve exigir:

- usuário CORE autenticado;
- motivo;
- reautenticação;
- MFA recente;
- expiração;
- auditoria;
- banner permanente.

UX desejada:

```text
Empresa
[ 25 Lounge              ]

Usuário
[ João — Administrador   ]

Modo
[ Somente leitura        ]

Duração
[ 30 minutos             ]

Motivo
[ Erro relatado no caixa ]

[ Iniciar sessão ]
```

Não exigir IDs manuais na interface.

Super Admin deve poder:

- encerrar qualquer Support Session;
- revogar sessões de outro membro CORE;
- desativar o acesso CORE imediatamente.

O Owner do tenant deve conseguir visualizar acessos realizados pela equipe CORE.

---

# 11. Gestão comercial por cliente

O Platform Admin deve permitir administrar a assinatura sem precisar criar um plano novo para cada exceção.

Exemplo:

```text
25 LOUNGE

Plano: PRO
Preço de tabela: R$ 299
Preço contratado: R$ 249

Filiais incluídas: 3
POS incluídos: 3
POS extras: +2
KDS: 1

WhatsApp: desabilitado
API Pública: habilitada
Ticket Validator: habilitado
```

---

# 12. Ativar/desativar módulos por cliente

Deve ser possível administrar módulos individualmente por tenant.

Estados:

```text
Herdar do plano
Forçar habilitado
Forçar desabilitado
```

Exemplo:

```text
25 LOUNGE
Plano: PRO

Backoffice          Habilitado pelo plano
Mesas               Habilitado pelo plano
Comandas             Habilitado pelo plano
Compras              Habilitado pelo plano
CORE POS             Override CORE
Ticket Validator     Override CORE
KDS                  Desabilitado
WhatsApp             Não contratado
API Pública          Override temporário
```

Isso permitirá liberar funcionalidades para clientes específicos sem criar outro plano.

---

# 13. Módulos por filial quando aplicável

Alguns módulos são tenant-wide.

Outros podem precisar de controle por filial.

Exemplo:

```text
25 Lounge
CORE POS: contratado

Beira-Mar      ON
Pavuna         ON
Rio Centro     OFF
```

A arquitetura deve permitir:

- módulo contratado pelo tenant;
- override do tenant;
- disponibilidade por filial quando aplicável.

---

# 14. Tenant Entitlement Overrides

Criar conceito de override individual do cliente.

Exemplo:

```text
CORE POS

Plano:       3
Override:   +2
Efetivo:     5

Origem:      Override CORE
Motivo:      Cliente piloto Stone
Expira:      30/11/2026
Criado por:  Luis
```

Override pode ser:

- permanente;
- temporário;
- habilitar módulo;
- desabilitar módulo;
- aumentar limite;
- reduzir limite.

Deve armazenar:

- tenant;
- capability;
- tipo de override;
- valor;
- início;
- fim opcional;
- motivo;
- criador;
- auditoria.

---

# 15. Add-ons

Diferenciar Add-on de Override CORE.

## Override CORE
Exceção administrativa/comercial.

## Add-on
Recurso adicional contratado pelo cliente.

Exemplo:

```text
Plano PRO          R$ 299
+ 2 POS            R$ 40
+ WhatsApp         R$ 49
+ 1 filial         R$ 30
-------------------------
MRR contratado     R$ 418
```

A cobrança pode continuar manual inicialmente.

O domínio deve ficar preparado para cobrança automática futura.

---

# 16. Preço de tabela x preço contratado

Não amarrar o valor real da assinatura exclusivamente ao preço da versão do plano.

Exemplo:

```text
Plano PRO             R$ 299
Preço contratado      R$ 239
Desconto               R$ 60
Motivo                 Cliente fundador
Validade               Permanente
```

MRR deve usar:

```text
Preço contratado
+ Add-ons
```

Registrar histórico das mudanças comerciais.

---

# 17. Arquitetura comercial desejada

O fluxo deve ser:

```text
Plan
   ↓
PlanVersion
   ↓
Subscription
   ↓
Entitlements
   ↓
Tenant Overrides
   ↓
Add-ons
   ↓
Effective Entitlements
   ↓
Usage
```

O POS e demais apps devem consultar **Effective Entitlements**, nunca regras hardcoded de plano.

---

# 18. Capabilities e limites

Preparar catálogo para suportar:

```text
core.enabled

users.max
branches.max
devices.max
pos.max
kds.max
print_agents.max

feature.pos
feature.ticket_validator
feature.tables
feature.commands
feature.counter
feature.inventory
feature.purchases
feature.reports
feature.production
feature.kds
feature.api
feature.whatsapp
```

Tipos necessários:

- boolean;
- limite numérico;
- unlimited;
- usage;
- override;
- add-on.

---

# 19. Regra para capability ausente

Novos módulos comerciais não podem ser habilitados automaticamente apenas porque uma versão antiga do plano não possui aquela capability.

Exemplo:

```text
feature.pos
```

Um plano antigo que nunca conheceu `feature.pos` não deve ganhar POS automaticamente.

Para novos módulos:

```text
capability ausente = não habilitado
```

ou utilizar política default explícita.

---

# 20. Usage e limites

Mostrar uso real de recursos.

Exemplo:

```text
Filiais       3 / 5
Usuários      12 / 20
CORE POS      4 / 5
KDS           1 / 2
```

Usage deve considerar:

- plano;
- override;
- add-on;
- unlimited;
- status do recurso.

---

# 21. Feature Flags

Separar rollout técnico de contratação comercial.

Entitlement responde:

> o cliente tem direito?

Feature Flag responde:

> podemos liberar tecnicamente agora?

Suportar progressivamente:

```text
ALL
NONE
PLAN
TENANT
PERCENTAGE
INTERNAL
BETA
EARLY_ACCESS
```

Exemplo:

```text
Novo CORE POS

Global          OFF
INTERNAL        ON
25 Lounge       ON
Plano PRO       OFF
```

Para liberar uma feature:

```text
Entitlement permite
AND
Feature Flag permite
```

---

# 22. Kill Switch

Criar Kill Switch global e por tenant/módulo.

Global:

```text
CORE POS
[ DESATIVAR EMERGÊNCIA ]
```

Tenant:

```text
25 Lounge

POS             NORMAL
Vendas          NORMAL
Integrações     NORMAL
```

Ação crítica deve exigir:

- preview;
- motivo;
- confirmação;
- reautenticação;
- MFA recente;
- auditoria.

---

# 23. Device Control Plane

Antes do POS, o Platform Admin precisa estar preparado para administrar dispositivos.

Criar entidade genérica:

```text
Device

id
tenant
branch

type
status

device_identifier
platform
app_version

pairing_status
paired_at
paired_by

last_seen_at

blocked_at
blocked_by

replaced_by

metadata
```

Tipos preparados:

```text
BACKOFFICE
POS
STONE_POS
KDS
PRINT_AGENT
TOTEM
MOBILE
```

---

# 24. Estados de Device

Preparar estados semelhantes a:

```text
PENDING
ACTIVE
BLOCKED
OFFLINE
REPLACED
REVOKED
```

Diferenciar:

- bloquear;
- desvincular;
- substituir.

Suspender tenant não deve excluir/desvincular devices.

Deve apenas retirar autorização operacional.

---

# 25. Pareamento e licenciamento

Fluxo esperado:

```text
App instalado
    ↓
Identificação tenant/filial
    ↓
Código de pareamento
    ↓
Aprovação
    ↓
Device registrado
    ↓
Entitlement/licença validado
    ↓
Operação liberada
```

Validar:

- tenant;
- filial;
- módulo habilitado;
- limite do plano;
- override;
- add-on;
- status do device;
- status do tenant;
- feature flag;
- kill switch.

---

# 26. Inventário global de Devices

Criar uma área global.

Exemplo:

```text
DISPOSITIVOS

Online             42
Offline             7
Bloqueados          2
Desatualizados      5
```

Dentro do tenant:

```text
25 Lounge

Stone P2 #01      Beira-Mar    ONLINE
Stone P2 #02      Pavuna       ONLINE
Tablet KDS        Cozinha      OFFLINE
```

Ações:

- bloquear;
- desbloquear;
- desvincular;
- substituir;
- encerrar sessão do operador quando aplicável;
- sincronizar;
- visualizar diagnóstico;
- visualizar histórico.

---

# 27. Heartbeat e Device Health

Device deve guardar pelo menos:

- último heartbeat;
- online/offline;
- versão do app;
- tenant;
- filial;
- último erro relevante.

Preparar para depois:

- latência;
- última venda;
- sincronização;
- rollout;
- versão mínima;
- status de atualização.

---

# 28. Dashboard operacional

O dashboard do Platform Admin não deve mostrar apenas métricas financeiras.

Além de:

```text
MRR
ARR
Clientes
Trials
Inadimplência
```

mostrar também sinais operacionais:

```text
POS offline
Devices sem heartbeat
Tenants acima do limite
Integrações desconectadas
Falhas críticas recentes
Filiais sem operação
Devices desatualizados
```

Objetivo:

> identificar problemas antes que o cliente abra chamado.

---

# 29. Diagnóstico do tenant

Criar:

```text
[ Executar diagnóstico ]
```

Resultado exemplo:

```text
✓ Assinatura
✓ Owner
✓ Filiais
✓ Usuários
✓ Entitlements
✓ Devices

⚠ 2 usuários acima do limite
⚠ 1 configuração inconsistente
⚠ 1 POS offline há 47 min
```

A primeira versão deve ser prioritariamente read-only.

Correções automáticas somente quando forem:

- determinísticas;
- seguras;
- idempotentes;
- auditadas.

Exemplos futuros:

```text
Recalcular estado SaaS
Reprocessar limites
Sincronizar configurações
```

---

# 30. Auditoria no Platform Admin

Expor a auditoria da plataforma pela interface.

Exemplo:

```text
Luis / CORE

Alterou limite POS
3 → 5

Motivo: Cliente piloto
31/08/2026 18:24
```

Filtros:

- tenant;
- usuário CORE;
- cliente;
- billing;
- suporte;
- segurança;
- devices;
- entitlements;
- configurações.

---

# 31. Timeline 360

Separar Timeline da auditoria técnica.

Exemplo:

```text
18:30 Venda realizada
18:28 POS voltou online
18:20 CORE aumentou limite de POS
17:52 Pagamento confirmado
16:41 Support Session iniciada
```

Objetivo:

> responder rapidamente “o que aconteceu com este cliente?”

---

# 32. Notas internas / CORE Only

Criar área que o cliente nunca vê.

Exemplo:

```text
Responsável comercial: Maria
Responsável CS: João
Responsável suporte: Felipe

Classificação: Cliente estratégico

Tags:
VIP
EARLY_ACCESS
STONE
ALTO_MRR

Observações internas:
...
```

Marcar explicitamente como informação interna.

---

# 33. Comunicação com o cliente

Preparar dentro do Tenant 360:

```text
[ Enviar comunicação ]
```

Tipos:

- suporte;
- manutenção;
- cobrança;
- aviso;
- onboarding;
- comercial.

Canais futuros:

- notificação interna;
- e-mail;
- WhatsApp.

Comunicações devem aparecer na Timeline.

Não precisa bloquear o POS ter todos os canais prontos, mas a arquitetura deve permitir evolução.

---

# 34. Ferramentas de correção e operação

O Platform Admin deve reduzir a necessidade de banco/terminal.

Criar ferramentas administrativas seguras para problemas comuns.

Exemplo:

```text
Verificar integridade do tenant
```

Resultado:

```text
✓ Usuários
✓ Memberships
✓ Filiais
✓ Assinatura
✓ Permissões
✓ Devices

⚠ configuração inconsistente
```

Evitar ferramentas genéricas de “editar banco”.

Cada ação corretiva deve possuir:

- regra conhecida;
- impacto previsível;
- auditoria;
- motivo quando necessário.

---

# 35. Operações remotas futuras nos dispositivos

Preparar o modelo para ações como:

- encerrar operador;
- bloquear device;
- desvincular;
- substituir;
- reenviar configuração;
- sincronizar;
- solicitar diagnóstico;
- atualizar app;
- forçar logout.

Algumas ações dependem das capacidades da Stone/Android e podem ser implementadas durante ou depois do POS.

O Platform Admin deve estar arquiteturalmente preparado.

---

# 36. Ações em massa

Preparar para administração em escala.

Exemplo:

```text
37 clientes selecionados

[ Habilitar feature ]
[ Enviar comunicado ]
[ Aplicar add-on ]
[ Alterar trial ]
[ Exportar ]
```

Ação em massa deve ter:

1. preview;
2. quantidade afetada;
3. impacto;
4. confirmação forte;
5. MFA quando crítica;
6. auditoria.

Pode ser implementada em onda posterior caso não seja necessária no lançamento inicial.

---

# 37. Política de ações críticas

Quanto maior a autonomia do Platform Admin, maior o controle necessário.

Classificar ações:

## Normal
Baixo risco.

## Sensível
Exige motivo/auditoria.

## Crítica
Exige:

- preview;
- confirmação forte;
- senha/reautenticação recente;
- MFA recente;
- motivo;
- auditoria forte.

Exemplos críticos:

- suspender tenant;
- transferir Owner;
- Kill Switch;
- bloquear devices em massa;
- alterar preço contratado;
- conceder override especial;
- Support Session READ_WRITE;
- encerrar sessão de outro usuário CORE.

---

# 38. Referências competitivas

Referências utilizadas:

- PDV Legal OEM;
- vhsys Painel do Parceiro White Label.

Conceitos observados publicamente que validam a direção do CORE:

- gestão de clientes;
- gestão de usuários do painel;
- perfis/permissões;
- licenças por filial;
- módulos por cliente/filial;
- visão de equipamentos;
- última comunicação;
- monitoramento proativo;
- acesso ao ambiente do cliente;
- liberar/bloquear cliente;
- relatórios;
- exportações.

Não copiar UI.

Princípio absorvido:

> O Platform Admin deve ajudar a equipe CORE a perceber e resolver problemas antes que o cliente reclame.

---

# 39. O que precisa estar pronto antes do POS

## Obrigatório

```text
[ ] Tenant 360 Control Center
[ ] Gestão de filiais
[ ] Gestão de usuários dos tenants

[ ] Equipe CORE administrável
[ ] RBAC CORE granular
[ ] MFA obrigatório

[ ] Support Session endurecida

[ ] Módulos por cliente
[ ] Overrides por cliente
[ ] Limites/Usage
[ ] Preço contratado
[ ] Fundação de Add-ons
[ ] Effective Entitlements

[ ] Política correta para capabilities novas

[ ] Feature Flags
[ ] Kill Switch

[ ] Device Control Plane
[ ] Estados de Device
[ ] Pareamento/licenciamento
[ ] Heartbeat
[ ] Inventário global de Devices

[ ] Dashboard operacional básico
[ ] Diagnóstico básico
[ ] Auditoria pela UI
[ ] Timeline básica
```

---

# 40. O que pode ficar para depois do início do POS

Não deve segurar o desenvolvimento do POS:

- Customer Health Score completo;
- Churn Risk avançado;
- mini CRM completo;
- pipeline comercial;
- round-robin;
- campanhas;
- WhatsApp comercial completo;
- Automation Builder;
- cohort analysis;
- expansion/contraction MRR avançado;
- Customer Success completo;
- ações em massa sofisticadas;
- analytics executivos avançados.

---

# 41. Sprints recomendados do Platform Admin antes do POS

## PA-1 — Equipe CORE e Segurança
- Equipe CORE;
- Roles;
- Permissões;
- MFA;
- sessões;
- revogação.

## PA-2 — Tenant 360
- novo Control Center;
- estados;
- abas;
- ações administrativas.

## PA-3 — Tenant Operations
- filiais;
- usuários;
- Owner;
- sessões;
- bloqueios.

## PA-4 — Commercial Control Plane
- preço contratado;
- entitlement overrides;
- módulos por cliente;
- módulos por filial;
- limites;
- usage;
- add-ons foundation.

## PA-5 — Capabilities e Rollout
- catálogo;
- Effective Entitlements;
- feature flags;
- kill switch.

## PA-6 — Device Control Plane
- Device;
- estados;
- pareamento;
- licenciamento;
- heartbeat;
- inventário global.

## PA-7 — Operação e Suporte
- dashboard operacional;
- diagnóstico;
- auditoria;
- timeline;
- notas internas.

Depois disso:

```text
CORE POS — Sprint 0
```

---

# 42. Estado arquitetural desejado quando o POS começar

```text
CORE Platform Admin
       │
       ├── Tenant
       │     ├── Subscription
       │     ├── Effective Entitlements
       │     ├── Overrides
       │     ├── Add-ons
       │     ├── Feature Flags
       │     └── Branches
       │
       ├── CORE Team / RBAC / MFA
       │
       ├── Device Registry
       │     ├── Pairing
       │     ├── Licensing
       │     ├── Heartbeat
       │     └── Status
       │
       ├── Audit / Timeline
       └── Support / Diagnostics
```

O POS então poderá nascer consumindo essa estrutura:

```text
CORE POS
   ↓
Device Authentication
   ↓
Tenant / Branch
   ↓
Effective Entitlements
   ↓
Feature Flags / Kill Switch
   ↓
Operator Authentication
   ↓
RBAC
   ↓
Operação
```

Esse é o escopo do Platform Admin que deve ser fechado antes de iniciar o CORE POS.


---

# 43. Novo Dashboard do Platform Admin

O dashboard inicial do Platform Admin deve refletir o papel de **Control Plane do CORE**, e não funcionar apenas como painel financeiro/comercial.

Ao abrir o painel, a equipe CORE deve conseguir responder rapidamente:

> Como está o negócio CORE?

e:

> Existe algum cliente que precisa da minha atenção agora?

O dashboard deve combinar:

- saúde financeira do SaaS;
- saúde operacional dos clientes;
- problemas que exigem ação;
- novos clientes;
- devices;
- atividade recente.

Não transformar a tela em um dashboard excessivamente analítico com dezenas de gráficos sem uso operacional.

---

# 44. Linha 1 — Saúde do SaaS

Cards principais:

```text
MRR CONTRATADO       CLIENTES ATIVOS       INADIMPLENTES       TRIALS ATIVOS
R$ 18.420            37                    4                   6
+8,4% mês            +3 este mês           R$ 1.237            2 vencem em breve
```

Manter como principais indicadores:

- MRR contratado;
- clientes ativos;
- inadimplentes;
- trials ativos.

Evitar ocupar o topo inteiro com muitos cards financeiros semelhantes.

---

# 45. Linha 2 — Atenção necessária

Esta deve ser uma das áreas mais importantes do dashboard.

Exemplo:

```text
ATENÇÃO NECESSÁRIA                                      Ver tudo →

🔴 4 clientes inadimplentes
   R$ 1.237 em aberto

🔴 3 dispositivos offline
   25 Lounge / Pavuna + 2

🟠 2 trials vencem nas próximas 48h

🟠 1 tenant acima do limite contratado

🟡 4 dispositivos usando versão antiga
```

Cada item deve ser clicável e abrir:

- tenant;
- lista filtrada;
- device;
- cobrança;
- diagnóstico;

conforme o caso.

O objetivo é transformar o dashboard em ferramenta diária de operação.

---

# 46. Linha 3 — Operação dos clientes

Criar um bloco de operação.

Exemplo:

```text
OPERAÇÃO

Devices online          42 / 47       89%
POS online              31 / 34
KDS online               5 / 6
Tenants operacionais    35 / 37
```

Ao lado:

```text
PROBLEMAS OPERACIONAIS

3   Devices offline
1   Tenant restrito
2   Integrações com erro
1   Tenant em manutenção
0   Incidentes críticos
```

Essa visão deve evoluir junto com o Device Control Plane.

Princípio:

> identificar problemas antes que o cliente abra chamado.

---

# 47. Linha 4 — Receita

Adicionar gráfico de MRR dos últimos 12 meses.

Primeira versão:

```text
MRR — últimos 12 meses
```

Pode inicialmente mostrar somente:

- MRR contratado histórico.

Quando o domínio estiver pronto, evoluir para:

```text
MRR inicial
Novo MRR
Expansão
Redução
Churn
MRR atual
```

Não inventar métricas sem fonte confiável.

---

# 48. Linha 5 — Novos clientes

Criar bloco:

```text
NOVOS CLIENTES

25 Lounge               PRO       Hoje
Supermarket              PRO       Ontem
Arena Music              BASIC     28 ago
Bar do João              TRIAL     27 ago
```

Cada cliente deve abrir diretamente o Tenant 360.

---

# 49. Linha 5 — Clientes que exigem atenção

Ao lado de Novos Clientes:

```text
ATENÇÃO

Supermarket
PAST_DUE · 8 dias

Arena Music
TRIAL · vence amanhã

25 Lounge
1 POS offline
```

Essa lista deve usar sinais reais da plataforma e permitir navegação rápida.

---

# 50. Linha 6 — Distribuição da base

Adicionar visão simples de composição da carteira.

Exemplo:

```text
POR PLANO

PRO          21
BASIC        11
ENTERPRISE    3
CUSTOM        2
```

E:

```text
POR BILLING

PAID         31
FREE          4
INTERNAL      2
```

Opcionalmente:

```text
ASSINATURAS

Mensal       29
Anual         8
```

Manter simples e legível.

---

# 51. Linha 7 — Atividade recente

Adicionar feed de atividade da plataforma.

Exemplo:

```text
ATIVIDADE RECENTE                                Ver timeline →

20:47  25 Lounge registrou pagamento
20:31  CORE habilitou Ticket Validator para Supermarket
20:14  Stone P2 / Pavuna ficou offline
19:52  Novo tenant "Arena Music" criado
19:44  Support Session iniciada em Bar do João
19:31  Plano do Supermarket alterado BASIC → PRO
```

Esse componente deve evoluir para consumir Domain Events/Timeline.

---

# 52. Ações rápidas no dashboard

Adicionar no topo:

```text
[ + Novo cliente ]   [ Registrar pagamento ]   [ Mais ações ▼ ]
```

Dentro de `Mais ações`:

```text
Criar plano
Iniciar suporte
Ver dispositivos
Ver inadimplentes
Configurações
```

Priorizar ações frequentes da equipe CORE.

---

# 53. Estrutura visual conceitual do Dashboard

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Dashboard                                      + Novo cliente        │
│ Visão geral da operação CORE                  Registrar pagamento  │
├────────────────┬────────────────┬────────────────┬──────────────────┤
│ MRR            │ Clientes       │ Inadimplentes │ Trials           │
│ R$ 18.420      │ 37             │ 4              │ 6                │
│ ↑ 8,4%         │ +3 no mês      │ R$ 1.237       │ 2 vencendo       │
├────────────────────────────────┬─────────────────────────────────────┤
│ ATENÇÃO NECESSÁRIA             │ OPERAÇÃO                           │
│ 🔴 4 inadimplentes             │ Devices       42/47                │
│ 🔴 3 devices offline           │ POS           31/34                │
│ 🟠 2 trials vencendo           │ KDS            5/6                 │
│ 🟡 1 limite excedido           │ Tenants       35/37                │
├────────────────────────────────┴─────────────────────────────────────┤
│ MRR — 12 MESES                                                       │
│                     gráfico                                          │
├────────────────────────────────┬─────────────────────────────────────┤
│ NOVOS CLIENTES                 │ CLIENTES QUE EXIGEM ATENÇÃO         │
│ 25 Lounge        PRO           │ Supermarket       PAST_DUE          │
│ Arena Music      TRIAL         │ 25 Lounge         POS OFFLINE       │
│ Bar do João      BASIC         │ Arena Music       TRIAL 1 DIA       │
├────────────────────────────────┼─────────────────────────────────────┤
│ DISTRIBUIÇÃO POR PLANO         │ BILLING                             │
│ PRO 21 · BASIC 11 · ...        │ PAID 31 · FREE 4 · INTERNAL 2      │
├────────────────────────────────┴─────────────────────────────────────┤
│ ATIVIDADE RECENTE                                                    │
│ 20:47 Pagamento · 25 Lounge                                          │
│ 20:31 Módulo ativado · Supermarket                                   │
│ 20:14 POS offline · Pavuna                                           │
└──────────────────────────────────────────────────────────────────────┘
```

---

# 54. Direção visual

Manter identidade visual do CORE.

Direção:

- canvas claro;
- cards brancos;
- hierarquia visual limpa;
- azul CORE como cor principal;
- cores semânticas apenas para status;
- poucos gráficos;
- evitar dashboard genérico abarrotado;
- priorizar legibilidade e tomada de decisão.

O dashboard deve parecer ferramenta operacional de SaaS, não painel decorativo.

---

# 55. O que não colocar agora no dashboard

Não bloquear o pré-POS com:

- Health Score completo;
- Churn Probability;
- NPS;
- CAC;
- LTV;
- cohort;
- dezenas de gráficos;
- métricas sem fonte confiável.

Esses itens podem entrar em ondas posteriores.

Antes do POS, a prioridade do dashboard é:

```text
Financeiro
+
Clientes
+
Problemas
+
Devices
+
Atividade
```

Essa é a versão mínima robusta do dashboard do Platform Admin.
