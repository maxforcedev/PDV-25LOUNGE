<role>
Reorganize a experiência de Backoffice agora que os fluxos operacionais principais já estão estabilizados.

Evite alterações de regra de negócio desnecessárias.
</role>

<block name="PRODUCTS">

Substitua o modal grande de Products por página dedicada:

/produtos
→ lista.

/produtos/[id]
→ detalhe/configuração.

Organize funcionalidades atuais em seções coerentes:

- Informações;
- Configuração de venda;
- Estoque/composição;
- Modificadores;
- Fornecedores/apresentações;
- Filiais/preços;
- Produção/destinos.

Topo:
- status;
- preço;
- ações conforme RBAC;
- duplicar;
- ativar/inativar;
- demais ações já existentes.

Reutilize componentes existentes.

Não duplique regra backend.
</block>

<block name="USERS">

Substitua o modal grande de Users por:

/usuarios
→ lista.

/usuarios/[id]
→ detalhe.

Seções:

- Informações;
- filiais/acessos;
- perfis;
- permissões/bloqueios;
- comissão individual;
- informações operacionais relevantes já existentes.

Mover a área atual de comissão individual para dentro do usuário correspondente.

NÃO recriar gerenciamento de Sessions removido anteriormente.
</block>

<block name="REPORTS">

Reorganize Relatórios por domínio.

Especialmente Estoque:

Relatórios
└── Estoque
    ├── Posição atual
    ├── Movimentações
    ├── Transferências
    ├── Divergências
    ├── Perdas
    └── Inventários

Crie rotas/páginas próprias quando necessário.

Reutilize services/querysets existentes.

Não duplique cálculo.

Audite os dados realmente disponíveis para organizar:

- Vendas;
- Atendimento;
- Caixa;
- Financeiro;
- Estoque;
- Compras;
- Contas a pagar;
- Auditoria.

Não crie relatório cuja métrica não possa ser calculada corretamente com os dados existentes.
</block>

<block name="BRANDING">

Criar branding global único para:

- página pública;
- Backoffice;
- Platform Admin.

Assets:

- logo retangular para fundo claro;
- logo retangular para fundo escuro;
- logo compacta para fundo claro;
- logo compacta para fundo escuro;
- favicon único.

Preserve fallback/compatibilidade com:
- logo_url;
- compact_logo_url;
- favicon_url.

Crie migration apropriada.
</block>

<task>
PÁGINA PÚBLICA

Aumentar a presença da logo.

Preservar proporção.

Não redesenhar a landing page inteira.
</task>

<task>
BACKOFFICE

Na sidebar escura, substituir:

ícone de escudo + CORE PDV + Administração

pela logo retangular apropriada para fundo escuro.

Use fallback se branding customizado não estiver disponível.
</task>

<task>
PLATFORM ADMIN

Consumir os mesmos assets globais.

Permitir configuração deles onde já existe configuração de plataforma.

NÃO alterar:
- tenant management;
- billing;
- MFA;
- support;
- subscriptions;
- funcionalidades administrativas.

Branding somente.
</task>

<validation>
Valide:

- rotas Products;
- deep-link;
- RBAC;
- User detail;
- permission UI;
- Reports;
- todas as rotas novas;
- branding fallback;
- light/dark;
- favicon;
- responsive;
- frontend lint/build;
- Platform Admin lint/build.
</validation>

<rules>
- Não alterar backend estável sem necessidade.
- Não implementar nova regra financeira.
- Não fazer commit.
- Não avançar para BLOCO 7.
</rules>

<final_response>
Informe alterações por domínio, rotas criadas, componentes reaproveitados, migrations e checks.

Finalize:
BLOCO 6 APROVADO
ou
BLOCO 6 NÃO APROVADO.
</final_response>