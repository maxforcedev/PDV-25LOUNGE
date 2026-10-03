import base64
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core import mail
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from django.test import TestCase

from apps.accounts.models import User
from apps.base.exceptions import DomainValidationError
from apps.base.models import AuditLog
from apps.cash.models import CashMovement, CashRegister, CashSessionStatus
from apps.cash.services import cancel_session, close_session, open_session
from apps.companies.models import (
    AccessProfile, Branch, Customer, FunctionalPermission, Status, UserBranchAccess, UserCompanyAccess,
    UserPermissionBlock,
)
from apps.companies.services import (
    create_branch_with_access, create_company_with_matrix, create_customer, set_customer_status,
)
from apps.pos.models import (
    AuthenticationChallenge, BranchPOSSettings, POSDevice, POSDeviceSettings,
    POSOperatorPinAttempt, POSOperatorSession, POSRequestRateLimit, QuickSaleCheckout, QuickSalePayment,
)
from apps.payment_integrations.models import (
    PaymentAttempt, PaymentAttemptStatus, PaymentIntent, PaymentProvider, PaymentProviderConnection,
    PaymentProviderConnectionEnvironment, PaymentTerminal, ProviderReversalOperation,
)
from apps.payment_integrations.providers.cielo import CieloSmartAdapter
from apps.payment_integrations.providers.base import ProviderPaymentResult
from apps.payment_integrations.services import PaymentIntegrationConflict
from apps.pos.provider_payments import resolve_provider_resources
from apps.pos.services import (
    _mask_email, authenticate_device, authenticate_operator_session,
    create_pin_reset_token, effective_settings, pairing_channels, set_pos_pin,
    version_gate,
)
from apps.pos.serializers import POSCustomerSerializer
from apps.inventory.models import Stock
from apps.products.models import Category, InventoryBehavior, Product, ProductBranchConfig, Unit
from apps.sales.models import Payment
from apps.sales.services import ensure_default_payment_methods
from apps.sales.quick_checkout import (
    QuickCheckoutConflict, apply_approved_quick_sale_payment_intent,
    cancel_quick_checkout, create_quick_sale_payment_intent, checkout_balance,
    finalize_quick_checkout, record_quick_checkout_payment,
    resolve_quick_sale_payment_attempt, reverse_quick_checkout_payment,
    start_quick_sale_payment_attempt,
)


class POSFoundationContractTests(SimpleTestCase):
    def test_licensing_code_normalizes_short_or_case_insensitive_input(self):
        code = 'CORE-7K9P2M'

        self.assertEqual(Branch.normalize_licensing_code(code.lower()), code)
        self.assertEqual(Branch.normalize_licensing_code(code.removeprefix('CORE-')), code)
        self.assertIsNone(Branch.normalize_licensing_code('CORE-O0IL1X'))

    def test_pairing_contacts_are_masked_and_do_not_expose_phone(self):
        branch = SimpleNamespace(
            email='loja@example.com',
            company=SimpleNamespace(email='financeiro@example.com'),
        )

        channels = pairing_channels(branch)

        self.assertEqual([item['masked'] for item in channels], ['l***@example.com', 'f***@example.com'])
        self.assertNotIn('loja@example.com', str([{key: value for key, value in item.items() if key != '_destination'} for item in channels]))

    def test_email_masking_does_not_leak_the_local_part(self):
        self.assertEqual(_mask_email('a@empresa.com'), 'a***@empresa.com')

    @override_settings(POS_MINIMUM_SUPPORTED_VERSION='1.2.0', POS_LATEST_VERSION='1.3.0')
    def test_version_gate_blocks_unsupported_release(self):
        with self.assertRaises(DomainValidationError) as context:
            version_gate('1.1.9')
        self.assertEqual(context.exception.status_code, 426)
        self.assertEqual(context.exception.payload['code'], 'pos_update_required')

    @override_settings(POS_MINIMUM_SUPPORTED_VERSION='1.2.0', POS_LATEST_VERSION='1.3.0')
    def test_version_gate_reports_optional_update(self):
        self.assertEqual(version_gate('1.2.0'), {
            'current_version': '1.2.0',
            'latest_version': '1.3.0',
            'minimum_supported_version': '1.2.0',
            'update_available': True,
            'update_required': False,
        })


class CieloAdapterContractTests(SimpleTestCase):
    def setUp(self):
        self.adapter = CieloSmartAdapter()
        self.attempt = SimpleNamespace(
            pk=uuid4(),
            provider_connection=SimpleNamespace(
                provider=SimpleNamespace(code='cielo'), configuration={},
            ),
            provider_connection_id=None,
            provider_order_id='cielo-order-1',
            provider_transaction_id='transaction-1',
            nsu='nsu-1',
            authorization_code='auth-1',
        )
        self.reversal = SimpleNamespace(
            pk=uuid4(), source_attempt=self.attempt, amount=Decimal('20.00'),
        )

    @staticmethod
    def _encoded(payload):
        return base64.b64encode(json.dumps(payload).encode()).decode()

    def _payment(self, *, amount=2000, status='2', transaction='transaction-1'):
        return {
            'amount': amount,
            'originalTransactionId': transaction,
            'originalCieloCode': 'nsu-1',
            'originalAuthCode': 'auth-1',
            'paymentFields': {'statusCode': status},
        }

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_reversal_command_uses_the_cielo_contract(self):
        command = self.adapter.build_reversal_command(
            reversal=self.reversal,
            callback_url='corepdv://cielo-payment-reversal-response',
        )
        request = json.loads(base64.b64decode(parse_qs(urlparse(command.uri).query)['request'][0]))

        self.assertEqual(command.operation, 'reversal')
        self.assertEqual(request['id'], 'cielo-order-1')
        self.assertEqual(request['value'], 2000)
        self.assertNotIn('orderId', request)

    def test_reversal_callback_requires_a_single_real_cancellation_transaction(self):
        result = self.adapter.parse_reversal_callback(
            reversal=self.reversal,
            response=self._encoded({
                'id': 'cielo-order-1',
                'payments': [self._payment(status='1'), self._payment(status='2')],
            }),
        )

        self.assertEqual(result.status, PaymentAttemptStatus.APPROVED)

    def test_reversal_callback_rejects_unproven_cancellation(self):
        cases = {
            'payment_transaction': {
                'id': 'cielo-order-1', 'payments': [self._payment(status='1')],
            },
            'different_order': {
                'id': 'other-order', 'payments': [self._payment()],
            },
            'different_amount': {
                'id': 'cielo-order-1', 'payments': [self._payment(amount=1000)],
            },
            'ambiguous': {
                'id': 'cielo-order-1', 'payments': [self._payment(), self._payment()],
            },
            'different_original_transaction': {
                'id': 'cielo-order-1', 'payments': [self._payment(transaction='other-transaction')],
            },
        }

        for name, payload in cases.items():
            with self.subTest(name=name):
                result = self.adapter.parse_reversal_callback(
                    reversal=self.reversal, response=self._encoded(payload),
                )
                self.assertEqual(result.status, PaymentAttemptStatus.UNKNOWN)

    def test_reversal_payload_error_overrides_responsecode_zero(self):
        for code, expected in (('1', PaymentAttemptStatus.CANCELLED), ('3', PaymentAttemptStatus.ERROR)):
            with self.subTest(code=code):
                result = self.adapter.parse_reversal_callback(
                    reversal=self.reversal,
                    response=self._encoded({'code': code, 'reason': 'Resposta Cielo'}),
                    responsecode='0',
                )
                self.assertEqual(result.status, expected)

    def test_payment_payload_error_overrides_responsecode_zero(self):
        result = self.adapter.parse_payment_callback(
            attempt=self.attempt,
            response=self._encoded({'code': '3', 'reason': 'Resposta Cielo'}),
            responsecode='0',
        )

        self.assertEqual(result.status, PaymentAttemptStatus.ERROR)


