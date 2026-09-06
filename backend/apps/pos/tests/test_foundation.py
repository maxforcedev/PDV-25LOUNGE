from types import SimpleNamespace
from unittest.mock import patch
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
from apps.cash.models import CashMovement, CashRegister
from apps.cash.services import open_session
from apps.companies.models import (
    Branch, FunctionalPermission, UserBranchAccess, UserCompanyAccess,
    UserPermissionBlock,
)
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

    def test_bootstrap_reports_fixed_and_flexible_cash_state_without_fake_selection(self):
        operator, _ = self.login_pos_operator()
        fixed_register = CashRegister.objects.create(branch=self.branch, name='Bar')
        fixed_session = open_session(
            fixed_register, '25.00', operator, self.branch, allow_pos_only=True,
        )
        BranchPOSSettings.objects.create(
            branch=self.branch,
            cash_binding_mode='FIXED',
            default_cash_register=fixed_register,
        )

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
        self.assertEqual(summary.status_code, 403, summary.data)
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
