# CORE PDV — RELATÓRIOS: CORREÇÕES PÓS-TESTE DAS FASES 1 E 2
**Data:** 02/09/2026  
**Status:** Fase 1 implementada + Fase 2 implementada, ambas em validação manual.  
**Documento canônico desta rodada:** este arquivo substitui as instruções anteriores V2/V3/V4 para as correções pós-teste.

---

# MISSÃO DO OPENCODE

Leia este documento integralmente.

- **FASE 1 já foi implementada.**
- **FASE 2 já foi implementada.**
- NÃO reimplementar Fase 1.
- NÃO reimplementar Fase 2.
- Corrigir e polir SOMENTE os pontos encontrados durante os testes.
- Depois da validação manual, seguir para a **FASE 3 — Compras, Fornecedores e Contas a pagar**.
- Toda melhoria desta rodada que represente um padrão transversal de relatórios — filtros colapsáveis, KPIs, loading, tabs/layout, links para entidades, modais de motivo, filtros históricos e exportação PDF/XLSX — deve ser implementada como infraestrutura/componente reutilizável sempre que tecnicamente adequado. As Fases 3, 4, 5 e 6 deverão reutilizar esses padrões, não recriá-los individualmente
---

# REGRA ABSOLUTA — NÃO EXECUTAR TESTES AUTOMATIZADOS

Para economizar créditos, **NÃO executar**:

- testes Django;
- suíte backend;
- suíte frontend;
- Jest/Vitest/Playwright;
- `npm test`;
- `npm run build`;
- CI/GitHub Actions;
- `npm audit`;
- `pip-audit`;
- Docker build;
- scans extensos;
- auditoria geral do projeto.

Pode fazer apenas leitura/revisão do código necessário, implementação e verificações estáticas pontuais.

Ao finalizar, NÃO avançar para a Fase 3 automaticamente. Entregar os testes manuais para o usuário.

---

# 1. PADRÃO GLOBAL DOS RELATÓRIOS

Todos os relatórios densos devem seguir obrigatoriamente:

```text
FILTROS

KPIs

MENUS / ABAS

CONTEÚDO
```

Os KPIs ficam **acima das abas**.

---

# 2. FILTROS — MOSTRAR PRIMEIRO APENAS O ESSENCIAL

Relatórios com muitos filtros não devem abrir mostrando uma grade enorme.

## Estado inicial

Mostrar diretamente:

```text
Período
Atalhos de período
```

e, quando realmente essencial, no máximo 1 ou 2 filtros principais adicionais.

Exemplo:

```text
Hoje | 7 dias | 30 dias | Personalizado

[ + Filtros ]
```

## `+ Filtros`

Ao clicar:

- revelar filtros avançados;
- preservar valores;
- permitir fechar sem perder seleção;
- mostrar contador quando houver filtros avançados ativos.

Exemplo:

```text
+ Filtros (3)
```

Quando útil, mostrar chips:

```text
Atendente: João ×
Produto: Coca ×
Status: Finalizada ×
```

e ação:

```text
Limpar filtros
```

## Mobile

Filtros avançados podem abrir em drawer, bottom sheet ou modal responsivo.

---

# 3. LOADING DOS RELATÓRIOS

Alguns relatórios demoram para carregar. O loading deve ser bonito e coerente com o CORE.

Usar:

- skeleton de KPIs;
- skeleton de tabela;
- skeleton de gráfico;
- shimmer/pulse discreto;
- spinner pequeno quando apropriado;
- transição suave;
- estrutura fixa para evitar layout pulando.

Ao trocar somente filtros, pode manter os dados anteriores visíveis e usar overlay/loading discreto.

Não usar porcentagem falsa ou progresso inventado.

---

# 4. KPIs — MELHORAR VISUAL EM TODAS AS PÁGINAS

Os KPIs das Fases 1 e 2 estão funcionais, mas visualmente neutros/mortos.

Criar componente reutilizável, por exemplo:

```text
ReportKpiCard
```

## Estrutura

```text
[ícone] FATURAMENTO

R$ 24.582,50

↑ 8,4%
```

ou:

```text
[ícone] VENDAS

142

↓ 3,2%
```

Usar Surface, Border, Primary, Muted e cores semânticas do CORE, preservando light/dark.

Pode ter ícone discreto, acento visual, número destacado, contexto secundário e hover sutil quando houver ação.

Não usar gradientes exagerados, sombra pesada, cards gigantes ou cores aleatórias.

## Semântica

