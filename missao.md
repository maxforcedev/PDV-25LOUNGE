# CORE PDV — PLANO CANÔNICO DE RELATÓRIOS POR FASES — V5
**Data:** 02/09/2026  
**Objetivo:** concluir funcionalmente os relatórios necessários antes do POS, preservando padrões reutilizáveis e deixando a reformulação visual completa para uma rodada final.

---

# 0. STATUS ATUAL

## FASE 1 — IMPLEMENTADA ✅

Relatórios-base já implementados, incluindo:

- Visão geral;
- Vendas;
- Recebimentos;
- Cancelamentos/estornos;
- Descontos/autorizações;
- Produtos;
- Atendentes;
- Operadores;
- Consumação;
- Resultado estimado;
- Comissões;
- Caixa;
- Sangrias;
- Preços por filial;
- Movimentações de estoque.

Não reimplementar.

---

## FASE 2 — IMPLEMENTADA ✅

Relatórios avançados de estoque/inventário já implementados, incluindo:

- Posição de estoque;
- Inventários realizados;
- Transferências;
- recebimentos;
- mercadoria em trânsito;
- divergências;
- perdas;
- impactos;
- drill-down operacional.

Não reimplementar.

---

## FASE 3 — IMPLEMENTADA ✅

Já implementados:

- Compras;
- Fornecedores;
- Contas a pagar.

### Estado atual

A Fase 3 está em validação manual e correções pontuais.

Não reimplementar.

Correções funcionais encontradas durante a validação devem ser tratadas como ajustes da própria Fase 3, sem reabrir o escopo inteiro.

---

## PRÓXIMA FASE

```text
FASE 4 — MESAS E COMANDAS
```

Somente iniciar após o usuário concluir a validação manual/correções pendentes da Fase 3.

---

# 1. REGRA DE EXECUÇÃO

## NÃO EXECUTAR TESTES AUTOMATIZADOS

Para economizar créditos, o OpenCode NÃO deve executar:

- suíte completa backend;
- Django tests;
- testes frontend;
- Jest;
- Vitest;
- Playwright;
- `npm test`;
- `npm run build`;
- CI;
- GitHub Actions;
- `npm audit`;
- `pip-audit`;
- Docker build;
- scans extensos;
- auditoria geral do projeto.

Pode realizar somente:

- leitura dos módulos necessários;
- implementação;
- verificações estáticas pontuais;
- `py_compile`, TypeScript check pontual ou equivalente quando realmente necessário.

Ao finalizar uma fase:

```text
1. O que foi implementado
2. Arquivos alterados
3. Endpoints criados/alterados
4. Migrations, se houver
5. Permissões utilizadas/criadas
6. Decisões arquiteturais
7. Pendências reais
8. Testes MANUAIS que o usuário deve executar
```

Nunca avançar automaticamente para a fase seguinte.

---

# 2. PRIORIDADE ATUAL

Nesta etapa do CORE, priorizar:

1. corretude dos dados;
2. regras de negócio;
3. multiempresa;
4. multifilial;
5. RBAC;
6. histórico/snapshots;
7. drill-down;
8. consistência financeira;
9. filtros;
10. exportação funcional.

## NÃO priorizar agora

- redesign completo dos relatórios;
- refinamento visual excessivo;
- animações;
- reconstrução estética página a página.

A aparência final dos relatórios será tratada em uma rodada única depois das fases funcionais.

---

# 3. PADRÃO GLOBAL DE RELATÓRIO

Todos os relatórios devem seguir conceitualmente:

```text
FILTROS

KPIs

MENUS / ABAS

CONTEÚDO
```

## Ordem obrigatória

1. filtros;
2. KPIs;
3. navegação interna;
4. conteúdo da aba.

KPIs não devem ficar abaixo das abas.

---

# 4. FILTROS PRINCIPAIS + FILTROS AVANÇADOS

