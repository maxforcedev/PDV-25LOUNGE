OPENCODE — MESA 1.8
UNIFICAR UI/UX DE PEDIDOS DA MESA COM VENDA RÁPIDA

HEAD esperado:
4a3d5807bb76101e3ed4007a546434bff32c91a2
MESA 1.7

Antes de alterar qualquer coisa, leia completamente:

pos/lib/sales/quick_sale_page.dart
pos/lib/sales/sale_models.dart
pos/lib/attendance/table_attendance_page.dart
pos/lib/attendance/attendance_pages.dart
pos/lib/attendance/attendance_models.dart
pos/lib/network/pos_api.dart
pos/lib/core/app_controller.dart

e no backend:

backend/apps/pos/views.py
backend/apps/pos/urls.py
backend/apps/attendance/serializers.py
backend/apps/attendance/services.py
backend/apps/production/services.py
backend/apps/sales/services.py

OBJETIVO:

A experiência de adicionar pedidos à Mesa deve ser A MESMA UI/UX BASE da Venda Rápida.

NÃO quero uma segunda implementação simplificada tentando imitar Venda Rápida.

Quero componentes compartilhados.

Venda Rápida e Mesa devem reutilizar:

- catálogo;
- categorias;
- favoritos;
- busca;
- fotos;
- scanner/código de barras;
- cards de produto;
- comportamento responsivo;
- carrinho;
- editor de produto;
- quantidade;
- modificadores;
- observações;
- disponibilidade;
- mensagens de estoque;
- layout desktop/tablet/mobile;
- barra de carrinho no mobile;
- padrões visuais;
- feedbacks.

A diferença deve estar somente nas funcionalidades específicas de cada contexto.

==================================================
REGRA DE ARQUITETURA
==================================================

NÃO transformar Mesa em Venda Rápida.

NÃO criar Sale ao salvar pedido de Mesa.

Não existe Comanda por baixo da Mesa.

Fluxos:

VENDA RÁPIDA:

SharedCatalog / SharedCart
→ pagamento
→ Sale

MESA:

SharedCatalog / SharedCart
→ SALVAR E ENVIAR PEDIDO
→ TableOrder
→ TableOrderItem

Portanto:

MESMA experiência de seleção
DESTINO diferente.

Extraia componentes compartilháveis da QuickSalePage quando necessário.

Não copie centenas de linhas para TableOrderPage.

Evite:

QuickSaleCatalogGrid
e
TableCatalogGrid

com implementações duplicadas.

Prefira algo como:

ProductCatalogPanel
ProductCard
CatalogFilters
CartPanel
ProductItemEditor
BarcodeScanner flow

configuráveis pelo contexto.

==================================================
1. INVESTIGAR PRIMEIRO O ERRO 400
==================================================

Existe erro real:

POST /api/v1/pos/table-attendances/1/orders/
→ HTTP 400

Antes de tentar corrigir no escuro:

- inspecione o payload real enviado pelo Flutter;
- inspecione a resposta JSON real do backend;
- identifique exatamente qual validação está gerando 400.

O PosApi atualmente pode perder detalhes de respostas DRF que vêm como:

{
  "items": [...]
}

ou outros dictionaries de validação.

Melhore o tratamento de erro SOMENTE se necessário para que o POS consiga exibir mensagem útil enviada pelo backend.

NÃO mascarar erro.

NÃO converter qualquer 400 em mensagem genérica.

Precisamos saber:

request:
- attendance_id
- items
- product
- quantity
- modifiers
- notes
- idempotency_key

response:
- código/mensagem/campos de validação reais.

IMPORTANTE:

Hoje TableOrderPage faz:

SaleItemEditorDialog
→ depois _TableCartItemDialog

Isso é errado/redundante.

Não quero dois editores sequenciais.

Quantidade, modificadores e observação devem ser tratados em UMA experiência coerente, igual à Venda Rápida.

Alterar quantidade depois de selecionar modificadores pode tornar as regras de modificadores inconsistentes e provocar 400.