**Danger:** perdas, estoque negativo, divergência crítica, vencidos.  
**Warning:** divergência pendente, estoque zerado, abaixo do mínimo, recebimento parcial.  
**Success:** resolução/conclusão positiva quando realmente aplicável.  
**Primary/Info/Neutral:** faturamento, vendas, transferências, inventários e métricas neutras.

---

# 5. `/relatorios/visao-geral`

## Ordem

```text
Filtros
KPIs
Composição do total recebido
Comparativo contra período anterior
Recebimentos por forma
Demais gráficos/análises
```

Mover `Composição do total recebido` para cima, antes do comparativo e dos recebimentos por forma.

## Linha `Vendas` no comparativo

No teste:

```text
Vendas
Atual: 4
Anterior: 8
Variação: -4.00
Variação %: -50%
```

`Vendas` é quantidade, não dinheiro.

Correto:

```text
Atual: 4
Anterior: 8
Variação: -4
Variação %: -50%
```

**NÃO colocar R$. NÃO colocar ,00 em quantidade inteira.**

Cada métrica deve conhecer o tipo:

```text
money
number
quantity
percent
percentage_points
```

Money usa `R$` e duas casas. Quantity usa número. Percent usa `%`.

---

# 6. PERÍODO ANTERIOR

Não adicionar novo bloco explicativo na UI.

Regra:

> período anterior = intervalo imediatamente anterior com a mesma duração.

Exemplos:

```text
Hoje → ontem
7 dias → 7 dias imediatamente anteriores
30 dias → 30 dias imediatamente anteriores
01/09 a 02/09 → 30/08 a 31/08
```

---

# 7. FILTROS HISTÓRICOS

Foi testado:

```text
Usuário participou de vendas
→ usuário soft-deleted
→ métricas históricas permaneceram
→ usuário sumiu do filtro
```

Métricas permanecerem = correto. Sumir do filtro histórico = incorreto.

Regra:

```text
Opções do filtro
=
entidades atuais relevantes
+
entidades históricas presentes nos dados do período
```

Não carregar todos os arquivados da história.

Aplicar a:

- atendentes;
- operadores;
- produtos;
- categorias;
- formas de pagamento;
- clientes;
- promoções;
- modificadores;
- fornecedores quando houver relatório histórico.

Mostrar badges quando necessário:

```text
Rayara (Arquivada)
Coca (Arquivado)
Visa Crédito (Inativo)
```

Usar snapshots históricos quando disponíveis, por exemplo:

```text
product_name
category_id_snapshot
category_name_snapshot
payment_method_name
payment_method_code
modifier_snapshot
```

Não reconstruir passado somente pelo cadastro atual.

---

# 8. `/relatorios/vendas` — ESTRUTURA

Sugestão de abas:

```text
Resumo
Vendas
Itens
Pagamentos
Vendas por hora
```

Evitar redundância com o relatório dedicado de Cancelamentos.

---

# 9. VENDAS POR HORA

Adicionar aba:

```text
Vendas por hora
```

Reutilizar agregações horárias/heatmap existentes quando possível.

Preferência dentro da aba:

```text
[ Linha | Mapa de calor ]
```

## Linha

Eixo X: horas do dia.

Pode apresentar:

- faturamento;
- quantidade de vendas;
- total recebido;
- ticket médio, se útil.

## Heatmap

```text
dia da semana × hora
```

Permitir visualizar intensidade por faturamento ou quantidade.

Tooltip:

```text
Sexta-feira · 23h
18 vendas
R$ 4.250,00
Ticket médio R$ 236,11
```

Mobile deve manter legibilidade.

---

# 10. VENDAS — RECEBIMENTOS POR FORMA

No trecho `Total dos recebimentos por forma`, usar em desktop dois cards lado a lado:

```text
┌──────────────────────┐ ┌────────────────────────────┐
│ TOTAL DOS PAGAMENTOS │ │ GRÁFICO POR FORMA         │
│ R$ ...               │ │ PIX / dinheiro / cartão   │
│ contexto/delta       │ │ distribuição completa     │
└──────────────────────┘ └────────────────────────────┘
```

No mobile, empilhar.

O gráfico deve mostrar forma, valor e percentual. Pode ser donut ou barras horizontais.

---

# 11. VENDAS — ABA `ITENS`

Tabela de itens vendidos:

```text
Venda
Data/hora
Produto
Categoria histórica
Quantidade
Preço base
Modificadores
Promoção
Desconto
Subtotal
Total
```

Com permissão de custo:

```text
Custo unitário
Custo total
Margem
Margem %
```

Preservar os cálculos atuais corretos.

---

# 12. VENDAS — ABA `PAGAMENTOS`

Referência como:

```text
V00047
```

deve ser clicável e abrir o detalhe real da venda.

Respeitar permissão de visualizar venda. Sem permissão, mostrar texto simples.

---

# 13. O QUE SIGNIFICA `STATUS` NA TABELA DE PAGAMENTOS

A coluna atual está ambígua.

O `Payment` histórico de venda não deve ganhar status fictício.

## Se o valor é o status da venda

Renomear:

```text
Status da venda
```

Exemplos:

```text
Finalizada
Cancelada
```

## Se existe situação real do pagamento derivada da origem/reversão

Usar:

```text
Situação do pagamento
```

Exemplos:

```text
Aplicado
Estornado
```

somente quando isso puder ser derivado de forma confiável.

## Se não há status próprio útil

Remover a coluna.

Não chamar status da venda de status do pagamento.

---

# 14. `/relatorios/recebimentos`

Na tabela `Eventos detalhados`:

## Venda clicável

```text
V00047
```

deve abrir o detalhe da venda, respeitando permissão.

## Motivo de estorno

Se houver motivo:

```text
Ver motivo
```

abre modal responsivo com o texto completo.

Se não houver motivo, não mostrar botão vazio.

Isso é especialmente importante no mobile.

---

# 15. `/relatorios/produtos` — MODIFICADORES

Na tabela `Desempenho por modificador`, não mostrar somente:

```text
melancia
```

O mesmo nome pode existir em vários grupos.

Exemplos:

```text
REDBULL — melancia
REDBULL — tradicional
NARGUILÉ — melancia
DRINK — melancia
```

Formato obrigatório:

```text
GRUPO — MODIFICADOR
```

Usar snapshot histórico `group_name` + `option_name` quando disponível.

---

# 16. PRODUTOS — REMOVER ABAS REDUNDANTES

Não manter `Desempenho` e `Margens/Custos` se apresentam a mesma informação.

Preferir:

```text
Desempenho
Categorias
Modificadores
Promoções
```

Na aba `Desempenho`, mostrar condicionalmente:

```text
Quantidade
Faturamento
Descontos
Custo
Margem R$
Margem %
```

Custo/margem apenas com permissão.

---

# 17. `/relatorios/cancelamentos`

Referência de venda:

```text
V00047
```

deve ser clicável para o detalhe, respeitando permissão.

---

# 18. MOVIMENTAÇÕES DE ESTOQUE — ORIGEM

Quando origem for venda, não mostrar apenas:

```text
Venda
```

Mostrar:

```text
Venda V00047
```

com link ao detalhe.

Aplicar o mesmo padrão quando houver páginas reais:

```text
Compra C00012
Inventário I00004
Transferência T00009
```

Sempre respeitando permissão.

---

# 19. `/estoque` — RESTAURAR PRODUTO ARQUIVADO

Produto soft-deleted com saldo residual hoje possui `Baixar saldo remanescente`.

Adicionar ao lado:

```text
Restaurar produto
```

## Restaurar

- mesmo Product ID;
- preservar vendas;
- preservar compras;
- preservar estoque;
- preservar auditoria;
- preservar histórico;
- validar nome;
- código interno;
- SKU;
- código de barras;
- conflitos atuais.

Se houver conflito, bloquear com mensagem clara.

Restaurar NÃO zera saldo.

UI:

```text
[ Restaurar produto ] [ Baixar saldo remanescente ]
```

Ações distintas e auditadas.

---

# 20. SENHA GLOBAL CORE — RECUPERAÇÃO

Regra:

```text
1 identidade CORE = 1 e-mail global = 1 senha global
```

Não basta remover o reset direto do administrador. É necessário resolver esquecimento de senha.

---

# 21. IMPLEMENTAR `ESQUECI MINHA SENHA`

Na tela global de login:

```text
Esqueci minha senha
```

Fluxo:

1. informar e-mail;
2. resposta neutra;
3. se existir identidade válida, enviar link/token;
4. titular define nova senha global;
5. token é invalidado;
6. nova senha vale para todas as empresas.

Segurança:

- token criptograficamente seguro;
- uso único;
- expiração;
- rate limit;
- não revelar se e-mail existe;
- auditoria;
- política de senha;
- token inválido/reutilizado deve falhar;
- nunca colocar senha em URL/log.

Mensagem neutra:

```text
Se existir uma conta vinculada a este e-mail, enviaremos as instruções para redefinição.
```

---

# 22. ADMIN NÃO DEVE DEFINIR SENHA GLOBAL DE OUTRO USUÁRIO

Administrador da Empresa B não pode digitar uma senha que altere silenciosamente o acesso da mesma identidade na Empresa A.

Substituir reset direto por:

```text
Enviar redefinição de senha
```

O titular recebe o fluxo no e-mail global e escolhe sua nova senha.

Não alterar:

- membership;
- perfil;
- filial;
- comissão;
- permissões.

Usuário autenticado continua podendo alterar a própria senha global em `Minha conta`.

---

# 23. EXPORTAÇÃO — UX

Preferir:

```text
[ Exportar ▾ ]
```

Menu:

```text
Excel (.xlsx)
PDF
CSV
```

Durante geração:

```text
Preparando relatório...
```

- impedir clique duplicado;
- loading no botão;
- erro encerra loading;
- preservar filtros.

---

# 24. PDF — TODOS OS RELATÓRIOS

PDF deve representar o relatório, não apenas despejar uma tabela.

Deve poder conter as mesmas informações relevantes da página:

- título;
- empresa;
- filial;
- período;
- filtros;
- KPIs;
- resumos;
- composições;
- gráficos;
- tabelas;
- totais;
- observações relevantes.

Não precisa copiar pixel a pixel o HTML.

---

# 25. GRÁFICOS NO PDF

Se a página tiver gráfico relevante, o PDF deve poder incluir o mesmo gráfico ou representação equivalente.

Exemplos:

- Vendas por hora;
- Recebimentos por forma;
- Comparativo;
- Evolução;
- Rankings;
- Distribuições.

Evoluir o exportador para aceitar conceitualmente:

```text
metadata
kpis
sections
charts
tables
summary
```

e não apenas `headers/rows/summary`.

---

# 26. CORRIGIR O EXPORTADOR COMPARTILHADO

Foi reproduzido erro de PDF no caminho compartilhado de exportação de Vendas e Consumações.

O problema passa por serialização de `dict/list` com `json.dumps(...)` quando há tipos aninhados não serializáveis diretamente.

Corrigir UMA VEZ no exportador compartilhado, não com hacks separados por report view.

Normalizar recursivamente:

```text
None
str
int
float
bool
Decimal
date
datetime
UUID
dict
list
tuple
```

e demais tipos conhecidos usados nos relatórios.

## PDF/CSV

Produzir texto seguro/legível para conteúdos complexos.

## XLSX

Preservar tipo real quando possível:

- Decimal → número;
- date → data;
- datetime → datetime;
- percentual → número percentual.

---

# 27. PDF COM TABELAS GRANDES

Suportar:

- portrait/landscape;
- muitas colunas;
- textos longos;
- wrap;
- largura por tipo de coluna;
- repetição de cabeçalho;
- paginação.

Não cortar informação silenciosamente.

Não deixar erro de layout virar 500 sem tratamento.

---

# 28. CABEÇALHO E RODAPÉ PDF

Cabeçalho:

```text
CORE PDV
Nome do relatório
Empresa
Filial
Período
Filtros relevantes
Gerado em
```

Rodapé:

```text
CORE PDV
Página X
```

---

# 29. EXCEL (.XLSX)

Excel deve ser útil para análise.

## Simples

```text
Metadados
KPIs/Resumo
Tabela
```

## Complexo

Usar sheets quando fizer sentido:

```text
Resumo
Vendas
Itens
Pagamentos
Vendas por hora
```

ou, no estoque:

```text
Resumo
Transferências
Inventários
Perdas
Divergências
```

Preservar tipos:

- moeda = número com formatação;
- datas = datas;
- percentuais = percentuais;
- quantidade = número.

Visual:

- cabeçalho CORE discreto;
- freeze pane;
- autofilter;
- largura adequada;
- wrap.

---

# 30. EXPORTAÇÃO RESPEITA RBAC

Exportação nunca é bypass de permissão.

Sem custo na tela:

```text
sem custo no PDF
sem custo no Excel
sem custo no CSV
```

Aplicar a todas as informações protegidas.

---

# 31. EXPORTAÇÃO RESPEITA FILTROS

Arquivo deve refletir exatamente:

- empresa;
- filial;
- período;
- filtros;
- aba/escopo;
- permissões.

---

# 32. PADRÃO DE LINKS INTERNOS

Quando uma tabela possui referência real:

```text
Venda V00047
Compra C00010
Transferência T00004
Inventário I00002
```

usar link interno quando rota existir e houver permissão.

Visual discreto, não botão gigante.

---

# 33. MODAIS PARA MOTIVOS/TEXTOS LONGOS

Motivos de:

- estorno;
- cancelamento;
- justificativa;
- observação crítica;

podem usar `Ver motivo` + modal responsivo.

Se não houver texto, não mostrar ação vazia.

---

# 34. FASES SEGUINTES — NÃO EXECUTAR AGORA

Depois da validação manual:

## FASE 3
- Compras
- Fornecedores
- Contas a pagar

## FASE 4
- Mesas e comandas
- Cancelamentos de itens
- Pagamentos parciais/estornos
- Transferências/merge/split

## FASE 5
- Promoções
- Modificadores
- Clientes

## FASE 6
- Central de Relatórios
- Exportação final
- Padronização geral

## FASE 7
Somente preparação futura:
- Tickets
- Produção
- POS
- Stone/PagBank

Não avançar automaticamente.

---

# 35. ORDEM DE IMPLEMENTAÇÃO DESTA RODADA

## BLOCO A — Infra comum
1. filtros principais + `+ Filtros`;
2. loading;
3. KPI reutilizável;
4. layout `Filtros → KPIs → Abas → Conteúdo`.

## BLOCO B — Visão Geral
5. composição subir;
6. `Vendas` formatado como quantidade;
7. filtros históricos.

## BLOCO C — Vendas
8. Vendas por hora;
9. linha/heatmap;
10. total + gráfico de recebimentos;
11. links de venda;
12. Status sem ambiguidade.

## BLOCO D — Recebimentos / Cancelamentos / Estoque
13. links de venda;
14. modal de motivo;
15. links de origem;
16. restaurar produto em `/estoque`.

## BLOCO E — Produtos
17. `Grupo — Modificador`;
18. remover redundância Desempenho x Margens/Custos.

## BLOCO F — Senha global
19. Esqueci minha senha;
20. admin envia redefinição;
21. Minha conta permanece.

## BLOCO G — Exportações
22. corrigir serialização compartilhada;
23. melhorar Exportar;
24. PDF com KPIs/gráficos/tabelas;
25. Excel estruturado;
26. RBAC e filtros.

Parar ao final.

---

# 36. TESTES MANUAIS A ENTREGAR AO USUÁRIO

O OpenCode NÃO executa.

## Layout
- relatório com muitos filtros → período + `+ Filtros`;
- KPIs acima das abas;
- conteúdo abaixo.

## Loading
- trocar período → skeleton/overlay elegante.

## Visão Geral
- Atual 4 / Anterior 8 → Variação `-4`, não `-4,00` e não R$;
- composição acima do comparativo.

## Histórico
- vender com usuário/produto → arquivar → consultar período → opção histórica continua no filtro.

## Vendas
- Vendas por hora;
- V00047 clicável em Pagamentos.

## Recebimentos
- V00047 clicável;
- estorno com motivo → modal.

## Produtos
- mesmo `melancia` em grupos diferentes → `GRUPO — melancia`.

## Cancelamentos
- V00047 abre detalhe.

## Movimentações
- origem venda → `Venda V00047` clicável.

## Estoque
- produto arquivado com saldo → Restaurar → mesmo ID/histórico/saldo.

## Senha
- Esqueci minha senha → fluxo neutro e global;
- admin não digita nova senha de outro usuário.

## Exportação
Testar manualmente:
- Visão Geral PDF;
- Vendas PDF;
- Consumações PDF;
- Produtos PDF;
- Estoque PDF;
- Excel de relatório complexo.

Conferir KPIs, gráficos, tabela, período, filtros e permissões.

---

# 37. CRITÉRIO DE CONCLUSÃO

Responder:

```text
CORREÇÕES PÓS-TESTE F1/F2 — CONCLUÍDAS

1. O que foi implementado
2. Arquivos alterados
3. Endpoints alterados
4. Migrations, se houver
5. Decisões arquiteturais
6. Pendências reais
7. Testes MANUAIS que devo executar
```

Não iniciar Fase 3.

---

# REFORÇO FINAL — NÃO EXECUTAR TESTES AUTOMATIZADOS

NÃO executar suíte backend/frontend, Django tests, Jest, Vitest, Playwright, build completo, CI, GitHub Actions, audits, Docker builds ou scans extensos.

Implementar, revisar estaticamente e entregar para validação manual.