Relatórios com muitos filtros não devem exibir tudo aberto inicialmente.

## Estado inicial

Mostrar principalmente:

```text
Período
Atalhos rápidos
```

e apenas filtros adicionais realmente essenciais para aquele relatório.

Exemplo:

```text
Hoje | 7 dias | 30 dias | Personalizado

[ + Filtros ]
```

## `+ Filtros`

Ao clicar:

- expandir filtros avançados;
- preservar valores;
- permitir recolher;
- exibir quantidade de filtros avançados ativos.

Exemplo:

```text
+ Filtros (3)
```

Pode mostrar chips quando útil:

```text
Fornecedor: Coca-Cola ×
Status: Recebido ×
Produto: Coca ×
```

Ação:

```text
Limpar filtros
```

---

# 5. REGRA GLOBAL — ATALHOS RÁPIDOS SÃO AUTOAPLICÁVEIS

**Regra obrigatória para todos os relatórios existentes e futuros.**

Ao clicar em um preset:

```text
Hoje
7 dias
30 dias
Outro atalho rápido
```

o relatório deve atualizar **imediatamente**.

Não exigir:

```text
clicar no atalho
→ depois clicar em Aplicar
```

## Comportamento correto

```text
clicou em Hoje → consulta/aplica imediatamente

clicou em 7 dias → consulta/aplica imediatamente

clicou em 30 dias → consulta/aplica imediatamente
```

## Botão `Aplicar`

Reservar para:

- período personalizado;
- combinação de filtros avançados;
- cenários em que múltiplas escolhas precisam ser confirmadas de uma vez.

## Regra de reutilização

Não implementar esse comportamento separadamente em cada fase.

Usar componente/hook/helper compartilhado sempre que tecnicamente adequado.

As Fases 4, 5 e 6 devem nascer com esse comportamento.

---

# 6. LOADING

Quando uma consulta demorar:

- skeleton de KPI;
- skeleton de tabela;
- skeleton de gráfico;
- shimmer/pulse discreto;
- overlay sutil ao atualizar filtro;
- manter layout estável.

Não usar:

- porcentagem falsa;
- progresso inventado;
- tela inteira piscando;
- loading diferente em cada relatório.

O padrão deve ser reutilizável.

---

# 7. FILTROS HISTÓRICOS

Relatório histórico não pode depender somente do cadastro ativo atual.

## Regra

```text
Opções do filtro
=
entidades atuais relevantes
+
entidades históricas presentes no período consultado
```

Exemplo:

```text
Rayara vendeu em agosto
Rayara foi arquivada em setembro
```

Ao consultar agosto:

```text
Rayara (Arquivada)
```

deve continuar disponível.

Aplicar a:

- atendentes;
- operadores;
- produtos;
- categorias;
- formas de pagamento;
- clientes;
- promoções;
- modificadores;
- fornecedores;
- demais dimensões históricas relevantes.

Não carregar indiscriminadamente todos os arquivados de toda a história.

---

# 8. SNAPSHOTS HISTÓRICOS

Sempre usar snapshot quando disponível.

Exemplos:

```text
product_name
internal_code
category_id_snapshot
category_name_snapshot
payment_method_name
payment_method_code
modifier_snapshot
promotion snapshot
component_cost_snapshot
```

Não reconstruir passado usando apenas cadastro atual.

---

# 9. LINKS / DRILL-DOWN

Toda referência concreta deve ser clicável quando:

- existir página de detalhe;
- usuário possuir permissão.

Exemplos:

```text
Venda V00047
Compra C00012
Inventário I00004
Transferência T00009
Comanda #1042
Mesa 12
```

## Sem permissão

Mostrar texto simples, não link quebrado.

## Padrão

Não criar implementação diferente por relatório.

Usar padrão reutilizável de referência/link protegido.

---

# 10. MOTIVOS E TEXTOS LONGOS

Para:

- motivo de estorno;
- cancelamento;
- divergência;
- justificativa;
- observação crítica;

usar quando necessário:

```text
Ver motivo
```

→ modal responsivo.

Especialmente importante em mobile.

Se não houver conteúdo, não exibir ação vazia.

---

# 11. EXPORTAÇÃO — REGRA FUNCIONAL

Todos os relatórios devem poder reutilizar a infraestrutura compartilhada.

Formatos:

```text
Excel (.xlsx)
PDF
CSV
```

Exportação deve respeitar:

- empresa;
- filial;
- período;
- filtros;
- RBAC;
- snapshots históricos;
- aba/escopo quando aplicável.

Exportação nunca é bypass de permissão.

---

# 12. PDF — FUNCIONAL AGORA, REDESIGN DEPOIS

Durante as fases funcionais, o PDF precisa:

- abrir sem 500;
- conter dados corretos;
- preservar filtros/contexto;
- suportar tabelas grandes;
- respeitar RBAC;
- preservar histórico.

## Aparência final

A reformulação visual completa dos PDFs será feita na rodada final de UX dos relatórios.

Não gastar tempo agora redesenhando PDF relatório por relatório.

---

# 13. EXCEL

Excel deve preservar tipos corretamente:

- dinheiro → número formatado;
- data → data;
- datetime → datetime;
- percentual → percentual;
- quantidade → número.

Relatórios complexos podem usar múltiplas sheets quando fizer sentido.

---

# 14. PADRÕES TRANSVERSAIS DEVEM SER REUTILIZÁVEIS

As seguintes melhorias não devem ser duplicadas em cada relatório:

- filtros colapsáveis;
- atalhos autoaplicáveis;
- KPIs;
- loading;
- tabs;
- links protegidos;
- modais de motivo;
- filtros históricos;
- exportação PDF/XLSX/CSV;
- formatação monetária;
- empty states;
- paginação.

As fases futuras devem reutilizar esses padrões.

---

# 15. CORREÇÕES DA FASE 3 — REGRA DE COMPRA PARCIAL ENCERRADA

A Fase 3 já foi implementada, mas durante a validação foi identificada a necessidade de diferenciar:

```text
Valor pedido
Valor recebido
Valor não recebido
```

## Exemplo

Pedido:

```text
R$ 34,00
```

Recebido:

```text
R$ 17,00
```

Encerramento:

```text
PARCIAL ENCERRADA
```

Relatório deve mostrar:

```text
Valor pedido:     R$ 34,00
Valor recebido:   R$ 17,00
Não recebido:     R$ 17,00
```

## Regras

Valor pedido:
- valor originalmente solicitado.

Valor recebido:
- valor correspondente somente à quantidade efetivamente recebida.

Não recebido:
- diferença referente à parte não recebida.

Ao encerrar parcialmente:

- não recebido permanece como informação histórica;
- não entra em estoque;
- não deve inflar quantidade recebida;
- não deve inflar métrica de compra efetivamente realizada;
- preservar pedido original para auditoria.

## Contas a pagar

Não reduzir automaticamente obrigação financeira sem consultar a regra real/documento financeiro.

Relatório de Compras e Contas a pagar não devem misturar:

```text
mercadoria pedida
mercadoria recebida
obrigação financeira
```

São conceitos relacionados, mas diferentes.

---

# 16. CENTRAL FINAL DE RELATÓRIOS

Estrutura desejada ao final:

## Vendas

- Visão geral;
- Vendas;
- Recebimentos;
- Produtos e desempenho;
- Atendentes;
- Operadores;
- Cancelamentos/estornos;
- Consumação.

## Financeiro — SOMENTE RELATÓRIOS EXISTENTES NO ESCOPO ATUAL

- Resultado estimado;
- Comissões;
- Descontos/autorizações;
- Caixa;
- Sangrias;
- Contas a pagar.

## Estoque

