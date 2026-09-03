# CORE POS — PLANO MESTRE DE IMPLEMENTAÇÃO POR SPRINTS

> **Objetivo:** implementar o CORE POS de forma incremental, segura e compatível com o CORE PDV atual, sem reinventar regras de negócio já existentes no backend Django.
>
> Este documento é a especificação funcional/técnica mestre da etapa POS.
>
> **REGRA PRINCIPAL:** o OpenCode NÃO deve inventar arquitetura, UX, permissões, fluxos, regras de autenticação, regras financeiras, regras de estoque, regras de caixa ou comportamento de dispositivo fora do que está definido aqui. Quando algo não estiver definido, registrar a dúvida e PARAR antes de implementar.

---

# 0. CONTEXTO E PRINCÍPIOS INEGOCIÁVEIS

## 0.1 O CORE POS NÃO É UM NOVO BACKEND

O CORE POS será um novo cliente operacional do CORE.

```text
CORE Backoffice / Next.js
          │
          ├──────────────┐
          ▼              ▼
    API Backoffice    API POS
          │              │
          └──────┬───────┘
                 ▼
          DOMAIN SERVICES
          ├── sales
          ├── inventory
          ├── purchases
          ├── cash
          ├── commands
          ├── products
          ├── production
          └── permissions
                 │
                 ▼
             PostgreSQL
```

NÃO duplicar cálculo de venda, estoque, modificadores, caixa, comanda, permissões, pagamentos, auditoria, regras de filial ou tenant.

O POS deve reutilizar os serviços de domínio existentes sempre que possível.

---

# 1. DECISÕES DE PRODUTO JÁ FECHADAS

## 1.1 Aplicativo único

Existirá um único app: `CORE POS`.

Não criar apps separados de Garçom, Estoque, Caixa ou Gerente.

O mesmo app será modular conforme:
- plano/entitlements;
- filial;
- dispositivo;
- usuário;
- permissões.

## 1.2 Primeiro acesso: identificação da filial

No primeiro acesso, solicitar:

```text
CNPJ da filial
OU
Código de Licenciamento CORE
```

Ambos devem funcionar sempre.

O código de licenciamento:
- é único;
- não sequencial;
- não previsível;
- pertence a uma filial;
- pode ser rotacionado;
- não autentica sozinho;
- apenas identifica a filial.

## 1.3 Verificação da filial por OTP

```text
CNPJ/Código
→ Branch encontrada
→ usar contatos já cadastrados no backend
→ escolher WhatsApp ou e-mail disponível
→ enviar OTP
→ validar OTP
→ registrar dispositivo
```

Os dados usados para OTP vêm do cadastro existente da empresa/filial no backend.

NÃO criar um cadastro paralelo obrigatório de "contato de pareamento".

O OTP deve:
- ser uso único;
- expirar;
- possuir limite de tentativas;
- possuir limite de reenvio;
- invalidar o anterior quando outro for gerado;
- não ser armazenado em texto puro;
- não permitir pareamento sem validação.

## 1.4 Dispositivo fica preso à filial

Após o pareamento:

```text
POSDevice.branch = filial identificada
```

O operador NÃO escolhe empresa ou filial no dia a dia.

Para mudar de filial:
- desvincular/revogar;
- fazer novo pareamento.

## 1.5 Usuários do POS não precisam ter Backoffice

Um usuário pode existir apenas como operador do POS.

Usar/adicionar gate explícito:

```text
can_access_pos = True/False
```

Isso NÃO substitui o RBAC.

## 1.6 Usuários exibidos no seletor

Mostrar apenas usuários que atendam TODOS:

```text
ativo
+
vinculado/autorizado naquela filial
+
can_access_pos = True
+
possui permissão para operar POS
+
PIN configurado
```

Usuário sem PIN não aparece.

## 1.7 PIN de 6 dígitos

O operador autentica por:

```text
selecionar usuário
+
PIN de 6 dígitos
```

O PIN:
- exatamente 6 dígitos;
- hash no backend;
- nunca visível para admin;
- não precisa ser único;
- possui rate limit;
- pode ser redefinido.

No Backoffice:

```text
Acesso ao POS: Sim/Não

PIN do POS
Status: Não configurado / Configurado

[ Enviar link para criar PIN ]
[ Redefinir PIN ]
```

O usuário cria o próprio PIN por link de uso único e expirável enviado para e-mail/WhatsApp cadastrado.

## 1.8 CashSession obrigatória

Ninguém vende sem `CashSession` aberta.

Regra obrigatória no backend.

A abertura de caixa depende da permissão:

```text
cash.open
```

Não de cargo fixo.

## 1.9 Permissões dinâmicas

Reutilizar o RBAC do Django.

NÃO hardcodar roles no Flutter.

Disponibilidade final:

```text
ENTITLEMENT DO PLANO
        ∩
CONFIGURAÇÃO DA MÁQUINA
        ∩
PERMISSÃO DO OPERADOR
        =
RECURSO DISPONÍVEL
```

Módulos futuros:
- Venda Balcão;
- Mesas / Comandas;
- Estoque;
- Relatórios;
- Configuração.

Ações:
- vender;
- cancelar;
- aplicar desconto;
- remover taxa de 10%;
- abrir/fechar caixa;
- sangria/suprimento;
- contar estoque;
- ver estoque;
- ver vendas próprias;
- ver vendas da filial;
- configurar dispositivo.

Frontend esconde, backend autoriza de verdade.

## 1.10 Configuração por máquina

Cada dispositivo possui configuração própria.

Exemplo:

```text
Stone Bar 01

Filial: Centro
Caixa padrão: Bar

Módulos:
✓ Venda Balcão
✓ Comandas
✗ Estoque
✗ Relatórios
```

## 1.11 Limite de dispositivos

Limite comercial por FILIAL.

Exemplo:

```text
3 POS por filial
```

Preparar ilimitado, numérico, add-on e override.

## 1.12 Atualização obrigatória

Backend mantém:

```text
latest_version
minimum_supported_version
```

Se versão atual < mínima:
- bloquear uso;
- exigir atualização;
- sem "continuar mesmo assim".

## 1.13 Atualizar / Sincronizar

Botão força atualização de:
- usuários;
- permissões;
- configuração da máquina;
- status do dispositivo;
- status da filial;
- versão mínima;
- caixa;
- capabilities.

Também sincronizar automaticamente ao abrir o app, após login/logout e periodicamente.

## 1.14 UX inicial

```text
Empresa X — Filial Y

Quem está operando?

[ seletor de usuário ]

PIN
[ • • • • • • ]

[ ENTRAR ]

↻ Atualizar / Sincronizar

Dispositivo: Stone Bar 01
Versão: 1.x.x
```

---

# 2. ARQUITETURA DE IDENTIDADES

O POS possui contextos separados:

```text
Tenant/Company
Branch
POSDevice
User/Operator
```

Toda operação importante deve poder registrar:

```text
company
branch
device
operator
cash_register
cash_session
```

Nunca confiar cegamente nesses IDs enviados pelo app.

---

# 3. ESTADOS DO DISPOSITIVO

Mínimo:

```text
PENDING
ACTIVE
BLOCKED
REVOKED
REPLACED
```

- `PENDING`: ainda não concluído quando aplicável.
- `ACTIVE`: pode operar.
- `BLOCKED`: preserva vínculo/histórico, mas não opera.
- `REVOKED`: credenciais revogadas.
- `REPLACED`: substituído por novo aparelho.

Sem exclusão física do histórico.

---

# 4. BLOQUEAR X DESVINCULAR

## Bloquear
- mantém filial;
- mantém histórico;
- impede autenticação/refresh/operação;
- pode ser reativado.

## Desvincular/Revogar
- invalida credenciais;
- encerra sessões;
- exige novo pareamento;
- preserva histórico.

---

# 5. SPRINT POS-0 — FUNDAÇÃO BACKEND

## Objetivo

Criar dispositivo, identificação, OTP, autenticação do device, operador, PIN, RBAC dinâmico e bootstrap.

**Não iniciar Flutter.**

## POS-0.1 — `POSDevice`

Criar entidade com, no mínimo:

```text
id UUID
company/branch
name
device_type
status
cash_register opcional
app_version
os_version opcional
device_model opcional
last_seen_at
paired_at
blocked_at
revoked_at
replaced_at
created_at
updated_at
created_by quando aplicável
```

Reutilizar padrões atuais de soft-delete/auditoria.

## POS-0.2 — Código de licenciamento

Adicionar/validar:

```text
Branch.licensing_code
```

Requisitos:
- gerado server-side;
- único;
- imprevisível;
- indexado;
- rotacionável;
- auditável.

Rotacionar o código NÃO revoga automaticamente devices já pareados.

## POS-0.3 — Identificação da filial

Endpoint conceitual:

```text
POST /api/v1/pos/pairing/identify/
```

Input:

```json
{"identifier":"CNPJ-ou-codigo"}
```

Responsabilidades:
- normalizar CNPJ;
- procurar CNPJ exato;
- procurar licensing code;
- retornar flow/challenge id;
- retornar somente canais mascarados;
- não retornar secrets.

## POS-0.4 — OTP

Criar challenge genérico, compatível com futura MFA.

Conceito:

```text
AuthenticationChallenge
```

Campos:
- id;
- purpose;
- branch;
- channel;
- destination masked/fingerprint;
- code_hash;
- expires_at;
- attempts;
- max_attempts;
- consumed_at;
- created_at.

Purpose inicial:

```text
POS_DEVICE_PAIRING
```

Envio:
- e-mail;
- WhatsApp via adapter/provider real quando integração existir.

Não inventar provider fake de produção.

## POS-0.5 — Confirmar OTP / criar device

Endpoint:

```text
POST /api/v1/pos/pairing/confirm/
```

Após OTP:
- cria/ativa POSDevice;
- vincula à filial;
- gera credencial segura;
- registra auditoria;
- invalida challenge.

## POS-0.6 — Autenticação de device

Criar autenticação própria da API POS.

A request deve resolver:

```text
request.pos_device
request.company
request.branch
```

Não usar `X-Branch-ID` para determinar branch do POS.

Credencial:
- revogável;
- rotacionável;
- não salva em texto puro no banco.

## POS-0.7 — `can_access_pos`

Adicionar/consolidar gate sem quebrar usuários atuais.

`False`:
- não aparece;
- não autentica.

`True`:
- ainda exige ativo + filial + permissão + PIN.

## POS-0.8 — PIN

Serviços:
- `set_pos_pin`;
- `verify_pos_pin`;
- `reset_pos_pin`.

Nunca retornar hash na API.

## POS-0.9 — Link para criar/resetar PIN

Backoffice:
- enviar link;
- redefinir PIN.

Token:
- aleatório;
- purpose-specific;
- expirável;
- uso único;
- invalidado após uso.

Página pública:
```text
Criar PIN do CORE POS
PIN
Confirmar PIN
```

Não exigir login Backoffice do garçom.

## POS-0.10 — Operadores disponíveis

Endpoint:

```text
GET /api/v1/pos/operators/
```

Retorna somente usuários elegíveis.

Dados mínimos:
- uuid;
- display_name;
- avatar opcional;
- iniciais.

## POS-0.11 — Login operador

Endpoint:

```text
POST /api/v1/pos/auth/operator/
```

Input:
- operator_id;
- pin.

Validar:
- device ACTIVE;
- branch/tenant operacionais;
- operador ativo;
- autorizado na branch;
- `can_access_pos`;
- permissão POS;
- PIN;
- rate limit.

Criar sessão de operador.

## POS-0.12 — Rate limit PIN

Default:
```text
5 falhas
15 minutos
```

Não bloquear toda filial por erro de uma pessoa.

## POS-0.13 — Bootstrap

```text
GET /api/v1/pos/bootstrap/
```

Retorna:
- release;
- company;
- branch;
- device;
- operator;
- cash register;
- cash session;
- modules;
- permissions;
- device capabilities;
- settings;
- latest/minimum version.

## POS-0.14 — RBAC

Reutilizar permissões existentes.

Só criar nova permissão quando não houver equivalente.

Gate provável:
```text
pos.operate
```

## POS-0.15 — Configuração por máquina

