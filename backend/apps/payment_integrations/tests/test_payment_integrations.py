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
        transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        first = self.start_attempt(intent)
        _first, declined_intent = resolve_payment_attempt(
            attempt=first, status=PaymentAttemptStatus.DECLINED,
        )
        second = self.start_attempt(declined_intent)

        self.assertEqual((first.attempt_number, second.attempt_number), (1, 2))
        self.assertEqual(declined_intent.status, PaymentIntentStatus.DECLINED)

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
        reconciled_attempt, reconciled_intent = resolve_payment_attempt(
            attempt=unknown_attempt, status=PaymentAttemptStatus.APPROVED,
        )
        self.assertEqual(reconciled_attempt.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(reconciled_intent.status, PaymentIntentStatus.APPROVED)

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
        with self.assertRaises(ValidationError):
            PaymentAttempt.objects.create(
                intent=intent, provider_connection=self.connection, terminal=self.terminal,
                attempt_number=1, amount=intent.amount, request_metadata={'token': 'secret'},
            )
        attempt = PaymentAttempt.objects.create(
            intent=intent, provider_connection=self.connection, terminal=self.terminal,
            attempt_number=1, amount=intent.amount,
        )
        attempt.response_metadata = {'authorization': 'secret'}
        with self.assertRaises(ValidationError):
            attempt.save()
