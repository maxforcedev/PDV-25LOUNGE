TRABALHE SOMENTE NESTES PONTOS NO HEAD ATUAL DA MAIN E DEPOIS PARE.

NÃO INICIE NOVA FASE.

NÃO MEXER EM:

* impressão;
* Stone;
* Cielo;
* PagBank;
* fiscal;
* Comanda legado;
* nova arquitetura fora do necessário.

==================================================

1. AGRUPAMENTO DA MESA DEVE SER CONSISTENTE
   ==================================================

Já existe agrupamento visual no:

RESUMO DA MESA

Quero a MESMA lógica de equivalência também em:

* Conferência;
* Pagar por itens;
* Transferir itens.

Não criar 3 critérios diferentes de agrupamento.

Centralize/reutilize a lógica de equivalência dos TableOrderItem para evitar:

Resumo agrupa de um jeito
Pagamento agrupa de outro
Transferência agrupa de outro.

O agrupamento continua sendo SOMENTE uma representação visual.

NUNCA substituir ou consolidar os TableOrderItem reais no backend.

Os IDs individuais precisam continuar existindo.

==================================================
2. CHAVE CORRETA DE EQUIVALÊNCIA
================================

Atualmente o agrupamento usa aproximadamente:

* productId;
* unitPrice;
* modifierSnapshot;
* notes;
* status;
* printStatus;
* cancellationReason.

TableOrderItem JÁ possui:

financialSnapshot

em:

pos/lib/attendance/attendance_models.dart

Portanto a equivalência deve considerar também o estado financeiro congelado.

Dois itens só podem estar no mesmo grupo quando forem realmente equivalentes.

Considerar:

* produto;
* preço;
* unidade;
* modificadores;
* observação;
* status relevante;
* financialSnapshot normalizado.

Especialmente informações como:

* promotion;
* promotion_name;
* promotion_discount_type;
* promotion_discount_value;
* promotion_benefit;
* manual_discount;
* manual_discount_intent;
* net_subtotal;
* participação em taxa;
* participação em comissão;

quando existirem no snapshot.

Não inventar campos.

Use os campos reais presentes no financialSnapshot.

Exemplo:

1x HEINEKEN normal
1x HEINEKEN com promoção

NÃO devem ser agrupadas se as condições financeiras forem diferentes.

==================================================
3. PAGAR POR ITENS — AGRUPAR
============================

Hoje:

pos/lib/payments/table_payment_page.dart

em:

_selectItems()

faz:

attendance.orders
→ order.items
→ cria um PaymentAllocationItem para CADA TableOrderItem.

Resultado:

HEINEKEN
HEINEKEN
HEINEKEN
HEINEKEN

Quero:

4x HEINEKEN

desde que os quatro itens sejam equivalentes pela regra definida acima.

IMPORTANTE:

o backend continua trabalhando com os TableOrderItem reais.

Exemplo:

grupo visual:

4x HEINEKEN

pode representar internamente:

item 31 = 1x
item 34 = 1x
item 38 = 1x
item 45 = 1x

Se o operador escolher pagar:

3x HEINEKEN

a interface precisa transformar isso, antes de enviar ao backend, em allocations reais.

Exemplo:

[
item 31 -> 1
item 34 -> 1
item 38 -> 1
]

Não enviar ID falso de grupo para a API.

Não criar TableOrderItem artificial.

A distribuição entre os itens reais deve ser determinística.

Preferência:

mais antigo primeiro, mantendo ordenação estável por:

confirmedAt / pedido / ID

ou, no mínimo, ID crescente caso seja a ordenação segura disponível.

Se um TableOrderItem tiver quantidade maior que 1, pode alocar quantidade parcial nele porque o backend de pagamento por itens já trabalha com:

allocated_quantity

e valida contra:

item.quantity.

==================================================
4. DISPONIBILIDADE AGRUPADA NO PAGAMENTO
========================================

O pagamento por itens já calcula quanto de cada TableOrderItem foi pago.

Ao agrupar:

a quantidade disponível apresentada deve ser a SOMA da disponibilidade dos itens reais daquele grupo.

