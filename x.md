Esse `409` é consequência do `500` anterior.

O que aconteceu foi:

```text
1. Você finalizou a Venda Rápida
2. finalize_quick_checkout() concluiu a venda no banco
3. checkout virou FINALIZED
4. depois disso a impressão explodiu com UUID
5. POS recebeu 500 e ficou achando que ainda estava no checkout
6. você apertou ESTORNAR
7. backend encontrou checkout FINALIZED
8. retornou 409
```

No código atual existe exatamente esta trava:

```python
if checkout.status != QuickSaleCheckoutStatus.OPEN:
    raise QuickCheckoutConflict(
        'checkout_closed',
        'O checkout já foi finalizado.',
    )
```

Então **não é erro do estorno em si**. É um problema de recuperação de estado: a venda foi finalizada, mas a interface não soube porque o efeito secundário de impressão derrubou a resposta.

Para checkout ainda aberto, estornar pagamento está correto. Depois que virou venda finalizada, o fluxo existente passa a ser **cancelamento da venda**, não estorno daquele `QuickSalePayment` do checkout.

Manda junto na correção:

````md
# MISSÃO — Corrigir recuperação após finalize + impedir estorno de checkout já finalizado

Trabalhe no HEAD mais recente da main.

Além da correção já solicitada para o UUID do fingerprint de impressão, corrigir o problema abaixo encontrado em uso real.

## CENÁRIO REAL

O POS executou:

POST /api/v1/pos/sales/checkouts/74ea6ba8-3b2b-420a-b7ec-80c662fee086/finalize/

O backend concluiu `finalize_quick_checkout()` e depois ocorreu erro no subsistema de impressão:

TypeError: Object of type UUID is not JSON serializable

O POS recebeu HTTP 500.

Logo depois, ainda na tela de pagamento, foi tentado:

POST /api/v1/pos/sales/checkouts/74ea6ba8-3b2b-420a-b7ec-80c662fee086/payments/2896d0a0-43dd-4ae0-a317-ba1e862785bc/reverse/

Resultado:

HTTP 409

## CAUSA

`finalize_quick_checkout()` já havia persistido:

- Sale;
- vínculo checkout.sale;
- checkout.status = FINALIZED;
- finalization_idempotency_key.

Porém uma falha posterior de impressão fez a API retornar 500.

O Flutter permaneceu com o estado local anterior do checkout e continuou oferecendo ações de pagamento/estorno.

Ao tentar estornar, o backend corretamente encontrou:

checkout.status != OPEN

e retornou conflito:

`checkout_closed`
`O checkout já foi finalizado.`

Portanto o problema é de CONSISTÊNCIA/RECUPERAÇÃO entre:

operação financeira concluída
+
efeito secundário de impressão falhou
+
cliente ficou com estado stale.

---

# 1. IMPRESSÃO NÃO PODE TRANSFORMAR VENDA CONCLUÍDA EM 500

Preservar a correção já solicitada.

Depois que `finalize_quick_checkout()` concluiu com sucesso:

- falha em QUICK_SALE_RECEIPT;
- falha em TICKET;
- falha ao criar PrintDocument;
- falha de fingerprint;
- qualquer falha interna do subsistema de impressão;

NÃO pode fazer o endpoint de finalização responder como se a venda tivesse falhado.

A venda é a operação principal.

Impressão é efeito secundário.

Registrar/logar a falha de impressão e devolver a venda concluída.

Não usar `except Exception` silencioso.

Registrar erro técnico de forma apropriada.

---

# 2. REPLAY DE FINALIZAÇÃO DEVE RECUPERAR A VENDA

Já existe idempotência na finalização.

Se:

checkout.status == FINALIZED
e
checkout.sale existe

uma repetição da mesma finalização deve retornar a Sale existente como replay.

NÃO:

- criar nova venda;
- baixar estoque novamente;
- registrar pagamentos novamente;
- criar outro checkout;
- cobrar novamente.

Preservar:

`Idempotency-Replayed: true`

quando aplicável.

---

# 3. POS DEVE SE RECUPERAR DE RESPOSTA INCERTA DA FINALIZAÇÃO

Existe uma janela importante:

request de finalize enviado
→ backend pode concluir
→ resposta pode falhar/perder conexão/efeito secundário gerar problema
→ cliente não sabe se concluiu.

O POS NÃO pode assumir automaticamente que o checkout continua OPEN.

Quando uma tentativa de finalização falhar de forma incerta, recuperar o checkout pelo backend antes de permitir novas ações financeiras.

Usar o endpoint de recuperação/detalhe já existente sempre que possível.

Se backend disser:

status = FINALIZED
sale_id != null

o POS deve:

- tratar a venda como concluída;
- ir para o estado/tela de venda concluída;
- NÃO continuar mostrando pagamento editável;
- NÃO oferecer estorno de QuickSalePayment daquele checkout.

---

# 4. NÃO OFERECER ESTORNO DE CHECKOUT FINALIZADO

No Flutter, a disponibilidade da ação de estorno deve depender do estado REAL retornado pelo backend.

QuickSalePayment pode ser estornado pelo fluxo de checkout somente enquanto:

checkout.status == OPEN