Remover esse fluxo duplicado.

==================================================
2. MESMA UI DE VENDA RÁPIDA
==================================================

A tela NOVO PEDIDO da Mesa deve visualmente parecer a Venda Rápida porque deve reutilizar a base dela.

Preservar da Venda Rápida:

- barra de pesquisa;
- categorias;
- filtro favoritos;
- scanner;
- cards;
- imagem do produto;
- preço;
- grid responsivo;
- carrinho lateral em telas maiores;
- carrinho mobile;
- contador de itens;
- editor de item;
- modificadores;
- quantidade;
- observação;
- mensagens de disponibilidade;
- feedback de carregamento.

Na Mesa, trocar a ação final:

VENDA RÁPIDA:
[ PAGAR / FINALIZAR ]

MESA:
[ SALVAR E ENVIAR PEDIDO ]

Após salvar:

→ backend cria TableOrder
→ confirma TableOrderItems
→ estoque/produção/tickets são processados no backend
→ Flutter limpa carrinho
→ volta para TableAttendancePage
→ recarrega atendimento
→ mostra pedido novo

==================================================
3. CATEGORIAS
==================================================

Mesa precisa ter o mesmo comportamento de categorias da Venda Rápida.

Usar categoria efetiva da filial retornada pelo catálogo.

Filtros:

[ Todos ]
[ Favoritos ]
[ Categoria A ]
[ Categoria B ]
...

Mesma experiência visual do Venda Rápida.

==================================================
4. FAVORITOS
==================================================

Mesa deve respeitar:

QuickSaleProduct.favorite

e oferecer o mesmo filtro Favoritos.

Não criar outro conceito de favorito.

O favorito pertence ao catálogo/produto e é compartilhado.

==================================================
5. FOTOS DOS PRODUTOS
==================================================

Mesa deve utilizar:

QuickSaleProduct.imageUrl

e renderizar exatamente com o mesmo componente/padrão da Venda Rápida.

Não criar card simplificado sem foto.

Fallback visual também deve ser o mesmo.

==================================================
6. ESTOQUE — MESMA REGRA DA VENDA RÁPIDA
==================================================

A configuração existente do Backoffice/POS deve valer para Mesa.

Hoje o backend possui:

effective_settings(device)
→ show_out_of_stock_products

Venda Rápida usa:

_visible_pos_catalog()

que:

se show_out_of_stock_products = true
→ produto aparece, mas indisponível quando aplicável

se false
→ produto sem estoque não aparece

O TableCatalog atualmente precisa ser revisado porque não está usando exatamente essa filtragem.

Mesa precisa respeitar a MESMA configuração.

Mas deve usar:

SalesChannel.TABLE

e não COUNTER.

Resultado esperado:

CONFIG:
mostrar produto sem estoque = false
→ não aparece na Mesa.

CONFIG:
mostrar produto sem estoque = true
→ aparece desabilitado
→ ao tocar:
   "Este produto está sem estoque no momento."

Além disso, o carrinho deve validar disponibilidade antes de salvar, reaproveitando o mesmo padrão de UX do Venda Rápida.

Não inventar cálculo de estoque no Flutter.

Backend continua fonte de verdade.

Se for necessário criar um endpoint de stock availability específico para TABLE, faça-o reutilizando:

assess_sale_stock_availability
ou serviço canônico equivalente

com:

channel = TABLE.

NÃO use o endpoint COUNTER da Venda Rápida para Mesa se isso ignorar disponibilidade específica do canal.

==================================================
7. PESQUISA
==================================================

Corrigir o bug atual.

Flutter Mesa hoje envia:

?q=

mas POSTableCatalogView lê:

?search=

Padronizar.

Idealmente utilizar a mesma convenção do catálogo do Venda Rápida:

search

Busca deve funcionar por:

- nome;
- código interno;
- código de barras;

conforme comportamento canônico já existente.

==================================================
8. SCANNER / CÓDIGO DE BARRAS
==================================================

