# CORE POS — CONTRATO MESTRE FUNCIONAL E TÉCNICO

**Projeto:** CORE PDV / CORE POS  
**Data de consolidação:** 2026-09-04  
**Status:** especificação mestre oficial para implementação  
**Consumidor principal deste documento:** OpenCode  
**Escopo:** CORE POS V1 + contratos preparados para Stone, impressão, sincronização e evolução futura

> **REGRA DE AUTORIDADE**
>
> Este arquivo é a fonte de verdade funcional e técnica do CORE POS.
>
> O OpenCode deve implementar exatamente o que está definido aqui, respeitando a arquitetura e os serviços de domínio já existentes no CORE PDV.
>
> Se encontrar uma implementação atual incompatível com este documento:
>
> 1. identificar a incompatibilidade;
> 2. preservar dados e regras de domínio corretas;
> 3. adaptar a camada POS;
> 4. não criar uma regra paralela;
> 5. registrar a divergência no checkpoint da sprint.
>
> O CORE POS NÃO É um novo backend. Ele é um novo cliente operacional do CORE PDV.

---

# 0. REGRAS CENTRAIS DO CONTRATO

## 0.1 Configuração por máquina NÃO controla módulos/permissões


A autorização funcional é determinada por:

```text
Tenant/assinatura operacional
        ∩
Entitlements efetivos
        ∩
Configuração/feature operacional da filial quando aplicável
        ∩
RBAC/permissões do operador
        =
Ação funcional autorizada
```

O dispositivo participa apenas como:

```text
device ativo
+
vinculado à filial
+
licenciado
+
versão suportada
+
capacidade técnica necessária
```

**Configuração por máquina não concede nem remove permissão funcional.**

Exemplos de configuração válida por máquina:

- impressora de recibo;
- impressora local integrada;
- confirmação automática de venda;
- formato do recibo;
- número de vias;
- largura do papel;
- preferências de impressão;
- preferências locais de relatório;
- capacidades técnicas do hardware;
- identificação do caixa/ponto quando o modo operacional exigir;
- opções de interface realmente locais.

Exemplos de configuração PROIBIDA por máquina:

- `pode_vender = true`;
- `pode_cancelar = false`;
- `mostrar_estoque = false` como mecanismo de segurança;
- `pode_remover_10 = true`;
- `pode_aplicar_desconto = true`.

Essas decisões pertencem ao RBAC e aos entitlements.

---

## 0.2 Configuração das máquinas será centralizada no Backoffice

Não exigir que uma loja com 30, 50 ou 100 máquinas configure cada aparelho manualmente.

A configuração segue herança:

```text
Default da plataforma
        ↓
Configuração padrão da filial
        ↓
Override específico do dispositivo, quando necessário
        ↓
Configuração efetiva
```

O Backoffice é a fonte administrativa.

O POS apenas recebe e aplica sua configuração efetiva.

---

## 0.3 “Impressora local” significa a impressora integrada da Stone

No contexto do CORE POS:

```text
local_printer
```

significa a impressora física integrada ao terminal Stone quando o hardware possuir essa capacidade.

Isso é diferente de:

```text
network printer
```

que é a impressora térmica de produção acessível pela rede local.

---

## 0.4 Sincronização geral e impressão são módulos separados

A Central de Sincronização do POS NÃO é a fila de impressão.

### Sincronização geral

Abrange:

- tenant;
- filial;
- device;
- operadores;
- permissões;
- entitlements/capabilities;
- catálogo;
- configurações;
- caixa;
- estado local;
- operações pendentes;
- outbox quando existir suporte offline.

### Impressão

Abrange:

- `ProductionJob`;
- `PrintJob`;
- impressoras;
- destinos de produção;
- claim/lease;
- impressão;
- ACK;
- retry;
- reimpressão.

Os dois subsistemas podem apresentar estados na mesma interface, mas não podem compartilhar fila, modelo ou regra de negócio.

---

## 0.5 Nome de UX da venda direta

No CORE POS, o nome de UX preferencial é:

```text
Venda Rápida
```

O backend pode continuar usando o canal técnico:

```text
counter
```

Não renomear modelos/enumerações de domínio apenas por causa do texto exibido no app.

---

## 0.6 Validador de Ticket

O Home do POS deverá poder disponibilizar:

```text
Validador de Ticket
```

Produtos com:

```text
Product.emits_ticket = true
```

geram ticket.

O ticket preserva, no snapshot:

- produto;
- quantidade;
- modificadores;
- observação quando aplicável;
- venda/pedido de origem;
- operador;
- identificação necessária para conferência.

O ticket é entregue/validado no setor responsável.

---

## 0.7 O Home não usa configuração da máquina para esconder funções

Depois da autenticação do operador, o Home é calculado pelo backend a partir de:

- status do tenant;
- status da filial;
- entitlements;
- feature flags/configurações operacionais da filial;
- permissões do operador.

A máquina pode influenciar somente a **capacidade técnica** da experiência.

Exemplo:

- terminal sem impressora integrada não oferece “imprimir nesta máquina”;
- isso NÃO significa que a permissão `sales.create` deixou de existir.

---

# 1. PRINCÍPIOS INEGOCIÁVEIS

## 1.1 Uma única fonte de verdade

O backend Django atual continua sendo autoridade para:

- autenticação e autorização;
- empresa e filial;
- catálogo;
- disponibilidade por filial;
- preços;
- modificadores;
- promoções;
- taxa de serviço;
- descontos;
- pagamentos;
- vendas;
- caixas;
- comandas;
- estoque;
- tickets;
- produção;
- auditoria;
- entitlements;
- limites;
- status SaaS.

O Flutter não replica regras financeiras ou de estoque.

---

## 1.2 Arquitetura

```text
┌─────────────────────┐
│ CORE Backoffice     │
│ Next.js             │
└─────────┬───────────┘
          │
          │
          ▼
┌─────────────────────────────────────┐
│            CORE API Django          │
│                                     │
│ /api/v1/...         /api/v1/pos/... │
│       │                    │         │
│       └────────┬───────────┘         │
│                ▼                     │
│         DOMAIN SERVICES              │
│ sales / cash / commands / inventory │
│ products / production / saas / RBAC │
└────────────────┬────────────────────┘
                 │
                 ▼
             PostgreSQL
                 ▲
                 │
┌────────────────┴────────────────────┐
│ CORE POS — Flutter / Android        │
│ Stone / tablet / celular            │
└─────────────────────────────────────┘
```

---

## 1.3 Não duplicar services

O OpenCode deve procurar um service existente antes de criar outro.

Exemplos que já existem no backend e devem ser reutilizados:

- motor de preview de venda;
- finalização de venda;
- abertura/fechamento de caixa;
- sangria/suprimento;
- comandas;
- pagamento parcial de comanda;
- estoque;
- modificadores;
- produção;
- auditoria;
- RBAC.

Se for necessário criar endpoint `/api/v1/pos/...`, esse endpoint deve atuar como **adapter da API POS** para os services existentes.

---

# 2. BASE ATUAL DO BACKEND QUE O POS DEVE REUTILIZAR

A implementação atual já possui conceitos importantes.

## 2.1 Produto

O `Product` já possui, entre outros:

```text
company
category
internal_code
sku
barcode
sale_price
is_sellable
is_favorite
available_counter
available_table
available_command
participates_in_service_fee
participates_in_commission
emits_ticket
inventory_behavior
status
archived_at
```

Disponibilidade operacional real deve considerar `ProductBranchConfig`.

---

## 2.2 Produto por filial

`ProductBranchConfig` é parte obrigatória da disponibilidade operacional.

O POS não deve considerar que um produto globalmente ativo esteja automaticamente disponível naquela filial.

Para Venda Rápida:

```text
channel = counter
```

Para mesa:

```text
channel = table
```

Para comanda:

```text
channel = command
```

---

## 2.3 Venda

A finalização atual possui:

- transação atômica;
- validação de filial;
- validação de permissão;
- validação de CashSession;
- estoque;
- modificadores;
- promoções;
- descontos;
- taxa de serviço;
- pagamentos;
- idempotência;
- auditoria;
- snapshots.

O POS deve chegar ao mesmo service, não implementar uma segunda finalização.

---

## 2.4 Caixa

O backend já possui:

- `CashRegister`;
- `CashSession`;
- entradas;
- sangrias;
- fechamento;
- permissões;
- auditoria;
- idempotência de movimentações.

---

## 2.5 Comandas

O backend já trata:

- mesa;
- comanda;
- pedidos;
- itens;
- baixa de estoque;
- pagamentos parciais;
- transferência;
- merge;
- split;
- cancelamento;
- fechamento;
- venda final da comanda.

---

## 2.6 Produção e impressão

Já existem:

```text
PrinterDevice
ProductionJob
PrintJob
Ticket
```

Estados atuais de impressão:

```text
PENDING
PROCESSING
PRINTED
FAILED
CANCELLED
```

Não criar um segundo `PrintJob` exclusivo para POS.

---

## 2.7 Ticket

Já existe `Ticket` com:

```text
ISSUED
USED
CANCELLED
```

O Validador de Ticket deve evoluir esse domínio.

Não criar tabela paralela de ticket do POS.

