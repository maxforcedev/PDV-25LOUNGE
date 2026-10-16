from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import (
    AccessProfile, FunctionalPermission, UserBranchAccess, UserCompanyAccess,
)
from apps.production.models import PrinterDevice
from apps.saas.tests.helpers import create_complete_test_plan, create_operational_test_tenant


class PrinterAdministrationPermissionTests(TestCase):
    def setUp(self):
        self.owner, self.company, _ = create_operational_test_tenant(
            code='printer-admin-permissions', email='printer.owner@example.com',
            trade_name='Printer permissions', legal_name='Printer permissions Ltda',
            plan_version=create_complete_test_plan(
                'printer-admin-permissions', enabled_features=('production', 'products'),
            ),
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.printer = PrinterDevice.objects.create(
            branch=self.branch, name='Cozinha',
            technical_configuration={'host': '192.168.1.50', 'port': 9100, 'timeout': 5},
        )

    def client_with(self, *codes):
        user = User.objects.create_user(
            email=f"{'-'.join(codes)}@example.com", password='Printer-Permissions-123!',
        )
        profile = AccessProfile.objects.create(
            company=self.company, name=f"Profile {' '.join(codes)}",
        )
        profile.permissions.set(FunctionalPermission.objects.filter(code__in=codes))
        UserCompanyAccess.objects.create(
            user=user, company=self.company, access_profile=profile,
        )
        UserBranchAccess.objects.create(
            user=user, branch=self.branch, access_profile=profile,
        )
        client = APIClient()
        client.force_authenticate(user)
        client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)
        return client

    def test_route_manager_gets_safe_catalog_but_cannot_manage_printers(self):
        client = self.client_with('print_routes.manage')

        catalog = client.get('/api/v1/printer-devices/route-options/')
        self.assertEqual(catalog.status_code, 200, catalog.data)
        item = catalog.data['results'][0]
        self.assertEqual(item, {
            'id': self.printer.pk, 'name': 'Cozinha', 'status': 'active',
            'connection_type': 'network',
        })
        self.assertEqual(client.get('/api/v1/printer-devices/').status_code, 403)
        self.assertEqual(client.post('/api/v1/printer-devices/', {}, format='json').status_code, 403)
        self.assertEqual(client.patch(
            f'/api/v1/printer-devices/{self.printer.pk}/', {'name': 'Invadida'}, format='json',
        ).status_code, 403)
        self.assertEqual(client.delete(f'/api/v1/printer-devices/{self.printer.pk}/').status_code, 403)
        self.assertEqual(client.post(f'/api/v1/printer-devices/{self.printer.pk}/test/').status_code, 403)

        response = client.post('/api/v1/print-routes/bulk-update/', {
            'routes': [{'document_type': 'ticket', 'mode': 'disabled'}],
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_printer_manager_keeps_full_administration_access(self):
        client = self.client_with('printers.manage')

        self.assertEqual(client.get('/api/v1/printer-devices/').status_code, 200)
        self.assertEqual(client.get('/api/v1/printer-devices/route-options/').status_code, 200)
        self.assertEqual(client.patch(
            f'/api/v1/printer-devices/{self.printer.pk}/', {'name': 'Cozinha 2'}, format='json',
        ).status_code, 200)

    def test_history_viewer_cannot_receive_printer_management_access(self):
        client = self.client_with('print_jobs.view')

        self.assertEqual(client.get('/api/v1/print-jobs/').status_code, 200)
        self.assertEqual(client.get('/api/v1/printer-devices/').status_code, 403)
        self.assertEqual(client.get('/api/v1/printer-devices/route-options/').status_code, 403)
        self.assertEqual(client.post(f'/api/v1/printer-devices/{self.printer.pk}/test/').status_code, 403)
