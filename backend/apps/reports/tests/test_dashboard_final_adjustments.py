from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attendance.models import TableAttendance
from apps.companies.services import create_company_with_matrix
from apps.commands.models import Command, Table
from apps.saas.models import Plan, PlanEntitlement, PlanVersion, Subscription
from apps.saas.services import ensure_capability_catalog, map_existing_company


class DashboardFinalAdjustmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            email='dashboard-final@example.com', password='password-123'
        )
        self.company = create_company_with_matrix(
            creator=self.user,
            trade_name='Dashboard Final', legal_name='Dashboard Final Ltda',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.branch.settings.uses_commands = True
        self.branch.settings.uses_tables = True
        self.branch.settings.save(update_fields=('uses_commands', 'uses_tables', 'updated_at'))
        capabilities = ensure_capability_catalog()
        plan = Plan.objects.create(code='dashboard-test', name='Dashboard Test')
        version = PlanVersion.objects.create(
            plan=plan, version=1, price='0.00',
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['core.enabled'], unlimited=True,
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['users.max'], limit_value=1,
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['branches.max'], limit_value=1,
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['pos.enabled'], unlimited=True,
        )
        PlanEntitlement.objects.create(
            plan_version=version, capability=capabilities['pos.devices.max'], limit_value=1,
        )
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities['feature.reports'],
            unlimited=True,
        )
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities['feature.commands'],
            unlimited=True,
        )
        PlanEntitlement.objects.create(
            plan_version=version,
            capability=capabilities['feature.tables'],
            unlimited=True,
        )
        map_existing_company(
            company=self.company,
            plan_version=version,
            billing_mode=Subscription.BillingMode.INTERNAL,
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

    def test_dashboard_empty_command_and_table_counts_do_not_error(self):
        response = self.client.get('/api/v1/dashboard/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['commands'], {
            'open_count': 0,
            'open_table_count': 0,
        })

    def test_dashboard_counts_open_commands_and_table_attendances_separately(self):
        Command.objects.create(
            company=self.company,
            branch=self.branch,
            command_number='CMD-001',
            opened_by=self.user,
        )
        table = Table.objects.create(branch=self.branch, name='Mesa 1')
        TableAttendance.objects.create(
            company=self.company,
            branch=self.branch,
            table=table,
            opened_by=self.user,
            seller_user=self.user,
        )

        response = self.client.get('/api/v1/dashboard/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['commands'], {
            'open_count': 1,
            'open_table_count': 1,
        })