class POSQuickCustomerContractTests(SimpleTestCase):
    def test_name_and_phone_are_required_but_cpf_is_optional(self):
        serializer = POSCustomerSerializer(data={'name': 'Ana'})

        self.assertFalse(serializer.is_valid())
        self.assertIn('phone', serializer.errors)
        self.assertNotIn('document', serializer.errors)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    POS_MINIMUM_SUPPORTED_VERSION='1.0.0',
    POS_LATEST_VERSION='1.0.0',
)
class POSFoundationIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner-pos@example.com', password='Strong-owner-password-123!'
        )
        self.company = create_company_with_matrix(
            creator=self.owner,
            trade_name='POS Test',
            legal_name='POS Test Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.branch.cnpj = '04252011000110'
        self.branch.email = 'pareamento@example.com'
        self.branch.save()
        self.client = APIClient()

    def pair_device(self, *, name='Stone Bar 01'):
        identify = self.client.post(
            reverse('pos:pairing-identify'),
            {'identifier': self.branch.licensing_code},
            format='json',
        )
        self.assertEqual(identify.status_code, 200, identify.data)
        channel = identify.data['channels'][0]
        with patch('apps.pos.services.secrets.randbelow', return_value=123456):
            otp = self.client.post(
                reverse('pos:pairing-request-otp'),
                {'pairing_flow_id': identify.data['pairing_flow_id'], 'channel_id': channel['id']},
                format='json',
            )
        self.assertEqual(otp.status_code, 200, otp.data)
        confirmation = self.client.post(
            reverse('pos:pairing-confirm'),
            {
                'challenge_id': otp.data['challenge_id'],
                'code': '123456',
                'device': {
                    'name': name,
                    'device_type': 'STONE_POS',
                    'app_version': '1.0.0',
                    'os_version': 'Android 14',
                    'device_model': 'Stone P2',
                },
            },
            format='json',
        )
        self.assertEqual(confirmation.status_code, 201, confirmation.data)
        return confirmation, otp.data['challenge_id']

    def create_pos_operator(self):
        operator = User.objects.create_user(
            email=f'operator-{uuid4()}@example.com',
            password='Strong-operator-password-123!',
            can_login=False,
            can_access_pos=True,
        )
        operator.pos_pin_hash = make_password('123456')
        operator.save(update_fields=['pos_pin_hash', 'updated_at'])
        profile = self.owner.company_accesses.get(company=self.company).access_profile
        UserCompanyAccess.objects.create(
            user=operator,
            company=self.company,
            access_profile=profile,
            can_login=False,
        )
        UserBranchAccess.objects.create(
            user=operator,
            branch=self.branch,
            access_profile=profile,
        )
        return operator

    def create_pos_authorizer(self, codes, *, can_access_pos=True, with_pin=True,
                              branch=None):
        branch = branch or self.branch
        profile = AccessProfile.objects.create(
            company=self.company, name=f'POS auth {uuid4()}',
            description='POS authorization test profile', is_system=False,
        )
        profile.permissions.set(FunctionalPermission.objects.filter(code__in=codes))
        authorizer = User.objects.create_user(
            email=f'authorizer-{uuid4()}@example.com',
            password='Web-password-is-not-the-pin-123!', can_login=False,
            can_access_pos=can_access_pos,
        )
        if with_pin:
            authorizer.pos_pin_hash = make_password('654321')
            authorizer.save(update_fields=['pos_pin_hash', 'updated_at'])
        UserCompanyAccess.objects.create(
            user=authorizer, company=self.company, access_profile=profile,
            can_login=False,
        )
        UserBranchAccess.objects.create(
            user=authorizer, branch=branch, access_profile=profile,
        )
        return authorizer

    def login_pos_operator(self):
        paired, _ = self.pair_device()
        operator = self.create_pos_operator()
        self.client.credentials(HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'])
        login = self.client.post(
            reverse('pos:operator-login'),
            {'operator_id': operator.pk, 'pin': '123456'},
            format='json',
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.client.credentials(
            HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'],
            HTTP_X_POS_OPERATOR_SESSION=login.data['operator_session']['token'],
        )
        return operator, paired

    def validate_pos_authorization(self, authorizer, *, purpose='sale', pin='654321'):
        return self.client.post(
            reverse('pos:sale-discount-authorization-validate'),
            {'type': purpose, 'user': authorizer.pk, 'method': 'pin', 'credential': pin},
            format='json',
        )

    def login_existing_pos_operator(self, operator, paired):
        self.client.credentials(HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'])
        login = self.client.post(
            reverse('pos:operator-login'),
            {'operator_id': operator.pk, 'pin': '654321'}, format='json',
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.client.credentials(
            HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'],
            HTTP_X_POS_OPERATOR_SESSION=login.data['operator_session']['token'],
        )

    def pos_sale_payload(self, cash_session):
        category = Category.objects.create(
            company=self.company, branch=self.branch, name=f'POS category {uuid4()}',
        )
        product = Product.objects.create(
            company=self.company, category=category, name=f'POS product {uuid4()}',
            internal_code=f'POS{uuid4().hex[:8]}', unit=Unit.UNIT,
            cost=Decimal('5.00'), sale_price=Decimal('20.00'),
            inventory_behavior=InventoryBehavior.DIRECT,
        )
        ProductBranchConfig.objects.create(
            product=product, branch=self.branch, category=category,
        )
        stock = Stock.objects.get(product=product, branch=self.branch)
        stock.current_quantity = Decimal('10')
        stock.average_unit_cost = Decimal('5.00')
        stock.last_unit_cost = Decimal('5.00')
        stock.save(update_fields=(
            'current_quantity', 'average_unit_cost', 'last_unit_cost', 'updated_at',
        ))
        cash_method = next(
            method for method in ensure_default_payment_methods(self.company)
            if method.code == 'cash'
        )
        return {
            'idempotency_key': str(uuid4()),
            'cash_session': cash_session.pk,
            'items': [{'client_item_id': str(uuid4()), 'product': product.pk, 'quantity': '1'}],
            'discount': {'type': 'amount', 'value': '0.00'},
            'service_fee_waived': True,
            'payments': [{
                'payment_method': cash_method.pk, 'amount': 'auto',
                'received_amount': '100.00',
            }],
        }

    def create_provider_checkout(self):
        operator, paired = self.login_pos_operator()
        register = CashRegister.objects.create(branch=self.branch, name=f'Provider cash {uuid4()}')
        BranchPOSSettings.objects.get_or_create(
            branch=self.branch, defaults={'cash_binding_mode': 'FLEXIBLE'},
        )
        opened = self.client.post(
            reverse('pos:cash-session-open'),
            {'register': register.pk, 'opening_amount': '0.00'}, format='json',
        )
        self.assertEqual(opened.status_code, 201, opened.data)
        checkout_response = self.client.post(
            reverse('pos:quick-checkout-create'),
            {
                key: value for key, value in self.pos_sale_payload(SimpleNamespace(pk=opened.data['id'])).items()
                if key not in {'cash_session', 'payments'}
            },
            format='json',
        )
        self.assertEqual(checkout_response.status_code, 201, checkout_response.data)
        checkout = QuickSaleCheckout.objects.get(pk=checkout_response.data['id'])
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        method = next(method for method in ensure_default_payment_methods(self.company) if method.code != 'cash')
        provider = PaymentProvider.objects.create(
            code=f'provider-{uuid4().hex[:8]}', name='Provider', integration_type='server_api',
        )
        connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=provider, name='Contrato',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
        )
        terminal = PaymentTerminal.objects.create(
            connection=connection, branch=self.branch, pos_device=device, name='Terminal',
        )
        return operator, device, checkout.cash_session, checkout, method, connection, terminal

    def start_configured_cielo_payment(self):
        _operator, device, _session, checkout, _method, _connection, _terminal = self.create_provider_checkout()
        cielo = PaymentProvider.objects.get(code='cielo')
        connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=cielo, name='Cielo local',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
            configuration={'merchant_code': '1234567890123456'},
        )
        PaymentTerminal.objects.create(
            connection=connection, branch=self.branch, pos_device=device, name='Cielo deste POS',
        )
        method = next(
            item for item in ensure_default_payment_methods(self.company)
            if item.code == 'credit_card'
        )
        started = self.client.post(
            reverse('pos:quick-sale-provider-payment-start', args=[checkout.pk]),
            {
                'payment_method': method.pk, 'provider': 'cielo', 'mode': 'remaining',
                'idempotency_key': str(uuid4()),
            },
            format='json',
        )
        self.assertEqual(started.status_code, 200, started.data)
        return checkout, started

    def create_provider_intent(self, checkout, operator, method, connection, terminal, *, mode='remaining', amount=None):
        return create_quick_sale_payment_intent(
            checkout=checkout, user=operator, payment_method_id=method.pk, mode=mode,
            amount=amount, allocations=[], provider_connection=connection, terminal=terminal,
            idempotency_key=uuid4(),
        )[0]

    def test_provider_resource_resolution_prefers_branch_and_rejects_ambiguity(self):
        _operator, device, _session, checkout, _method, _connection, _terminal = self.create_provider_checkout()
        cielo = PaymentProvider.objects.get(code='cielo')
        company_connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=cielo, name='Cielo company',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
        )
        branch_connection = PaymentProviderConnection.objects.create(
            company=self.company, branch=self.branch, provider=cielo, name='Cielo branch',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
        )
        PaymentTerminal.objects.create(
            connection=company_connection, branch=self.branch, pos_device=device, name='Company terminal',
        )
        PaymentTerminal.objects.create(
            connection=branch_connection, branch=self.branch, pos_device=device, name='Branch terminal',
        )

        connection, _terminal = resolve_provider_resources(checkout=checkout, provider_code='cielo')

        self.assertEqual(connection.pk, branch_connection.pk)
        PaymentProviderConnection.objects.create(
            company=self.company, branch=self.branch, provider=cielo, name='Cielo branch duplicate',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
        )
        with self.assertRaises(PaymentIntegrationConflict) as context:
            resolve_provider_resources(checkout=checkout, provider_code='cielo')
        self.assertEqual(context.exception.code, 'payment_provider_connection_ambiguous')

    def test_provider_resource_resolution_rejects_a_terminal_from_another_pos(self):
        _operator, device, _session, checkout, _method, _connection, _terminal = self.create_provider_checkout()
        cielo = PaymentProvider.objects.get(code='cielo')
        connection = PaymentProviderConnection.objects.create(
            company=self.company, branch=self.branch, provider=cielo, name='Cielo branch',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
        )
        other_device = POSDevice.objects.create(
            branch=self.branch, name='Outro POS', status=POSDevice.Status.ACTIVE,
        )
        PaymentTerminal.objects.create(
            connection=connection, branch=self.branch, pos_device=other_device, name='Outro terminal',
        )

        with self.assertRaises(PaymentIntegrationConflict) as context:
            resolve_provider_resources(checkout=checkout, provider_code='cielo')
        self.assertEqual(context.exception.code, 'payment_provider_terminal_unavailable')

    def test_generated_licensing_code_is_short_and_unambiguous(self):
        self.assertRegex(
            Branch.generate_licensing_code(),
            r'^CORE-[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{6}$',
        )

    def test_pairing_uses_opaque_contact_and_otp_can_only_be_consumed_once(self):
        confirmation, challenge_id = self.pair_device()

        self.assertEqual(confirmation.data['device']['status'], POSDevice.Status.ACTIVE)
        device = POSDevice.objects.get(pk=confirmation.data['device']['id'])
        self.assertNotEqual(device.credential_hash, confirmation.data['device_credential'])
        self.assertTrue(device.credential_fingerprint)

    def test_device_credential_fingerprint_authenticates_and_upgrades_legacy_device(self):
        confirmation, _ = self.pair_device()
        credential = confirmation.data['device_credential']
        device = POSDevice.objects.get(pk=confirmation.data['device']['id'])

        self.assertEqual(authenticate_device(credential).pk, device.pk)
        device.credential_fingerprint = ''
        device.save(update_fields=['credential_fingerprint', 'updated_at'])

        self.assertEqual(authenticate_device(credential).pk, device.pk)
        device.refresh_from_db()
        self.assertTrue(device.credential_fingerprint)

    def test_operator_session_fingerprint_authenticates_and_upgrades_legacy_session(self):
        operator, paired = self.login_pos_operator()
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        token = self.client.post(
            reverse('pos:operator-login'),
            {'operator_id': operator.pk, 'pin': '123456'}, format='json',
        ).data['operator_session']['token']
        session = POSOperatorSession.objects.filter(device=device, operator=operator).latest('created_at')

        self.assertEqual(authenticate_operator_session(device, token).pk, session.pk)
        session.token_fingerprint = ''
        session.save(update_fields=['token_fingerprint', 'updated_at'])

        self.assertEqual(authenticate_operator_session(device, token).pk, session.pk)
        session.refresh_from_db()
        self.assertTrue(session.token_fingerprint)

        replay = self.client.post(
            reverse('pos:pairing-confirm'),
            {
                'challenge_id': challenge_id,
                'code': '123456',
                'device': {'name': 'Replay'},
            },
            format='json',
        )
        self.assertEqual(replay.status_code, 400)

    def test_pairing_identifies_an_active_branch_by_cnpj(self):
        response = self.client.post(
            reverse('pos:pairing-identify'),
            {'identifier': '04.252.011/0001-10'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['branch']['display_name'], self.branch.name)

    def test_pairing_accepts_short_or_case_insensitive_licensing_code(self):
        self.branch.licensing_code = 'CORE-7K9P2M'
        self.branch.save(update_fields=['licensing_code', 'updated_at'])

        short = self.client.post(
            reverse('pos:pairing-identify'), {'identifier': '7k9p2m'}, format='json',
        )
        prefixed = self.client.post(
            reverse('pos:pairing-identify'), {'identifier': 'core-7k9p2m'}, format='json',
        )

        self.assertEqual(short.status_code, 200, short.data)
        self.assertEqual(prefixed.status_code, 200, prefixed.data)

    def test_wrong_otp_attempts_are_persisted_and_consume_the_challenge(self):
        identify = self.client.post(
            reverse('pos:pairing-identify'),
            {'identifier': self.branch.licensing_code},
            format='json',
        )
        channel = identify.data['channels'][0]
        with patch('apps.pos.services.secrets.randbelow', return_value=123456):
            otp = self.client.post(
                reverse('pos:pairing-request-otp'),
                {'pairing_flow_id': identify.data['pairing_flow_id'], 'channel_id': channel['id']},
                format='json',
            )
        for _ in range(5):
            response = self.client.post(
                reverse('pos:pairing-confirm'),
                {
                    'challenge_id': otp.data['challenge_id'],
                    'code': '000000',
                    'device': {'name': 'Stone Bar 01'},
                },
                format='json',
            )
            self.assertEqual(response.status_code, 400, response.data)
        challenge = AuthenticationChallenge.objects.get(pk=otp.data['challenge_id'])
        self.assertEqual(challenge.attempts, 5)
        self.assertIsNotNone(challenge.consumed_at)

    def test_active_device_authenticates_pos_only_operator_and_pin_is_rate_limited(self):
        paired, _ = self.pair_device()
        operator = User.objects.create_user(
            email='operator-pos@example.com',
            password='Strong-operator-password-123!',
            can_login=False,
            can_access_pos=True,
        )
        operator.pos_pin_hash = make_password('123456')
        operator.save(update_fields=['pos_pin_hash', 'updated_at'])
        profile = self.owner.company_accesses.get(company=self.company).access_profile
        UserCompanyAccess.objects.create(
            user=operator,
            company=self.company,
            access_profile=profile,
            can_login=False,
        )
        UserBranchAccess.objects.create(
            user=operator,
            branch=self.branch,
            access_profile=profile,
        )
        self.client.credentials(HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'])

        operators = self.client.get(reverse('pos:operators'))
        self.assertEqual(operators.status_code, 200, operators.data)
        self.assertEqual([item['id'] for item in operators.data['operators']], [operator.pk])

        for _ in range(5):
            response = self.client.post(
                reverse('pos:operator-login'),
                {'operator_id': operator.pk, 'pin': '000000'},
                format='json',
            )
            self.assertEqual(response.status_code, 401, response.data)
        response = self.client.post(
            reverse('pos:operator-login'),
            {'operator_id': operator.pk, 'pin': '123456'},
            format='json',
        )
        self.assertEqual(response.status_code, 429, response.data)
        self.assertTrue(POSOperatorPinAttempt.objects.get(device_id=paired.data['device']['id'], operator=operator).locked_until)

    def test_device_cannot_change_branch_and_cash_overrides_stay_in_scope(self):
        paired, _ = self.pair_device()
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        other_branch = create_branch_with_access(
            creator=self.owner,
            company=self.company,
            name='Outra filial',
            address_pending=True,
        )
        foreign_register = CashRegister.objects.create(branch=other_branch, name='Caixa externo')

        with self.assertRaises(ValidationError):
            POSDevice.objects.filter(pk=device.pk).update(branch=other_branch)
        with self.assertRaises(ValidationError):
            BranchPOSSettings.objects.create(
                branch=self.branch,
                default_cash_register=foreign_register,
            )
        with self.assertRaises(ValidationError):
            POSDeviceSettings.objects.create(
                device=device,
                default_cash_register=foreign_register,
            )

    def test_setting_pin_invalidates_other_outstanding_reset_links(self):
        self.owner.can_access_pos = True
        self.owner.save(update_fields=['can_access_pos', 'updated_at'])
        first, first_token = create_pin_reset_token(self.owner, self.company, self.owner)
        second, second_token = create_pin_reset_token(self.owner, self.company, self.owner)

        set_pos_pin(first_token, '123456')
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.consumed_at)
        self.assertIsNotNone(second.consumed_at)
        with self.assertRaises(DomainValidationError):
            set_pos_pin(second_token, '654321')

    @override_settings(POS_PIN_RESET_DELIVERY_LIMIT=1)
    def test_device_can_request_eligible_operator_pin_reset_without_leaking_delivery_data(self):
        paired, _ = self.pair_device()
        mail.outbox.clear()
        operator = self.create_pos_operator()
        other_operator = self.create_pos_operator()
        self.client.credentials(HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'])

        response = self.client.post(
            reverse('pos:operator-pin-reset', args=[operator.pk]),
            {'company': 999999, 'branch': 999999}, format='json',
        )

        self.assertEqual(response.status_code, 202, response.data)
        self.assertNotIn('token', response.data)
        self.assertNotIn(operator.email, str(response.data))
        self.assertEqual(len(mail.outbox), 1)
        audit = AuditLog.objects.get(action='pos.operator.pin_reset_requested')
        self.assertIsNone(audit.actor)
        self.assertEqual(audit.company, self.branch.company)
        self.assertEqual(audit.branch, self.branch)
        self.assertEqual(audit.metadata['source'], 'pos')
        self.assertEqual(audit.metadata['device_id'], paired.data['device']['id'])
        self.assertEqual(audit.metadata['target_user_id'], operator.pk)

        rate_limited = self.client.post(
            reverse('pos:operator-pin-reset', args=[other_operator.pk]), format='json',
        )
        self.assertEqual(rate_limited.status_code, 429, rate_limited.data)
        self.assertEqual(len(mail.outbox), 1)

        ineligible = User.objects.create_user(
            email='ineligible-reset@example.com', password='Strong-password-123!',
            can_login=False, can_access_pos=False,
        )
        denied = self.client.post(
            reverse('pos:operator-pin-reset', args=[ineligible.pk]), format='json',
        )
        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_backoffice_device_administration_keeps_credentials_private(self):
        paired, _ = self.pair_device()
        device_id = paired.data['device']['id']
        self.client.force_authenticate(self.owner)

        response = self.client.get(
            reverse('pos:pos-admin-device-list'), {'company': self.company.pk},
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'][0]['id'], str(device_id))
        self.assertNotIn('credential_hash', response.data['results'][0])
        self.assertNotIn(paired.data['device_credential'], str(response.data))

        blocked = self.client.post(
            reverse('pos:pos-admin-device-block', args=[device_id]),
            {'company': self.company.pk}, format='json',
        )
        self.assertEqual(blocked.status_code, 200, blocked.data)
        self.assertEqual(blocked.data['status'], POSDevice.Status.BLOCKED)

    def test_backoffice_pos_settings_are_scoped_to_branch(self):
        paired, _ = self.pair_device()
        device_id = paired.data['device']['id']
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            f"{reverse('pos:pos-admin-device-device-settings', args=[device_id])}?company={self.company.pk}",
            {'receipt_print_mode': 'automatic', 'paper_width': 58},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['receipt_print_mode'], 'automatic')
        self.assertEqual(response.data['effective_settings']['paper_width'], 58)

    def test_stock_visibility_setting_inherits_branch_and_accepts_device_override(self):
        paired, _ = self.pair_device()
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        BranchPOSSettings.objects.create(
            branch=self.branch, show_out_of_stock_products=False,
        )

        self.assertFalse(effective_settings(device)['show_out_of_stock_products'])
        POSDeviceSettings.objects.create(
            device=device, show_out_of_stock_products=True,
        )
        self.assertTrue(effective_settings(device)['show_out_of_stock_products'])

    def test_pos_customer_search_and_creation_are_scoped_to_device_company(self):
        operator, _ = self.login_pos_operator()

        created = self.client.post(
            reverse('pos:customers'), {
                'name': 'Cliente POS',
                'phone': '11999999999',
                'document': '52998224725',
            },
            format='json',
        )
        found = self.client.get(reverse('pos:customers'), {'q': 'Cliente POS'})

        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(found.status_code, 200, found.data)
        self.assertEqual(found.data['customers'], [created.data])
        UserPermissionBlock.objects.create(
            company=self.company, branch=None, user=operator,
            permission=FunctionalPermission.objects.get(code='customers.view'),
            created_by=self.owner,
        )
        self.assertEqual(
            self.client.get(reverse('pos:customers')).status_code,
            403,
        )
        hidden_conflict = self.client.post(reverse('pos:customers'), {
            'name': 'Outro Cliente', 'phone': '11999999999',
        }, format='json')
        self.assertEqual(hidden_conflict.status_code, 400, hidden_conflict.data)
        self.assertEqual(hidden_conflict.data['code'], 'customer_identity_conflict')
        self.assertEqual(hidden_conflict.data['details'], {})
        self.assertEqual(
            hidden_conflict.data['message'],
            'Já existe um cliente cadastrado com este telefone ou CPF.',
        )
        operator.permission_blocks.filter(permission__code='customers.view').delete()
        UserPermissionBlock.objects.create(
            company=self.company, branch=None, user=operator,
            permission=FunctionalPermission.objects.get(code='customers.add'),
            created_by=self.owner,
        )
        self.assertEqual(
            self.client.post(reverse('pos:customers'), {'name': 'Sem cadastro'}, format='json').status_code,
            403,
        )

    def test_pos_inactive_customer_conflict_can_be_reactivated(self):
        operator, _ = self.login_pos_operator()
        customer = create_customer(
            company=self.company, name='Cliente Inativo', phone='21999999999',
        )
        set_customer_status(customer=customer, status='inactive')

        search = self.client.get(reverse('pos:customers'), {'q': '(21) 99999-9999'})
        self.assertEqual(search.status_code, 200, search.data)
        self.assertEqual(search.data['customers'], [])
        self.assertEqual(search.data['inactive_identity']['customer']['id'], customer.pk)
        self.assertTrue(search.data['inactive_identity']['can_reactivate'])

        conflict = self.client.post(reverse('pos:customers'), {
            'name': 'Novo Cliente', 'phone': '21999999999',
        }, format='json')
        self.assertEqual(conflict.status_code, 400, conflict.data)
        self.assertEqual(conflict.data['code'], 'customer_inactive_identity_conflict')
        self.assertTrue(conflict.data['details']['can_reactivate'])

        activated = self.client.post(reverse('pos:customer-activate', args=[customer.pk]), format='json')
        self.assertEqual(activated.status_code, 200, activated.data)
        self.assertEqual(activated.data['id'], customer.pk)
        self.assertTrue(AuditLog.objects.filter(
            action='pos.customer.activated', object_id=str(customer.pk), actor=operator,
        ).exists())

        active_conflict = self.client.post(reverse('pos:customers'), {
            'name': 'Outro Cliente', 'phone': '21999999999',
        }, format='json')
        self.assertEqual(active_conflict.status_code, 400, active_conflict.data)
        self.assertEqual(active_conflict.data['code'], 'customer_identity_conflict')
        self.assertEqual(active_conflict.data['details']['customer']['status'], 'active')

        repeated_activation = self.client.post(
            reverse('pos:customer-activate', args=[customer.pk]), format='json',
        )
        self.assertEqual(repeated_activation.status_code, 200, repeated_activation.data)
        self.assertEqual(AuditLog.objects.filter(
            action='pos.customer.activated', object_id=str(customer.pk), actor=operator,
        ).count(), 1)

    def test_pos_rejects_phone_and_cpf_that_belong_to_different_customers(self):
        self.login_pos_operator()
        create_customer(company=self.company, name='Cliente A', phone='21999999999')
        create_customer(
            company=self.company, name='Cliente B', phone='21888888888', document='52998224725',
        )

        conflict = self.client.post(reverse('pos:customers'), {
            'name': 'Dados Cruzados',
            'phone': '21999999999',
            'document': '52998224725',
        }, format='json')

        self.assertEqual(conflict.status_code, 400, conflict.data)
        self.assertEqual(conflict.data['code'], 'customer_identity_mismatch')
        self.assertEqual(conflict.data['details'], {})
        self.assertEqual(Customer.objects.filter(company=self.company).count(), 2)

    def test_pos_inactive_customer_conflict_cannot_be_reactivated_without_permission(self):
        operator, _ = self.login_pos_operator()
        customer = create_customer(
            company=self.company, name='Cliente Inativo', phone='21999999999',
        )
        set_customer_status(customer=customer, status='inactive')
        UserPermissionBlock.objects.create(
            company=self.company, branch=None, user=operator,
            permission=FunctionalPermission.objects.get(code='customers.change'),
            created_by=self.owner,
        )

        conflict = self.client.post(reverse('pos:customers'), {
            'name': 'Novo Cliente', 'phone': '21999999999',
        }, format='json')
        self.assertEqual(conflict.status_code, 400, conflict.data)
        self.assertFalse(conflict.data['details']['can_reactivate'])
        self.assertIn('não possui permissão', conflict.data['message'])
        self.assertEqual(
            self.client.post(reverse('pos:customer-activate', args=[customer.pk])).status_code,
            403,
        )

    def test_pos_only_authorizer_uses_pin_and_permission_specific_lists(self):
        _, _ = self.login_pos_operator()
        authorizer = self.create_pos_authorizer({'sales.apply_discount'})
        item_authorizer = self.create_pos_authorizer({'sales.apply_item_discount'})

        discount = self.client.get(reverse('pos:sale-discount-authorizers'))
        item = self.client.get(reverse('pos:sale-item-discount-authorizers'))
        fee = self.client.get(reverse('pos:sale-service-fee-authorizers'))
        valid = self.validate_pos_authorization(authorizer)
        wrong_scope = self.validate_pos_authorization(authorizer, purpose='item')
        wrong_pin = self.validate_pos_authorization(authorizer, pin='000000')
        item_valid = self.validate_pos_authorization(item_authorizer, purpose='item')
        item_wrong_pin = self.validate_pos_authorization(
            item_authorizer, purpose='item', pin='000000',
        )

        self.assertEqual(discount.status_code, 200, discount.data)
        self.assertIn(authorizer.pk, [row['id'] for row in discount.data['authorizers']])
        self.assertNotIn(authorizer.pk, [row['id'] for row in item.data['authorizers']])
        self.assertIn(item_authorizer.pk, [row['id'] for row in item.data['authorizers']])
        self.assertNotIn(authorizer.pk, [row['id'] for row in fee.data['authorizers']])
        self.assertEqual(valid.status_code, 200, valid.data)
        self.assertEqual(wrong_scope.status_code, 400, wrong_scope.data)
        self.assertEqual(wrong_pin.status_code, 400, wrong_pin.data)
        self.assertEqual(item_valid.status_code, 200, item_valid.data)
        self.assertEqual(item_wrong_pin.status_code, 400, item_wrong_pin.data)

    def test_pos_authorizer_filters_access_pin_block_and_branch(self):
        _, _ = self.login_pos_operator()
        no_access = self.create_pos_authorizer(
            {'sales.apply_discount'}, can_access_pos=False,
        )
        no_pin = self.create_pos_authorizer({'sales.apply_discount'}, with_pin=False)
        blocked = self.create_pos_authorizer({'sales.apply_discount'})
        UserPermissionBlock.objects.create(
            company=self.company, branch=self.branch, user=blocked,
            permission=FunctionalPermission.objects.get(code='sales.apply_discount'),
            created_by=self.owner,
        )
        other_branch = create_branch_with_access(
            creator=self.owner, company=self.company, name='Filial autorizador',
            address_pending=True,
        )
        foreign = self.create_pos_authorizer(
            {'sales.apply_discount'}, branch=other_branch,
        )

        response = self.client.get(reverse('pos:sale-discount-authorizers'))

        self.assertEqual(response.status_code, 200, response.data)
        ids = [row['id'] for row in response.data['authorizers']]
        self.assertNotIn(no_access.pk, ids)
        self.assertNotIn(no_pin.pk, ids)
        self.assertNotIn(blocked.pk, ids)
        self.assertNotIn(foreign.pk, ids)
        for authorizer in (no_access, no_pin, blocked, foreign):
            rejected = self.validate_pos_authorization(authorizer)
            self.assertEqual(rejected.status_code, 400, rejected.data)

    def test_pos_authorization_rate_limit_and_audit_never_store_pin(self):
        _, paired = self.login_pos_operator()
        authorizer = self.create_pos_authorizer({'sales.apply_discount'})
        for _ in range(5):
            response = self.validate_pos_authorization(authorizer, pin='000000')
            self.assertEqual(response.status_code, 400, response.data)
        limited = self.validate_pos_authorization(authorizer, pin='000000')

        self.assertEqual(limited.status_code, 429, limited.data)
        self.assertEqual(limited.data['code'], 'authorization_pin_rate_limited')
        self.assertTrue(POSRequestRateLimit.objects.filter(locked_until__isnull=False).exists())
        failed = AuditLog.objects.filter(
            action='pos.authorization.failed', actor=authorizer,
        ).latest('id')
        rate_limited = AuditLog.objects.filter(
            action='pos.authorization.rate_limited', actor=authorizer,
        ).latest('id')
        for audit in (failed, rate_limited):
            self.assertEqual(audit.company_id, self.company.pk)
            self.assertEqual(audit.branch_id, self.branch.pk)
            self.assertEqual(audit.metadata['permission_code'], 'sales.apply_discount')
            self.assertEqual(audit.metadata['authorizer_user_id'], authorizer.pk)
            self.assertEqual(audit.metadata['device_id'], paired.data['device']['id'])
            self.assertNotIn('000000', str(audit.metadata))
            self.assertNotIn('654321', str(audit.metadata))
            self.assertNotIn('000000', str(audit.before))
            self.assertNotIn('654321', str(audit.after))
            self.assertNotIn('000000', str(audit))
            self.assertNotIn('654321', str(audit))
        self.client.credentials(
            HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'],
        )
        login = self.client.post(
            reverse('pos:operator-login'),
            {'operator_id': authorizer.pk, 'pin': '654321'},
            format='json',
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.assertTrue(login.data['operator_session']['token'])

    def test_pos_service_fee_finalization_requires_its_own_pin_authorization(self):
        paired, _ = self.pair_device()
        seller = self.create_pos_authorizer({'sales.create'})
        self.login_existing_pos_operator(seller, paired)
        register = CashRegister.objects.create(branch=self.branch, name='POS service fee')
        cash_session = open_session(register, '0.00', self.owner, self.branch)
        settings = self.branch.settings
        settings.charges_service_fee = True
        settings.service_fee_rate = Decimal('10.00')
        settings.save(update_fields=['charges_service_fee', 'service_fee_rate', 'updated_at'])
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        device.active_cash_session = cash_session
        device.save(update_fields=('active_cash_session', 'updated_at'))

        missing = self.client.post(
            reverse('pos:sale-finalize'), self.pos_sale_payload(cash_session), format='json',
        )
        discount_only = self.create_pos_authorizer({'sales.apply_discount'})
        wrong_permission_payload = self.pos_sale_payload(cash_session)
        wrong_permission_payload['service_fee_authorization'] = {
            'user': discount_only.pk, 'method': 'pin', 'credential': '654321',
        }
        wrong_permission = self.client.post(
            reverse('pos:sale-finalize'), wrong_permission_payload, format='json',
        )
        fee_authorizer = self.create_pos_authorizer({'sales.waive_service_fee'})
        wrong_pin_payload = self.pos_sale_payload(cash_session)
        wrong_pin_payload['service_fee_authorization'] = {
            'user': fee_authorizer.pk, 'method': 'pin', 'credential': '000000',
        }
        wrong_pin = self.client.post(
            reverse('pos:sale-finalize'), wrong_pin_payload, format='json',
        )
        accepted_payload = self.pos_sale_payload(cash_session)
        accepted_payload['service_fee_authorization'] = {
            'user': fee_authorizer.pk, 'method': 'pin', 'credential': '654321',
        }
        accepted = self.client.post(
            reverse('pos:sale-finalize'), accepted_payload, format='json',
        )

        self.assertEqual(missing.status_code, 400, missing.data)
        self.assertEqual(wrong_permission.status_code, 400, wrong_permission.data)
        self.assertEqual(wrong_pin.status_code, 400, wrong_pin.data)
        self.assertEqual(accepted.status_code, 201, accepted.data)

    def test_bootstrap_reports_fixed_and_flexible_cash_state_without_fake_selection(self):
        operator, paired = self.login_pos_operator()
        fixed_register = CashRegister.objects.create(branch=self.branch, name='Bar')
        fixed_session = open_session(
            fixed_register, '25.00', operator, self.branch, allow_pos_only=True,
        )
        BranchPOSSettings.objects.create(
            branch=self.branch,
            cash_binding_mode='FIXED',
            default_cash_register=fixed_register,
        )
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        device.active_cash_session = fixed_session
        device.save(update_fields=('active_cash_session', 'updated_at'))

        fixed = self.client.get(reverse('pos:bootstrap'))

        self.assertEqual(fixed.status_code, 200, fixed.data)
        self.assertEqual(fixed.data['cash']['mode'], 'FIXED')
        self.assertEqual(fixed.data['cash']['register']['id'], fixed_register.pk)
        self.assertEqual(fixed.data['cash']['session']['id'], fixed_session.pk)
        self.assertEqual(fixed.data['cash']['session']['opening_amount'], '25.00')
        UserPermissionBlock.objects.create(
            company=self.company,
            branch=self.branch,
            user=operator,
            permission=FunctionalPermission.objects.get(code='cash_registers.view'),
            created_by=self.owner,
        )
        redacted = self.client.get(reverse('pos:bootstrap'))
        self.assertEqual(redacted.status_code, 200, redacted.data)
        self.assertNotIn('opening_amount', redacted.data['cash']['session'])
        operator.permission_blocks.filter(permission__code='cash_registers.view').delete()

        flexible_register = CashRegister.objects.create(branch=self.branch, name='Pista')
        open_session(
            flexible_register, '10.00', operator, self.branch, allow_pos_only=True,
        )
        settings = self.branch.pos_settings
        settings.cash_binding_mode = 'FLEXIBLE'
        settings.save(update_fields=['cash_binding_mode', 'updated_at'])

        flexible = self.client.get(reverse('pos:bootstrap'))

        self.assertEqual(flexible.status_code, 200, flexible.data)
        self.assertEqual(flexible.data['cash']['mode'], 'FLEXIBLE')
        self.assertNotIn('register', flexible.data['cash'])
        self.assertNotIn('session', flexible.data['cash'])
        self.assertEqual(
            {item['id'] for item in flexible.data['cash']['registers']},
            {fixed_register.pk, flexible_register.pk},
        )

    def test_pos_cash_requires_operator_scope_and_uses_pos_only_operator_rbac(self):
        operator, paired = self.login_pos_operator()
        register = CashRegister.objects.create(branch=self.branch, name='Bar')
        BranchPOSSettings.objects.create(
            branch=self.branch,
            cash_binding_mode='FLEXIBLE',
        )

        self.client.credentials(HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'])
        without_operator = self.client.get(reverse('pos:cash-overview'))
        self.assertEqual(without_operator.status_code, 401, without_operator.data)

        self.client.credentials(
            HTTP_X_POS_DEVICE_CREDENTIAL=paired.data['device_credential'],
            HTTP_X_POS_OPERATOR_SESSION=self.client.post(
                reverse('pos:operator-login'),
                {'operator_id': operator.pk, 'pin': '123456'}, format='json',
            ).data['operator_session']['token'],
        )
        opened = self.client.post(
            reverse('pos:cash-session-open'),
            {'register': register.pk, 'opening_amount': '5.00'},
            format='json',
        )
        self.assertEqual(opened.status_code, 201, opened.data)
        session_id = opened.data['id']

        other_branch = create_branch_with_access(
            creator=self.owner, company=self.company, name='Outra filial', address_pending=True,
        )
        foreign_register = CashRegister.objects.create(branch=other_branch, name='Externo')
        foreign_session = open_session(foreign_register, '0.00', self.owner, other_branch)
        foreign_entry = self.client.post(
            reverse('pos:cash-session-entry', args=[foreign_session.pk]),
            {'idempotency_key': str(uuid4()), 'amount': '1.00', 'reason': 'Fora do escopo'},
            format='json',
        )
        self.assertEqual(foreign_entry.status_code, 404, foreign_entry.data)

        operator.is_superuser = True
        operator.save(update_fields=['is_superuser', 'updated_at'])
        UserPermissionBlock.objects.create(
            company=self.company,
            branch=self.branch,
            user=operator,
            permission=FunctionalPermission.objects.get(code='cash_registers.manual_entry'),
            created_by=self.owner,
        )
        blocked_entry = self.client.post(
            reverse('pos:cash-session-entry', args=[session_id]),
            {'idempotency_key': str(uuid4()), 'amount': '1.00', 'reason': 'Sem permissao'},
            format='json',
        )
        self.assertEqual(blocked_entry.status_code, 403, blocked_entry.data)

    def test_pos_cash_context_is_persisted_and_flexible_session_can_be_selected(self):
        operator, paired = self.login_pos_operator()
        first = CashRegister.objects.create(branch=self.branch, name='Balcão')
        second = CashRegister.objects.create(branch=self.branch, name='Pista')
        BranchPOSSettings.objects.create(
            branch=self.branch, cash_binding_mode='FLEXIBLE',
        )

        opened = self.client.post(
            reverse('pos:cash-session-open'),
            {'register': first.pk, 'opening_amount': '10.00'}, format='json',
        )

        self.assertEqual(opened.status_code, 201, opened.data)
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        self.assertEqual(device.active_cash_session_id, opened.data['id'])
        self.assertEqual(
            opened.data['cash_state']['active_session']['id'], opened.data['id'],
        )
        other_session = open_session(
            second, '0.00', operator, self.branch, allow_pos_only=True,
        )
        selected = self.client.post(
            reverse('pos:cash-session-select'), {'register': second.pk}, format='json',
        )

        self.assertEqual(selected.status_code, 200, selected.data)
        device.refresh_from_db()
        self.assertEqual(device.active_cash_session_id, other_session.pk)
        self.assertEqual(
            selected.data['cash_state']['active_session']['id'], other_session.pk,
        )
        closed = self.client.post(
            reverse('pos:cash-session-close', args=[other_session.pk]),
            {'closing_amount_informed': '0.00'}, format='json',
        )
        self.assertEqual(closed.status_code, 200, closed.data)
        self.assertIsNone(closed.data['cash_state']['active_session'])
        device.refresh_from_db()
        self.assertIsNone(device.active_cash_session_id)

    def test_flexible_cash_selection_requires_cash_open_permission(self):
        operator, paired = self.login_pos_operator()
        first = CashRegister.objects.create(branch=self.branch, name='Selection first')
        second = CashRegister.objects.create(branch=self.branch, name='Selection second')
        first_session = open_session(
            first, '0.00', operator, self.branch, allow_pos_only=True,
        )
        open_session(second, '0.00', operator, self.branch, allow_pos_only=True)
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        device.active_cash_session = first_session
        device.save(update_fields=('active_cash_session', 'updated_at'))
        UserPermissionBlock.objects.create(
            company=self.company,
            branch=self.branch,
            user=operator,
            permission=FunctionalPermission.objects.get(code='cash_registers.open'),
            created_by=self.owner,
        )

        selected = self.client.post(
            reverse('pos:cash-session-select'), {'register': second.pk}, format='json',
        )

        self.assertEqual(selected.status_code, 403, selected.data)
        device.refresh_from_db()
        self.assertEqual(device.active_cash_session_id, first_session.pk)

    def test_flexible_cash_selection_rejects_unavailable_register(self):
        operator, paired = self.login_pos_operator()
        active_register = CashRegister.objects.create(branch=self.branch, name='Available selection cash')
        unavailable_register = CashRegister.objects.create(branch=self.branch, name='Unavailable selection cash')
        BranchPOSSettings.objects.create(branch=self.branch, cash_binding_mode='FLEXIBLE')
        active_session = open_session(
            active_register, '0.00', operator, self.branch, allow_pos_only=True,
        )
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        device.active_cash_session = active_session
        device.save(update_fields=('active_cash_session', 'updated_at'))

        selected = self.client.post(
            reverse('pos:cash-session-select'), {'register': unavailable_register.pk}, format='json',
        )

        self.assertEqual(selected.status_code, 409, selected.data)
        self.assertEqual(selected.data['code'], 'cash_session_unavailable')
        device.refresh_from_db()
        self.assertEqual(device.active_cash_session_id, active_session.pk)

    def test_quick_checkout_binds_non_cash_tender_to_active_device_session(self):
        _operator, _paired = self.login_pos_operator()
        register = CashRegister.objects.create(branch=self.branch, name='Quick checkout cash')
        BranchPOSSettings.objects.create(branch=self.branch, cash_binding_mode='FLEXIBLE')
        opened = self.client.post(
            reverse('pos:cash-session-open'),
            {'register': register.pk, 'opening_amount': '0.00'}, format='json',
        )
        self.assertEqual(opened.status_code, 201, opened.data)
        payload = self.pos_sale_payload(SimpleNamespace(pk=opened.data['id']))
        checkout = self.client.post(
            reverse('pos:quick-checkout-create'),
            {key: value for key, value in payload.items() if key not in {'cash_session', 'payments'}},
            format='json',
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        non_cash_method = next(
            method for method in ensure_default_payment_methods(self.company)
            if method.code != 'cash'
        )
        recorded = self.client.post(
            reverse('pos:quick-checkout-payment', args=[checkout.data['id']]),
            {
                'payment_method': non_cash_method.pk,
                'mode': 'value',
                'amount': '20.00',
                'idempotency_key': str(uuid4()),
            },
            format='json',
        )

        self.assertEqual(recorded.status_code, 200, recorded.data)
        self.assertEqual(
            QuickSalePayment.objects.get(checkout_id=checkout.data['id']).cash_session_id,
            opened.data['id'],
        )

    def test_quick_checkout_payment_rejects_changed_cash_context(self):
        operator, paired = self.login_pos_operator()
        first = CashRegister.objects.create(branch=self.branch, name='Checkout context A')
        second = CashRegister.objects.create(branch=self.branch, name='Checkout context B')
        BranchPOSSettings.objects.create(branch=self.branch, cash_binding_mode='FLEXIBLE')
        opened = self.client.post(
            reverse('pos:cash-session-open'),
            {'register': first.pk, 'opening_amount': '0.00'}, format='json',
        )
        self.assertEqual(opened.status_code, 201, opened.data)
        checkout_payload = self.pos_sale_payload(SimpleNamespace(pk=opened.data['id']))
        checkout = self.client.post(
            reverse('pos:quick-checkout-create'),
            {key: value for key, value in checkout_payload.items() if key not in {'cash_session', 'payments'}},
            format='json',
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        open_session(second, '0.00', operator, self.branch, allow_pos_only=True)
        switched = self.client.post(
            reverse('pos:cash-session-select'), {'register': second.pk}, format='json',
        )
        self.assertEqual(switched.status_code, 200, switched.data)
        non_cash_method = next(
            method for method in ensure_default_payment_methods(self.company)
            if method.code != 'cash'
        )

        recorded = self.client.post(
            reverse('pos:quick-checkout-payment', args=[checkout.data['id']]),
            {
                'payment_method': non_cash_method.pk,
                'mode': 'value',
                'amount': '20.00',
                'idempotency_key': str(uuid4()),
            },
            format='json',
        )

        self.assertEqual(recorded.status_code, 409, recorded.data)
        self.assertEqual(recorded.data['code'], 'cash_context_changed')
        self.assertFalse(QuickSalePayment.objects.filter(checkout_id=checkout.data['id']).exists())

    def test_provider_attempt_start_rejects_a_switched_cash_context(self):
        operator, device, _session, checkout, method, connection, terminal = self.create_provider_checkout()
        intent = self.create_provider_intent(checkout, operator, method, connection, terminal)
        other_session = open_session(
            CashRegister.objects.create(branch=self.branch, name='Cash context B'),
            '0.00', operator, self.branch, allow_pos_only=True,
        )
        device.active_cash_session = other_session
        device.save(update_fields=('active_cash_session', 'updated_at'))

        with self.assertRaises(QuickCheckoutConflict) as context:
            start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)

        self.assertEqual(context.exception.code, 'cash_context_changed')
        self.assertFalse(intent.attempts.exists())

    def test_provider_result_and_apply_keep_the_original_checkout_cash_context(self):
        operator, device, session, checkout, method, connection, terminal = self.create_provider_checkout()
        intent = self.create_provider_intent(checkout, operator, method, connection, terminal)
        attempt = start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)
        other_session = open_session(
            CashRegister.objects.create(branch=self.branch, name='Result context B'),
            '0.00', operator, self.branch, allow_pos_only=True,
        )
        device.active_cash_session = other_session
        device.save(update_fields=('active_cash_session', 'updated_at'))

        approved_attempt, approved_intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.APPROVED,
        )
        payment, _replayed = apply_approved_quick_sale_payment_intent(
            checkout=checkout, intent=approved_intent, user=operator,
        )

        self.assertEqual(approved_attempt.status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(payment.cash_session_id, session.pk)
        self.assertNotEqual(payment.cash_session_id, other_session.pk)

    def test_close_and_cancel_block_processing_unknown_and_approved_provider_intents(self):
        operator, _device, session, checkout, method, connection, terminal = self.create_provider_checkout()
        intent = self.create_provider_intent(checkout, operator, method, connection, terminal)
        attempt = start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)

        def assert_session_actions_blocked():
            with self.assertRaises(ValidationError):
                close_session(session, '0.00', operator, self.branch, allow_pos_only=True)
            with self.assertRaises(ValidationError):
                cancel_session(session, 'PAY-1.2 test', operator, self.branch)
            session.refresh_from_db()
            self.assertEqual(session.status, CashSessionStatus.OPEN)

        assert_session_actions_blocked()
        attempt, _intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.UNKNOWN,
        )
        assert_session_actions_blocked()
        _attempt, _intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.APPROVED,
        )
        assert_session_actions_blocked()

    def test_cancel_session_blocks_any_paid_open_checkout_and_allows_unpaid_checkout(self):
        operator, device, partial_session, partial_checkout, _method, _connection, _terminal = self.create_provider_checkout()
        cash_method = self.company.payment_methods.get(code='cash')
        record_quick_checkout_payment(
            checkout=partial_checkout, user=operator, payment_method_id=cash_method.pk,
            mode='value', amount='5.00', received_amount='5.00', allocations=[],
            idempotency_key=uuid4(), pos_device=device,
        )
        with self.assertRaises(ValidationError):
            cancel_session(partial_session, 'Partial payment', operator, self.branch)

        operator, device, manual_session, manual_checkout, _method, _connection, _terminal = self.create_provider_checkout()
        record_quick_checkout_payment(
            checkout=manual_checkout, user=operator, payment_method_id=cash_method.pk,
            mode='remaining', amount=None, received_amount='20.00', allocations=[],
            idempotency_key=uuid4(), pos_device=device,
        )
        with self.assertRaises(ValidationError):
            cancel_session(manual_session, 'Full manual payment', operator, self.branch)

        operator, _device, provider_session, provider_checkout, method, connection, terminal = self.create_provider_checkout()
        intent = self.create_provider_intent(provider_checkout, operator, method, connection, terminal)
        attempt = start_quick_sale_payment_attempt(checkout=provider_checkout, intent=intent, user=operator)
        _attempt, approved_intent = resolve_quick_sale_payment_attempt(
            checkout=provider_checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.APPROVED,
        )
        apply_approved_quick_sale_payment_intent(
            checkout=provider_checkout, intent=approved_intent, user=operator,
        )
        with self.assertRaises(ValidationError):
            cancel_session(provider_session, 'Provider payment', operator, self.branch)

        operator, _device, unpaid_session, _checkout, _method, _connection, _terminal = self.create_provider_checkout()
        cancelled = cancel_session(unpaid_session, 'No payments', operator, self.branch)
        self.assertEqual(cancelled.status, CashSessionStatus.CANCELLED)

    def test_unknown_intent_blocks_checkout_until_reconciled_and_applies_once(self):
        operator, device, session, checkout, method, connection, terminal = self.create_provider_checkout()
        intent = self.create_provider_intent(checkout, operator, method, connection, terminal)
        attempt = start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)
        attempt, unknown_intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.UNKNOWN,
        )
        cash_method = self.company.payment_methods.get(code='cash')

        with self.assertRaises(QuickCheckoutConflict) as context:
            record_quick_checkout_payment(
                checkout=checkout, user=operator, payment_method_id=cash_method.pk,
                mode='value', amount='1.00', received_amount='1.00', allocations=[],
                idempotency_key=uuid4(), pos_device=device,
            )
        self.assertEqual(context.exception.code, 'payment_intent_in_progress')
        with self.assertRaises(QuickCheckoutConflict):
            cancel_quick_checkout(checkout=checkout, user=operator)
        with self.assertRaises(QuickCheckoutConflict):
            finalize_quick_checkout(
                checkout=checkout, user=operator, permissions=[], idempotency_key=uuid4(),
            )
        with self.assertRaises(QuickCheckoutConflict):
            start_quick_sale_payment_attempt(checkout=checkout, intent=unknown_intent, user=operator)
        with self.assertRaises(ValidationError):
            close_session(session, '0.00', operator, self.branch, allow_pos_only=True)
        with self.assertRaises(ValidationError):
            cancel_session(session, 'Unknown provider result', operator, self.branch)

        _attempt, approved_intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.APPROVED,
        )
        payment, replayed = apply_approved_quick_sale_payment_intent(
            checkout=checkout, intent=approved_intent, user=operator,
        )
        replay, replayed_again = apply_approved_quick_sale_payment_intent(
            checkout=checkout, intent=approved_intent, user=operator,
        )
        self.assertFalse(replayed)
        self.assertTrue(replayed_again)
        self.assertEqual(payment.pk, replay.pk)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 1)

    def test_apply_rejects_every_invalid_frozen_application_context(self):
        cases = (
            ('invalid-mode', lambda item: {'mode': 'invalid', 'allocations': []}),
            ('value-with-allocations', lambda item: {
                'mode': 'value', 'allocations': [{'item': item.pk, 'allocated_quantity': '1', 'amount': '20.00'}],
            }),
            ('remaining-with-allocations', lambda item: {
                'mode': 'remaining', 'allocations': [{'item': item.pk, 'allocated_quantity': '1', 'amount': '20.00'}],
            }),
            ('external-item', lambda item: {
                'mode': 'items', 'allocations': [{'item': 999999999, 'allocated_quantity': '1', 'amount': '20.00'}],
            }),
            ('duplicate-item', lambda item: {
                'mode': 'items', 'allocations': [
                    {'item': item.pk, 'allocated_quantity': '1', 'amount': '10.00'},
                    {'item': item.pk, 'allocated_quantity': '1', 'amount': '10.00'},
                ],
            }),
            ('nonpositive-quantity', lambda item: {
                'mode': 'items', 'allocations': [{'item': item.pk, 'allocated_quantity': '0', 'amount': '20.00'}],
            }),
            ('excessive-quantity', lambda item: {
                'mode': 'items', 'allocations': [{'item': item.pk, 'allocated_quantity': '2', 'amount': '20.00'}],
            }),
            ('tampered-allocation-amount', lambda item: {
                'mode': 'items', 'allocations': [{'item': item.pk, 'allocated_quantity': '1', 'amount': '19.00'}],
            }),
            ('allocation-total-different-from-intent', lambda item: {
                'mode': 'items', 'allocations': [{'item': item.pk, 'allocated_quantity': '1', 'amount': '20.00'}],
                'amount': '19.00',
            }),
        )
        for name, build_context in cases:
            with self.subTest(context=name):
                operator, _device, _session, checkout, method, connection, terminal = self.create_provider_checkout()
                intent = self.create_provider_intent(checkout, operator, method, connection, terminal)
                attempt = start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)
                _attempt, approved_intent = resolve_quick_sale_payment_attempt(
                    checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.APPROVED,
                )
                context = {
                    'amount': f'{approved_intent.amount:.2f}',
                    **build_context(checkout.items.get()),
                }
                # The model normally prevents this write; apply must still defend
                # against data already compromised outside the application layer.
                PaymentIntent._base_manager.filter(pk=approved_intent.pk).update(
                    application_context=context,
                )
                with self.assertRaises(QuickCheckoutConflict) as error:
                    apply_approved_quick_sale_payment_intent(
                        checkout=checkout, intent=approved_intent, user=operator,
                    )
                self.assertEqual(error.exception.code, 'payment_intent_context_invalid')
                self.assertFalse(QuickSalePayment.objects.filter(checkout=checkout).exists())

    def test_partial_manual_and_provider_payment_finalize_with_two_sources(self):
        operator, device, _session, checkout, method, connection, terminal = self.create_provider_checkout()
        cash_method = self.company.payment_methods.get(code='cash')
        manual_payment, _replayed = record_quick_checkout_payment(
            checkout=checkout, user=operator, payment_method_id=cash_method.pk,
            mode='value', amount='5.00', received_amount='5.00', allocations=[],
            idempotency_key=uuid4(), pos_device=device,
        )
        intent = self.create_provider_intent(checkout, operator, method, connection, terminal)
        attempt = start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)
        approved_attempt, approved_intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.APPROVED,
        )
        provider_payment, _replayed = apply_approved_quick_sale_payment_intent(
            checkout=checkout, intent=approved_intent, user=operator,
        )
        paid, remaining = checkout_balance(checkout)

        finalized = self.client.post(
            reverse('pos:quick-checkout-finalize', args=[checkout.pk]),
            {'idempotency_key': str(uuid4())}, format='json',
        )
        self.assertEqual(finalized.status_code, 200, finalized.data)
        manual_payment.refresh_from_db()
        sale = manual_payment.final_payment.sale

        self.assertEqual(paid, Decimal('20.00'))
        self.assertEqual(remaining, Decimal('0.00'))
        self.assertEqual(sale.payments.count(), 2)
        self.assertEqual(provider_payment.source_payment_attempt_id, approved_attempt.pk)
        self.assertEqual(provider_payment.final_payment.source_quick_sale_payment_id, provider_payment.pk)
        self.assertEqual(manual_payment.final_payment.source_quick_sale_payment_id, manual_payment.pk)
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 2)

    def test_provider_payment_requires_provider_reversal_while_manual_payment_can_reverse(self):
        operator, device, _session, checkout, method, connection, terminal = self.create_provider_checkout()
        manual_method = self.company.payment_methods.get(code='cash')
        manual_payment, _replayed = record_quick_checkout_payment(
            checkout=checkout, user=operator, payment_method_id=manual_method.pk,
            mode='value', amount='5.00', received_amount='5.00', allocations=[],
            idempotency_key=uuid4(), pos_device=device,
        )
        intent = self.create_provider_intent(checkout, operator, method, connection, terminal)
        attempt = start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)
        _attempt, approved_intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.APPROVED,
        )
        provider_payment, _replayed = apply_approved_quick_sale_payment_intent(
            checkout=checkout, intent=approved_intent, user=operator,
        )

        with self.assertRaises(QuickCheckoutConflict) as context:
            reverse_quick_checkout_payment(
                payment=provider_payment, user=operator, reason='Provider test', idempotency_key=uuid4(),
            )
        self.assertEqual(context.exception.code, 'provider_reversal_required')
        reversal, replayed = reverse_quick_checkout_payment(
            payment=manual_payment, user=operator, reason='Manual test', idempotency_key=uuid4(),
        )
        self.assertFalse(replayed)
        self.assertEqual(reversal.reversal_of_id, manual_payment.pk)

    def test_provider_fallback_uses_the_approved_attempt_connection(self):
        operator, device, _session, checkout, method, connection, terminal = self.create_provider_checkout()
        intent = self.create_provider_intent(checkout, operator, method, connection, terminal)
        first = start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)
        _first, declined_intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=first, user=operator, status=PaymentAttemptStatus.DECLINED,
        )
        reassigned_device = POSDevice.objects.create(
            branch=self.branch, name='Fallback reassignment', status=POSDevice.Status.ACTIVE,
        )
        terminal.pos_device = reassigned_device
        terminal.save()
        fallback_provider = PaymentProvider.objects.create(
            code=f'fallback-{uuid4().hex[:8]}', name='Fallback', integration_type='server_api',
        )
        fallback_connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=fallback_provider, name='Fallback connection',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
        )
        fallback_terminal = PaymentTerminal.objects.create(
            connection=fallback_connection, branch=self.branch, pos_device=device,
            name='Fallback terminal',
        )
        second = start_quick_sale_payment_attempt(
            checkout=checkout, intent=declined_intent, user=operator,
            provider_connection=fallback_connection, terminal=fallback_terminal,
        )
        approved_attempt, approved_intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=second, user=operator, status=PaymentAttemptStatus.APPROVED,
        )
        payment, _replayed = apply_approved_quick_sale_payment_intent(
            checkout=checkout, intent=approved_intent, user=operator,
        )

        self.assertEqual(approved_attempt.provider_connection_id, fallback_connection.pk)
        self.assertEqual(approved_attempt.terminal_id, fallback_terminal.pk)
        self.assertEqual(approved_attempt.provider_connection.provider_id, fallback_provider.pk)
        self.assertEqual(payment.source_payment_attempt_id, approved_attempt.pk)

    def test_provider_payment_flows_from_quick_checkout_to_sale_payment(self):
        operator, paired = self.login_pos_operator()
        register = CashRegister.objects.create(branch=self.branch, name='Provider checkout cash')
        BranchPOSSettings.objects.create(branch=self.branch, cash_binding_mode='FLEXIBLE')
        opened = self.client.post(
            reverse('pos:cash-session-open'),
            {'register': register.pk, 'opening_amount': '0.00'}, format='json',
        )
        self.assertEqual(opened.status_code, 201, opened.data)
        checkout_response = self.client.post(
            reverse('pos:quick-checkout-create'),
            {
                key: value for key, value in self.pos_sale_payload(SimpleNamespace(pk=opened.data['id'])).items()
                if key not in {'cash_session', 'payments'}
            },
            format='json',
        )
        self.assertEqual(checkout_response.status_code, 201, checkout_response.data)
        checkout = QuickSaleCheckout.objects.get(pk=checkout_response.data['id'])
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        method = next(method for method in ensure_default_payment_methods(self.company) if method.code != 'cash')
        provider = PaymentProvider.objects.create(
            code='provider-e2e', name='Provider E2E', integration_type='server_api',
        )
        connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=provider, name='Contrato E2E',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
        )
        terminal = PaymentTerminal.objects.create(
            connection=connection, branch=self.branch, pos_device=device, name='Terminal E2E',
        )

        intent, replayed = create_quick_sale_payment_intent(
            checkout=checkout, user=operator, payment_method_id=method.pk, mode='remaining',
            amount=None, allocations=[], provider_connection=connection, terminal=terminal,
            idempotency_key=uuid4(),
        )
        self.assertFalse(replayed)
        self.assertEqual(intent.status, 'ready')
        attempt = start_quick_sale_payment_attempt(checkout=checkout, intent=intent, user=operator)
        method.status = Status.INACTIVE
        method.save()
        approved_attempt, approved_intent = resolve_quick_sale_payment_attempt(
            checkout=checkout, attempt=attempt, user=operator, status=PaymentAttemptStatus.APPROVED,
        )
        self.assertEqual(approved_intent.status, 'approved')
        self.assertFalse(QuickSalePayment.objects.filter(checkout=checkout).exists())
        with self.assertRaises(ValidationError):
            QuickSalePayment.objects.create(
                checkout=checkout, payment_method=method, amount=approved_intent.amount,
                operator=operator, cash_session=checkout.cash_session,
                source_type='provider', source_payment_attempt=approved_attempt,
                idempotency_key=uuid4(), request_fingerprint='direct-provider-payment',
            )

        payment, applied_replay = apply_approved_quick_sale_payment_intent(
            checkout=checkout, intent=approved_intent, user=operator,
        )
        replay, applied_replay_again = apply_approved_quick_sale_payment_intent(
            checkout=checkout, intent=approved_intent, user=operator,
        )
        self.assertFalse(applied_replay)
        self.assertTrue(applied_replay_again)
        self.assertEqual(replay.pk, payment.pk)
        self.assertEqual(payment.source_payment_attempt_id, approved_attempt.pk)

        finalized = self.client.post(
            reverse('pos:quick-checkout-finalize', args=[checkout.pk]),
            {'idempotency_key': str(uuid4())}, format='json',
        )
        self.assertEqual(finalized.status_code, 200, finalized.data)
        sale_payment = payment.final_payment
        self.assertEqual(sale_payment.source_quick_sale_payment_id, payment.pk)
        self.assertEqual(sale_payment.payment_method_code, method.code)
        self.assertEqual(sale_payment.payment_method_name, method.name)
        with self.assertRaises(ValidationError):
            Payment.objects.create(
                sale=sale_payment.sale, payment_method=method, amount=payment.amount,
                source_quick_sale_payment=payment,
            )

    def test_pos_finalize_sale_uses_active_cash_session_inside_service_transaction(self):
        operator, paired = self.login_pos_operator()
        register = CashRegister.objects.create(branch=self.branch, name='Direct POS cash')
        cash_session = open_session(register, '0.00', operator, self.branch, allow_pos_only=True)
        device = POSDevice.objects.get(pk=paired.data['device']['id'])
        device.active_cash_session = cash_session
        device.save(update_fields=('active_cash_session', 'updated_at'))
        payload = self.pos_sale_payload(cash_session)
        product = Product.objects.get(pk=payload['items'][0]['product'])
        product.emits_ticket = True
        product.save(update_fields=('emits_ticket', 'updated_at'))

        finalized = self.client.post(
            reverse('pos:sale-finalize'), payload, format='json',
        )

        self.assertEqual(finalized.status_code, 201, finalized.data)
        self.assertEqual(finalized.data['sale']['cash_session'], cash_session.pk)
        self.assertEqual(finalized.data['effects']['print_document_id'], finalized.data['effects']['print_document']['id'])
        self.assertIn('reprint_eligible', finalized.data['effects']['print_document'])
        self.assertEqual(len(finalized.data['effects']['tickets']), 1)
        ticket = finalized.data['effects']['tickets'][0]
        self.assertIsNotNone(ticket['id'])
        self.assertIsNotNone(ticket['print_document_id'])
        self.assertIn('reprint_eligible', ticket['print_document'])

    def test_pos_superuser_without_effective_sales_create_cannot_start_sale(self):
        operator, _ = self.login_pos_operator()
        operator.is_superuser = True
        operator.save(update_fields=['is_superuser', 'updated_at'])
        UserPermissionBlock.objects.create(
            company=self.company, branch=self.branch, user=operator,
            permission=FunctionalPermission.objects.get(code='sales.create'),
            created_by=self.owner,
        )

        response = self.client.post(reverse('pos:sale-finalize'), {}, format='json')

        self.assertEqual(response.status_code, 403, response.data)

    def test_pos_cash_overview_allows_operational_permissions_but_redacts_opening_amount(self):
        operator, _ = self.login_pos_operator()
        register = CashRegister.objects.create(branch=self.branch, name='Bar')
        BranchPOSSettings.objects.create(
            branch=self.branch, cash_binding_mode='FIXED', default_cash_register=register,
        )
        open_session(register, '30.00', operator, self.branch, allow_pos_only=True)
        view_permission = FunctionalPermission.objects.get(code='cash_registers.view')
        UserPermissionBlock.objects.create(
            company=self.company, branch=self.branch, user=operator,
            permission=view_permission, created_by=self.owner,
        )

        overview = self.client.get(reverse('pos:cash-overview'))

        self.assertEqual(overview.status_code, 200, overview.data)
        self.assertNotIn('opening_amount', overview.data['session'])
        summary = self.client.get(reverse('pos:cash-session-summary', args=[overview.data['session']['id']]))
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertTrue(overview.data['session']['capabilities']['can_view'])
        for code in (
            'cash_registers.open', 'cash_registers.manual_entry',
            'cash_registers.withdraw', 'cash_registers.close',
            'cash_registers.administer_others',
        ):
            UserPermissionBlock.objects.create(
                company=self.company, branch=self.branch, user=operator,
                permission=FunctionalPermission.objects.get(code=code), created_by=self.owner,
            )

        denied = self.client.get(reverse('pos:cash-overview'))
        self.assertEqual(denied.status_code, 403, denied.data)

    def test_pos_cash_beneficiaries_filter_category_and_device_company_scope(self):
        _, _ = self.login_pos_operator()
        profile = self.owner.company_accesses.get(company=self.company).access_profile
        dj = User.objects.create_user(
            email='dj-beneficiary@example.com', password='Strong-password-123!',
            can_login=False, user_type=User.UserType.DJ,
        )
        UserCompanyAccess.objects.create(
            user=dj, company=self.company, access_profile=profile, can_login=False,
        )
        foreign = User.objects.create_user(
            email='foreign-beneficiary@example.com', password='Strong-password-123!',
            can_login=False, user_type=User.UserType.DJ,
        )

        djs = self.client.get(
            f"{reverse('pos:cash-beneficiaries')}?category=dj&company=999999&branch=999999",
        )
        advance = self.client.get(f"{reverse('pos:cash-beneficiaries')}?category=advance")

        self.assertEqual(djs.status_code, 200, djs.data)
        self.assertEqual(djs.data['beneficiaries'], [{
            'id': dj.pk, 'name': dj.email, 'user_type': User.UserType.DJ,
        }])
        self.assertEqual(advance.status_code, 200, advance.data)
        self.assertIn(dj.pk, {item['id'] for item in advance.data['beneficiaries']})
        self.assertNotIn(foreign.pk, {item['id'] for item in advance.data['beneficiaries']})
        self.assertEqual(
            self.client.get(f"{reverse('pos:cash-beneficiaries')}?category=invalid").status_code,
            400,
        )

    def test_pos_withdrawal_accepts_company_beneficiary(self):
        operator, _ = self.login_pos_operator()
        register = CashRegister.objects.create(branch=self.branch, name='Bar')
        BranchPOSSettings.objects.create(branch=self.branch, cash_binding_mode='FLEXIBLE')
        opened = self.client.post(
            reverse('pos:cash-session-open'),
            {'register': register.pk, 'opening_amount': '0.00'}, format='json',
        )
        self.assertEqual(opened.status_code, 201, opened.data)
        profile = self.owner.company_accesses.get(company=self.company).access_profile
        dj = User.objects.create_user(
            email='withdrawal-dj@example.com', password='Strong-password-123!',
            can_login=False, user_type=User.UserType.DJ,
        )
        UserCompanyAccess.objects.create(
            user=dj, company=self.company, access_profile=profile, can_login=False,
        )

        withdrawal = self.client.post(
            reverse('pos:cash-session-withdrawal', args=[opened.data['id']]),
            {
                'idempotency_key': str(uuid4()), 'amount': '25.00', 'reason': 'Cache DJ',
                'category': 'dj', 'result_effect': 'operating_expense', 'beneficiary_user': dj.pk,
            },
            format='json',
        )

        self.assertEqual(withdrawal.status_code, 201, withdrawal.data)
        self.assertEqual(withdrawal.data['beneficiary']['id'], dj.pk)
        self.assertEqual(CashMovement.objects.get(pk=withdrawal.data['id']).beneficiary_user, dj)

    def test_pos_cash_movement_replays_idempotently(self):
        _, _ = self.login_pos_operator()
        register = CashRegister.objects.create(branch=self.branch, name='Bar')
        BranchPOSSettings.objects.create(branch=self.branch, cash_binding_mode='FLEXIBLE')
        opened = self.client.post(
            reverse('pos:cash-session-open'),
            {'register': register.pk, 'opening_amount': '0.00'},
            format='json',
        )
        self.assertEqual(opened.status_code, 201, opened.data)
        key = str(uuid4())
        payload = {'idempotency_key': key, 'amount': '12.00', 'reason': 'Troco inicial'}

        created = self.client.post(
            reverse('pos:cash-session-entry', args=[opened.data['id']]), payload, format='json',
        )
        replayed = self.client.post(
            reverse('pos:cash-session-entry', args=[opened.data['id']]), payload, format='json',
        )

        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(replayed.status_code, 200, replayed.data)
        self.assertEqual(created.data['id'], replayed.data['id'])
        self.assertEqual(CashMovement.objects.filter(cash_session_id=opened.data['id']).count(), 1)
        audit = AuditLog.objects.get(action='cash_movement.manual_entry')
        self.assertEqual(audit.metadata['source'], 'pos')
        self.assertEqual(audit.metadata['device_name'], 'Stone Bar 01')
        self.assertEqual(audit.metadata['operation_reference'], key)
        audit_count = AuditLog.objects.count()
        self.client.post(
            reverse('pos:cash-session-entry', args=[opened.data['id']]), payload, format='json',
        )
        self.assertEqual(AuditLog.objects.count(), audit_count)

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_provider_start_is_idempotent_and_does_not_persist_launch_uri(self):
        _operator, device, _session, checkout, _method, _connection, _terminal = self.create_provider_checkout()
        cielo = PaymentProvider.objects.get(code='cielo')
        connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=cielo, name='Cielo local',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
            configuration={'merchant_code': '1234567890123456'},
        )
        PaymentTerminal.objects.create(
            connection=connection, branch=self.branch, pos_device=device, name='Cielo deste POS',
        )
        method = next(
            item for item in ensure_default_payment_methods(self.company)
            if item.code == 'credit_card'
        )
        payload = {
            'payment_method': method.pk, 'provider': 'cielo', 'mode': 'remaining',
            'idempotency_key': str(uuid4()),
        }

        started = self.client.post(
            reverse('pos:quick-sale-provider-payment-start', args=[checkout.pk]), payload,
            format='json',
        )
        replayed = self.client.post(
            reverse('pos:quick-sale-provider-payment-start', args=[checkout.pk]), payload,
            format='json',
        )

        self.assertEqual(started.status_code, 200, started.data)
        self.assertEqual(replayed.status_code, 200, replayed.data)
        self.assertEqual(started['Cache-Control'], 'no-store')
        self.assertIn('launch_uri', started.data)
        self.assertTrue(started.data['launch_available'])
        self.assertEqual(started.data['intent_id'], replayed.data['intent_id'])
        self.assertEqual(started.data['attempt_id'], replayed.data['attempt_id'])
        self.assertTrue(replayed.data['replayed'])
        self.assertFalse(replayed.data['launch_available'])
        self.assertNotIn('launch_uri', replayed.data)
        self.assertEqual(PaymentIntent.objects.filter(origin_id=str(checkout.pk)).count(), 1)
        self.assertEqual(PaymentAttempt.objects.filter(intent__origin_id=str(checkout.pk)).count(), 1)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 0)
        current = self.client.get(reverse('pos:quick-checkout-detail', args=[checkout.pk]))
        self.assertEqual(current.status_code, 200, current.data)
        self.assertEqual(current.data['payment_integration']['intent_status'], 'processing')
        self.assertEqual(current.data['payment_integration']['attempt_status'], 'processing')
        self.assertTrue(current.data['payment_integration']['requires_recovery'])
        self.assertFalse(current.data['payment_integration']['can_retry'])
        attempt = PaymentIntent.objects.get(pk=started.data['intent_id']).attempts.get()
        self.assertEqual(attempt.status, PaymentAttemptStatus.PROCESSING)
        self.assertNotIn('launch_uri', attempt.request_metadata)
        self.assertNotIn(started.data['launch_uri'], str(AuditLog.objects.values_list('after', 'metadata')))

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_cielo_callback_is_parsed_by_backend_and_applied_once(self):
        _operator, device, _session, checkout, _method, _connection, _terminal = self.create_provider_checkout()
        cielo = PaymentProvider.objects.get(code='cielo')
        connection = PaymentProviderConnection.objects.create(
            company=self.company, provider=cielo, name='Cielo local',
            environment=PaymentProviderConnectionEnvironment.SANDBOX,
            configuration={'merchant_code': '1234567890123456'},
        )
        PaymentTerminal.objects.create(
            connection=connection, branch=self.branch, pos_device=device, name='Cielo deste POS',
        )
        method = next(
            item for item in ensure_default_payment_methods(self.company)
            if item.code == 'credit_card'
        )
        started = self.client.post(
            reverse('pos:quick-sale-provider-payment-start', args=[checkout.pk]),
            {
                'payment_method': method.pk, 'provider': 'cielo', 'mode': 'remaining',
                'idempotency_key': str(uuid4()),
            },
            format='json',
        )
        self.assertEqual(started.status_code, 200, started.data)
        response = base64.b64encode(json.dumps({
            'reference': f"CORE-{started.data['attempt_id']}",
            'payments': [{
                'amount': '2000', 'installments': 0,
                'paymentFields': {'statusCode': '0', 'paymentTransactionId': 'transaction-1'},
            }],
        }).encode()).decode()
        callback_url = reverse(
            'pos:quick-sale-provider-payment-result',
            args=[checkout.pk, started.data['attempt_id']],
        )

        resolved = self.client.post(callback_url, {'response': response}, format='json')
        replayed = self.client.post(callback_url, {'response': response}, format='json')

        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(replayed.status_code, 200, replayed.data)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 1)
        intent = PaymentIntent.objects.get(pk=started.data['intent_id'])
        self.assertEqual(intent.status, 'applied')

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_provider_transaction_conflict_returns_409_not_500(self):
        checkout, started = self.start_configured_cielo_payment()
        adapter = SimpleNamespace(parse_payment_callback=lambda **_kwargs: ProviderPaymentResult(
            status=PaymentAttemptStatus.APPROVED,
            result_data={'provider_transaction_id': 'conflicting-transaction'},
            safe_metadata={'provider': 'cielo'},
        ))

        with patch('apps.payment_integrations.providers.registry.get_adapter', return_value=adapter), patch(
            'apps.pos.views.resolve_quick_sale_payment_attempt',
            side_effect=QuickCheckoutConflict(
                'provider_transaction_conflict',
                'Não foi possível confirmar unicamente esta transação na Cielo.',
            ),
        ):
            response = self.client.post(
                reverse('pos:quick-sale-provider-payment-result', args=[checkout.pk, started.data['attempt_id']]),
                {'response': ''}, format='json',
            )

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['code'], 'provider_transaction_conflict')

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_cielo_multiline_success_callback_is_applied_once(self):
        checkout, started = self.start_configured_cielo_payment()
        response = base64.encodebytes(json.dumps({
            'reference': f"CORE-{started.data['attempt_id']}",
            'id': 'cielo-order-1',
            'terminal': 'terminal-1',
            # U+03FF yields Base64 containing literal '+' and '/' after UTF-8 encoding.
            'extra': '\u03ff' + ' Resposta longa da Cielo para reproduzir o transporte em múltiplas linhas. ' * 8,
            'payments': [{
                'amount': '2000', 'installments': 1,
                'paymentFields': {
                    'statusCode': '1', 'paymentTransactionId': 'transaction-multiline-1',
                    'productName': 'Crédito à vista',
                },
            }],
        }, ensure_ascii=False).encode()).decode()
        self.assertIn('\n', response)
        self.assertIn('+', response)
        self.assertIn('/', response)
        self.assertIn('=', response)
        callback_url = reverse(
            'pos:quick-sale-provider-payment-result',
            args=[checkout.pk, started.data['attempt_id']],
        )

        resolved = self.client.post(callback_url, {'response': response}, format='json')
        replayed = self.client.post(callback_url, {'response': response}, format='json')

        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(replayed.status_code, 200, replayed.data)
        self.assertEqual(PaymentIntent.objects.get(pk=started.data['intent_id']).status, 'applied')
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 1)
        self.assertEqual(len(resolved.data['payments']), 1)

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_cielo_malformed_callback_stays_unknown_without_payment(self):
        checkout, started = self.start_configured_cielo_payment()
        resolved = self.client.post(
            reverse(
                'pos:quick-sale-provider-payment-result',
                args=[checkout.pk, started.data['attempt_id']],
            ),
            {'response': 'not-valid-base64!'},
            format='json',
        )

        self.assertEqual(resolved.status_code, 200, resolved.data)
        intent = PaymentIntent.objects.get(pk=started.data['intent_id'])
        self.assertEqual(intent.status, PaymentAttemptStatus.UNKNOWN)
        self.assertEqual(intent.attempts.get().status, PaymentAttemptStatus.UNKNOWN)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 0)
        self.assertEqual(resolved.data['payment_integration']['intent_status'], 'unknown')
        self.assertTrue(resolved.data['payment_integration']['requires_recovery'])

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_cielo_reversal_applies_only_after_confirmed_provider_callback(self):
        checkout, started = self.start_configured_cielo_payment()
        payment_response = base64.b64encode(json.dumps({
            'reference': f"CORE-{started.data['attempt_id']}",
            'id': 'cielo-order-reversal-1',
            'payments': [{
                'amount': '2000', 'installments': 1,
                'authCode': 'auth-reversal-1', 'cieloCode': 'nsu-reversal-1',
                'paymentFields': {
                    'statusCode': '0', 'paymentTransactionId': 'transaction-reversal-1',
                },
            }],
        }).encode()).decode()
        payment_result = self.client.post(
            reverse('pos:quick-sale-provider-payment-result', args=[checkout.pk, started.data['attempt_id']]),
            {'response': payment_response}, format='json',
        )
        self.assertEqual(payment_result.status_code, 200, payment_result.data)
        payment = QuickSalePayment.objects.get(checkout=checkout, source_type='provider')
        attempt = PaymentAttempt.objects.get(pk=started.data['attempt_id'])

        started_reversal = self.client.post(
            reverse('pos:quick-sale-provider-reversal-start', args=[checkout.pk, payment.pk]),
            {'idempotency_key': str(uuid4()), 'reason': 'Cliente desistiu'}, format='json',
        )
        self.assertEqual(started_reversal.status_code, 200, started_reversal.data)
        self.assertEqual(started_reversal.data['operation'], 'reversal')
        self.assertIn('lio://payment-reversal', started_reversal.data['launch_uri'])
        reversal_request = json.loads(base64.b64decode(parse_qs(
            urlparse(started_reversal.data['launch_uri']).query,
        )['request'][0]))
        self.assertEqual(reversal_request['id'], 'cielo-order-reversal-1')
        self.assertEqual(reversal_request['value'], 2000)
        self.assertNotIn('orderId', reversal_request)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 1)
        self.assertFalse(started_reversal.data['capabilities']['can_record_payment'])

        reversal_response = base64.b64encode(json.dumps({
            'id': 'cielo-order-reversal-1',
            'payments': [{
                'amount': 2000,
                'authCode': 'auth-reversal-1',
                'cieloCode': 'nsu-reversal-1',
                'paymentFields': {
                    'statusCode': '1', 'paymentTransactionId': 'transaction-reversal-1',
                },
            }, {
                'amount': 2000,
                'originalTransactionId': 'transaction-reversal-1',
                'originalCieloCode': 'nsu-reversal-1',
                'originalAuthCode': 'auth-reversal-1',
                'paymentFields': {'statusCode': '2'},
            }],
        }).encode()).decode()
        reversal_url = reverse(
            'pos:quick-sale-provider-reversal-result',
            args=[checkout.pk, started_reversal.data['operation_id']],
        )
        resolved = self.client.post(reversal_url, {'response': reversal_response}, format='json')
        replayed = self.client.post(reversal_url, {'response': reversal_response}, format='json')

        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(replayed.status_code, 200, replayed.data)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 2)
        self.assertTrue(QuickSalePayment.objects.filter(reversal_of=payment).exists())
        self.assertEqual(PaymentAttempt.objects.get(pk=attempt.pk).status, PaymentAttemptStatus.APPROVED)
        self.assertEqual(resolved.data['paid_amount'], '0.00')
        self.assertEqual(resolved.data['remaining_amount'], '20.00')
        self.assertTrue(resolved.data['capabilities']['can_record_payment'])

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_cielo_reversal_error_or_cancelled_keeps_original_payment(self):
        checkout, started = self.start_configured_cielo_payment()
        payment_response = base64.b64encode(json.dumps({
            'reference': f"CORE-{started.data['attempt_id']}",
            'id': f"cielo-order-{started.data['attempt_id']}",
            'payments': [{
                'amount': '2000', 'installments': 1,
                'authCode': 'auth-reversal', 'cieloCode': 'nsu-reversal',
                'paymentFields': {
                    'statusCode': '0', 'paymentTransactionId': f"transaction-{started.data['attempt_id']}",
                },
            }],
        }).encode()).decode()
        self.client.post(
            reverse('pos:quick-sale-provider-payment-result', args=[checkout.pk, started.data['attempt_id']]),
            {'response': payment_response}, format='json',
        )
        payment = QuickSalePayment.objects.get(checkout=checkout, source_type='provider')

        def start_reversal():
            started_reversal = self.client.post(
                reverse('pos:quick-sale-provider-reversal-start', args=[checkout.pk, payment.pk]),
                {'idempotency_key': str(uuid4())}, format='json',
            )
            self.assertEqual(started_reversal.status_code, 200, started_reversal.data)
            return started_reversal.data['operation_id']

        for code, expected_status in (('1', 'cancelled'), ('3', 'error')):
            with self.subTest(code=code):
                operation_id = start_reversal()
                response = base64.b64encode(json.dumps({
                    'code': code, 'reason': 'Resultado não aprovado',
                }).encode()).decode()
                resolved = self.client.post(
                    reverse('pos:quick-sale-provider-reversal-result', args=[checkout.pk, operation_id]),
                    {'response': response}, format='json',
                )

                self.assertEqual(resolved.status_code, 200, resolved.data)
                self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 1)
                self.assertFalse(QuickSalePayment.objects.filter(reversal_of=payment).exists())
                self.assertEqual(ProviderReversalOperation.objects.get(pk=operation_id).status, expected_status)

        operation_id = start_reversal()
        launch_failed = self.client.post(
            reverse('pos:quick-sale-provider-reversal-launch-failed', args=[checkout.pk, operation_id]),
            {}, format='json',
        )
        self.assertEqual(launch_failed.status_code, 200, launch_failed.data)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 1)
        self.assertEqual(ProviderReversalOperation.objects.get(pk=operation_id).status, 'error')
        self.assertTrue(launch_failed.data['capabilities']['can_record_payment'])

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_cielo_cancelled_callback_releases_the_quick_sale_checkout(self):
        checkout, started = self.start_configured_cielo_payment()
        response = base64.b64encode(json.dumps({
            'reference': f"CORE-{started.data['attempt_id']}",
            'payments': [{
                'amount': '2000', 'installments': 0,
                'paymentFields': {'statusCode': '2'},
            }],
        }).encode()).decode()

        resolved = self.client.post(
            reverse('pos:quick-sale-provider-payment-result', args=[checkout.pk, started.data['attempt_id']]),
            {'response': response}, format='json',
        )

        self.assertEqual(resolved.status_code, 200, resolved.data)
        intent = PaymentIntent.objects.get(pk=started.data['intent_id'])
        self.assertEqual(intent.status, PaymentAttemptStatus.CANCELLED)
        self.assertEqual(intent.attempts.get().status, PaymentAttemptStatus.CANCELLED)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 0)
        self.assertEqual(resolved.data['payment_integration']['intent_status'], 'cancelled')
        self.assertEqual(resolved.data['payment_integration']['attempt_status'], 'cancelled')
        self.assertFalse(resolved.data['payment_integration']['can_retry'])
        self.assertTrue(resolved.data['capabilities']['can_record_payment'])

    @override_settings(
        CIELO_SMART_CLIENT_ID='cielo-client-id-for-test',
        CIELO_SMART_ACCESS_TOKEN='cielo-access-token-for-test',
    )
    def test_cielo_error_callback_keeps_a_retryable_provider_payment(self):
        checkout, started = self.start_configured_cielo_payment()
        response = base64.b64encode(json.dumps({
            'code': '3', 'reason': 'Falha no terminal',
        }).encode()).decode()

        resolved = self.client.post(
            reverse('pos:quick-sale-provider-payment-result', args=[checkout.pk, started.data['attempt_id']]),
            {'response': response}, format='json',
        )

        self.assertEqual(resolved.status_code, 200, resolved.data)
        intent = PaymentIntent.objects.get(pk=started.data['intent_id'])
        self.assertEqual(intent.status, PaymentAttemptStatus.ERROR)
        self.assertEqual(intent.attempts.get().status, PaymentAttemptStatus.ERROR)
        self.assertEqual(QuickSalePayment.objects.filter(checkout=checkout).count(), 0)
        self.assertTrue(resolved.data['payment_integration']['can_retry'])
        self.assertTrue(resolved.data['payment_integration']['can_cancel'])
        self.assertEqual(resolved.data['payment_integration']['provider_message'], 'Falha no terminal')
