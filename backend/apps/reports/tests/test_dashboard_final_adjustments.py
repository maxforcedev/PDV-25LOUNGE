from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Branch, Company


class DashboardFinalAdjustmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            email='dashboard-final@example.com', password='password-123'
        )
        self.company = Company.objects.create(
            trade_name='Dashboard Final', legal_name='Dashboard Final Ltda'
        )
        self.branch = Branch.objects.create(
            company=self.company, name='Matriz', is_matrix=True
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

    def test_overview_report_preserves_moved_time_analyses(self):
        response = self.client.get(
            '/api/v1/reports/sales/',
            {
                'scope': 'overview',
                'start_datetime': '2026-09-01T00:00:00',
                'end_datetime': '2026-09-01T23:59:59',
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('heatmap', response.data['summary'])
        self.assertIn('weekly_comparison', response.data['summary'])
        self.assertIn('current', response.data['summary']['weekly_comparison'])
        self.assertIn('previous', response.data['summary']['weekly_comparison'])
