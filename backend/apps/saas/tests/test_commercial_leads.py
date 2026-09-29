from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.saas.models import CommercialLead


class PublicCommercialLeadTests(TestCase):
    payload = {
        'name': '  Marina  Silva ',
        'company_name': '  Casa  Central ',
        'whatsapp': '(11) 99999-1111',
        'email': 'MARINA@EXAMPLE.COM ',
        'segment': ' Restaurantes ',
        'message': ' Quero conhecer o CORE. ',
        'source_path': '/contato?plano=pro',
        'plan_interest': 'pro',
        'utm_source': 'google',
    }

    @override_settings(SALES_LEAD_EMAIL='sales@example.com')
    @patch('apps.saas.views.send_mail', side_effect=RuntimeError('smtp unavailable'))
    def test_saved_lead_is_not_lost_when_notification_fails(self, send_mail):
        response = APIClient().post(reverse('saas-public-leads'), self.payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        lead = CommercialLead.objects.get(pk=response.data['id'])
        self.assertEqual(lead.status, CommercialLead.Status.NEW)
        self.assertEqual(lead.name, 'Marina Silva')
        self.assertEqual(lead.email, 'marina@example.com')
        self.assertEqual(lead.whatsapp, '11999991111')
        send_mail.assert_called_once()

    def test_honeypot_and_invalid_whatsapp_are_rejected(self):
        client = APIClient()
        spam = client.post(reverse('saas-public-leads'), {**self.payload, 'honeypot': 'bot'}, format='json')
        invalid_phone = client.post(reverse('saas-public-leads'), {**self.payload, 'whatsapp': '123'}, format='json')

        self.assertEqual(spam.status_code, 400)
        self.assertEqual(invalid_phone.status_code, 400)
        self.assertEqual(CommercialLead.objects.count(), 0)
