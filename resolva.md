POS-3 — RODADA FINAL DE PERFORMANCE + PENDÊNCIAS CRÍTICAS

Você já tem todo o contexto do projeto.

Base atual:
main no commit mais recente após "crticos pre-pos4".

Esta rodada NÃO é para adicionar funcionalidade nova.
É para corrigir PERFORMANCE do CORE POS e fechar as últimas pendências encontradas na auditoria.

NÃO iniciar POS-4.
NÃO alterar missao.md.
NÃO commitar missao.md.
NÃO criar arquitetura paralela.
NÃO fazer refatoração ampla fora do necessário.

==================================================
IMPORTANTE — NÃO CRIAR/RODAR TESTES AUTOMATIZADOS
==================================================

NÃO criar testes automatizados nesta rodada.
NÃO criar arquivos de teste.
NÃO rodar suíte Django.
NÃO rodar testes Flutter.
NÃO fazer build completo.

Queremos primeiro corrigir e medir o runtime REAL.

Validações permitidas:

- python manage.py check, se necessário;
- dart format somente nos Dart tocados;
- dart analyze focado;
- git diff --check;
- inspeção manual;
- chamadas reais no ambiente rodando;
- logs [POS PERF] / [POS SERVER].

==================================================
1. PROBLEMA DE PERFORMANCE CONFIRMADO
==================================================

Logs reais atuais:

AVAILABILITY:

POS device_auth_ms=595
POS operator_session_auth_ms=741
POS permission_context_ms=842
POS view_ms=1516
total_ms=1556

PREVIEW:

POS device_auth_ms=805
POS operator_session_auth_ms=893
POS permission_context_ms=999
POS view_ms=1898
total_ms=1919

IMPORTANTE:

Os tempos possuem hierarquia.

device_auth acontece antes do context.

operator_session_auth está DENTRO de permission_context.

Então, aproximadamente:

Availability:
device auth ~595ms
permission context ~842ms
restante da view ~79ms

Preview:
device auth ~805ms
permission context ~999ms
restante da view ~94ms

Conclusão:

O cálculo de estoque/financeiro NÃO é hoje o principal gargalo.

O problema está principalmente em:

- autenticação do device;
- autenticação da operator session;
- validações repetidas;
- resolução repetida de RBAC;
- várias requests sequenciais para uma única inclusão.

NÃO começar otimizando a engine financeira/estoque sem evidência.

==================================================
2. DEVICE CREDENTIAL — NÃO USAR PASSWORD HASH CARO EM TODA REQUEST
==================================================

Hoje o device credential possui:

credential_hash
credential_fingerprint

credential_fingerprint já é criado com HMAC usando SECRET_KEY:

_secret_fingerprint(credential)

e é indexado.

Mesmo assim, authenticate_device():

1. calcula fingerprint;
2. encontra o device;
3. ainda executa check_password(credential, credential_hash)
   em TODA request.

Device credential é um token aleatório de alta entropia gerado pelo servidor.

NÃO é senha humana.
NÃO é PIN.

Não precisamos pagar o custo de password hashing adaptativo em toda chamada normal depois de termos um fingerprint HMAC secreto e indexado.

==================================================
3. NOVO FAST PATH DE DEVICE AUTH
==================================================

Para devices modernos que possuem:

credential_fingerprint != ''

usar o fingerprint HMAC como lookup/autenticação normal.

Conceitualmente:

fingerprint = HMAC(SECRET_KEY, credential)

device = POSDevice.objects
    .select_related('branch__company')
    .filter(
        credential_fingerprint=fingerprint,
        status=ACTIVE,
    )
    .first()

Se encontrou:
→ credential autenticada.

NÃO executar check_password no caminho normal.

Motivo de segurança:

credential_fingerprint NÃO é SHA simples.
É HMAC utilizando SECRET_KEY.

Não trocar por hash público simples.

NÃO armazenar credential em claro.

credential_hash pode continuar existindo por compatibilidade/migração,
mas não deve ser validado com algoritmo caro a cada request moderna.

==================================================
4. FALLBACK LEGADO DO DEVICE
==================================================

Preservar compatibilidade com registros antigos onde:

credential_fingerprint == ''

Somente nesse caso:

→ procurar candidatos legados;
→ validar com check_password();
→ se válido:
    preencher credential_fingerprint;
→ próximas requests usam fast path.

Ou seja:

MODERNO:
HMAC lookup
→ direto.

LEGADO:
check_password uma vez
→ backfill fingerprint
→ depois fast path.

NÃO fazer fallback varrendo grande quantidade de devices modernos.

==================================================
5. OPERATOR SESSION TOKEN — MESMO PROBLEMA
==================================================

POSOperatorSession já possui:

token_hash
token_fingerprint

O token da sessão também é gerado aleatoriamente pelo backend.

Hoje authenticate_operator_session():

1. calcula fingerprint;
2. encontra sessão;
3. ainda executa check_password(token, token_hash)
   em TODA request.

Remover o custo de password hashing do caminho normal da operator session.

Para:

token_fingerprint != ''

usar:

HMAC fingerprint
+
device
+
ended_at IS NULL
+
expires_at > now

como lookup normal.

Não comparar token em claro.
Não salvar token em claro.

==================================================
6. FALLBACK LEGADO DA OPERATOR SESSION
==================================================

Para sessões antigas com:

token_fingerprint == ''

manter fallback:

check_password()
→ se válido:
    persistir token_fingerprint
→ próximas requests fast path.

Mesmo princípio do device.

==================================================
7. NÃO MEXER NO HASH DE PIN E SENHA
==================================================

ATENÇÃO:

Essa otimização vale APENAS para:

- device credential aleatória;
- operator session token aleatório.

NÃO aplicar em:

- PIN de operador;
- PIN de autorizador;
- senha do Backoffice;
- OTP humano quando aplicável.

PIN e senha humana DEVEM continuar usando mecanismo seguro apropriado.

Não transformar PIN em HMAC lookup simples.

==================================================
8. REMOVER VALIDAÇÃO DUPLICADA DO DEVICE NA MESMA REQUEST
==================================================

Hoje existe trabalho duplicado.

Fluxo aproximado:

POSDeviceAuthentication
→ authenticate_device()
→ validate_device_operational()

depois a view:

context()
→ self.device()
→ validate_device_operational() novamente.

Isso não faz sentido dentro da MESMA request.

Criar request-scoped device context.

Depois de POSDeviceAuthentication autenticar:

request.pos_device = device validado

A view deve reutilizar esse mesmo objeto.

Não buscar/refazer toda validação operacional novamente.

Se determinada view precisa de:

version_gate

fazer somente o gate necessário sobre o device já autenticado,
sem refazer autenticação e queries inteiras.

==================================================
9. DEVICE DEVE VIR COM branch/company JÁ CARREGADOS
==================================================

Authenticate device usando:

select_related('branch__company')

ou equivalente.

Depois:

request.pos_device.branch
request.pos_device.branch.company

não devem causar queries adicionais desnecessárias.

Evitar refetch do mesmo POSDevice dentro da request.

==================================================
10. OPERATOR SESSION — NÃO PERCORRER TODOS OS OPERADORES
==================================================

Hoje authenticate_operator_session():

depois de encontrar a sessão chama:

eligible_operator(device.branch, session.operator_id)

E eligible_operator usa pos_operator_queryset(),
que monta candidatos da filial e pode avaliar permissões para vários usuários.

Isso é desnecessário.

Estamos autenticando UM operador específico.

Criar caminho direto de elegibilidade.

Conceitualmente:

eligible_pos_operator(branch, user_id)

deve verificar SOMENTE aquele usuário:

- user ativo;
- archived_at null;
- can_access_pos true;
- branch access ativo;
- AccessProfile ativo;
- company access ativo;
- SaaS status correto;
- empresa/filial operacionais;
- PIN configurado quando isso for requisito da elegibilidade;
- possuir ao menos uma permission operacional efetiva;
- UserPermissionBlock respeitado.

Mas sem iterar todos os usuários da filial.

==================================================
11. NÃO RESOLVER RBAC DUAS VEZES
==================================================

Hoje existe possibilidade de:

authenticate_operator_session()
→ eligibility
→ permission resolution

e logo depois:

POSCashView.context()
→ operator_permission_codes()

novamente.

Dentro da mesma request devemos resolver permissões efetivas uma vez.

Criar contexto request-scoped, conceitualmente:

POSRequestContext {
    device
    operator_session
    operator
    permission_codes
}

ou equivalente simples.

Não precisa criar framework gigante.

Objetivo:

uma request
→ uma autenticação device
→ uma autenticação session
→ uma resolução permissionária.

==================================================
12. PRESERVAR REVOGAÇÃO IMEDIATA DE ACESSO
==================================================

NÃO resolver performance fazendo cache longo de permissions entre requests.

Se alguém:

- bloquear UserPermissionBlock;
- remover permission;
- remover branch access;
- desativar can_access_pos;
- suspender usuário;

a próxima request precisa perceber.

Pode haver cache SOMENTE dentro da request.

Não criar cache de 5 minutos, Redis ou memória de processo para RBAC nesta rodada.

==================================================
13. ADICIONAR INSTRUMENTAÇÃO GRANULAR
==================================================

Antes/depois da otimização, queremos saber exatamente os tempos.

Adicionar logs leves como:

POS device_auth_lookup_ms=
POS device_auth_operational_ms=

POS operator_session_lookup_ms=
POS operator_eligibility_ms=
POS permission_resolution_ms=

Não registrar:

credential
token
PIN
hash
fingerprint completo.

Manter também:

POS device_auth_ms
POS operator_session_auth_ms
POS permission_context_ms
POS view_ms
POS total_ms

para comparação.

==================================================
14. OBJETIVO DE PERFORMANCE DA AUTENTICAÇÃO
==================================================

Não inventar números de benchmark.

Após implementar, medir no ambiente real.

Esperamos redução GRANDE porque password hashing deixa de ocorrer em toda request.

Não declarar resolvido antes de medir.

Entregar logs reais comparando:

ANTES
vs
DEPOIS

para:

/sales/availability/
/sales/preview/

==================================================
15. FLUXO ATUAL DO CARRINHO FAZ REQUESTS DEMAIS
==================================================

Hoje uma inclusão normal pode fazer:

1. POST /sales/availability/     preflight
2. POST /sales/availability/     revalidation
3. POST /sales/preview/

Tudo sequencial.

Isso gera sensação de lentidão.

Com ~1-2 segundos por request,
o usuário pode esperar vários segundos até ver o preço oficial.

Precisamos manter:

VERIFICAÇÃO ANTES
+
VERIFICAÇÃO DEPOIS

mas não obrigatoriamente em 3 requests separadas.

==================================================
16. NOVO FLUXO DE ADIÇÃO
==================================================

Fluxo desejado:

TOQUE NO PRODUTO
        ↓
fast check local
        ↓
candidate cart em memória
        ↓
POST /sales/availability/   ← preflight
        ↓
aprovado?
        ↓
SIM
        ↓
commit no carrinho
        ↓
mostrar item + preço provisório imediatamente
        ↓
POST /sales/preview/
        ↓
preview também faz REVALIDAÇÃO READ-ONLY do estoque
        ↓
retorna financeiro oficial
        ↓
substitui valor provisório pelo oficial.

Portanto:

ANTES:
availability
availability
preview

DEPOIS:
availability
preview com revalidation

2 requests.

==================================================
17. PREVIEW DEVE REVALIDAR ESTOQUE
==================================================

No POSSalePreviewView:

antes de calcular financeiro oficial,
executar a mesma disponibilidade canônica:

assess_sale_stock_availability(
    company=...,
    raw_items=...,
    branch=...,
    channel=COUNTER,
)

Se:

available=false
AND
enforced=true

preview NÃO deve calcular estado como válido.

Retornar erro operacional estruturado/amigável contendo shortages.

Não criar segunda engine.

Reutilizar:

assess_sale_stock_availability()

Depois, se disponível:

calculate_preview()

Esse preview passa a ser também a revalidação pós-inclusão.

==================================================
18. NÃO USAR LOCK NO PREVIEW
==================================================

Preview continua read-only.

