CORE PDV — MISSÃO 2 / PARTE 1
Enforcement global de módulos: Plano → Filial → RBAC
Trabalhe sobre o main atual do projeto maxforcedev/PDV-25LOUNGE.
Antes de alterar, leia a implementação existente. Não substitua a arquitetura atual por outro sistema. Esta missão deve consolidar e completar o que já existe.
Hoje já temos uma boa fundação em:
backend/apps/companies/features.py
backend/apps/saas/services.py
backend/apps/saas/permissions.py
backend/apps/companies/models.py
backend/apps/companies/serializers.py
backend/apps/accounts/serializers.py

frontend/src/lib/feature-guards.ts
frontend/src/lib/authorized-routes.ts
frontend/src/providers/auth-provider.tsx
frontend/src/components/admin-guard.tsx
frontend/src/components/app-shell.tsx

backend/apps/pos/services.py

A regra definitiva do CORE passa a ser:
RECURSO EFETIVO =
tenant operacional
AND entitlement/plano habilitado
AND módulo habilitado naquela filial
AND dependências do módulo habilitadas

AÇÃO AUTORIZADA =
recurso efetivo
AND RBAC/permissão do usuário

RBAC nunca pode habilitar recurso fora do plano ou desabilitado na filial.
Superusuário, Owner, perfil administrativo ou permissão gravada no banco também não devem transformar uma capability comercial indisponível em disponível.
DISPONIBILIDADE OPERACIONAL POR FILIAL PARA TODOS OS MÓDULOS
Hoje BranchSettings.feature_flags() possui switches locais principalmente para:
tables
commands
counter
consumption
cash_register

Enquanto diversos outros módulos definidos em FEATURE_CAPABILITIES usam implicitamente True na filial.
Isso precisa ser corrigido.
A filial deve possuir disponibilidade operacional explícita para todos os módulos comerciais atualmente existentes:
tables
commands
counter
consumption
cash_register
production
products
inventory
purchases
suppliers
customers
promotions
reports
audit
financial
pos

Preserve os campos atuais e, seguindo o padrão já existente de BranchSettings, adicione os switches ausentes, por exemplo:
uses_products
uses_inventory
uses_purchases
uses_suppliers
uses_customers
uses_promotions
uses_production
uses_reports
uses_audit
uses_financial
uses_pos

Não transformar nesta missão BranchSettings em uma arquitetura completamente diferente.
Criar migration segura e não destrutiva.
Para os novos campos, preservar o comportamento existente das filiais atuais:
default=True

O entitlement continua sendo a autoridade superior.
Portanto:
plano OFF + filial ON = OFF
plano ON + filial OFF = OFF
plano ON + filial ON = ON

core.enabled, users.max, branches.max, limites quantitativos e outras capabilities que não representam módulo operacional de filial não devem virar switches de filial.
NÃO CONFUNDIR MÓDULO COM CONFIGURAÇÃO INTERNA
Continuam sendo configurações/subfeatures e NÃO novos módulos comerciais:
allow_negative_stock
charges_service_fee
consumption_limit_enabled
service_fee_rate
commission_rate
fixed_daily_cost

Elas só podem ser usadas quando o módulo correspondente estiver efetivamente disponível.
Exemplo:
inventory OFF
→ configuração de estoque negativo não opera/não aparece

financial OFF
→ taxa, comissão e configurações financeiras não operam/não aparecem

DEPENDÊNCIAS NA FILIAL
O plano já possui dependências declarativas em CAPABILITY_DEPENDENCIES.
A disponibilidade operacional da filial precisa respeitar a mesma lógica.
No mínimo:
inventory → products

counter → products + cash_register

commands → products + cash_register

purchases → suppliers + products + inventory

promotions → products

production → products

tables → commands

consumption → commands

Não permitir estados efetivos incoerentes.
Exemplo:
products = OFF
inventory = ON

resultado efetivo:
inventory = OFF

Ao editar a filial, preferir validação clara. Não criar estado silenciosamente inconsistente no banco.
Se o usuário tentar habilitar um módulo sem seu requisito, retornar erro amigável indicando a dependência.
Ao desabilitar um pré-requisito que possui módulos dependentes habilitados, exigir que os dependentes sejam desabilitados na mesma alteração ou tratar de forma segura e explícita.
Não apagar dados históricos ao desabilitar módulos.
branch_feature_states() COMO FONTE DE VERDADE
Consolidar:
branch_feature_states(branch)


como resolução canônica de disponibilidade comercial da filial.
Cada módulo deve informar pelo menos:
plan_allowed
enabled

enabled só pode ser True se:
plano permite
+
switch da filial permite
+
dependências efetivas permitem
+
tenant está operacional

require_branch_feature() deve continuar sendo a barreira fail-closed no backend.
Não duplicar regras diferentes em vários módulos.
BACKEND — AUDITORIA COMPLETA
Auditar todos os endpoints tenant/operacionais existentes e garantir enforcement do módulo correspondente.
Isso inclui, conforme aplicável:
Balcão/vendas
Consumação
Mesas
Comandas
Caixa
Produtos
Categorias
Modificadores
Preços por filial
Estoque
Transferências
Inventários
Perdas
Compras
Recebimentos
Contas a pagar
Fornecedores
Clientes
Promoções
Produção
Impressoras
Rotas de impressão
Fila de impressão
Tickets
Financeiro
Formas de pagamento
Comissões
Dashboard
Relatórios
Auditoria
Dispositivos POS
APIs operacionais do POS

