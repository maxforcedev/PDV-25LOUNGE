# CORE PDV — PLANO DE IMPLEMENTAÇÃO DOS RELATÓRIOS POR FASES
**Data:** 01/09/2026  
**Objetivo:** organizar, completar e padronizar a Central de Relatórios do CORE PDV antes do início do POS.

---

# REGRA DE EXECUÇÃO

## NÃO EXECUTAR TESTES AUTOMATIZADOS

Para economizar créditos e tempo de execução, o OpenCode NÃO deve executar nesta rodada:

- suíte completa do backend;
- testes Django;
- testes frontend;
- Jest/Vitest;
- Playwright;
- `npm test`;
- `npm run build`;
- `npm audit`;
- `pip-audit`;
- CI;
- GitHub Actions;
- Docker build;
- scans extensos.

Pode executar apenas verificações estáticas simples e pontuais quando realmente necessárias.

Ao concluir cada fase, informar somente:

```text
1. O que foi implementado
2. Arquivos alterados
3. Migrations criadas, se houver
4. Endpoints criados/alterados
5. Decisões de arquitetura
6. Lista curta de testes manuais que devo executar
```

Não iniciar POS nesta rodada.

---

# ESTRUTURA FINAL DA CENTRAL DE RELATÓRIOS

## Vendas
- Visão geral
- Vendas
- Recebimentos / Formas de pagamento
- Produtos e desempenho
- Atendentes
- Operadores
- Cancelamentos e estornos
- Consumação / Cortesias

## Financeiro
- Resultado estimado
- Comissões
- Descontos e autorizações
- Caixa
- Sangrias
- Contas a pagar

## Estoque
- Posição de estoque
- Movimentações de estoque
- Consumo / Custos
- Preços por filial
- Transferências de estoque

## Inventários
- Inventários realizados

## Compras
- Compras
- Fornecedores

## Operação
- Mesas e comandas
- Promoções
- Modificadores
- Clientes

## Auditoria & Controle
- Auditoria

---

# PRINCÍPIOS GERAIS

Todos os relatórios devem:

- respeitar empresa atual;
- respeitar filial atual quando o relatório for branch-scoped;
- respeitar permissões existentes;
- impedir vazamento de dados entre empresas/filiais;
- utilizar snapshots históricos quando existentes;
- não recalcular histórico apenas com base no cadastro atual;
- usar `Decimal` em valores monetários;
- usar paginação em tabelas extensas;
- permitir Hoje / 7 dias / 30 dias / Personalizado;
- não duplicar filtro de filial quando o seletor global já define o contexto;
- esconder custo/margem quando o usuário não tiver permissão;
- priorizar leitura rápida + drill-down;
- evitar relatórios redundantes.

---


---

# PADRÃO DE UX PARA RELATÓRIOS COMPLEXOS — USAR ABAS INTERNAS

Relatórios mais densos NÃO devem concentrar todos os KPIs, gráficos e tabelas em uma única página longa.

Seguir o mesmo padrão de navegação já utilizado no CORE em telas como Produtos e Usuários:

```text
Cabeçalho
Período / filtros globais
KPIs principais
Abas internas
Conteúdo da aba atual
```

## Regras gerais

- filtros de período ficam no topo e afetam todas as abas;
- empresa/filial continuam vindo do contexto global;
- filtros específicos podem existir dentro da aba;
- não repetir a mesma informação em várias abas;
- a aba `Resumo` mostra indicadores e tendências;
- abas detalhadas mostram tabelas e drill-down;
- evitar mais de 5–6 abas principais quando possível;
- quando houver muitas subdivisões, usar filtros/segmentos dentro da aba em vez de criar dezenas de abas;
- manter o estado da aba na URL quando fizer sentido;
- manter responsividade mobile/tablet/desktop;
- não carregar dados pesados de todas as abas ao mesmo tempo se não for necessário;
- lazy-load ou buscar dados quando a aba for aberta quando isso reduzir custo e tempo;
- permissões devem controlar também a exibição das abas;
- uma aba sem permissão não deve aparecer;
- não usar aba vazia apenas para “preencher” layout.