Exemplo:

HEINEKEN:

item 31:
1 original
1 já pago
= 0 disponível

item 34:
1 disponível

item 38:
1 disponível

item 45:
1 disponível

Mostrar:

HEINEKEN
Disponível: 3

e não quatro linhas separadas.

Ao selecionar 2:

gerar allocations sobre 2 unidades realmente disponíveis.

Nunca realocar quantidade que já foi paga.

==================================================
5. PREVIEW DO PAGAMENTO CONTINUA COM IDs REAIS
==============================================

Hoje o preview usa:

previewTablePayment(
attendanceId,
allocations
)

Preservar isso.

O agrupamento deve ser desfeito em allocations reais ANTES de chamar o backend.

O backend NÃO precisa conhecer o grupo visual.

Quando o backend retornar:

available_quantities

por item real, a UI agrupada deve recalcular/somar a disponibilidade por grupo.

Não modificar o motor financeiro apenas para suportar a apresentação.

==================================================
6. PAYMENTALLOCATIONITEM
========================

Hoje PaymentAllocationItem representa somente:

* id;
* name;
* quantity;
* availableQuantity;
* unit.

Adapte o contrato da forma mais limpa para permitir um item visual representar múltiplos itens reais.

Pode existir conceito como:

PaymentAllocationSource

contendo:

* itemId real;
* quantidade total;
* quantidade disponível.

E o PaymentAllocationItem visual possuir suas sources.

Não é obrigatório usar exatamente esses nomes.

Mas NÃO utilizar um ID sintético que depois seja enviado acidentalmente para o backend.

O resultado final de:

PaymentAllocationSelection.allocations

deve continuar contendo apenas:

item = ID REAL DO TableOrderItem
allocated_quantity = quantidade real.

==================================================
7. TRANSFERIR ITENS — AGRUPAR TAMBÉM
====================================

Hoje:

_TableItemTransferPage

recebe:

List<TableOrderItem>

e mostra uma CheckboxListTile para cada registro.

Resultado:

HEINEKEN
HEINEKEN
HEINEKEN
HEINEKEN

Quero agrupar:

4x HEINEKEN

pela MESMA regra de equivalência usada no Resumo/Pagamento.

==================================================
8. TRANSFERÊNCIA PRECISA PRESERVAR OS IDs
=========================================

O backend atual de transferência exige a quantidade integral de cada TableOrderItem.

Existe regra equivalente a:

if quantity != item.quantity:
partial_table_item_transfer_unsupported

NÃO alterar essa regra nesta missão.

Portanto não inventar transferência parcial arbitrária de um TableOrderItem.

Comportamento desejado:

4x HEINEKEN

representando:

item 31
item 34
item 38
item 45

Ao marcar o grupo inteiro:

selecionar os quatro TableOrderItem reais.

Payload:

[
{"item": 31, "quantity": quantidade original},
{"item": 34, "quantity": quantidade original},
{"item": 38, "quantity": quantidade original},
{"item": 45, "quantity": quantidade original}
]

Se o operador quiser somente parte do grupo:

permitir expandir/abrir o grupo para selecionar entradas individuais.

Exemplo:

4x HEINEKEN

> selecionar entradas

[✓] 1x Pedido #18
[✓] 1x Pedido #21
[ ] 1x Pedido #24
[ ] 1x Pedido #26

Assim continuamos respeitando a regra atual de transferência integral por TableOrderItem.

NÃO implementar partial transfer no backend agora.

==================================================
9. CONFIRMAÇÃO DA TRANSFERÊNCIA TAMBÉM AGRUPADA
===============================================

Hoje o AlertDialog final percorre todos os items selecionados e pode voltar a mostrar:

1x HEINEKEN
1x HEINEKEN
1x HEINEKEN

Agrupar também nessa confirmação:

3x HEINEKEN

sem perder o payload real.

==================================================
10. ERRO REAL AO FECHAR MESA
============================

Erro recebido:

POST /api/v1/pos/table-attendances/1/close/

Traceback:

close_table_attendance()
→ finalize_sale()
→ backend/apps/sales/services.py
→ aproximadamente linha 2520

falha:

'value': f'{snapshot["manual_discount_intent"]["value"]:.2f}'

Exception:

ValueError:
Unknown format code 'f' for object of type 'str'

A causa já foi identificada no HEAD atual.

NÃO É Flutter.

NÃO É o PostgreSQL FOR UPDATE anterior.

O erro anterior já foi ultrapassado porque agora o fechamento chega até:

finalize_sale().

==================================================
11. CAUSA EXATA DO TIPO STRING
==============================

Em:

backend/apps/sales/services.py

função:

_frozen_command_snapshots()

existe atualmente lógica semelhante a:

financial_snapshot = getattr(item, 'financial_snapshot', None) or {}

...

'promotion_discount_value':
Decimal(str(...))

'promotion_benefit':
Decimal(str(...))

'manual_discount':
Decimal(str(...))

'net_subtotal':
Decimal(str(...))

PORÉM:

'manual_discount_intent':
financial_snapshot.get('manual_discount_intent')
or {'type': 'amount', 'value': Decimal('0.00')}

O financial_snapshot é armazenado em JSON.

Quando ele volta do JSON:

manual_discount_intent pode ser:

{
"type": "amount",
"value": "0.00"
}

Ou seja:

value = STRING

Depois o finalize_sale presume que esse valor é Decimal e executa:

f'{value:.2f}'

gerando:

ValueError:
Unknown format code 'f' for object of type 'str'

==================================================
12. CORREÇÃO CORRETA
====================

NÃO corrigir apenas assim:

str(value)

na linha de auditoria.

NÃO mascarar o problema apenas no f-string.

A inconsistência de tipo deve ser resolvida quando o financial snapshot congelado é RECONSTRUÍDO.

Use a função que já existe no mesmo serviço:

normalize_discount_intent(...)

Ela já transforma:

{
'type': 'amount',
'value': '10.00'
}

em:

{
'type': 'amount',
'value': Decimal('10.00')
}

e também valida:

* amount;
* percentage;
* valores negativos;
* percentual máximo;
* precisão monetária.

Portanto `_frozen_command_snapshots()` deve reconstruir o:

manual_discount_intent

de forma NORMALIZADA.

Conceitualmente:

raw_manual_intent =
financial_snapshot.get('manual_discount_intent')

manual_discount_intent =
normalize_discount_intent(
raw_manual_intent,
field=...,
)

e então colocar no snapshot interno.

Não precisa usar exatamente esse código, mas o resultado interno deve manter o contrato:

snapshot['manual_discount_intent']['type'] = str válido
snapshot['manual_discount_intent']['value'] = Decimal

==================================================
13. NÃO ALTERAR O FORMATO PERSISTIDO DESNECESSARIAMENTE
=======================================================

financial_snapshot é JSON e naturalmente serializa números monetários como string quando essa foi a convenção usada.

Não faça migration para isso.

Não mude JSONField para outro tipo.

O problema é a reconstrução para o domínio Python.

Regra arquitetural:

JSON/storage
→ strings serializadas são aceitáveis

domínio financeiro interno
→ Decimal

==================================================
14. REVISAR OUTROS CAMPOS DO SNAPSHOT
=====================================

Já existem conversões para Decimal em:

* promotion_discount_value;
* promotion_benefit;
* manual_discount;
* net_subtotal.

Confirme se qualquer outro campo monetário vindo de financial_snapshot está entrando cru no domínio onde depois se espera Decimal.

Não fazer refatoração ampla.

Corrigir somente inconsistências reais da mesma reconstrução.

==================================================
15. NÃO MASCARAR NO AUDIT_LOG
=============================

O erro apareceu durante construção de:

item_snapshots

para auditoria.

Mas o valor também é usado antes em:

SaleItem.objects.create(
manual_discount_intent_value=...
)

O fato de o Django aceitar/coagir uma string em determinado campo NÃO significa que o contrato interno esteja correto.

Normalize na origem.

Depois a linha:

f'{snapshot["manual_discount_intent"]["value"]:.2f}'