---

# 3. IDENTIDADES DO CORE POS

Existem quatro contextos distintos:

```text
Company/Tenant
Branch
POSDevice
Operator/User
```

E, durante operações financeiras:

```text
CashRegister
CashSession
```

Toda operação crítica deve conseguir ser rastreada até:

```text
company
branch
device
operator
cash_register
cash_session
```

quando aplicável.

---

# 4. REGRA DE ESCOPO

## 4.1 Company e Branch vêm do device

Depois do pareamento:

```text
POSDevice.branch = filial
POSDevice.company = filial.company
```

O app NÃO escolhe filial no uso diário.

O app pode receber IDs no bootstrap para exibição e cache, porém endpoints operacionais não devem confiar em:

```text
company_id
branch_id
```

enviados livremente pelo Flutter.

O servidor deriva o contexto do device autenticado.

---

## 4.2 Troca de filial

Para mudar uma máquina de filial:

```text
revogar/desvincular
→ invalidar credencial
→ novo pareamento
```

Não oferecer seletor cotidiano de empresa/filial no POS.

---

# 5. DISPOSITIVO — `POSDevice`

## 5.1 Objetivo

Representar o terminal operacional pareado.

A arquitetura deve permanecer compatível com o inventário genérico futuro de Devices do CORE.

Não criar dois inventários concorrentes de hardware.

---

## 5.2 Tipos previstos

O desenho deve aceitar, sem necessariamente implementar todos agora:

```text
POS
STONE_POS
TABLET_POS
MOBILE_POS
PRINT_AGENT
KDS
TOTEM
```

Para V1, implementar somente o que for realmente utilizado.

---

## 5.3 Estados

Mínimo:

```text
PENDING
ACTIVE
BLOCKED
REVOKED
REPLACED
```

Opcionalmente o estado visual ONLINE/OFFLINE é derivado de heartbeat e não precisa substituir o estado administrativo.

### ACTIVE

Pode autenticar e operar, desde que:

- tenant operacional;
- filial operacional;
- entitlement válido;
- versão suportada;
- operador autorizado.

### BLOCKED

- preserva vínculo;
- preserva histórico;
- credenciais não operam;
- pode ser reativado.

### REVOKED

- credencial invalidada;
- sessões encerradas;
- exige novo pareamento.

### REPLACED

- histórico preservado;
- não volta a operar normalmente;
- aponta para substituição quando aplicável.

---

## 5.4 Campos mínimos

```text
id UUID
branch
name
device_type
status
app_version
os_version
device_model
hardware_identifier_hash opcional
paired_at
last_seen_at
blocked_at
revoked_at
replaced_at
replaced_by opcional
created_at
updated_at
```

Configuração operacional não precisa ficar toda na mesma tabela.

---

# 6. CREDENCIAL DO DEVICE

## 6.1 Requisitos

- gerada server-side;
- alta entropia;
- revogável;
- rotacionável;
- armazenada no app em Android Keystore/Secure Storage;
- não armazenada em texto puro no banco;
- nunca exibida novamente no Backoffice;
- escopada ao device;
- inválida após revogação.

---

## 6.2 Device ≠ operador

Ter uma máquina autenticada NÃO significa ter um usuário autenticado.

São camadas diferentes:

```text
Device Auth
      ↓
Operator Auth
      ↓
Operação
```

---

# 7. PRIMEIRO ACESSO / PAREAMENTO

## 7.1 Tela inicial

```text
[ CORE PDV ]

Digite o CNPJ da filial
ou o Código de Licenciamento

[ CNPJ OU CÓDIGO ]

Onde encontro meu código?  ?
Não tem cadastro?           ?
```

### “Onde encontro meu código?”

Pode abrir:

- vídeo;
- GIF;
- explicação visual;

mostrando onde encontrar o código no Backoffice.

### “Não tem cadastro?”

Exibir QR Code/link para landing page/onboarding do CORE.

Não implementar um cadastro improvisado dentro do POS.

---

## 7.2 Identificadores aceitos

A interface aceita:

```text
CNPJ da filial
OU
Código de Licenciamento CORE
```

CNPJ é o caminho preferencial.

O código é alternativa/fallback e é obrigatório principalmente quando a filial não possuir CNPJ próprio.

O backend pode aceitar ambos sempre.

---

# 8. CÓDIGO DE LICENCIAMENTO

## 8.1 Regras

```text
Branch.licensing_code
```

Deve ser:

- gerado no backend;
- único;
- não sequencial;
- imprevisível;
- indexado;
- rotacionável;
- auditável.

O código:

- identifica a filial;
- NÃO autentica o dispositivo sozinho;
- NÃO substitui OTP;
- NÃO é uma API key.

Rotacionar o código não revoga devices já pareados.

---

# 9. VERIFICAÇÃO DO PAREAMENTO POR OTP

## 9.1 Fonte dos contatos

Usar contatos já existentes no CORE.

Não criar cadastro paralelo obrigatório de “contato de pareamento”.

O servidor determina os canais elegíveis a partir dos dados cadastrados da empresa/filial.

Retornar somente versões mascaradas.

Exemplo:

```text
WhatsApp: (***) *****-1234
E-mail: l***@empresa.com
```

---

## 9.2 Challenge

Usar conceito genérico:

```text
AuthenticationChallenge
```

para permitir evolução futura de MFA.

Purpose inicial:

```text
POS_DEVICE_PAIRING
```

Campos conceituais:

```text
id
purpose
branch
channel
destination_fingerprint
destination_masked
code_hash
expires_at
attempts
max_attempts
resend_count
consumed_at
created_at
```

---

## 9.3 Segurança do OTP

- uso único;
- expiração;
- hash no banco;
- limite de tentativas;
- cooldown de reenvio;
- rate limit por identificador/IP/device fingerprint;
- novo OTP invalida o anterior do mesmo fluxo;
- não registrar código em log;
- não retornar código em resposta;
- sem bypass de produção.

---

# 10. CONTRATO DE PAREAMENTO — API

Os nomes abaixo são o contrato preferencial da API POS.
Se existir endpoint equivalente na arquitetura atual, reutilizar sem duplicação.

---

## 10.1 Identificar filial

```http
POST /api/v1/pos/pairing/identify/
```

### Request

```json
{
  "identifier": "12345678000190"
}
```

ou

```json
{
  "identifier": "CORE-8G4K-..."
}
```

### Response

```json
{
  "pairing_flow_id": "uuid",
  "branch": {
    "display_name": "25 Lounge — Centro"
  },
  "channels": [
    {
      "id": "opaque-channel-id",
      "type": "whatsapp",
      "masked": "(**) *****-1234"
    },
    {
      "id": "opaque-channel-id-2",
      "type": "email",
      "masked": "l***@empresa.com"
    }
  ],
  "expires_in_seconds": 600
}
```

Não retornar contato puro.

---

## 10.2 Solicitar OTP

```http
POST /api/v1/pos/pairing/request-otp/
```

### Request

```json
{
  "pairing_flow_id": "uuid",
  "channel_id": "opaque-channel-id"
}
```

### Response

```json
{
  "challenge_id": "uuid",
  "destination": "(**) *****-1234",
  "expires_in_seconds": 300,
  "resend_available_in_seconds": 60
}
```

---

## 10.3 Confirmar OTP e registrar device

```http
POST /api/v1/pos/pairing/confirm/
```

### Request

```json
{
  "challenge_id": "uuid",
  "code": "123456",
  "device": {
    "name": "Stone Bar 01",
    "device_type": "STONE_POS",
    "app_version": "1.0.0",
    "os_version": "Android ...",
    "device_model": "Stone P2"
  }
}
```

### Response

```json
{
  "device": {
    "id": "uuid",
    "name": "Stone Bar 01",
    "status": "ACTIVE"
  },
  "device_credential": "RETURNED_ONLY_ONCE",
  "bootstrap_required": true
}
```

A credencial é devolvida apenas no momento necessário e deve ser persistida em secure storage.

---

# 11. OPERADOR DO POS

## 11.1 Usuário POS pode não usar o Backoffice

Não exigir que um garçom possua login funcional no Backoffice para operar o POS.

Criar/manter gate explícito:

```text
can_access_pos
```

Este gate NÃO substitui permissões.

---

## 11.2 Elegibilidade

Um usuário aparece no seletor somente se:

```text
User ativo
+
não arquivado
+
membership ativo na empresa
+
acesso ativo à filial
+
can_access_pos = true
+
possui permissão operacional compatível
+
possui PIN POS configurado
```

Não reutilizar cegamente selectors de Backoffice que exijam `can_login = true` caso isso impeça operadores exclusivamente POS.

---

# 12. PIN DO OPERADOR

## 12.1 Regras

```text
6 dígitos numéricos exatos
```

- hash no backend;
- nunca logado;
- nunca retornado;
- não precisa ser único;
- não usar como senha Django;
- não persistir no dispositivo;
- comparação segura;
- rate limit;
- reset auditado.

---

## 12.2 Gestão no Backoffice

Na tela do usuário:

```text
Acesso ao POS: Sim / Não

PIN do POS
Status: Não configurado / Configurado

[ Enviar link para criar PIN ]
[ Redefinir PIN ]
```