NÃO usar select_for_update.
NÃO colocar transaction.atomic só para stock check.

Finalização continua sendo autoridade transacional e usa locks.

Fluxo:

preflight availability
→ preview/revalidation
→ finalize_sale com locks

==================================================
19. SE PREVIEW DESCOBRIR ESTOQUE ALTERADO
==================================================

Exemplo:

preflight aprovou Coca x2.

Antes do preview outra máquina vendeu estoque.

Preview revalida e retorna shortage.

Flutter:

→ reverte somente a mutation que acabou de ser aprovada;
→ restaura lastValidatedCart anterior;
→ mostra mensagem amigável;
→ não mantém item inválido.

Preservar:

generation
latest-state-wins
single-flight.

==================================================
20. RESTAURAR FAST-PATH product.canSell
==================================================

No commit recente foi removido o bloqueio local:

if (!product.canSell) {
    ...
    return;
}

Restaurar.

Se o catálogo já informou:

stock_applicable=true
stock_available=false
can_sell=false

NÃO fazer request ao backend só para descobrir novamente que não pode vender.

Mostrar imediatamente:

"Este produto está sem estoque no momento."

Isso é somente otimização/UX.

Backend continua protegendo todas as requests.

==================================================
21. NÃO BLOQUEAR QUANDO NEGATIVO É PERMITIDO
==================================================

Se catálogo informa:

canSell=true

mesmo:

stockAvailable=false

porque:

allow_negative_stock=true

deve permitir seguir para preflight.

Não confundir:

stockAvailable
com
canSell.

==================================================
22. PREÇO PROVISÓRIO IMEDIATO
==================================================

Hoje o carrinho mostra:

officialLine == null
? '--'
: preço

Isso faz parecer que o sistema travou.

NÃO mostrar "--" para uma linha que acabou de entrar.

O catálogo já possui:

QuickSaleProduct.price

E modifiers já possuem:

additionalPrice

Calcular SOMENTE para exibição um valor provisório simples:

(base sale price + modifier additional prices) * quantity

e exibir imediatamente.

Exemplo:

Coca R$ 8,00
→ tocou
→ carrinho já mostra R$ 8,00

Não esperar preview para mostrar alguma coisa.

==================================================
23. VALOR PROVISÓRIO NÃO É AUTORIDADE FINANCEIRA
==================================================

Muito importante:

NÃO usar cálculo Flutter para:

- fechar venda;
- definir total oficial;
- calcular promoção oficial;
- calcular service fee;
- calcular comissão;
- decidir pagamento.

É APENAS placeholder visual enquanto preview está carregando.

O preview backend continua sendo autoridade.

Quando preview chegar:

valor provisório
→ substituído pelo officialLine.lineTotal.

Se houver promoção:

R$ 10 provisório
→ preview pode atualizar para R$ 8 oficial.

Isso é esperado.

==================================================
24. INDICADOR VISUAL DISCRETO
==================================================

Enquanto officialLine ainda não chegou,
pode mostrar o valor provisório normalmente
e um indicador pequeno de atualização.

Exemplo:

R$ 8,00
Atualizando...

Não deixar:

--

como conteúdo principal.

Não deixar interface pulando excessivamente.

==================================================
25. BOTÃO DE PAGAMENTO CONTINUA BLOQUEADO
==================================================

Mesmo mostrando preço provisório:

IR PARA PAGAMENTO

continua exigindo:

preview oficial != null
loadingPreview = false

Não permitir checkout baseado apenas no preço local.

==================================================
26. PREVIEW SINGLE-FLIGHT CONTINUA
==================================================

Preservar:

debounce
single-flight
pending latest preview
generation

Não criar preview paralelo descontrolado.

Se usuário tocar rapidamente:

tap
tap
tap

coalescer as intenções quando possível.

Não enviar previews de estados intermediários inúteis.

==================================================
27. AVAILABILITY — NÃO VALIDAR MUTATION UMA POR UMA QUANDO TODAS PASSAM
==================================================

Hoje:

candidate completo
→ availability

Se falhar, _acceptedCartMutations pode verificar mutations individualmente.

Isso pode ser usado somente no caminho de RECUPERAÇÃO.

