OPENCODE — CORREÇÕES FINAIS DA FASE 1 DE PAGAMENTOS DA VENDA RÁPIDA

IMPORTANTE:
- O ESTADO ATUAL DO GITHUB É A FONTE DA VERDADE.
- HEAD auditado: f6a42bd6469dfedee923e386a4f411b146682f9e
- Antes de alterar, leia o código atual e confirme cada problema.
- NÃO reimplementar Pagamentos do zero.
- NÃO começar Mesas.
- NÃO começar Comandas.
- NÃO alterar Android / Gradle / Kotlin.
- NÃO executar testes automatizados.
- NÃO criar testes automatizados agora.
- NÃO executar builds completos.
- Não fazer alterações fora deste escopo.
- Preserve checkout persistente, StockReservation, baixa física, caixa, pagamentos parciais e arquitetura atual que já estão funcionando.

Validações permitidas somente:
- flutter analyze
- python manage.py check
- python manage.py makemigrations --check --dry-run
- git diff --check

==================================================
OBJETIVO
==================================================

Corrigir os pontos restantes encontrados na auditoria do GitHub e FECHAR a Fase 1 da Venda Rápida antes de conectarmos o SharedPaymentPage em Mesas.

==================================================
1. CORRIGIR IDEMPOTÊNCIA DE PAGAMENTOS IGUAIS
==================================================

AINDA ESTÁ ERRADO.

Hoje o Flutter identifica uma operação pendente por algo semelhante a:

payment:$checkoutId:$paymentMethodId:$mode:$amount:$receivedAmount:$allocations

Isso NÃO identifica uma tentativa de pagamento.
Isso identifica apenas o conteúdo financeiro.

Cenário real:

Cliente A:
R$30 débito

Backend aplica pagamento.
Resposta se perde.

Depois:

Cliente B:
R$30 débito

Esses são DOIS pagamentos diferentes.

O app NÃO pode reutilizar automaticamente a idempotency_key do pagamento anterior só porque o payload é igual.

REGRA:

Cada tentativa iniciada pelo operador deve ter uma identidade própria.

Exemplo conceitual:

payment_intent_id = UUID

payment_intent_id
→ idempotency_key

Retry da MESMA tentativa:
→ reutiliza a mesma chave.

Novo clique/novo pagamento:
→ novo intent UUID;
→ nova idempotency_key,
mesmo que método, valor e allocations sejam idênticos.

O payload não deve ser usado como identidade exclusiva da tentativa.

A persistência deve permitir recuperação de uma tentativa INCERTA após crash/rede sem transformar pagamentos futuros iguais em replay.

Não perder proteção contra duplicação.

==================================================
2. FINALIZAR VENDA DEVE FECHAR A PAYMENT PAGE
==================================================

Hoje o fluxo finaliza a Sale e chama onCompleted(), mas a Payment Page pode continuar aberta com o checkout antigo.

Corrigir.

Fluxo esperado:

saldo = 0
→ FINALIZAR VENDA
→ backend finaliza
→ sucesso
→ limpar estado persistente do checkout
→ limpar draft da Venda Rápida
→ fechar SharedPaymentPage
→ retornar à Venda Rápida pronta para uma NOVA venda.

Não deixar na tela um checkout já FINALIZED.

Também preservar recuperação segura se a resposta da finalização for perdida.

==================================================
3. CANCELAR CHECKOUT DEVE VOLTAR PARA VENDA RÁPIDA LIMPA
==================================================

Backend já cancela corretamente e libera StockReservation.

Mas a UX precisa ficar correta.

Fluxo:

CANCELAR
→ confirmação
→ backend CANCELLED
→ reserva RELEASED
→ limpar estado local do checkout
→ limpar carrinho/draft daquela Venda Rápida
→ fechar Payment Page
→ Venda Rápida vazia.

Não voltar com os mesmos produtos no carrinho depois de ter cancelado o checkout.

Se existem pagamentos ativos:
- backend continua bloqueando cancelamento;
- UI deve informar claramente:
  “Estorne todos os pagamentos antes de cancelar a venda.”

==================================================
4. NÃO PERMITIR EDITAR VENDA APÓS PRIMEIRO PAGAMENTO
==================================================

Backend já congela corretamente após pagamento.

Mas a UX Flutter ainda precisa acompanhar isso.

Cenário:

Venda = R$100
→ paga R$30
→ operador aperta voltar
→ retorna ao catálogo
→ altera produtos
→ parece que alterou a venda
→ checkout backend continua congelado.

Isso é inconsistente.

REGRA:

Após o PRIMEIRO pagamento aplicado:

- itens não podem ser alterados;
- quantidades não podem ser alteradas;
- modificadores não podem ser alterados;
- produtos não podem ser adicionados/removidos;
- descontos/taxa/cliente bloqueados conforme capabilities oficiais.

