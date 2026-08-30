**# CORE PDV — PRE-POS HARDENING / CORREÇÕES OBRIGATÓRIAS ANTES DO POS**

\> **\*\*Objetivo:\*\*** revisar, corrigir e endurecer o estado atual do CORE PDV **\*\*antes de iniciar qualquer desenvolvimento do CORE POS / Flutter / Stone\*\***.

\>

\> Este trabalho é um **\*\*GATE PRE-POS\*\***. Enquanto os critérios de aceite deste documento não estiverem concluídos e validados, **\*\*NÃO iniciar o POS\*\***.

**---**

\<role>

Você está atuando como **\*\*Senior Staff Engineer / Security Engineer / QA Engineer\*\*** no CORE PDV.

Sua responsabilidade não é apenas "fazer o erro sumir".  

Você deve:

1\. identificar a **\*\*causa raiz\*\***;

2\. verificar se o mesmo padrão ocorre em outros pontos do projeto;

3\. corrigir o backend, frontend, banco e migrations quando necessário;

4\. preservar isolamento multi-tenant e integridade financeira;

5\. preservar os testes existentes, sem criar baterias extensas de testes durante as Fases 2 a 7;

6\. fazer validação mínima e objetiva durante cada fase e deixar a validação automatizada global para a Fase 8;

7\. documentar exatamente o que foi alterado, validado e o que permaneceu pendente.

\</role>

**---**

**## 1. REGRAS INEGOCIÁVEIS**

\<hard\_rules>

\- **\*\*NÃO iniciar ou implementar o POS nesta tarefa.\*\***

