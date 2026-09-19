# CORE PDV — Correção e Finalização do Fluxo de Pagamentos do Novo Módulo de Mesas

CORRIJA E FINALIZE O FLUXO DE PAGAMENTOS DO NOVO MÓDULO DE MESAS.

PARTA DO HEAD ATUAL DA MAIN.

O ÚLTIMO COMMIT IMPLEMENTOU A BASE DE PAGAMENTOS DE MESA, MAS A AUDITORIA DO CÓDIGO ENCONTROU PENDÊNCIAS FUNCIONAIS E DE RBAC QUE BLOQUEIAM O USO REAL.

IMPORTANTE:

- NÃO iniciar Stone/Cielo/PagBank.
- NÃO mexer em Comanda legado.
- NÃO recriar o motor financeiro.
- NÃO duplicar lógica financeira no Flutter.
- NÃO remover idempotência.
- NÃO alterar estoque/produção/impressão/fiscal fora do necessário.
- NÃO criar nova bateria de testes automatizados.
- O teste funcional final será feito manualmente.
- Corrija somente o necessário para fechar MESAS + PAGAMENTOS.

---

## 1. BLOQUEADOR PRINCIPAL: ACESSO À TELA DE PAGAMENTO

Hoje existe botão de pagamento no `TableOrderPage`, mas ele depende de:

`tables.payments.view`

A implementação atual faz algo equivalente a:

```dart
onPressed:
    !_can('tables.payments.view')
        ? null
        : _openPayments
```

O problema é que as migrations das permissões de Mesa adicionaram as permissões novas praticamente somente ao perfil:

`Administrador`

Por isso perfis operacionais como:

- Gerente
- Operador de Caixa

podem não conseguir sequer abrir a tela de pagamentos.

CORRIGIR O RBAC PADRÃO.

---

## 2. PERMISSÕES PADRÃO DE MESAS

Atualizar os perfis SISTEMA padrão e criar migration/data migration segura para os perfis já existentes.

### ADMINISTRADOR

Continua com todas as permissões de Mesa.

### GERENTE

Deve possuir por padrão:

- `tables.view`
- `tables.open`
- `tables.set_customer`
- `tables.add_items`
- `tables.cancel_items`
- `tables.payments.view`
- `tables.payments.record`
- `tables.payments.reverse`
- `tables.transfer`
- `tables.transfer_items`
- `tables.merge`
- `tables.close`

Não precisa necessariamente receber `tables.manage` se isso continuar sendo administração estrutural/configuração.

### OPERADOR DE CAIXA

Deve possuir por padrão:

- `tables.view`
- `tables.open`
- `tables.set_customer`
- `tables.add_items`
- `tables.payments.view`
- `tables.payments.record`
- `tables.close`

NÃO adicionar por padrão ao Operador:

- `tables.payments.reverse`
- `tables.transfer`
- `tables.transfer_items`
- `tables.merge`
- `tables.manage`

Estorno continua usando autorização por PIN quando o operador não possui a permissão.

NÃO simplesmente adicionar todas as permissões para todo mundo.

Preservar RBAC granular.

---

## 3. EXISTING TENANTS / PERFIS JÁ CRIADOS

Não basta alterar apenas `DEFAULT_PROFILE_PERMISSIONS`.

Criar migration/data migration idempotente para atualizar os perfis SISTEMA já existentes.

Não sobrescrever customizações de perfis personalizados.

A alteração deve atingir somente os perfis padrão `is_system=True` correspondentes.

---

## 4. CORRIGIR DÉBITO / CRÉDITO NO GRID

BUG CONFIRMADO.

O backend retorna:

```text
cash        → visual_group= cash / kind=cash
pix         → visual_group= pix  / kind=pix
credit_card → visual_group= card / kind=credit
debit_card  → visual_group= card / kind=debit
VA/VR       → visual_group= card / kind=benefit
```

Mas `TablePaymentPage` atualmente classifica somente `visualGroup`.

Resultado:

Crédito e Débito caem em `OUTROS`.

CORRIGIR para usar a mesma regra da Venda Rápida.

Resultado esperado:

```text
[ DINHEIRO ] [ DÉBITO  ]
[ PIX      ] [ CRÉDITO ]
[ OUTROS, se existir ]
```