Admin não vê PIN.

Admin não recebe hash.

Preferir que o próprio usuário defina por link de uso único.

---

## 12.3 Link de criação/reset

Token:

- purpose-specific;
- uso único;
- expira;
- invalidado depois da utilização;
- alta entropia;
- hash/fingerprint no backend;
- não exige login Backoffice.

Página pública:

```text
Criar PIN do CORE POS

Novo PIN
Confirmar PIN

[ SALVAR ]
```

---

# 13. RATE LIMIT DO PIN

Default inicial:

```text
5 falhas
→ bloqueio temporário de 15 minutos
```

O mecanismo deve estar isolado por combinação adequada de:

```text
device
operator
```

Não bloquear toda a filial porque um operador errou.

O bloqueio temporário do PIN não deve inativar a conta global.

---

# 14. AUTENTICAÇÃO DO OPERADOR — API

## 14.1 Listar operadores

```http
GET /api/v1/pos/operators/
```

Requer Device Auth.

### Response

```json
{
  "operators": [
    {
      "id": "uuid-or-user-id",
      "display_name": "João",
      "initials": "JS",
      "avatar_url": null
    }
  ]
}
```

Não enviar:

- e-mail completo sem necessidade;
- CPF;
- senha;
- hash PIN;
- permissions de outros usuários.

---

## 14.2 Login

```http
POST /api/v1/pos/auth/operator/
```

### Request

```json
{
  "operator_id": "uuid-or-user-id",
  "pin": "123456"
}
```

Validar novamente no servidor:

- device ACTIVE;
- credencial válida;
- company ativa;
- branch ativa;
- tenant operacional;
- entitlement POS;
- versão suportada;
- usuário ativo;
- membership;
- acesso à filial;
- `can_access_pos`;
- PIN;
- rate limit;
- RBAC mínimo.

### Response

```json
{
  "operator_session": {
    "token": "opaque-or-existing-secure-session-token",
    "expires_at": "server-defined"
  },
  "operator": {
    "id": "id",
    "display_name": "João"
  },
  "bootstrap_required": true
}
```

O formato exato do token pode reutilizar a infraestrutura segura existente.
Não introduzir JWT apenas porque “é comum” se a base atual não exigir.

---

## 14.3 Logout

```http
POST /api/v1/pos/auth/logout/
```

Encerra a sessão do operador.

NÃO revoga o device.

---

# 15. BOOTSTRAP

## 15.1 Endpoint

```http
GET /api/v1/pos/bootstrap/
```

O bootstrap é o contrato canônico de estado operacional do app.

---

## 15.2 Resposta conceitual

```json
{
  "server_time": "2026-09-04T12:00:00-03:00",

  "release": {
    "current_version": "1.0.0",
    "latest_version": "1.1.0",
    "minimum_supported_version": "1.0.0",
    "update_available": true,
    "update_required": false
  },

  "company": {
    "id": 10,
    "trade_name": "Empresa X",
    "operational": true
  },

  "branch": {
    "id": 20,
    "name": "Centro",
    "operational": true
  },

  "device": {
    "id": "uuid",
    "name": "Stone Bar 01",
    "type": "STONE_POS",
    "status": "ACTIVE",
    "capabilities": {
      "integrated_printer": true
    }
  },

  "operator": {
    "id": 50,
    "display_name": "João"
  },

  "permissions": [
    "sales.create",
    "sales.apply_discount",
    "tickets.validate"
  ],

  "modules": {
    "quick_sale": {
      "enabled": true
    },
    "commands": {
      "enabled": false,
      "reason": "permission_missing"
    },
    "ticket_validator": {
      "enabled": true
    },
    "inventory": {
      "enabled": false,
      "reason": "entitlement_or_permission_missing"
    },
    "reports": {
      "enabled": false,
      "reason": "permission_missing"
    }
  },

  "cash": {
    "mode": "FIXED",
    "register": {
      "id": 1,
      "name": "Bar"
    },
    "session": null
  },

  "settings": {
    "receipt": {
      "print_mode": "automatic",
      "format": "detailed",
      "copies": 1,
      "printer": {
        "kind": "stone_integrated"
      }
    }
  }
}
```

---

# 16. CÁLCULO DE MÓDULOS DO HOME

## 16.1 Home após login

Módulos planejados:

```text
Venda Rápida
Mesas / Comandas
Validador de Ticket
Estoque
Relatórios
Configuração/Informações do dispositivo
```

“Configuração” no POS não significa administrar permissões.
Pode exibir status e preferências locais permitidas.

---

## 16.2 Regra

Exemplo conceitual:

```text
quick_sale =
tenant_operational
AND branch_operational
AND entitlement/feature counter
AND operator has sales.create
```

```text
commands =
tenant_operational
AND branch_operational
AND feature commands
AND operator has at least commands.view/open/add_items as apropriado
```

```text
ticket_validator =
tenant_operational
AND branch_operational
AND ticket/production feature when applicable
AND operator has tickets.validate
```

```text
inventory =
tenant_operational
AND branch_operational
AND entitlement applicable
AND operator has inventory permission
```

A configuração da máquina NÃO entra como permissão.

---

# 17. CONFIGURAÇÃO POR MÁQUINA — NOVO CONTRATO

## 17.1 Administração central

Tela Backoffice:

```text
Configurações
→ Dispositivos
→ CORE POS
→ [Stone Bar 01]
```

---

## 17.2 Herança

```text
BranchPOSSettings
        ↓
POSDeviceSettings override
        ↓
effective_settings
```

Não obrigar override para tudo.

---

## 17.3 Campos previstos

### Identificação

```text
device_name
```

### Caixa/ponto

```text
cash_binding_mode = FIXED | FLEXIBLE
default_cash_register opcional
```

### Recibo/confirmação

```text
receipt_printer
sale_confirmation_print
automatic_or_manual
receipt_format = detailed | simplified
paper_width
copies
```

### Relatórios locais

```text
local_report_print_preferences
```

### Hardware

```text
sound
brightness
timeout
peripherals
```

somente quando realmente necessário e suportado.

---

## 17.4 Impressora efetiva de recibo

Exemplos:

```text
stone_integrated
printer_device:<id>
none
```

“stone_integrated” só pode ser usado se o device reportar essa capability.

---

# 18. FIXED X FLEXIBLE — CAIXA

A arquitetura deve aceitar:

```text
FIXED
```

Device possui caixa padrão definido no Backoffice.

```text
FLEXIBLE
```

Operador escolhe entre caixas permitidos da filial.

Isso é preferência/vínculo operacional, não permissão.

O backend ainda valida:

```text
cash_registers.open
cash_registers.close
...
```

---

# 19. CASHSESSION É OBRIGATÓRIA PARA VENDER

## 19.1 Regra

Nenhuma venda normal deve ser finalizada sem `CashSession` aberta e válida.

O frontend pode bloquear cedo.

O backend deve bloquear de verdade.

---

## 19.2 Permissões atuais reais do CORE

Reutilizar os códigos existentes:

```text
cash_registers.view
cash_registers.open
cash_registers.manual_entry
cash_registers.withdraw
cash_registers.close
cash_registers.add
cash_registers.change
cash_registers.change_status
cash_registers.administer_others
```

Não criar:

```text
cash.open
cash.close
```

se os códigos reais acima já existem.

---

# 20. VENDA RÁPIDA

## 20.1 Canal de domínio

UX:

```text
Venda Rápida
```

Backend:

```text
SalesChannel.COUNTER
```

---

# 21. CATÁLOGO POS

## 21.1 Endpoint

Preferencial:

```http
GET /api/v1/pos/catalog/
```

ou reutilizar o catálogo atual com contrato POS enxuto.

---

## 21.2 Filtro obrigatório

Somente produtos:

- ativos;
- não arquivados;
- vendáveis;
- com `ProductBranchConfig` da filial;
- `is_available = true`;
- disponíveis em `counter`;
- respeitando categoria/config efetiva.

---

## 21.3 Payload enxuto

```json
{
  "id": 100,
  "name": "Cerveja",
  "internal_code": "CERV01",
  "barcode": "789...",
  "category": {
    "id": 5,
    "name": "Bebidas"
  },
  "price": "10.00",
  "image": null,
  "favorite": true,
  "emits_ticket": true,
  "modifier_groups": []
}
```

Não enviar custo para operador sem permissão e sem necessidade.

---

# 22. BUSCA POR CÓDIGO DE BARRAS

```http
GET /api/v1/pos/products/barcode/{barcode}/
```

Busca exata no escopo do device/branch.

Não permitir produto de outra empresa/filial por IDOR.

---

# 23. CARRINHO LOCAL

O carrinho Flutter guarda somente intenção:

```text
client_item_id
product_id
quantity
selected_modifiers
notes
```

O Flutter pode exibir estimativa local, porém o valor oficial vem do backend.

Nunca confiar no preço enviado pelo app.

---

# 24. MODIFICADORES

Reutilizar integralmente o domínio atual.

O POS deve respeitar:

- grupo;
- opções;
- mínimo;
- máximo;
- quantidade selecionada;
- preço adicional;
- efeitos de estoque;
- substituição de componentes;
- snapshots históricos.

