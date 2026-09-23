Pode mandar exatamente isso pro OpenCode:

> **MISSÃO — Correções finais do módulo de impressão após o commit `fix impressao`**
>
> Trabalhe em cima do **HEAD mais recente da branch principal**. No momento da revisão, o HEAD era `27cdda60856ae71f2581a0609795f81bbf63aee4`.
>
> **Não refaça a arquitetura de impressão.** A base atual com `PrintDocument -> PrintRoute -> PrinterDevice -> PrintJob -> PrintManager` deve ser preservada. O objetivo é corrigir inconsistências encontradas na revisão do código.
>
> **IMPORTANTE:** não executar testes, `flutter analyze`, builds, suites backend, `makemigrations --check`, linters ou verificações semelhantes. Não gastar tempo/créditos executando testes. Apenas implemente as correções. Eu farei os testes funcionais manualmente depois.
>
> 1. **Corrigir definitivamente a diferença entre “documento existe” e “documento foi impresso”.**
>
> Hoje várias telas consideram que, se existe `documentId`, então já houve impressão física. Isso está errado principalmente em rotas `MANUAL`.
>
> `PrintDocument` pode existir sem nenhum `PrintJob` inicial, ou com job ainda `PENDING/PROCESSING`.
>
> O POS deve usar os estados reais já existentes:
>
> * `initial_printed`
> * `reprint_eligible`
> * `queued`
> * status dos `print_jobs`
>
> Não usar apenas `documentId != null` para determinar `IMPRIMIR` ou `REIMPRIMIR`.
>
> Corrigir isso em:
>
> * Conta da Mesa;
> * Conferência;
> * Recibo final da Mesa;
> * Recibo/comprovante da Venda Rápida;
> * comprovantes individuais de pagamento;
> * tickets.
>
> Regra:
>
> * documento sem impressão inicial concluída → **IMPRIMIR**;
>
> * impressão inicial `PRINTED` ou `UNCERTAIN` → pode oferecer **REIMPRIMIR**;
>
> * `PENDING/PROCESSING` → não criar reimpressão; mostrar estado coerente como impressão pendente/em andamento;
>
> * `FAILED` antes do envio → permitir retry seguro, não chamar isso de reimpressão.
>
> 2. **Persistir estado dos documentos da Mesa no GET normal.**
>
> Hoje `POSTableAttendanceView.get()` retorna Mesa, summary e orders, mas não retorna os `PrintDocument`s relacionados.
>
> Ao sair da Mesa e entrar novamente, o Flutter perde o estado de Conta/Conferência/Recibo.
>
> O backend deve retornar na consulta normal da Mesa os documentos relevantes daquela Mesa, com os estados necessários para o POS decidir corretamente:
>
> * `TABLE_BILL`
> * `TABLE_CONFERENCE`
> * `TABLE_FINAL_RECEIPT`
>
> O Flutter já possui `printDocuments` / `printDocumentFor()`. Ajustar o contrato se necessário, mas manter uma fonte persistente no backend.
>
> Não depender da memória da tela.
>
> 3. **Resolver versionamento/snapshot de Conta e Conferência.**
>
> Exemplo:
>
> Mesa = R$100 → imprime Conferência v1.
>
> Depois adiciona/cancela item → Mesa = R$130.
>
> O botão não pode continuar fazendo `REIMPRIMIR` do snapshot antigo de R$100.
>
> Já existe `snapshot_hash` e `version` em `PrintDocument`.
>
> O estado retornado para o POS deve representar o **documento correspondente ao snapshot atual da origem**.
>
> Se o snapshot atual mudou:
>
> * o documento antigo continua histórico;
> * uma nova emissão deve criar nova versão;
> * a interface deve oferecer **IMPRIMIR** a versão atual;
> * `REIMPRIMIR` deve reimprimir somente a versão/snapshot correspondente.
>
> Não sobrescrever documento histórico.
>
> 4. **Implementar idempotência real para emissão manual e reimpressão de documentos.**
>
> O Flutter já envia `idempotency_key`, porém o backend atual não utiliza essa chave no contrato de impressão/reimpressão.
>
> Corrigir.
>
> Uma mesma intenção com o mesmo `idempotency_key` não pode gerar dois conjuntos de `PrintJob`.
>
> Cenário obrigatório:
>
> usuário toca REIMPRIMIR → backend cria reprint #1 → resposta HTTP se perde → cliente repete com mesma chave → backend deve devolver o mesmo resultado, sem criar reprint #2.
>
> O mesmo princípio vale para emissão manual inicial.
>
> A idempotência deve ser persistente no backend e auditável, não apenas proteção em memória.
>
> Não misturar isso com o `idempotency_key` físico do `PrintJob`; são responsabilidades diferentes.
>
> 5. **Padronizar `document_type` entre backend e frontend.**
>
> Existe incompatibilidade atual:
>
> backend serializa nomes como:
>
> `TABLE_BILL`
>
> enquanto o frontend de rotas trabalha com:
>
> `table_bill`
>
> Padronizar a API para usar os values persistidos em lowercase:
>
> `table_bill`
> `table_conference`
> `table_final_receipt`
> `quick_sale_receipt`
> `payment_receipt`
> `ticket`
>
> Ajustar serializer/types/frontend de forma consistente.
>
> Não permitir que a UI considere uma rota existente como inexistente por diferença de casing.
>
> 6. **Não permitir rota ativa sem impressora quando o modo exigir impressão.**
>
> Hoje é possível salvar uma rota `MANUAL` ou `AUTOMATIC` sem `PrinterDevice`, e `enqueue_print_document()` simplesmente gera zero jobs.
>
> Isso cria falso sucesso.
>
> Regra:
>
> * `DISABLED` pode não ter impressora;
> * `MANUAL` e `AUTOMATIC` devem possuir ao menos uma impressora válida/ativa configurada para aquela rota.
>
> Validar no backend e também melhorar UX no Backoffice.
>
> Não retornar sucesso de “enviado para impressão” se nenhum `PrintJob` puder ser criado.
>
> 7. **Restringir as rotas atuais aos tipos de impressora realmente executáveis neste bloco.**
>
> O executor atual do POS só executa `NETWORK`.
>
> Não permitir que a configuração das rotas atuais selecione silenciosamente USB/Bluetooth/Stone integrada se esses tipos ainda não possuem executor operacional neste bloco.
>
> Por enquanto:
>
> * rotas deste bloco devem trabalhar com `NETWORK`;
> * tipos futuros permanecem modelados no backend;
> * não criar job que ficará eternamente parado por falta de executor.
>
> Stone/USB/Bluetooth serão tratados nos blocos futuros.
>
> 8. **Corrigir teste de impressora para não exigir ProductionDestination.**
>
> Uma impressora pode existir exclusivamente para:
>
> * Conta;
> * Conferência;
> * Recibo;
> * Comprovante;
> * Ticket.
>
> Ela não precisa pertencer a Cozinha/Bar/Copa.
>
> `test_printer_device()` atualmente exige ao menos um `ProductionDestination`. Remover essa dependência.
>
> Um `PrintJob` de teste deve poder ser criado diretamente para qualquer `PrinterDevice NETWORK` ativo e válido.
>
> Não inventar ProductionDestination artificial só para teste.
>
> 9. **Corrigir margem física ESC/POS.**
>
> A alteração atual reduziu a largura imprimível:
>
> * 58mm: 28 colunas;
> * 80mm: 42 colunas.
>
> Porém o texto continua começando na coluna zero. Isso só cria sobra do lado direito e desloca a centralização.
>
> Implementar margem esquerda real e largura útil interna.
>
> Exemplo conceitual para 80mm:
>
> `|  conteúdo útil centralizado...  |`
>
> e não:
>
> `|conteúdo útil centralizado...      |`
>
> A margem deve valer para:
>
> * linhas normais;
> * centralização;
> * colunas;
> * separadores;
> * títulos;
> * itens;
> * documentos;
> * produção;
> * teste de impressora.
>
> Preservar wrapping, negrito, tamanho aumentado, feed antes do corte e suporte 58/80.
>
> 10. **Corrigir comprovante individual de pagamento da Venda Rápida.**
>
> O backend já aceita `PAYMENT_RECEIPT` com origem `quick_sale_payment`, mas a UI da Venda Rápida atualmente possui comentário dizendo que quick-sale payment não tem origem válida e deixa `onPrint: null`.
>
> Isso está incompatível com o backend novo.
>
> Implementar impressão/reimpressão individual do pagamento da Venda Rápida da mesma forma conceitual que a Mesa, respeitando:
>
> * rota configurada;
>
> * permissão;
>
> * idempotência;
>
> * estado persistente;
>
> * impressão inicial vs reimpressão.
>
> 11. **Restaurar corretamente estado dos tickets.**
>
> Na Venda Rápida os tickets já recebem `PrintDocument` automático no backend, mas a tela inicializa `_ticketDocumentIds` vazia.
>
> O response já contém `effects.tickets` com `print_document`.
>
> Popular o estado usando esses dados.
>
> Se ticket já teve impressão inicial `PRINTED/UNCERTAIN`, mostrar reimpressão.
>
> Se só existe documento e ainda não houve impressão, não chamar de reimpressão.
>
> 12. **Não deixar falha administrativa de impressão invalidar operação financeira já concluída.**
>
> Revisar principalmente:
>
> * `close_table_attendance()`;
> * finalização de Venda Rápida;
> * criação de tickets;
> * emissão automática de recibos/documentos.
>
> Venda/fechamento/pagamento válido deve ser a fonte principal.
>
> A criação/enfileiramento do documento não deve provocar rollback financeiro apenas porque houve uma falha secundária do subsistema de impressão.
>
> Usar separação pós-commit (`transaction.on_commit()` ou abordagem equivalente apropriada) onde necessário.
>
> Cuidado para preservar idempotência e não gerar emissão duplicada no pós-commit.
>
> 13. **Preservar rigorosamente o que já está correto.**
>
> Não quebrar:
>
> * `ProductionJob` para produção;
> * `PrintDocument` para documentos;
> * `PrintJob` como execução física;
> * impressão local NETWORK pelo CORE POS;
> * `claim / lease / physical_dispatch_started_at`;
> * `UNCERTAIN`;
> * local print ledger;
> * reconcile;
> * retry diferente de reprint;
> * cancelamento de produção via job `CANCEL`;
> * Mesa imprimindo produção ao confirmar/enviar pedido;
> * fechamento da Mesa não reimprimindo produção;
> * Product -> ProductionDestination -> PrinterDevice;
> * múltiplas impressoras por finalidade;
> * herança por filial;
> * override por POS;
> * número de cópias;
> * formato detalhado/simplificado;
> * auditoria.
>
> **Escopo:** Mesa + Venda Rápida + documentos/tickets/pagamentos já implementados no módulo de impressão atual.
>
> **Não iniciar Block 2/Block 3**, não implementar Stone integrada, Print Agent, USB ou Bluetooth agora.
>
> **Ao terminar, me entregue somente um resumo objetivo** contendo:
>
> * arquivos alterados;
> * causa de cada problema;
> * como foi corrigido;
> * mudanças de contrato/API;
> * migrations criadas, se houver;
> * qualquer ponto que ainda dependa de teste físico.
>
> **Não execute testes.**