Mesa deve ter o mesmo botão e experiência do scanner da Venda Rápida.

Reutilizar:

ProductBarcodeScannerPage

e o mesmo fluxo visual.

IMPORTANTE:

não usar cegamente:

quickSaleBarcode()

se esse endpoint:

- exige sales.create;
- usa SalesChannel.COUNTER.

Mesa precisa funcionar para operador que possua:

tables.add_items

mesmo que não tenha:

sales.create.

Criar/reutilizar contrato próprio para TABLE.

Exemplo aceitável:

GET tables/catalog/barcode/<barcode>/

ou equivalente.

O produto localizado precisa ser validado em:

SalesChannel.TABLE

e respeitar estoque/configuração.

==================================================
9. CLIENTE NA MESA
==================================================

Na Mesa quero:

- visualizar cliente;
- procurar cliente;
- adicionar cliente;
- trocar cliente;
- remover cliente;
- criar cliente, respeitando permissões existentes.

Reutilizar a mesma UI e APIs de pesquisa/criação do Venda Rápida sempre que forem genéricas.

Permissões continuam sendo:

customers.view
customers.add
customers.change

Não criar cadastro de cliente específico para Mesa.

TableAttendance deve ser o dono do vínculo do cliente.

Se o backend atual só permite informar customer ao ABRIR a Mesa e não existe forma segura de atualizar depois:

criar uma operação explícita no backend para atualizar cliente do TableAttendance aberto.

Algo equivalente a:

PATCH/POST table-attendances/<id>/customer/

ações:

- set customer;
- replace customer;
- clear customer.

Com:

- tenant/branch isolation;
- auditoria;
- permissão adequada;
- Mesa OPEN obrigatória.

Não fechar/reabrir Mesa para trocar cliente.

==================================================
10. MODIFICADORES
==================================================

Reutilizar exatamente o editor e as regras da Venda Rápida.

Não criar outro sistema.

Precisa respeitar:

- grupo obrigatório;
- min selections;
- max selections;
- quantidade por opção;
- min total quantity;
- max total quantity;
- required quantity;
- preço adicional;
- regras de estoque de modificadores.

Payload final para Mesa:

{
  product,
  quantity,
  modifiers,
  notes
}

O backend continua chamando resolve_modifiers().

==================================================
11. OBSERVAÇÕES
==================================================

Mesmo campo/UX do Venda Rápida.

Exemplo:

Hambúrguer
Obs: sem cebola

Essa observação precisa:

→ salvar no TableOrderItem;
→ aparecer na Mesa;
→ ir para produção/cozinha;
→ aparecer no ticket/payload quando aplicável.

==================================================
12. DESCONTO
==================================================

Mesa precisa ter experiência equivalente à Venda Rápida para:

- desconto da conta;
- desconto por item quando fizer sentido;
- autorização por PIN quando operador não possui permissão direta.

Reutilizar:

sales.apply_discount
sales.apply_item_discount

ou os códigos de permissão específicos de Mesa já existentes, se o backend já os separou.

IMPORTANTE:

não duplicar motor financeiro.

Backend é fonte da verdade.

Hoje TableAttendance já possui contexto financeiro como:

checkout_discount
checkout_service_fee_waived

e record_table_payment congela contexto financeiro no primeiro pagamento.

Precisamos de UX coerente ANTES do pagamento.

Se não existir endpoint para alterar/previewar contexto de checkout da Mesa antes do primeiro pagamento:

criar operação explícita para atualizar o contexto financeiro da Mesa aberta e retornar table_summary atualizado.

Não implementar desconto somente visualmente no Flutter.

Não recalcular total no app.

==================================================
13. REMOVER / RESTAURAR TAXA DE SERVIÇO
==================================================

Assim como Venda Rápida:

- remover taxa;
- restaurar taxa;
- exigir autorização quando necessário.

O backend já possui regra financeira canônica.

A Mesa deve somente executar operação autorizada e mostrar resultado do backend.

Preservar:

service_fee_rate_snapshot

da Mesa.