Mínimo:
- enabled_modules;
- default_cash_register;
- name.

Preparar para printers/destinations.

## POS-0.16 — Limite por filial

Integrar com entitlements.

Ao atingir limite:
- bloquear novo pareamento;
- manter devices existentes;
- erro de negócio claro.

## POS-0.17 — Heartbeat

```text
POST /api/v1/pos/heartbeat/
```

Atualizar:
- last_seen;
- app_version;
- device metadata permitida.

Não gravar heartbeat em audit log imutável a cada chamada.

## POS-0.18 — Version gate

Bootstrap/heartbeat retornam:
```text
update_available
update_required
```

## POS-0.19 — Auditoria

Auditar:
- pareamento;
- OTP;
- bloquear/revogar device;
- alteração de caixa/config;
- operador login/logout;
- PIN setup/reset.

## Critérios POS-0

- [ ] CNPJ identifica filial.
- [ ] Código CORE identifica filial.
- [ ] OTP usa dados do cadastro atual.
- [ ] Device preso à filial.
- [ ] Device auth não usa cookie/CSRF do Backoffice.
- [ ] Garçom sem Backoffice pode operar.
- [ ] PIN 6 dígitos hashado.
- [ ] Usuário sem PIN não aparece.
- [ ] Usuário de outra filial não aparece.
- [ ] Usuário inativo não aparece.
- [ ] RBAC aplicado.
- [ ] Rate limit.
- [ ] Bootstrap.
- [ ] Limite por filial.
- [ ] Device bloqueado não opera.
- [ ] Versão incompatível é bloqueada.
- [ ] Flutter ainda não iniciado.

---

# 6. SPRINT POS-1 — FLUTTER BASE / PAREAMENTO

## Objetivo

Criar o app Flutter mínimo para parear device e autenticar operador.

## POS-1.1 — Projeto único

Criar `CORE POS`.

Alvos:
- Android;
- Stone Android;
- celular/tablet Android.

## POS-1.2 — Arquitetura

Separar:
- networking;
- secure storage;
- auth/device state;
- operator state;
- modules/features;
- repositories/services;
- DTOs;
- screens.

Não fazer HTTP dentro de widgets.

## POS-1.3 — Secure storage

Credencial do device no Android Keystore/secure storage.

Não usar SharedPreferences puro para secrets.

## POS-1.4 — Primeiro acesso

Tela:

```text
CNPJ ou Código de Licenciamento
[________________________]
[ Continuar ]
```

## POS-1.5 — OTP

Escolha do canal mascarado e entrada do código.

Respeitar cooldown/reenvio.

## POS-1.6 — Persistência

Após pareamento:
- salvar credencial segura;
- não pedir CNPJ novamente.

## POS-1.7 — Tela de operadores

Exatamente:

```text
Empresa — Filial

Quem está operando?

[ seletor ]

PIN
[______]

[ ENTRAR ]

↻ Atualizar / Sincronizar
```

## POS-1.8 — Sincronizar

Atualiza operators/device/version/config.

## POS-1.9 — Operator session

Após PIN:
- salvar sessão/token;
- nunca persistir PIN.

## POS-1.10 — Trocar operador

Encerra apenas sessão do operador.

Não desvincula device.

## POS-1.11 — Update required

Tela bloqueante sem "depois".

## Critérios POS-1

- [ ] Pareamento por CNPJ.
- [ ] Pareamento por código.
- [ ] OTP.
- [ ] Persistência.
- [ ] Lista operadores.
- [ ] PIN.
- [ ] Sincronização.
- [ ] Trocar operador.
- [ ] Bloqueio remoto.
- [ ] Update required.

---

# 7. SPRINT POS-2 — HOME MODULAR + CAIXA

## Objetivo

Criar shell operacional e CashSession.

## POS-2.1 — Home modular

Renderizar apenas módulos do bootstrap:

```text
Venda Balcão
Mesas/Comandas
Estoque
Relatórios
Configuração
```

## POS-2.2 — Estado do caixa

Mostrar:
- caixa;
- status;
- sessão;
- responsável;
- horário.

## POS-2.3 — Venda sem caixa

Bloqueio frontend + backend.

