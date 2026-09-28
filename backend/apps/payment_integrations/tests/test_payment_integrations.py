from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.companies.models import Status
from apps.companies.services import create_company_with_matrix
from apps.pos.models import POSDevice
from apps.payment_integrations.models import (
    PaymentAttempt, PaymentAttemptStatus, PaymentIntentOriginType, PaymentIntentStatus, PaymentProvider,
    PaymentProviderConnection, PaymentProviderConnectionEnvironment, PaymentTerminal,
)
from apps.payment_integrations.services import (
    PaymentIntegrationConflict, create_payment_attempt, create_payment_intent,
    resolve_payment_attempt, transition_payment_attempt, transition_payment_intent,
)
from apps.sales.models import PaymentMethod


class PaymentIntegrationsTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            email='pay0@example.com', password='Strong-password-123!',
        )
        self.company = create_company_with_matrix(
            creator=self.operator, trade_name='Pay 0', legal_name='Pay 0 Ltda',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.method = PaymentMethod.objects.create(
            company=self.company, code='credit_card', name='Crédito', status=Status.ACTIVE,
        )
        self.device = POSDevice.objects.create(
            branch=self.branch, name='Caixa 1', status=POSDevice.Status.ACTIVE,
        )
        self.provider = PaymentProvider.objects.create(
            code='generic', name='Genérico', status=Status.ACTIVE,
            integration_type='server_api',
        )
        self.connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=self.provider, name='Contrato principal',
            environment=PaymentProviderConnectionEnvironment.SANDBOX, status=Status.ACTIVE,
        )
        self.terminal = PaymentTerminal.objects.create(
            connection=self.connection, branch=self.branch, pos_device=self.device,
            name='Terminal Caixa 1', status=Status.ACTIVE,
        )

    def create_intent(self, *, amount=Decimal('100.00'), key=None):
        return create_payment_intent(
            company=self.company, branch=self.branch, pos_device=self.device,
            operator=self.operator, origin_type=PaymentIntentOriginType.QUICK_SALE,
            origin_id=uuid4(), payment_method=self.method, amount=amount,
            provider_connection=self.connection, terminal=self.terminal,
            idempotency_key=key or uuid4(),
        )

    def start_attempt(self, intent):
        attempt = create_payment_attempt(intent=intent)
        return transition_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.PROCESSING,
        )

    def test_creates_valid_intent_and_keeps_financial_ledgers_untouched(self):
        intent, replayed = self.create_intent()

        self.assertFalse(replayed)
        self.assertEqual(intent.status, PaymentIntentStatus.CREATED)
        self.assertEqual(intent.amount, Decimal('100.00'))
        self.assertEqual(intent.attempts.count(), 0)

    def test_rejects_non_positive_amount(self):
        with self.assertRaises(ValidationError):
            self.create_intent(amount=Decimal('0.00'))

    def test_inactive_payment_method_blocks_intent_creation(self):
        self.method.status = Status.INACTIVE
        self.method.save()

        with self.assertRaises(ValidationError):
            self.create_intent()

    def test_idempotency_replays_only_matching_request(self):
        key = uuid4()
        first, replayed = self.create_intent(key=key)
        second, replayed_again = self.create_intent(key=key)

        self.assertFalse(replayed)
        self.assertTrue(replayed_again)
        self.assertEqual(first.pk, second.pk)
        with self.assertRaises(PaymentIntegrationConflict) as context:
            self.create_intent(key=key, amount=Decimal('101.00'))
        self.assertEqual(context.exception.code, 'idempotency_key_conflict')

    def test_attempt_numbers_are_sequential(self):
        intent, _ = self.create_intent()
        intent = transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        first = self.start_attempt(intent)
        _first, declined_intent = resolve_payment_attempt(
            attempt=first, status=PaymentAttemptStatus.DECLINED,
        )
        second = self.start_attempt(declined_intent)

        self.assertEqual((first.attempt_number, second.attempt_number), (1, 2))
        self.assertEqual(declined_intent.status, PaymentIntentStatus.DECLINED)

    def test_declined_attempt_can_be_retried_and_approved_without_applying(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        first = self.start_attempt(intent)
        _first, declined_intent = resolve_payment_attempt(
            attempt=first, status=PaymentAttemptStatus.DECLINED,
        )
        second = self.start_attempt(declined_intent)
        approved_attempt, approved_intent = resolve_payment_attempt(
            attempt=second, status=PaymentAttemptStatus.APPROVED,
        )

        self.assertEqual(first.status, PaymentAttemptStatus.DECLINED)
        self.assertEqual(approved_attempt.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(approved_intent.status, PaymentIntentStatus.APPROVED)
        self.assertIsNone(approved_intent.applied_at)

    def test_unknown_is_preserved_until_authoritative_transition(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        unknown_attempt, unknown = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.UNKNOWN,
        )

        self.assertEqual(unknown.status, PaymentIntentStatus.UNKNOWN)
        with self.assertRaises(PaymentIntegrationConflict) as context:
            create_payment_attempt(intent=unknown)
        self.assertEqual(context.exception.code, 'intent_unknown')
        with self.assertRaises(PaymentIntegrationConflict):
            transition_payment_intent(intent=unknown, status=PaymentIntentStatus.APPROVED)
        reconciled_attempt, reconciled_intent = resolve_payment_attempt(
            attempt=unknown_attempt, status=PaymentAttemptStatus.APPROVED,
        )
        self.assertEqual(reconciled_attempt.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(reconciled_intent.status, PaymentIntentStatus.APPROVED)

    def test_unknown_attempt_can_be_reconciled_to_declined_only_by_resolution(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        unknown_attempt, unknown_intent = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.UNKNOWN,
        )

        with self.assertRaises(PaymentIntegrationConflict):
            transition_payment_intent(intent=unknown_intent, status=PaymentIntentStatus.DECLINED)
        reconciled_attempt, reconciled_intent = resolve_payment_attempt(
            attempt=unknown_attempt, status=PaymentAttemptStatus.DECLINED,
        )

        self.assertEqual(reconciled_attempt.status, PaymentAttemptStatus.DECLINED)
        self.assertEqual(reconciled_intent.status, PaymentIntentStatus.DECLINED)

    def test_approved_does_not_apply_automatically_and_invalid_transition_is_rejected(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        _approved_attempt, approved = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.APPROVED,
        )

        self.assertEqual(approved.status, PaymentIntentStatus.APPROVED)
        self.assertIsNone(approved.applied_at)
        with self.assertRaises(PaymentIntegrationConflict):
            transition_payment_intent(intent=approved, status=PaymentIntentStatus.DECLINED)

    def test_provider_result_cannot_be_applied_directly_to_intent(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        self.start_attempt(intent)

        with self.assertRaises(PaymentIntegrationConflict):
            transition_payment_intent(intent=intent, status=PaymentIntentStatus.APPROVED)

    def test_attempt_amount_must_match_the_intent(self):
        intent, _ = self.create_intent()

        with self.assertRaises(ValidationError):
            PaymentAttempt.objects.create(
                intent=intent, provider_connection=self.connection, terminal=self.terminal,
                attempt_number=1, amount=Decimal('101.00'),
            )

    def test_intent_structural_fields_are_immutable_after_creation(self):
        intent, _ = self.create_intent()
        other_method = PaymentMethod.objects.create(
            company=self.company, code='debit_card', name='Débito', status=Status.ACTIVE,
        )
        other_connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=self.provider, name='Contrato alternativo',
            environment=PaymentProviderConnectionEnvironment.SANDBOX, status=Status.ACTIVE,
        )
        changes = {
            'amount': Decimal('101.00'),
            'origin_id': str(uuid4()),
            'payment_method': other_method,
            'provider_connection': other_connection,
            'terminal': None,
            'idempotency_key': uuid4(),
            'request_fingerprint': 'a' * 64,
        }

        for field, value in changes.items():
            intent.refresh_from_db()
            setattr(intent, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                intent.save()

        intent.refresh_from_db()
        intent.amount = Decimal('101.00')
        intent.origin_id = str(uuid4())
        with self.assertRaises(ValidationError):
            intent.save()

    def test_connection_identity_is_immutable_but_administration_is_allowed(self):
        other_operator = User.objects.create_user(
            email='pay0-connection@example.com', password='Strong-password-123!',
        )
        other_company = create_company_with_matrix(
            creator=other_operator, trade_name='Outra conexão', legal_name='Outra conexão Ltda',
        )
        other_provider = PaymentProvider.objects.create(
            code='other-connection', name='Outro provedor', status=Status.ACTIVE,
            integration_type='server_api',
        )
        changes = {
            'company': other_company,
            'branch': other_company.branches.get(is_matrix=True),
            'provider': other_provider,
            'environment': PaymentProviderConnectionEnvironment.PRODUCTION,
        }

        for field, value in changes.items():
            self.connection.refresh_from_db()
            setattr(self.connection, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.connection.save()

        self.connection.refresh_from_db()
        self.connection.name = 'Contrato renomeado'
        self.connection.status = Status.INACTIVE
        self.connection.configuration = {'merchant_reference': 'updated'}
        self.connection.capabilities_override = {'capture_mode': 'manual'}
        self.connection.save()
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.name, 'Contrato renomeado')
        self.assertEqual(self.connection.status, Status.INACTIVE)
        self.assertEqual(self.connection.configuration, {'merchant_reference': 'updated'})

    def test_terminal_identity_and_external_id_history_protection(self):
        other_connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=self.provider, name='Outro contrato terminal',
            environment=PaymentProviderConnectionEnvironment.SANDBOX, status=Status.ACTIVE,
        )
        other_operator = User.objects.create_user(
            email='pay0-terminal@example.com', password='Strong-password-123!',
        )
        other_company = create_company_with_matrix(
            creator=other_operator, trade_name='Outro terminal', legal_name='Outro terminal Ltda',
        )
        changes = {
            'connection': other_connection,
            'branch': other_company.branches.get(is_matrix=True),
        }

        for field, value in changes.items():
            self.terminal.refresh_from_db()
            setattr(self.terminal, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.terminal.save()

        other_device = POSDevice.objects.create(
            branch=self.branch, name='Caixa 2', status=POSDevice.Status.ACTIVE,
        )
        self.terminal.refresh_from_db()
        self.terminal.name = 'Terminal renomeado'
        self.terminal.status = Status.INACTIVE
        self.terminal.pos_device = other_device
        self.terminal.external_id = 'terminal-before-history'
        self.terminal.save()
        self.terminal.refresh_from_db()
        self.assertEqual(self.terminal.name, 'Terminal renomeado')
        self.assertEqual(self.terminal.status, Status.INACTIVE)
        self.assertEqual(self.terminal.pos_device_id, other_device.pk)

        self.terminal.status = Status.ACTIVE
        self.terminal.save()
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        create_payment_attempt(intent=intent)
        self.terminal.external_id = 'terminal-after-history'
        with self.assertRaises(ValidationError):
            self.terminal.save()

    def test_configuration_querysets_block_updates_and_instance_saves_remain_allowed(self):
        other_provider = PaymentProvider.objects.create(
            code='queryset-other', name='Outro provedor queryset', status=Status.ACTIVE,
            integration_type='server_api',
        )
        other_connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=self.provider, name='Outra conexão queryset',
            environment=PaymentProviderConnectionEnvironment.SANDBOX, status=Status.ACTIVE,
        )
        other_operator = User.objects.create_user(
            email='pay0-queryset@example.com', password='Strong-password-123!',
        )
        other_company = create_company_with_matrix(
            creator=other_operator, trade_name='Outra queryset', legal_name='Outra queryset Ltda',
        )
        other_branch = other_company.branches.get(is_matrix=True)

        self.provider.code = 'provider-save-bypass'
        with self.assertRaises(ValidationError):
            self.provider.save()
        self.provider.refresh_from_db()

        updates = (
            ('provider_code', PaymentProvider.objects.filter(pk=self.provider.pk), {'code': 'provider-update-bypass'}),
            ('connection_provider', PaymentProviderConnection.objects.filter(pk=self.connection.pk), {'provider': other_provider}),
            ('connection_company', PaymentProviderConnection.objects.filter(pk=self.connection.pk), {'company': other_company}),
            ('connection_sensitive_configuration', PaymentProviderConnection.objects.filter(pk=self.connection.pk), {
                'configuration': {'access_token': 'secret'},
            }),
            ('terminal_connection', PaymentTerminal.objects.filter(pk=self.terminal.pk), {'connection': other_connection}),
            ('terminal_branch', PaymentTerminal.objects.filter(pk=self.terminal.pk), {'branch': other_branch}),
            ('terminal_external_id', PaymentTerminal.objects.filter(pk=self.terminal.pk), {'external_id': 'queryset-bypass'}),
            ('terminal_sensitive_metadata', PaymentTerminal.objects.filter(pk=self.terminal.pk), {
                'metadata': {'authorization': 'secret'},
            }),
        )
        for name, queryset, values in updates:
            with self.subTest(update=name), self.assertRaises(ValidationError):
                queryset.update(**values)

        self.provider.name = 'Provedor administrado'
        self.provider.status = Status.INACTIVE
        self.provider.capabilities = {'supports_refunds': False}
        self.provider.save()
        self.connection.name = 'Conexão administrada'
        self.connection.status = Status.INACTIVE
        self.connection.configuration = {'merchant_reference': 'updated'}
        self.connection.capabilities_override = {'capture_mode': 'manual'}
        self.connection.save()
        self.terminal.name = 'Terminal administrado'
        self.terminal.status = Status.INACTIVE
        self.terminal.capabilities = {'accepts_nfc': True}
        self.terminal.metadata = {'location': 'counter'}
        self.terminal.save()

        self.provider.refresh_from_db()
        self.connection.refresh_from_db()
        self.terminal.refresh_from_db()
        self.assertEqual(self.provider.name, 'Provedor administrado')
        self.assertEqual(self.connection.name, 'Conexão administrada')
        self.assertEqual(self.terminal.name, 'Terminal administrado')

    def test_direct_attempt_creation_requires_processing_intent(self):
        intent, _ = self.create_intent()

        with self.assertRaises(ValidationError):
            PaymentAttempt.objects.create(
                intent=intent, provider_connection=self.connection, terminal=self.terminal,
                attempt_number=1, amount=intent.amount,
            )

        intent = transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        with self.assertRaises(ValidationError):
            PaymentAttempt.objects.create(
                intent=intent, provider_connection=self.connection, terminal=self.terminal,
                attempt_number=1, amount=intent.amount,
            )

        attempt = create_payment_attempt(intent=intent)
        self.assertEqual(attempt.status, PaymentAttemptStatus.CREATED)
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntentStatus.PROCESSING)

    def test_attempt_structural_fields_are_immutable_and_service_updates_result_data(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = create_payment_attempt(intent=intent)
        other_intent, _ = self.create_intent()
        other_connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=self.provider, name='Contrato do attempt alternativo',
            environment=PaymentProviderConnectionEnvironment.SANDBOX, status=Status.ACTIVE,
        )
        changes = {
            'intent': other_intent,
            'provider_connection': other_connection,
            'terminal': None,
            'attempt_number': 2,
            'amount': Decimal('101.00'),
        }

        for field, value in changes.items():
            attempt.refresh_from_db()
            setattr(attempt, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                attempt.save()

        attempt.refresh_from_db()
        attempt.provider_transaction_id = 'direct-orm-change'
        with self.assertRaises(ValidationError):
            attempt.save()
        processing = transition_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.PROCESSING,
            result_data={'provider_transaction_id': 'provider-transaction'},
        )
        resolved_attempt, _intent = resolve_payment_attempt(
            attempt=processing, status=PaymentAttemptStatus.APPROVED,
            result_data={'authorization_code': '123456', 'nsu': '789'},
        )

        self.assertEqual(processing.provider_transaction_id, 'provider-transaction')
        self.assertEqual(resolved_attempt.authorization_code, '123456')
        self.assertEqual(resolved_attempt.nsu, '789')

    def test_inactive_terminal_blocks_new_attempt(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        self.terminal.status = Status.INACTIVE
        self.terminal.save()

        with self.assertRaises(ValidationError):
            create_payment_attempt(intent=intent)

    def test_inactive_connection_blocks_new_attempt(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        self.connection.status = Status.INACTIVE
        self.connection.save()

        with self.assertRaises(ValidationError):
            create_payment_attempt(intent=intent)

    def test_inactive_provider_blocks_new_attempt(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        self.provider.status = Status.INACTIVE
        self.provider.save()

        with self.assertRaises(ValidationError):
            create_payment_attempt(intent=intent)

    def test_inactive_payment_method_blocks_new_attempt(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        self.method.status = Status.INACTIVE
        self.method.save()

        with self.assertRaises(ValidationError):
            create_payment_attempt(intent=intent)

    def test_inactive_resources_block_created_to_processing(self):
        for resource in (self.provider, self.connection, self.terminal, self.method):
            with self.subTest(resource=resource.__class__.__name__):
                intent, _ = self.create_intent()
                transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
                attempt = create_payment_attempt(intent=intent)
                resource.status = Status.INACTIVE
                resource.save()

                with self.assertRaises(ValidationError):
                    transition_payment_attempt(
                        attempt=attempt, status=PaymentAttemptStatus.PROCESSING,
                    )

                resource.status = Status.ACTIVE
                resource.save()

    def test_terminal_deactivated_after_processing_does_not_block_approved_result(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        self.terminal.status = Status.INACTIVE
        self.terminal.save()

        resolved_attempt, resolved_intent = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.APPROVED,
        )

        self.assertEqual(resolved_attempt.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(resolved_intent.status, PaymentIntentStatus.APPROVED)

    def test_connection_deactivated_after_processing_does_not_block_result(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        self.connection.status = Status.INACTIVE
        self.connection.save()

        resolved_attempt, resolved_intent = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.DECLINED,
        )

        self.assertEqual(resolved_attempt.status, PaymentAttemptStatus.DECLINED)
        self.assertEqual(resolved_intent.status, PaymentIntentStatus.DECLINED)

    def test_provider_deactivated_after_processing_does_not_block_result(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        self.provider.status = Status.INACTIVE
        self.provider.save()

        resolved_attempt, resolved_intent = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.ERROR,
        )

        self.assertEqual(resolved_attempt.status, PaymentAttemptStatus.ERROR)
        self.assertEqual(resolved_intent.status, PaymentIntentStatus.ERROR)

    def test_payment_method_deactivated_after_processing_does_not_block_approved_result(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        self.method.status = Status.INACTIVE
        self.method.save()

        resolved_attempt, resolved_intent = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.APPROVED,
        )

        self.assertEqual(resolved_attempt.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(resolved_intent.status, PaymentIntentStatus.APPROVED)

    def test_payment_method_deactivated_after_processing_does_not_block_declined_result(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        self.method.status = Status.INACTIVE
        self.method.save()

        resolved_attempt, resolved_intent = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.DECLINED,
        )

        self.assertEqual(resolved_attempt.status, PaymentAttemptStatus.DECLINED)
        self.assertEqual(resolved_intent.status, PaymentIntentStatus.DECLINED)

    def test_payment_method_deactivated_after_processing_allows_unknown_reconciliation(self):
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        attempt = self.start_attempt(intent)
        self.method.status = Status.INACTIVE
        self.method.save()

        unknown_attempt, unknown_intent = resolve_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.UNKNOWN,
        )
        reconciled_attempt, reconciled_intent = resolve_payment_attempt(
            attempt=unknown_attempt, status=PaymentAttemptStatus.APPROVED,
        )

        self.assertEqual(unknown_intent.status, PaymentIntentStatus.UNKNOWN)
        self.assertEqual(reconciled_attempt.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(reconciled_intent.status, PaymentIntentStatus.APPROVED)

    def test_deactivated_resources_do_not_block_unknown_reconciliation(self):
        for resource in (self.terminal, self.connection, self.provider):
            with self.subTest(resource=resource.__class__.__name__):
                intent, _ = self.create_intent()
                transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
                attempt = self.start_attempt(intent)
                resource.status = Status.INACTIVE
                resource.save()

                unknown_attempt, unknown_intent = resolve_payment_attempt(
                    attempt=attempt, status=PaymentAttemptStatus.UNKNOWN,
                )
                reconciled_attempt, reconciled_intent = resolve_payment_attempt(
                    attempt=unknown_attempt, status=PaymentAttemptStatus.APPROVED,
                )

                self.assertEqual(unknown_intent.status, PaymentIntentStatus.UNKNOWN)
                self.assertEqual(reconciled_attempt.status, PaymentAttemptStatus.APPROVED)
                self.assertEqual(reconciled_intent.status, PaymentIntentStatus.APPROVED)
                resource.status = Status.ACTIVE
                resource.save()

    def test_provider_swap_requires_explicit_terminal_none_when_no_terminal_is_used(self):
        other_provider = PaymentProvider.objects.create(
            code='other', name='Outro', status=Status.ACTIVE, integration_type='server_api',
        )
        other_connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=other_provider, name='Outro contrato',
            environment=PaymentProviderConnectionEnvironment.SANDBOX, status=Status.ACTIVE,
        )
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)

        with self.assertRaises(ValidationError):
            create_payment_attempt(intent=intent, provider_connection=other_connection)
        attempt = create_payment_attempt(
            intent=intent, provider_connection=other_connection, terminal=None,
        )

        self.assertEqual(attempt.provider_connection_id, other_connection.pk)
        self.assertIsNone(attempt.terminal_id)

    def test_direct_orm_cannot_create_inconsistent_terminal_or_intent_status(self):
        other_operator = User.objects.create_user(
            email='pay0-other@example.com', password='Strong-password-123!',
        )
        other_company = create_company_with_matrix(
            creator=other_operator, trade_name='Outra', legal_name='Outra Ltda',
        )
        other_branch = other_company.branches.get(is_matrix=True)

        with self.assertRaises(ValidationError):
            PaymentTerminal.objects.create(
                connection=self.connection, branch=other_branch, name='Incompatível', status=Status.ACTIVE,
            )
        with self.assertRaises(ValidationError):
            PaymentAttempt.objects.create(
                intent=self.create_intent()[0], provider_connection=self.connection,
                terminal=self.terminal, attempt_number=1, amount=Decimal('100.00'),
                status=PaymentAttemptStatus.APPROVED,
            )

    def test_sensitive_metadata_is_rejected_at_every_persistence_boundary(self):
        with self.assertRaises(ValidationError):
            PaymentProvider.objects.create(
                code='unsafe', name='Inseguro', status=Status.ACTIVE,
                integration_type='server_api', capabilities={'access_token': 'secret'},
            )
        with self.assertRaises(ValidationError):
            PaymentProviderConnection.objects.create(
                company=self.company, provider=self.provider, name='Insegura',
                environment=PaymentProviderConnectionEnvironment.SANDBOX,
                configuration={'client_secret': 'secret'},
            )
        with self.assertRaises(ValidationError):
            PaymentTerminal.objects.create(
                connection=self.connection, branch=self.branch, name='Inseguro',
                metadata={'authorization_header': 'secret'},
            )
        intent, _ = self.create_intent()
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        with self.assertRaises(ValidationError):
            create_payment_attempt(
                intent=intent, request_metadata={'token': 'secret'},
            )
        attempt = create_payment_attempt(intent=intent)
        attempt.response_metadata = {'authorization': 'secret'}
        with self.assertRaises(ValidationError):
            attempt.save()