\- **\*\*NÃO implementar \`django-csp\` nem CSP no Next.js nesta tarefa.\*\***

\- Não mascarar erros com \`try/except\` genérico.

\- Não remover validações de backend apenas para o frontend "funcionar".

\- Não alterar regras financeiras ou de estoque sem rastrear todos os consumidores.

\- Não fazer exclusão física de registros históricos que possam ter vínculo com vendas, compras, estoque, auditoria ou comandas.

\- Não quebrar compatibilidade multiempresa/multifilial.

\- Não confiar em \`company\`, \`branch\`, \`user\`, \`product\`, \`supplier\` ou IDs enviados pelo cliente sem validação server-side.

\- Não aceitar relações cross-tenant apenas porque o usuário conhece o ID.

\- Não criar migration destrutiva sem necessidade.

\- Não apagar dados existentes para "resolver" constraints.

\- Não comentar ou desabilitar testes existentes.

\- Não reduzir cobertura removendo assertions.

\- Não mudar o design system global sem necessidade.

\- Não duplicar lógica de domínio entre views/serializers/services.

\- Quando houver uma regra de negócio já centralizada em \`services.py\`, reutilizá-la.

\- **\*\*MODO ECONÔMICO DE EXECUÇÃO:\*\*** nas Fases 2 a 7, não criar novos testes automatizados salvo autorização explícita do usuário.

\- Nas Fases 2 a 7, não executar suíte global, Docker build completo, smoke global, lint/build global ou auditorias amplas repetidamente.

\- Preservar todos os testes existentes. Não remover, comentar, desabilitar ou enfraquecer testes para obter resultado verde.

\- Quando houver um teste existente diretamente relacionado à alteração e sua execução for rápida, ele pode ser executado **\*\*uma única vez ao final da fase\*\***. Não repetir a suíte após cada patch.

\- Toda nova migration deve ser executável em banco com dados existentes.

\- A validação automatizada completa do projeto — suíte backend, lint, builds, Docker, migrations e smoke — será executada **\*\*uma única vez na Fase 8\*\***.

\- Antes de alterar qualquer arquivo, **\*\*leia a implementação real atual\*\***. Os caminhos citados neste documento são pontos de partida, não autorização para assumir que o código ainda está idêntico.

\</hard\_rules>

**---**

**# 2. METODOLOGIA OBRIGATÓRIA**

Execute o trabalho em fases.

**## MODO DE EXECUÇÃO ATUAL — ECONOMIA DE CRÉDITOS**

As Fases 0 e 1 já foram concluídas e registradas no final deste documento.

\- **\*\*NÃO reexecutar Fase 0 nem Fase 1.\*\***

\- **\*\*NÃO repetir os testes, builds ou revisões já registrados nessas fases.\*\***

\- A partir da Fase 2, executar **\*\*somente uma fase por vez\*\***.

\- Ao terminar uma fase, atualizar o checklist, entregar um checkpoint curto e **\*\*PARAR\*\***.

\- **\*\*NÃO iniciar a fase seguinte sem autorização explícita do usuário.\*\***

\- Nas Fases 2 a 7, priorizar leitura do código, análise de causa raiz, implementação e validação mínima.

\- Nas Fases 2 a 7, **\*\*NÃO criar novos testes automatizados por padrão\*\***.

\- Nas Fases 2 a 7, **\*\*NÃO executar suíte completa de backend, builds completos, Docker build, smoke global ou CI equivalente\*\***.

\- Se existir um teste automatizado já pronto e diretamente relacionado à mudança, executar no máximo o teste/módulo focado **\*\*uma única vez no final da fase\*\***, apenas quando for realmente útil.

\- A Fase 8 será o único momento para validação global automatizada do projeto.

\- Evitar subagentes/revisões independentes repetitivas para problemas simples. Usar análise adicional apenas quando houver risco real de segurança, concorrência, migration ou integridade de dados.

\- Não transformar uma correção pequena em refatoração estrutural ampla sem necessidade comprovada.

\- Se durante uma fase surgir uma descoberta fora do escopo daquela fase, registrar como pendência e seguir; não iniciar uma nova frente automaticamente.

**## Fase 0 — Baseline antes de modificar**


Antes de escrever código:

1\. Identifique:

   - estrutura do backend;

   - estrutura do frontend;

   - platform-admin;

   - banco;

   - migrations;

   - serviços de domínio;

   - testes existentes;

   - Docker;

   - CI;

   - scripts de smoke/release.

2\. Rode o máximo possível da validação existente:

   - Django system checks;

   - migration consistency;

   - testes backend;

   - lint frontend;

   - build frontend;

   - build platform-admin;

   - Docker build/config;

   - scripts de validação existentes.

3\. Registre qualquer falha que **\*\*já existia antes das alterações\*\***.

4\. Faça uma busca global pelos padrões relacionados aos bugs abaixo, para evitar corrigir apenas o local visualmente afetado.

**---**

**# 3. BUG P0 — \`/PRODUTOS\` RETORNA 500 EM FILIAL NOVA**

**## Sintoma conhecido**

Usuário possui duas filiais:

\- filial A possui produtos/estoque e funciona;

\- filial B é nova e não possui estoque/materialização completa.

Ao abrir \`/produtos\`, ocorrem respostas \`500\`.

Erro observado:

\`\`\`text

ValueError: content and package\_content are required

\`\`\`

Ponto observado anteriormente:

\`\`\`text

apps/products/serializers.py

get\_branch\_stock()

\`\`\`

chamando algo equivalente a:

\`\`\`python

content\_breakdown(

    stock.current\_content if stock else Decimal("0"),

    config.package\_content,

)

\`\`\`

com \`current\_content=None\` ou configuração incompatível.

**## Objetivo**

Uma filial nova, vazia ou ainda sem \`Stock\` materializado **\*\*NUNCA pode derrubar o endpoint de produtos\*\***.

**## Trabalho obrigatório**

1\. Rastreie completamente:

   - \`get\_branch\_stock\`;

   - \`content\_breakdown\`;

   - models de \`Stock\`;

   - configurações de estoque fracionado/conteúdo;

   - criação de filial;

   - criação de produto;

   - alterações de estoque mínimo;

   - compras;

   - inventário;

   - qualquer \`get\_or\_create(Stock...)\`;

   - seeds/fixtures.

2\. Descubra por que existem registros com:

   - \`current\_content = NULL\`;

   - \`package\_content = NULL\`;

   - combinações semanticamente inválidas.

3\. Centralize a inicialização/materialização de \`Stock\`.

   Não deixar cada view/service decidir de forma independente como inicializar os campos.

4\. Para produtos com controle que exija conteúdo fracionado:

   - ausência de saldo deve ser representada de forma consistente como zero;

   - nunca como estado que derrube serialização.

5\. Para produtos aos quais \`content\_breakdown()\` não se aplica:

   - não chamar a função indevidamente.

6\. Adicione correção de dados existentes, quando necessária:

   - preferencialmente por data migration segura;

   - sem destruir movimentações;

   - sem inventar estoque positivo.

7\. O serializer deve ser resiliente a filial sem estoque.

8\. Não esconder inconsistência estrutural grave silenciosamente:

   - corrija a origem;

   - deixe logging útil quando apropriado.

**## Validação da Fase 1 — JÁ CONCLUÍDA**

A Fase 1 já foi validada e suas evidências estão registradas no checklist ao final deste documento.

**Não criar nem reexecutar testes desta fase. Não refazer a revisão de materialização de Stock.**

Somente retornar à Fase 1 se uma alteração posterior quebrar explicitamente este comportamento.

**## Critério de aceite**

\`\`\`text

GET /api/v1/products/

\`\`\`

não pode retornar \`500\` simplesmente porque a filial é nova, vazia ou não possui saldo.

**---**

**# 4. BUG P0 — MODIFICADORES: 5 UNIDADES SENDO INTERPRETADAS COMO 5 OPÇÕES**

**## Sintoma**

Grupo:

\`\`\`text

Distribua exatamente 5 unidades

\`\`\`

Usuário seleciona:

\`\`\`text

MELANCIA

Qtd.: 5

\`\`\`

UI mostra:

\`\`\`text

5/5

\`\`\`

mas também mostra:

\`\`\`text

redbull exige no mínimo 5 opção(ões).

\`\`\`

Isso é incorreto.

**## Regra esperada**

Exemplo de grupo Red Bull com total obrigatório de 5 unidades:

\`\`\`text

5 Melancia                  → válido

5 Tropical                  → válido

3 Melancia + 2 Tropical     → válido

1 + 1 + 1 + 1 + 1          → válido

\`\`\`

Desde que as regras específicas do grupo sejam respeitadas.

O sistema deve diferenciar explicitamente:

\`\`\`text

quantidade de opções distintas selecionadas

\`\`\`

de:

\`\`\`text

quantidade total distribuída entre as opções

\`\`\`

**## Trabalho obrigatório**

**### 4.1 Auditar frontend**

Localize toda lógica semelhante a:

\`\`\`text

selectedCount

selectedTotal

min\_selections

max\_selections

required\_quantity

expected\_quantity

\`\`\`

Não corrigir apenas a mensagem.

Verificar:

\- modal de produto;

\- carrinho;

\- edição do item;

\- PDV;

\- venda direta;

\- comanda;

\- qualquer componente reutilizado.

**### 4.2 Auditar backend**

Procure validações semelhantes a:

\`\`\`python

selection\_count = len(selections)

\`\`\`

e comparação com:

\`\`\`text

min\_selections

max\_selections

expected\_quantity

required\_quantity

\`\`\`

A API deve possuir a mesma semântica do frontend.

**### 4.3 Definir a semântica de forma única**

Internamente devem existir conceitos distintos, mesmo que os nomes atuais precisem ser preservados por compatibilidade:

\`\`\`text

selection\_count

\= quantidade de opções distintas selecionadas com quantidade > 0

selected\_quantity\_total

\= soma das quantidades de todas as opções

\`\`\`

Quando o grupo for do tipo/disposição que exige uma quantidade total exata, a validação de quantidade deve usar:

\`\`\`text

selected\_quantity\_total

\`\`\`

e não \`len(selections)\`.

Não remova \`min\_selections\`/\`max\_selections\` se eles tiverem outra finalidade legítima.  

Corrija a regra sem quebrar grupos do tipo:

\`\`\`text

"Escolha até 2 sabores"

"Escolha 1 adicional"

\`\`\`

**### 4.4 Mensagens**

A mensagem deve refletir a regra real.

Exemplo:

\`\`\`text

Distribua exatamente 5 unidades.

\`\`\`

ou:

\`\`\`text

Faltam 2 unidades para completar este grupo.

\`\`\`

Não usar "5 opções" quando a regra é quantidade.

**## Validação mínima da Fase 2 — SEM NOVOS TESTES AUTOMATIZADOS**

Não criar novos arquivos de teste nesta fase.

Validar diretamente o comportamento alterado, usando a forma mais barata disponível no ambiente:

\- total 5 em uma única opção → aceita;

\- 3 + 2 → aceita;

\- total 4 → rejeita;

\- total 6 → rejeita;

\- grupo que realmente limita opções distintas continua respeitando esse limite;

\- frontend e backend usam a mesma semântica.

Se já existir um teste focado exatamente nessa regra, pode executá-lo uma única vez ao final da fase.

Não executar suíte global de vendas/comandas/frontend nesta fase.

**## Critério de aceite**

O caso da imagem fornecida deve funcionar:

\`\`\`text

Melancia = 5

Total = 5/5

\`\`\`

→ **\*\*Adicionar ao carrinho permitido.\*\***

**---**

**# 5. P0 — REMOVER CONCEITO DE “MODIFICADOR ARQUIVADO”**

**## Decisão de produto**

Para modificadores, o usuário não deve trabalhar com:

\`\`\`text

ativo

inativo

arquivado

\`\`\`

A experiência deve ser:

\`\`\`text

EXISTE

ou

FOI EXCLUÍDO

\`\`\`

A exclusão deve ser **\*\*soft-delete\*\*** no banco para manter integridade histórica.

**## Trabalho obrigatório**

1\. Audite:

   - \`ModifierGroup\`;

   - \`ModifierOption\`;

   - serializers;

   - managers/querysets;

   - endpoints;

   - filtros;

   - frontend;

   - textos "arquivados";

   - status ACTIVE/INACTIVE atualmente usados;

   - histórico de vendas/comandas.

2\. Implementar lifecycle de exclusão coerente, por exemplo:

\`\`\`text

deleted\_at

deleted\_by

\`\`\`

ou reutilizar infraestrutura de soft-delete já existente no projeto, se houver uma padrão consolidado.

3\. Registros soft-deleted:

   - não aparecem em listagens normais;

   - não podem ser selecionados em novos produtos/vendas;

   - permanecem referenciáveis pelo histórico;

   - não são fisicamente apagados;

   - não precisam possuir UI de "arquivados";

   - não precisam ter fluxo de restauração, salvo se o projeto já possuir requisito explícito.

4\. Remover da interface:

   - "Ver arquivados";

   - "Ocultar arquivados";

   - ações confusas de ativar/desativar que estejam sendo usadas como exclusão.

5\. Se \`status\` ainda for necessário internamente por compatibilidade, não deixar dois lifecycles concorrentes sem uma justificativa técnica clara.

**---**

**# 6. P0 — CONSTRAINT DE NOME BLOQUEIA RECRIAÇÃO APÓS SOFT-DELETE**

**## Erro observado**

\`\`\`text

Restrição "products\_modifier\_group\_company\_name\_ci\_unique" foi violada.

\`\`\`

Cenário:

1\. existiu modificador/grupo chamado \`Redbull\`;

2\. ele foi "apagado"/arquivado;

3\. usuário tenta criar \`Redbull\` novamente;

4\. banco bloqueia por unique constraint.

**## Objetivo**

Soft-delete não pode impedir a criação de um novo registro ativo com o mesmo nome.

**## Trabalho obrigatório**

1\. Auditar todas as constraints de:

   - \`ModifierGroup\`;

   - \`ModifierOption\`;

   - entidades associadas que também possuam lifecycle/soft-delete.

2\. Unique constraints que representam "unicidade entre registros existentes" devem ignorar registros soft-deleted.

Exemplo conceitual:

\`\`\`text

UNIQUE WHERE deleted\_at IS NULL

\`\`\`

3\. Preservar case-insensitive uniqueness para registros ativos.

4\. Criar migration segura:

   - remover constraint antiga;

   - criar partial/conditional constraint correta.

5\. Verificar se existem dados atuais que poderiam impedir a migration.

**## Validação mínima da Fase 3 — SEM NOVOS TESTES AUTOMATIZADOS**

Não criar bateria de regressão nesta fase.

Validar diretamente, por shell/API/consulta controlada ao banco quando necessário:

\- criar `Redbull`;

\- soft-delete `Redbull`;

\- criar novo `Redbull`;

\- operação deve funcionar;

\- dois `Redbull` não deletados continuam proibidos;

\- case-insensitive uniqueness continua funcionando;

\- histórico antigo permanece íntegro.

Executar somente checks de migration estritamente necessários à migration criada.

Não executar suíte global.

**---**

**# 7. P1 — COMPRAS: CAMPO “QNTD RECEBIDA” EXIBE \`12.00000000\`**

**## Sintoma**

No fluxo de recebimento de compras:

\`\`\`text

12.00000000

\`\`\`

é apresentado no input em vez de:

\`\`\`text

12

\`\`\`

**## Objetivo**

Melhorar apresentação sem perder precisão.

**## Regra**

Exemplos:

\`\`\`text

12.00000000 → 12

12.50000000 → 12,5 (ou formato numérico padronizado pelo frontend atual)

12.12500000 → 12,125

\`\`\`

Não arredondar ou truncar valores significativos.

**## Trabalho obrigatório**

1\. Identifique a origem:

   - serializer;

   - DTO;

   - estado React;

   - input;

   - formatter.

2\. Não mudar a precisão armazenada no banco só para resolver UI.

3\. Criar/reutilizar helper de formatação para valor decimal editável.

4\. Garantir que, após o usuário editar e enviar:

   - decimal válido chega corretamente ao backend;

   - locale não causa envio incorreto;

   - quantidades fracionadas continuam possíveis quando o produto aceita.

5\. Verificar outros inputs que possam apresentar o mesmo padrão de zeros artificiais.

**## Validação mínima da Fase 4 — COMPRAS**

Não criar novos testes automatizados.

Validar manualmente/focadamente:

\- `12.00000000` é exibido como `12`;

\- `12.50000000` mantém a parte significativa;

\- quantidade fracionada legítima continua editável;

\- submit envia o valor correto;

\- recebimento parcial continua funcionando.

Não rodar build global do frontend nesta fase.

**---**

**# 8. P1 — APRESENTAÇÕES DEVEM PERTENCER AO PRODUTO, NÃO AO FORNECEDOR**

**## Decisão de domínio**

Uma apresentação descreve como um produto pode ser comprado/manipulado.

Exemplo:

\`\`\`text

Produto: Heineken

Apresentações:

\- UN

\- CX 12

\- CX 24

\- FD 6

\`\`\`

Essas apresentações existem independentemente de qual fornecedor vende o produto.

**## Arquitetura desejada**

\`\`\`text

PRODUCT

│

├── ProductPurchasePresentation

│   ├── UN

│   ├── CX12

│   └── CX24

│

└── Suppliers

    ├── Supplier A

    │   └── pode fornecer CX12

    └── Supplier B

        └── pode fornecer CX24

\`\`\`

O fornecedor pode se relacionar com uma apresentação já existente e possuir atributos próprios, por exemplo:

\`\`\`text

supplier\_code

supplier\_barcode

is\_default

last\_cost

\`\`\`

se estes conceitos já existirem ou forem necessários ao fluxo atual.

**## Observação importante**

O projeto aparentemente já possui algo semelhante a:

\`\`\`text

ProductPurchasePresentation

\`\`\`

ligado diretamente a \`Product\`.

Se isso já estiver correto no backend:

**\*\*NÃO recriar o domínio.\*\***

Refatore o fluxo/API/frontend para utilizar a entidade correta e migre os relacionamentos legados com o mínimo de ruptura.

**## Trabalho obrigatório**

1\. Mapear:

   - \`ProductPurchasePresentation\`;

   - \`ProductSupplier\`;

   - \`ProductSupplierUnit\`;

   - compra;

   - entrada direta;

   - conversão de unidade;

   - custo;

   - frontend de produtos;

   - frontend de fornecedores.

2\. Definir uma única fonte da verdade para:

   - apresentação;

   - fator de conversão;

   - unidade.

3\. A apresentação deve ser cadastrada a partir do **\*\*produto\*\***.

4\. O relacionamento fornecedor-produto deve referenciar uma apresentação existente quando necessário.

5\. Não duplicar fator de conversão em múltiplos lugares sem regra de precedência.

6\. Se houver registros legados:

   - escrever migration/data migration;

   - preservar compras históricas;

   - preservar snapshots de compra existentes.

**## Critério de UX**

Dentro de Produto:

\`\`\`text

Apresentações

\+ Adicionar apresentação

\`\`\`

separado de:

\`\`\`text

Fornecedores

\+ Vincular fornecedor

\`\`\`

**---**

**# 9. P0 SECURITY — IMPEDIR ENUMERAÇÃO DE USUÁRIOS**

**## Problema**

Respostas diferentes permitem descobrir se um e-mail existe.

Exemplos de mensagens atuais/anteriores:

\`\`\`text

E-mail ou senha inválidos.

Seu usuário está inativo.

A empresa vinculada ao seu usuário está inativa.

A filial vinculada ao seu usuário está inativa.

\`\`\`

**## Objetivo**

Antes de uma identidade estar validamente autenticada, a resposta não deve revelar se:

\- e-mail existe;

\- conta está ativa;

\- conta está inativa;

\- \`can\_login\` está false;

\- empresa existe;

\- tenant está ativo;

\- usuário pertence a determinada empresa.

**## Regra externa**

Para credencial inválida ou identidade que não pode autenticar:

\`\`\`text

E-mail ou senha inválidos.

\`\`\`

Use a mesma:

\- mensagem;

\- status HTTP;

\- estrutura de payload;

\- comportamento observável razoável.

Não retornar campos que entreguem a causa interna.

**## Trabalho obrigatório**

Auditar:

\- login Backoffice;

\- login Platform Admin;

\- Django Admin;

\- recuperação de senha;

\- convite/ativação, quando existir;

\- endpoints que aceitam e-mail e retornam existência;

\- reset de senha.

**## Observação**

Depois que o usuário está autenticamente identificado, mensagens operacionais podem informar bloqueios a que ele tem direito de conhecer, desde que isso não reabra enumeração anônima.

**## Validação mínima da Fase 5 — ENUMERAÇÃO**

Não criar novos testes automatizados.

Comparar diretamente as respostas dos cenários relevantes:

\- e-mail inexistente;

\- senha inválida;

\- usuário inativo;

\- conta sem login;

\- tenant inativo, quando aplicável;

\- tentativa válida.

Para estados não autenticados equivalentes, validar que mensagem/status/payload não criam oráculo de existência.

Não executar suíte completa de autenticação.

**---**

**# 10. P0 SECURITY — ADICIONAR \`django-axes\`**

**## Objetivo**

Adicionar proteção contra brute force nos fluxos de autenticação, incluindo:

\`\`\`text

Backoffice

Platform Admin

Django Admin nativo

\`\`\`

**## Regra importante**

**\*\*Não basta instalar o pacote.\*\***

O projeto possui autenticação customizada.  

Qualquer fluxo que use diretamente:

\`\`\`python

check\_password(...)

\`\`\`

ou valide usuário fora do pipeline de \`authenticate()\` precisa ser revisado para garantir que o Axes realmente observe tentativas válidas e inválidas.

**## Trabalho obrigatório**

1\. Adicionar versão estável do \`django-axes\` compatível com:

   - versão atual do Django;

   - Python atual do projeto.

2\. Seguir o padrão real de dependências do repositório.

3\. Configurar corretamente:

   - \`INSTALLED\_APPS\`;

   - authentication backends;

   - middleware, se exigido pela versão;

   - settings.

4\. Integrar com:

   - login Backoffice;

   - Platform Admin;

   - \`/admin/\`.

5\. Configurações de threshold/cooldown devem ser centralizadas e configuráveis por environment.

**### Default recomendado, salvo incompatibilidade com arquitetura atual:**

\`\`\`text

5 falhas

cooldown de 15 minutos

\`\`\`

Evitar lock global ingênuo apenas por IP, pois redes de estabelecimentos podem compartilhar IP.

Use estratégia que leve em conta identidade + origem de forma segura conforme recursos suportados pela versão utilizada.

6\. Auditar se proxies/reverse proxy estão fornecendo IP correto.

   Não confiar cegamente em headers manipuláveis pelo cliente.

7\. Logging:

   - registrar bloqueios;

   - não logar senhas;

   - não expor stack sensível ao usuário.

**## Validação mínima da Fase 5 — DJANGO-AXES**

Não criar novos testes automatizados nesta fase.

Validar o Axes de forma focada nos três fluxos:

\- Backoffice;

\- Platform Admin;

\- Django Admin.

Fazer somente as tentativas necessárias para confirmar:

\- falhas abaixo do limite ainda permitem nova tentativa;

\- atingir o limite bloqueia;

\- credencial correta durante lock permanece bloqueada conforme política;

\- cooldown/configuração foi aplicada;

\- uma identidade diferente não é bloqueada indevidamente por colisão simples.

Após validar, limpar/resetar os registros de lockout do ambiente de desenvolvimento se necessário.

Não executar suíte global.

**---**

**# 11. P0 SECURITY — AUDITORIA COMPLETA DE IDOR**

**## Objetivo**

Garantir que conhecer um UUID/ID não permita acessar ou modificar recurso de:

\`\`\`text

outra empresa

outra filial não autorizada

outro tenant

\`\`\`

Isso deve ser validado em TODO o projeto, não apenas em produtos.

**## Áreas mínimas da auditoria**

Verificar todos os ViewSets/APIViews/actions/serializers de:

\- companies;

\- branches;

\- memberships;

\- users;

\- customers;

\- suppliers;

\- products;

\- categories;

\- modifier groups/options;

\- purchase presentations;

\- inventory;

\- stock;

\- stock adjustments;

\- transfers;

\- purchases;

\- purchase items;

\- accounts payable;

\- sales;

\- sale items;

\- payments;

\- cash registers;

\- cash sessions;

\- commands;

\- tables;

\- production;

\- printers;

\- print jobs;

\- SaaS/admin;

\- support sessions;

\- audit;

\- integrations existentes;

\- qualquer endpoint de upload/download/anexo.

**## Vetores obrigatórios**

**### 11.1 Detail endpoints**

\`\`\`text

GET /resource/{id}

\`\`\`

Objeto de outro tenant não deve ser retornado.

**### 11.2 Mutation**

\`\`\`text

PATCH

PUT

DELETE

POST action

\`\`\`

ID conhecido não pode permitir alteração de outro tenant.

**### 11.3 IDs aninhados no payload**

Exemplo:

\`\`\`json

{

  "product": "uuid-de-outro-tenant"

}

\`\`\`

Não confiar em \`PrimaryKeyRelatedField(queryset=Model.objects.all())\` sem validação contextual adequada.

Sempre que razoável, o próprio queryset do campo deve ser limitado pelo contexto autorizado.

**### 11.4 Query parameters**

Auditar:

\`\`\`text

?company=

?branch=

?user=

?product=

?supplier=

\`\`\`

Usuário não pode trocar contexto enviando ID arbitrário.

**### 11.5 Headers**

Auditar:

\`\`\`text

X-Branch-ID

\`\`\`

Ele deve selecionar apenas filiais às quais o usuário tem acesso.

**### 11.6 Nested actions**

Exemplo:

\`\`\`text

/commands/{command\_id}/items/{item\_id}

/purchases/{purchase\_id}/receive/

/sales/{sale\_id}/cancel/

\`\`\`

Validar tanto pai quanto filho.

**## Resposta**

Para recurso de outro tenant, preferir **\*\*404\*\*** quando isso for consistente com a arquitetura, evitando confirmar a existência do objeto.

Não transformar toda falta de permissão em 404 se houver semântica legítima de 403 dentro do próprio tenant.

**## Auditoria e validação mínima da Fase 6 — SEM NOVOS TESTES AUTOMATIZADOS**

**Não criar uma suíte/matriz automatizada de IDOR nesta missão.**

Usar inspeção de código + chamadas manuais/focadas somente nos pontos realmente suspeitos ou corrigidos.

Usar como referência conceitual:

```text
Tenant A
Tenant B
Branch A1
Branch A2
Branch B1
User A
User B
```

Para cada vulnerabilidade encontrada, validar diretamente que:

\- leitura cruzada não funciona;

\- mutação cruzada não funciona;

\- IDs aninhados não escapam do tenant;

\- `X-Branch-ID` não seleciona filial sem acesso;

\- query params não trocam contexto arbitrariamente.

Priorizar os vazamentos já encontrados no baseline e os padrões de alto risco.

Não tentar gerar centenas de requests apenas para "cobertura".

Não executar suíte global de testes nesta fase.

**## Entrega obrigatória**

No relatório final, criar uma seção:

\`\`\`text

IDOR AUDIT

\`\`\`

com:

\- endpoints auditados;

\- vulnerabilidades encontradas;

\- correções;

\- validações focadas realizadas;

\- áreas sem risco identificado.

**---**

**# 12. P1 SECURITY — REDUZIR TEMPO DE SESSÃO**

\> **\*\*CSP está explicitamente fora do escopo.\*\***

**## Problema**

\`SESSION\_COOKIE\_AGE\` não está configurado e herda default do Django.

**## Objetivo**

Reduzir exposição de sessão roubada sem tornar o PDV/backoffice inutilizável durante um turno.

**## Implementação recomendada**

Tornar configurável via environment.

Default inicial recomendado para o backoffice:

\`\`\`text

8 horas = 28800 segundos

\`\`\`

Se a arquitetura permitir timeout por inatividade com segurança, avaliar:

\`\`\`text

SESSION\_SAVE\_EVERY\_REQUEST = True

\`\`\`

de forma consciente.

Não alterar política de cookie seguro existente:

\`\`\`text

Secure

HttpOnly

SameSite

\`\`\`

sem justificativa.

**## Também auditar**

\- logout invalida sessão;

\- alteração de senha invalida sessões quando aplicável;

\- suspensão de usuário impede reutilização indevida;

\- support session não herda sessão infinita;

\- Platform Admin não deve ficar permanentemente autenticado.

**## Critério**

A configuração deve aparecer em \`.env.example\`/documentação operacional correspondente.

**---**

**# 13. P1 — RELEASE / VERSÃO DO SISTEMA**

**## Objetivo**

Tornar possível saber exatamente qual versão/build está implantada.

Precisamos conseguir responder:

\`\`\`text

Qual versão do CORE PDV está rodando?

Qual commit?

Qual ambiente?

Quando foi feito o build?

\`\`\`

**## Arquitetura**

Criar uma única fonte de versão da aplicação.

Sugestão:

\`\`\`text

VERSION

\`\`\`

na raiz, contendo versão semântica:

\`\`\`text

0.x.y

\`\`\`

ou reutilizar uma fonte já existente se o projeto tiver padrão melhor.

Adicionar metadata de build:

\`\`\`text

APP\_VERSION

GIT\_SHA

BUILD\_DATE

ENVIRONMENT

\`\`\`

**## Backend**

Disponibilizar metadata de forma apropriada.

Exemplo conceitual:

\`\`\`json

{

  "version": "0.9.0",

  "commit": "a82ef91",

  "environment": "production",

  "build\_date": "2026-08-29T..."

}

\`\`\`

Não expor secrets.

**## Frontend**

Exibir discretamente em local apropriado, como:

\`\`\`text

Perfil / Sobre

rodapé de configurações

\`\`\`

Formato:

\`\`\`text

CORE PDV v0.9.0

build a82ef91

\`\`\`

**## Platform Admin**

Também deve conseguir identificar a versão implantada.

**## Docker/CI**

Sempre que possível, propagar:

\- version;

\- git SHA;

\- build date

durante build/deploy sem depender de edição manual de vários arquivos.

**## Logs**

Startup log deve incluir pelo menos versão + ambiente + SHA.

**## Opcional, se fizer sentido sem aumentar excessivamente o escopo**

Criar/atualizar:

\`\`\`text

CHANGELOG.md

\`\`\`

Mas não transformar esta tarefa em construção de um sistema completo de release notes.

**---**

**# 14. REVISÃO SISTÊMICA APÓS AS CORREÇÕES**

Depois de implementar os itens conhecidos, **\*\*não encerre imediatamente\*\***.

Faça uma nova inspeção do projeto buscando padrões semelhantes.

**## Buscar especificamente**

**### Dados opcionais chegando em funções que exigem valor**

Exemplo do bug:

\`\`\`text

None → helper que exige Decimal

\`\`\`

**### Soft-delete + unique constraints**

Buscar outras entidades com:

\`\`\`text

deleted\_at/status/lifecycle

\+

UNIQUE

\`\`\`

que possam sofrer o mesmo problema.

**### Decimal cru em inputs**

Buscar strings do banco como:

\`\`\`text

12.00000000

\`\`\`

sendo colocadas diretamente em inputs.

**### Querysets globais em serializers**

Buscar:

\`\`\`python

Model.objects.all()

\`\`\`

em campos relacionados tenant-scoped.

**### \`Model.objects.get(pk=id)\` sem tenant context**

Auditar.

**### Confiança excessiva em \`company\`/\`branch\` do request**

Auditar.

**### Mensagens que revelam existência de conta**

Auditar.

**### \`check\_password\` fora do fluxo autenticador**

Auditar para Axes.

**### Validações duplicadas frontend/backend com semântica divergente**

Especialmente:

\- modifiers;

\- estoque;

\- compras;

\- pagamento;

\- comanda.

**---**

**# 15. VALIDAÇÃO FINAL ÚNICA — EXECUTAR SOMENTE NA FASE 8**

Esta é a **única fase** em que a validação global automatizada deve ser executada.

**Não criar novos testes automatizados nesta fase apenas para aumentar cobertura.**  
O objetivo é rodar o que o projeto já possui e verificar se as alterações das Fases 2 a 7 não quebraram o sistema.

Executar cada grupo global **uma única vez**. Se houver falha, diagnosticar e executar novamente somente o alvo afetado; não repetir toda a suíte sem necessidade.

**## Backend**

Executar uma única vez:

```text
Django check
migration consistency
makemigrations --check
test suite existente
```

Usar PostgreSQL real quando o fluxo oficial do projeto exigir PostgreSQL.

**## Frontend**

Executar uma única vez o padrão oficial já existente:

```text
lint
type checks quando existentes
build
```

para:

\- frontend;

\- platform-admin.

Evitar reinstalar dependências se o ambiente já estiver íntegro.

**## Docker**

Executar uma única validação final necessária:

```text
docker compose config
build oficial quando necessário
healthchecks/startup
```

Não repetir build sem cache diversas vezes.

**## Smoke**

Executar o smoke existente uma única vez.

**## Regra de economia**

Se um comando global falhar:

1. registrar a falha;
2. identificar o alvo;
3. corrigir;
4. executar primeiro somente a validação focada afetada;
5. repetir o global somente quando realmente necessário para o veredito PRE-POS.

**---**

**# 16. TESTE MANUAL OBRIGATÓRIO PRE-POS**

Criar checklist e validar manualmente, quando o ambiente permitir:

**## Login**

\- login correto;

\- senha errada;

\- usuário inexistente;

\- usuário bloqueado pelo Axes;

\- logout;

\- Django Admin;

\- Platform Admin.

**## Empresa/filial**

\- trocar filial;

\- filial vazia;

\- filial com produtos;

\- usuário sem acesso à filial.

**## Produtos**

\- lista vazia;

\- criar produto;

\- apresentação;

\- fornecedor;

\- estoque zero;

\- produto fracionado.

**## Modificadores**

\- criar grupo;

\- criar opções;

\- excluir;

\- recriar mesmo nome;

\- produto com distribuição de exatamente 5 unidades;

\- 5 de uma opção;

\- 3 + 2;

\- quantidade inválida.

**## Compras**

\- criar pedido;

\- receber integral;

\- receber parcial;

\- input de quantidade não mostra zeros artificiais;

\- custo e estoque corretos.

**## Multi-tenant / IDOR**

Tentar manipular IDs manualmente entre dois tenants.

Nenhuma leitura ou mutação indevida pode ocorrer.

**---**

**# 17. DEFINITION OF DONE**

Este trabalho somente pode ser considerado concluído quando:

\- [x] \`/produtos\` não retorna 500 em filial nova/vazia.

\- [x] causa raiz de \`current\_content/package\_content\` foi corrigida.

\- [x] dados existentes inconsistentes foram tratados com segurança.

\- [x] regra de modificadores diferencia opções de quantidade total.

\- [x] caso \`Melancia = 5\` funciona.

\- [x] backend e frontend usam a mesma semântica.

\- [x] "modificadores arquivados" foi removido do fluxo.

\- [x] modificadores usam soft-delete coerente.

\- [x] nome pode ser recriado após soft-delete.

\- [x] constraint ainda bloqueia duplicados ativos.

\- [x] compra mostra \`12\` em vez de \`12.00000000\`.

\- [x] apresentações pertencem diretamente ao produto.

\- [x] fornecedores relacionam-se à apresentação sem serem donos dela.

\- [x] enumeração de usuários foi eliminada.

\- [x] \`django-axes\` protege Backoffice.

\- [x] \`django-axes\` protege Platform Admin.

\- [x] \`django-axes\` protege Django Admin.

\- [x] auditoria IDOR completa foi realizada.

\- [x] auditoria IDOR e validações cross-tenant focadas foram concluídas.

\- [x] \`SESSION\_COOKIE\_AGE\` foi reduzido e configurável.

\- [x] versão/release/build do CORE PDV é identificável.

\- [x] migrations estão consistentes.

\- [x] suíte backend existente foi executada na Fase 8 e o resultado real foi registrado.

\- [x] lint/build frontend foram executados uma única vez na Fase 8 e o resultado foi registrado.

\- [x] lint/build platform-admin foram executados uma única vez na Fase 8 e o resultado foi registrado.

\- [x] Docker build passa.

\- [x] CI equivalente está verde.

\- [x] smoke test passa.

\- [x] nenhum teste existente foi removido/desabilitado para obter verde.

\- [x] relatório final foi produzido.

\- [x] **\*\*nenhum código do POS foi iniciado nesta tarefa.\*\***

\- [x] **\*\*nenhum trabalho de django-csp/CSP Next foi realizado nesta tarefa.\*\***

**---**

**# 18. RELATÓRIO FINAL OBRIGATÓRIO**

Ao terminar, responda com um relatório estruturado exatamente nestas seções:

**## 1. Resumo executivo**

Explique:

\- o que foi corrigido;

\- estado final;

\- se o sistema está ou não apto para avançar ao próximo gate.

**## 2. Causas raiz encontradas**

Para cada bug:

\- sintoma;

\- causa;

\- correção.

**## 3. Arquivos alterados**

Tabela:

\`\`\`text

arquivo | motivo | tipo de alteração

\`\`\`

**## 4. Migrations**

Para cada migration:

\- app;

\- finalidade;

\- impacto em dados existentes;

\- rollback conceitual.

**## 5. Segurança**

Separar:

\`\`\`text

django-axes

account enumeration

IDOR

session hardening

\`\`\`

**## 6. IDOR Audit**

Listar endpoints/módulos auditados e resultado.

**## 7. Validações realizadas**

Listar somente o que realmente foi executado:

\- validações manuais/focadas das Fases 2 a 7;

\- testes existentes eventualmente executados de forma focada;

\- validação global executada na Fase 8.

Não há obrigação de criar novos testes automatizados nesta missão.

**## 8. Comandos executados**

Registrar:

\- testes;

\- lint;

\- builds;

\- Docker;

\- smoke.

**## 9. Resultados**

Informar totais reais:

\`\`\`text

backend tests: X passed / Y failed / Z skipped

frontend lint: PASS/FAIL

frontend build: PASS/FAIL

platform-admin lint: PASS/FAIL

platform-admin build: PASS/FAIL

docker build: PASS/FAIL

smoke: PASS/FAIL

\`\`\`

**\*\*Não inventar números.\*\***

**## 10. Pendências reais**

Se algo não puder ser concluído:

\- explique exatamente;

\- indique bloqueio;

\- não marque como feito.

**## 11. Veredito PRE-POS**

Usar apenas uma destas classificações:

\`\`\`text

✅ GO PARA O PRÓXIMO GATE

🟡 GO COM RESSALVAS

🔴 NO-GO

\`\`\`

Justificar tecnicamente.

**---**

**# 19. ORDEM DE EXECUÇÃO CONTROLADA**

As Fases 0 e 1 estão concluídas. Não repeti-las.

A partir de agora:

```text
Fase 2 — Modificadores: semântica de quantidade
→ validação mínima
→ atualizar checklist
→ PARAR e aguardar autorização

