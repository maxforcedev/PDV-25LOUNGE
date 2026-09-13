OPENCODE — MESA 1.9
FECHAR COMPLETAMENTE A ETAPA DE PEDIDOS DA MESA

IMPORTANTE:
A FONTE DA VERDADE É O ESTADO ATUAL DO REPOSITÓRIO.

HEAD de referência analisado:
1ee7103039c1a8d5c083725b43d0511431f86204
MESA 1.8.1

NÃO confie em checkpoints anteriores.
Leia o código atual antes de alterar qualquer coisa.

O execute.md foi removido de propósito.
NÃO recriar execute.md.
NÃO criar documentos/instruções operacionais na raiz do projeto.

==================================================
REGRA CRÍTICA — VENDA RÁPIDA ESTÁ APROVADA
==================================================

A VENDA RÁPIDA JÁ FOI APROVADA.

NÃO modificar seu comportamento.

Nesta missão:

NÃO modificar:
pos/lib/sales/quick_sale_page.dart

NÃO alterar:
- UX da Venda Rápida;
- carrinho;
- checkout;
- scanner;
- estoque;
- descontos;
- taxa;
- clientes;
- modificadores;
- permissões;
- mensagens;
- responsividade;
- fluxo de venda;
- cálculo.

A Mesa deve se adaptar ao padrão aprovado.

Pode REUTILIZAR componentes que já estão públicos, como:

- ProductCatalogPanel
- ProductCard
- MobileCartBar
- BatchQuantityDialog
- SaleItemEditorDialog
- ProductBarcodeScannerPage

Mas não alterar a Venda Rápida para acomodar a Mesa.

==================================================
OBJETIVO DESTA MISSÃO
==================================================

Finalizar a camada de PEDIDOS da Mesa.

Ao concluir MESA 1.9, queremos:

Mesa
→ Novo pedido
→ catálogo no padrão Venda Rápida
→ carrinho/resumo coerente
→ estoque validado
→ modificadores
→ cliente
→ desconto/taxa
→ salvar e enviar
→ estoque/produção/ticket
→ visualizar pedido enviado
→ cancelar item
→ cancelar pedido inteiro
→ impressão de cancelamento na cozinha
→ solicitar conta
→ transferências
→ agrupamento/separação

SEM implementar pagamentos ainda.

NÃO implementar nesta missão:

- pagamento parcial;
- pagar por valor;
- pagar por itens;
- divisão por pessoas;
- saldo total;
- Stone/Cielo;
- fechamento financeiro da Mesa.

Isso será MESA 2.

==================================================
1. VALIDAR PRIMEIRO SALVAR E ENVIAR PEDIDO
==================================================

Antes de avançar nas novas funcionalidades, valide o fluxo atual:

POST
/api/v1/pos/table-attendances/<id>/orders/

Testar manualmente o contrato pelo código/uso atual para:

A. produto simples sem promoção;
B. produto com modificador;
C. produto com observação;
D. produto que emite ticket;
E. produto com destino de produção.

IMPORTANTE:

No MESA 1.8.1 foi corrigido o crash:

Decimal(str(None))

de promotion_discount_value.

Não desfazer essa correção.

Sem promoção deve continuar:

promotion = null
promotion_name = null
promotion_discount_type = null
promotion_discount_value = null
promotion_benefit = 0

Se o POST ainda retornar HTTP 400:

NÃO CHUTAR A CAUSA.

Capturar e informar:

REQUEST JSON EXATO

RESPONSE JSON EXATA

campo que falhou

validação responsável

correção aplicada.

O PosApi já foi melhorado para preservar erros DRF.

Use a resposta real.

==================================================
2. PROTEGER CONTRA PEDIDO DUPLICADO
==================================================

Existe risco de múltiplos cliques rápidos em:

SALVAR E ENVIAR PEDIDO

Corrigir.

Regra:

se _saving == true
→ NÃO permitir novo envio.

Adicionar proteção lógica dentro de _save(), e não apenas visual.

Exemplo conceitual:

if (_saving) return;

Além disso:

uma tentativa de envio deve usar UMA chave de idempotência estável.

Não gerar uma chave diferente caso a resposta da mesma tentativa fique incerta.

Fluxo:

criou tentativa
→ cria idempotency_key
→ mantém essa key até sucesso ou erro definitivamente conhecido.

Se:

POST orders → sucesso

mas:

GET TableAttendance depois → falhar

NÃO reenviar automaticamente o POST.

O pedido já pode existir.