## Estrutura recomendada por relatório complexo

### Vendas

```text
Resumo
Vendas
Itens
Pagamentos
Cancelamentos
```

**Resumo**
- KPIs;
- evolução;
- distribuição por pagamento;
- comparativo de período.

**Vendas**
- tabela principal de vendas;
- filtros;
- detalhe expandido.

**Itens**
- produtos;
- categoria histórica;
- modificadores;
- promoções;
- descontos.

**Pagamentos**
- forma;
- valor aplicado;
- recebido;
- troco;
- origem;
- estornos.

**Cancelamentos**
- vendas canceladas;
- itens cancelados;
- responsáveis;
- motivos;
- impacto financeiro.

---

### Produtos e desempenho

```text
Desempenho
Categorias
Modificadores
Promoções
Margem e custos
```

**Desempenho**
- quantidade;
- faturamento;
- ticket;
- ranking.

**Categorias**
- quantidade;
- faturamento;
- custo;
- margem por categoria.

**Modificadores**
- adicionais vendidos;
- quantidade;
- faturamento adicional.

**Promoções**
- utilizações;
- desconto;
- receita líquida.

**Margem e custos**
- custo histórico;
- margem R$;
- margem %;
- somente para usuários autorizados.

---

### Compras

```text
Resumo
Pedidos
Itens
Recebimentos
Divergências
```

**Resumo**
- total comprado;
- compras realizadas;
- pendências;
- divergências.

**Pedidos**
- pedido;
- fornecedor;
- status;
- datas;
- valores.

**Itens**
- produto;
- unidade de compra;
- quantidade;
- preço;
- custo efetivo.

**Recebimentos**
- pedido;
- recebido agora;
- total recebido;
- pendente.

**Divergências**
- faltas;
- sobras;
- motivo;
- responsável;
- impacto.

---

### Fornecedores

```text
Resumo
Compras
Produtos
Custos
Contas a pagar
```

**Resumo**
- nº compras;
- total comprado;
- ticket médio;
- última compra;
- contas abertas/vencidas.

**Compras**
- histórico de compras.

**Produtos**
- produtos mais comprados.

**Custos**
- último preço;
- custo médio;
- evolução de preço.

**Contas a pagar**
- parcelas;
- vencimentos;
- status;
- pagamentos.

---

### Estoque

Preferir uma experiência unificada de estoque com abas internas:

```text
Posição
Movimentações
Inventários
Transferências
Perdas e ajustes
```

**Posição**
- saldo atual;
- mínimo/máximo;
- custo médio;
- valor em estoque;
- situação.

**Movimentações**
- entradas;
- vendas;
- ajustes;
- inventários;
- reversões.

**Inventários**
- histórico;
- divergências;
- impacto.

**Transferências**
- origem;
- destino;
- enviado;
- recebido;
- diferença.

**Perdas e ajustes**
- produto;
- quantidade;
- motivo;
- responsável;
- impacto financeiro.

A Central pode continuar apresentando atalhos individuais para Posição, Movimentações, Inventários e Transferências, mas todos podem convergir para a mesma área de Estoque com a aba correta já selecionada.

---

### Mesas e comandas

```text
Resumo
Comandas
Itens
Pagamentos
Cancelamentos
Transferências
```

**Resumo**
- abertas;
- fechadas;
- mesas utilizadas;
- ticket;
- tempo médio.

**Comandas**
- comanda;
- mesa;
- cliente;
- abertura;
- fechamento;
- duração;
- total.

**Itens**
- produtos;
- modificadores;
- descontos.

**Pagamentos**
- pagamentos parciais;
- recebido;
- troco;
- estornos.

**Cancelamentos**
- item;
- responsável;
- motivo;
- valor.

**Transferências**
- mesa;
- item;
- merge;
- split;
- origem/destino;
- responsável.

---

### Caixa

```text
Resumo
Sessões
Recebimentos
Sangrias
Entradas
Diferenças
```

**Resumo**
- sessões;
- diferenças;
- sangrias;
- entradas.