## POS-2.4 — Abrir caixa

Controlado por `cash.open`.

## POS-2.5 — Fechar caixa

Reutilizar domínio atual e `cash.close`.

## POS-2.6 — Sangria/Suprimento

Somente com módulo/config/permissão.

## POS-2.7 — FIXED/FLEXIBLE

Preparar modos:
- FIXED: caixa definido no device;
- FLEXIBLE: escolher entre caixas permitidos da branch.

## Critérios POS-2

- [ ] Home dinâmica.
- [ ] CashSession obrigatória.
- [ ] Abertura por permissão.
- [ ] Fechamento por permissão.
- [ ] Fixed/flexible.
- [ ] Backend é autoridade.

---

# 8. SPRINT POS-3 — VENDA BALCÃO

## Objetivo

Venda direta sobre o motor existente.

## POS-3.1 — Catálogo POS

```text
GET /api/v1/pos/catalog/
```

Retorno enxuto:
- produto;
- preço da filial;
- barcode;
- disponibilidade;
- categoria;
- modificadores;
- flags necessárias.

Evitar N+1.

## POS-3.2 — Barcode exato

```text
GET /api/v1/pos/products/barcode/{barcode}/
```

## POS-3.3 — Carrinho local

Guardar:
- product;
- quantity;
- modifiers;
- notes;
- client_item_id.

Backend recalcula.

## POS-3.4 — Modificadores

Reutilizar exatamente a semântica atual.

## POS-3.5 — Preview

```text
POST /api/v1/pos/sales/calculate/
```

Backend retorna subtotal/desconto/taxa/total.

## POS-3.6 — Desconto

RBAC existente.

## POS-3.7 — Taxa de serviço

Remoção/alteração por permissão granular.

## POS-3.8 — Idempotência

Toda finalização usa `idempotency_key`.

## POS-3.9 — Finalização

Reutilizar `finalize_sale()` ou equivalente.

## POS-3.10 — Auditoria

Registrar device/operator/cash session.

## Critérios POS-3

- [ ] Catálogo.
- [ ] Barcode.
- [ ] Carrinho.
- [ ] Modificadores.
- [ ] Preview.
- [ ] Desconto por permissão.
- [ ] Taxa por permissão.
- [ ] Idempotência.
- [ ] Estoque correto.
- [ ] Device/operator registrados.

---

# 9. SPRINT POS-4 — MESAS / COMANDAS

## Objetivo

Levar comandas ao POS sem duplicação por retry.

## POS-4.1 — Idempotência antes do Flutter

Abrir comanda/adicionar pedido devem ser protegidos antes do consumo móvel.

## POS-4.2 — Client IDs

Usar conforme necessário:
- `client_command_id`;
- `client_order_id`;
- `idempotency_key`.

## POS-4.3 — Pedido atômico

Preferir:

```text
POST /api/v1/pos/commands/{id}/orders/
```

Backend atomicamente:
- valida;
- cria pedido;
- cria itens;
- aplica estoque conforme domínio;
- gera produção;
- responde estado.

Retry retorna a mesma operação.

## POS-4.4 — Mesas

Listar estado, comanda, total e atendente.

## POS-4.5 — Abrir comanda

Idempotente.

## POS-4.6 — Itens

Produto, quantidade, modificadores, observação.

## POS-4.7 — Pagamento parcial

Reutilizar domínio.

## POS-4.8 — Transfer/Merge/Split

Expor somente operações existentes e permitidas.

## POS-4.9 — Fechamento

Reutilizar motor atual.

## Critérios POS-4

- [ ] Abrir comanda não duplica.
- [ ] Pedido não duplica.
- [ ] Retry seguro.
- [ ] Estoque.
- [ ] Pagamento parcial.
- [ ] Fechamento.
- [ ] RBAC.
- [ ] Auditoria.

---

# 10. SPRINT POS-5 — IMPRESSÃO LOCAL / PRODUÇÃO

## Objetivo

POS imprime diretamente na LAN.

## POS-5.1 — Backend fonte da verdade

Manter `ProductionJob` + `PrintJob`.

## POS-5.2 — Claim