Use:

- `kind`
- `visualGroup`
- `code`

de forma consistente.

Não hardcodar IDs.

VA/VR/benefícios/customizados ficam em `OUTROS`.

---

## 5. MESA E VENDA RÁPIDA DEVEM USAR A MESMA CLASSIFICAÇÃO

Não manter duas regras diferentes para agrupar formas de pagamento.

Extrair/reutilizar uma função/abstração compartilhada para determinar:

- Dinheiro
- Débito
- PIX
- Crédito
- Outros

Assim, quando uma classificação mudar, muda nos dois fluxos.

---

## 6. ESTADO INCERTO / PENDING PAYMENT

Hoje Mesa mantém `_pending` quando um pagamento falha ou fica incerto.

Isso é bom.

Mas existe um problema:

ENQUANTO `_pending != null`, ainda é possível iniciar outro pagamento.

ISSO NÃO PODE ACONTECER.

Quando existir pagamento pendente/incerto:

desabilitar:

- Dinheiro
- Débito
- PIX
- Crédito
- Outros
- Dividir
- Pagar por itens
- qualquer novo pagamento

Deixar disponível somente:

- TENTAR NOVAMENTE
- ATUALIZAR / RECONCILIAR

---

## 7. RECONCILIAÇÃO DO PENDING

Ao atualizar a tela com `_pending != null`:

carregar:

`tablePaymentLedger(attendanceId)`

e procurar se já existe pagamento com:

`idempotency_key == pending.idempotencyKey`

Se existir:

- considerar a tentativa confirmada;
- limpar `_pending`;
- atualizar resumo;
- não reenviar pagamento.

Se não existir:

- manter pending;
- permitir retry usando A MESMA idempotency key.

NUNCA gerar nova chave para retry da mesma tentativa.

---

## 8. PERSISTÊNCIA DE ESTADO INCERTO

Analisar o comportamento atual em fechamento/reabertura da tela.

Se `_pending` existir apenas em memória e puder ser perdido ao sair do app/tela após timeout, implementar persistência mínima equivalente ao padrão robusto da Venda Rápida.

Precisamos evitar:

```text
timeout
↓
app fecha
↓
operador abre novamente
↓
não sabe se pagamento foi realizado
↓
registra outro
```

O backend continua sendo a fonte da verdade.

---

## 9. PAGAR POR ITENS PRECISA DE PREVIEW OFICIAL

Hoje o usuário seleciona itens e a UI apenas diz:

> O valor dos itens será calculado oficialmente pela Mesa.

Isso não é suficiente.

Fluxo correto:

```text
PAGAR POR ITENS
↓
seleciona itens/quantidades
↓
BACKEND calcula valor oficial
↓
UI mostra:
VALOR DOS ITENS
R$ XX,XX
↓
seleciona/confirma forma
```

NÃO calcular valor financeiro no Flutter.

Criar/reutilizar endpoint de preview de pagamento por itens, usando a MESMA lógica interna de:

`_table_allocation_amount()`

sem persistir pagamento.

Não duplicar cálculo.

---

## 10. PREVIEW DE ITENS DEVE CONSIDERAR

O valor oficial precisa considerar:

- preço congelado;
- modificadores;
- promoções;
- desconto por item;
- desconto da conta;
- taxa de serviço;
- quantidades já pagas;
- alocações existentes;
- quantidade disponível restante.

Apenas backend decide o valor.

---

## 11. DIVIDIR IGUAL

Hoje Mesa possui backend com:

- `equal_split`
- `next_person`
- `next_amount`
- `paid_people`
- `remaining_people`
- `people_count`

A UI precisa usar isso.

Ao tocar:

`DIVIDIR IGUAL`

mostrar algo como:

```text
DIVIDIR IGUAL

Pessoa 2 de 4

VALOR DA PARTE
R$ 25,00

[ DINHEIRO ] [ DÉBITO ]
[ PIX      ] [ CRÉDITO ]
```

Não mostrar apenas:

> O valor será calculado oficialmente.

---

## 12. NEXT_AMOUNT É FONTE DA VERDADE

Usar o valor oficial retornado pelo backend.

