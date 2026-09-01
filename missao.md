# CORE PDV — AJUSTES FINAIS DE USUÁRIOS, CATEGORIAS, COMPRAS E DASHBOARD
**Data:** 01/09/2026

---

## 1. Usuário existente ativo NÃO deve oferecer restauração

Diferenciar obrigatoriamente três situações.

### A — Usuário/membership ativo na empresa atual

Se o e-mail ou CPF informado já pertence a um usuário **ativo e não soft-deleted naquela empresa**, NÃO oferecer “Restaurar”.

Retornar erro normal de duplicidade, por exemplo:

```text
Já existe um usuário com este e-mail nesta empresa.
```

ou:

```text
Já existe um usuário com este CPF nesta empresa.
```

### B — Usuário/membership soft-deleted na empresa atual

Somente aqui oferecer:

```text
Já existiu um usuário com estes dados. Deseja restaurá-lo?

[ Restaurar usuário ] [ Cancelar ]
```

### C — E-mail e CPF apontam para identidades diferentes

Bloquear e exigir regularização.

Não escolher automaticamente uma identidade.

Criar testes separados para:

- usuário ativo;
- usuário soft-deleted;
- conflito entre identificadores.

---

## 2. “Pode acessar Backoffice?” NÃO pode excluir/desvincular usuário

O campo deve significar exclusivamente:

> **Esta pessoa pode autenticar no Backoffice?**

Ao mudar de **SIM para NÃO**, preservar:

- membership da empresa;
- filiais;
- perfil/cargo;
- comissão;
- vínculos operacionais;
- vendas e histórico;
- futura utilização como operador POS.

Não fazer:

- archive;
- `UserCompanyAccess.is_active = false`;
- apagar `branch_accesses`;
- limpar perfil;
- remover a pessoa da empresa.

O usuário simplesmente deixa de poder fazer login no Backoffice.

Idealmente o acesso ao Backoffice deve ser **company-scoped**, e não uma propriedade global capaz de afetar outra empresa.

### Cenário obrigatório

```text
Rayara
Empresa: 25 Lounge
Filial: Pavuna
Perfil: Garçom
Pode acessar Backoffice: SIM
```

Ao desmarcar:

```text
Pode acessar Backoffice: NÃO
```

Resultado esperado:

- continua pertencendo à 25 Lounge;
- continua na Pavuna;
- continua com perfil Garçom;
- continua ativa operacionalmente;
- não consegue autenticar no Backoffice.

Ao marcar novamente:

- habilita acesso ao Backoffice;
- preserva filial;
- preserva perfil;
- preserva histórico.

---

## 3. Usuário soft-deleted deve poder ser restaurado

Quando um usuário tiver sido apagado por soft-delete e depois houver tentativa de cadastro com os mesmos identificadores fortes, oferecer restauração.

Identificadores fortes:

- e-mail normalizado;
- CPF, quando informado.

Exemplo:

```text
Já existiu um usuário com estes dados.

Rayara
E-mail: rayara@email.com
Excluído em: 28/08/2026

[ Restaurar usuário ]
[ Cancelar ]
```

Ao restaurar:

- preservar a mesma identidade;
- preservar histórico;
- restaurar somente o membership da empresa atual;
- não afetar vínculos com outras empresas;
- não restaurar automaticamente acessos indevidos;
- permitir configurar novamente se poderá acessar o Backoffice;
- registrar auditoria.

### Multiempresa

```text
Rayara
├── 25 Lounge     EXCLUÍDA
└── Supermarket   ATIVA
```

Restaurar na 25 Lounge não deve interferir no Supermarket.

---

## 4. Produto soft-deleted — restaurar registro existente

Aplicar a mesma filosofia usada para usuário apagado.

Cenário:

```text
Criar produto "Coca"
→ soft-delete
→ tentar cadastrar "Coca" novamente
```

Resultado esperado:

```text
Já existiu um produto chamado "Coca".

Produto excluído em: 28/08/2026

[ Restaurar produto ]
[ Cancelar ]
```

Não retornar simplesmente:

```text
Já existe um produto com este nome nesta empresa.
```

Não criar automaticamente outro produto com identidade diferente.

Ao restaurar:

- preservar o mesmo Product ID;
- preservar histórico de vendas;
- preservar histórico de compras;
- preservar movimentações de estoque;
- preservar auditoria;
- validar conflitos atuais de nome;
- validar código interno;
- validar SKU;
- validar código de barras;
- validar demais identificadores únicos.

