## AJUSTES ADICIONAIS — SOFT DELETE / RESTAURAÇÃO / PROPAGAÇÃO DE CATEGORIA

### 1. USUÁRIO APAGADO — RESTAURAR, NÃO CRIAR OUTRO

Quando um usuário tiver sido apagado por soft-delete e depois for realizado um novo cadastro com dados que identifiquem a mesma pessoa, o sistema não deve simplesmente retornar:

> E-mail já existe.

O backend deve detectar que existe uma identidade/membership soft-deleted compatível e retornar um conflito estruturado.

Exemplo:

```text
Já existiu um usuário com estes dados.

Rayara
E-mail: rayara@email.com
Excluído em: 28/08/2026

[ Restaurar usuário ]
[ Cancelar ]
```

Usar como identificadores fortes:

* e-mail normalizado;
* CPF, quando informado.

Para e-mail/CPF iguais, NÃO criar outra identidade global.

O comportamento esperado é restaurar/revincular o registro existente.

Ao restaurar:

* remover soft-delete do membership correspondente;
* preservar histórico;
* preservar ID da identidade;
* restaurar somente os vínculos apropriados da empresa atual;
* não expor informações de outras empresas;
* não restaurar automaticamente permissões indevidas;
* perguntar/configurar novamente se poderá acessar o Backoffice;
* registrar auditoria.

Em cenário multiempresa:

```text
Rayara
├── 25 Lounge     EXCLUÍDA
└── Supermarket   ATIVA
```

Restaurar na 25 Lounge não deve interferir no vínculo ativo do Supermarket.

Criar testes:

```text
criar usuário
→ soft-delete na empresa A
→ tentar criar com mesmo e-mail/CPF
→ archived_user_exists
→ restaurar
→ membership da empresa A volta
→ outra empresa permanece intacta
```

---

### 2. PRODUTO APAGADO — MESMA REGRA DE RESTAURAÇÃO DO USUÁRIO

Aplicar ao produto a mesma filosofia usada para usuário soft-deleted.

Cenário:

```text
Criar produto "Coca"
→ apagar via soft-delete
→ tentar cadastrar novamente "Coca"
```

Não retornar simplesmente:

> Já existe um produto com este nome nesta empresa.

E não criar automaticamente outro produto com identidade diferente.

O comportamento esperado é:

```text
Já existiu um produto chamado "Coca".

Produto excluído em: 28/08/2026

[ Restaurar produto ]
[ Cancelar ]
```

Neste fluxo, remover a opção padrão de:

```text
[ Criar novo ]
```

quando os identificadores caracterizarem claramente o mesmo produto.

Objetivo:

* preservar o mesmo ID;
* preservar histórico de vendas;
* preservar histórico de compras;
* preservar movimentações de estoque;
* preservar auditoria;
* evitar múltiplas identidades históricas para o mesmo produto.

Ao restaurar, validar conflitos atuais de:

* nome;
* código interno;
* SKU;
* código de barras;
* demais identificadores únicos.

Se algum identificador tiver sido reutilizado por outro produto ativo, retornar mensagem clara informando o conflito e impedir restauração até regularização.

O backend deve retornar código estruturado, por exemplo:

```text
archived_product_exists
```

e o frontend deve abrir o modal de restauração.

Criar teste completo de integração:

```text
POST Coca
→ archive endpoint
→ confirmar archived_at
→ POST Coca novamente
→ archived_product_exists
→ frontend abre modal
→ Restaurar
→ mesmo Product ID volta a ficar ativo
```

Também corrigir mensagens duplicadas como:

```text
Já existe um produto com este nome nesta empresa.
Já existe um produto com este nome nesta empresa.
```

A mensagem deve aparecer somente uma vez.

---

### 3. CATEGORIAS — PROPAGAÇÃO DEVE IGNORAR PRODUTOS APAGADOS/INOPERANTES

A listagem/contador normal da categoria já está filtrando corretamente produtos ativos/não arquivados.

Porém a função de propagação ainda precisa seguir exatamente a mesma regra.

Hoje `apply_config_to_products()` pode considerar todos os `ProductBranchConfig` vinculados à categoria e, consequentemente, incluir:

* produtos soft-deleted;
* produtos inativos;
* produtos indisponíveis na filial.

Isso gera situações como:

```text
Produtos realmente operacionais: 3
Resultado da propagação: 6/6
```

O resultado correto deve ser:

```text
3/3 produtos alterados
```

A propagação deve afetar apenas:

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

Preferir reutilizar selector/queryset central de produtos operacionais em vez de recriar manualmente os filtros.

A mesma coleção de produtos deve ser usada para:

* contar quantos produtos serão alterados;
* aplicar a alteração;
* retornar `total_products`;
* retornar `updated_products`.

Adicionar teste com:

```text
3 produtos ativos/disponíveis
2 produtos soft-deleted
1 produto indisponível
```

Resultado obrigatório:

```text
total_products = 3
updated_products = 3
```

Também testar que nenhuma configuração dos produtos excluídos/inativos/indisponíveis foi alterada.

---

### 4. REGRA GERAL DE SOFT DELETE

A partir desta correção, usar a seguinte regra de domínio:

> Soft-delete significa que o registro desaparece da operação atual, mas sua identidade e histórico continuam existindo.

Quando um novo cadastro corresponder claramente a um registro soft-deleted:

```text
detectar registro existente
→ oferecer restauração
→ preservar identidade/histórico
```

Não tratar soft-delete como se o registro nunca tivesse existido.

Aplicar esse princípio de forma consistente em:

* usuários;
* produtos;
* fornecedores;
* categorias;

sempre respeitando as particularidades e constraints de cada domínio.

Não considerar concluído apenas pelo comportamento visual.

Adicionar testes backend e frontend para os fluxos de detecção e restauração.