Não depender exclusivamente de esconder interface.
Uma chamada direta à API deve receber 403 quando o módulo estiver:
fora do plano
OU
desabilitado naquela filial

A regra vale para leitura e escrita quando o endpoint pertence àquele módulo.
Recursos compostos exigem todas as capabilities relevantes.
Exemplos:
contas a pagar
→ purchases + financial

produto/fornecedor
→ products + suppliers

relatório de estoque
→ reports + inventory

relatório financeiro
→ reports + financial

relatório de mesas/comandas
→ reports + tables + commands

Atualize os mapas existentes em SaaSTenantRuntimePermission/COMMERCIAL_FEATURES_BY_BASENAME/rotas específicas em vez de criar uma segunda arquitetura concorrente.
Endpoints customizados que não utilizem basename também precisam ser auditados.
FRONTEND — FAIL CLOSED
O mesmo estado resolvido pelo backend deve continuar chegando em:
User.branches[].features

E deve comandar toda a interface.
Quando um módulo estiver indisponível:
não aparece no menu
URL direta é bloqueada
página privada não renderiza
botões do módulo não aparecem
atalhos não aparecem
cards/KPIs do módulo não aparecem
selects/opções exclusivas daquele módulo não aparecem
permissões funcionais daquele módulo não aparecem como opção operacional

Revise:
app-shell.tsx
feature-guards.ts
authorized-routes.ts
AdminGuard
páginas privadas
editor de permissões

Não confiar apenas no AppShell.
Digitar diretamente, por exemplo:
/estoque
/compras
/producao
/relatorios/...
/pos-dispositivos

deve falhar/redirect quando a feature da filial estiver desligada.
MEU NEGÓCIO → CONFIGURAÇÕES DA FILIAL
Na seção existente:
Operação
Ative ou desative recursos desta filial.

passar a permitir controlar todos os módulos operacionais que o plano daquela empresa possui.
Exibir somente módulos que tenham:
plan_allowed = true

Não permitir habilitar via payload manual uma feature que o plano não possui.
Depois de salvar, o auth/me/estado de features e a interface devem refletir imediatamente a nova disponibilidade.
Usar nomes amigáveis em português.
CORE POS
O POS também faz parte desta regra.
feature.pos/pos.enabled não deve ser apenas uma configuração visual.
Se a empresa possui POS no plano, mas a filial desabilitou POS:
novo pareamento na filial → bloqueado
dispositivo existente → não pode continuar operacional
bootstrap → bloqueado
operador → não deve conseguir iniciar operação
venda → bloqueada

Para módulos internos do POS:
Venda rápida → counter + permissão
Mesas → tables + permissão
Comandas → commands + permissão
Caixa → cash_register + permissão

Manter modules_for() baseado em branch_feature_enabled().
Não criar allowlist funcional por máquina. A regra continua sendo:
plano + filial + RBAC

Configuração do dispositivo não substitui autorização funcional.
PRESERVAÇÃO DE DADOS E RBAC
Desabilitar módulo:
NÃO remove registros
NÃO remove histórico
NÃO apaga permissões dos perfis
NÃO apaga configuração do módulo
NÃO apaga devices
NÃO apaga vendas

Apenas torna a funcionalidade indisponível operacionalmente.
Se posteriormente o plano/filial reabilitar o módulo, as permissões RBAC existentes voltam a ser consideradas.
Isso é importante:
Entitlement/feature decide SE o módulo existe para aquele contexto.
RBAC decide QUEM pode usá-lo.

NÃO MEXER AINDA
Esta é somente a Parte 1 da Missão 2.
Não entrar ainda em:
regras específicas de categoria
propagação de produtos
copiar produto para filial
canais de venda do produto
alteração de comportamento de estoque do produto
redesign de modificadores
rotas Produto → Setor → Impressora
UX de POS Devices
dashboard visual
relatórios visuais
importação por planilha
Platform Admin público

Também não alterar:
CMV já aprovado
snapshot histórico de custos
motor financeiro
motor de estoque
pagamentos
Cielo
Stone
PagBank
SMTP/Resend
recuperação de senha

TESTES OBRIGATÓRIOS
Atualizar/criar cobertura para confirmar:
plano OFF / filial ON / RBAC ON → bloqueado
plano ON / filial OFF / RBAC ON → bloqueado
plano ON / filial ON / RBAC OFF → bloqueado
plano ON / filial ON / RBAC ON → permitido

dependência da filial OFF → dependente OFF

endpoint direto bloqueado
módulo some do frontend
deep-link é bloqueado
POS da filial desabilitada é bloqueado
módulo reabilitado preserva RBAC/dados

Cobrir pelo menos um módulo de cada grupo relevante e testes específicos das dependências.
Preservar os testes existentes.
Corrigir os testes, e não executar. O GitHub já faz isso.
Não executar:
python manage.py test
python manage.py check
migrate
makemigrations
npm test
npm run build
npm run lint
flutter test
flutter build

Se migration for necessária, escrevê-la corretamente sem executá-la.
ENTREGA
Ao concluir:
faça commit e push no main;
informe o SHA;
liste os arquivos alterados;
informe a migration criada;
explique como ficou a regra:
Plano → Filial → Dependências → RBAC

informe quais endpoints/módulos foram auditados;
confirme que URL direta/API/POS também estão fail-closed;
confirme que dados e permissões históricas não são apagados;
confirme explicitamente que não entrou nas Partes 2–7 da Missão 2.
Não faça deploy. Não mexa na VPS.