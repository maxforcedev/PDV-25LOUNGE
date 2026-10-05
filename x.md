Não execute novamente a suíte completa neste ambiente.

Nós JÁ temos a lista de erros do último GitHub Actions. Use essa lista como backlog e trabalhe em cima dela agora.

Para cada caso:

1. analise a causa;
2. classifique como:
   - REGRESSÃO REAL;
   - TESTE LEGADO/DESATUALIZADO;
   - FIXTURE/SETUP QUEBRADO;
   - CONTRATO ALTERADO;
   - REGRA DE NEGÓCIO ALTERADA;
3. só depois altere código ou teste;
4. não enfraqueça segurança, idempotência, RBAC, Cielo, caixa ou impressão apenas para deixar teste verde;
5. NÃO execute suíte completa;
6. no máximo rode o teste isolado relacionado à alteração;
7. me passe o comando exato para EU executar localmente.

Os dois casos que você já corrigiu podem ser considerados resolvidos:

- `apps.inventory.tests.test_block_3_cockpit.Block3InventoryTests.test_loss_observation_is_optional_except_other`
- fixture de `apps.payment_integrations.tests.test_cielo_adapter`

Agora continue pelos erros JÁ conhecidos do último Action.

## PRIORIDADE 1 — CIELO / PAGAMENTOS

Analise primeiro:

`test_cielo_reversal_applies_only_after_confirmed_provider_callback`

Erro:
`KeyError: 'capabilities'`

E:

`test_cielo_reversal_error_or_cancelled_keeps_original_payment`

O teste espera que após reversal ERROR/CANCELLED seja possível registrar pagamento novamente, mas atualmente `can_record_payment` continua `False`.

Aqui NÃO presuma que o teste está errado.

Confirme a máquina de estados real do reversal Cielo e se alguma intenção/sessão fica presa em estado intermediário.

Também revisar:

`test_provider_payment_flows_from_quick_checkout_to_sale_payment`

`test_partial_manual_and_provider_payment_finalize_with_two_sources`

Nesses dois há expectativa de HTTP 200 enquanto a API atual retorna 201 com venda corretamente finalizada.

Primeiro confirme qual é o contrato REST atual correto.

Se 201 estiver correto, atualize o teste.

NÃO altere endpoint funcional para 200 apenas para satisfazer teste antigo.

---

## PRIORIDADE 2 — CAIXA / PERMISSÕES

Analise:

`test_cancel_session_blocks_any_paid_open_checkout_and_allows_unpaid_checkout`

`test_close_and_cancel_block_processing_unknown_and_approved_provider_intents`

`test_unknown_intent_blocks_checkout_until_reconciled_and_applies_once`

Eles estão falhando em:

`PermissionDenied: Você não possui permissão nesta filial.`

dentro de `_validate_current_branch`.

NÃO remova essa validação.

Verifique se o teste está usando operador/filial/contexto antigo.

Se a segurança atual estiver correta, atualize fixture/setup do teste.

Também analisar:

`test_pos_cash_overview_allows_operational_permissions_but_redacts_opening_amount`

onde `overview.data['session']` está `None`.

`test_pos_cash_requires_operator_scope_and_uses_pos_only_operator_rbac`

onde o teste espera 401 e a API atual retorna 403 para sessão de operador ausente/inválida.

Antes de alterar, confirmar qual contrato atual de autenticação POS está correto.

---

## PRIORIDADE 3 — AUDITORIA / PIN / AUTORIZAÇÃO

Analisar:

`test_pos_authorization_rate_limit_and_audit_never_store_pin`

Erro:

`AuditLog.DoesNotExist`

Não remova expectativa de auditoria sem verificar.

Autorização por PIN é ação sensível e deve ser auditável.

Descubra se:

- o log realmente deixou de ser criado;
- mudou o action code;
- mudou metadata;
- o teste está procurando registro antigo.

Também:

`test_pos_cash_movement_replays_idempotently`

O teste encontrou 8 AuditLogs quando esperava 7.

IMPORTANTE:

idempotência financeira significa não duplicar efeito financeiro.

Ela NÃO necessariamente significa que uma nova tentativa/replay não possa gerar um novo evento de auditoria.

Confirme se houve duplicação da movimentação ou apenas um log legítimo do replay.

---

## PRIORIDADE 4 — TESTES CLARAMENTE LEGADOS

Corrigir os testes que ainda usam:

`reverse('pos:sale-finalize')`

nos casos:

`test_pos_finalize_sale_uses_active_cash_session_inside_service_transaction`

`test_pos_service_fee_finalization_requires_its_own_pin_authorization`

`test_pos_superuser_without_effective_sales_create_cannot_start_sale`

A rota `pos:sale-finalize` não existe mais.

NÃO reintroduza essa rota.

Descubra qual é o fluxo/end-point atual equivalente e migre os testes para o contrato atual.

Também corrigir:

`test_operator_session_fingerprint_authenticates_and_upgrades_legacy_session`

que possui:

`NameError: challenge_id is not defined`

Isso aparenta ser erro direto do próprio teste.

---

## PRIORIDADE 5 — DEVICE / OPERADOR

Analisar:

`test_backoffice_device_administration_keeps_credentials_private`

A API atualmente exige empresa explícita para consultar devices e retorna:

`Selecione uma empresa para consultar dispositivos POS.`

Confirme se isso corresponde ao isolamento multiempresa atual.

Se sim, atualize o teste/fixture em vez de remover a exigência.

Também:

`test_device_can_request_eligible_operator_pin_reset_without_leaking_delivery_data`

A falha atual é comparação:

string UUID vs objeto UUID.

Corrigir a expectativa/normalização do teste, se o contrato atual estiver correto.

---

## PRIORIDADE 6 — BENEFICIÁRIOS / SANGRIA / CAIXA

Analisar:

`test_pos_cash_beneficiaries_filter_category_and_device_company_scope`

A estrutura atual retornada mudou.

Não force a API para o formato antigo sem verificar o contrato atual.

E:

`test_pos_withdrawal_accepts_company_beneficiary`

A API responde:

`Use beneficiary_type e beneficiary_id no POS.`

Se esse for o contrato atual correto, atualizar teste e payload.

---

## PRIORIDADE 7 — IMPRESSÃO

Analisar:

`test_failed_is_retryable_but_uncertain_requires_explicit_reprint`

O serviço está bloqueando retry com:

`Somente falha comprovadamente anterior ao envio físico pode receber retry.`

Essa proteção existe para evitar impressão física duplicada.

NÃO remova essa regra só para deixar o teste verde.

Verifique se o teste está montando um job FAILED que deveria realmente ser retryable ou se o contrato mudou.

Também:

`test_product_selects_printers_without_exposing_destination_management`

está retornando 404 para o produto.

Investigue:

- tenant;
- filial;
- soft delete;
- queryset;
- fixture;
- escopo do usuário;
- product id usado.

Não altere isolamento de empresa/filial para satisfazer o teste.

---

## PRIORIDADE 8 — SUPPORT SESSION

Analisar:

`test_non_impersonated_support_me_synthesizes_active_branch_context`

Está falhando porque:

`create_support_session`

agora exige senha atual e retorna:

`Senha atual invalida.`

Isso provavelmente decorre das regras de segurança atuais para Support Session.

Não retire reautenticação.

Atualize o setup/teste caso a política atual realmente exija senha/2FA.

---

## PRIORIDADE 9 — FORNECEDORES

Analisar:

`test_suppliers_are_branch_owned_and_soft_deleted_tax_id_can_be_reused`

O teste espera recriar um fornecedor arquivado com o mesmo CPF/CNPJ.

Mas a API atual retorna:

`archived_supplier_exists`

Não altere automaticamente.

Descubra a regra de negócio vigente:

- devemos restaurar o fornecedor arquivado?
- ou criar um novo registro?
- ou impedir duplicação histórica?

Preserve integridade e histórico.

Explique qual regra o código atualmente implementa antes de alterar qualquer coisa.

---

## TESTES LOCAIS

Após cada grupo corrigido, NÃO execute toda a suíte.

Me passe o comando específico.

Exemplo:

`docker compose exec -T backend python manage.py test --keepdb apps.pos.tests.test_foundation.POSFoundationIntegrationTests.test_cielo_reversal_error_or_cancelled_keeps_original_payment`

Eu executo aqui e retorno o resultado.

Somente depois de resolvermos os erros conhecidos EU executarei:

`docker compose exec -T backend python manage.py test --keepdb --failfast`

E, quando estiver tudo verde:

`docker compose exec -T backend python manage.py test --keepdb`

Não gaste mais créditos executando 400+ testes neste ambiente.