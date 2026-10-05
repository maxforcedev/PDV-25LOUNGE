Use o ESTADO ATUAL DO GITHUB como fonte da verdade.

Não execute novamente a suíte completa.

Também não precisamos “descobrir a próxima falha residual” rodando 437 testes, porque já temos a lista do último GitHub Actions e os testes completos serão executados localmente por mim.

IMPORTANTE:

Você desviou para a correção dos testes antes de terminar a missão anterior.

No GitHub atual, desde `f1efc6cf693ab880ca1fb6353e0594a3f966f03e`, os commits novos alteraram apenas testes e `x.md`.

Portanto, a missão:

“Finalizar a separação entre MESAS e COMANDAS, remover referências operacionais restantes do modelo antigo e deixar Backend, Backoffice, POS, RBAC e testes coerentes com a arquitetura atual.”

AINDA NÃO ESTÁ CONCLUÍDA no código publicado.

Retome essa missão primeiro.

Não precisa recomeçar do zero: analise o GitHub atual e implemente apenas o que ainda está pendente.

Principalmente confira e corrija, caso ainda existam:

- Backoffice de Comandas enviando `table` na abertura;
- operação “Transferir mesa” em Comandas;
- `commands/<id>/transfer/` sendo chamado pelo frontend;
- split de Comanda enviando Mesa;
- Comanda exibindo `table_name` operacionalmente;
- POS exibindo “Sem mesa” em Comandas;
- `tableId`, `tableName` e `isPrimary` usados operacionalmente em AttendanceCommand;
- serializer operacional de Comanda expondo campos de Mesa sem necessidade;
- permissão órfã `commands.transfer`;
- reports tratando Comanda atual como vinculada à Mesa;
- métricas atuais de Mesa usando Command/AttendanceCommand em vez de TableAttendance;
- qualquer caminho operacional atual Comanda → Mesa;
- qualquer caminho operacional atual Mesa → Command.

Preserve:

- `commands.Table` como entidade física da Mesa;
- `TableAttendance` como entidade operacional da Mesa;
- `commands.transfer_items`;
- campos/migrations históricos quando necessários para leitura de registros antigos;
- segurança, RBAC, idempotência e auditoria.

NÃO:

- reintroduza `open_table`;
- recrie transferência Comanda → Mesa;
- redesenhe Comandas;
- apague migrations históricas;
- execute a suíte completa;
- gaste tempo tentando descobrir erros já conhecidos do CI.

Quando terminar essa limpeza arquitetural, faça commit/push.

Depois me entregue:

1. arquivos alterados;
2. referências operacionais Mesa ↔ Comanda removidas;
3. referências históricas que permaneceram e por quê;
4. confirmação de que `TableAttendance` é a única entidade operacional da Mesa;
5. confirmação de que uma Comanda nova NÃO pertence a uma Mesa;
6. testes específicos que EU devo executar localmente.

Somente depois disso voltaremos ao backlog dos erros do GitHub Actions.