Se algum identificador tiver sido reutilizado por outro produto ativo, bloquear a restauração e informar o conflito.

---

## 5. Produto restaurado deve redirecionar para `/produtos`

Após clicar em **Restaurar produto** e concluir com sucesso:

- fechar modal;
- mostrar feedback de sucesso;
- redirecionar para:

```text
/produtos
```

Não permanecer em:

```text
/produtos/novo
```

nem deixar o formulário antigo aberto.

---

## 6. Produto usado em composição não pode ser apagado

Antes do soft-delete verificar:

- composição comum;
- composição fracionada.

Se o produto estiver sendo utilizado em qualquer composição ativa, bloquear.

Mensagem esperada:

```text
Este produto é utilizado na composição de “Combo X”.
Remova-o da composição antes de excluir.
```

Se estiver usado em várias composições, informar as dependências ou quantidade.

Após remover das composições, permitir o soft-delete.

---

## 7. Reorder de categorias com soft-delete

Bug reproduzido:

```text
Informe exatamente todas as categorias da empresa, sem repeticao.
```

Depois a UI informa que a ordem anterior foi restaurada.

A validação de reorder deve considerar somente categorias atuais da filial:

```text
branch = filial atual
AND
deleted_at IS NULL
```

A lista enviada pelo frontend e a lista validada pelo backend precisam possuir exatamente o mesmo escopo.

### Teste obrigatório

```text
Criar categorias:
A
B
C

Soft-delete B

Reordenar:
C
A
```

Resultado esperado:

```text
200 OK
```

Sem exigir a categoria B apagada.

---

## 8. Categorias — propagação deve considerar somente produtos operacionais

A propagação deve afetar e contar somente produtos operacionais válidos da filial.

Não incluir:

- produtos soft-deleted;
- produtos inativos;
- produtos indisponíveis.

Conjunto esperado:

```text
Product.archived_at IS NULL
AND
Product.status = ACTIVE
AND
ProductBranchConfig.is_available = TRUE
AND
ProductBranchConfig.branch = filial atual
AND
ProductBranchConfig.category = categoria atual
```

Exemplo:

```text
3 produtos ativos/disponíveis
2 produtos soft-deleted
1 produto indisponível
```

Resultado obrigatório:

```text
3/3 produtos alterados
```

Não:

```text
6/6
```

Usar selector/queryset central, evitando duplicação de regra.

---

## 9. Configuração efetiva do produto deve respeitar a filial

Quando existe `ProductBranchConfig` da filial atual, a tela de produto deve mostrar os valores efetivos daquela filial.

Inclui:

- categoria;
- `available_counter`;
- `available_table`;
- `available_command`;
- `participates_in_service_fee`;
- `participates_in_commission`;
- demais propriedades branch-scoped.

Exemplo:

```text
Pavuna
Taxa de serviço = FALSE

Beira-Mar
Taxa de serviço = TRUE
```

Abrir produto na Pavuna:

```text
FALSE
```

Abrir na Beira-Mar:

```text
TRUE
```

Salvar Pavuna não pode alterar Beira-Mar.

Auditoria de `ProductBranchConfig` deve registrar também taxa e comissão no before/after.

---

## 10. `/compras/nova` — preço unitário continua editável

O preço unitário não pode ser somente resultado visual.

O usuário deve poder preencher qualquer um dos dois campos.

### Modo A — preço da apresentação

```text
Unidade de compra: PCT com 10 UN
Preço PCT: R$ 30,00
```

Resultado:

```text
Preço unitário: R$ 3,00
```

### Modo B — preço unitário

```text
Unidade de compra: PCT com 10 UN
Preço unitário: R$ 3,00
```

Resultado:

```text
Preço PCT: R$ 30,00
```

Os dois campos devem ser inputs editáveis e sincronizados.

Recomendação de estado frontend:

```text
presentationPrice
baseUnitPrice
lastEditedPriceField
```

Evitar loops de atualização e erros de arredondamento.

Manter precisão interna alta e usar duas casas apenas na apresentação monetária.

### Testes obrigatórios

```text
30 / 10 = 3
3 × 10 = 30
12 × 2,50 = 30
0.234423 → R$ 0,23 na UI
```

Subtotal e custo efetivo devem permanecer corretos.

---

## 11. Dashboard do Backoffice — simplificar de verdade

