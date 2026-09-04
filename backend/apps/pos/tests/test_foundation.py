from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from django.test import TestCase

from apps.accounts.models import User
from apps.base.exceptions import DomainValidationError
from apps.cash.models import CashRegister
from apps.companies.models import UserBranchAccess, UserCompanyAccess
from apps.companies.services import create_branch_with_access, create_company_with_matrix
from apps.pos.models import (
    AuthenticationChallenge, BranchPOSSettings, POSDevice, POSDeviceSettings,
    POSOperatorPinAttempt,
)
from apps.pos.services import (
    _mask_email, create_pin_reset_token, pairing_channels, set_pos_pin,
    version_gate,
)


class POSFoundationContractTests(SimpleTestCase):
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

    def test_pairing_uses_opaque_contact_and_otp_can_only_be_consumed_once(self):
        confirmation, challenge_id = self.pair_device()

        self.assertEqual(confirmation.data['device']['status'], POSDevice.Status.ACTIVE)
        device = POSDevice.objects.get(pk=confirmation.data['device']['id'])
        self.assertNotEqual(device.credential_hash, confirmation.data['device_credential'])

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
