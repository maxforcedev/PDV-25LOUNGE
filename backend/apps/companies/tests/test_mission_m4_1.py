from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.services import create_company_with_matrix, ensure_permission_catalog


PASSWORD = 'Mission-M4-1-Secure-123!'


class MissionM41BusinessTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(
            email='owner.m41@example.com', password=PASSWORD
        )
        self.company_a = create_company_with_matrix(
            creator=self.owner,
            trade_name='Empresa A M41',
            legal_name='Empresa A M41 Legal',
        )
        self.company_b = create_company_with_matrix(
            creator=self.owner,
            trade_name='Empresa B M41',
            legal_name='Empresa B M41 Legal',
        )
        self.branch_a = self.company_a.branches.get(is_matrix=True)
        self.branch_b = self.company_b.branches.get(is_matrix=True)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch_a.pk)

    def _branch_payload(self, company, name):
        return {
            'company': company.pk,
            'name': name,
            'address': {
                'zip_code': '01001000', 'street': 'Rua Teste', 'number': '1',
                'complement': '', 'neighborhood': 'Centro', 'city': 'Sao Paulo',
                'state': 'SP',
            },
        }

    def test_duplicate_branch_name_is_friendly_and_company_scoped(self):
        duplicate = self.client.post(
            f'/api/v1/branches/?company={self.company_a.pk}',
            self._branch_payload(self.company_a, 'Matriz'), format='json',
        )
        self.assertEqual(duplicate.status_code, 400, duplicate.data)
        self.assertEqual(
            duplicate.data['name'][0],
            'Já existe uma filial com esse nome nesta empresa.',
        )
        own_name = self.client.patch(
            f'/api/v1/branches/{self.branch_a.pk}/?company={self.company_a.pk}',
            {'name': 'Matriz'}, format='json',
        )
        self.assertEqual(own_name.status_code, 200, own_name.data)

        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch_b.pk)
        other_company = self.client.post(
            f'/api/v1/branches/?company={self.company_b.pk}',
            self._branch_payload(self.company_b, 'Filial Centro'), format='json',
        )
        self.assertEqual(other_company.status_code, 201, other_company.data)

    def test_business_overview_uses_real_company_counts(self):
        response = self.client.get(
            f'/api/v1/branches/overview/?company={self.company_a.pk}'
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['company']['id'], self.company_a.pk)
        self.assertEqual(response.data['counts']['branches'], 1)
        self.assertEqual(response.data['counts']['active_users'], 1)
        self.assertEqual(response.data['counts']['products'], 0)
        self.assertEqual(response.data['counts']['printer_devices'], 0)
