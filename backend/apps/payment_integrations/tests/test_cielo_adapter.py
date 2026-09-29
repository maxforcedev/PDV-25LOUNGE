import base64
import hashlib
import json
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from django.test import SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User
from apps.companies.models import Status
from apps.companies.services import create_company_with_matrix
from apps.payment_integrations.models import (
    PaymentAttemptStatus,
    PaymentIntentOriginType,
    PaymentIntentStatus,
    PaymentProvider,
    PaymentProviderConnection,
    PaymentProviderConnectionEnvironment,
    PaymentTerminal,
)
from apps.payment_integrations.providers.base import ProviderLaunchCommand, ProviderPaymentResult
from apps.payment_integrations.providers.cielo import (
    CieloSmartAdapter,
    amount_to_cents,
    get_cielo_credentials,
)
from apps.payment_integrations.providers.registry import get_adapter
from apps.payment_integrations.services import (
    PaymentIntegrationConflict,
    create_payment_attempt,
    create_payment_intent,
    resolve_payment_attempt,
    transition_payment_attempt,
    transition_payment_intent,
)
from apps.pos.models import POSDevice, QuickSalePayment
from apps.sales.models import PaymentMethod, PaymentMethodCode


class CieloSmartAdapterTests(SimpleTestCase):
    secret_client_id = 'cielo-client-id-for-test'
    secret_access_token = 'cielo-access-token-for-test'

    def setUp(self):
        self.adapter = CieloSmartAdapter()

    def attempt(self, *, amount=Decimal('10.50'), method=PaymentMethodCode.CREDIT_CARD,
                installment_mode='store'):
        return SimpleNamespace(
            id=uuid4(),
            amount=amount,
            intent=SimpleNamespace(payment_method=SimpleNamespace(code=method)),
            provider_connection=SimpleNamespace(
                configuration={'credit_installment_mode': installment_mode},
                provider=SimpleNamespace(code='cielo', integration_type='local_deep_link'),
            ),
        )

    @staticmethod
    def items():
        return [{
            'name': 'Coffee', 'quantity': 2, 'sku': 'COFFEE-001',
            'unitOfMeasure': 'UN', 'unitPrice': 525,
        }]

    def command_payload(self, attempt, *, installments=1, merchant_code=None):
        configuration = attempt.provider_connection.configuration
        if merchant_code is not None:
            configuration['merchant_code'] = merchant_code
        command = self.adapter.build_payment_command(
            attempt=attempt,
            callback_url='core://payment/callback?source=cielo',
            items=self.items(),
            installments=installments,
        )
        self.assertIsInstance(command, ProviderLaunchCommand)
        self.assertEqual(command.operation, 'payment')
        parsed = urlsplit(command.uri)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ('lio', 'payment', ''))
        query = parse_qs(parsed.query, strict_parsing=True)
        self.assertEqual(query['urlCallback'], ['core://payment/callback?source=cielo'])
        payload = json.loads(base64.b64decode(query['request'][0], validate=True).decode('utf-8'))
        return command, payload

    def approved_callback(self, attempt, *, status_code=1, amount=1050, reference=None,
                          transaction_id='transaction-123'):
        return base64.b64encode(json.dumps({
            'id': 'order-123',
            'reference': reference or f'CORE-{attempt.id}',
            'payments': [{
                'amount': amount,
                'authCode': 'auth-123',
                'brand': 'Visa',
                'cieloCode': 'nsu-123',
                'installments': 0,
                'mask': '411111******1111',
                'terminal': 'terminal-123',
                'paymentFields': {
                    'paymentTransactionId': transaction_id,
                    'statusCode': status_code,
                    'productName': 'CREDITO_AVISTA',
                    'numberOfQuotas': 0,
                },
            }],
        }).encode('utf-8')).decode('ascii')

    def assert_secret_absent(self, value):
        rendered = json.dumps(value, default=str, sort_keys=True)
        if self.secret_client_id in rendered or self.secret_access_token in rendered:
            self.fail('Secret material leaked into a safe representation.')

    @override_settings(CIELO_SMART_CLIENT_ID=None, CIELO_SMART_ACCESS_TOKEN=None)
    def test_missing_client_id_is_a_controlled_conflict(self):
        with self.assertRaises(PaymentIntegrationConflict) as context:
            get_cielo_credentials()

        self.assertEqual(context.exception.code, 'cielo_credentials_missing')

    @override_settings(CIELO_SMART_CLIENT_ID='cielo-client-id-for-test', CIELO_SMART_ACCESS_TOKEN=None)
    def test_missing_access_token_is_a_controlled_conflict(self):
        with self.assertRaises(PaymentIntegrationConflict) as context:
            get_cielo_credentials()

        self.assertEqual(context.exception.code, 'cielo_credentials_missing')

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_settings_credentials_build_a_command_without_leaking_to_safe_surfaces(self):
        credentials = get_cielo_credentials()
        self.assertEqual(
            hashlib.sha256(credentials.client_id.encode()).hexdigest(),
            '90105bcb0d7a444dd138fd2a2274e38072b95a21ec1665c9aff0c4a5ff806980',
        )
        self.assertEqual(
            hashlib.sha256(credentials.access_token.encode()).hexdigest(),
            'f01582dc26b5e30808818d25fdf6e36744333f429b808dc17d1d6290c30eb1b5',
        )

        command, payload = self.command_payload(self.attempt())

        self.assertTrue(payload['clientID'])
        self.assertTrue(payload['accessToken'])
        self.assert_secret_absent(command.safe_metadata)
        self.assert_secret_absent(repr(command))

    def test_amount_to_cents_is_exact_and_rejects_invalid_amounts(self):
        self.assertEqual(amount_to_cents(Decimal('1.00')), 100)
        self.assertEqual(amount_to_cents(Decimal('10.50')), 1050)
        self.assertEqual(amount_to_cents(Decimal('100.00')), 10000)

        for invalid in (Decimal('0.00'), Decimal('-0.01'), Decimal('1.001')):
            with self.subTest(amount=invalid), self.assertRaises(PaymentIntegrationConflict):
                amount_to_cents(invalid)

    def test_registry_resolves_the_cielo_adapter(self):
        self.assertIsInstance(get_adapter('cielo'), CieloSmartAdapter)

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_build_command_maps_payment_codes_and_cielo_installments(self):
        cases = (
            (PaymentMethodCode.DEBIT_CARD, 1, 'store', 'DEBITO_AVISTA', 0),
            (PaymentMethodCode.CREDIT_CARD, 1, 'store', 'CREDITO_AVISTA', 0),
            (PaymentMethodCode.CREDIT_CARD, 2, 'store', 'CREDITO_PARCELADO_LOJA', 2),
            (PaymentMethodCode.CREDIT_CARD, 2, 'administrator', 'CREDITO_PARCELADO_ADM', 2),
            (PaymentMethodCode.CREDIT_CARD, 2, 'bank', 'CREDITO_PARCELADO_BNCO', 2),
            (PaymentMethodCode.PIX, 1, 'store', 'PIX', 0),
            (PaymentMethodCode.FOOD_VOUCHER, 1, 'store', 'VOUCHER_ALIMENTACAO', 0),
            (PaymentMethodCode.MEAL_VOUCHER, 1, 'store', 'VOUCHER_REFEICAO', 0),
        )
        for method, installments, mode, payment_code, cielo_installments in cases:
            with self.subTest(method=method, installments=installments, mode=mode):
                attempt = self.attempt(method=method, installment_mode=mode)
                _command, payload = self.command_payload(attempt, installments=installments)
                self.assertEqual(payload['paymentCode'], payment_code)
                self.assertEqual(payload['installments'], cielo_installments)

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_build_command_is_deterministic_safe_and_contains_only_configured_merchant_code(self):
        attempt = self.attempt()
        command, payload = self.command_payload(attempt)

        self.assertEqual(payload['reference'], f'CORE-{attempt.id}')
        self.assertEqual(payload['value'], '1050')
        self.assertIsInstance(payload['value'], str)
        self.assertEqual(payload['items'], self.items())
        self.assertNotIn('merchantCode', payload)
        self.assertEqual(command.safe_metadata, {
            'provider': 'cielo',
            'payment_code': 'CREDITO_AVISTA',
            'installments': 0,
            'reference': f'CORE-{attempt.id}',
            'amount_cents': 1050,
            'merchant_code_present': False,
        })

        _command, configured_payload = self.command_payload(attempt, merchant_code='1234567890123456')
        self.assertEqual(configured_payload['merchantCode'], '1234567890123456')

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_cash_and_invalid_cielo_connection_configuration_are_rejected(self):
        with self.assertRaises(PaymentIntegrationConflict) as cash_error:
            self.command_payload(self.attempt(method=PaymentMethodCode.CASH))
        self.assertEqual(cash_error.exception.code, 'cielo_payment_method_unsupported')

        with self.assertRaises(PaymentIntegrationConflict) as mode_error:
            self.command_payload(self.attempt(installment_mode='unsupported'), installments=2)
        self.assertEqual(mode_error.exception.code, 'cielo_configuration_invalid')

        attempt = self.attempt()
        attempt.provider_connection.provider.code = 'generic'
        with self.assertRaises(PaymentIntegrationConflict) as connection_error:
            self.command_payload(attempt)
        self.assertEqual(connection_error.exception.code, 'cielo_connection_invalid')

    def test_success_callbacks_map_card_and_pix_results_without_raw_response_metadata(self):
        attempt = self.attempt()
        card = self.adapter.parse_payment_callback(
            attempt=attempt, response=self.approved_callback(attempt), responsecode=None,
        )
        pix = self.adapter.parse_payment_callback(
            attempt=attempt, response=self.approved_callback(
                attempt, status_code=0, transaction_id='pix-transaction-123',
            ), responsecode=None,
        )

        self.assertIsInstance(card, ProviderPaymentResult)
        self.assertEqual(card.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(card.result_data, {
            'provider_transaction_id': 'transaction-123',
            'provider_order_id': 'order-123',
            'provider_reference': f'CORE-{attempt.id}',
            'terminal_external_id': 'terminal-123',
            'authorization_code': 'auth-123',
            'nsu': 'nsu-123',
            'card_brand': 'Visa',
            'card_mask': '411111******1111',
            'installments': 1,
            'payment_product': 'CREDITO_AVISTA',
            'provider_status': 'approved',
            'provider_status_code': '1',
            'provider_message': '',
        })
        self.assertEqual(pix.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(pix.result_data['provider_transaction_id'], 'pix-transaction-123')
        self.assertEqual(pix.result_data['provider_status_code'], '0')
        self.assert_secret_absent(card.safe_metadata)
        self.assertNotIn('payments', card.safe_metadata)

        cancelled = self.adapter.parse_payment_callback(
            attempt=attempt,
            response=self.approved_callback(attempt, status_code=2),
            responsecode=None,
        )
        self.assertEqual(cancelled.status, PaymentAttemptStatus.CANCELLED)
        self.assertEqual(cancelled.result_data['provider_status_code'], '2')

    def test_callback_error_codes_are_final_non_approval_results_with_sanitized_reason(self):
        expected = {
            '1': PaymentAttemptStatus.CANCELLED,
            '2': PaymentAttemptStatus.ERROR,
            '3': PaymentAttemptStatus.ERROR,
            '4': PaymentAttemptStatus.ERROR,
        }
        for responsecode, status in expected.items():
            with self.subTest(responsecode=responsecode):
                result = self.adapter.parse_payment_callback(
                    attempt=self.attempt(), response='', responsecode=responsecode,
                )
                self.assertEqual(result.status, status)
                self.assertEqual(result.result_data['provider_status_code'], responsecode)
                self.assertTrue(result.result_data['provider_message'])
                self.assert_secret_absent(result.safe_metadata)

    def test_json_error_payload_has_precedence_over_neutral_responsecode(self):
        expected = {
            '1': PaymentAttemptStatus.CANCELLED,
            '2': PaymentAttemptStatus.ERROR,
            '3': PaymentAttemptStatus.ERROR,
            '4': PaymentAttemptStatus.ERROR,
        }
        for code, status in expected.items():
            with self.subTest(code=code):
                response = base64.b64encode(json.dumps({
                    'code': int(code),
                    'reason': 'CANCELADO accessToken=provider-secret',
                }).encode('utf-8')).decode('ascii')
                result = self.adapter.parse_payment_callback(
                    attempt=self.attempt(), response=response, responsecode='0',
                )
                self.assertEqual(result.status, status)
                self.assertEqual(result.result_data['provider_status_code'], code)
                self.assertNotIn('provider-secret', result.result_data['provider_message'])

    def test_parser_rejects_non_cielo_attempt_and_invalid_merchant_code(self):
        attempt = self.attempt()
        attempt.provider_connection.provider.code = 'stone'
        with self.assertRaises(PaymentIntegrationConflict) as provider_error:
            self.adapter.parse_payment_callback(
                attempt=attempt, response='', responsecode=None,
            )
        self.assertEqual(provider_error.exception.code, 'cielo_connection_invalid')

        for merchant_code in ('abc', '123', '123456789012345', '12345678901234567', '1234-5678-9012-3456'):
            with self.subTest(merchant_code=merchant_code), self.assertRaises(PaymentIntegrationConflict) as config_error:
                self.command_payload(self.attempt(), merchant_code=merchant_code)
            self.assertEqual(config_error.exception.code, 'cielo_configuration_invalid')

    def test_callback_ignores_current_connection_configuration(self):
        attempt = self.attempt()
        attempt.provider_connection.configuration = {'credit_installment_mode': 'invalid'}

        result = self.adapter.parse_payment_callback(
            attempt=attempt, response=self.approved_callback(attempt), responsecode=None,
        )

        self.assertEqual(result.status, PaymentAttemptStatus.APPROVED)

    def test_unprovable_callbacks_are_unknown_never_approved(self):
        attempt = self.attempt()
        malformed = (
            ('invalid base64', 'not-base64'),
            ('invalid json', base64.b64encode(b'{not-json').decode('ascii')),
            ('missing payments', base64.b64encode(json.dumps({
                'id': 'order-123', 'reference': f'CORE-{attempt.id}', 'payments': [],
            }).encode('utf-8')).decode('ascii')),
            ('missing transaction id', self.approved_callback(attempt, transaction_id='')),
            ('amount mismatch', self.approved_callback(attempt, amount=999)),
            ('reference mismatch', self.approved_callback(attempt, reference='CORE-other-attempt')),
        )
        for name, response in malformed:
            with self.subTest(case=name):
                result = self.adapter.parse_payment_callback(
                    attempt=attempt, response=response, responsecode=None,
                )
                self.assertEqual(result.status, PaymentAttemptStatus.UNKNOWN)
                self.assertNotEqual(result.status, PaymentAttemptStatus.APPROVED)

        ambiguous = json.loads(base64.b64decode(self.approved_callback(attempt)).decode('utf-8'))
        second = dict(ambiguous['payments'][0])
        second['paymentFields'] = dict(second['paymentFields'], paymentTransactionId='transaction-456')
        ambiguous['payments'].append(second)
        result = self.adapter.parse_payment_callback(
            attempt=attempt,
            response=base64.b64encode(json.dumps(ambiguous).encode('utf-8')).decode('ascii'),
            responsecode=None,
        )
        self.assertEqual(result.status, PaymentAttemptStatus.UNKNOWN)


class CieloAdapterBridgeTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            email='cielo-adapter@example.com', password='Strong-password-123!',
        )
        self.company = create_company_with_matrix(
            creator=self.operator, trade_name='Cielo Adapter', legal_name='Cielo Adapter Ltda',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.device = POSDevice.objects.create(
            branch=self.branch, name='Cielo Caixa', status=POSDevice.Status.ACTIVE,
        )
        self.method = PaymentMethod.objects.create(
            company=self.company, code=PaymentMethodCode.CREDIT_CARD,
            name='Crédito Cielo', status=Status.ACTIVE,
        )
        self.provider = PaymentProvider.objects.get(code='cielo')
        self.assertEqual(self.provider.name, 'Cielo Smart')
        self.assertEqual(self.provider.integration_type, 'local_deep_link')
        self.assertTrue(self.provider.capabilities['payment'])
        self.assertTrue(self.provider.capabilities['reversal'])
        self.assertTrue(self.provider.capabilities['recovery'])
        self.connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=self.provider, name='Cielo Sandbox',
            environment=PaymentProviderConnectionEnvironment.SANDBOX, status=Status.ACTIVE,
        )
        self.terminal = PaymentTerminal.objects.create(
            connection=self.connection, branch=self.branch, pos_device=self.device,
            name='Cielo Terminal', status=Status.ACTIVE,
        )

    def test_processing_attempt_resolves_after_connection_configuration_change(self):
        intent, _ = create_payment_intent(
            company=self.company, branch=self.branch, pos_device=self.device, operator=self.operator,
            origin_type=PaymentIntentOriginType.QUICK_SALE, origin_id=uuid4(),
            payment_method=self.method, amount=Decimal('10.50'),
            provider_connection=self.connection, terminal=self.terminal, idempotency_key=uuid4(),
            _quick_sale_bridge=True,
        )
        intent = transition_payment_intent(intent=intent, status=PaymentIntentStatus.READY)
        self.assertEqual(intent.status, PaymentIntentStatus.READY)
        attempt = create_payment_attempt(intent=intent)
        self.assertEqual(attempt.status, PaymentAttemptStatus.CREATED)
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntentStatus.PROCESSING)
        attempt = transition_payment_attempt(
            attempt=attempt, status=PaymentAttemptStatus.PROCESSING,
        )
        self.assertEqual(attempt.status, PaymentAttemptStatus.PROCESSING)
        adapter = CieloSmartAdapter()
        self.connection.configuration = {'credit_installment_mode': 'invalid'}
        self.connection.save()
        with self.assertRaises(PaymentIntegrationConflict) as build_error:
            adapter.build_payment_command(
                attempt=attempt,
                callback_url='core://payment/callback?source=cielo',
                items=[{
                    'name': 'Coffee', 'quantity': 2, 'sku': 'COFFEE-001',
                    'unitOfMeasure': 'UN', 'unitPrice': 525,
                }],
            )
        self.assertEqual(build_error.exception.code, 'cielo_configuration_invalid')
        response = base64.b64encode(json.dumps({
            'id': 'order-bridge-123',
            'reference': f'CORE-{attempt.id}',
            'payments': [{
                'amount': 1050,
                'authCode': 'auth-bridge-123',
                'brand': 'Visa',
                'cieloCode': 'nsu-bridge-123',
                'installments': 0,
                'mask': '411111******1111',
                'terminal': 'terminal-bridge-123',
                'paymentFields': {
                    'paymentTransactionId': 'transaction-bridge-123',
                    'statusCode': 1,
                    'productName': 'CREDITO_AVISTA',
                    'numberOfQuotas': 0,
                },
            }],
        }).encode('utf-8')).decode('ascii')

        result = adapter.parse_payment_callback(
            attempt=attempt, response=response, responsecode=None,
        )
        resolved_attempt, resolved_intent = resolve_payment_attempt(
            attempt=attempt, status=result.status, result_data=result.result_data,
            response_metadata=result.safe_metadata,
        )

        self.assertEqual(resolved_attempt.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(resolved_intent.status, PaymentIntentStatus.APPROVED)
        self.assertFalse(QuickSalePayment.objects.filter(source_payment_attempt=resolved_attempt).exists())
