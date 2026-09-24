Continue no HEAD atual.

Na última revisão, o HEAD era:

`f2b11d2e718dad4332174dc30b1f5dca9067bb21`

Antes de alterar, confira o HEAD atual.

A parte principal de `PrintRoute` / `PrintRouteOverride` foi corrigida, mas ainda ficou uma inconsistência de UX/contexto de filial no Backoffice que pode fazer o usuário configurar a filial errada.

---

# 1. PROBLEMA ATUAL

Na tela:

```text
/pos-dispositivos

existe um seletor local de filial:

branchId
settingsBranchId

Agora os overrides de impressão usam corretamente esse settingsBranchId.

Exemplo:

Topo global:
Filial A

Tela Dispositivos POS:
seleciona Filial B

Overrides:
trabalham na Filial B ✅

Porém o botão:

Configurar regras da filial

continua navegando somente para:

/producao/rotas-impressao

Essa página usa o currentBranch global.

Então pode acontecer:

currentBranch global = Filial A

/pos-dispositivos:
filial selecionada localmente = Filial B

→ clicar "Configurar regras da filial"

→ /producao/rotas-impressao abre Filial A

O operador pode achar que está configurando a Filial B, mas salva a rota na Filial A.

CORRIGIR.

2. OBJETIVO

Não pode existir ambiguidade sobre qual filial está sendo configurada.

Ao sair de:

Dispositivos POS
→ Filial B
→ Configurar regras da filial

a tela:

Produção → Rotas de impressão

deve abrir necessariamente na:

Filial B
3. PREFERÊNCIA DE ARQUITETURA

A preferência é usar o contexto global de filial como fonte principal de verdade.

Ou seja:

currentBranch

deve representar a filial operacional atual do Backoffice.

Evitar manter dois contextos independentes de filial para funcionalidades branch-scoped.

Se for viável sem expandir demais a missão:

seletor local da tela
→ ao mudar filial
→ atualizar currentBranch global

e então todas as telas branch-scoped usam o mesmo contexto.

4. CASO NÃO QUEIRA REMOVER O SELETOR LOCAL AGORA

Se preservar:

branchId / settingsBranchId

dentro de /pos-dispositivos, então o botão:

Configurar regras da filial

deve sincronizar o contexto global antes de navegar.

Exemplo conceitual:

settingsBranchId = B
→ setCurrentBranchId(B)
→ navegar para /producao/rotas-impressao

Não fazer apenas:

<Link href="/producao/rotas-impressao">

sem sincronizar a filial.

5. NÃO USAR QUERY PARAM COMO ÚNICA FONTE DE VERDADE

Evitar solução frágil como:

/producao/rotas-impressao?branch=2

enquanto o header global continuar dizendo outra filial.

Se usar query param temporariamente, a página deve sincronizar o currentBranch global imediatamente.

A UI inteira precisa concordar sobre a filial.

6. HEADER GLOBAL

Depois da navegação, o seletor do topo deve mostrar a mesma filial:

Filial B

Não pode ficar:

Topo: Filial A
Tela: Filial B
7. DOCUMENT PRINT ROUTES

Preservar a correção atual de:

DocumentPrintRoutes({
    posDeviceId,
    branchId
})

e o uso de:

effectiveBranchId

com:

X-Branch-ID

Não regredir isso.

8. MELHORAR LABEL DA FILIAL

Hoje, quando DocumentPrintRoutes recebe branchId, a UI pode mostrar algo como:

Filial: 2

Isso não é bom.

Mostrar o nome da filial.

Exemplo:

Filial: Matriz

Pode resolver usando:

currentBranch

quando sincronizado corretamente,

ou buscando o nome correspondente em:

user.branches

Não exibir ID técnico para o usuário.

9. OVERRIDES

Preservar a lógica atual:

sem override
→ herda filial

inherit_branch = true
→ herda filial

inherit_branch = false
→ usa override

Não alterar effective_print_route() novamente sem necessidade.

10. "USAR REGRA DA FILIAL"

Preservar:

DELETE override
→ reload
→ Herdando da filial
→ configuração efetiva atualizada

Não voltar a atualizar apenas estado local sem reload.

11. CONFIGURAÇÃO EFETIVA

Continuar mostrando no override:

Herdando da filial

Modo efetivo: Manual/Automático/Desabilitado
Impressoras efetivas: ...
Cópias: ...

Se possível, traduzir os modos para o usuário:

manual → Manual
automatic → Automático
disabled → Desabilitado

Evitar mostrar valor técnico em inglês.

12. CENÁRIO ESPERADO

Exemplo:

Empresa: 25 Lounge

Topo global:
Matriz

/pos-dispositivos:
seleciona Filial Centro

→ Overrides passam a usar Filial Centro

→ clicar "Configurar regras da filial"

→ currentBranch global muda para Filial Centro

→ abre /producao/rotas-impressao

→ topo mostra Filial Centro

→ GET print-routes usa X-Branch-ID da Filial Centro

→ salvar Conferência = Manual

→ volta depois e continua Manual na Filial Centro
13. CENÁRIO DE TROCA

Depois:

Topo global:
Filial Centro

→ trocar para Matriz

→ /producao/rotas-impressao
→ recarrega rotas da Matriz

Não carregar dados da filial anterior.

14. NÃO ALTERAR BACKEND SEM NECESSIDADE

O backend atual de resolução está correto:

override = PrintRouteOverride.objects.filter(
    pos_device=pos_device,
    document_type=document_type,
).first()

return route if override is None or override.inherit_branch else override

Preservar isso.

A missão agora é principalmente corrigir consistência de contexto de filial no frontend.

15. NÃO REGREDIR CORREÇÕES ANTERIORES

Preservar:

resolução correta de PrintRoute;
resolução correta de PrintRouteOverride;
inherit_branch;
X-Branch-ID explícito;
mensagem detalhada de rota desabilitada;
polling de produção;
polling de PrintDocument;
PAYMENT_RECEIPT;
Conferência;
hash + fallback legado;
UNCERTAIN;
fechamento de Mesa;
quantidade formatada;
retry != reprint;
impressão NETWORK.
ARQUIVOS A REVISAR

No mínimo:

frontend/src/app/(private)/pos-dispositivos/page.tsx
frontend/src/components/document-print-routes.tsx
frontend/src/providers/auth-provider.tsx
frontend/src/lib/http.ts

Talvez não seja necessário alterar todos.

Alterar apenas o necessário.

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

CHECKPOINT

Ao terminar informe:

como eliminou a divergência entre settingsBranchId e currentBranch;
o que acontece ao clicar "Configurar regras da filial";
se o header global passa a refletir a filial correta;
se /producao/rotas-impressao usa a mesma filial;
se o X-Branch-ID continua correto;
se a UI agora mostra o nome da filial em vez do ID;
se os modos herdados aparecem traduzidos;
arquivos frontend alterados;
arquivos backend alterados — idealmente nenhum;
migrations criadas — não deveria precisar;
pontos restantes para teste manual.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.

Depois pare.