Não reimplementar validação de mínimo/máximo em um segundo motor.

O Flutter pode validar para UX, mas o backend valida novamente.

---

# 25. PREVIEW DE VENDA

```http
POST /api/v1/pos/sales/preview/
```

### Request conceitual

```json
{
  "items": [
    {
      "client_item_id": "uuid",
      "product": 100,
      "quantity": "2",
      "modifiers": []
    }
  ],
  "discount": "0.00",
  "service_fee_waived": false
}
```

### Backend

Chamar motor financeiro existente.

### Response

```json
{
  "subtotal": "20.00",
  "promotion_discount_total": "0.00",
  "item_discount_total": "0.00",
  "discount": "0.00",
  "service_fee_rate": "10.00",
  "service_fee_amount": "2.00",
  "total": "22.00",
  "items": []
}
```

---

# 26. DESCONTOS E TAXA DE SERVIÇO

## 26.1 Permissões reais existentes

```text
sales.apply_discount
sales.apply_item_discount
sales.waive_service_fee
```

Reutilizar.

Não inventar nomes novos sem necessidade.

---

## 26.2 Autorizações pontuais

Se o backend atual suportar autorização por terceiro/supervisor, o POS pode expor a UX correspondente.

A regra continua no servidor.

---

# 27. FINALIZAÇÃO DE VENDA

Preferencial:

```http
POST /api/v1/pos/sales/
```

O endpoint deve adaptar o payload para `finalize_sale()` existente.

---

## 27.1 Request conceitual

```json
{
  "idempotency_key": "uuid-gerado-no-device",

  "items": [
    {
      "client_item_id": "uuid",
      "product": 100,
      "quantity": "2",
      "modifiers": []
    }
  ],

  "payments": [
    {
      "payment_method": 1,
      "amount": "22.00"
    }
  ],

  "discount": "0.00",
  "service_fee_waived": false
}
```

---

## 27.2 Servidor deriva

Não confiar livremente em:

```text
company
branch
device
operator
cash session
channel
price
cost
stock result
permissions
```

---

## 27.3 Resultado

A venda deve registrar/rastrear:

```text
created_by/operator
POSDevice
CashSession
branch
company
```

Se modelos históricos atuais não possuírem `device`, adicionar vínculo/snapshot sem quebrar histórico anterior.

---

# 28. IDEMPOTÊNCIA

## 28.1 Venda

Toda finalização usa:

```text
idempotency_key
```

Gerada no client antes do primeiro envio.

Retry da mesma intenção:

```text
mesma key
+
mesmo fingerprint
=
mesma venda
```

Mesma key com payload diferente:

```text
idempotency_key_conflict
```

---

## 28.2 Nunca gerar nova key em retry automático

Se ocorreu timeout após envio:

ERRADO:

```text
retry
→ gerar nova UUID
→ pode duplicar venda
```

CERTO:

```text
retry
→ reutilizar UUID original
```

---

# 29. TICKETS

## 29.1 Emissão

Produto:

```text
Product.emits_ticket = true
```

Ao confirmar a operação correspondente:

- venda rápida finalizada;
- item de comanda confirmado;

o backend cria `Ticket`.

Não criar ticket duplicado ao fechar a comanda se o item já gerou ticket.

---

## 29.2 Snapshot

O ticket deve congelar informações necessárias para entrega:

```text
ticket number
validation code
product
quantity
modifiers
notes
source
sale/order/command context
table when applicable
operator
issued_at
```

Usar `identification_snapshot` ou estrutura histórica equivalente.

---

## 29.3 Modificadores no ticket

Obrigatório.

Exemplo:

```text
WHISKY
2x

MODIFICADORES
+ Red Bull Tropical
+ Gelo de coco
```

O validador deve exibir essas informações antes da confirmação quando necessário.

---

# 30. VALIDADOR DE TICKET

## 30.1 Home

Adicionar módulo:

```text
Validador de Ticket
```

Aparece somente quando operador possui autorização.

---

## 30.2 Permissão

O RBAC atual possui:

```text
tickets.view
tickets.reprint
```

Para validar, adicionar SOMENTE se ainda não existir equivalente:

```text
tickets.validate
```

Essa é uma nova permissão legítima porque “visualizar ticket” não equivale a consumi-lo.

---

## 30.3 Código para leitura

O `Ticket.number` atual é útil para visualização humana.

Para leitura segura por QR/barcode, adicionar código opaco se ainda não existir:

```text
validation_code
```

Requisitos:

- server-side;
- único no escopo necessário;
- imprevisível;
- indexado;
- não depender somente de número sequencial.

O número humano continua existindo.

---

## 30.4 Estados

Reutilizar:

```text
ISSUED
USED
CANCELLED
```

### ISSUED

Pode ser validado.

### USED

Já entregue.

### CANCELLED

Não pode ser entregue.

---

## 30.5 Endpoint

```http
POST /api/v1/pos/tickets/validate/
```

### Request por leitura

```json
{
  "validation_code": "opaque-code",
  "idempotency_key": "uuid"
}
```

Manual fallback, se aprovado na UI:

```json
{
  "ticket_number": 12345,
  "idempotency_key": "uuid"
}
```

Sempre escopar à branch do device.

---

## 30.6 Validação atômica

Backend:

1. autentica device;
2. autentica operador;
3. exige `tickets.validate`;
4. trava ticket;
5. confirma mesma branch;
6. verifica `ISSUED`;
7. muda para `USED`;
8. define `used_at`;
9. registra operador;
10. registra device;
11. audita;
12. responde snapshot.

Adicionar campos quando necessários:

```text
used_by
used_device
```

ou snapshots equivalentes.

---

## 30.7 Segundo uso

Se outro operador tentar usar ticket já utilizado:

```json
{
  "code": "ticket_already_used",
  "message": "Este ticket já foi utilizado.",
  "details": {
    "used_at": "...",
    "used_by": "..."
  }
}
```

Não marcar novamente.

---

## 30.8 Ticket cancelado

```json
{
  "code": "ticket_cancelled",
  "message": "Este ticket foi cancelado.",
  "details": {}
}
```

---

## 30.9 Estoque

Validar ticket NÃO baixa estoque.

Estoque já foi tratado na venda/pedido de origem.

---

## 30.10 CashSession

Validação de ticket não é venda.

Não exigir CashSession aberta apenas para validar/entregar ticket.

---

# 31. MESAS E COMANDAS

## 31.1 Conceitos continuam separados

```text
Table
Command
Order
OrderItem
```

Não fundir entidades.

---

## 31.2 Estoque

Item confirmado em comanda baixa estoque conforme o domínio atual.

Fechar comanda NÃO faz segunda baixa.

---

## 31.3 Contratos POS

Preferir API agregada e idempotente.

### Mapa de mesas

```http
GET /api/v1/pos/tables/
```

### Abrir comanda

```http
POST /api/v1/pos/commands/
```

Com:

```text
client_command_id
ou
idempotency_key
```

### Criar pedido atômico

```http
POST /api/v1/pos/commands/{command_id}/orders/
```

Request:

```json
{
  "idempotency_key": "uuid",
  "client_order_id": "uuid",
  "items": [
    {
      "client_item_id": "uuid",
      "product": 100,
      "quantity": "1",
      "modifiers": [],
      "notes": "Sem gelo"
    }
  ]
}
```

Backend deve:

```text
validar tudo
→ criar order
→ criar itens
→ confirmar conforme regra
→ baixar estoque
→ gerar produção
→ gerar ticket quando emits_ticket
→ responder
```

sem operação parcial acidental.

---

# 32. PERMISSÕES REAIS DE COMANDA

Reutilizar:

```text
commands.view
commands.open
commands.add_items
commands.cancel_items
commands.finalize
commands.transfer
commands.transfer_items
commands.merge
commands.split
commands.payments.view
commands.payments.record
commands.payments.reverse
```

Não criar duplicatas com nomes parecidos.

---

# 33. PAGAMENTO PARCIAL DE COMANDA

Reutilizar domínio atual.

O POS deve poder:

- visualizar pagamentos;
- registrar pagamento parcial;
- estornar pagamento quando autorizado;
- ver saldo restante;
- finalizar quando regra permitir.

Cada ação respeita sua permissão real.

---

# 34. IMPRESSÃO — VISÃO GERAL

Existem dois grandes usos:

```text
1. Produção
2. Recibo/confirmação para cliente/loja
```

Não misturar semânticas.

---

# 35. IMPRESSÃO DE PRODUÇÃO

## 35.1 Prioridade

Arquitetura preferencial:

```text
CORE POS / Stone
        │
        │ LAN local
        ▼
Impressora da cozinha/bar/copa
```

Não exigir PC.

Não exigir Print Agent em loja simples.

---

## 35.2 Roteamento

Fonte de verdade:

```text
Product
   ↓
ProductionDestination / Setor
   ↓
PrinterDevice(s)
```

Exemplos:

```text
Pizza → Cozinha → Impressora Cozinha
Whisky → Bar → Impressora Bar
Café → Copa → Impressora Copa
```

---

## 35.3 Backend ainda registra jobs

Preservar:

```text
ProductionJob
PrintJob
```