Estados:
```text
PENDING → CLAIMED → PRINTED/FAILED
```

## POS-5.3 — Lease

Lease expira se executor morrer.

## POS-5.4 — ACK

POS envia sucesso/falha.

## POS-5.5 — Ticket

Incluir:
- setor;
- mesa/comanda;
- pedido;
- produto;
- quantidade;
- modificadores;
- observação;
- operador;
- horário.

## POS-5.6 — Setor → impressora

Reutilizar:

```text
Product → Production Destination → Printer(s)
```

## POS-5.7 — Oscilação de internet

Job já recebido pode imprimir localmente quando possível; ACK depois.

## POS-5.8 — Print Agent

Não obrigatório nesta sprint.

## Critérios POS-5

- [ ] PrintJob criado.
- [ ] Claim único.
- [ ] Lease.
- [ ] Ticket real.
- [ ] ACK.
- [ ] Retry.
- [ ] Falhas visíveis.
- [ ] Reimpressão auditada.

---

# 11. SPRINT POS-6 — STONE

## Objetivo

Pagamento integrado sem corromper financeiro.

## POS-6.1 — `PaymentTransaction`

Não registrar apenas `Payment`.

Estados:
```text
INITIATED
PROCESSING
APPROVED
DECLINED
CANCELLED
REFUNDED
RECONCILIATION_NEEDED
```

## POS-6.2 — Dados

Guardar somente o permitido:
- provider;
- device;
- external transaction id;
- NSU;
- authorization code;
- brand;
- installments;
- amount;
- status.

Nunca PAN completo/CVV.

## POS-6.3 — Fluxo

```text
iniciar
→ Stone
→ aprovado
→ CORE
→ finalize_sale()
→ Payment
```

## POS-6.4 — Aprovado sem venda

Marcar `RECONCILIATION_NEEDED`.

Permitir recuperação/reconciliação/estorno.

## POS-6.5 — Estorno/cancelamento

Por permissão + motivo + auditoria.

## POS-6.6 — Providers futuros

Adapter/abstração. Stone é primeiro provider, não o domínio inteiro.

## Critérios POS-6

- [ ] Aprovação.
- [ ] Recusa.
- [ ] Reconciliar.
- [ ] NSU/autorização.
- [ ] Cancelamento.
- [ ] Estorno.
- [ ] Approved-without-sale recuperável.
- [ ] Sem dado proibido.

---

# 12. SPRINT POS-7 — ESTOQUE NO POS

## Objetivo

Módulo de estoque dinâmico.

## POS-7.1 — Gate

```text
entitlement ∩ device config ∩ permission
```

## POS-7.2 — Consultar

`inventory.view`.

## POS-7.3 — Contar

`inventory.count`.

Reutilizar domínio existente.

## POS-7.4 — Ajustar

`inventory.adjust` separado.

Quem conta não necessariamente ajusta.

## POS-7.5 — Transferir

Somente se permitido.

## Critérios POS-7

- [ ] Módulo dinâmico.
- [ ] Consultar.
- [ ] Contar.
- [ ] Ajustar separado.
- [ ] Sem estoque paralelo.

---

# 13. SPRINT POS-8 — RELATÓRIOS

## Objetivo

Relatórios apropriados ao operador.

## POS-8.1 — Próprias vendas

Permissão:
```text
reports.own_sales
```

Pode exibir:
- vendas;
- pedidos;
- ticket médio;
- comissão.

## POS-8.2 — Filial

Permissão:
```text
reports.branch_sales
```

Pode ver ranking/visão da filial.

## POS-8.3 — Escopo

Backend filtra.

Não enviar dados sensíveis e esconder só no Flutter.

## Critérios POS-8

- [ ] Operador vê somente próprias vendas quando esse é seu escopo.
- [ ] Filial somente com permissão.
- [ ] Backend controla.

---

# 14. SPRINT POS-9 — CONFIGURAÇÃO POR MÁQUINA

## Objetivo

Administrar devices pelo Backoffice.

## POS-9.1 — Inventário

Tela:

```text
Configurações → Dispositivos
```

Mostrar:
- nome;
- filial;
- status;
- online/offline;
- operador;
- caixa;
- app version;
- last_seen;
- módulos.