==================================================
3. CLIQUE SIMPLES — IGUAL VENDA RÁPIDA
==================================================

Manter o comportamento implementado no 1.8.1:

produto simples
→ toque
→ entra diretamente.

SEM modal de confirmação.

Produto que realmente exige configuração obrigatória
→ SaleItemEditorDialog.

Revisar _requiresConfiguration para garantir coerência com as regras reais de:

- required;
- minSelections;
- minTotalQuantity;
- requiredQuantity.

Não abrir modal desnecessariamente.

==================================================
4. MESCLAR PRODUTOS IGUAIS NO CARRINHO
==================================================

Mesa ainda faz:

_cart.add(item)

para todo toque.

Isso produz:

1x Coca
1x Coca
1x Coca

Quero o comportamento operacional aprovado da Venda Rápida:

3x Coca

quando forem itens equivalentes.

Itens podem ser mesclados quando:

- mesmo produto;
- mesmos modificadores;
- mesma observação;
- mesmas condições relevantes.

Produto simples sem modificadores/observação:

tap Coca
tap Coca
tap Coca

→ uma linha
3x Coca.

NÃO mesclar itens diferentes semanticamente.

Exemplo:

1x Hambúrguer + Bacon
1x Hambúrguer + Cheddar

continuam separados.

Criar essa lógica NA MESA.

NÃO alterar QuickSalePage.

==================================================
5. PRESSIONAR — ADICIONAR EM LOTE
==================================================

Manter:

long press
→ BatchQuantityDialog.

Mas corrigir a diferença atual.

Venda Rápida aprovada passa por editor quando o produto possui modificadores.

Na Mesa:

se produto possuir QUALQUER grupo de modificadores relevante
→ após escolher quantidade, permitir configurar modificadores.

Não considerar apenas modificadores obrigatórios.

Exemplo:

pressionar Gin
→ quantidade 5
→ produto possui adicional opcional
→ editor pode ser utilizado para configurar o lote.

Preservar coerência de quantidade/modificadores.

==================================================
6. ESTOQUE — CRIAR PREFLIGHT PARA TABLE
==================================================

Hoje o catálogo já usa:

SalesChannel.TABLE

e respeita:

show_out_of_stock_products.

Preservar isso.

Mas ainda falta o equivalente ao preflight da Venda Rápida.

Precisamos validar:

- quantidade;
- produto;
- composição;
- modificadores;
- estoque relacionado;

ANTES de consolidar alterações relevantes no carrinho/enviar pedido.

NÃO fazer cálculo de estoque no Flutter.

Backend é a fonte da verdade.

Criar/reutilizar serviço backend usando o motor canônico:

assess_sale_stock_availability

ou equivalente existente,

MAS COM:

channel = SalesChannel.TABLE

e permissão:

tables.add_items

NÃO exigir:

sales.create

para operador de Mesa.

Pode criar endpoint específico, por exemplo:

POST /api/v1/pos/tables/availability/

ou nome equivalente consistente.

Payload deve trabalhar com itens da Mesa.

Flutter:

adicionar/editar/lote
→ consulta disponibilidade quando necessário
→ se insuficiente:
   mensagem clara
   não consolidar alteração inválida.

Exemplo:

"Você tentou adicionar 10 unidades, mas há somente 2 disponíveis."

Preservar configuração:

show_out_of_stock_products = false
→ produto indisponível não aparece.

show_out_of_stock_products = true
→ produto aparece indisponível;
→ toque informa falta de estoque.

==================================================
7. QUANTIDADES FRACIONADAS
==================================================

O contador atual usa .round().

Isso não pode distorcer produto fracionado.

Não transformar:

0,500 kg → 1 item
1,600 kg → 2 itens

como se fossem unidades físicas inteiras.

Definir comportamento coerente para a barra/resumo.

Para produtos UNIT:
pode somar quantidade inteira.

Para KG/L/etc:
não use round() para representar quantidade vendida.

Se o indicador da barra for "linhas/produtos", use quantidade de linhas.

Se for "itens", mantenha semântica adequada.

Não inventar uma soma incorreta.

==================================================
8. RESUMO DO PEDIDO — MOBILE
==================================================

Manter o padrão:

[ X itens ]                  [ VER RESUMO ]

Ao tocar:

RESUMO DO PEDIDO • MESA XX

Precisa mostrar de forma completa:

2x Hambúrguer
   + Bacon
   + Cheddar
   Obs: sem cebola
   R$ XX,XX

6x Heineken
   R$ XX,XX

Permitir:

- editar;
- remover;
- alterar quantidade;
- modificadores;
- observação.