O fato de a impressão física ser local não remove rastreabilidade no servidor.

---

# 36. CLAIM / LEASE / ACK DE PRINTJOB

O modelo atual já usa:

```text
PENDING
PROCESSING
PRINTED
FAILED
CANCELLED
```

Não trocar para `CLAIMED` sem necessidade.

Usar:

```text
PENDING
→ PROCESSING
→ PRINTED | FAILED
```

---

## 36.1 Claim

Preferencial:

```http
POST /api/v1/pos/print-jobs/claim/
```

O servidor seleciona jobs imprimíveis pela filial/device.

Ao claim:

- lock transacional;
- muda para `PROCESSING`;
- registra executor device;
- registra lease;
- incrementa attempts quando apropriado.

Adicionar se necessário:

```text
processing_device
lease_expires_at
```

---

## 36.2 Lease

Se o app morrer após claim:

```text
lease expira
→ job pode voltar a ser elegível
```

Evitar ficar preso eternamente em PROCESSING.

---

## 36.3 ACK

```http
POST /api/v1/pos/print-jobs/{id}/ack/
```

Sucesso:

```json
{
  "status": "printed"
}
```

Falha:

```json
{
  "status": "failed",
  "error_code": "network_unreachable",
  "error_message": "..."
}
```

Backend normaliza mensagens e não armazena secrets.

---

# 37. PAYLOAD DO TICKET DE PRODUÇÃO

Deve conter snapshot suficiente para imprimir sem novas consultas:

```text
setor
mesa
comanda
pedido
produto
quantidade
modificadores
observação
operador
horário
tipo do evento
```

Cancelamento deve ser distinguível visualmente.

---

# 38. INTERNET OSCILANDO DURANTE IMPRESSÃO

Se o POS já recebeu o job e possui dados necessários:

```text
imprimir localmente
→ persistir ACK pendente
→ enviar ACK quando conexão voltar
```

Isso é diferente de criar uma nova venda offline.

---

# 39. PRINT AGENT

Futuro/alternativa para:

- Windows;
- USB;
- impressoras legadas;
- topologias especiais.

Não é dependência da operação comum do CORE POS.

---

# 40. RECIBO NÃO FISCAL / VIA CLIENTE / VIA LOJA

Configuração central por filial + override por device.

Opções possíveis:

```text
printer = stone_integrated | printer_device | none
print_confirmation = automatic | manual | disabled
format = detailed | simplified
copies = N
paper_width = ...
```

O recibo desta etapa é não fiscal.

Não transformar em NFC-e/SAT/fiscal sem o módulo fiscal.

---

# 41. STONE — IMPRESSORA INTEGRADA

Quando `device_type = STONE_POS` e hardware suportar:

```text
capabilities.integrated_printer = true
```

O Backoffice pode selecionar:

```text
Impressora local da máquina
```

que resolve para a impressora integrada Stone.

Não criar um `PrinterDevice` fake de rede apontando para a Stone.

---

# 42. SINCRONIZAÇÃO GERAL DO APP

## 42.1 Indicador

Exibir pequeno indicador no menu/interface:

```text
Sincronizado
Sincronizando
Pendências
Erro
```

---

## 42.2 Ao tocar

Abrir:

```text
Central de Sincronização
```

---

## 42.3 Central de Sincronização

Exibir:

- status geral;
- heartbeat;
- última sincronização;
- itens sincronizados;
- operações pendentes;
- erros;
- filtros;
- horário;
- tentativa;
- mensagem resumida.

Ações:

```text
[ Sincronizar agora ]
[ Tentar novamente itens com erro ]
```

---

# 43. O QUE A SINCRONIZAÇÃO GERAL ABRANGE

```text
tenant
branch
device status
device config
operator list
operator session validity
permissions
entitlements
feature flags
catalog
branch product config
cash registers
cash session
version gate
local operational settings
pending transaction outbox quando suportada
```

Não sincronizar “o banco inteiro”.

---

# 44. O QUE NÃO ENTRA NA FILA DE SINCRONIZAÇÃO GERAL

Não tratar como item genérico de sync:

```text
PrintJob
```

Impressão possui estado próprio.

A Central pode mostrar um resumo/link:

```text
Impressão: 2 pendentes
```

mas o processamento permanece no módulo de impressão.

---

# 45. BOOTSTRAP X SYNC

### Bootstrap

Snapshot operacional completo necessário para iniciar/recuperar o app.

### Sync incremental

Atualizações posteriores.

Na primeira versão, pode reutilizar bootstrap em alguns refreshes se o volume for aceitável.

Não criar arquitetura de delta/cursor excessivamente complexa antes de existir necessidade.

---

# 46. HEARTBEAT

Preferencial:

```http
POST /api/v1/pos/heartbeat/
```

Request:

```json
{
  "app_version": "1.0.0",
  "os_version": "...",
  "capabilities": {
    "integrated_printer": true
  }
}
```

Backend atualiza:

```text
last_seen_at
app_version
metadata permitida
capabilities técnicas permitidas
```

Não criar AuditLog imutável para cada heartbeat.

---

# 47. ONLINE/OFFLINE

Online/offline é estado derivado do heartbeat.

Não confundir:

```text
OFFLINE visual
```

com:

```text
BLOCKED administrativo
```

Um device offline pode voltar sozinho.

Um device blocked não deve operar ao voltar.

---

# 48. VERSIONAMENTO DO APP

Backend/platform config mantém:

```text
latest_version
minimum_supported_version
```

---

## 48.1 Update available

```text
current < latest
AND
current >= minimum
```

Pode operar, mostrando atualização disponível.

---

## 48.2 Update required

```text
current < minimum
```

Bloquear operação.

Sem:

```text
Continuar mesmo assim
```

---

# 49. RESILIÊNCIA V1 — ONLINE-FIRST

Decisão:

```text
CORE POS V1 = ONLINE-FIRST
```

Não prometer offline transacional completo.

---

# 50. OUTBOX LOCAL

Quando uma operação for oficialmente habilitada para fila local:

Guardar:

```text
local_operation_id
operation_type
idempotency_key
payload
created_at
last_attempt_at
attempt_count
status
last_error
```

Estados locais:

```text
PENDING
SENDING
CONFIRMED
ERROR
```

---

# 51. REGRAS DA OUTBOX

- idempotency key nasce antes do primeiro envio;
- retry mantém a mesma key;
- resposta confirmada encerra item;
- erro de negócio definitivo não fica em retry infinito;
- erro de rede pode ser reenviado;
- operator/device originais devem ser preservados quando necessário;
- logout não pode apagar operação pendente;
- revogação do device deve impedir envio até reconciliação adequada.

---

# 52. OFFLINE COMPLETO — FUTURO

Somente com especificação própria.

Exigirá:

- banco local;
- política de estoque concorrente;
- múltiplos devices offline;
- resolução de conflitos;
- preços/promos expirados;
- autorização;
- pagamentos;
- reconciliação.

Não implementar escondido dentro da V1.

---

# 53. STONE — PAGAMENTOS

Stone será provider de pagamento, não o domínio financeiro inteiro.

Usar abstração que permita futuro:

```text
Stone
PagBank
outros providers
```

Não implementar API Stone sem documentação oficial vigente.

---

# 54. `PaymentTransaction`

Preparar entidade de transação de adquirente.

Estados conceituais:

```text
INITIATED
PROCESSING
APPROVED
DECLINED
CANCELLED
REFUNDED
RECONCILIATION_NEEDED
```

---

# 55. DADOS PERMITIDOS DE TRANSAÇÃO

Guardar somente o necessário e permitido:

```text
provider
device
external_transaction_id
NSU
authorization_code
brand
installments
amount
status
timestamps
```

Nunca:

```text
PAN completo
CVV
dados sensíveis não necessários
```

---

# 56. FLUXO STONE

```text
Operador finaliza carrinho
        ↓
CORE cria intenção/idempotency context
        ↓
Stone inicia pagamento
        ↓
APPROVED
        ↓
CORE finaliza venda usando service canônico
        ↓
Payment registrado
        ↓
PaymentTransaction ligado à venda
```

---

# 57. APPROVED WITHOUT SALE

Caso crítico:

```text
Stone aprovou
+
CORE não confirmou venda
```

Nunca simplesmente tentar cobrar novamente.

Marcar:

```text
RECONCILIATION_NEEDED
```

Permitir:

- recuperar venda;
- reconciliar;
- estornar conforme provider;
- auditar.

---

# 58. CANCELAMENTO/ESTORNO STONE

Exige:

- permissão;
- motivo;
- provider transaction;
- auditoria;
- idempotência.

Não alterar Payment local sem coordenar status da transação quando integração estiver ativa.

---

# 59. ESTOQUE NO POS

Módulo futuro do mesmo app.

Não criar app separado.

---

## 59.1 Permissões reais atuais

Reutilizar:

```text
inventory.view
inventory.move
inventory.entry
inventory.exit
inventory.adjust
inventory.regularize
inventory.change_minimum
inventory.view_history
inventory.view_stock_kpis
inventory.view_stock_costs
inventory.transfer.view
inventory.transfer.create
inventory.transfer.dispatch
inventory.transfer.receive
inventory.transfer.resolve
inventory.loss.record
inventory.count.perform
inventory.report.view
```

