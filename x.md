Continue no HEAD atual.

Na última revisão, o HEAD era:

`3c053617079e33cf3b1a2260763f1400ff7ff11f`

Antes de alterar, confira o HEAD atual.

A parte de impressão ficou praticamente fechada. O foco agora é **corrigir definitivamente a máquina de estados da Venda Rápida**, porque ainda existem caminhos em que um checkout antigo pode contaminar uma nova venda.

NÃO mexer no que já está funcionando na impressão, Mesa, Conferência, tickets e reimpressões.

---

# 1. REGRA CENTRAL DA VENDA RÁPIDA

Nova Venda Rápida significa:

```text
novo intent operacional

Portanto:

checkout antigo != nova venda

A única exceção permitida é recuperação técnica do MESMO intent para preservar idempotência após falha de rede.

Separar de forma explícita:

RECOVERY TÉCNICO

de:

RECOVERY FUNCIONAL

Recovery funcional/visual continua PROIBIDO.

2. NÃO DEVOLVER CHECKOUT ANTIGO COM PAGAMENTO

Hoje ainda existe risco porque em createQuickSaleCheckout() a ordem está semelhante a:

if (!checkout.canEditFinancials) return checkout;

final hasAppliedPayment = ...

Isso está errado.

Um checkout com pagamento normalmente já terá:

canEditFinancials = false

Então ele pode ser retornado ANTES de verificarmos que existe dinheiro aplicado.

CORRIGIR A ORDEM.

Primeiro verificar:

tem pagamento aplicado?
tem operação financeira incerta?
status terminal?

Somente depois considerar qualquer outra capability.

3. CHECKOUT ANTIGO COM PAGAMENTO

Cenário:

checkout antigo OPEN
+
pagamento aplicado

Ao iniciar nova Venda Rápida:

NÃO:

return checkout
abrir checkout velho
cancelar checkout velho
limpar local state
misturar carrinho novo

FAZER:

bloquear a criação da nova venda

e mostrar mensagem clara:

Existe uma venda anterior com pagamento aplicado.
Conclua ou estorne os pagamentos antes de iniciar uma nova venda.

Preservar totalmente o checkout antigo.

4. CHECKOUT ANTIGO COM OPERAÇÃO INCERTA

Se existir qualquer estado como:

payment_attempts
pending finalize
pending reverse
pending payment
ou outra operação financeira incerta

NÃO cancelar.

NÃO reutilizar.

NÃO criar nova venda por cima.

Bloquear e informar:

Existe uma operação financeira anterior aguardando confirmação.
Resolva essa operação antes de iniciar uma nova venda.

Preservar idempotency keys e state persistido.

5. CHECKOUT ANTIGO OPEN SEM PAGAMENTO E SEM INCERTEZA

Cenário:

checkout OPEN
paid = 0
sem operação pendente/incerta

Esse checkout antigo não pertence à nova venda.

Fluxo obrigatório:

identificar checkout antigo
→ cancelar no backend
→ confirmar status CANCELLED
→ limpar state local
→ criar um checkout NOVO

NÃO:

updateQuickSaleCheckout(oldCheckout, newItems)

NÃO reaproveitar checkout antigo como container da nova venda.

6. CHECKOUT FINALIZED É TERMINAL

Hoje existe risco de:

checkout FINALIZED
→ recoverQuickSaleCheckout()
→ return checkout

e depois:

createQuickSaleCheckout()
→ !canEditFinancials
→ return checkout finalized

PROIBIR.

Se:

status = finalized

ou:

status = cancelled

então:

limpar referência local correspondente
→ nunca devolver como checkout de nova venda

Terminal é terminal.

7. FINALIZAÇÃO INCERTA E _recoveredQuickSaleResult

Existe hoje:

QuickSaleResult? _recoveredQuickSaleResult;

e:

takeRecoveredQuickSaleResult()

Isso precisa ser tratado com muito cuidado.

Risco atual:

Venda A
→ finalize incerto
→ recovery confirma Venda A
→ _recoveredQuickSaleResult = Venda A

depois começa Venda B

alguma operação da Venda B retorna null
→ takeRecoveredQuickSaleResult()
→ pega resultado da Venda A

Isso NÃO pode acontecer.

8. _recoveredQuickSaleResult PRECISA SER ESCOPADO

O resultado recuperado deve estar associado ao checkout/intenção que o gerou.

Não usar um slot global solto.

Preferir algo como:

checkoutId + QuickSaleResult

ou:

operation id / intent id

Assim:

resultado recuperado do checkout A

só pode ser consumido por:

checkout A

Nunca por B.

9. AO COMEÇAR NOVO CHECKOUT, NÃO PODE SOBRAR RESULTADO RECUPERADO ANTIGO

Antes de criar uma nova operação real:

garantir que nenhum recovered result antigo possa vazar

Mas NÃO simplesmente apagar resultado necessário de uma operação financeira ainda pendente.

Resolver corretamente o ownership.

10. MESMO REQUEST / MESMO INTENT

Recovery técnico continua permitido quando o request é o MESMO.

Exemplo:

create checkout
→ request enviado
→ rede caiu antes da resposta

Existe:

creation_idempotency_key
creation_request

Se o operador repete exatamente o mesmo intent:

mesmo request
mesma idempotency key

pode recuperar o checkout criado no servidor.

Isso é correto e deve permanecer.

11. REQUEST ANTIGO DIFERENTE DO REQUEST ATUAL

Esse é outro ponto ainda perigoso.

Hoje, se existe:

creation_idempotency_key antigo
creation_request antigo

e o novo carrinho/request é diferente, o código ainda pode:

recoverQuickSaleCheckout(oldKey)
→ pegar checkout antigo
→ update com itens novos

NÃO fazer isso.

Se:

oldRequest != newRequest

tratar como NOVO INTENT.

12. NOVO INTENT COM CHECKOUT ANTIGO RECUPERADO

Se recuperar pelo creation_idempotency_key antigo e encontrar:

OPEN
sem pagamento
sem operação incerta

então:

cancelar antigo
→ confirmar cancelamento
→ limpar state
→ gerar nova creation idempotency key
→ criar novo checkout

Não atualizar o antigo.

13. NOVO INTENT + CHECKOUT ANTIGO COM PAGAMENTO

Se o checkout encontrado pela chave antiga possuir pagamento:

bloquear nova venda

Não trocar itens.

Não cancelar.

Não reutilizar.

14. NOVO INTENT + CHECKOUT ANTIGO COM INCERTEZA

Mesma regra:

bloquear
→ preservar state
→ resolver recovery técnico primeiro
15. NÃO USAR canEditFinancials COMO PRIMEIRO DECISOR

canEditFinancials é capability de edição, não definição suficiente de ownership da nova venda.

A ordem deve ser conceitualmente:

1. status terminal?
2. operação incerta?
3. pagamento aplicado?
4. mesmo intent ou novo intent?
5. checkout antigo pode ser cancelado?
6. só então capabilities

Não começar com:

if (!checkout.canEditFinancials) return checkout;
16. CRIAR UMA DECISÃO CENTRAL DE "CHECKOUT ANTIGO"

Evitar espalhar regras em vários if.

Criar helper(s) claros se fizer sentido.

Exemplo conceitual:

_resolvePersistedQuickSaleBeforeNewIntent(...)

ou equivalente.

O objetivo é que:

createQuickSaleCheckout()

não tenha vários caminhos diferentes reaproveitando checkout antigo sem a mesma política.

17. _replaceHistoricalQuickCheckout()

Revisar essa função.

Ela hoje ainda é usada para trocar instância quando os itens mudam e há histórico.

Garantir que ela NÃO seja usada para transformar arbitrariamente um checkout velho em uma nova venda.

Se tiver pagamento histórico:

não cancelar silenciosamente

Se for checkout sem pagamento antigo:

cancelar antigo
→ criar novo

de forma explícita.

18. updateQuickSaleCheckout()

Hoje updateQuickSaleCheckout() também chama:

recoverQuickSaleCheckout()

Revisar para que recuperação técnica não volte a trazer um checkout de outro intent.

Esse método deve editar apenas o checkout atual pertencente à operação em curso.

Se detectar state incompatível:

não trocar ownership silenciosamente
19. checkout_requires_new_instance

No tratamento desse erro existe recovery.

Preservar o tratamento, mas aplicar as mesmas regras:

mesmo checkout atual
→ pode criar nova instância conforme regra

Não deixar essa exceção abrir caminho para recuperar checkout antigo de outra operação.

20. takeRecoveredQuickSaleResult()

Alterar API se necessário.

Preferir algo como:

takeRecoveredQuickSaleResult(checkoutId)

ou equivalente.

Se o resultado armazenado não pertencer ao checkout solicitado:

return null

Nunca entregar resultado de outra venda.

21. SHARED PAYMENT PAGE

Hoje existe caminho semelhante a:

final recovered = widget.controller.takeRecoveredQuickSaleResult();

Revisar.

A tela sabe:

_checkout.id

Então qualquer recovered result consumido deve corresponder exatamente a esse checkout.

22. NÃO RESTAURAR VENDA VISUALMENTE

Preservar:

QuickSalePage abre limpa

Não reintroduzir:

Venda em andamento recuperada
_restoreCheckoutDraft()
_resumeCheckout()
23. SAÍDA NORMAL DA TELA DE PAGAMENTO

Preservar:

sem pagamento
→ cancelar checkout
→ aguardar confirmação
→ depois sair

e:

com pagamento
→ não sair
→ concluir ou estornar
24. RECOVERY TÉCNICO APÓS CRASH

Se o app reiniciar com operação incerta:

não fingir que não existe

Mas também:

não abrir automaticamente como venda normal

Resolver internamente e bloquear nova venda enquanto houver risco financeiro.

25. IMPRESSÃO — NÃO REGREDIR

A parte de impressão deste HEAD está aprovada.

Preservar:

pollPrintDocument = 15 tentativas / 2s;
Conferência com guard _polling;
Conferência inicia polling ao abrir queued;
PAYMENT_RECEIPT Mesa inicia polling ao carregar queued;
PAYMENT_RECEIPT Venda Rápida inicia polling ao carregar queued;
Sets de guards por payment;
produção com polling de até ~30s;
FAILED BEFORE SEND → TENTAR NOVAMENTE;
UNCERTAIN → sem retry automático;
REPRINT → tarja preta;
Solicitar Conta → automatic_only=False;
uma única impressão inicial;
datas brasileiras;
desconto consolidado;
dedupe de TOTAL/Taxa;
Tickets respeitando POS/override;
Mesa vazia bloqueada;
fechamento da Mesa voltando ao grid.
26. CENÁRIO A — CHECKOUT ANTIGO SEM PAGAMENTO
Venda A
→ checkout OPEN
→ sem pagamento
→ app fecha

abre Venda Rápida
→ tela limpa

monta Venda B
→ iniciar pagamento

sistema encontra checkout A
→ cancela A
→ cria checkout B

B nunca usa ID de A.

27. CENÁRIO B — CHECKOUT ANTIGO COM PAGAMENTO
Venda A
→ checkout OPEN
→ pagamento aplicado
→ app fecha

abre Venda Rápida
→ monta Venda B
→ tenta continuar

BLOQUEAR

Mensagem:

Existe uma venda anterior com pagamento aplicado.
Conclua ou estorne antes de iniciar uma nova venda.

Não abrir B com checkout A.

28. CENÁRIO C — FINALIZED ANTIGO
checkout A = FINALIZED
→ state local antigo
→ nova Venda B

Resultado:

limpar state de A
→ criar checkout B

Nunca:

return checkout A
29. CENÁRIO D — FINALIZAÇÃO INCERTA RECUPERADA
Venda A
→ finalize enviado
→ resposta perdida
→ recovery confirma sale A

Resultado recuperado:

só pode ser consumido pela operação/tela de A

Nunca pela Venda B.

30. CENÁRIO E — MESMO CREATE INCERTO
request A
→ create enviado
→ resposta perdida

Nova tentativa com:

mesma creation idempotency key
mesmo creation_request

Pode recuperar o mesmo checkout.

Isso deve continuar.

31. CENÁRIO F — REQUEST DIFERENTE
creation_request salvo = A
novo request = B

Não atualizar checkout A para virar B.

Tratar B como novo intent.

32. CHECKPOINT

Ao terminar informe:

qual era o caminho que permitia checkout antigo com pagamento ser devolvido;
como reorganizou a ordem das validações;
como trata checkout OPEN sem pagamento;
como trata checkout OPEN com pagamento;
como trata operação incerta;
como trata FINALIZED;
como trata CANCELLED;
como diferencia mesmo intent de novo intent;
como trata creation_request diferente;
se _replaceHistoricalQuickCheckout() foi alterado;
se updateQuickSaleCheckout() foi alterado;
como checkout_requires_new_instance ficou seguro;
como _recoveredQuickSaleResult foi escopado;
como takeRecoveredQuickSaleResult() impede consumo cruzado;
como SharedPaymentPage consome recovered result;
se a UI continua sem recovery visual;
se recovery técnico/idempotência foram preservados;
se todas as correções de impressão permaneceram intactas;
arquivos Flutter alterados;
arquivos backend alterados — idealmente nenhum;
migrations criadas — não deveria precisar;
pontos restantes para teste manual.
REGRA CRÍTICA

NÃO EXECUTE TESTES.

NÃO execute:

flutter analyze
flutter test
flutter build
flutter run
pytest
npm test
npm build
npm lint
suites
makemigrations --check

Eu farei os testes manualmente.

NÃO mexer no Android/Kotlin nesta missão.

Depois pare.