Remover a taxa NÃO significa alterar a alíquota congelada.

Significa:

checkout_service_fee_waived = true

Restaurar:

checkout_service_fee_waived = false

conforme regras atuais.

==================================================
14. PEDIDOS JÁ SALVOS NA MESA
==================================================

TableAttendancePage precisa mostrar claramente:

PEDIDO #123
hora
operador se disponível

itens:
2x Heineken
1x Hambúrguer
   + Bacon
   + Cheddar
   Obs: sem cebola

status.

Não misturar os pedidos antigos no carrinho do pedido novo.

Carrinho é apenas o pedido ainda não enviado.

Depois de:

SALVAR E ENVIAR

ele vira pedido histórico/confirmado da Mesa.

==================================================
15. CANCELAR ITEM DA MESA
==================================================

Adicionar ação no item confirmado:

CANCELAR ITEM

Exigir:

- permissão tables.cancel_items;
- motivo do cancelamento;
- confirmação visual.

Usar endpoint existente de cancelamento do TableOrderItem.

O backend já possui:

cancel_table_item()

Ele:

- valida Mesa aberta;
- bloqueia item financeiramente alocado quando necessário;
- gera movimento reverso de estoque;
- cria aviso de cancelamento da produção;
- cancela ticket;
- audita.

NÃO reproduzir isso no Flutter.

Flutter apenas manda:

item_id
reason
idempotency_key

e recarrega Mesa.

==================================================
16. CANCELAMENTO DEVE IMPRIMIR NA COZINHA
==================================================

IMPORTANTE:

O backend JÁ possui:

create_table_cancellation_jobs()

Esse serviço:

- encontra ProductionJob NEW do TableOrderItem;
- cria ProductionJob CANCEL;
- usa as impressoras que receberam o pedido original;
- cria PrintJob de cancelamento;
- envia payload com:
  event = CANCEL
  mesa
  item
  modificadores
  observação
  cancellation_reason

PRESERVAR ESSA ARQUITETURA.

Portanto:

cancelar item no POS
→ backend cancel_table_item
→ create_table_cancellation_jobs
→ CANCELAMENTO vai para mesma cozinha/setor/impressora que recebeu o item.

NÃO imprimir cancelamento diretamente pelo Flutter.

==================================================
17. CANCELAR PEDIDO INTEIRO
==================================================

Quero também:

CANCELAR PEDIDO

Exemplo:

Pedido #1058
[ CANCELAR PEDIDO ]

Não quero o Flutter disparando N cancelamentos sem atomicidade.

Se backend ainda não possui cancelamento de TableOrder inteiro:

criar serviço próprio e transacional.

Algo equivalente:

cancel_table_order(
    order,
    reason,
    user,
    idempotency_key
)

Ele deve:

- exigir Mesa OPEN;
- validar todos os itens;
- verificar alocações financeiras;
- impedir cancelamento se algum item não puder ser cancelado;
- somente depois cancelar todos;
- reverter estoque de cada item;
- gerar ProductionJob CANCEL de cada item;
- imprimir cancelamentos nos respectivos setores;
- cancelar tickets;
- atualizar status do TableOrder;
- auditar uma operação única;
- ser idempotente.

Ou tudo cancela, ou nada cancela.

NÃO fazer loop ingênuo no Flutter.

==================================================
18. NÃO CANCELAR APENAS VISUALMENTE
==================================================

Depois do cancelamento:

item/pedido deve aparecer como CANCELADO ou ser separado visualmente.

Não apagar histórico.

O financeiro da Mesa deve ser recalculado pelo backend.

Se pagamento já foi alocado ao item:

backend deve bloquear e orientar:

"Estorne o pagamento alocado ao item antes de cancelá-lo."

Não redistribuir pagamento automaticamente.

==================================================
19. UI/UX EXATAMENTE NO PADRÃO VENDA RÁPIDA
==================================================

Não quero uma tela genérica Flutter com:

Card
GridView
TextField

montados separadamente.

