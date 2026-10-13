# CORE PDV — MISSÃO 3 | PARTE 1
## REFORMULAÇÃO PROFISSIONAL DOS RELATÓRIOS E EXPORTAÇÕES

**Repositório:** `maxforcedev/PDV-25LOUNGE`  
**Branch:** `main`  
**Commit de referência:** `a457bc7`  
**Prioridade:** Alta  
**Escopo principal:** CORE Backoffice, relatórios e exportações PDF.

## 1. OBJETIVO

Precisamos transformar os relatórios do CORE PDV em documentos profissionais, modernos, organizados e úteis para a gestão empresarial.

O problema atual não é necessariamente a falta de dados, mas a maneira como eles são organizados e apresentados.

Já identificamos casos em que o relatório de apenas um dia gera aproximadamente 90 páginas, sem uma apresentação adequada, sem a identidade visual oficial do CORE e com informações excessivamente fragmentadas.

O objetivo desta missão é:

- Modernizar completamente a apresentação dos PDFs.
- Utilizar a identidade visual oficial do CORE PDV.
- Reduzir páginas desnecessárias e informações repetidas.
- Destacar os indicadores mais importantes.
- Separar relatórios executivos de relatórios detalhados.
- Organizar tabelas, agrupamentos, resumos e informações financeiras.
- Preservar todos os dados autorizados.
- Manter as exportações em Excel e CSV funcionando corretamente.

**Não modificar a lógica dos relatórios nem os cálculos comerciais e financeiros.**

---

## 2. ANÁLISE DA ESTRUTURA ATUAL

A geração de arquivos está centralizada principalmente em:

`backend/apps/base/report_exports.py`

Esse módulo já utiliza:

- ReportLab para PDFs.
- OpenPyXL para Excel.
- CSV para exportações tabulares.
- `render_report_export()` como mecanismo compartilhado.
- `report_key_value_rows()` para converter estruturas existentes.
- `_structured_sections()` para transformar estruturas do resumo em tabelas.

O backend dos relatórios está principalmente em:

`backend/apps/reports/views.py`

A interface de exportação está em:

`frontend/src/components/report-export-action.tsx`

Há também diferentes componentes de relatórios em:

- `frontend/src/components/dedicated-report.tsx`
- `frontend/src/components/commands-report.tsx`
- `frontend/src/components/commercial-complement-report.tsx`
- `frontend/src/components/phase-three-report.tsx`
- `frontend/src/components/tickets-report.tsx`
- `frontend/src/components/reports-center.tsx`

### Problemas de apresentação identificados

**1. Identidade visual insuficiente**

O PDF utiliza basicamente texto, sem incorporar adequadamente a logo oficial.

**2. Tabelas excessivamente genéricas**

As colunas recebem larguras iguais, independentemente do conteúdo.

**3. Fontes pequenas**

Existem tabelas com fontes de aproximadamente 5 a 6 pontos.

**4. Estruturas repetitivas**

`_structured_sections()` transforma indiscriminadamente diversas listas e estruturas do resumo em novas tabelas.

Dependendo da resposta, isso pode duplicar informações já exibidas em outras seções.

**5. Paginação inadequada**

Existem cabeçalhos repetidos nas tabelas, mas falta uma hierarquia visual mais completa.

**6. Falta de distinção entre visão executiva e detalhamento**

Um empresário que deseja verificar o desempenho do dia não deveria precisar percorrer dezenas de páginas de registros operacionais.

### Diretriz arquitetural

**Reutilizar e evoluir o mecanismo centralizado já existente.**

Não desenvolver um gerador separado para cada página e não duplicar a lógica financeira do backend.

---

## 3. DOIS FORMATOS DE RELATÓRIO PDF

Implementar dois modos de exportação.

### A. RELATÓRIO EXECUTIVO — PADRÃO

Destinado ao empresário ou gestor que deseja compreender o desempenho do negócio rapidamente.

Esse relatório deverá conter:

- Identificação da empresa e filial.
- Título do relatório.
- Período selecionado.
- Data e horário de geração.
- Indicadores essenciais.
- Totais consolidados.
- Tabelas resumidas.
- Agrupamentos realmente relevantes.
- Observações importantes, quando existirem.

Não incluir automaticamente todos os registros individuais do período.

A finalidade é apresentar uma visão clara, objetiva e profissional.

**O número de páginas deverá ser consequência do conteúdo realmente necessário, sem imposição arbitrária de um limite.**

### B. RELATÓRIO DETALHADO

Destinado à conferência, contabilidade, auditoria e análise aprofundada.

Deverá apresentar:

- Identificação e período.
- Resumo financeiro.
- Indicadores principais.
- Registros detalhados autorizados.
- Agrupamentos pertinentes.
- Informações operacionais relevantes.
- Paginação adequada.

O modo detalhado poderá possuir mais páginas, pois sua finalidade é apresentar informações completas.

Entretanto, não poderá gerar duplicações desnecessárias nem tabelas desorganizadas.

### Regra fundamental

**Nunca excluir silenciosamente dados de um relatório detalhado.**

O PDF executivo é uma apresentação resumida intencional.

O PDF detalhado é uma apresentação completa, de acordo com o escopo e as permissões do relatório.

CSV e Excel deverão continuar oferecendo os dados completos previstos pelos contratos atuais.

---

## 4. NOVA IDENTIDADE VISUAL DOS PDFs

Os relatórios deverão utilizar a identidade oficial do CORE PDV.

### Paleta de cores

**Azul principal:** `#3454D1`  
**Azul escuro:** `#2945B6`  
**Texto principal:** `#283C50`  
**Texto secundário:** `#64748B`  
**Fundo auxiliar:** `#F0F2F8`  
**Bordas:** `#E2E8F0`  
**Sucesso:** `#17C666`  
**Atenção:** `#FFA21D`  
**Perigo:** `#EA4D4D`

A paleta deverá ser utilizada com sobriedade, mantendo legibilidade na impressão.

### Logo oficial

Utilizar a nova identidade oficial do CORE PDV:

- CORE em azul-marinho.
- PDV em azul vivo.
- Símbolo espiral no O.
- Slogan: **O CORAÇÃO DO SEU NEGÓCIO**.

O frontend já possui os assets oficiais em:

`frontend/public/branding/`

Incluindo:

- `core-logo-light.png`
- `core-logo-dark.png`
- Versões compactas.

O backend deverá utilizar o asset oficial apropriado, garantindo sua disponibilidade no ambiente de produção.

Não depender de uma requisição externa ao frontend para renderizar a marca dentro do PDF.

Não reconstruir a logo usando texto genérico.

Preservar o branding dinâmico da plataforma quando aplicável, utilizando somente assets autorizados e seguros.

### Cabeçalho

Criar um cabeçalho profissional contendo:

- Logo CORE PDV.
- Título do relatório.
- Nome da empresa.
- Nome da filial.
- Período.
- Data e horário da geração.

O nome empresarial deve receber destaque apropriado, pois o relatório pertence à operação daquele cliente.

### Rodapé

Criar um rodapé padronizado com:

- Identificação discreta do CORE PDV.
- Data da geração, quando apropriado.
- Numeração de páginas.
- Separador visual discreto.

Preferencialmente:

`Página X de Y`

Sem ocupar espaço excessivo do documento.

---

## 5. NOVA HIERARQUIA DOS DOCUMENTOS

O documento deverá seguir uma ordem lógica.

### Primeira seção — Identificação

Cabeçalho, título, período e filtros relevantes.

### Segunda seção — Resumo executivo

Apresentar os principais números do relatório.

Por exemplo, em um relatório de vendas:

- Valor bruto.
- Descontos.
- Faturamento.
- Quantidade de vendas.
- Ticket médio.
- Total recebido, quando autorizado.
- Cancelamentos, quando pertinentes.