## POS-9.2 — Ações

Permissões para:
- renomear;
- bloquear;
- reativar;
- revogar;
- substituir;
- trocar caixa;
- alterar módulos;
- impressoras/destinos.

## POS-9.3 — Atualização dinâmica

Backend nega imediatamente; POS sincroniza visual depois.

## POS-9.4 — Replacement

```text
antigo → REPLACED
novo → ACTIVE
```

## Critérios POS-9

- [ ] Inventário.
- [ ] Bloqueio.
- [ ] Revogação.
- [ ] Replacement.
- [ ] Módulos.
- [ ] Limite por filial visível.

---

# 15. SPRINT POS-10 — RESILIÊNCIA ONLINE-FIRST

## Objetivo

Lidar com internet instável sem fingir offline completo.

## POS-10.1 — Decisão

V1 = `ONLINE-FIRST`.

## POS-10.2 — Outbox limitada

Operações pendentes seguras, sempre com idempotency key.

## POS-10.3 — Estados visuais

```text
Enviando
Confirmado
Falha
Aguardando conexão
```

## POS-10.4 — Cache

Pode cachear:
- operadores;
- catálogo;
- config;
- permissões;
- jobs já recebidos.

## POS-10.5 — Reconectar

Após reconexão:
- refresh device;
- refresh operator;
- retry idempotente;
- sync jobs.

## Critérios POS-10

- [ ] Timeout não duplica venda.
- [ ] Timeout não duplica pedido.
- [ ] Estado pendente claro.
- [ ] Reconexão recupera.
- [ ] Não existe falso "offline completo".

---

# 16. SPRINTS FUTURAS

## POS-11 — OFFLINE TRANSACIONAL COMPLETO

Somente com documento próprio antes do código.

Exigirá:
- DB local;
- outbox;
- sync cursor;
- conflict resolution;
- vendas offline;
- estoque concorrente;
- reconciliação;
- regras de estoque negativo;
- conflito entre múltiplos devices offline.

## POS-12 — KDS / PRODUÇÃO AVANÇADA

Futuro:
- KDS;
- status de preparo;
- tempos;
- prioridade;
- múltiplas telas;
- cancelamentos.

## POS-13 — PRINT AGENT

Para:
- Windows;
- USB;
- impressoras legadas;
- topologias complexas.

Não tornar obrigatório em lojas simples.

---

# 17. PERMISSÕES — DIRETRIZ

Antes de criar novas, pesquisar RBAC atual.

Permissões conceituais possíveis:

```text
pos.operate

sales.create
sales.view
sales.cancel
sales.discount
sales.discount_above_limit

service_fee.remove
service_fee.change

payments.receive
payments.reverse

cash.open
cash.close
cash.withdraw
cash.deposit
cash.view

commands.open
commands.add_item
commands.transfer
commands.merge
commands.cancel_item
commands.close

inventory.view
inventory.count
inventory.adjust
inventory.transfer

reports.own_sales
reports.branch_sales

pos_device.view
pos_device.configure
pos_device.block
pos_device.revoke
```

Não duplicar permission que já existe com outro nome equivalente.

---

# 18. CONTRATO DE SEGURANÇA

- Device credential ≠ operador.
- PIN ≠ senha Backoffice.
- Branch deriva do device.
- Company deriva da branch.
- CashSession validada pelo servidor.
- Permissão validada pelo servidor.
- Versão do app validada pelo servidor.
- Auditoria registra device + operator.

---

# 19. CAMPOS QUE O FLUTTER NÃO DEVE CONTROLAR LIVREMENTE

Não confiar cegamente em:

```text
company_id
branch_id
device_id
cash_session_id
permissions
price
discount authority
service fee authority
stock result
```

Servidor deriva/valida.

---

# 20. SINCRONIZAÇÃO

"Atualizar / Sincronizar" atualiza:

```text
device status
branch status
tenant status
operators
permissions
modules
cash registers
cash session
minimum app version
feature/capability flags
```

Não baixar banco inteiro.

---

# 21. VERSIONAMENTO DA API

Usar namespace:

```text
/api/v1/pos/
```