A aparência e interação precisam nascer dos componentes do Venda Rápida.

Na prática quero abrir:

Mesa 12
→ NOVO PEDIDO

e sentir que estou na mesma tela do Venda Rápida.

Diferenças:

título:
Novo pedido • Mesa 12

ação final:
SALVAR E ENVIAR PEDIDO

e não:
FINALIZAR VENDA.

O resto da seleção deve ser compartilhado.

==================================================
20. RESPONSIVIDADE
==================================================

Preservar comportamento do Venda Rápida:

TELA GRANDE / TABLET:
catálogo + carrinho

MOBILE / STONE:
catálogo
+ barra inferior de carrinho
→ VER CARRINHO

Não criar layout exclusivo de Mesa que se comporte diferente.

==================================================
21. CORRIGIR OS DOIS PONTOS BACKEND PENDENTES
==================================================

Aproveitar esta etapa para corrigir SOMENTE os dois bugs pequenos já encontrados:

A)

Em _confirm_table_item(), quando NÃO existe promoção:

promotion_discount_value deve permanecer None/null

e NÃO:

"0.00"

Preservar coerência do constraint do SaleItem.

B)

cancel_table_item() cria replacement_preview.

Esse preview precisa usar os snapshots congelados da Mesa:

service_fee_rate_snapshot
commission_rate_snapshot

para não avaliar cancelamento usando taxa atual da filial.

Não fazer outras refatorações financeiras desnecessárias.

==================================================
22. /pos/pin
==================================================

Corrigir também o blocker localizado do frontend Next:

/pos/pin

useSearchParams() precisa ficar sob Suspense boundary conforme Next atual.

Alteração mínima.

Não refatorar frontend inteiro.

==================================================
23. NÃO IMPLEMENTAR PAGAMENTOS/SPLITS AINDA
==================================================

Ainda NÃO montar a UI de:

- pagar por valor;
- pagar itens;
- divisão igual;
- saldo total.

Primeiro quero o motor/UX de PEDIDOS da Mesa redondo.

Depois iremos para:

MESA 2 — PAGAMENTOS.

==================================================
24. NÃO ALTERAR ANDROID
==================================================

NÃO mexer em:

Gradle
AGP
Kotlin
AndroidManifest
compileSdk
targetSdk
Flutter version

==================================================
25. NÃO CRIAR NEM EXECUTAR TESTES
==================================================

NÃO criar testes automatizados.

NÃO alterar testes existentes.

NÃO executar:

flutter test
python manage.py test
npm test
pytest
jest
vitest

NÃO executar builds completos manualmente.

Pode executar somente checks leves:

flutter analyze
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check

Se migrations forem necessárias para alguma operação nova, crie somente se realmente necessárias.

==================================================
CHECKPOINT
==================================================

Depois PARE.

Me entregue:

1. causa EXATA encontrada para o HTTP 400 ao salvar pedido;
2. request que estava sendo enviado;
3. response de validação do backend;
4. arquivos alterados;
5. quais componentes da Venda Rápida passaram a ser compartilhados;
6. confirmação de que não existe uma segunda UI paralela de catálogo/carrinho;
7. categorias na Mesa;
8. favoritos;
9. busca;
10. scanner;
11. fotos;
12. comportamento de produto sem estoque;
13. configuração show_out_of_stock_products respeitada;
14. cliente na Mesa;
15. modificadores;
16. observações;
17. descontos;
18. remoção/restauração da taxa;
19. cancelamento de item;
20. cancelamento de pedido;
21. confirmação de que cancelamento gera PrintJob para a cozinha/setor original;
22. correção do snapshot sem promoção;
23. correção do preview de cancelamento;
24. correção de /pos/pin;
25. resultado do flutter analyze;
26. outros checks leves;
27. confirmação de que NÃO executou testes;
28. confirmação de que NÃO executou builds manuais;
29. confirmação de que NÃO alterou Android/Gradle/Kotlin.

Depois PARE.

NÃO avance para pagamentos/splits ainda.