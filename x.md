# MISSÃO — Fechar recuperação de Venda Rápida finalizada com estado stale no POS

Trabalhe no **HEAD mais recente da main**.

Na última revisão, o HEAD era:

`a03bba27af5fba7d8a11ed2323902860e411efd5`

Antes de alterar, confira o HEAD atual.

## CONTEXTO

As últimas correções resolveram corretamente:

- UUID no fingerprint de impressão;
- impressão automática não derrubar Sale já finalizada;
- replay imediato da finalização com a mesma idempotency key;
- bloqueio de reprint parcial;
- bloqueio de estorno quando o `_checkout.status` local já não está OPEN.

Porém ainda existe uma falha de recuperação quando o backend já finalizou a venda e o Flutter continua com um checkout local stale.

---

# REGRA CRÍTICA

**NÃO EXECUTE TESTES.**

NÃO execute:

- `flutter analyze`
- `flutter test`
- build Flutter
- pytest
- npm test
- npm build
- npm lint
- suites
- `makemigrations --check`

Eu farei o build e os testes manualmente.

---

# 1. PROBLEMA REAL AINDA EXISTENTE

Existe este cenário:

```text
POS envia finalize
→ backend cria Sale
→ checkout vira FINALIZED
→ resposta falha ou conexão cai

Flutter tenta replay
→ replay também falha ou conexão continua ruim

Flutter continua na tela de pagamento
com `_checkout.status == open` local/stale

Depois o operador tenta estornar pagamento.

O Flutter chama:

POST /sales/checkouts/<checkout>/payments/<payment>/reverse/

O backend corretamente responde:

409
code = checkout_closed

porque o checkout real já está FINALIZED.

Hoje o Flutter mostra o erro, mas pode continuar com o checkout stale na tela.

Isso precisa ser corrigido.

2. NÃO REMOVER A PROTEÇÃO DO BACKEND

Preservar:

if checkout.status != QuickSaleCheckoutStatus.OPEN:
    raise QuickCheckoutConflict(
        'checkout_closed',
        'O checkout já foi finalizado.',
    )

Essa regra está correta.

NÃO reabrir checkout.

NÃO permitir estorno de QuickSalePayment depois que a Sale foi materializada.

3. QUICKSALECHECKOUT PRECISA CONHECER sale_id

O backend já devolve em _quick_checkout_payload():

{
  "id": "...",
  "status": "finalized",
  "sale_id": 123
}

Porém o model Flutter QuickSaleCheckout atualmente não possui saleId.

CORRIGIR.

Em:

pos/lib/sales/sale_models.dart

adicionar algo equivalente a:

final int? saleId;

ou tipo compatível com o ID real da Sale.

Fazer parse de:

json['sale_id']

Preservar null quando não houver Sale.

4. CHECKOUT FINALIZED NÃO É "CHECKOUT SUMIU"

Hoje recoverQuickSaleCheckout() faz algo equivalente a:

if (_isTerminalQuickSaleCheckout(checkout)) {
  await _writeQuickCheckoutState({});
  return null;
}

Isso é insuficiente para:

FINALIZED + sale_id

FINALIZED significa que existe uma operação concluída que precisa ser recuperada.

Não tratar simplesmente como null/descartado.

Diferenciar:

CANCELLED
→ pode limpar estado e retornar null

FINALIZED + sale_id
→ precisa recuperar conclusão da venda
5. CRIAR RECUPERAÇÃO DA VENDA FINALIZADA

Quando o checkout recuperado estiver:

status = finalized
sale_id != null

o AppController deve conseguir recuperar a Sale/result correspondente.

Preferir reutilizar endpoint POS/backend existente.

Não criar lógica duplicada se já houver endpoint que retorne a Sale/result final.

Objetivo:

checkout FINALIZED
→ localizar Sale
→ montar/obter QuickSaleResult
→ limpar pending/local state
→ retornar estado final para UI

Não recalcular venda.

Não criar nova Sale.

Não refazer estoque.

Não refazer pagamentos.

6. RECUPERAÇÃO DEVE FUNCIONAR APÓS RESTART

Cenário:

POS finaliza venda
→ backend conclui
→ app fecha/crasha/perde conexão
→ operador abre app novamente

Se o estado local ainda contém:

checkout_id
+
pending.finalize

e o backend responde:

status = finalized
sale_id != null

o POS deve reconhecer:

A VENDA JÁ FOI CONCLUÍDA

e não oferecer edição, pagamento ou estorno do checkout.

7. TRATAR checkout_closed EM _runQuickCheckoutOperation()

Hoje _runQuickCheckoutOperation() trata erro HTTP < 500 genericamente:

remove pending
→ mostra erro
→ retorna null

Adicionar tratamento específico para:

error.code == 'checkout_closed'

Antes de simplesmente abandonar a operação:

consultar novamente o checkout;
obter estado real do backend;
se estiver FINALIZED e tiver sale_id, iniciar recuperação da venda final;
limpar operação pendente correspondente;
impedir continuidade no checkout editável.
8. ESTORNO COM ESTADO STALE

Cenário:

Flutter local:
_checkout.status = open

Backend:
checkout.status = finalized

Usuário toca ESTORNAR.

Backend responde:

409 checkout_closed

O Flutter deve:

buscar checkout novamente
↓
receber finalized + sale_id
↓
atualizar estado
↓
sair do fluxo editável
↓
tratar venda como concluída

Não apenas mostrar snackbar e permanecer na mesma tela.

9. OUTRAS OPERAÇÕES DE CHECKOUT TAMBÉM DEVEM SER DEFENSIVAS

O mesmo problema pode ocorrer em:

estorno;
pagamento;
cancelamento;
edição financeira;
qualquer ação que dependa de checkout OPEN.

Se backend responder checkout_closed, usar a mesma recuperação centralizada.

Não implementar lógica diferente em cada tela.

Criar helper central no AppController, se apropriado.

10. NÃO CONFUNDIR FINALIZED COM CANCELLED

Regra:

CANCELLED
→ checkout encerrado sem Sale válida
→ limpar estado local

FINALIZED + sale_id
→ venda concluída
→ recuperar resultado final

Não tratar os dois estados igualmente.

11. TELA DE PAGAMENTO

Se a tela SharedPaymentPage descobrir que o checkout foi finalizado no backend:

NÃO manter:

grid de pagamento ativo;
estorno de QuickSalePayment;
edição financeira;
botão finalizar;
cancelamento do checkout.

Ela deve sair do fluxo financeiro e encaminhar o resultado final já materializado.

12. REUTILIZAR O onCompleted

A SharedPaymentPage já possui fluxo:

await widget.onCompleted(result);
Navigator.pop(result);

A recuperação de venda finalizada deve, se possível, convergir para esse mesmo fluxo.

Objetivo:

finalização normal
ou
recuperação após erro

→ ambos terminam com QuickSaleResult
→ onCompleted(result)
→ Venda concluída

Evitar duas arquiteturas de finalização.

13. FINALIZE REPLAY CONTINUA COM A MESMA CHAVE

Preservar a implementação atual:

erro >= 500
ou erro de rede
→ tentar finalize novamente com MESMA key

Não gerar nova idempotency key durante recuperação.

14. PENDING FINALIZE

Se ainda existir:

pending['finalize']

e o backend confirmar checkout FINALIZED:

remover esse pending.

Não deixar operação financeira incerta armazenada depois de o servidor confirmar a Sale.

15. recoverQuickSaleCheckout() PRECISA TER SEMÂNTICA CLARA

Pode refatorar para evitar retorno ambíguo.

Hoje:

null

pode significar:

não existe checkout;
foi cancelado;
foi finalizado;
erro de rede;
erro de API.

Isso dificulta a recuperação.

Se necessário, criar tipo/resultado interno que diferencie:

OPEN checkout
FINALIZED sale
CANCELLED
NOT_FOUND
ERROR

Não é obrigatório se houver solução simples, mas não esconder FINALIZED + sale_id em null.

16. BACKEND: GARANTIR QUE FINALIZED SEMPRE TENHA SALE

Já existe validação no model:

FINALIZED exige sale

Preservar.

Não criar estado intermediário persistente:

FINALIZED sem sale
17. NÃO REABRIR CHECKOUT

PROIBIDO:

FINALIZED → OPEN

PROIBIDO remover checkout.sale.

PROIBIDO manipular QuickSalePayment para simular rollback de venda finalizada.

Depois da finalização, a entidade correta é Sale.

18. CANCELAMENTO PÓS-VENDA

Não implementar refund/adquirente agora.

Preservar domínio existente:

QuickSaleCheckout OPEN
→ estorno de QuickSalePayment

Sale FINALIZED
→ cancel_sale / fluxo de cancelamento de venda

Não misturar os dois.

19. NÃO REGREDIR CORREÇÕES ANTERIORES

Preservar:

UUID canonicalizado no fingerprint;
fingerprint somente quando necessário;
impressão secundária não derruba Sale;
tickets secundários não derrubam Sale;
PrintDocumentRequest;
generated_jobs;
print_document_state;
retry != reprint;
reprint parcial bloqueado;
múltiplas impressoras;
múltiplas cópias;
GET read-only;
snapshot/versionamento;
margens ESC/POS.
20. NÃO COMEÇAR NOVO BLOCO

NÃO implementar:

Stone refund;
Cielo refund;
TEF;
fiscal;
USB;
Bluetooth;
Print Agent;
KDS;
Delivery;
Comanda.
RESULTADO ESPERADO 1 — FINALIZAÇÃO NORMAL
checkout OPEN
→ paga
→ FINALIZAR
→ backend cria Sale
→ response sucesso
→ QuickSaleResult
→ tela Venda concluída
RESULTADO ESPERADO 2 — RESPOSTA PERDIDA
FINALIZAR
→ backend cria Sale
→ resposta perdida
→ POS repete mesma key
→ backend retorna replay
→ tela Venda concluída
RESULTADO ESPERADO 3 — DUPLA FALHA / RESTART
FINALIZAR
→ backend cria Sale
→ resposta falha
→ replay falha por rede
→ app reinicia

recover
→ backend devolve checkout FINALIZED + sale_id
→ POS recupera Sale
→ limpa pending
→ trata venda como concluída
RESULTADO ESPERADO 4 — ESTORNO STALE
Flutter acha que checkout está OPEN
backend já está FINALIZED

ESTORNAR
→ 409 checkout_closed
→ POS consulta checkout
→ encontra FINALIZED + sale_id
→ recupera venda
→ sai da tela de pagamento
→ NÃO tenta estornar QuickSalePayment novamente
CHECKPOINT FINAL

Ao terminar informe:

como sale_id passou a ser representado no Flutter;
como recoverQuickSaleCheckout() diferencia CANCELLED de FINALIZED;
como recupera a Sale de checkout FINALIZED;
como trata checkout_closed;
como _runQuickCheckoutOperation() ficou defensivo;
como a SharedPaymentPage sai do estado stale;
como funciona após restart;
como pending.finalize é limpo;
arquivos backend alterados;
arquivos Flutter alterados;
migrations criadas, se houver;
pontos que ainda dependem de teste manual.

NÃO EXECUTE TESTES.

NÃO EXECUTE FLUTTER ANALYZE.

NÃO EXECUTE BUILD.

Depois pare.