No final:

[ SALVAR E ENVIAR PEDIDO ]

Não é pagamento.

==================================================
9. RESUMO DESKTOP/TABLET
==================================================

Layout:

CATÁLOGO | RESUMO DO PEDIDO

Manter identidade da Venda Rápida.

O painel da direita deve mostrar:

- produto;
- quantidade;
- modificadores;
- observação;
- valor;
- editar;
- excluir.

E:

SALVAR E ENVIAR PEDIDO

Não colocar checkout/pagamentos.

==================================================
10. TOTAL DO PEDIDO
==================================================

Se houver total provisório no carrinho antes de enviar:

pode ser usado somente para UX.

NÃO considerar cálculo Flutter como fonte financeira oficial.

Depois do pedido ser salvo:

valores oficiais vêm de:

table_summary / backend.

Taxa, promoções, descontos e regras financeiras são backend.

==================================================
11. HISTÓRICO DE PEDIDOS DA MESA
==================================================

TableAttendancePage atual mostra informação simplificada.

Melhorar.

Quero:

PEDIDO #1058
14:32
Operador: João

2x Hambúrguer
   + Bacon
   + Cheddar
   Obs: sem cebola

1x Coca-Cola

Status: CONFIRMADO

O backend possui TableOrder.

Não quero continuar dependendo apenas de:

lista plana de TableOrderItem
→ Flutter agrupa por order_id

se isso impedir metadados do pedido.

Revisar contrato do detalhe da TableAttendance.

Preferência:

orders: [
  {
    id,
    status,
    created_at,
    created_by,
    created_by_name,
    items: [...]
  }
]

Não quebrar consumidores existentes sem necessidade.

Flutter TableOrder deve representar os metadados reais.

==================================================
12. CLIENTE DA MESA
==================================================

Implementar no TableAttendancePage:

CLIENTE
[ Nenhum cliente ]

ou:

CLIENTE
João da Silva
(21) ...

Ações:

- VER;
- PESQUISAR;
- ADICIONAR;
- TROCAR;
- REMOVER.

Reutilizar APIs/modelos genéricos já existentes do POS para clientes.

Permissões existentes devem continuar sendo respeitadas:

customers.view
customers.add
customers.change

Não criar cadastro de cliente duplicado.

O cliente deve ficar vinculado ao:

TableAttendance

e não ao pedido individual.

Se atualmente só é possível definir cliente ao abrir Mesa:

criar operação backend explícita para atendimento OPEN.

Exemplo:

PATCH/POST
table-attendances/<id>/customer/

Suportar:

set
replace
clear

Com:

- tenant isolation;
- branch isolation;
- status OPEN;
- auditoria;
- RBAC.

Não fechar/reabrir Mesa para alterar cliente.

==================================================
13. DESCONTO DA MESA
==================================================

Implementar contexto financeiro ANTES do pagamento.

Precisamos poder:

- aplicar desconto da Mesa;
- remover desconto;
- visualizar desconto atual.

Usar motor financeiro canônico existente.

NÃO calcular total no Flutter.

Permissão/autorização deve seguir regra já existente.

Reutilizar:

sales.apply_discount

e fluxo de autorização/PIN existente quando necessário.

Se backend não possui operação explícita para atualizar checkout_discount
antes do primeiro pagamento:

criar endpoint próprio de checkout context da Mesa.

Exemplo conceitual:

PATCH
table-attendances/<id>/checkout-context/

{
  "discount": "20.00"
}

Backend:

→ valida autorização;
→ atualiza checkout_discount;
→ retorna summary atualizado;
→ audita.

==================================================
14. DESCONTO POR ITEM
==================================================

Mesa precisa estar preparada para desconto por item conforme regras existentes.

NÃO criar novo motor.

Usar a mesma regra financeira canônica e permissão:

sales.apply_item_discount

quando aplicável.

IMPORTANTE:

TableOrderItem possui financial_snapshot congelado.

Definir corretamente como desconto posterior ao envio deve funcionar.

Não simplesmente editar financial_snapshot manualmente no Flutter/backend.

Se a arquitetura atual ainda não oferece operação segura para isso:

implementar serviço de domínio explícito.

Preservar auditoria.

==================================================
15. REMOVER / RESTAURAR TAXA DE SERVIÇO
==================================================

Implementar na Mesa:

[ REMOVER TAXA ]

e, depois:

[ RESTAURAR TAXA ]

NÃO alterar:

service_fee_rate_snapshot

A alíquota congelada continua a mesma.