**Sessões**
- abertura;
- fechamento;
- operador;
- fundo;
- esperado/informado.

**Recebimentos**
- formas;
- valores;
- vendas relacionadas.

**Sangrias**
- valor;
- motivo;
- categoria;
- beneficiário.

**Entradas**
- entradas manuais;
- motivo;
- operador.

**Diferenças**
- esperado;
- informado;
- diferença;
- responsável;
- contexto.

---

### Financeiro / Resultado

Para evitar poluição:

```text
Resumo
Resultado
Comissões
Descontos e autorizações
Contas a pagar
```

Esta estrutura pode ser usada em uma área financeira consolidada, mantendo também atalhos diretos na Central.

---

### Clientes

```text
Resumo
Clientes
Compras
Produtos
Comandas
```

Não transformar esta tela em CRM completo.

---

## Regra de navegação

Quando o usuário vier da Central por um atalho específico, abrir diretamente a aba correspondente.

Exemplos:

```text
Central → Inventários realizados
→ /relatorios/estoque?tab=inventarios
```

```text
Central → Sangrias
→ /relatorios/caixa?tab=sangrias
```

```text
Central → Cancelamentos
→ /relatorios/vendas?tab=cancelamentos
```

Se a arquitetura atual usa rotas separadas e alterar isso gerar risco desnecessário, manter as rotas existentes, mas reutilizar o mesmo componente/tab layout. Não fazer refactor de rota apenas por estética.

## Regra de densidade

A aba deve conter, em geral:

```text
até 4–6 KPIs
+
no máximo 1–2 gráficos realmente úteis
+
1 tabela principal
+
detalhe expandido quando necessário
```

Evitar:

- 10+ cards;
- três ou quatro gráficos simultâneos sem necessidade;
- tabelas diferentes empilhadas uma após outra;
- repetir os mesmos KPIs em todas as abas;
- colocar relatórios completos dentro do Resumo.


# FASE 1 — CORRIGIR E ENRIQUECER RELATÓRIOS JÁ EXISTENTES

## 1. VISÃO GERAL

### Objetivo
Visão executiva do período sem duplicar o dashboard.

### KPIs
- faturamento bruto;
- faturamento líquido;
- número de vendas;
- ticket médio;
- total recebido;
- descontos;
- taxa de serviço;
- cancelamentos;
- consumação/cortesias;
- resultado estimado;
- margem estimada.

### Comparação com período anterior
Exibir:
- variação R$;
- variação %;
- alta/queda.

Regras:
- Hoje x ontem;
- 7 dias x 7 dias anteriores;
- 30 dias x 30 dias anteriores;
- personalizado x período anterior de mesmo tamanho.

### Gráficos
- evolução de vendas;
- recebimentos por forma;
- faturamento por dia/hora quando fizer sentido.

Não incluir rankings completos ou heatmap detalhado.

---

## 2. VENDAS

### Tabela
```text
Venda
Data/hora
Cliente
Atendente
Operador
Caixa
Status
Subtotal
Desconto
Taxa
Total
Recebido
```

### Detalhe
```text
Produto
Categoria histórica
Quantidade
Preço base
Modificadores/adicionais
Promoção
Desconto do item
Subtotal
Total
```

### Com permissão de custo
```text
Custo unitário histórico
Custo total
Margem R$
Margem %
```

### Pagamentos
```text
Forma
Valor aplicado
Valor recebido
Troco
Horário
Origem
```

Origem:
- venda direta;
- comanda;
- pagamento parcial.

### Filtros
- período;
- status;
- cliente;
- atendente;
- operador;
- forma de pagamento;
- produto;
- categoria;
- faixa de valor.

---

## 3. RECEBIMENTOS / FORMAS DE PAGAMENTO

### KPIs
- total recebido;
- quantidade de pagamentos;
- ticket médio recebido;
- dinheiro;
- PIX;
- cartão;
- outros;
- troco total;
- estornos.

### Distribuição
```text
Forma
Quantidade
Valor
%
```

### Detalhado
```text
Data/hora
Venda/comanda
Forma
Valor aplicado
Valor recebido
Troco
Operador
Status
```