Preferência:

Após primeiro pagamento, botão voltar da Payment Page NÃO deve simplesmente retornar para uma Venda Rápida editável.

Pode:

A) manter operador no pagamento até finalizar/cancelar via estornos;

OU

B) permitir voltar para uma visualização bloqueada daquela venda, sem edição.

Escolha a solução mais coerente com a arquitetura atual e mais simples de manter.

O backend continua sendo a fonte de verdade.

==================================================
5. DINHEIRO SEM TROCO NÃO DEVE EXIGIR “VALOR RECEBIDO”
==================================================

Hoje o fluxo de dinheiro exige received_amount >= amount mesmo quando o operador NÃO ativou “Informar valor recebido”.

Isso não faz sentido operacionalmente.

Fluxo normal:

DINHEIRO
→ digita R$30
→ CONFIRMAR

Deve resultar conceitualmente em:

amount = 30
received_amount = 30
change = 0

SEM obrigar o operador a ativar campo adicional.

O campo:

INFORMAR VALOR RECEBIDO

serve SOMENTE quando existe possibilidade de troco.

Exemplo:

Valor aplicado: R$30
Valor recebido: R$50
Troco: R$20

Se toggle estiver desligado:
received_amount = amount.

Se ligado:
received_amount precisa ser >= amount.

Pagamento por itens em dinheiro deve seguir a mesma regra.

==================================================
6. PAGAMENTO POR ITENS — DISPONIBILIDADE PRECISA ABRIR CORRETA
==================================================

Backend calcula corretamente quantidade já paga.

Mas a tela pode inicialmente mostrar quantidade total antes do primeiro preview daquela abertura.

Exemplo:

5x Coca
já foram pagas 2.

Ao abrir novamente:

PAGAR POR ITENS

deve mostrar imediatamente:

Disponível: 3

NÃO:

Disponível: 5

e só depois corrigir.

A informação de quantidade alocável deve vir de estado oficial/backend.

Pode:

- incluir available_quantity no payload do checkout;

OU
- carregar um preview/availability apropriado ao abrir a página;

escolha a alternativa mais coerente e reutilizável.

Não recalcular apenas no Flutter usando suposições.

==================================================
7. FRACIONADOS — NÃO USAR 500 TOQUES PARA 0,500 KG
==================================================

A correção de precisão em milésimos foi válida.

Mas a UX atual incrementando 0,001 por toque é inviável.

Produto fracionado deve permitir entrada prática.

Exemplo:

Disponível:
1,500 kg

Operador pode selecionar:

0,500
1,000
1,500

sem apertar + 500 vezes.

Para UN:
- manter step inteiro de 1.

Para fracionados:
- fornecer entrada numérica de quantidade;
- respeitar até 3 casas decimais;
- validar <= quantidade disponível;
- backend continua calculando valor oficial.

Pode manter botões +/- como complemento, mas deve existir entrada direta.

==================================================
8. DIVIDIR IGUAL — INVALIDAR PLANO SE SALDO MUDAR POR FORA
==================================================

A distribuição de centavos agora ficou correta:

R$100 / 3
→ 33,34
→ 33,33
→ 33,33

Preservar isso.

Mas `_equalSplitParts` é local.

Cenário:

criou divisão;
pagou uma parte;
depois fez pagamento normal;
ou estornou pagamento.

O saldo muda, mas a divisão local pode continuar representando valor antigo.

REGRA:

Enquanto o operador estiver pagando através da própria divisão:
- manter partes já pagas;
- não recalcular a divisão após cada parte.

MAS:

Se o saldo for alterado EXTERNAMENTE àquela divisão:
- pagamento normal;
- pagamento por itens;
- estorno;
- outra ação que altere saldo;

invalidar o plano de divisão atual.

Na próxima entrada em DIVIDIR IGUAL:
- criar uma nova divisão sobre o saldo atual.

Não criar Pessoas, Comandas ou entidades escondidas.

Dividir igual continua sendo um helper operacional.

==================================================
9. VA / VR DEVEM SER CLASSIFICADOS COMO CARTÃO/BENEFÍCIO
==================================================

Hoje metadata oficial ainda trata apenas:

cash
pix
credit_card
debit_card

e demais códigos caem em OTHER.

Preparar estrutura oficial para:

VA
VR
benefit

Sem usar o nome visual para decidir.

Adicionar códigos/metadata coerentes com o domínio atual.

Exemplo conceitual:

cash
visual_group=cash
kind=cash

pix
visual_group=pix
kind=pix

credit_card
visual_group=card
kind=credit

debit_card
visual_group=card
kind=debit

food_voucher / va
visual_group=card
kind=benefit

meal_voucher / vr
visual_group=card
kind=benefit

Não precisa integrar provider nesta missão.

Todos continuam podendo ter:

source=manual

