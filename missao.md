# CORE PDV — AJUSTES MANUAIS DESTA RODADA
**Data:** 01/09/2026

## IMPORTANTE — NÃO EXECUTAR TESTES AUTOMATIZADOS

Para economizar créditos e tempo de execução, nesta rodada:

**NÃO executar:**
- testes Django;
- suíte backend completa;
- testes frontend;
- Playwright;
- Vitest/Jest;
- `npm test`;
- `npm run build`;
- `npm audit`;
- `pip-audit`;
- CI/GitHub Actions;
- scans extensos;
- Docker builds.

Fazer apenas:
- revisão do código alterado;
- implementação das correções;
- validações estáticas simples quando necessárias;
- testes manuais dos fluxos descritos.

Ao finalizar, informar:
- arquivos alterados;
- migrations criadas;
- resumo das correções;
- lista dos testes manuais que devo executar.

---

# 1. RESTAURAÇÃO DE USUÁRIO SOFT-DELETED

O fluxo ainda está falhando no ambiente real.

Cenário:

```text
ray@corepdv.com
→ usuário pertence à empresa
→ usuário é apagado via soft-delete
→ tentar cadastrar novamente ray@corepdv.com
```

Resultado atual incorreto:

```text
Já existe um usuário com este e-mail nesta empresa.
```

Resultado esperado:

```text
Já existiu um usuário com estes dados.

[ Restaurar usuário ]
[ Cancelar ]
```

## Regra obrigatória

### Usuário ATIVO na empresa atual

Se o membership atual tem:

```text
archived_at IS NULL
```

retornar duplicidade normal:

```text
Já existe um usuário com este e-mail nesta empresa.
```

ou:

```text
Já existe um usuário com este CPF nesta empresa.
```

NÃO mostrar restauração.

### Usuário SOFT-DELETED na empresa atual

Se o membership tem:

```text
archived_at IS NOT NULL
```

retornar conflito estruturado equivalente a:

```text
archived_user_exists
```

e abrir modal de restauração.

Revisar o fluxo completo:

```text
archive endpoint
→ UserCompanyAccess.archived_at
→ nova tentativa de cadastro
→ detecção do membership arquivado
→ archived_user_exists
→ modal frontend
```

Não enfraquecer a validação de duplicidade ativa para fazer o modal aparecer.

---

# 2. RESTAURAÇÃO DE USUÁRIO DEVE SER COMPANY-SCOPED

Cenário:

```text
Rayara
├── 25 Lounge     SOFT-DELETED
└── Supermarket   ATIVA
```

Ao restaurar na 25 Lounge:

- restaurar somente o membership da 25 Lounge;
- não alterar o Supermarket;
- preservar a mesma identidade global;
- preservar histórico;
- não revelar dados da outra empresa.

---

# 3. ACESSO AO BACKOFFICE NÃO É MEMBERSHIP OPERACIONAL

Manter separados:

```text
Pessoa pertence à empresa
Pessoa pertence à filial
Pessoa possui perfil/cargo
Pessoa pode acessar Backoffice
```

Exemplo correto:

```text
Rayara
Empresa: 25 Lounge
Filial: Pavuna
Perfil: Garçom
Pode acessar Backoffice: NÃO
```

Resultado:

- continua na empresa;
- continua na filial;
- continua com perfil;
- continua elegível para vendas/comissões/operações;
- apenas não consegue autenticar no Backoffice.

Desligar Backoffice NÃO pode:
- arquivar usuário;
- desativar membership;
- remover filial;
- remover perfil;
- zerar comissão.

---

# 4. REVISAR `eligible_branch_users()`

Separar definitivamente:

```text
elegível operacionalmente
```

de:

```text
autorizado a entrar no Backoffice
```

Funcionário sem Backoffice pode continuar sendo:

- vendedor;
- garçom;
- comissionado;
- responsável por operação;
- futuramente operador POS.

Revisar os callers de `eligible_branch_users()` para não excluir usuários operacionais apenas porque não possuem acesso ao Backoffice.

---

# 5. PRODUTO SOFT-DELETED — MESMA FILOSOFIA

### Produto ativo

Se já existe Coca ativa:

```text
Já existe um produto com este nome nesta empresa.
```

NÃO oferecer restauração.

### Produto soft-deleted

Se Coca foi apagada:

```text
Já existiu um produto chamado "Coca".

[ Restaurar produto ]
[ Cancelar ]
```

A restauração deve preservar:

- mesmo Product ID;
- histórico;
- vendas;
- compras;
- estoque;
- auditoria.

Depois da restauração:

```text
redirecionar para /produtos
```

---

# 6. DASHBOARD — MELHORAR “ATENÇÃO OPERACIONAL”

Manter o dashboard simplificado.

Não voltar a encher a Home de relatórios e rankings.

Adicionar na área de atenção, somente quando o valor for maior que zero:

## Críticos

```text
Estoque negativo
Divergência de pagamentos
```

## Atenção

```text
Estoque zerado
Produtos abaixo do mínimo
```

## Informação operacional

```text
Mesas abertas
Comandas abertas
Caixas abertos
```

Exemplo:

```text
ATENÇÃO OPERACIONAL

🔴 2 produtos com estoque negativo
🔴 R$ 32,00 de divergência de pagamentos

🟠 5 produtos com estoque zerado
🟠 7 produtos abaixo do mínimo

🔵 8 mesas abertas
🔵 11 comandas abertas
🔵 2 caixas abertos
```

Regras:
- não mostrar item com valor zero;
- vermelho = crítico;
- amarelo/laranja = atenção;
- azul/neutro = informação operacional;
- mesa aberta não é erro;
- manter a área compacta;
- no máximo aproximadamente 6–7 itens relevantes.

---

# 7. MESAS E COMANDAS NO DASHBOARD

Usar sempre a filial selecionada globalmente.

### Mesas abertas

Contar mesas distintas com operação/comanda aberta na filial atual.

### Comandas abertas

Contar comandas com status aberto na filial atual.

Não misturar dados de outras filiais.

Respeitar as permissões existentes.

---

# 8. ESTOQUE ZERADO NO DASHBOARD

Usar o indicador já existente de estoque zerado.

Regra:

```text
zero_count > 0
```

→ mostrar em Atenção Operacional.

Não criar consulta duplicada desnecessária.

Produtos soft-deleted não entram nesse indicador atual.

---

# 9. NÃO VOLTAR A SOBRECARREGAR O DASHBOARD

Manter a Home focada em:

```text
4 KPIs principais
+
Atenção operacional
+
1 gráfico principal
+
Top 5 produtos
+
Formas de pagamento
+
Últimas vendas
```

Continuar deixando em Relatórios:

- mapa de calor;
- ranking completo de vendedores;
- ranking completo de operadores;
- descontos detalhados;
- cancelamentos detalhados;
- composição financeira detalhada;
- CMV detalhado;
- análises extensas.

---

# 10. VALIDAÇÃO MANUAL

NÃO rodar testes automatizados.

Depois da implementação, estes cenários serão testados manualmente.

## Usuário

```text
1. Criar usuário A.
2. Soft-delete.
3. Tentar criar com mesmo e-mail.
4. Deve oferecer Restaurar.

5. Criar usuário B ativo.
6. Tentar criar novamente com mesmo e-mail.
7. Deve dizer que já existe.
8. NÃO oferecer Restaurar.
```

## Multiempresa

```text
Usuário em Empresa A e Empresa B.
Soft-delete somente em A.
B continua intacta.
Restaurar em A.
B continua intacta.
```

## Backoffice

```text
Desligar acesso ao Backoffice.
Usuário continua na empresa/filial/perfil.
Login Backoffice deixa de funcionar.
```

## Produto

```text
Coca ativa → nova Coca = duplicidade.
Coca soft-deleted → nova Coca = oferecer restauração.
Restaurar → voltar para /produtos.
```

## Dashboard

Validar visualmente:

```text
estoque negativo
estoque zerado
abaixo do mínimo
mesas abertas
comandas abertas
caixas abertos
divergência de pagamentos
```

Itens com valor zero não devem aparecer.

---

# CRITÉRIO DE CONCLUSÃO

Nesta rodada NÃO executar suíte automatizada.

Ao finalizar, responder apenas:

```text
1. CORRIGIDO / PARCIAL / NÃO CORRIGIDO
2. Arquivos modificados
3. Migration criada, se houver
4. Decisões de arquitetura tomadas
5. Lista curta de testes manuais que devo executar
```

Não iniciar o POS.
Não iniciar o Platform Admin.
Não ampliar escopo além destes pontos.