Não dividir:

`total / people_count`

manualmente no Flutter.

Isso é importante para centavos/resíduos.

Exemplo:

```text
R$ 100,01 / 3
```

O backend decide:

- pessoa 1
- pessoa 2
- pessoa 3

e o Flutter apenas apresenta.

---

## 13. DINHEIRO EM DIVIDIR IGUAL

Como o valor da parte já estará conhecido oficialmente:

permitir informar:

```text
VALOR DA PARTE
R$ 25,00

VALOR RECEBIDO
R$ 30,00

TROCO
R$ 5,00
```

Sem adivinhação.

---

## 14. DINHEIRO EM PAGAR POR ITENS

Mesma regra.

Primeiro:

backend calcula valor oficial dos itens.

Depois:

```text
VALOR DOS ITENS
R$ 42,50

VALOR RECEBIDO
R$ 50,00

TROCO
R$ 7,50
```

---

## 15. VALIDAR RECEBIDO >= APLICADO NO FLUTTER

BUG ATUAL:

Mesa permite habilitar confirmar dinheiro com:

```text
Aplicado R$ 50
Recebido R$ 10
```

e só o backend rejeita.

Corrigir.

O botão CONFIRMAR deve permanecer desabilitado se:

`received_amount < applied_amount`

O backend continua validando também.

---

## 16. MOSTRAR TROCO ANTES DE CONFIRMAR

Reutilizar a experiência da Venda Rápida.

Sempre que método for Dinheiro:

mostrar:

- aplicado;
- recebido;
- troco.

Atualizar troco em tempo real.

---

## 17. PAGAR SALDO

BUG ATUAL:

No modo:

`remaining`

o campo aparece editável.

Porém o backend ignora o `amount` digitado e usa o saldo oficial.

Isso pode fazer o operador visualizar uma coisa e pagar outra.

CORRIGIR.

PAGAR SALDO deve mostrar:

```text
PAGAR SALDO

R$ 87,50
```

Valor travado.

Sem campo editável.

Backend continua usando `mode=remaining`.

---

## 18. PAGAR POR VALOR

Somente o modo:

`value`

deve permitir editar o valor aplicado manualmente.

Não permitir:

- zero;
- negativo;
- maior que saldo.

---

## 19. HEADER DE PAGAMENTO DE MESA

Quero a mesma lógica visual da Venda Rápida.

Em tela pequena:

```text
← PAGAMENTO        👤  ⇄  ⋮
```

Onde:

- 👤 = Cliente
- ⇄ = Dividir
- ⋮ = opções financeiras

Em tela maior pode mostrar labels.

Não quero Mesa com experiência diferente sem necessidade.

---

## 20. BOTÃO DIVIDIR NO HEADER

Hoje Mesa pede:

```text
forma de pagamento
→ modo
```

Enquanto Venda Rápida possui:

```text
DIVIDIR
→ dividir igual / pagar por itens.
```

Padronizar.

Header:

`DIVIDIR`

abre:

```text
DIVIDIR IGUAL
PAGAR POR ITENS
```

Depois o usuário escolhe a forma de pagamento.

Evitar duas UX diferentes para a mesma operação.

---

## 21. PAGAMENTO NORMAL

Ao tocar diretamente:

- Dinheiro
- Débito
- PIX
- Crédito

fluxo normal deve ser:

`PAGAR POR VALOR`

com opção de:

`PAGAR SALDO`

na própria entrada.

Não precisa abrir modal intermediário perguntando modalidade em todas as formas.

Seguir a experiência que já funciona na Venda Rápida.

---

## 22. COMPONENTES COMPARTILHADOS

Hoje existem:

- `payment_contract.dart`
- `quick_sale_payment_adapter.dart`
- `table_payment_adapter.dart`
- `shared_payment_widgets.dart`
- `shared_payment_page.dart`
- `table_payment_page.dart`

A refatoração ficou pela metade.

Não quero copiar toda a tela novamente.

Reutilizar o máximo possível da composição e comportamento.

Se for adequado, extrair um shell/controller compartilhado para:

- header;
- grid;
- pending;
- histórico;
- resumo;
- reversal;
- selector de formas;
- entrada dinheiro;
- entrada de valor.