---

## 59.2 Contar ≠ ajustar

Quem possui:

```text
inventory.count.perform
```

não automaticamente possui:

```text
inventory.adjust
```

Preservar separação.

---

# 60. RELATÓRIOS NO POS

O operador pode receber visões conforme RBAC.

Reutilizar permissions reais quando possível:

```text
sales.view
reports.view_sales
reports.view_cash
reports.view_receipts
reports.view_team
commissions.view
...
```

Se existir necessidade de “somente minhas vendas”, preferir filtro de escopo no backend.

Só criar permissão nova se a semântica atual não cobrir o caso.

---

# 61. CONFIGURAÇÃO/STATUS NO APP

Pode mostrar:

```text
device name
branch
app version
last sync
sync state
printer status
cash binding
operator
heartbeat
```

Não permitir pelo app alterar:

- RBAC;
- plano;
- entitlement;
- filial;
- device licensing;
- permissões;
- configurações administrativas críticas,

salvo fluxo explicitamente definido.

---

# 62. ENTITLEMENTS DO POS

O modelo comercial continua:

```text
Plan
→ PlanVersion
→ Subscription
→ Entitlements
→ Overrides/Add-ons
→ Effective Entitlements
→ Usage
```

O POS consome **entitlements efetivos**.

---

## 62.1 Capabilities

Reutilizar capacidades existentes quando elas representam a regra.

Exemplos atuais:

```text
feature.tables
feature.commands
feature.counter
feature.consumption
feature.cash_register
feature.production
```

Para licenciar o POS em si, criar somente se necessário:

```text
pos.enabled
```

Para limite de devices, capability/recurso dedicado:

```text
pos.devices.max
```

com escopo por filial conforme arquitetura comercial.

Não criar uma capability diferente para cada botão sem necessidade.

---

# 63. LIMITE DE DEVICES

Regra comercial:

```text
limite por filial
```

Preparar:

- ilimitado;
- limite numérico;
- add-on;
- override por tenant;
- histórico/auditoria.

Ao atingir limite:

- não derrubar devices ativos aleatoriamente;
- bloquear novo pareamento;
- retornar erro de negócio claro;
- permitir replacement quando aplicável.

---

# 64. REPLACEMENT

Fluxo:

```text
device antigo
→ REPLACED

device novo
→ ACTIVE
```

Replacement não equivale a simples exclusão.

Preservar histórico do device antigo.

---

# 65. SUSPENSÃO DO TENANT

Suspender tenant:

- não apaga device;
- não desvincula automaticamente;
- retira autorização operacional.

Ao reativar financeiramente, device ainda existe e volta conforme regras vigentes.

Suspensão administrativa continua separada da financeira.

---

# 66. API POS — NAMESPACE

Usar:

```text
/api/v1/pos/
```

Não misturar endpoints POS dentro de caminhos aleatórios sem necessidade.

A camada `/pos/` deriva contexto do device.

---

# 67. CONTRATO DE ERROS

O backend atual possui `DomainValidationError`:

```json
{
  "code": "machine_readable_code",
  "message": "Mensagem humana.",
  "details": {}
}
```

O POS deve preferir esse formato para regras de negócio que precisam de tratamento específico.

---

## 67.1 Códigos importantes

Exemplos:

```text
device_blocked
device_revoked
device_replaced
device_limit_reached
unsupported_app_version
tenant_not_operational
branch_not_operational
operator_not_eligible
pin_invalid
pin_rate_limited
cash_session_required
idempotency_key_conflict
product_unavailable
ticket_already_used
ticket_cancelled
print_job_lease_conflict
payment_reconciliation_required
```

Não usar texto de mensagem como chave lógica no Flutter.

---

# 68. HTTP STATUS — DIRETRIZ

Usar semanticamente:

```text
200 OK
201 Created
204 No Content
400 regra/input inválido
401 autenticação ausente/inválida
403 autenticado sem autorização
404 recurso não existe no escopo
409 conflito/idempotência/estado concorrente quando apropriado
423/429 somente se arquitetura atual justificar
500 erro inesperado
```

Não vazar existência de recurso de outra filial.

---

# 69. SEGURANÇA

## 69.1 Nunca confiar no Flutter

O Flutter é cliente não confiável.

Validar sempre no servidor:

- tenant;
- branch;
- device;
- operator;
- permissions;
- entitlement;
- status;
- versão;
- CashSession;
- produto;
- preço;
- modificadores;
- pagamento;
- estoque.

---

## 69.2 Secrets

Nunca retornar:

- hash de PIN;
- hash de OTP;
- device credential persistida;
- secrets de Stone;
- credenciais de printer bridge;
- secrets de integrações.

---

## 69.3 CORS/CSRF/Auth

Device API não deve depender de cookie/CSRF do Backoffice.

Usar autenticação própria adequada a cliente nativo.

Não enfraquecer as proteções do Backoffice para fazer o POS funcionar.

---

# 70. AUDITORIA

Auditar ações de negócio e segurança.

---

## 70.1 Device

```text
pos_device.paired
pos_device.blocked
pos_device.reactivated
pos_device.revoked
pos_device.replaced
pos_device.config_changed
```

---

## 70.2 Operador

```text
pos_operator.login
pos_operator.logout
pos_pin.setup
pos_pin.reset
```

Não registrar PIN.

---

## 70.3 Operações

Vendas, caixa, comandas, tickets, impressão e estoque já devem continuar entrando nas auditorias dos seus próprios domínios.

Adicionar `device_id` em metadata/campo quando útil.

---

## 70.4 Heartbeat

Não criar AuditLog para cada heartbeat.

Isso geraria volume sem valor de auditoria.

---

# 71. EVENTOS DE DOMÍNIO

Preservar arquitetura preparada para eventos como:

```text
device.paired
device.offline
sale.finalized
ticket.issued
ticket.used
print_job.failed
stone.transaction.failed
```

Não introduzir message broker apenas para dizer que existe event-driven.

Usar estrutura atual e evoluir quando necessário.

---

# 72. PERMISSÕES REAIS DO CORE RELEVANTES AO POS

Esta lista é baseada no RBAC atual e deve ser pesquisada no código antes de adicionar qualquer código novo.

## Produtos

```text
products.view
products.configure_branch
products.configure_destinations
modifiers.view
```

## Caixa

```text
cash_registers.view
cash_registers.open
cash_registers.manual_entry
cash_registers.withdraw
cash_registers.close
cash_registers.administer_others
```

## Vendas

```text
sales.create
sales.view
sales.cancel
sales.apply_discount
sales.apply_item_discount
sales.waive_service_fee
sales.create_consumption
sales.view_consumption
sales.cancel_consumption
```

## Comandas

```text
commands.view
commands.open
commands.add_items
commands.cancel_items
commands.finalize
commands.transfer
commands.transfer_items
commands.merge
commands.split
commands.payments.view
commands.payments.record
commands.payments.reverse
```

## Produção

```text
production.view
printers.manage
print_jobs.view
print_jobs.retry
print_jobs.reprint
tickets.view
tickets.reprint
```

## Estoque

Consultar seção específica.

## Relatórios

Reutilizar `reports.*` existentes.

---

# 73. NOVAS PERMISSÕES QUE PODEM SER NECESSÁRIAS

Adicionar apenas após busca no catálogo atual.

Prováveis:

```text
pos.operate
pos_devices.view
pos_devices.manage
pos_devices.block
pos_devices.revoke
tickets.validate
```

Não criar permissões como:

```text
pos.sell
pos.discount
pos.cash_open
```

porque as permissões reais de domínio já existem.

---

# 74. MODELOS POS — PROPOSTA DE RESPONSABILIDADE

O OpenCode deve adaptar ao padrão existente do projeto.

Não é obrigatório usar exatamente estes nomes se houver abstração existente melhor.

---

## 74.1 POSDevice

Responsável por:

- identidade do hardware;
- branch;
- status;
- versão;
- heartbeat;
- capabilities;
- lifecycle.

---

## 74.2 POSDeviceCredential

Responsável por:

- autenticação revogável;
- hash;
- created_at;
- revoked_at;
- rotation.

Pode ser embutido em modelo seguro equivalente se a arquitetura atual preferir.

---

## 74.3 POSOperatorCredential / PIN

Responsável por:

- user;
- PIN hash;
- configured_at;
- reset metadata;
- lock/rate-limit state quando apropriado.

Não reutilizar `User.password`.

---

## 74.4 POSOperatorSession

Responsável por:

- device;
- operator;
- branch;
- started_at;
- expires_at;
- ended_at;
- last_seen;
- revogação.

Pode reutilizar infraestrutura de session/token existente se mantiver essas garantias.

---

## 74.5 POSDeviceSettings

Responsável por override do device.

Não armazenar RBAC.

---

## 74.6 BranchPOSSettings

Responsável por defaults da filial.

Pode estar dentro de settings existentes se isso for mais coerente.

---

# 75. SINCRONIZAÇÃO — MODELO LOCAL FLUTTER

A Central de Sincronização é principalmente responsabilidade do cliente.

Estruturas locais conceituais:

```text
SyncState
SyncHistoryItem
OutboxItem
CachedBootstrap
CachedCatalog
```

Não criar tabelas Django para cada item de UI da sync center sem necessidade.

---

# 76. FLUTTER — ARQUITETURA

Criar somente depois do POS-0 backend.

Separar:

```text
networking
secure storage
device auth
operator auth
bootstrap
sync
catalog
cart
sales
cash
commands
tickets
printing
stone
inventory
reports
local persistence
UI
```

Não fazer request HTTP diretamente em widgets.

---

# 77. SECURE STORAGE

Secrets:

```text
device credential
operator session token
```

devem usar Keystore/secure storage.

Não usar SharedPreferences puro.

Nunca persistir PIN.

---

# 78. HOME / UX

## Antes de operador

```text
CORE PDV

Empresa X — Filial Y

Quem está operando?

[ João ▼ ]

PIN
[ • • • • • • ]

[ ENTRAR ]

↻ Atualizar / Sincronizar

Dispositivo: Stone Bar 01
Versão: 1.0.0
```

---

## Depois de operador

Exemplo:

```text
Olá, João

[ Venda Rápida ]
[ Mesas / Comandas ]
[ Validador de Ticket ]
[ Estoque ]
[ Relatórios ]

Sincronizado ✓
Caixa: Bar — Aberto
```

Renderizar somente módulos autorizados pelo backend.

---

# 79. CENTRAL DE SINCRONIZAÇÃO — UX

```text
Sincronização

Status: Sincronizado
Última sincronização: 10:32
Heartbeat: Online

Pendências: 0
Erros: 0

[ Sincronizar agora ]

Histórico
✓ Catálogo atualizado
✓ Permissões atualizadas
✓ Caixa atualizado
```

Com erro:

```text
! Venda local #ABC
  Erro de conexão
  3 tentativas

[ Tentar novamente ]
```

---

# 80. CONFIGURAÇÃO DE IMPRESSORAS NO BACKOFFICE

Separar:

```text
Impressoras da filial
Rotas de produção
Configuração de recibo
Overrides de devices
```

---

## 80.1 Filial

Exemplo:

```text
Impressora Cozinha
connection: network
host: 192.168.1.50
port: 9100
destination: Cozinha
```

---

## 80.2 Device

Exemplo:

```text
Stone Bar 01

Recibo:
  Impressora = Local da Stone
  Automático = Sim
  Formato = Detalhado
  Vias = 1
```

Isso não muda quais vendas o operador pode realizar.

---

# 81. STATUS DE IMPRESSORA

Pode reaproveitar:

```text
NOT_TESTED
ONLINE
OFFLINE
BRIDGE_UNAVAILABLE
FAILED
```

Para network printer utilizada diretamente pelo POS, atualizar status com testes/ACKs adequados.

Não marcar online apenas porque o registro existe.

---

# 82. RECEIPT X PRODUCTION TICKET X REDEEMABLE TICKET

São três conceitos diferentes.

## Receipt

Comprovante/recibo não fiscal da venda.

## Production ticket

Pedido que sai na cozinha/bar/copa.

## Redeemable Ticket

Ticket emitido para produto com `emits_ticket`, validado depois para entrega.

Não usar a mesma entidade para os três.

---

# 83. FLUXO COMPLETO — PRIMEIRO ACESSO

```text
App abre
  ↓
não possui device credential
  ↓
Tela CNPJ/Código
  ↓
Identify
  ↓
Branch encontrada
  ↓
Canais mascarados
  ↓
Usuário escolhe canal
  ↓
OTP
  ↓
Confirm
  ↓
POSDevice ACTIVE
  ↓
credential no secure storage
  ↓
Bootstrap device
  ↓
Lista de operadores
  ↓
PIN
  ↓
Operator Session
  ↓
Bootstrap autenticado
  ↓
Home
```

---

# 84. FLUXO COMPLETO — ABERTURA NORMAL DO APP

```text
App abre
  ↓
lê device credential
  ↓
valida/heartbeat
  ↓
device ACTIVE?
  ├─ não → tela bloqueada
  └─ sim
       ↓
version gate
       ├─ update required → bloquear
       └─ ok
            ↓
sync/bootstrap
            ↓
lista operadores
            ↓
PIN
            ↓
Home
```

---

# 85. FLUXO — VENDA RÁPIDA

```text
Operador autenticado
  ↓
Venda Rápida
  ↓
CashSession aberta?
  ├─ não
  │   ├─ tem cash_registers.open → oferecer abrir
  │   └─ sem permissão → bloquear venda
  │
  └─ sim
       ↓
catálogo da filial
       ↓
carrinho
       ↓
modificadores
       ↓
preview backend
       ↓
pagamento
       ↓
idempotency_key
       ↓
finalize_sale()
       ↓
estoque
       ↓
tickets emits_ticket
       ↓
production jobs
       ↓
recibo/print
       ↓
sucesso
```

---

# 86. FLUXO — COMANDA

```text
Operador
  ↓
Mesas/Comandas
  ↓
seleciona/abre comanda
  ↓
adiciona pedido
  ↓
POST order atômico + idempotente
  ↓
confirma itens
  ↓
baixa estoque
  ↓
production jobs
  ↓
tickets emits_ticket
  ↓
comanda permanece aberta
  ↓
pagamentos parciais quando houver
  ↓
finalize command
  ↓
gera venda final
  ↓
NÃO baixa estoque novamente
  ↓
NÃO cria ticket duplicado
```

---

# 87. FLUXO — VALIDADOR DE TICKET

```text
Operador
  ↓
Validador de Ticket
  ↓
scanner/código
  ↓
backend trava Ticket
  ↓
branch correta?
  ↓
ISSUED?
  ├─ USED → mostrar já utilizado
  ├─ CANCELLED → mostrar cancelado
  └─ ISSUED
       ↓
mostrar item/modificadores
       ↓
validar
       ↓
USED + used_at + used_by + device
       ↓
auditoria
       ↓
entregar produto
```

---

# 88. FLUXO — IMPRESSÃO PRODUÇÃO

```text
Venda/Pedido confirmado
  ↓
ProductionJob
  ↓
Product → Destination
  ↓
PrintJob(s)
  ↓
POS claim
  ↓
PROCESSING + lease
  ↓
impressão LAN
  ↓
ACK
  ├─ PRINTED
  └─ FAILED
```

---

# 89. FLUXO — SINCRONIZAÇÃO

```text
Sync acionado
  ↓
validar device/version
  ↓
flush outbox elegível
  ↓
bootstrap/refresh de dados
  ↓
atualizar cache
  ↓
revalidar operator/permissions
  ↓
registrar resultado local
  ↓
indicador:
SYNCED | PENDING | ERROR
```

Impressão fica fora dessa fila.

---

# 90. FLUXO — BLOQUEIO REMOTO

```text
Admin bloqueia device
  ↓
backend status = BLOCKED
  ↓
qualquer operação nova é negada imediatamente
  ↓
heartbeat/sync percebe
  ↓
POS mostra tela bloqueada
```

Não depender da próxima sincronização para a segurança:
o backend deve negar desde o momento da alteração.

---

# 91. TESTES OBRIGATÓRIOS — POS-0

## Pairing

- CNPJ correto;
- licensing code correto;
- identificador inválido;
- branch inativa;
- tenant suspenso;
- OTP expirado;
- OTP errado;
- OTP consumido;
- resend;
- brute force;
- limite de devices;
- replacement.

## Device Auth

- credential válida;
- inválida;
- revogada;
- blocked;
- replaced;
- outra branch;
- versão abaixo da mínima.

## Operator

- ativo;
- inativo;
- outra filial;
- sem `can_access_pos`;
- sem PIN;
- PIN errado;
- rate limit;
- sessão expirada;
- logout.

## Escopo

- device não troca branch por payload;
- operator não acessa outra empresa;
- IDOR por product/ticket/cash register negado.

---

# 92. TESTES OBRIGATÓRIOS — VENDA

- produto sem ProductBranchConfig não vende;
- produto indisponível no counter não vende;
- modificador válido;
- modificador inválido;
- estoque insuficiente;
- estoque negativo quando permitido;
- preço da filial;
- promoção;
- desconto;
- item discount;
- taxa;
- waive fee;
- CashSession obrigatória;
- split payment;
- dinheiro/troco;
- idempotency replay;
- idempotency conflict;
- ticket emits_ticket;
- produção;
- device/operator auditável.

---

# 93. TESTES — TICKET VALIDATOR

- ISSUED → USED;
- USED não usa novamente;
- CANCELLED não usa;
- outra filial 404/deny;
- sem `tickets.validate`;
- retry com mesma idempotency key;
- corrida de dois devices: somente um utiliza;
- modifiers preservados;
- não baixa estoque;
- comanda não duplica ticket no fechamento.

---

# 94. TESTES — IMPRESSÃO

- um job só tem um executor ativo;
- lease expira;
- ACK success;
- ACK failure;
- retry;
- reprint auditada;
- device de outra filial não claim;
- printer de outra filial não recebe;
- network offline;
- reconnect;
- payload de modifiers;
- cancelamento.

---

# 95. PRE-POS GATE

