from django.core import mail
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.accounts.models import User


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    FRONTEND_URL='https://app.example.test',
)
class SelfServicePasswordResetTests(TestCase):
    request_url = '/api/v1/auth/password-reset/'
    confirm_url = '/api/v1/auth/password-reset/confirm/'

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='reset@example.test', password='Current-password-123!',
        )

    def test_request_is_neutral_and_sends_a_reset_link_only_for_an_account(self):
        known = self.client.post(self.request_url, {'email': self.user.email}, format='json')
        unknown = self.client.post(self.request_url, {'email': 'missing@example.test'}, format='json')

        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/redefinir-senha?uid=', mail.outbox[0].body)

    def test_confirmation_accepts_valid_link_and_rejects_malformed_uid(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        from django.contrib.auth.tokens import default_token_generator

        valid = self.client.post(self.confirm_url, {
            'uid': uid,
            'token': default_token_generator.make_token(self.user),
            'new_password': 'Replacement-password-456!',
        }, format='json')
        self.assertEqual(valid.status_code, 200, valid.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Replacement-password-456!'))

        invalid = self.client.post(self.confirm_url, {
            'uid': '////', 'token': 'invalid', 'new_password': 'Another-password-789!',
        }, format='json')
        self.assertEqual(invalid.status_code, 400)
        self.assertIn('token', invalid.data)
