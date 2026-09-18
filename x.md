O BUG 3 PERSISTIU EM TESTE MANUAL NO HEAD 8435cbb9b43535cbb5a6b2c895b98cf338bac782.

NÃO considere a implementação atual suficiente.

CENÁRIO REAL QUE CONTINUA COM PROBLEMA:

1. adiciono produto A;
2. entro em pagamento;
3. registro pagamento;
4. estorno completamente;
5. paid_amount volta para 0;
6. volto para o carrinho;
7. removo produto A;
8. adiciono produto B;
9. entro novamente em pagamento;
10. o checkout/histórico anterior ainda pode ser reutilizado.

A regra continua sendo:

SE O CHECKOUT JÁ TEVE QUALQUER HISTÓRICO DE PAGAMENTO E A COMPOSIÇÃO DOS ITENS MUDOU, ESSE CHECKOUT NÃO PODE RECEBER A NOVA COMPOSIÇÃO.

O checkout antigo deve continuar preservado no banco com:

* itens antigos;
* pagamento original;
* reversal;
* allocations;
* auditoria;
* histórico completo.

Depois de todos os pagamentos ativos terem sido estornados, se os itens mudarem:

* cancelar/encerrar corretamente o checkout antigo;
* limpar somente o vínculo local daquele checkout quando for seguro;
* gerar NOVA creation_idempotency_key;
* criar NOVO QuickSaleCheckout;
* novo checkout deve começar com payments = [];
* paid_amount = 0;
* nenhum pagamento/reversal anterior pode aparecer na nova venda.

NÃO dependa somente de:

checkout.payments.isNotEmpty

para descobrir histórico financeiro no Flutter.

A fonte da verdade deve ser o backend.

Adicionar ao payload oficial do checkout campo/capability equivalente a:

has_payment_history: true/false

calculado no backend pela existência de QUALQUER QuickSalePayment do checkout, inclusive pagamentos posteriormente estornados.

O Flutter deve consumir essa informação oficial.

IMPORTANTE:

O backend já possui a defesa:

checkout_requires_new_instance

quando tentam mudar itens de checkout com histórico de pagamentos.

PORÉM O FLUTTER ATUAL NÃO TRATA ESSE CONFLITO CORRETAMENTE.

Hoje updateQuickSaleCheckout captura PosApiException genericamente, chama _handleApiError(error) e retorna null.

Isso deixa o checkout antigo associado ao estado local e permite que ele seja recuperado novamente.

CORRIGIR:

Se updateQuickSaleCheckout receber especificamente:

code = checkout_requires_new_instance

o fluxo deve fazer a transição segura para um NOVO checkout, e não simplesmente deixar o checkout antigo ativo no estado local.

Essa transição deve:

1. verificar o estado real do checkout;
2. garantir que não há pagamento ativo;
3. garantir que não existe payment_attempt/pending operation com resultado de rede incerto;
4. cancelar o checkout antigo somente se for seguro;
5. preservar integralmente ledger/auditoria;
6. limpar o estado local associado ao checkout antigo;
7. gerar nova creation_idempotency_key;
8. criar novo checkout com o carrinho atual;
9. garantir que o novo checkout possua outro ID;
10. garantir que payments do novo checkout esteja vazio.

NÃO APAGAR payment_attempt ou pending operation cujo resultado de rede seja incerto.

Se houver operação financeira incerta, primeiro resolver/reconciliar o checkout com o backend antes de permitir a troca.

Também corrigir os outros pontos encontrados na revisão:

1. checkout_can_pay_by_items atualmente chama _allocation_amount(), que lança item_allocation_mismatch para amount <= 0. Isso pode quebrar a busca por quantidade fracionária cuja menor unidade arredonda inicialmente para R$0,00 e pode fazer a montagem do payload do checkout lançar exceção. A capability deve ser uma leitura segura e nunca transformar um simples GET/payload em erro por causa de candidato inválido.

2. tornar a comparação de composição dos itens canônica/estrutural. Não depender de jsonEncode(Map) bruto e ordem de chaves para decidir se os itens mudaram.

3. remover do .gitignore a regra genérica "*.md" adicionada nesse commit. missao.md já estava ignorado especificamente. Não ignorar toda documentação Markdown do projeto.

NÃO alterar Mesas/Comandas.
NÃO alterar Android/Gradle.
NÃO fazer refatoração geral.
NÃO alterar outros módulos.
NÃO criar testes automatizados.
NÃO executar testes automatizados.
NÃO executar build completo.

Antes de encerrar, revisar MANUALMENTE PELO CÓDIGO o cenário exato do BUG 3 e mostrar no checkpoint:

* ID do checkout antigo;
* momento em que has_payment_history é detectado;
* motivo pelo qual o PUT no checkout antigo não acontece;
* cancelamento seguro do checkout antigo;
* limpeza do estado local;
* geração de nova creation_idempotency_key;
* criação do checkout novo;
* garantia de que checkout novo não contém payments antigos;
* tratamento de checkout_requires_new_instance como fallback;
* tratamento de payment_attempt/pending incerto sem perda de idempotência.

Depois PARE.