Esses indicadores deverão ser derivados dos dados oficiais já calculados pelo sistema.

Não criar novos cálculos paralelos.

### Terceira seção — Análise consolidada

Exibir agrupamentos relevantes ao relatório.

Exemplos:

- Vendas por forma de pagamento.
- Desempenho de produtos.
- Resultados por vendedor.
- Vendas por horário.
- Movimentações por categoria.

Mostrar apenas os agrupamentos que realmente pertencem ao relatório solicitado.

### Quarta seção — Detalhamento

Somente quando aplicável ao modo selecionado.

Apresentar tabelas e informações operacionais completas, sem duplicar as seções anteriores.

---

## 6. CORRIGIR AS PÁGINAS EXCESSIVAS

Essa é uma das prioridades da missão.

Investigar especialmente:

- `_structured_sections()`
- `report_key_value_rows()`
- Estruturas passadas pelo parâmetro `summary`.
- Repetições entre `summary` e `rows`.
- Tabelas aninhadas.
- Campos JSON muito extensos.
- Agrupamentos que não pertencem ao relatório solicitado.

### Comportamento desejado

Um relatório executivo de um dia deverá apresentar os principais indicadores e agrupamentos, sem despejar todo o histórico de registros.

Um relatório detalhado deverá manter os registros completos, mas organizar adequadamente as páginas.

Não transformar automaticamente todos os arrays presentes em `summary` em seções do PDF.

Adotar seleção explícita e controlada de seções conforme o tipo de relatório.

### Evitar

- Repetir a mesma informação em três tabelas diferentes.
- Incluir JSON bruto no PDF.
- Criar páginas praticamente vazias.
- Cortar tabelas indevidamente.
- Quebrar títulos dos seus respectivos conteúdos.
- Utilizar espaçamentos exagerados.
- Gerar páginas apenas para pequenos agrupamentos que poderiam estar juntos.
- Diminuir fontes excessivamente para tentar encaixar tudo.

**Não resolver o problema de 90 páginas simplesmente eliminando registros obrigatórios ou limitando a quantidade de linhas.**

---

## 7. TABELAS PROFISSIONAIS

Reformular a apresentação das tabelas PDF.

### Requisitos

- Cabeçalhos legíveis.
- Colunas com larguras proporcionais ao conteúdo.
- Alinhamento à esquerda para descrições.
- Alinhamento à direita para valores financeiros.
- Alinhamento adequado de quantidades e datas.
- Alternância discreta de fundo entre linhas, quando útil.
- Separadores leves.
- Quebra de texto controlada.
- Títulos de colunas repetidos nas páginas seguintes.
- Quebras de página inteligentes.
- Linhas de totais com destaque.
- Ausência de sobreposição de conteúdo.
- Fonte adequada para leitura e impressão.

Não utilizar fontes minúsculas como solução padrão.

### Orientação da página

Preservar A4 como padrão.

Utilizar retrato para relatórios compactos e paisagem quando o conteúdo tabular exigir.

Não definir a orientação exclusivamente pela quantidade de colunas sem considerar suas larguras e conteúdos.

Campos secundários muito extensos poderão ser apresentados em seções complementares, quando isso melhorar a legibilidade e preservar a informação no modo detalhado.

---

## 8. FORMATAÇÃO BRASILEIRA

Padronizar corretamente:

**Moeda:** R$ 1.234,56

**Datas:** 13/10/2026

**Data e hora:** 13/10/2026 às 14:30

**Percentuais:** 10,00%

**Quantidades:** precisão e unidade adequadas ao produto ou indicador.

**Valores negativos:** apresentação consistente.

**Campos inexistentes:** representar como não disponível, e não como zero fictício.

Respeitar o fuso horário da empresa ou filial quando configurado, preservando os critérios de período já implementados.

Garantir suporte adequado a acentos e caracteres da língua portuguesa nos PDFs.