nesta fase.

Não espalhar hardcode no Flutter.

==================================================
10. REGRA VISUAL DOS 4 BOTÕES DE PAGAMENTO
==================================================

Aplicar exatamente esta regra:

As formas vêm da API.

Se as únicas formas disponíveis forem:

DINHEIRO
CRÉDITO
DÉBITO
PIX

mostrar diretamente os 4:

[ DINHEIRO ]
[ CRÉDITO ]
[ DÉBITO ]
[ PIX ]

SEM criar agrupador Cartão nesse caso.

Se existirem MAIS formas do que cabem diretamente, usar:

[ DINHEIRO ]
[ CARTÃO ]
[ PIX ]
[ OUTROS ]

onde:

CARTÃO
→ Crédito
→ Débito
→ VA
→ VR
→ demais modalidades visual_group=card.

OUTROS
→ demais formas disponíveis.

Regra geral:

- mostrar SOMENTE métodos ativos vindos da API;
- nenhuma forma ativa pode desaparecer;
- prioridade visual:
  Dinheiro
  Cartão / Crédito-Débito
  PIX
  Outros.

Não depender da ordem `order_by(name)` para determinar posição visual.

==================================================
11. REMOVER FUNÇÕES FINANCEIRAS DO CATÁLOGO
==================================================

A separação que definimos ainda não foi concluída.

CATÁLOGO / CARRINHO deve cuidar de:

- produtos;
- quantidade;
- modificadores;
- observação;
- remover item;
- apagar carrinho.

PAGAMENTO deve cuidar de:

- cliente;
- desconto por item;
- desconto geral;
- taxa de serviço;
- pagamentos;
- estornos.

Hoje ainda existem:

- cliente no menu do carrinho;
- desconto geral;
- taxa;
- desconto por item no editor do carrinho.

Mover a UX financeira para SharedPaymentPage.

IMPORTANTE:
NÃO remover capacidade backend.
NÃO alterar motor financeiro.

Apenas centralizar a UX.

==================================================
12. DESCONTO POR ITEM NA PAYMENT PAGE
==================================================

A Payment Page ainda precisa oferecer:

DESCONTO POR ITEM

antes do primeiro pagamento.

Fluxo esperado:

Pagamento
→ menu superior
→ DESCONTO POR ITEM
→ listar itens do checkout
→ selecionar item
→ aplicar R$ ou %
→ usar o mesmo sistema de autorização existente
→ backend recalcula snapshot
→ atualizar resumo.

Reutilizar:

SharedDiscountDialog
SharedAuthorizationDialog

e mecanismos atuais.

Permissão:

sales.apply_item_discount

Se operador não possui:
- selecionar autorizador;
- PIN;
- validar;
- não persistir PIN.

Após primeiro pagamento:
- opção bloqueada.

==================================================
13. CAPABILITIES DEVEM CONSIDERAR STATUS DO CAIXA
==================================================

Hoje o payload pode devolver:

can_record_payment = true
can_reverse_payment = true
can_edit_financials = true

mesmo que a CashSession do checkout já esteja CLOSED.

Depois o endpoint falha.

Evitar isso.

Capabilities devem refletir o estado operacional real.

Se cash_session CLOSED:

can_record_payment = false
can_reverse_payment = false
can_edit_financials = false

Mas:

se checkout já estiver 100% pago:
can_finalize pode continuar true
conforme regra existente que permite materializar checkout integralmente pago após fechamento do caixa.

Não permitir novos pagamentos depois do caixa fechado.

Não permitir estorno depois do caixa fechado.

Não permitir alteração financeira depois do caixa fechado.

==================================================
14. PRESERVAR STOCK RESERVATION
==================================================

NÃO alterar a arquitetura de reserva que foi criada.

Preservar:

StockReservation
StockReservationRequirement

ACTIVE
CONSUMED
RELEASED
EXPIRED

Reserva NÃO altera saldo físico.

Reserva NÃO cria StockMovement.

Pagamento parcial:
- mantém reserva sem expiração.

Após todos os pagamentos serem estornados:
- volta a possuir TTL.

Checkout cancelado:
- libera reserva.

Finalização:
- baixa estoque real;
- consome reserva.

Outras saídas físicas:
- continuam respeitando reservas.

Não criar dupla baixa.

==================================================
15. PRESERVAR ORDEM DE LOCKS
==================================================

A correção de ordem de locks criada no quick checkout deve permanecer.

Não introduzir novamente inversão.

Continuar seguindo ordem coerente com:

CashSession
→ QuickSaleCheckout
→ Payments
→ Reservation/Stock

quando aplicável.

Não remover select_for_update necessário.

==================================================
16. RESUMO FINANCEIRO
==================================================

Preservar resumo que agora já possui:

Subtotal
Promoções
Descontos por item
Desconto da venda
Taxa de serviço
Total
Pago
Falta