A operação deve atuar em:

checkout_service_fee_waived

Backend é fonte da verdade.

Usar autorização quando operador não possuir permissão direta.

Reutilizar regras existentes.

Retornar summary recalculado pelo backend.

IMPORTANTE:

se já existir pagamento e o contexto financeiro estiver congelado,
respeitar as regras atuais e bloquear alteração incompatível.

==================================================
16. CANCELAR ITEM ENVIADO
==================================================

Adicionar na TableAttendancePage:

CANCELAR ITEM

Somente para item elegível.

Exigir:

tables.cancel_items

Fluxo:

operador toca cancelar
→ confirmação
→ motivo obrigatório
→ POST backend
→ refresh da Mesa.

Usar serviço existente:

cancel_table_item()

NÃO reproduzir regras no Flutter.

Backend já:

- estorna estoque;
- impede cancelamento incompatível com pagamentos;
- cancela ticket;
- gera ProductionJob CANCEL;
- gera PrintJob de cancelamento;
- audita.

Mostrar mensagem de erro real quando backend bloquear.

==================================================
17. IMPRESSÃO DE CANCELAMENTO NA COZINHA
==================================================

PRESERVAR O QUE JÁ EXISTE.

Hoje:

cancel_table_item()
→ create_table_cancellation_jobs()

Esse fluxo encontra ProductionJob NEW original
e cria CANCEL nas impressoras que receberam o pedido original.

NÃO imprimir diretamente pelo Flutter.

NÃO criar segunda arquitetura de cancelamento.

Apenas garantir que a UI chama o backend correto.

==================================================
18. CANCELAR PEDIDO INTEIRO
==================================================

Hoje existe cancelamento de ITEM, mas não existe operação atômica de TableOrder.

Implementar.

UI:

PEDIDO #1058
[ CANCELAR PEDIDO ]

Motivo obrigatório.

Backend:

criar serviço transacional próprio.

Exemplo:

cancel_table_order(
    order,
    user,
    reason,
    idempotency_key
)

Regras:

1. TableAttendance deve estar OPEN;
2. pedido deve pertencer à Mesa/filial;
3. bloquear se algum item não puder ser cancelado;
4. verificar pagamentos/alocações;
5. validar tudo ANTES de cancelar;
6. depois cancelar todos os itens;
7. estornar estoque;
8. cancelar tickets;
9. criar ProductionJob CANCEL;
10. gerar PrintJob nas impressoras originais;
11. atualizar status do TableOrder;
12. auditar uma única operação;
13. idempotência obrigatória.

ATÔMICO:

ou todo o pedido é cancelado,
ou nenhum item é cancelado.

NÃO fazer:

Flutter:
for item in order.items:
   POST cancel

Isso é proibido.

==================================================
19. STATUS VISUAL DE CANCELAMENTO
==================================================

Não apagar item/pedido cancelado do histórico.

Mostrar:

CANCELADO

Motivo:
"Cliente desistiu"

Itens cancelados podem ficar visualmente diferenciados.

O histórico precisa continuar auditável.

Financeiro da Mesa deve vir recalculado pelo backend.

==================================================
20. SOLICITAR CONTA
==================================================

Backend já possui:

request-bill
clear-bill

Adicionar UI na Mesa.

Quando não solicitado:

[ SOLICITAR CONTA ]

Quando solicitado:

CONTA SOLICITADA
[ CANCELAR SOLICITAÇÃO ]

Respeitar permissão existente.

Atualizar TableAttendance após operação.

==================================================
21. TRANSFERIR ITENS
==================================================

Backend já possui:

transfer-items

Adicionar UI.

Fluxo:

selecionar itens
→ TRANSFERIR
→ escolher Mesa destino aberta
→ confirmar.

Respeitar regras backend:

- mesma filial;
- destino aberto;
- item confirmado só integral quando regra atual exigir;
- pagamento alocado bloqueia transferência;
- sem redistribuição financeira automática.

Não duplicar regra no Flutter.

==================================================
22. AGRUPAR / SEPARAR MESAS
==================================================

Agrupamento já existe na tela de Mesas.

Separação existe no controller/backend, mas não está acessível na nova tela.

Adicionar ação apropriada quando Mesa fizer parte de grupo:

[ SEPARAR DO GRUPO ]

Respeitar:

tables.merge

ou permissão existente apropriada.

Não destruir histórico.

==================================================
23. /redefinir-senha — CI
==================================================

Existe blocker independente da Mesa:

frontend:
/redefinir-senha