Fase 3 — Modificadores: soft-delete + constraints
→ validação mínima
→ atualizar checklist
→ PARAR e aguardar autorização

Fase 4 — Compras + Apresentações Produto ↔ Fornecedor
→ validação mínima
→ atualizar checklist
→ PARAR e aguardar autorização

Fase 5 — Account enumeration + django-axes
→ validação mínima
→ atualizar checklist
→ PARAR e aguardar autorização

Fase 6 — Auditoria IDOR
→ corrigir somente vulnerabilidades reais encontradas
→ validação manual/focada
→ atualizar checklist
→ PARAR e aguardar autorização

Fase 7 — SESSION_COOKIE_AGE + Release/version/build metadata
→ validação mínima
→ atualizar checklist
→ PARAR e aguardar autorização

Fase 8 — Revisão sistêmica + VALIDAÇÃO GLOBAL ÚNICA
→ suíte backend existente uma vez
→ lint/build uma vez
→ Docker/smoke uma vez
→ corrigir somente o necessário
→ PARAR

Fase 9 — Relatório final + veredito PRE-POS
```

**Regra:** nenhuma fase inicia automaticamente a próxima.

**Regra:** nenhuma fase 2–7 deve gastar tempo criando baterias extensas de testes automatizados.

**Regra:** a Fase 8 é o ponto central de validação automatizada global.

**---**

**# 20. PROIBIÇÃO FINAL**

\<out\_of\_scope>

Não implementar nesta tarefa:

\- Flutter;

\- CORE POS;

\- autenticação de POS/device;

\- pareamento Stone;

\- payment transaction Stone;

\- offline sync;

\- PrintJob claim/lease/ACK para POS;

\- API \`/pos/\`;

\- \`django-csp\`;

\- CSP Next.js.

Esses itens pertencem à próxima etapa **\*\*depois\*\*** do PRE-POS estar verde.

\</out\_of\_scope>

**---**

**# RESULTADO ESPERADO**

Ao final deste trabalho, o CORE PDV deve estar em um estado estável em que possamos dizer:

\> **\*\*"A base web/backend foi corrigida, endurecida e validada. Agora podemos começar a fundação do CORE POS sem carregar bugs conhecidos ou falhas básicas de segurança para o novo aplicativo."\*\***

**---**

**# CHECKLIST DE EXECUÇÃO**

\> **\*\*MODO ECONÔMICO ATIVO:\*\*** Fases 2–7 sem criação de baterias de testes automatizados e sem suíte global; Fase 8 concentra a validação global. Cada fase deve parar em checkpoint e aguardar autorização.

\- [x] Fase 0 — baseline, inventário técnico, validações iniciais e falhas preexistentes registrados.

\- [x] Fase 1 — \`/produtos\` e materialização centralizada de \`Stock\` corrigidos e validados.

\- [x] Fase 2 — semântica de quantidade dos modificadores corrigida e validada.

\- [x] Fase 3 — soft-delete e constraints de modificadores corrigidos e validados.

\- [x] Fase 4 — compras e apresentações centradas no Produto corrigidas e validadas.

\- [x] Fase 5 — enumeração de contas eliminada e \`django-axes\` integrado e validado.

\- [x] Fase 6 — auditoria IDOR concluída, vulnerabilidades reais corrigidas e validações focadas realizadas.

\- [x] Fase 7 — sessões e metadata de release endurecidas e validadas.

\- [x] Fase 8 — revisão sistêmica e validação final completa executadas.

\- [x] Fase 9 — relatório final e veredito PRE-POS entregues.

**## Baseline registrado**

\- Django check: PASS (\`1\` check explicitamente silenciado).

\- Migration consistency e \`makemigrations --check --dry-run\`: PASS.

\- Backend: \`240\` testes executados; \`9\` erros preexistentes, \`0\` falhas de assertion reportadas.

\- Frontend: build/TypeScript/66 rotas compilados; lint do container local bloqueado por dependência ausente.

\- Platform Admin: lint PASS; build/TypeScript/10 rotas PASS.

\- Docker Compose e Stack config: PASS; quatro serviços locais saudáveis.

\- Smoke equivalente: \`4/4\` URLs com HTTP \`200\`.

\- Dependency audit: FAIL, \`pypdf==5.9.0\` com \`37\` vulnerabilidades conhecidas.

\- IDOR baseline: vazamento cross-branch confirmado em audit logs e oráculos de existência identificados.

\- Escopo: nenhum código de POS, Flutter, Stone, \`/pos/\`, \`django-csp\` ou CSP Next foi iniciado.

**## Fase 1 validada**

\- Materialização centralizada em \`apps.inventory.materialization\`, usada por signals, inventário, estoque mínimo, vendas e comandas.

\- Ordem de locks explícita e determinística em operações de estoque: \`Company -> Branch -> Product -> FractionConfig -> Stock\`.

\- Signals de criação serializados por empresa com advisory lock transacional do PostgreSQL e materialização em lote.

\- Serializer de produtos resiliente a filial sem \`Stock\` e a legado fracionado com \`current\_content = NULL\`, sem inventar saldo positivo.

\- Data migration \`inventory.0019\_reconcile\_fractional\_stock\_content\` aplicada: \`1\` saldo legado nulo reconciliado de zero para zero; \`0\` inconsistências remanescentes no ambiente local.

\- Regressões: \`16/16\` cenários focados PASS, \`37/37\` cenários finais de inventário PASS, \`66/66\` consumidores de vendas/comandas PASS e \`33/33\` comandas revalidadas após o endurecimento final de locks.

\- Django check, consistência de migrations, compilação Python e \`git diff --check\`: PASS.

\- Revisão independente final: nenhum bloqueador alto ou médio remanescente para a Fase 1.

**## Fase 2 validada**

\- Causa raiz: grupos de distribuição exata aplicavam `min_selections`/`max_selections` à quantidade de opções distintas antes de validar a soma das unidades.

\- Regra de domínio separada em dois modos mutuamente exclusivos: grupos com componente substituído validam a soma exata; grupos comuns preservam `min_selections`/`max_selections` sobre opções distintas.

\- Payloads com a mesma opção repetida continuam rejeitados antes das regras quantitativas; obrigatoriedade e validação de quantidade positiva foram preservadas.

\- O `ModifierPicker` aplica a mesma separação usando `required_quantity`, mantendo mensagens específicas para total de unidades e para quantidade de opções.

\- Validação focada e transacional: uma opção com quantidade `5` aceita, divisão `3+2` aceita, totais `4` e `6` rejeitados, opção duplicada rejeitada e grupo comum com `min=2` continua exigindo duas opções distintas.

\- Venda direta validada por `_consolidate_items` e comanda validada por `add_order_item`, ambas com uma opção de quantidade `5`; dados temporários revertidos.

\- Rodada das `20` regressões existentes de modificadores foi interrompida pelo limite de `120s` após progresso sem falhas reportadas; não foi repetida conforme o modo econômico.

\- Django check, consistência de migrations e `git diff --check`: PASS; nenhuma migration criada.

\- Lint focado do frontend não iniciou porque `eslint`/`node_modules` não estão instalados no host nem no contêiner; build global e instalação de dependências não foram executados nesta fase.

**## Fase 3 validada**

\- Causa raiz: grupos, opções e vínculos usavam \`status=inactive\` como exclusão reversível, enquanto constraints incondicionais continuavam reservando nomes e vínculos.

\- Lifecycle único implementado com \`deleted\_at\`/\`deleted\_by\`; \`status\` permanece somente como estado derivado e protegido por constraints de consistência.

\- Exclusão de grupo faz soft-delete em cadeia de opções e vínculos; exclusão física pelos managers/modelos foi bloqueada.

\- Endpoints de ativar/desativar foram removidos; grupos, opções e vínculos agora usam \`DELETE\`, sem restauração pela API.

\- UI sem “Ver/Ocultar arquivados” ou ativar/inativar; exclusões são confirmadas e desvinculação no produto usa \`DELETE\`.

\- Managers e filtros operacionais ocultam excluídos de listagens, catálogo, vendas, comandas e novos vínculos, preservando snapshots históricos.

\- Migration \`products.0014\_modifier\_soft\_delete\` aplicada no PostgreSQL: \`5\` grupos, \`13\` opções e \`7\` vínculos legados convertidos após cascata; \`0\` inconsistências de lifecycle.

\- A migration desambigua opções ativas legadas com colisão case-insensitive usando o mesmo \`LOWER()\` do banco, sem apagar registros.

\- Constraints confirmadas no PostgreSQL: unicidade parcial CI de grupo por empresa, opção por grupo e vínculo produto/grupo, todas com \`WHERE deleted\_at IS NULL\`.

\- Validações focadas: \`20/20\` API/domínio/reorder/lifecycle PASS, \`1/1\` migration legada PASS e \`6/6\` modificadores inteligentes/venda/comanda PASS.

\- Frontend build/TypeScript: PASS, \`66/66\` rotas geradas.

\- Django check, consistência de migrations e \`git diff --check\`: PASS.

\- Revisão independente final: nenhum bloqueador alto ou médio remanescente para a Fase 3.

**## Fase 4 validada**

\- Causa raiz do input: `pending_stock_quantity` era copiado diretamente do DTO para o estado React e para o input de recebimento, preservando zeros decimais artificiais da representação da API.

\- `formatEditableDecimal` centraliza a normalização visual sem usar `Number`, arredondar ou remover casas significativas; `12.00000000` vira `12`, `12.50000000` vira `12.5` e `12.12500000` vira `12.125`.

\- O recebimento inicial, estoque mínimo, conteúdo fracionável e fatores de apresentação agora usam valores editáveis normalizados; o submit continua convertendo vírgula para ponto e preservando o contrato decimal do backend.

\- Causa raiz do domínio: `ProductPurchasePresentation` já pertencia ao produto e já era a autoridade preferencial nas compras, mas não possuía serializer, serviço, rota ou UX própria; o cadastro ainda nascia dentro de `ProductSupplierUnit` e duplicava código, descrição e fator.

\- `ProductPurchasePresentation` ganhou CRUD/status auditado e multi-tenant em `/api/v1/product-purchase-presentations/`, exposição separada no contrato do produto e identidade `company/product` imutável.

\- A tela de produto separa “Apresentações” de “Fornecedores”: apresentações são cadastradas no produto e cada fornecedor apenas vincula uma apresentação existente com seus atributos próprios, como barcode e vínculo padrão.

\- `ProductSupplierUnit` continua aceitando o contrato legado por compatibilidade concreta, mas novos vínculos da UI usam `purchase_presentation`; código, descrição e fator legados são espelhos sincronizados da apresentação canônica.

\- A inativação de uma apresentação inativa seus vínculos ativos; novas compras rejeitam apresentação canônica inativa e unidades legadas são normalizadas e persistidas antes do snapshot.

\- A duplicação de produto agora copia primeiro suas apresentações e remapeia os vínculos de fornecedores para apresentações pertencentes à cópia.

\- Snapshots de `PurchaseOrderItem`, `PurchaseReceiptItem` e movimentos de estoque foram preservados; nenhuma compra histórica foi reescrita e nenhuma migration foi necessária.

\- Validações transacionais: CRUD canônico, vínculo, rejeição cross-product, sincronização de espelhos, contrato embutido do produto, duplicação segura e API create/list/deactivate com cascata PASS; todos os dados temporários foram revertidos.

\- Regressões existentes: rodada focada com `5` testes resultou inicialmente em `4` PASS e `1` erro por uma unicidade excessiva introduzida nesta fase; a restrição foi removida para preservar múltiplos vínculos legítimos e o único teste afetado passou em nova execução (`1/1`).

\- Entrada direta, apresentação canônica entre fornecedores e recebimento parcial com motivo/idempotência passaram nas regressões focadas.

\- Frontend focado: helper decimal validado nos três valores obrigatórios e transpile sintático isolado de `6` arquivos alterados PASS; build/lint global não foi executado nesta fase.

\- Django check, consistência de migrations e `git diff --check`: PASS.

\- Nenhuma atividade da Fase 5 foi iniciada neste checkpoint.

**## Fase 5 validada**

\- Causa raiz dos logins: Backoffice e Platform Admin consultavam a conta e executavam `check_password()` antes de `authenticate()`, expondo estados distintos e impedindo que as falhas fossem observadas uniformemente pelo backend de autenticação.
\- Backoffice, Platform Admin e Django Admin agora passam pelo `AxesStandaloneBackend`; a identidade é normalizada sem diferenciar caixa e o bloqueio combina identidade + IP confiável, com limite de `5` falhas, cooldown/expiração de `15` minutos e reset após sucesso.
\- Cabeçalhos de proxy só participam da identificação quando `TRUST_PROXY_HEADERS=True`; nesse caso usa-se o último endereço de `X-Forwarded-For`, e a fronteira entre IP encaminhado e `REMOTE_ADDR` foi validada diretamente.
\- Falhas de credencial, conta inativa, login desabilitado, tenant/filial sem acesso operacional e ausência de acesso à plataforma usam mensagem externa genérica; a quinta falha retorna `429` também nos endpoints DRF, sem depender apenas da resposta do middleware.
\- O cadastro público não revela se o e-mail já existe: e-mail novo e existente retornam `201` com o mesmo contrato opaco, o caso existente executa hash de senha equivalente e um advisory lock transacional impede corrida de unicidade; o provisionamento administrativo autenticado preserva o conflito explícito.
\- A interface pública de cadastro passou a apresentar confirmação genérica e referência opaca; recuperação de senha e convite anônimo não existem, e os resets disponíveis permanecem autenticados/autorizados.
\- A política operacional do Axes foi documentada e propagada por `backend/.env.example`, `.env.production.example`, Docker Compose e Docker Stack; as migrations `axes.0001`–`0010` foram aplicadas e `migrate --check` passou em PostgreSQL efêmero, removido ao final.
\- Regressões existentes focadas: login, separação de autorização Platform/tenant e CSRF/idempotência do cadastro público `3/3` PASS.
\- Validação direta: equivalência de enumeração `6/6` PASS; lockout nos três logins `3/3` PASS; credencial correta permaneceu bloqueada durante o cooldown, enquanto outra identidade no mesmo IP continuou disponível; cadastro novo/existente e replay idempotente PASS.
\- Django check, compilação Python, consistência de migrations, `pip check`, Docker Compose/Stack config, transpile sintático isolado do cadastro e `git diff --check`: PASS; suíte global, builds globais e Docker build não foram executados nesta fase.
\- Nenhuma atividade da Fase 6 foi iniciada neste checkpoint.

**## Fase 6 validada — IDOR AUDIT**

\- Superfície auditada por inspeção de ViewSets, APIViews, actions, serializers, services e permissions: companies/branches/memberships/users/customers, suppliers/apresentações, products/categories/modificadores, inventory/stock/ajustes/transferências/perdas/contagens, purchases/itens/contas a pagar/anexos, sales/itens/pagamentos/caixas, commands/tables, production/printers/jobs/tickets, reports, SaaS/admin, Support Sessions e audit logs.
\- Vetores revisados: detail/mutation, IDs aninhados, query params, `X-Branch-ID`, ações pai/filho, suporte impersonado e não impersonado, uploads/downloads e distinções entre recurso externo e inexistente; anexos de compras, fotos de perdas e foto de perfil permanecem vinculados ao queryset do pai ou ao próprio usuário.
\- Vulnerabilidade 1 confirmada: `scope=all` de audit logs incluía eventos sem `branch` de toda a empresa para usuário autorizado em somente uma filial, permitindo que um evento referente a outra filial fosse inferido pelo `object_id`/payload.
\- Correção de auditoria: logs com filial continuam limitados às filiais autorizadas; logs company-wide sem filial só são expostos quando o usuário possui `audit_logs.view` em todas as filiais da empresa; eventos cujo objeto é a própria `Branch` agora persistem a filial explicitamente. Superuser e suporte não impersonado preservam seus escopos administrativos existentes.
\- Vulnerabilidade 2 confirmada: relações resolvidas por querysets globais devolviam erro contextual para ID existente de outro tenant e `does_not_exist` para ID inexistente, formando oráculo em payloads de produtos, promoções, vendas, destinos de produção, modificadores e domínio de fornecedores/apresentações.
\- Correção dos payloads: querysets relacionais foram limitados pela empresa/filial autorizada antes da resolução do ID; cálculo/finalização de venda resolve produtos dentro da empresa; autorizadores de desconto são resolvidos somente pelo serviço branch-scoped. IDs externos e inexistentes agora seguem o mesmo contrato sem revelar existência.
\- Details e mutations cross-tenant já estavam protegidos pelos querysets funcionais e mantiveram `404`; query params, headers, ações aninhadas, transferências e anexos não apresentaram bypass após a revisão. Platform Admin global continua separado por permissões de plataforma; Support Session continua presa ao tenant e ao modo de leitura/escrita.
\- Validação manual transacional A/A1/A2/B: log A1 visível; log A2 e evento branchless ocultos para acesso apenas A1; evento branchless visível após concessão em todas as filiais; inferência de `Branch` persistida; detail externo/inexistente ambos `404`; IDs externos/inexistentes de promoção e fornecedor com o mesmo código/mensagem de campo. Dados temporários revertidos e script removido.
\- Regressões focadas limpas: `17/17` PASS para vendas cross-tenant/idempotência, produtos cross-tenant, relação de fornecedor e redação contextual de auditoria; após o endurecimento final, `7/7` casos exatos de produto, preço, reorder/modificadores, venda e fornecedor cross-tenant PASS.
\- Uma rodada ampliada de `31` testes foi interrompida em `120s` após `27` cenários sem falha reportada e não foi repetida integralmente conforme o modo econômico. Uma rodada anterior de `23` testes teve `22` PASS e `1` erro preexistente de expectativa em `test_presentation_preset_api_is_scoped_and_can_be_inactivated`: o teste tenta ler `count` ao consultar empresa não autorizada, enquanto a permission class encerra corretamente com `403` antes da paginação.
\- Django check e `git diff --check`: PASS; nenhuma migration, alteração frontend, suíte global ou build global foi executado nesta fase.
\- Revalidação após a interrupção: correções de causa raiz revisadas sem alterações adicionais; validação transacional `4/4` PASS para escopo de audit logs, inferência de filial e oráculos em detail/payload; regressões cross-tenant exatas `7/7` PASS. O script temporário foi removido e o frontend permaneceu sem alteração por não haver contrato afetado.
\- Nenhuma atividade da Fase 8 foi iniciada neste checkpoint.

**## Fase 7 validada**

\- Causa raiz das sessões: `SESSION_COOKIE_AGE` e a renovação por atividade não estavam configurados, mantendo o default de 14 dias do Django sem política operacional explícita.

\- A sessão principal agora expira após `28800` segundos de inatividade e é renovada a cada request autenticado com `SESSION_SAVE_EVERY_REQUEST=True`; `Secure`, `HttpOnly` e `SameSite=Lax` foram preservados, e valores não positivos são rejeitados na inicialização.

\- A política foi documentada e propagada por `backend/.env.example`, `.env.production.example`, Docker Compose e Docker Stack; Backoffice, Django Admin e Platform Admin compartilham o limite, enquanto Support Sessions mantêm o `expires_at` temporário próprio e mais restritivo.

\- Auditoria dos fluxos existentes: logout continua chamando `django.contrib.auth.logout`, mudança/reset de senha altera o hash que invalida sessões anteriores, e `CanLoginMiddleware` encerra a sessão de usuário inativo ou sem `can_login`.

\- `VERSION` na raiz passou a ser a fonte semântica única (`0.9.0`); CI/GHCR validam o formato e injetam versão, SHA completo, data UTC de build e ambiente nas três imagens a partir do mesmo commit, sem editar Dockerfiles ou frontends por release.

\- O backend centraliza a metadata em `apps.base.release`, registra versão + ambiente + SHA no startup e a expõe sem secrets em `/api/v1/` e `/health/`; o contrato preexistente `version: v1` do API root foi preservado.

\- Backoffice e Platform Admin exibem discretamente versão, SHA curto, ambiente e data de build nos respectivos menus laterais, usando os valores públicos incorporados durante o build.

\- Validações focadas: `5/5` testes novos de política deslizante, API, health e startup log PASS; login, logout e rejeição de Support Session expirada `3/3` PASS em PostgreSQL efêmero, removido ao final.

\- Django check, compilação Python, consistência de migrations sem alterações, validação de `SESSION_COOKIE_AGE` inválido, Docker Compose/Stack config, versão semântica e `git diff --check`: PASS.

\- Transpile sintático isolado dos shells e helpers de release do Backoffice e Platform Admin: PASS; suíte global, builds globais e Docker build não foram executados nesta fase.

\- Nenhuma atividade da Fase 8 foi iniciada neste checkpoint.

**## Fase 8 validada — revisão sistêmica e validação global**

\- Revisão sistêmica de opcionais/Decimal, soft-delete com constraints, inputs decimais, querysets relacionais, `get(pk=...)`, contexto company/branch, enumeração, `check_password()` e contratos frontend/backend não encontrou nova vulnerabilidade ou divergência de produção além das correções já registradas.
\- A auditoria de dependências identificou `pypdf==5.9.0` vulnerável; o pin foi atualizado para `pypdf==6.16.2`. O teste focal de exportação PDF passou `5/5`, a imagem backend foi reconstruída com a versão nova e `pip-audit -r requirements.txt` retornou `No known vulnerabilities found`.
\- `django-axes==8.3.1` exige request no backend de autenticação. O backend local sintetiza contexto mínimo para chamadas programáticas sem request, preservando a aplicação do Axes; autenticações HTTP continuam recebendo a request real.
\- Regressões foram alinhadas ao contrato já protegido: pagamento de parcela ocorre após o pedido ser realizado, e consulta de empresa sem acesso retorna `403` em vez de expor paginação vazia. Os cinco cenários focados afetados passaram.
\- Backend: Django check PASS (1 check silenciado), `migrate --check` PASS, `makemigrations --check --dry-run` sem alterações e suíte existente `248/248` PASS em PostgreSQL real.
\- Frontend: lint PASS sem erros (`58` warnings preexistentes); build/TypeScript PASS com `66` rotas.
\- Platform Admin: lint PASS; build oficial do estágio `builder`/TypeScript PASS com `10` rotas. A tentativa de build por bind mount do Compose não foi considerada veredito porque o mount ocultava `node_modules` da imagem.
\- Docker: `docker compose config --quiet` PASS e build oficial do Compose PASS para backend, frontend e Platform Admin. Os quatro healthchecks ficaram saudáveis.
\- Smoke local PASS: `/health/`, `/`, `/login` e Platform Admin `/login` retornaram HTTP `200`.
\- `git diff --check` PASS; nenhuma migration foi criada, nenhum teste foi removido/desabilitado e nenhum código de POS, Flutter, Stone, `/pos/`, `django-csp` ou CSP Next.js foi iniciado.
\- Nenhuma atividade da Fase 9 foi iniciada neste checkpoint.

**## Fase 9 concluída — relatório final e veredito PRE-POS**

\- Causas raiz, correções e validações foram consolidadas dos checkpoints das Fases 1 a 8; não houve alteração de código nesta fase e, portanto, nenhuma nova regressão ou causa raiz a corrigir.
\- Migrations: \`products.0014_modifier_soft_delete\` implementou soft-delete e unicidade parcial de modificadores; \`inventory.0019_reconcile_fractional_stock_content\` reconciliou conteúdo fracionado legado sem inventar saldo. Ambas foram aplicadas e a consistência de migrations passou na Fase 8.
\- Segurança: Axes cobre Backoffice, Platform Admin e Django Admin; enumeração anônima foi eliminada; escopo de audit logs e relações de payload foi endurecido contra IDOR; sessão passou a ter política configurável de 8 horas.
\- Validações efetivamente realizadas: regressões focadas das Fases 1 a 7, exportação PDF \`5/5\`, cenários afetados por Axes/compra/IDOR \`5/5\`, backend \`248/248\`, frontend lint/build, Platform Admin lint/build, auditoria de dependências sem vulnerabilidades conhecidas, Docker Compose build/health e smoke local \`4/4\`.
\- Resultado: não há pendência técnica bloqueante identificada para o escopo PRE-POS. Os avisos de lint do frontend (\`58\`) são preexistentes, não impedem build e não correspondem a erro de tipo.
\- Veredito PRE-POS: ✅ GO PARA O PRÓXIMO GATE. A base web/backend está corrigida, endurecida e validada; nenhum código de POS, Flutter, Stone, \`/pos/\`, \`django-csp\` ou CSP Next.js foi iniciado.