- Posição de estoque;
- Movimentações;
- Consumo/custos;
- Preços por filial;
- Transferências.

## Inventários

- Inventários realizados.

## Compras

- Compras;
- Fornecedores.

## Operação

- Mesas e comandas;
- Promoções;
- Modificadores;
- Clientes.

## Auditoria

- Auditoria.

---

# 17. MÓDULO FINANCEIRO COMPLETO — ADIADO

Não criar/reformular agora um módulo financeiro completo.

A estrutura futura pode contemplar:

```text
Financeiro
├── Visão geral
├── Contas a receber
├── Contas a pagar
├── Fluxo de caixa
├── Conciliação
├── Recebíveis Stone/PagBank
├── Taxas
├── Previsões
├── Chargebacks
└── Resultado
```

Porém isso está **fora do escopo atual pré-POS**.

## Motivo

Não é necessário bloquear as fases funcionais atuais nem o início do POS.

Stone/PagBank futuramente poderão exigir evolução desse módulo.

Portanto:

```text
NÃO implementar agora.
NÃO refatorar a estrutura atual por causa disso.
```

---

# 18. FASE 4 — MESAS E COMANDAS — PRÓXIMA

## Objetivo

Criar relatórios operacionais completos de mesas e comandas usando a infraestrutura já existente.

## Estrutura recomendada

```text
Resumo
Comandas
Itens
Pagamentos
Cancelamentos
Transferências
```

Pode ajustar nomes se a arquitetura real indicar opção melhor, sem perder os conceitos.

---

## 18.1. Resumo

KPIs funcionais:

- mesas abertas no período;
- comandas abertas;
- comandas encerradas;
- faturamento associado;
- ticket médio por comanda;
- permanência média, se houver dados confiáveis;
- cancelamentos;
- transferências/merge/split quando existentes.

Não fazer redesign avançado agora.

---

## 18.2. Comandas

Tabela:

```text
Comanda
Mesa
Abertura
Encerramento
Operador/atendente
Cliente, quando houver
Itens
Subtotal
Descontos
Taxa de serviço
Total
Status
```

Referência da comanda deve permitir drill-down quando existir tela e permissão.

---

## 18.3. Itens

Mostrar:

```text
Comanda
Mesa
Produto histórico
Categoria histórica
Quantidade
Modificadores
Promoção
Desconto
Subtotal
Cancelamento, quando houver
```

Usar snapshots históricos.

---

## 18.4. Pagamentos

Mostrar:

- forma;
- valor;
- parcial;
- total;
- estorno;
- status/situação real;
- vínculo com comanda;
- venda gerada, quando aplicável.

Não inventar status.

---

## 18.5. Cancelamentos

Mostrar:

- comanda;
- item;
- quantidade;
- valor;
- responsável;
- autorizador;
- motivo;
- data/hora.

`Ver motivo` em modal quando necessário.

---

## 18.6. Transferências / Merge / Split

Quando já existirem no domínio:

- transferência entre mesas;
- transferência de item;
- merge;
- split;
- origem;
- destino;
- responsável;
- data/hora.

Preservar histórico/auditoria.

---

## 18.7. Filtros

Incluir apenas os necessários:

- período;
- atalhos autoaplicáveis;
- status;
- mesa;
- comanda;
- atendente;
- operador;
- cliente;
- forma de pagamento.

Filtros avançados ficam em `+ Filtros`.

---

## 18.8. Multiempresa/multifilial

Obrigatório:

- contexto da empresa;
- contexto da filial;
- nenhum vazamento;
- histórico por filial correto.

---

# 19. FASE 5 — RELATÓRIOS COMERCIAIS COMPLEMENTARES

Implementar somente depois da Fase 4 validada.

Inclui:

```text
Promoções
Modificadores
Clientes
```

---

## 19.1. Promoções

Estrutura sugerida:

```text
Resumo
Promoções
Produtos
Impacto
```

Métricas:

- utilizações;
- quantidade afetada;
- valor bruto;
- desconto;
- receita líquida;
- produtos envolvidos;
- período;
- usuários/vendas relacionadas.

Preservar snapshot.

---

## 19.2. Modificadores

Mostrar sempre contexto completo:

```text
GRUPO — MODIFICADOR
```

Exemplo:

```text
REDBULL — melancia
NARGUILÉ — melancia
```

Métricas:

- quantidade;
- receita adicional;
- produtos relacionados;
- grupos;
- participação.

Não confiar apenas no nome atual.

---

## 19.3. Clientes

Estrutura:

```text
Resumo
Clientes
Compras
Produtos
Comandas
```

quando os dados existirem.

Métricas:

- clientes atendidos;
- recorrência;
- ticket;
- total comprado;
- última compra;
- produtos mais consumidos;
- comandas relacionadas.

Respeitar LGPD e permissões.

---

# 20. FASE 6 — RODADA FINAL DE RELATÓRIOS / UX

**Somente depois das Fases 4 e 5 funcionarem corretamente.**

Esta será a etapa de reformulação visual global.

Não fazer redesign isolado antes dela, salvo correção crítica de usabilidade.

---

## 20.1. Objetivo

Transformar os relatórios atualmente funcionais em uma experiência visual consistente e premium do CORE.

Aplicar a TODOS os relatórios de uma vez.

---

## 20.2. Redesign dos KPIs

Criar padrão visual final:

- ícones;
- hierarquia;
- delta;
- semântica;
- light/dark;
- responsividade;
- hover/drill-down quando útil.

Sem “cards mortos”.

---

## 20.3. Filtros finais

Padronizar:

```text
Período + atalhos
+ Filtros
chips ativos
limpar filtros
```

Atalhos continuam autoaplicáveis.

Mobile:

- drawer;
- bottom sheet;
- modal responsivo.

---

## 20.4. Gráficos

Revisar cada relatório e escolher gráficos realmente úteis.

Exemplos:

- linha;
- barras;
- donut;
- heatmap;
- distribuição;
- evolução;
- ranking.

Não colocar gráfico por decoração.

---

## 20.5. Tabelas

Padronizar:

- densidade;
- alinhamento;
- moeda;
- quantidade;
- data/hora;
- badges;
- links;
- ações;
- sticky headers;
- paginação;
- mobile;
- colunas opcionais.

---

## 20.6. Loading

Aplicar skeletons finais consistentes.

---

## 20.7. Empty states

Estados vazios úteis:

```text
Nenhuma venda encontrada neste período.
Nenhuma transferência corresponde aos filtros.
```

Com orientação quando fizer sentido.

---

## 20.8. PDF FINAL

Depois de todos os relatórios existirem, reformular o PDF para representar melhor a página.

Suportar:

- identidade CORE;
- KPIs;
- gráficos;
- seções;
- tabelas;
- filtros;
- período;
- empresa;
- filial;
- cabeçalho;
- rodapé;
- paginação;
- landscape quando necessário.

Não precisa copiar HTML pixel a pixel.

---

## 20.9. Excel final

Aprimorar:

- sheets;
- títulos;
- filtros;
- freeze pane;
- widths;
- formatação;
- tipos;
- resumo;
- dados.

---

## 20.10. Central de Relatórios

Revisar a Central:

- nomes;
- agrupamentos;
- descrições;
- permissões;
- links;
- duplicidades;
- ordem;
- atalhos;
- relatórios sem implementação.

---

# 21. FASE 7 — GATE PRÉ-POS

Não implementar POS dentro desta fase.

Objetivo: confirmar que o Backoffice fornece base suficiente para o POS.

Validar:

- vendas;
- produtos;
- preços;
- estoque;
- modificadores;
- promoções;
- mesas;
- comandas;
- usuários;
- permissões;
- filial;
- caixa;
- impressão/produção;
- tickets quando aplicável;
- histórico;
- auditoria.