Tratar:
- parcial;
- estorno;
- consumação;
- venda cancelada;
- divergência recebido x aplicado.

---

## 4. CANCELAMENTOS E ESTORNOS

### KPIs
- vendas canceladas;
- valor total cancelado;
- % do faturamento cancelado;
- itens cancelados em comandas;
- pagamentos estornados.

### Vendas canceladas
```text
Venda
Data/hora
Valor
Atendente
Operador
Cancelado por
Motivo
Valor revertido
```

### Itens cancelados
```text
Comanda
Mesa
Produto
Quantidade
Valor
Cancelado por
Motivo
Data/hora
```

### Estornos
```text
Venda/Comanda
Valor
Forma
Estornado por
Motivo
Data/hora
```

Nunca perder ator, motivo e impacto financeiro.

---

## 5. DESCONTOS E AUTORIZAÇÕES

Renomear “Descontos” para:

```text
Descontos e autorizações
```

### KPIs
- desconto total;
- vendas com desconto;
- desconto médio;
- desconto por item;
- desconto na conta;
- promoção;
- taxa removida.

### Tabela
```text
Venda/Comanda
Tipo
Valor
Percentual
Aplicado por
Aprovado por
Atendente
Data/hora
```

Tipos:
- item;
- conta;
- promoção;
- retirada de taxa.

---

## 6. PRODUTOS E DESEMPENHO

### KPIs
- unidades vendidas;
- faturamento;
- custo;
- margem;
- descontos;
- produto mais vendido.

### Tabela
```text
Produto
Categoria
Quantidade
Faturamento
Descontos
Custo
Margem R$
Margem %
Ticket médio
```

Custo/margem apenas com permissão.

### Por categoria
```text
Categoria
Quantidade
Faturamento
Custo
Margem
```

### Modificadores
```text
Modificador
Quantidade
Faturamento adicional
Produtos onde foi usado
```

### Promoções
```text
Promoção
Utilizações
Valor concedido
Receita líquida
```

---

## 7. ATENDENTES

```text
Atendente
Quantidade de vendas
Faturamento
Ticket médio
Itens vendidos
Comissão
Descontos
Cancelamentos
Taxas removidas
```

Ao expandir:
- produtos mais vendidos;
- vendas;
- horários de maior movimento.

---

## 8. OPERADORES

Adicionar à Central.

```text
Operador
Vendas processadas
Total recebido
Caixas operados
Descontos autorizados
Cancelamentos
Estornos
Diferenças de caixa
```

---

## 9. CONSUMAÇÃO / CORTESIAS

```text
Beneficiário
Referência
Produto
Categoria
Quantidade
Valor comercial
Valor cobrado
Subsídio/cortesia
Custo
Responsável
Data/hora
```

KPIs:
- valor comercial;
- valor cobrado;
- valor subsidiado;
- custo;
- beneficiários.

Rankings:
- beneficiário;
- produto;
- categoria.

---

## 10. RESULTADO ESTIMADO

Na Central, usar:

```text
Resultado estimado
```

e não “Faturamento”.

Mostrar:
```text
Receita recebida
(-) CMV
(-) consumação/cortesias
(-) comissões
(-) despesas consideradas
= resultado estimado
```

KPIs:
- receita;
- custo;
- resultado;
- margem %.

Deixar claro que é resultado operacional/estimado, não DRE contábil completa.

---

## 11. COMISSÕES

```text
Funcionário
Vendas elegíveis
Base de cálculo
Percentual
Comissão total
```

Detalhe:
```text
Venda
Produto
Quantidade
Base
Percentual
Comissão
```

---

## 12. CAIXA

### KPIs
- sessões abertas;
- sessões fechadas;
- diferença total;
- sangrias;
- entradas manuais.

### Tabela
```text
Sessão
Operador
Aberto por
Abertura
Fechado por
Fechamento
Duração
Fundo
Entradas
Sangrias
Esperado
Informado
Diferença
Status
```

