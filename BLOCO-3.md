<role>
Evolua exclusivamente a experiência operacional de ESTOQUE do CORE PDV.

Preserve o domínio e a fonte de verdade já existentes:
StockMovement continua sendo a base histórica do estoque.
</role>

<tasks>

1. /estoque COMO COCKPIT

Remova a navegação operacional fragmentada que hoje separa excessivamente:

- Visão geral;
- Movimentações;
- Transferências;
- Divergências;
- Perdas;
- Inventário.

Transforme /estoque na página operacional principal.

Ações principais:

- Entrada em grupo;
- Nova transferência;
- Nova contagem;
- Histórico.

Sempre respeitando RBAC/Feature/Branch.

---

2. TRANSFERÊNCIA

Exibir "Nova transferência" quando existirem PELO MENOS 2 Branches ativas e acessíveis da mesma Company.

Duas filiais já são suficientes.

---

3. HISTÓRICO

Use Histórico como consulta de movimentações.

Não mantenha outra aba redundante fazendo a mesma coisa.

Preserve filtros úteis.

---

4. DIVERGÊNCIAS

Remover da navegação operacional principal.

A consulta analítica será:

Relatórios → Estoque → Divergências.

Não remova regras/services necessários para tratamento das divergências.

---

5. NOVA CONTAGEM

Implementar dois modos:

CONTAGEM COMPLETA:
- todos os produtos controlados em estoque da Branch;
- incluir produtos com saldo zero;
- agrupar por Categoria;
- busca/filtro;
- campos de contagem diretamente na lista.

CONTAGEM PARCIAL:
- selecionar apenas os produtos desejados.

---

6. OBSERVAÇÃO

Observação geral de InventoryCount deve ser opcional.

Atualize:
- model quando necessário;
- serializer;
- service;
- frontend;
- migration.

Preserve registros antigos.

---

7. UNIDADE CANÔNICA / CONTEÚDO

Para produto rastreado por embalagem + residual:

se embalagens completas estiver preenchido e residual estiver vazio:
→ interpretar residual como 0.

Não exigir que usuário digite zero.

Continue rejeitando valores inválidos.

---

8. REVISÃO ANTES DA CAPTURA

Preserve snapshot imutável depois da captura.

Fluxo desejado:

Contagem
→ Revisão
→ usuário pode voltar e editar
→ Capturar
→ InventoryCount imutável
→ Confirmar inventário.

Não permita editar snapshot já persistido/capturado apenas para suportar "Voltar".
</tasks>

<task>
9. CORES

Na revisão/detalhe:

Contado < teórico
→ vermelho / falta.

Contado = teórico
→ verde / correto.

Contado > teórico
→ amarelo / sobra.

Use cores semânticas do design system.
</task>

<task>
10. PERDAS

LossRecord continua existindo no domínio.

Não remova sua modelagem.

Mas a entrada operacional deve ser integrada a:

Movimentação → Saída → Natureza: Perda.

Quando perda:

- motivo obrigatório;
- quantidade/conteúdo;
- foto opcional;
- observação opcional.

Não mantenha dois fluxos concorrentes para registrar a mesma perda.
</task>

<task>
11. FOTO

Adicionar foto/anexo opcional à perda.

Use armazenamento seguro já existente ou a abstração adequada do projeto.

NÃO grave base64 no banco.

Valide acesso por Company/Branch.

Não exponha arquivo privado sem autorização.
</task>

<task>
12. MOTIVO / OBSERVAÇÃO

Motivo estruturado continua obrigatório.

Observação passa a ser opcional.

Se motivo = OTHER:
exija descrição suficiente para preservar auditabilidade.
</task>

<validation>
Crie/atualize testes para:

- contagem completa;
- saldo zero;
- parcial;
- residual vazio=0;
- imutabilidade;
- divergências;
- perdas;
- attachment scope;
- cross-tenant;
- RBAC.

Execute testes direcionados + lint/build das telas alteradas.
</validation>

<rules>
- Não redesenhar Inventory engine.
- Não mudar fonte da verdade do estoque.
- Não alterar regras de Sales/Commands.
- Não fazer commit.
- Não avançar para BLOCO 4.
</rules>

<final_response>
Informe mudanças, migrations, testes e eventuais riscos.

Finalize:
BLOCO 3 APROVADO
ou
BLOCO 3 NÃO APROVADO.
</final_response>