Somente depois:

```text
INICIAR CORE POS
```

---

# 22. INVENTÁRIO — SITUAÇÃO

Relatórios e estrutura de inventário da Fase 2 já existem.

Não criar uma nova fase de reformulação de inventário apenas por estética.

Se durante testes operacionais aparecerem problemas reais de:

- contagem;
- recontagem;
- aplicação de ajuste;
- divergência;
- encerramento;
- auditoria;
- permissões;

corrigir como requisito operacional antes do POS.

Não fazer uma reescrita preventiva sem evidência de necessidade.

---

# 23. ROADMAP ATUAL

```text
FASE 1 ✅
Relatórios-base

FASE 2 ✅
Estoque e inventários

FASE 3 ✅
Compras, Fornecedores e Contas a pagar
→ validação/correções pontuais atuais

FASE 4 ⏭️
Mesas e Comandas

FASE 5
Promoções, Modificadores e Clientes

FASE 6
Redesign final + UX + Central + PDF/Excel

FASE 7
Gate pré-POS

DEPOIS
CORE POS
```

## Fora do escopo atual

```text
Reformulação completa do módulo Financeiro
```

fica para uma etapa futura.

---

# 24. COMANDO-PADRÃO PARA AS PRÓXIMAS FASES

Ao executar qualquer fase futura:

```text
Leia integralmente este .md para entender arquitetura, padrões e dependências.

Execute SOMENTE a fase solicitada.

Não reimplemente fases concluídas.

Não faça redesign geral dos relatórios antes da Fase 6.

Reutilize:
- filtros colapsáveis;
- atalhos rápidos autoaplicáveis;
- KPIs;
- loading;
- links protegidos;
- filtros históricos;
- snapshots;
- exportação compartilhada;
- RBAC.

Preserve:
- multiempresa;
- multifilial;
- auditoria;
- histórico;
- regras financeiras;
- permissões.

Não faça auditoria geral do projeto.

Não execute testes automatizados, builds, CI, Docker build ou scans extensos.

Ao terminar, pare e entregue testes manuais.

Não avance automaticamente para a próxima fase.
```

---

# 25. COMANDO DA FASE 4

Quando a Fase 3 estiver validada:

```text
Leia integralmente:
CORE_PDV_PLANO_RELATORIOS_POR_FASES_V5_2026-09-02.md

Execute SOMENTE a FASE 4 — MESAS E COMANDAS.

As Fases 1, 2 e 3 já estão implementadas.
NÃO reimplemente nenhuma delas.
NÃO inicie a Fase 5.

IMPORTANTE:

O redesign completo dos relatórios está adiado para a Fase 6.

Nesta fase priorize:
- dados corretos;
- regras de negócio;
- histórico;
- snapshots;
- RBAC;
- multiempresa;
- multifilial;
- drill-down;
- filtros;
- exportação funcional.

Reutilize os padrões compartilhados já existentes.

ATALHOS RÁPIDOS:
Hoje / 7 dias / 30 dias e demais presets devem aplicar imediatamente ao clicar.
Não exigir botão Aplicar depois de selecionar um preset.
Aplicar fica para período personalizado/filtros avançados quando necessário.

NÃO execute testes automatizados.
NÃO execute build.
NÃO execute CI.
NÃO execute Docker build.
NÃO faça auditoria geral.

Ao terminar, PARE.

Retorne:
1. Implementado
2. Arquivos alterados
3. Endpoints
4. Migrations
5. Permissões
6. Decisões
7. Pendências
8. Testes MANUAIS

NÃO inicie a Fase 5.
```

---

# 26. REGRA FINAL

A prioridade até o POS é:

> primeiro fazer todas as funções corretas; depois fazer todos os relatórios bonitos de uma vez.

Evitar retrabalho visual enquanto ainda existem novos tipos de relatório entrando no sistema.

