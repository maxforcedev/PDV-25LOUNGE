# ADENDO À MISSÃO — Build Flutter continua quebrando + avisos Gradle/AGP/Kotlin

Adicionar esta correção à missão anterior do erro 500 ao remover `PrintRouteOverride`.

Trabalhe no HEAD mais recente da main.

Na revisão atual, o HEAD é:

`13c58c1ae86acdfe4fdec6d181fdccb5e21d3b94`

---

# 1. ERRO FATAL REAL DO BUILD AINDA NÃO FOI CORRIGIDO

Build real executado manualmente:

```text
lib/payments/shared_payment_page.dart:691:55:
Error: The argument type 'void Function()?' can't be assigned
to the parameter type 'void Function()'.

onReverse: _checkout.status == 'open'
    ? () => _reverse(payment)
    : null,

Depois:

Target kernel_snapshot_program failed

Execution failed for task ':app:compileFlutterBuildDebug'

BUILD FAILED

Confirmação no HEAD atual:

pos/lib/payments/shared_payment_widgets.dart

ainda possui:

final VoidCallback onReverse;

Portanto a correção solicitada anteriormente AINDA NÃO ENTROU.

2. CORRIGIR PaymentHistoryItem.onReverse

Em:

pos/lib/payments/shared_payment_widgets.dart

alterar:

final VoidCallback onReverse;

para:

final VoidCallback? onReverse;

O construtor pode continuar:

required this.onReverse,

desde que o tipo seja nullable.

Isso permite que o chamador declare explicitamente:

onReverse: null

quando a operação não estiver disponível.

3. NÃO MOSTRAR BOTÃO DE ESTORNO QUANDO CALLBACK FOR NULL

Hoje existe lógica equivalente a:

if (!reversed)
  IconButton(
    onPressed: working ? null : onReverse,
    tooltip: 'Estornar',
    ...
  )

Corrigir para renderizar o botão somente quando:

!reversed
AND
onReverse != null

Conceitualmente:

if (!reversed && onReverse != null)
  IconButton(
    onPressed: working ? null : onReverse,
    tooltip: 'Estornar',
    ...
  )

Não usar:

() {}

Não criar callback fake.

Se não pode estornar, o botão não deve existir.

4. PRESERVAR A PROTEÇÃO DA VENDA FINALIZADA

NÃO alterar isto em:

shared_payment_page.dart

onReverse: _checkout.status == 'open'
    ? () => _reverse(payment)
    : null,

Isso está correto.

A finalidade é:

checkout OPEN
→ botão ESTORNAR disponível

checkout FINALIZED/CANCELLED
→ botão ESTORNAR indisponível
5. REVISAR TODOS OS USOS DE PaymentHistoryItem

Verificar chamadas em:

Venda Rápida;
Mesa;
outros fluxos compartilhados de pagamento.

A mudança para VoidCallback? não pode quebrar os lugares que continuam passando callback normal.

Não mudar regra de negócio dos estornos.

6. AVISOS DE GRADLE / AGP / KOTLIN NÃO SÃO O ERRO FATAL

O build também exibiu:

Warning: Flutter support for your project's Gradle version (8.14.0)
will soon be dropped.

Upgrade para pelo menos Gradle 9.1.0.

Também:

Android Gradle Plugin 8.11.1
→ futuro mínimo informado pelo Flutter: 9.0.1

E:

Kotlin 2.2.20
→ futuro mínimo informado pelo Flutter: 2.3.20

Esses são AVISOS DE COMPATIBILIDADE FUTURA.

Eles NÃO causaram o build atual falhar.

A falha fatal atual é exclusivamente:

void Function()? can't be assigned to void Function()
7. NÃO ATUALIZAR GRADLE / AGP / KOTLIN NESTA MISSÃO

NÃO alterar agora:

gradle-wrapper.properties;
Gradle 8.14.0;
Android Gradle Plugin 8.11.1;
Kotlin 2.2.20;
settings.gradle;
build.gradle;

somente por causa desses warnings.

Essa atualização será tratada em missão separada porque envolve compatibilidade Android/Flutter e não deve ser misturada com um bug funcional simples.

Não usar também:

--android-skip-build-dependency-validation

como "correção".

O projeto ainda aceita essas versões atualmente; Flutter apenas informa que o suporte será removido futuramente.

8. PRESERVAR TAMBÉM A CORREÇÃO DO DELETE DE OVERRIDE

Continuar a missão anterior para:

DELETE /api/v1/print-route-overrides/<id>/

que atualmente gera 500.

Preservar a correção correta:

PrintRouteOverride
→ pos_device
→ branch

e ajustar resolução de object permission para usar:

obj.pos_device.branch_id

quando aplicável.

Também deixar _company_ids_from_object() entender objetos vinculados via pos_device.

Não adicionar branch_id fake ao PrintRouteOverride.

RESULTADO ESPERADO
Flutter

Este código:

onReverse: _checkout.status == 'open'
    ? () => _reverse(payment)
    : null,

deve ser válido.

Checkout aberto:

ESTORNAR aparece

Checkout finalizado:

ESTORNAR não aparece

Sem erro:

void Function()? can't be assigned to void Function()
Backoffice

Criar override:

POST /print-route-overrides/
→ 201

Voltar para regra da filial:

DELETE /print-route-overrides/<id>/
→ 204

Sem 500.

REGRA CRÍTICA

NÃO EXECUTE TESTES.

NÃO EXECUTE:

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

Eu farei o build e os testes manualmente.

CHECKPOINT

Ao terminar informe:

se PaymentHistoryItem.onReverse passou para VoidCallback?;
como ficou a condição para renderizar o botão ESTORNAR;
quais usos de PaymentHistoryItem foram revisados;
se Gradle/AGP/Kotlin permaneceram intocados;
como corrigiu o DELETE de PrintRouteOverride;
arquivos Flutter alterados;
arquivos backend alterados;
migrations criadas — não deveria precisar;
pontos que ainda dependem de teste manual.

NÃO EXECUTE TESTES.
NÃO EXECUTE ANALYZE.
NÃO EXECUTE BUILD.

Depois pare.