Se possível ocultar linhas zeradas somente se isso for compatível com o padrão já usado no CORE.

Não recalcular valores financeiros no Flutter.

Backend/snapshot é fonte de verdade.

==================================================
17. ESTORNO
==================================================

Preservar a correção atual:

pagamento original estornado
→ deve aparecer visualmente como ESTORNADO;
→ não pode mostrar botão Estornar novamente.

Reversão continua no histórico.

Não apagar pagamento original.

Permissão:
sales.payments.reverse.

==================================================
18. CAIXA FLEXIBLE
==================================================

Preservar a correção atual.

Se houver:

1 sessão:
→ selecionar automaticamente.

Mais de 1:
→ operador escolhe.

Nunca voltar a usar `.first` silenciosamente.

FIXED continua respeitando caixa fixo.

==================================================
19. RECOVERY POR OPERADOR
==================================================

Preservar a correção atual:

Device + Operator.

Operador B não recupera checkout do Operador A.

Backend também filtra checkout pelo operator.

Não apagar checkout de A quando B entrar.

Cada operador pode recuperar seu próprio checkout.

==================================================
20. RECOVERY FINALIZED/CANCELLED
==================================================

Preservar:

checkout FINALIZED recuperado
→ limpar estado local.

checkout CANCELLED recuperado
→ limpar estado local.

Não deixar checkout zumbi bloquear próxima venda.

==================================================
21. FLUXOS QUE DEVEM FUNCIONAR AO FINAL
==================================================

VALIDAR POR LEITURA/LÓGICA, SEM EXECUTAR TESTES AUTOMATIZADOS.

Cenário A:

Venda R$100
→ DINHEIRO
→ R$100
→ confirmar sem ativar “valor recebido”
→ pago R$100
→ finalizar
→ voltar Venda Rápida limpa.

Cenário B:

R$100
→ PIX R$30
→ DÉBITO R$20
→ DINHEIRO R$50
→ saldo zero.

Cenário C:

Dinheiro:
valor aplicado R$30
valor recebido R$50
troco R$20.

Cenário D:

5 Coca
→ pagar 2
→ próxima entrada em pagar itens mostra 3 disponíveis imediatamente.

Cenário E:

1,500 kg
→ operador digita 0,500
→ preview oficial do backend.

Cenário F:

R$100 / 3
→ 33,34
→ 33,33
→ 33,33.

Cenário G:

cria divisão
→ paga uma parte
→ faz pagamento por fora
→ divisão anterior é invalidada.

Cenário H:

R$30 débito
→ resposta incerta
→ retry da mesma tentativa não duplica.

Depois:
novo pagamento R$30 débito
→ DEVE criar novo pagamento.

Cenário I:

Operador A possui checkout aberto
→ operador B entra no mesmo POS
→ não recupera checkout de A.

Cenário J:

checkout sem pagamento expira
→ tentar pagar
→ reserva é revalidada/readquirida se houver estoque.

Cenário K:

caixa fechado
→ UI já mostra pagamento/estorno bloqueados
→ checkout totalmente pago ainda pode finalizar quando regra backend permitir.

Cenário L:

cancelar checkout sem pagamentos
→ reserva liberada
→ carrinho limpo
→ Venda Rápida vazia.

Cenário M:

checkout parcialmente pago
→ não permitir editar catálogo como se fosse uma venda nova.

==================================================
22. NÃO IMPLEMENTAR AGORA
==================================================

NÃO implementar:

- Stone provider;
- Cielo provider;
- PagBank provider;
- Pix integrado;
- TEF;
- Mesas;
- Comandas;
- prepaid;
- wallet;
- impressão;
- mudanças de Android;
- novos módulos.

Métodos continuam MANUAIS nesta fase.

==================================================
23. CHECKPOINT FINAL
==================================================

Ao terminar, PARE.

Não comece Mesas.

Me entregue:

1. HEAD/commit;
2. arquivos alterados;
3. correção da idempotência de pagamentos iguais;
4. como ficou o payment_intent/retry;
5. como ficou finalizar e fechar Payment Page;
6. como ficou cancelamento e limpeza do carrinho;
7. como ficou bloqueio após primeiro pagamento;
8. como ficou dinheiro sem troco;
9. como ficou pagamento por itens já parcialmente pago;
10. como ficou entrada de quantidade fracionada;
11. como ficou divisão igual e invalidação;
12. como ficou VA/VR;
13. como ficou regra dos 4 botões;
14. como ficou desconto por item na Payment Page;
15. quais controles financeiros foram removidos do catálogo;
16. como ficaram capabilities com caixa fechado;
17. confirmações de que StockReservation e locks foram preservados;
18. validações leves executadas;
19. pendências/riscos restantes.

NÃO executar testes automatizados.
NÃO executar build completo.