### Detalhe
- recebimentos por forma;
- entradas;
- sangrias;
- cancelamento;
- motivo;
- responsável.

---

## 13. SANGRIAS

```text
Data/hora
Caixa
Sessão
Operador
Valor
Categoria
Beneficiário
Motivo
Observação
```

Adicionar agrupamento:
- operador;
- categoria;
- beneficiário.

---

## 14. PREÇOS POR FILIAL

Corrigir disponibilidade.

### Tabela
```text
Produto
Preço padrão
Filial A
Filial B
Filial C
```

Cada célula:
- preço específico;
- preço padrão herdado;
- não disponível.

Exemplo:
```text
Coca
Padrão R$ 10
Pavuna R$ 11
Centro R$ 10 (padrão)
Caxias Não disponível
```

---

## 15. MOVIMENTAÇÕES DE ESTOQUE

Adicionar corretamente à Central.

```text
Data/hora
Produto
Categoria
Tipo
Origem
Saldo anterior
Movimento
Saldo final
Unidade
Custo snapshot
Impacto em custo
Responsável
Motivo
Referência
```

Tipos:
- entrada;
- venda;
- perda;
- ajuste;
- inventário;
- transferência;
- reversão.

Avaliar snapshot de categoria para novas movimentações.

---

# FASE 2 — ESTOQUE E INVENTÁRIO

## 16. POSIÇÃO DE ESTOQUE

Criar relatório real.

### Cards
```text
Valor total em estoque
Abaixo do mínimo
Zerados
Negativos
```

### Tabela
```text
Produto
Categoria
Unidade
Saldo atual
Mínimo
Máximo
Custo médio
Último custo
Valor em estoque
Situação
```

Situações:
- Normal;
- Abaixo do mínimo;
- Zerado;
- Negativo;
- Arquivado com saldo.

Regras:
- arquivado com saldo != 0 aparece com badge;
- não entra nos KPIs atuais;
- arquivado com saldo 0 some da visão padrão;
- histórico continua acessível.

---

## 17. INVENTÁRIOS REALIZADOS

### Cards
- inventários;
- itens contados;
- divergentes;
- impacto financeiro.

### Tabela
```text
Inventário
Data
Filial
Responsável
Status
Itens
Corretos
Faltas
Sobras
Impacto financeiro
```

### Detalhe
```text
Produto
Saldo esperado
Contagem
Divergência
Tipo
Custo
Impacto
```

Cores:
- falta vermelho;
- sobra amarelo;
- exato verde.

---

## 18. TRANSFERÊNCIAS DE ESTOQUE

```text
Transferência
Origem
Destino
Data
Responsável
Status
Itens
Qtd enviada
Qtd recebida
Divergência
```

Detalhe:
```text
Produto
Enviado
Recebido
Diferença
Custo
```

---

# FASE 3 — COMPRAS, FORNECEDORES E CONTAS A PAGAR

## 19. COMPRAS

### Cards
```text
Total comprado
Compras realizadas
Pendente de recebimento
Parcialmente recebidas
Com divergência
```

### Tabela
```text
Compra
Fornecedor
Tipo
Status
Criada em
Pedido realizado em
Recebida em
Valor bruto
Desconto
Frete
Outras despesas
Total
Documento
```

Tipos:
- Pedido de compra;
- Entrada direta.

Status:
- RASCUNHO;
- PEDIDO_REALIZADO;
- PARCIALMENTE_RECEBIDO;
- RECEBIDO;
- CANCELADO.

### Itens
```text
Produto
Unidade de compra
Qtd pedida
Recebida agora
Total recebido
Pendente
Preço apresentação
Preço unitário
Custo efetivo unitário
Divergência
```

Filtros:
- fornecedor;
- status;
- tipo;
- período;
- documento;
- responsável.

---

## 20. FORNECEDORES

Criar relatório real. O link não pode apontar para Produtos.

### Cards
- fornecedores ativos;
- total comprado;
- fornecedores com contas vencidas;
- maior volume de compra.

### Tabela
```text
Fornecedor
Documento
Qtd compras
Total comprado
Ticket médio
Última compra
Contas abertas
Contas vencidas
```