Não converter valores monetários utilizando operações imprecisas de ponto flutuante.

---

## 9. RELATÓRIOS CONTEMPLADOS

A nova estrutura de apresentação deverá ser aplicável aos relatórios do CORE Backoffice.

### Vendas e comercial

- Visão geral.
- Vendas.
- Recebimentos.
- Produtos e desempenho.
- Atendentes.
- Operadores.
- Comissões.
- Descontos.
- Cancelamentos.
- Consumações.

### Financeiro

- Resultado operacional estimado.
- Caixa.
- Sangrias.
- Contas a pagar.

### Estoque e compras

- Posição de estoque.
- Movimentações.
- Consumo e custos.
- Transferências.
- Inventários.
- Compras.
- Fornecedores.
- Preços por filial.

### Operação

- Mesas e comandas.
- Promoções.
- Modificadores.
- Tickets.
- Clientes.

Reutilizar os endpoints e contratos existentes.

Não adicionar métricas que ainda não existam no backend.

Cada relatório deverá apresentar somente indicadores pertinentes à sua finalidade, respeitando os dados e as permissões existentes.

### Prioridade de implementação

Começar pelos relatórios:

1. Visão geral.
2. Vendas.
3. Recebimentos.
4. Caixa.
5. Resultado operacional.

Depois aplicar o mesmo padrão aos demais relatórios, sem duplicar componentes de geração.

---

## 10. MELHORIAS NO EXCEL E CSV

O foco principal é o PDF, mas preservar e organizar as outras exportações.

### Excel

Manter:

- Dados completos.
- Separação lógica entre resumo e dados.
- Nomes de colunas compreensíveis.
- Filtros.
- Congelamento de cabeçalhos.
- Formatação monetária.
- Formatação de datas.
- Valores numéricos utilizáveis em fórmulas.
- Proteção contra fórmulas maliciosas originadas de dados externos.

Realizar apenas ajustes necessários para manter consistência e legibilidade.

### CSV

Preservar:

- Todos os registros autorizados.
- Cabeçalhos.
- Compatibilidade com Excel.
- Codificação adequada.
- Ausência de truncamentos.
- Proteção contra injeção de fórmulas.

Não substituir dados completos do CSV ou Excel por versões executivas.

---

## 11. NOVA EXPERIÊNCIA DE EXPORTAÇÃO NO BACKOFFICE

Revisar:

`frontend/src/components/report-export-action.tsx`

Atualmente, o menu de exportação apresenta PDF, Excel e CSV.

Evoluir esse comportamento para oferecer:

**PDF — Resumo executivo**

**PDF — Relatório detalhado**

**Excel — Dados completos**

**CSV — Dados completos**

### Compatibilidade

Preservar os endpoints existentes.

O parâmetro atual `export=pdf` deverá continuar válido e representar o relatório executivo por padrão.

Introduzir um parâmetro específico para selecionar o detalhamento, por exemplo `pdf_mode`, validado por uma lista explícita de valores permitidos.

Não utilizar esse parâmetro para alterar cálculos ou filtros de negócio.

Quando a exportação em PDF não estiver disponível para determinado relatório, preservar um comportamento consistente e informar a limitação sem inventar dados.

### Interface

- Manter o estilo visual do Backoffice.
- Exibir carregamento durante a exportação.
- Evitar acionamentos duplicados.
- Apresentar erros compreensíveis.
- Manter nomes de arquivos legíveis.
- Preservar os filtros selecionados pelo usuário.
- Respeitar a filial ativa.
- Respeitar a permissão `reports.export`.

---

## 12. SEGURANÇA E MULTIEMPRESA

A exportação precisa manter todas as regras de segurança já existentes.

### Obrigatório

- Isolamento por tenant.
- Isolamento por filial.
- Permissões granulares dos relatórios.
- Autorização de exportação.
- Restrições de custos e margens.
- Restrições de informações financeiras.
- Redação de dados não autorizados antes da renderização.
- Respeito às sessões de suporte CORE.
- Auditoria das exportações.