deve funcionar naturalmente porque o valor voltou a ser Decimal.

==================================================
16. TRANSAÇÃO
=============

Preservar:

@transaction.atomic

em:

close_table_attendance()

e:

finalize_sale().

O fechamento não pode gerar:

* Sale parcial;
* SaleItem parcial;
* Payment parcial;
* baixa de estoque parcial;
* Mesa fechada sem venda.

Não criar tratamento que capture o ValueError e continue a transação.

Corrigir o dado.

==================================================
17. PRESERVAR LEDGER DA MESA
============================

NÃO alterar novamente a correção recente:

_locked_table_payments()
_active_locked_table_payments()
_locked_active_table_payments()

Preservar:

TableAttendance lock
→ TablePayment lock sem nullable outer join
→ detectar reversões
→ pagamentos ativos.

Não reintroduzir:

select_for_update()
+
reversal__isnull=True

no fluxo novo da Mesa.

==================================================
18. REGRESSÃO A VALIDAR
=======================

O fechamento deve funcionar quando os itens possuem financial_snapshot contendo:

manual_discount_intent:

A)
{
"type": "amount",
"value": "0.00"
}

B)
{
"type": "amount",
"value": "10.00"
}

C)
{
"type": "percentage",
"value": "10.00"
}

Não mudar o valor financeiro durante a normalização.

Exemplo:

"10.00"
→ Decimal("10.00")

e NÃO:

"10.00"
→ 0
ou
→ 1000
ou
→ 10%.

O type continua determinando a semântica.

==================================================
19. CASHSESSION
===============

Preservar:

CAIXA
→ POSDevice.active_cash_session
→ Mesa / Venda Rápida / pagamentos.

Não adicionar seletor de caixa.

Não alterar:

table_cash_session_mismatch.

==================================================
20. ERRO DE DomainValidationError
=================================

Também continua valendo a correção já apontada em:

POSCashSessionSelectView

onde existe:

DomainValidationError(
code='cash_session_unavailable',
message='...',
status_code=status.HTTP_409_CONFLICT,
)

mas DomainValidationError.**init** atualmente não aceita status_code.

Corrija esse TypeError conforme instrução anterior, usando o padrão de conflito já existente no projeto ou solução arquitetural equivalente.

Não deixar 500 nesse caminho.

==================================================
21. VALIDAÇÃO
=============

Não criar bateria nova de Widget/E2E.

Rodar:

* flutter analyze;
* python manage.py check;
* python manage.py makemigrations --check --dry-run;
* git diff --check.

Rodar teste backend direcionado existente do fechamento de Mesa se disponível.

Se adicionar teste de regressão backend, que seja somente para o bug específico:

financial_snapshot
→ manual_discount_intent.value string
→ fechar Mesa
→ Sale finalizada sem ValueError.

==================================================
22. CHECKPOINT FINAL
====================

Ao terminar informe:

1. como centralizou/reutilizou a equivalência de itens;
2. quais campos fazem parte da equivalência;
3. como financialSnapshot participa da chave;
4. como Pagar por itens aparece agrupado;
5. como quantidade agrupada vira allocations de IDs reais;
6. como evita pagar novamente quantidade já alocada;
7. como trata seleção parcial de um grupo no pagamento;
8. como Transferir itens aparece agrupado;
9. como transferência preserva TableOrderItem reais;
10. como permite selecionar somente parte das entradas sem quebrar partial_table_item_transfer_unsupported;
11. como ficou a confirmação da transferência;
12. causa exata do ValueError do fechamento;
13. onde a string entrava no snapshot;
14. como manual_discount_intent agora é normalizado;
15. confirmação de que o domínio interno recebe Decimal;
16. confirmação de que não apenas mascarou o f-string;
17. confirmação de preservação do transaction.atomic;
18. confirmação de preservação do ledger lockado;
19. correção do cash_session_unavailable;
20. arquivos alterados;
21. flutter analyze;
22. Django check;
23. migrations check;
24. git diff --check.

DEPOIS PARE.

NÃO INICIE OUTRA FASE.