O dashboard atual concentra informação demais e funciona como:

```text
Dashboard
+
Relatório financeiro
+
Rankings
+
Estoque
+
BI
```

A Home deve responder em aproximadamente 10 segundos:

- Quanto vendi?
- Quantas vendas?
- Qual meu ticket médio?
- Qual resultado?
- Existe algum problema agora?
- O que está vendendo?

### Estrutura desejada

#### Topo

```text
Hoje | 7 dias | 30 dias | Personalizado
```

#### 4 KPIs principais

```text
Faturamento
Vendas
Ticket médio
Resultado estimado
```

#### Atenção operacional

Mostrar somente alertas relevantes e acionáveis, por exemplo:

- caixa aberto;
- estoque negativo;
- produtos abaixo do mínimo;
- outras exceções reais.

#### Um gráfico principal

```text
Vendas no período
```

Não colocar diversos gráficos competindo pela atenção.

#### Blocos secundários

```text
Top 5 produtos
Formas de pagamento
Últimas 5 vendas
```

### Mover para Relatórios / “Ver detalhes”

- mapa de calor;
- ranking completo de vendedores;
- ranking de operadores;
- cancelamentos detalhados;
- descontos detalhados;
- consumação detalhada;
- composição financeira detalhada;
- CMV/custos detalhados;
- demais análises extensas.

Não apagar essas informações do sistema.

Apenas removê-las da Home e direcionar para a área apropriada.

---

## 12. Dashboard — corrigir período personalizado

O botão:

```text
Personalizado
```

deve realmente:

- abrir seleção de data inicial/final;
- aplicar o range;
- atualizar os dados;

ou ser removido enquanto não houver funcionalidade.

Não manter botão visual sem ação.

---

## 13. Dashboard — não duplicar filtro de filial

A filial já é definida pelo seletor global do CORE.

Não mostrar novamente um campo de filial desabilitado no dashboard apenas para repetir contexto.

O dashboard deve usar automaticamente:

```text
currentCompany
+
currentBranch
```

---

## 14. Regra de estados de usuário

Não tratar estes conceitos como iguais:

### Usuário operacional ativo

Pessoa vinculada à empresa/filial e utilizada pela operação.

### Sem acesso ao Backoffice

Pessoa continua ativa operacionalmente, mas não pode autenticar no Backoffice.

### Inativo

Vínculo temporariamente desativado segundo regra operacional própria.

### Soft-deleted

Registro removido da operação atual, preservado somente para histórico/restauração.

Esses estados precisam ser representados separadamente.

---

# TESTES OBRIGATÓRIOS

Antes de considerar concluído, adicionar regressões para:

### Usuários

- usuário ativo duplicado → erro de duplicidade, sem modal Restaurar;
- usuário soft-deleted → modal Restaurar;
- e-mail/CPF conflitantes → bloquear;
- desligar Backoffice → preserva membership;
- desligar Backoffice → preserva filial;
- desligar Backoffice → preserva perfil;
- desligar Backoffice → impede apenas login;
- ligar novamente → preserva vínculos;
- multiempresa → alterar Empresa A não afeta Empresa B.

### Produtos

- Coca ativa + novo cadastro Coca → erro de duplicidade;
- Coca soft-deleted + novo cadastro Coca → modal Restaurar;
- restaurar → mantém mesmo Product ID;
- restaurar → redireciona `/produtos`;
- componente comum em uso → bloqueia exclusão;
- componente fracionado em uso → bloqueia exclusão;
- remover composição → permite excluir.

### Categorias

- reorder após soft-delete;
- propagação ignora arquivados;
- propagação ignora inativos;
- propagação ignora indisponíveis;
- quantidade apresentada é igual ao conjunto realmente alterado.

### Compras

- preço apresentação → unitário;
- preço unitário → apresentação;
- valores fracionários;
- arredondamento visual;
- subtotal correto.

### Dashboard

- Hoje;
- 7 dias;
- 30 dias;
- Personalizado;
- sem botão morto;
- Branch vem do seletor global;
- informações detalhadas continuam disponíveis em Relatórios.

---

# Critério de conclusão

Não considerar concluído apenas porque a interface mudou.

Para cada item:

```text
CORRIGIDO
PARCIAL
NÃO CORRIGIDO
```

Informar:

- arquivos alterados;
- migrations criadas;
- testes adicionados;
- resultado da suíte;
- resultado do CI;
- possíveis riscos/regressões.
