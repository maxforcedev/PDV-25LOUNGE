Continue no HEAD atual.

Problema encontrado no POS:

Praticamente todas as ações de impressão estão retornando:

`A rota deste documento está desabilitada.`

Revise e corrija o fluxo completo de resolução de rotas.

Hoje a arquitetura correta deve ser:

```text
PrintRoute da filial
        ↓
POS sem override
        ↓
herda exatamente a regra da filial

POS com override explícito e inherit_branch=false
        ↓
usa o override do POS
1. NÃO ALTERAR A ARQUITETURA

Não quero hardcode de impressora.

Não quero IP salvo diretamente na Mesa/Venda.

Não quero ativar todas as impressões automaticamente.

Continuar usando:

PrintRoute
PrintRouteOverride
effective_print_route()
PrinterDevice
PrintDocument
PrintJob
2. INVESTIGAR POR QUE O POS ESTÁ RECEBENDO DISABLED

Revise:

ensure_print_routes()
effective_print_route()
issue_print_document()
enqueue_print_document()

Hoje ensure_print_routes() cria rotas novas com:

mode = DISABLED

Isso pode continuar sendo o default de segurança.

O problema a corrigir é:

se o usuário configurou a rota da filial como MANUAL ou AUTOMATIC, o POS não pode continuar recebendo DISABLED indevidamente.

Verifique:

filial do POSDevice;
branch usada na emissão;
PrintRoute carregada;
PrintRouteOverride;
inherit_branch;
document_type;
impressoras relacionadas;
contexto de filial do Backoffice.
3. OVERRIDE DO POS

A regra deve ser inequívoca.

Se NÃO existir override:

usar PrintRoute da filial

Se existir:

inherit_branch = true
→ usar PrintRoute da filial

Somente se:

inherit_branch = false

usar:

mode
printer_devices
copies
document_format

do override.

Um override antigo salvo como:

mode = disabled
inherit_branch = false

pode efetivamente bloquear o POS.

Isso é válido se foi configurado propositalmente, mas a UI precisa deixar isso extremamente claro.

4. BACKOFFICE — ROTAS DA FILIAL

Revise:

Produção
→ Rotas de impressão

A tela deve mostrar a configuração REAL da filial ativa.

Ao salvar:

Conferência → Manual
Comprovante de pagamento → Manual
Recibo final → Automático

o backend deve persistir exatamente esses valores para a filial correta.

Depois de atualizar a página, os mesmos valores devem continuar aparecendo.

Não pode salvar em outra filial por inconsistência de currentBranch.

5. POSSÍVEL INCONSISTÊNCIA DE FILIAL

Revise especialmente o uso de:

currentBranch
branchId
settingsBranchId

na tela de Dispositivos POS e nas Rotas de impressão.

Já identificamos anteriormente que pos-dispositivos possui seletor/local state de filial enquanto DocumentPrintRoutes usa o currentBranch global.

Não pode acontecer:

Tela mostra Filial B
mas DocumentPrintRoutes consulta/salva Filial A

Corrija se essa inconsistência ainda existir.

Para configuração de impressão por filial, deve haver UMA fonte de verdade clara para o branch usado pela API.

6. OVERRIDES NO BACKOFFICE

Em:

Dispositivos POS
→ Overrides de impressão por POS

deve ficar muito claro:

Herdando da filial

ou:

Override ativo

Se estiver herdando, mostrar também a configuração efetiva:

Exemplo:

Herdando da filial
Modo efetivo: Manual
Impressora efetiva: Cozinha
Cópias: 1

Não mostrar apenas "Herdando da filial" sem deixar claro o que está sendo herdado.

7. USAR REGRA DA FILIAL

Ao clicar:

Usar regra da filial

o resultado final deve ser:

nenhum override efetivo para aquele document_type/POS

e:

effective_print_route(...)

deve retornar a PrintRoute da filial.

Se a implementação atual deleta o override, preservar essa abordagem.

Garantir que o DELETE não deixe estado stale no frontend.

Depois de remover:

recarregar configuração
→ badge Herdando da filial
→ mostrar modo efetivo correto
8. TIPOS QUE PRECISAM SER REVISADOS

No mínimo:

TABLE_CONFERENCE
TABLE_FINAL_RECEIPT
QUICK_SALE_RECEIPT
PAYMENT_RECEIPT
TICKET
TABLE_BILL enquanto existir

Não corrigir apenas Conferência.

9. NÃO CONFUNDIR PRODUÇÃO COM ROTAS DE DOCUMENTOS

Produção continua:

Produto
→ ProductionDestination
→ PrinterDevice
→ ProductionJob
→ PrintJob

Documentos continuam:

PrintDocumentType
→ PrintRoute / PrintRouteOverride
→ PrinterDevice
→ PrintJob

Não usar PrintRoute para decidir destino de produção.

10. UX PARA ROTAS DESABILITADAS

Se uma rota estiver realmente desabilitada, manter o bloqueio.

Mas a mensagem precisa ajudar o operador.

Em vez de apenas:

A rota deste documento está desabilitada.

usar mensagem operacional mais útil, por exemplo:

A impressão de "Comprovante de pagamento" está desabilitada para este POS/filial. Configure em Produção > Rotas de impressão.

Se houver override responsável pelo bloqueio:

A impressão de "Comprovante de pagamento" está desabilitada por uma configuração específica deste POS.

Se possível identificar isso sem complicar a arquitetura.

11. NÃO ATIVAR TUDO AUTOMATICAMENTE

IMPORTANTE:

Não mudar ensure_print_routes() simplesmente para:

AUTOMATIC

ou:

MANUAL

sem impressora configurada.

Isso poderia gerar impressões inesperadas.

Novas filiais podem continuar começando com rotas desabilitadas.

O que precisamos corrigir é:

configuração salva
→ resolução efetiva correta
→ POS respeita a configuração
12. MELHORAR ONBOARDING DE IMPRESSÃO

Quando existir impressora NETWORK cadastrada mas rotas ainda estiverem desabilitadas, o Backoffice deve deixar claro:

Impressora cadastrada.

As rotas de documentos ainda precisam ser configuradas.

Mostrar CTA:

CONFIGURAR ROTAS DE IMPRESSÃO

Não deixar o usuário descobrir apenas quando o POS retornar erro.

13. CONFIGURAÇÃO ESPERADA PARA TESTE MANUAL

Depois da correção, vou configurar:

Conferência
Modo: Manual
Impressora: NETWORK cadastrada
Cópias: 1

Comprovante de pagamento
Modo: Manual
Impressora: NETWORK cadastrada
Cópias: 1

Recibo final da mesa
Modo: Manual ou Automático
Impressora: NETWORK cadastrada
Cópias: 1

Recibo venda rápida
Modo: Manual ou Automático
Impressora: NETWORK cadastrada
Cópias: 1

Sem override no POS.

Resultado esperado:

POS
→ herda filial
→ effective_print_route retorna MANUAL/AUTOMATIC
→ PrintJob criado
→ PrintManager imprime
14. CENÁRIO COM OVERRIDE

Depois vou configurar apenas:

PAYMENT_RECEIPT

com override nesse POS.

Resultado:

PAYMENT_RECEIPT
→ usa override

TABLE_CONFERENCE
→ continua herdando filial

TABLE_FINAL_RECEIPT
→ continua herdando filial

Um tipo não pode interferir no outro.

15. NÃO REGREDIR O QUE JÁ FOI CORRIGIDO

Preservar:

polling de produção;
UNCERTAIN;
polling de PrintDocument;
Conferência atualizada;
PAYMENT_RECEIPT;
hash novo + fallback legado;
1.000x → 1x;
Solicitar Conta → TABLE_CONFERENCE;
fechamento de Mesa → grid;
bloqueio de produtos após solicitar conta;
retry != reprint;
claim/lease;
idempotência;
impressão NETWORK local.
CHECKPOINT

Ao terminar informe:

qual era a causa de as rotas aparecerem desabilitadas;
se havia inconsistência entre filial selecionada e currentBranch;
como ficou effective_print_route();
como ficou a herança sem override;
como ficou inherit_branch=true;
como ficou override explícito inherit_branch=false;
se "Usar regra da filial" remove corretamente o override;
como a UI mostra a configuração efetiva herdada;
como ficou a mensagem quando a rota está realmente desabilitada;
arquivos backend alterados;
arquivos frontend alterados;
arquivos Flutter alterados;
migrations criadas — não deveria precisar;
o que depende de teste manual.

REGRA CRÍTICA:

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

Depois pare.