e demais regras atuais forem satisfeitas.

Se:

checkout.status == FINALIZED

não chamar:

`/sales/checkouts/<checkout>/payments/<payment>/reverse/`

A UI deve atualizar o checkout e remover/desabilitar essa ação.

---

# 5. BACKEND CONTINUA BLOQUEANDO ESTORNO DE CHECKOUT FINALIZADO

NÃO remover esta proteção:

```python
if checkout.status != QuickSaleCheckoutStatus.OPEN:
    raise QuickCheckoutConflict(
        'checkout_closed',
        'O checkout já foi finalizado.',
    )
````

Ela está correta.

Não permitir alteração do ledger do checkout depois da materialização da Sale.

---

# 6. DIFERENCIAR ESTORNO DE CHECKOUT E CANCELAMENTO DE VENDA

Antes da finalização:

QuickSaleCheckout
→ QuickSalePayment
→ pode estornar pagamento

Depois da finalização:

QuickSaleCheckout FINALIZED
→ Sale materializada

não voltar atrás alterando QuickSalePayment.

O fluxo de reversão operacional passa a ser a entidade Sale.

O projeto já possui:

SaleViewSet.cancel
→ `cancel_sale(...)`

Preservar essa separação de domínio.

NÃO criar uma gambiarra que reabra checkout finalizado.

NÃO mudar FINALIZED de volta para OPEN.

---

# 7. NÃO REABRIR CHECKOUT FINALIZADO

Proibido corrigir fazendo:

FINALIZED → OPEN

ou removendo:

checkout.sale

Isso quebraria:

* idempotência;
* estoque;
* caixa;
* auditoria;
* tickets;
* produção;
* vínculo com Sale.

Checkout finalizado é imutável do ponto de vista financeiro.

---

# 8. TRATAR 409 `checkout_closed` NO FLUTTER

Mesmo com a recuperação preventiva, tratar esse conflito defensivamente.

Se uma ação de pagamento/estorno retornar:

`checkout_closed`

o POS deve:

1. consultar novamente o checkout;
2. verificar `status`;
3. se FINALIZED e houver `sale_id`, recuperar o estado final;
4. sair do fluxo de pagamento editável;
5. informar de forma adequada que a venda já foi concluída.

Não deixar o usuário preso numa tela stale.

---

# 9. NÃO CONFUNDIR CANCELAMENTO DE VENDA COM REFUND DE ADQUIRENTE

Neste momento preservar o comportamento do CORE já existente.

Não implementar agora:

* estorno Stone;
* refund Cielo;
* refund adquirente;
* TEF;
* novo fluxo fiscal.

Aqui estamos corrigindo somente a consistência do domínio CORE.

---

# 10. CORRIGIR TAMBÉM O UUID DO FINGERPRINT

Preservar a missão anterior:

`POSDevice.pk` é UUID.

Canonicalizar antes do `json.dumps`.

No mínimo:

```python
'pos_device_id': str(pos_device.pk) if pos_device else None
```

E evitar calcular fingerprint quando não existe `idempotency_key`, se ele não for necessário.

---

# 11. BLOQUEAR REPRINT PARCIAL

Preservar também a correção pendente:

`reprint_print_document()` só pode executar se:

`print_document_state(document)['reprint_eligible'] == True`

Não permitir reprint quando houver job inicial:

* FAILED;
* PENDING;
* PROCESSING.

---

# RESULTADO ESPERADO

Fluxo normal:

finalizar
→ Sale criada
→ impressão funciona
→ tela Venda concluída

Falha de impressão:

finalizar
→ Sale criada
→ impressão falha
→ venda continua respondendo como concluída
→ POS mostra venda concluída
→ impressão pode ser tratada separadamente

Resposta perdida/erro incerto:

finalizar
→ backend conclui
→ POS não sabe
→ POS recupera checkout
→ encontra FINALIZED + sale_id
→ mostra Venda concluída
→ não oferece estorno de checkout

Estorno antes da finalização:

checkout OPEN
→ pagamento aplicado
→ ESTORNAR
→ permitido

Após finalização:

checkout FINALIZED
→ estorno de QuickSalePayment não permitido
→ não reabrir checkout

---

# REGRA CRÍTICA

NÃO EXECUTE TESTES.

NÃO EXECUTE:

* flutter analyze
* flutter test
* build
* pytest
* npm test
* npm build
* npm lint
* suites
* makemigrations --check

Eu farei a validação manual.

Ao terminar informe:

1. como protegeu a resposta da venda contra falha de impressão;
2. como ficou a recuperação de finalize incerto;
3. como o Flutter reage a checkout FINALIZED;
4. como trata `checkout_closed`;
5. se manteve o bloqueio de estorno após materialização da Sale;
6. como ficou o replay idempotente da finalização;
7. arquivos backend alterados;
8. arquivos Flutter alterados;
9. migrations, se houver;
10. pontos que ainda dependem de teste manual.

Depois pare.

```

Esse caso foi útil porque mostrou uma falha importante de UX/transação: **o backend estava correto ao negar o estorno; o erro foi o POS continuar se comportando como se a venda ainda estivesse aberta depois de uma finalização que, na prática, já aconteceu.**
```
