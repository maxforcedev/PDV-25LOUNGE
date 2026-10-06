from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.saas.models import GlobalSaaSSettings
from apps.saas.serializers import GlobalSaaSSettingsSerializer
from apps.saas.views import PublicSettingsView
from rest_framework.test import APIRequestFactory
from unittest.mock import patch


class LegalSettingsValidationTests(SimpleTestCase):
    def test_accepts_public_fields_and_preserves_existing_support(self):
        serializer = GlobalSaaSSettingsSerializer(data={
            'support_email': 'suporte@example.com',
            'legal_settings': {
                'legal_name': 'Empresa Exemplo', 'cnpj': '69.366.055/0001-16',
                'privacy_email': 'privacidade@example.com', 'effective_date': '2026-10-05',
                'website_url': 'https://example.com',
            },
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['support_email'], 'suporte@example.com')

    def test_partial_update_preserves_other_contacts_and_can_clear_a_field(self):
        instance = GlobalSaaSSettings(legal_settings={
            'legal_name': 'Empresa Exemplo', 'privacy_email': 'privacidade@example.com', 'cnpj': '69.366.055/0001-16',
        })
        serializer = GlobalSaaSSettingsSerializer(instance, data={
            'legal_settings': {'legal_name': 'Novo Nome', 'privacy_email': ''},
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch.object(instance, 'save'):
            serializer.save()
        self.assertEqual(instance.legal_settings['legal_name'], 'Novo Nome')
        self.assertEqual(instance.legal_settings['privacy_email'], '')
        self.assertEqual(instance.legal_settings['cnpj'], '69.366.055/0001-16')

    def test_rejects_unknown_private_fields_and_invalid_contact_values(self):
        for data in ({'password': 'private'}, {'privacy_email': 'invalid'},
                     {'website_url': 'javascript:alert(1)'}, {'effective_date': '2026-02-30'},
                     {'cnpj': '11111111111111'}):
            with self.subTest(data=data):
                serializer = GlobalSaaSSettingsSerializer(data={'legal_settings': data}, partial=True)
                self.assertFalse(serializer.is_valid())


class PublicLegalSettingsTests(TestCase):
    def test_public_endpoint_only_exposes_declared_institutional_fields(self):
        settings = GlobalSaaSSettings.objects.create(
            support_email='suporte@example.com',
            legal_settings={'legal_name': 'Empresa Exemplo', 'address': 'Rua Exemplo, 10',
                            'privacy_email': 'privacidade@example.com', 'password': 'secret'},
        )
        response = APIClient().get(reverse('saas-public-settings'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['legal_settings']['address'], 'Rua Exemplo, 10')
        self.assertNotIn('password', response.data['legal_settings'])
        self.assertNotIn('enforcement_enabled', response.data)
        self.assertEqual(response.data['support_email'], settings.support_email)


class PublicLegalSettingsContractTests(SimpleTestCase):
    def test_public_response_is_allowlisted_without_database_access(self):
        instance = GlobalSaaSSettings(support_email='suporte@example.com', legal_settings={
            'legal_name': 'Empresa Exemplo', 'privacy_email': 'privacidade@example.com', 'password': 'secret',
        })
        with patch('apps.saas.views.GlobalSaaSSettings.objects.first', return_value=instance):
            response = PublicSettingsView.as_view()(APIRequestFactory().get('/api/v1/public/settings/'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('password', response.data['legal_settings'])
        self.assertNotIn('enforcement_enabled', response.data)
        self.assertEqual(response.data['legal_settings']['privacy_email'], 'privacidade@example.com')