Antes de implementar POS-0:

```text
backend migrations consistentes
backend system check
testes relevantes verdes
frontend Backoffice build verde
Platform Admin build verde
```

Falhas preexistentes devem ser classificadas.

Não “corrigir” teste mudando regra correta do domínio apenas para ficar verde.

---

# 96. ORDEM ATUALIZADA DE IMPLEMENTAÇÃO

```text
PRE-POS
  ↓
POS-0 — Backend Foundation
  ↓
POS-1 — Flutter / Pairing / Operator
  ↓
POS-2 — Home + Caixa + Sync Center
  ↓
POS-3 — Venda Rápida
  ↓
POS-4 — Ticket Validator
  ↓
POS-5 — Mesas / Comandas
  ↓
POS-6 — Impressão LAN + Recibos
  ↓
POS-7 — Stone Payments
  ↓
POS-8 — Estoque no POS
  ↓
POS-9 — Relatórios
  ↓
POS-10 — Resiliência Online-first
  ↓
Release V1
```

Pode haver ajuste de numeração sem alterar dependências.

---

# 97. POS-0 — ESCOPO EXATO PARA O OPENCODE

Implementar somente backend/fundação.

## Obrigatório

- `POSDevice`;
- lifecycle;
- licensing code;
- pairing identify;
- OTP;
- pairing confirm;
- device credential;
- device authentication;
- `can_access_pos`;
- PIN 6 dígitos;
- setup/reset link;
- operator eligibility;
- operator login/logout;
- rate limit;
- POS operator session;
- bootstrap;
- heartbeat;
- version gate;
- entitlements mínimos do POS;
- limite de devices;
- auditoria;
- RBAC necessário;
- settings base com arquitetura de herança;
- testes focados.

## Não implementar ainda

- Flutter;
- venda UI;
- Stone;
- offline completo;
- KDS;
- Print Agent;
- fiscal;
- IA;
- campanhas;
- microserviços.

---

# 98. POS-0 — REGRAS DE IMPLEMENTAÇÃO

Antes de alterar:

1. mapear models existentes;
2. mapear `User`, memberships e branch access;
3. mapear RBAC real;
4. mapear `Branch`;
5. mapear SaaS/entitlements;
6. mapear AuditLog;
7. mapear auth atual;
8. mapear errors;
9. mapear CashRegister/CashSession;
10. mapear Production/Ticket para evitar duplicação futura.

---

# 99. PROIBIDO AO OPENCODE

Não:

- reescrever motor de venda;
- reescrever estoque;
- reescrever comanda;
- mudar IDs/tenant model sem necessidade;
- criar novo banco;
- criar microserviço;
- adicionar Redis “por garantia”;
- criar Kafka/RabbitMQ sem requisito;
- hardcodar roles;
- colocar permissão na configuração do device;
- usar `X-Branch-ID` como fonte da branch do POS;
- armazenar PIN em claro;
- armazenar OTP em claro;
- armazenar device secret em claro;
- criar provider fake de WhatsApp como produção;
- inventar API Stone;
- fazer offline completo;
- misturar PrintJob na outbox de sync;
- duplicar `Ticket`;
- duplicar `PrinterDevice`;
- duplicar `CashSession`;
- duplicar `Sale`.

---

# 100. CHECKPOINT DE CADA SPRINT

Ao terminar:

```text
1. Resumo
2. Arquivos alterados
3. Models
4. Migrations
5. Endpoints
6. Permissions adicionadas/reutilizadas
7. Entitlements
8. Testes executados
9. Testes passando
10. Pendências
11. Decisões não implementadas
12. Riscos
```

E PARAR.

Não iniciar sprint seguinte sem autorização.

---

# 101. CONTRACT CHECKLIST — POS-0

- [ ] Device é preso a uma única branch.
- [ ] Branch deriva do device.
- [ ] CNPJ funciona.
- [ ] Licensing code funciona.
- [ ] OTP usa contato existente.
- [ ] OTP é seguro.
- [ ] Credential de device é segura.
- [ ] Device blocked não opera.
- [ ] Device revoked não opera.
- [ ] Version gate funciona.
- [ ] Operador POS não precisa necessariamente usar Backoffice.
- [ ] `can_access_pos` é independente do RBAC.
- [ ] PIN possui 6 dígitos.
- [ ] PIN é hash.
- [ ] Usuário sem PIN não aparece.
- [ ] Usuário de outra filial não aparece.
- [ ] Rate limit funciona.
- [ ] Operator Session existe.
- [ ] Bootstrap existe.
- [ ] Heartbeat existe.
- [ ] Limite por filial existe.
- [ ] Device settings NÃO armazenam permissões.
- [ ] Herança filial → device preparada.
- [ ] Auditoria.
- [ ] Testes de isolamento.

---

# 102. CONTRACT CHECKLIST — FLUTTER

- [ ] Android.
- [ ] Stone.
- [ ] Secure Storage.
- [ ] Pareamento.
- [ ] OTP.
- [ ] Operadores.
- [ ] PIN.
- [ ] Home dinâmica.
- [ ] Sync indicator.
- [ ] Sync Center.
- [ ] Caixa.
- [ ] Venda Rápida.
- [ ] Validador de Ticket.
- [ ] Comandas.
- [ ] Impressão.
- [ ] Stone payment quando integrado.
- [ ] Estoque.
- [ ] Relatórios.
- [ ] Version gate.
- [ ] Bloqueio remoto.

---

# 103. CONTRATO FINAL DE AUTORIZAÇÃO

Para qualquer ação funcional:

```text
request possui device autenticado?
        ↓
device ACTIVE?
        ↓
tenant operacional?
        ↓
branch operacional?
        ↓
app version suportada?
        ↓
operator session válida?
        ↓
entitlement/feature permite?
        ↓
operator possui permission real?
        ↓
contexto adicional válido?
(CashSession, estoque, ticket, etc.)
        ↓
SERVICE DE DOMÍNIO
```

**Configuração da máquina não concede autorização funcional.**

---

# 104. CONTRATO FINAL DE SINCRONIZAÇÃO

```text
SYNC
=
estado/config/cache/operações pendentes do app
```

```text
PRINT
=
jobs físicos de impressão
```

Nunca tratar como a mesma fila.

---

# 105. CONTRATO FINAL DE IMPRESSÃO

```text
Admin configura no Backoffice
        ↓
filial possui defaults
        ↓
device pode possuir override
        ↓
POS recebe effective config
```

Produção:

```text
Product
→ Destination
→ PrinterDevice
→ PrintJob
→ POS
→ LAN
→ impressora
→ ACK
```

Recibo Stone:

```text
Sale
→ receipt payload
→ device config = stone_integrated
→ impressora integrada
```

---

# 106. CONTRATO FINAL DO TICKET

```text
Product.emits_ticket = true
        ↓
Venda finalizada OU item de comanda confirmado
        ↓
Ticket ISSUED
        ↓
QR/barcode/código
        ↓
Validador CORE POS
        ↓
tickets.validate
        ↓
USED
```

O ticket:

- contém modificadores;
- não baixa estoque ao ser usado;
- não é gerado duas vezes no fechamento da comanda;
- é escopado à branch;
- registra quem usou e em qual device.

---

# 107. CONTRATO FINAL DO POS

O CORE POS é:

```text
um cliente operacional seguro,
pareado a uma filial,
com identidade própria de device,
operado por usuários autenticados por PIN,
autorizado pelo RBAC e pelos entitlements,
consumindo os mesmos services de domínio do CORE PDV.
```

Ele NÃO é:

```text
um segundo PDV com regras próprias,
um novo backend,
uma cópia offline do CORE,
um sistema de permissões por máquina,
um Print Agent obrigatório,
um banco paralelo.
```

---

# 108. PRIMEIRA INSTRUÇÃO A SER DADA AO OPENCODE

> Leia integralmente `missao.md`.
>
> Considere este documento a fonte de verdade funcional e técnica do CORE POS.
>
> Antes de implementar, faça uma auditoria de compatibilidade do código atual com a seção POS-0.
>
> Não reescreva services de domínio existentes.
>
> Não implemente Flutter ainda.
>
> Não use configuração de máquina como sistema de permissões.
>
> Não misture sincronização geral com impressão.
>
> Reutilize os códigos reais de RBAC presentes em `backend/apps/companies/rbac.py`.
>
> Reutilize `Product.emits_ticket`, `Ticket`, `ProductionJob`, `PrintJob`, `CashSession`, `Sale`, `Command` e seus services existentes.
>
> Execute SOMENTE o POS-0.
>
> Ao finalizar, entregue o checkpoint técnico descrito neste documento e PARE.

---

# 109. GOVERNANÇA DESTE CONTRATO

Sempre que uma decisão do CORE POS for alterada:

1. atualizar este arquivo;
2. remover a regra que deixou de valer;
3. manter somente uma versão vigente de cada regra;
4. atualizar os testes afetados;
5. revisar os contratos de API relacionados;
6. manter este arquivo autocontido.

O objetivo é permitir que qualquer agente de código leia apenas este documento e tenha contexto suficiente para implementar corretamente.

---

**FIM DO CONTRATO MESTRE — CORE POS**