O mecanismo de PDF deve consumir somente dados já autorizados.

Não implementar atalhos que busquem informações diretamente de outras empresas ou filiais.

Não deixar a geração executiva revelar indicadores derivados que permitam contornar permissões financeiras.

Os dois modos de PDF deverão usar os mesmos critérios de autorização.

---

## 13. DESEMPENHO E CONFIABILIDADE

A geração de PDFs deverá evitar processamento desnecessário.

Investigar especialmente estruturas duplicadas e materializações repetidas de grandes conjuntos de dados.

Preservar paginação e filtragem nas consultas existentes.

Não limitar silenciosamente relatórios detalhados.

Se um relatório ultrapassar os limites operacionais suportados, utilizar tratamento explícito e seguro, sem retornar um documento incompleto apresentado como completo.

Não introduzir dependência obrigatória de serviços externos para gerar PDF.

Garantir que o mecanismo funcione no ambiente de produção, inclusive nos containers Docker utilizados pelo CORE PDV.

---

## 14. RESTRIÇÕES DA MISSÃO

**NÃO criar, modificar ou executar testes automatizados.**

Não adicionar testes Django, frontend, integração ou E2E.

Não iniciar auditoria geral do projeto.

Não alterar cálculos financeiros.

Não alterar as regras de comissões.

Não modificar a lógica de CMV.

Não alterar o estoque ou os saldos.

Não modificar vendas ou pagamentos históricos.

Não alterar o CORE POS.

Não refatorar componentes não relacionados.

Não criar um novo sistema de relatórios paralelo.

Não modificar o dashboard operacional fora do necessário para as exportações.

Não iniciar outra parte da Missão 3.

**Esta missão é exclusivamente sobre a apresentação e a exportação dos relatórios.**

---

## 15. CRITÉRIOS DE CONCLUSÃO

A entrega deverá garantir:

1. PDFs com a identidade visual oficial do CORE PDV.
2. Cabeçalho e rodapé profissionais.
3. Informações corretas da empresa, filial e período.
4. Relatório executivo organizado e compacto.
5. Relatório detalhado completo.
6. Remoção de duplicações desnecessárias.
7. Tabelas legíveis e corretamente paginadas.
8. Formatação monetária e datas brasileiras.
9. Ausência de campos JSON brutos desnecessários no PDF.
10. Preservação dos dados e cálculos originais.
11. CSV e Excel íntegros.
12. Permissões e auditoria preservadas.
13. Interface de exportação clara e integrada.
14. Funcionamento compatível com o ambiente Docker de produção.

---

## 16. ENTREGA FINAL

Apresentar um relatório técnico contendo:

- Diagnóstico das principais causas da paginação excessiva.
- Arquivos modificados.
- Arquitetura adotada para os novos PDFs.
- Como são selecionados os indicadores de cada relatório.
- Funcionamento do modo executivo e detalhado.
- Como a logo oficial foi incorporada.
- Como foram tratadas as tabelas e quebras de página.
- Como foram preservadas as permissões.
- Alterações na interface do Backoffice.
- Eventuais limitações remanescentes.
- Hash do commit.
- Confirmação do push para `main`.

Publicar a implementação na branch `main`.

Não iniciar outra missão após a entrega.

## RESULTADO ESPERADO

O CORE PDV deverá passar a gerar relatórios com aparência de um produto SaaS profissional, utilizando sua identidade visual oficial e oferecendo informações organizadas para empresários, gestores e equipes administrativas.

O relatório executivo deverá apresentar rapidamente os dados essenciais do negócio.

O relatório detalhado deverá preservar a profundidade necessária para conferência e auditoria.

**Nosso objetivo não é apenas reduzir páginas: é transformar os relatórios em uma ferramenta de gestão profissional e confiável, compatível com a identidade e o posicionamento comercial do CORE PDV.**