Preparar evolução posterior sem quebrar todos os apps.

---

# 22. TESTES — MODO ECONÔMICO

Durante sprints:
- não rodar suíte global repetidamente;
- usar testes focados;
- preservar testes existentes;
- criar somente regressões realmente importantes;
- validação global completa apenas ao fim de macro-release.

---

# 23. CHECKPOINT OBRIGATÓRIO

Ao terminar cada sprint:

1. atualizar checklist;
2. listar arquivos alterados;
3. listar migrations;
4. listar endpoints;
5. listar validações;
6. listar pendências;
7. PARAR.

Não iniciar próxima sprint sem autorização.

---

# 24. ORDEM OFICIAL

```text
PRE-POS CONCLUÍDO
      ↓
POS-0 Backend Foundation
      ↓
POS-1 Flutter Base
      ↓
POS-2 Home + Caixa
      ↓
POS-3 Venda Balcão
      ↓
POS-4 Comandas
      ↓
POS-5 Impressão
      ↓
POS-6 Stone
      ↓
POS-7 Estoque
      ↓
POS-8 Relatórios
      ↓
POS-9 Configuração por Máquina
      ↓
POS-10 Resiliência Online-first
      ↓
RELEASE V1
```

Futuro:
```text
POS-11 Offline completo
POS-12 KDS
POS-13 Print Agent
```

---

# 25. PROIBIDO INVENTAR

Não:
- escolher provider WhatsApp sem decisão;
- inventar preços/planos;
- inventar roles;
- inventar estados financeiros;
- duplicar venda/estoque/caixa;
- inventar offline completo;
- inventar fluxo fiscal;
- inventar Stone API sem documentação oficial;
- trocar stack backend;
- criar microserviços sem necessidade;
- criar banco novo;
- adicionar Redis/queue "porque pode ser útil";
- mudar multi-tenancy;
- hardcodar permissões no Flutter;
- expor secrets.

Quando faltar decisão:

```text
REGISTRAR DÚVIDA
→ EXPLICAR IMPACTO
→ PARAR
→ AGUARDAR DECISÃO
```

---

# 26. CHECKLIST MESTRE

- [ ] POS-0 — Fundação Backend
- [ ] POS-1 — Flutter Base
- [ ] POS-2 — Home + Caixa
- [ ] POS-3 — Venda Balcão
- [ ] POS-4 — Comandas
- [ ] POS-5 — Impressão
- [ ] POS-6 — Stone
- [ ] POS-7 — Estoque
- [ ] POS-8 — Relatórios
- [ ] POS-9 — Configuração por Máquina
- [ ] POS-10 — Resiliência Online-first

Futuro:
- [ ] POS-11 — Offline completo
- [ ] POS-12 — KDS
- [ ] POS-13 — Print Agent

---

# 27. PRIMEIRA INSTRUÇÃO PARA O OPENCODE

> Leia este documento integralmente.
>
> Execute SOMENTE a Sprint POS-0.
>
> Antes de alterar qualquer arquivo, analise o projeto atual e mapeie models, permissions, services, serializers, autenticação, entitlements, Branch, User/Membership, CashRegister/CashSession e auditoria já existentes.
>
> Reutilize a arquitetura atual. Não duplique regras de domínio.
>
> Não inicie Flutter.
>
> Não inicie POS-1.
>
> Se encontrar uma decisão não definida neste documento que altere arquitetura ou regra de negócio, registre a dúvida e pare antes de implementá-la.
>
> Durante a implementação use validações focadas, sem rodar a suíte global repetidamente.
>
> Ao terminar POS-0, entregue checkpoint técnico, atualize o checklist e PARE.

---

# 28. RESULTADO ESPERADO APÓS POS-0

```text
CORE Backend
├── POSDevice
├── Licensing Code
├── Pairing
├── OTP
├── Device Auth
├── POS Operator Gate
├── PIN 6 dígitos
├── PIN Setup Link
├── Operator Auth
├── Dynamic RBAC
├── Machine Config
├── Device Limit per Branch
├── Heartbeat
├── Version Gate
└── POS Bootstrap
```

Só depois disso iniciar Flutter.