useSearchParams()
sem Suspense.

Corrigir com alteração MÍNIMA seguindo o mesmo padrão já aplicado em /pos/pin.

NÃO refatorar autenticação.

NÃO mexer em outras telas.

Objetivo:

parar de bloquear a pipeline por esse erro.

==================================================
24. NÃO ALTERAR ANDROID
==================================================

NÃO mexer em:

- Gradle;
- AGP;
- Kotlin;
- compileSdk;
- targetSdk;
- AndroidManifest;
- Flutter SDK/version;
- configuração de build Android.

==================================================
25. NÃO ALTERAR VENDA RÁPIDA
==================================================

Repito:

NÃO MODIFICAR:

pos/lib/sales/quick_sale_page.dart

A Venda Rápida está aprovada.

Se alguma implementação exigir alteração nela:

PARE.

Encontre outra forma para a Mesa reutilizar o que já está público.

==================================================
26. NÃO IMPLEMENTAR PAGAMENTOS
==================================================

Mesmo que o backend já possua:

record_table_payment
equal split
payment allocations
reverse payment

NÃO criar as telas de pagamento agora.

MESA 1.9 termina em:

PEDIDOS + OPERAÇÕES DA MESA.

MESA 2 começa pagamentos.

==================================================
27. NÃO CRIAR / EXECUTAR TESTES
==================================================

NÃO criar testes automatizados.

NÃO modificar testes existentes.

NÃO executar:

python manage.py test
pytest
flutter test
npm test
jest
vitest

NÃO executar builds completos manualmente.

NÃO executar:

flutter build
npm run build
docker build
docker compose build

O GitHub pode executar CI automaticamente após push.
Isso é separado da execução manual.

==================================================
28. CHECKS LEVES PERMITIDOS
==================================================

Pode executar apenas:

flutter analyze

python manage.py check

python manage.py makemigrations --check --dry-run

git diff --check

python -m compileall
se realmente necessário.

==================================================
29. NÃO FAZER ALTERAÇÕES FORA DO ESCOPO
==================================================

Não aproveitar para:

- cleanup geral;
- renomear arquivos sem necessidade;
- mudar arquitetura não relacionada;
- alterar módulos de Comandas;
- alterar Venda Rápida;
- alterar pagamentos;
- alterar Android;
- resolver warnings antigos aleatórios;
- atualizar dependências.

==================================================
CHECKPOINT OBRIGATÓRIO
==================================================

Quando terminar, PARE.

Não avance para MESA 2.

Me entregue objetivamente:

1. HEAD inicial usado;
2. arquivos alterados;
3. resultado real do SALVAR E ENVIAR PEDIDO;
4. se houve HTTP 400:
   - request exata;
   - response exata;
   - causa exata;
   - correção;
5. como ficou proteção contra duplo envio;
6. como a idempotency_key do pedido é mantida;
7. comportamento do toque simples;
8. comportamento do long press/lote;
9. como produtos iguais são mesclados;
10. como itens com modificadores diferentes permanecem separados;
11. endpoint/preflight TABLE de estoque;
12. confirmação de SalesChannel.TABLE;
13. comportamento show_out_of_stock_products;
14. comportamento para quantidade fracionada;
15. UI mobile VER RESUMO;
16. UI desktop/tablet;
17. conteúdo completo do resumo;
18. estrutura nova do histórico de TableOrder;
19. cliente da Mesa;
20. permissões de cliente;
21. desconto da Mesa;
22. desconto por item;
23. remover/restaurar taxa;
24. autorizações/PIN;
25. cancelar item;
26. cancelar pedido inteiro;
27. confirmação de atomicidade do cancelamento de pedido;
28. confirmação de que cancelamento gera PrintJob na cozinha original;
29. solicitar/cancelar solicitação de conta;
30. transferência de itens;
31. separação de Mesa agrupada;
32. correção de /redefinir-senha;
33. resultado do flutter analyze;
34. resultado do python manage.py check;
35. resultado do makemigrations --check --dry-run;
36. resultado do git diff --check;
37. confirmação de que NÃO criou testes;
38. confirmação de que NÃO executou testes;
39. confirmação de que NÃO executou builds manuais;
40. confirmação de que NÃO alterou Android/Gradle/Kotlin;
41. confirmação de que NÃO modificou quick_sale_page.dart;
42. confirmação de que NÃO implementou pagamentos/splits.

Depois PARE e aguarde revisão.

NÃO considere a tarefa concluída apenas porque "compila".
A conclusão será avaliada pelo estado real do GitHub.