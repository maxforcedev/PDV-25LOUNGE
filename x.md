TRABALHE NO HEAD ATUAL DA MAIN.

FAÇA SOMENTE ESTAS CORREÇÕES FINAIS DO BLOCO 1 DE IMPRESSÃO.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.
NÃO EXECUTE SUÍTES BACKEND.
NÃO INICIE BLOCO 2.

==================================================

1. RECONCILIAÇÃO PRECISA SER IDEMPOTENTE
   ==================================================

Hoje pode ocorrer:

POS envia impressão fisicamente
→ reportPrintResult("printed")
→ backend salva PRINTED
→ resposta HTTP se perde
→ LocalPrintLedger continua com state=sent
→ próxima reconcile chama complete_print_job()
→ backend rejeita porque job já está PRINTED
→ reconcile retorna nenhum job_id
→ ledger local nunca é removido.

Corrigir.

reconcile_print_jobs() deve reconhecer estados terminais já compatíveis.

Exemplos:

local state = sent

backend = PRINTED
→ considerar reconciliado
→ retornar job_id.

backend = UNCERTAIN
→ considerar reconciliado
→ retornar job_id.

local state = failed_before_send

backend = FAILED
→ considerar reconciliado
→ retornar job_id.

Não alterar novamente um estado terminal correto apenas para reconciliar.

Objetivo:

reconcile deve ser idempotente.

O Flutter continua removendo SOMENTE os job_ids devolvidos pelo backend.

==================================================
2. REPRINT SOMENTE QUANDO SEMANTICAMENTE VÁLIDO
===============================================

Hoje o Backoffice mostra "Reimprimir" para qualquer PrintJob não-test.

Isso está errado.

Reprint significa:

"uma execução física anterior já ocorreu ou pode ter ocorrido e o operador explicitamente quer uma nova via."

Permitir reprint somente para:

PRINTED
UNCERTAIN

Regras:

PRINTED
→ Reimprimir permitido.

UNCERTAIN
→ Reimprimir permitido como decisão humana explícita.

FAILED
→ NÃO mostrar Reimprimir.
→ usar Retry.

PENDING
→ NÃO mostrar Reimprimir.

PROCESSING
→ NÃO mostrar Reimprimir.

CANCELLED
→ NÃO mostrar Reimprimir, salvo se existir alguma regra já explícita no domínio que justifique.

Aplicar a validação em DOIS lugares:

Backoffice/UI
e
backend reprint_print_job().

Não confiar somente na UI.

Para batch:

todos os sources do batch precisam estar em estado compatível com reprint.

Preservar a reimpressão do batch inteiro já implementada.

==================================================
3. DISPATCH FÍSICO ABANDONADO NÃO PODE FICAR PROCESSING PARA SEMPRE
===================================================================

Agora existe corretamente:

physical_dispatch_started_at.

Depois desse ponto o job NÃO pode voltar automaticamente para outro POS.

Preservar isso.

Porém existe o cenário:

POS faz claim
→ start_print_dispatch()
→ backend grava physical_dispatch_started_at
→ POS cai / app fecha / comunicação morre
→ nunca chega printed/failed/uncertain.

Hoje esse job pode ficar:

PROCESSING
+
physical_dispatch_started_at != null

indefinidamente.

Criar uma transição segura para:

UNCERTAIN

quando um dispatch físico iniciado permanecer sem resultado por tempo suficiente.

NÃO voltar para PENDING.

NÃO entregar para outro POS.

NÃO imprimir automaticamente.

Pode usar um prazo configurável/constante razoável.

Exemplo conceitual:

physical_dispatch_started_at + timeout de segurança
→ sem resultado final
→ UNCERTAIN.

Essa transição pode ocorrer de forma oportunística ao consultar fila/histórico/reconciliação, sem necessidade de criar worker complexo nesta fase.

Auditar:

print_job.uncertain_timeout

ou nome equivalente.

==================================================
4. BATCH
========

Se um ticket físico possui vários PrintJobs com o mesmo batch_key:

a transição para UNCERTAIN precisa atingir o batch inteiro.

Nunca deixar:

job A = UNCERTAIN
job B = PROCESSING
job C = PROCESSING

se foram parte da mesma execução física.

==================================================
5. LEDGER LOCAL ATTEMPTED
=========================

Revisar também registros locais:

state = attempted.

Eles podem permanecer caso algo morra na fronteira entre:

claim
start_print_dispatch
socket.

Não reenviar fisicamente automaticamente.

Garantir que esses registros não cresçam indefinidamente.

A reconciliação deve conseguir descobrir o estado no backend e:

* remover o ledger se não houver mais responsabilidade local;
* ou manter/transformar para estado seguro quando necessário.

Prioridade absoluta:

NÃO DUPLICAR IMPRESSÃO.

==================================================
6. PRESERVAR
============

NÃO alterar o que já ficou correto:

physical_dispatch_started_at;

claim/lease;

POS só abre socket depois de start_print_dispatch;

job com dispatch iniciado não volta para fila;

batch;

TCP LAN;

ESC/POS;

LocalPrintLedger;

network_printing;

PrintManager funcionando sem operador logado;

Mesa;

Venda Rápida;

CANCEL;

teste de impressora;

last_seen_at baseado em observação real;

reprint do batch inteiro.

==================================================
7. NÃO EXECUTAR TESTES
======================

NÃO RODAR:

flutter test
flutter analyze
flutter build
python manage.py test
python manage.py check
makemigrations --check
git diff --check

Eu vou conferir o resultado diretamente pelo GitHub.

==================================================
CHECKPOINT FINAL
================

Ao terminar informe somente:

1. como reconcile passou a tratar jobs já PRINTED/UNCERTAIN/FAILED;
2. quando o ledger local é removido;
3. quais estados permitem reprint;
4. como backend impede reprint inválido;
5. após quanto tempo dispatch abandonado vira UNCERTAIN;
6. como isso funciona para batch;
7. como registros attempted são resolvidos;
8. arquivos alterados;
9. migrations, caso existam.

DEPOIS PARE.

NÃO EXECUTE TESTES.
NÃO INICIE BLOCO 2.