Mesa e Quick Sale mudam apenas adapter e ações específicas.

NÃO fazer uma mega-refatoração desnecessária se isso colocar Venda Rápida em risco.

Prioridade:

não duplicar comportamento financeiro/UX.

---

## 23. DESCONTO DA MESA

Hoje Mesa criou um AlertDialog próprio simples.

Venda Rápida já possui:

`SharedDiscountDialog`

REUTILIZAR.

Mesa já possui:

- `checkout_discount`
- `checkout_discount_type`

Portanto permitir corretamente:

- valor;
- percentual.

Não criar um segundo editor inferior.

---

## 24. DESCONTO / TAXA ANTES DO PAGAMENTO

Continuar permitindo editar:

- cliente;
- desconto;
- taxa de serviço;

antes do primeiro pagamento.

Respeitar autorização por PIN quando necessário.

---

## 25. BLOQUEIO APÓS PRIMEIRO PAGAMENTO

Depois do primeiro pagamento aplicado:

bloquear edição financeira.

Não mostrar texto gigante de “edição financeira bloqueada”.

Apenas:

- desabilitar ações;
- manter layout estável.

---

## 26. ESTORNO

Preservar o fluxo atual corrigido.

Pagamento não estornado:

ação ESTORNAR continua acessível.

Se operador possui:

`tables.payments.reverse`

→ confirmação → estorno.

Se não possui:

→ seleciona autorizador  
→ PIN 6 dígitos  
→ backend valida  
→ estorno.

Motivo continua OPCIONAL.

---

## 27. HISTÓRICO / REVERSAL

Preservar:

- pagamento original no histórico;
- reversal append-only;
- `reversal_of`;
- `reversal_reason`;
- motivo mostrado somente quando preenchido.

---

## 28. FECHAMENTO DA MESA

Só permitir:

`FECHAR MESA`

quando:

`remaining_balance == 0`

segundo estado oficial do backend.

Não calcular isso localmente.

---

## 29. SELEÇÃO DE CAIXA NO FECHAMENTO

Revisar `_close()`.

Hoje, se existem várias sessões de caixa abertas, a UI pode pedir caixa novamente mesmo quando pagamentos em dinheiro da Mesa já determinam a sessão.

Usar a lógica oficial:

Se pagamentos em dinheiro já possuem sessão válida única:

→ não perguntar novamente.

Se nenhum pagamento determinou sessão e o backend precisa de uma sessão para consolidar:

→ selecionar caixa.

Se modo FIXED já determina caixa:

→ não perguntar.

Evitar pergunta redundante.

---

## 30. NAVEGAÇÃO APÓS FECHAR

Preservar:

```text
Mesa
↓
Pagamento
↓
FECHAR MESA
↓
backend fecha
↓
TableAttendance CLOSED
↓
volta para lista de Mesas
↓
grid atualiza
↓
Mesa disponível
```

Não voltar para tela financeira antiga.

---

## 31. PAGAMENTO PARCIAL

Preservar:

```text
Mesa R$100
Dinheiro R$30
PIX R$20
Crédito R$50
```

Resumo sempre vindo do backend:

- Total
- Pago
- Falta

---

## 32. FORMAS DE PAGAMENTO VIA API

Continuar usando:

`tables/checkout-options/`

Nenhuma forma deve ser inventada no Flutter.

Todos os métodos ativos recebidos devem estar acessíveis.

---

## 33. MUITOS MÉTODOS / OUTROS

Preservar bottom sheet rolável.

VA, VR, vouchers e métodos customizados devem aparecer em:

`OUTROS`

quando aplicável.

---

## 34. CAIXA / POS DEVICE

Preservar validações já adicionadas de:

`_pos_sale_session()`

Não permitir que device opere sessão de caixa incompatível.

---

## 35. NÃO MISTURAR COM COMANDA LEGADO

O fluxo novo usa somente:

- `TableAttendance`
- `TablePayment`
- `TablePaymentAllocation`

Não mexer no fluxo antigo:

`AttendanceCommand / Command`.

---

## 36. NÃO REGREDIR VENDA RÁPIDA

Venda Rápida deve continuar funcionando exatamente como antes.