No caso normal:

candidate completo disponível
→ 1 request availability.

Não transformar todo carrinho em N requests.

==================================================
28. RESET COMPLETO APÓS VENDA CONCLUÍDA
==================================================

Ainda existe uma pendência grave.

"Apagar carrinho" limpa:

- draft;
- lastValidatedCart;
- pendingCartMutations;
- availability state;
- preview state.

Mas onSaleCompleted atualmente limpa basicamente:

_draft.clearAfterSale()

e alguns estados de preview.

Isso pode deixar:

_lastValidatedCart

da venda anterior vivo.

Corrigir.

Criar UM helper central, por exemplo conceitual:

_resetSaleDraftState()

Esse helper deve limpar atomicamente:

- _draft;
- _lastValidatedCart;
- _pendingCartMutations;
- availability generation;
- availability debounce;
- pending availability;
- preview generation;
- preview debounce;
- pending preview;
- loading preview.

Usar o MESMO helper em:

1. venda concluída;
2. apagar carrinho.

Não ter dois resets diferentes.

==================================================
29. CARRINHO VAZIO
==================================================

Quando a última linha for removida:

cart=[]
lastValidatedCart=[]
pendingMutations=[]
preview=null
loadingPreview=false

Cancelar debounce/pending request antigo.

Não deixar preview da venda anterior na tela.

==================================================
30. AUDITORIA DE AUTORIZAÇÃO POR PIN — ACTOR ERRADO
==================================================

Ainda existe:

actor=approver

em tentativas:

pos.authorization.failed
pos.authorization.rate_limited

Isso é semanticamente incorreto.

Exemplo:

Operador Pedro está logado.

Pedro seleciona gerente João.

Pedro digita PIN errado.

Audit atual pode registrar:

actor = João

Mas não sabemos se João digitou o PIN.

Quem iniciou a operação foi Pedro.

==================================================
31. ACTOR CORRETO
==================================================

Passar o operador atualmente autenticado para:

validate_pos_authorization()

ou contexto equivalente.

Audit:

actor
→ operador logado que iniciou a tentativa.

metadata:

authorizer_user_id
→ gerente selecionado.

Exemplo:

actor_user_id = Pedro
authorizer_user_id = João
permission_code = sales.apply_discount
device_id = ...

No sucesso pode registrar claramente:

requested_by
approved_by

ou metadata equivalente.

Não registrar PIN.

==================================================
32. ALTERAR FLUXO DE AUTHORIZATION SEM DUPLICAR RBAC
==================================================

Não criar outra função paralela de permissão.

Somente adicionar o requester/operator ao contexto da autorização.

A elegibilidade do approver continua canonical:

eligible_pos_authorizers()
+
permission específica
+
branch
+
blocks
+
can_access_pos
+
PIN.

==================================================
33. NÃO REGISTRAR SEGREDOS
==================================================

Em nenhum log/perf/audit registrar:

device credential
operator token
PIN
password
credential_hash
token_hash
pos_pin_hash
fingerprint completo.

Performance logs só podem registrar:

tempo
IDs não secretos quando necessários
view/action.

==================================================
34. NÃO REGREDIR O QUE JÁ FOI CORRIGIDO
==================================================

Preservar:

- RBAC company/branch;
- UserPermissionBlock;
- can_access_pos;
- POS-only can_login=false;
- Cash Summary;
- Superuser sem bypass POS;
- autorização por PIN;
- rate limit;
- descontos;
- item discount;
- service fee authorization;
- clientes;
- show_out_of_stock_products;
- allow_negative_stock;
- InventoryBehavior.NONE;
- componentes;
- frações;
- barcode;
- mensagens amigáveis;
- unidade und/unds/kg/g/L/ml;
- long press;
- latest-state-wins;
- idempotência;
- finalize_sale;
- produção;
- tickets existentes.

NÃO iniciar POS-4.

==================================================
35. MEDIÇÃO OBRIGATÓRIA APÓS ALTERAÇÃO
==================================================

Não criar testes automatizados.

Depois das alterações, subir o ambiente normal e medir manualmente.

Executar pelo menos:

A)
adicionar produto DIRECT simples.

Registrar:

availability
preview

B)
adicionar produto COMPONENTS.

C)
adicionar produto sem controle de estoque.

D)
3 taps rápidos.

E)
produto zerado canSell=false.

Para cada chamada relevante registrar:

POS device_auth_lookup_ms
POS device_auth_operational_ms
POS device_auth_ms

POS operator_session_lookup_ms
POS operator_eligibility_ms
POS operator_session_auth_ms

POS permission_resolution_ms
POS permission_context_ms

POS view_ms
POS total_ms

==================================================
36. O QUE QUERO VER DEPOIS
==================================================

ANTES temos exemplos reais:

Availability:
device_auth=595ms
permission_context=842ms
view=1516ms
total=1556ms

Preview:
device_auth=805ms
permission_context=999ms
view=1898ms
total=1919ms

Depois da mudança entregue os novos logs reais.

Não diga:

"ficou rápido"

sem números.

==================================================
37. PERFILAMENTO SE AINDA FICAR LENTO
==================================================

Se depois de remover password hashing por request e duplicações ainda houver lentidão:

NÃO sair refatorando tudo.

Usar os novos timings para identificar precisamente:

- DB lookup;
- eligibility;
- RBAC;
- availability;
- preview financeiro;
- serialization.

E relatar antes de outra mudança grande.

==================================================
38. CONFIGURAÇÃO "MOSTRAR PRODUTOS SEM ESTOQUE"
==================================================

Preservar o que foi implementado.

Padrão da filial:

branches/{branch}/pos-settings/

Campo:

show_out_of_stock_products

Override:

pos/admin/devices/{device}/settings/

A UI já possui:

"Mostrar produtos sem estoque"

e:

"Usar padrão da filial"

Não remover.

==================================================
39. SEM MIGRATION DESNECESSÁRIA
==================================================

A princípio essa rodada NÃO precisa de alteração de model.

Já existem:

credential_fingerprint
token_fingerprint

Não criar novos campos equivalentes sem necessidade.

Não criar migration só para performance.

==================================================
40. VALIDAÇÃO LEVE
==================================================

NÃO criar testes automatizados.

Executar somente:

- python manage.py check se necessário;
- dart format arquivos tocados;
- dart analyze focado;
- git diff --check;
- execução manual no ambiente real;
- captura dos timings reais.

NÃO rodar full test suite.
NÃO rodar flutter test.
NÃO rodar Django tests.
NÃO fazer build completo.

==================================================
41. CHECKPOINT FINAL
==================================================

Ao terminar:

PARE.

NÃO iniciar POS-4.

Entregar exatamente:

1. commit/base utilizado;
2. arquivos alterados;
3. causa do device_auth lento;
4. como device credential passou a ser autenticada;
5. como funciona fallback legado;
6. causa do operator_session_auth lento;
7. como operator token passou a ser autenticado;
8. confirmação de que PIN/senha humana continuam com hash forte;
9. como eliminou validate_device duplicado;
10. como eliminou lookup/eligibility desnecessário;
11. como permission resolution ficou uma vez por request;
12. fluxo antigo de requests por add;
13. fluxo novo de requests por add;
14. como preview revalida estoque;
15. confirmação de que finalização continua com locks;
16. como preço provisório funciona;
17. confirmação de que preço provisório nunca é usado para finalizar;
18. comportamento de canSell=false;
19. reset completo após venda concluída;
20. comportamento ao remover último item;
21. correção do actor da auditoria PIN;
22. logs reais ANTES/DEPOIS de availability;
23. logs reais ANTES/DEPOIS de preview;
24. número real de requests para adicionar 1 produto simples;
25. qualquer gargalo que ainda permaneça;
26. confirmação de que missao.md não foi alterado;
27. confirmação de que nenhum teste automatizado foi criado/rodado;
28. confirmação de que POS-4 NÃO foi iniciado.

NÃO declarar POS-3 encerrado sozinho.

Finalizar dizendo apenas:

"Rodada de performance concluída e pronta para auditoria."

Nós vamos revisar o GitHub e os logs antes de considerar oficialmente o POS-3 fechado.