### Detalhe
- produtos mais comprados;
- último preço;
- custo médio;
- evolução de preço;
- divergências;
- contas a pagar.

Respeitar escopo de filial.

---

## 21. CONTAS A PAGAR

### Cards
```text
Vencidas
Vence hoje
Próximos 7 dias
Próximos 30 dias
Pagas no período
```

### Tabela
```text
Vencimento
Fornecedor
Compra
Parcela
Valor
Status
Dias em atraso
Valor pago
Data pagamento
Forma
Responsável
```

Status:
- aberta;
- vencida;
- paga;
- cancelada.

Filtros:
- vencimento;
- fornecedor;
- status;
- forma.

---

# FASE 4 — MESAS E COMANDAS

## 22. MESAS E COMANDAS

### Cards
```text
Comandas abertas
Comandas fechadas
Mesas utilizadas
Ticket médio
Tempo médio de permanência
```

### Tabela
```text
Comanda
Mesa
Cliente
Status
Aberta em
Fechada em
Duração
Aberta por
Fechada por
Total
```

### Detalhe — itens
```text
Produto
Modificadores
Quantidade
Preço
Desconto
Total
```

### Pagamentos
```text
Forma
Valor
Recebido
Troco
Horário
Responsável
```

### Cancelamentos
```text
Produto
Quantidade
Valor
Cancelado por
Motivo
Data/hora
```

### Transferências
```text
Tipo
Origem
Destino
Responsável
Data/hora
```

### Descontos/taxa
```text
Desconto
Taxa removida
Aprovador
Responsável
```

---

## 23. CANCELAMENTOS DE ITENS

Aba de Mesas e Comandas.

```text
Comanda
Mesa
Produto
Quantidade
Valor
Cancelado por
Motivo
Data/hora
```

---

## 24. PAGAMENTOS PARCIAIS / ESTORNOS

Aba.

```text
Comanda
Mesa
Forma
Valor aplicado
Valor recebido
Troco
Status
Estornado por
Motivo
Data/hora
```

---

## 25. TRANSFERÊNCIAS / MERGE / SPLIT

Mostrar:
- transferência de mesa;
- transferência de item;
- união;
- divisão;
- responsável;
- origem;
- destino;
- data/hora;
- impacto financeiro.

---

# FASE 5 — RELATÓRIOS COMERCIAIS COMPLEMENTARES

## 26. PROMOÇÕES

### Cards
- utilizações;
- faturamento vinculado;
- desconto concedido;
- receita líquida.

### Tabela
```text
Promoção
Utilizações
Produtos
Faturamento original
Desconto concedido
Faturamento líquido
Ticket médio
```

Detalhe:
- vendas;
- clientes;
- produtos;
- horários/dias.

---

## 27. MODIFICADORES

### Cards
- modificadores vendidos;
- faturamento adicional;
- mais vendido.

### Tabela
```text
Modificador
Quantidade
Faturamento adicional
Produtos associados
Ticket adicional médio
```

---

## 28. CLIENTES

### Cards
- clientes atendidos;
- recorrentes;
- ticket médio;
- frequência média.

### Tabela
```text
Cliente
Qtd compras
Faturamento
Ticket médio
Última compra
Frequência
```

Detalhe:
- produtos preferidos;
- categorias;
- comandas;
- histórico;
- promoções.

Não transformar isso em CRM nesta fase.

---

# FASE 6 — CENTRAL, EXPORTAÇÃO E UX

## 29. CENTRAL DE RELATÓRIOS

Corrigir nomes e links.

### Corrigir
```text
Faturamento → Resultado estimado
```

### Adicionar
- Operadores;
- Movimentações;
- Compras;
- Fornecedores real;
- Contas a pagar;
- Posição de estoque real;
- Inventários real;
- Mesas e comandas;
- Promoções;
- Modificadores;
- Clientes.

### Corrigir links provisórios
- Fornecedores não abre Produtos;
- Posição de estoque não é Estoque avançado genérico;
- Inventários não aponta para tela genérica.

---

