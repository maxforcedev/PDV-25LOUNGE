from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.services import create_company_with_matrix, ensure_permission_catalog
from apps.production.models import PrinterDevice
from apps.products.models import ProductionDestination


PASSWORD = 'Mission-M2-Secure-123!'


class BranchCompanyContextTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner.m2@example.com', password=PASSWORD)
        self.company_a = create_company_with_matrix(
            creator=self.owner, trade_name='Empresa A M2', legal_name='Empresa A M2 Legal',
        )
        self.company_b = create_company_with_matrix(
            creator=self.owner, trade_name='Empresa B M2', legal_name='Empresa B M2 Legal',
        )
        self.branch_a = self.company_a.branches.get(is_matrix=True)
        self.branch_b = self.company_b.branches.get(is_matrix=True)
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def context(self, branch):
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(branch.pk)

    def test_list_returns_only_selected_company(self):
        self.context(self.branch_a)
        response = self.client.get(f'/api/v1/branches/?company={self.company_a.pk}')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item['id'] for item in response.data['results']], [self.branch_a.pk])

        self.context(self.branch_b)
        response = self.client.get(f'/api/v1/branches/?company={self.company_b.pk}')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item['id'] for item in response.data['results']], [self.branch_b.pk])

    def test_cross_company_branch_id_is_blocked_for_all_actions(self):
        self.context(self.branch_a)
        company_query = f'?company={self.company_a.pk}'
        requests = (
            self.client.get(f'/api/v1/branches/{self.branch_b.pk}/{company_query}'),
            self.client.patch(f'/api/v1/branches/{self.branch_b.pk}/{company_query}', {'name': 'Invasao'}, format='json'),
            self.client.post(f'/api/v1/branches/{self.branch_b.pk}/activate/{company_query}'),
            self.client.post(f'/api/v1/branches/{self.branch_b.pk}/deactivate/{company_query}'),
            self.client.get(f'/api/v1/branches/{self.branch_b.pk}/settings/{company_query}'),
            self.client.patch(f'/api/v1/branches/{self.branch_b.pk}/settings/{company_query}', {'service_fee_rate': '9.00'}, format='json'),
        )
        self.assertTrue(all(response.status_code in (403, 404) for response in requests))
        self.branch_b.refresh_from_db()
        self.assertEqual(self.branch_b.name, 'Matriz')
        self.assertEqual(self.branch_b.status, 'active')
        self.assertNotEqual(str(self.branch_b.settings.service_fee_rate), '9.00')

    def test_create_rejects_company_different_from_context(self):
        self.context(self.branch_a)
        response = self.client.post(f'/api/v1/branches/?company={self.company_a.pk}', {
            'company': self.company_b.pk,
            'name': 'Filial B indevida',
            'email': 'filial.b@example.com',
            'address': {
                'zip_code': '01001000', 'street': 'Rua B', 'number': '1',
                'complement': '', 'neighborhood': 'Centro', 'city': 'Sao Paulo', 'state': 'SP',
            },
        }, format='json')
        self.assertIn(response.status_code, (400, 403))
        self.assertFalse(self.company_b.branches.filter(name='Filial B indevida').exists())

    def test_contradictory_header_and_query_are_rejected_by_session_auth(self):
        client = APIClient()
        response = client.post('/api/v1/auth/login/', {
            'email': self.owner.email, 'password': PASSWORD,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        response = client.get(
            f'/api/v1/branches/?company={self.company_a.pk}',
            HTTP_X_BRANCH_ID=str(self.branch_b.pk),
        )
        self.assertEqual(response.status_code, 403)

    @patch('apps.production.permissions.require_branch_feature')
    def test_printer_configuration_remains_bound_to_active_branch(self, _feature):
        destination_a = ProductionDestination.objects.create(
            branch=self.branch_a, name='Cozinha A', code='cozinha-a',
        )
        destination_b = ProductionDestination.objects.create(
            branch=self.branch_b, name='Cozinha B', code='cozinha-b',
        )
        printer_a = PrinterDevice.objects.create(branch=self.branch_a, name='Printer A')
        printer_b = PrinterDevice.objects.create(branch=self.branch_b, name='Printer B')
        printer_a.destinations.add(destination_a)
        printer_b.destinations.add(destination_b)

        self.context(self.branch_a)
        response = self.client.get('/api/v1/printer-devices/')
        self.assertEqual(response.status_code, 200, response.data)
        results = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual([item['id'] for item in results], [printer_a.pk])
        self.assertEqual(self.client.get(f'/api/v1/printer-devices/{printer_b.pk}/').status_code, 404)
        response = self.client.patch(
            f'/api/v1/printer-devices/{printer_b.pk}/', {'name': 'Invadida'}, format='json',
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post('/api/v1/printer-devices/', {
            'branch': self.branch_b.pk,
            'name': 'Printer cruzada',
            'device_type': 'manual',
            'connection_type': 'network',
            'status': 'active',
            'destination_ids': [destination_b.pk],
            'technical_configuration': {},
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PrinterDevice.objects.filter(name='Printer cruzada').exists())