Verificar especialmente:

- Dinheiro;
- Débito;
- PIX;
- Crédito;
- Outros;
- parcial;
- pagar por itens;
- dividir;
- estorno;
- autorização PIN;
- pending/retry;
- finalização;
- navegação para catálogo.

---

## 37. TESTE FUNCIONAL SERÁ MANUAL

NÃO criar nova bateria de testes Widget/E2E.

O proprietário do projeto fará o teste funcional.

Pode atualizar testes existentes somente quando necessário para manter integridade do código.

---

## 38. CHECKS

Executar:

- `flutter analyze`
- `git diff --check`
- Django system check
- migrations check

Se alterar backend financeiro/serializers/views, executar os checks backend relevantes.

Não gastar a missão corrigindo dívidas antigas não relacionadas.

---

## 39. CENÁRIOS QUE DEVEM FICAR PRONTOS

### CENÁRIO A

```text
Operador de Caixa
→ abre Mesa
→ adiciona itens
→ abre PAGAMENTO
```

### CENÁRIO B

```text
R$100
Dinheiro R$30
PIX R$70
→ saldo zero
→ Fecha Mesa
```

### CENÁRIO C

```text
R$100 / 4 pessoas
→ DIVIDIR
→ DIVIDIR IGUAL
→ Pessoa 1 R$25
→ Pessoa 2 R$25
→ Pessoa 3 R$25
→ Pessoa 4 R$25
```

### CENÁRIO D

```text
PAGAR POR ITENS
→ seleciona Pizza + Coca
→ backend retorna valor oficial
→ operador vê valor
→ escolhe pagamento
```

### CENÁRIO E

```text
Dinheiro
Aplicado R$40
Recebido R$50
Troco R$10
```

### CENÁRIO F

```text
PAGAR SALDO R$70
→ valor travado
→ não editável
```

### CENÁRIO G

```text
pagamento sofre timeout
→ fica PENDING
→ novos pagamentos bloqueados
→ refresh/reconciliação
→ se já entrou, limpa pending
→ se não entrou, retry mesma idempotency key
```

### CENÁRIO H

```text
Estorno
→ operador sem permissão
→ Gerente/Administrador
→ PIN
→ estorno
```

### CENÁRIO I

```text
Dinheiro / Débito / PIX / Crédito
visíveis separadamente

VA / VR / customizados
→ OUTROS
```

---

## 40. CHECKPOINT FINAL

AO TERMINAR, INFORMAR:

1. causa de a tela de pagamento estar inacessível;
2. permissões padrão adicionadas ao Gerente;
3. permissões padrão adicionadas ao Operador de Caixa;
4. migration criada para perfis sistema existentes;
5. confirmação de que perfis personalizados não foram sobrescritos;
6. como Débito/Crédito foram corrigidos;
7. como ficou OUTROS;
8. como pending bloqueia novos pagamentos;
9. como funciona reconciliação por idempotency_key;
10. se pending foi persistido e como;
11. como ficou preview oficial de pagar por itens;
12. como ficou dividir igual;
13. como `next_amount` é usado;
14. como ficou dinheiro em pagar por itens;
15. como ficou dinheiro em dividir igual;
16. validação recebido >= aplicado;
17. cálculo visual de troco;
18. como ficou PAGAR SALDO;
19. como ficou o header compartilhado;
20. como ficou o botão DIVIDIR;
21. como Mesa e Venda Rápida compartilham comportamento;
22. como ficou desconto por valor/percentual;
23. bloqueio financeiro após pagamento;
24. confirmação de estorno com autorização;
25. fechamento da Mesa;
26. seleção de caixa no fechamento;
27. navegação após fechamento;
28. confirmação de que Comanda legado não foi alterado;
29. confirmação de que Venda Rápida não regrediu;
30. arquivos alterados;
31. `flutter analyze`;
32. `git diff --check`;
33. Django system check;
34. migrations check;
35. resumo objetivo do diff.

DEPOIS PARE.

NÃO INICIE OUTRA FASE.

NÃO IMPLEMENTE STONE/CIELO/PAGBANK.

QUERO TESTAR MANUALMENTE MESAS + PAGAMENTOS ANTES DE SEGUIR.