## 30. EXPORTAÇÃO

Formatos desejados, quando houver renderer correspondente:

```text
CSV
XLSX
PDF
```

Regras:
- não mostrar formato não suportado;
- frontend/backend devem aceitar o mesmo conjunto;
- exportar filtros atuais;
- incluir empresa/filial/período;
- custo apenas para quem possui permissão.

---

## 31. PADRÃO VISUAL

Cada relatório deve reutilizar o padrão de abas internas definido neste documento quando o volume de informação justificar.

Cada relatório:

### Cabeçalho
- título;
- descrição;
- período;
- filtros;
- exportação.

### KPIs
Máximo 4–6 principais.

### Corpo
- gráfico útil;
- tabela;
- expansão;
- paginação;
- empty state.

Evitar:
- cards demais;
- informação duplicada;
- gráficos decorativos;
- cores excessivas;
- filtros sem utilidade.

---

# FASE 7 — APENAS PREPARAÇÃO PARA O POS

Não implementar agora.

Depois do POS:

## Tickets
- emitidos;
- validados;
- cancelados;
- tempo emissão→validação;
- produto/modificador;
- operador;
- setor.

## Produção
- pedidos por setor;
- tempo de preparo;
- atrasos;
- reimpressões;
- cancelamentos;
- fila.

## POS / dispositivos
- vendas por terminal;
- operador;
- dispositivo;
- uptime;
- versão;
- falhas.

## Stone/PagBank
- transações;
- autorizações;
- recusas;
- estornos;
- conciliação;
- divergência.

---

# ORDEM EXATA PARA O OPENCODE

## FASE 1
1. Visão geral
2. Vendas
3. Recebimentos
4. Cancelamentos e estornos
5. Descontos e autorizações
6. Produtos
7. Atendentes
8. Operadores
9. Consumação
10. Resultado estimado
11. Comissões
12. Caixa
13. Sangrias
14. Preços por filial
15. Movimentações de estoque

## FASE 2
16. Posição de estoque
17. Inventários realizados
18. Transferências de estoque

## FASE 3
19. Compras
20. Fornecedores
21. Contas a pagar

## FASE 4
22. Mesas e comandas
23. Cancelamentos de itens
24. Pagamentos parciais/estornos
25. Transferências/merge/split

## FASE 5
26. Promoções
27. Modificadores
28. Clientes

## FASE 6
29. Central de Relatórios
30. Exportação
31. Padronização visual

## FASE 7
Somente preparar arquitetura futura para:
- Tickets
- Produção
- POS
- Stone/PagBank

---

# CRITÉRIO DE CONCLUSÃO POR FASE

Ao encerrar uma fase, responder:

```text
FASE X — CONCLUÍDA

Implementado:
- ...

Arquivos alterados:
- ...

Endpoints:
- ...

Migrations:
- nenhuma / lista

Pendências manuais:
- ...

Não executados:
- testes automatizados
- build completo
- CI
```

---

# VALIDAÇÃO MANUAL

O OpenCode apenas informa os testes que o usuário deverá fazer.

Exemplos:

```text
Cancelamentos:
cancelar venda com motivo
→ confirmar usuário + motivo no relatório
```

```text
Preços por filial:
produto indisponível em filial B
→ mostrar “Não disponível”
```

```text
Compras:
compra parcialmente recebida
→ conferir pedido / recebido / pendente
```

```text
Posição de estoque:
produto arquivado com saldo
→ aparecer com badge Arquivado
```

```text
Mesas e comandas:
abrir e fechar comanda
→ validar duração, operador, pagamentos e total
```

---

# NÃO EXECUTAR TESTES AUTOMATIZADOS — REFORÇO FINAL

Durante toda esta implementação, NÃO executar automaticamente:

- Django tests;
- suíte backend;
- suíte frontend;
- Jest/Vitest;
- Playwright;
- builds completos;
- CI;
- GitHub Actions;
- audits;
- Docker builds;
- scans extensos.

Implementar fase por fase e entregar para validação manual.

Não iniciar POS até este escopo de relatórios ser revisado pelo usuário.
