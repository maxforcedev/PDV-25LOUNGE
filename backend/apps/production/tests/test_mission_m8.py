from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.models import AuditLog
from apps.companies.models import UserBranchAccess, UserCompanyAccess
from apps.companies.services import create_company_with_matrix
from apps.products.models import Category, Product, ProductProductionDestination
from apps.production.models import (
    PrintJob,
    PrintJobStatus,
    PrinterDevice,
    PrinterOperationalStatus,
)


class MissionM8PrinterTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner.m8@example.com', password='Mission-M8-123!',
        )
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Empresa M8', legal_name='Empresa M8 Legal',
            enforce_saas_limits=False,
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)
        feature = patch('apps.production.permissions.require_branch_feature')
        feature.start()
        self.addCleanup(feature.stop)

    def create_printer(self, name='Cozinha', connection_type='network', configuration=None):
        configurations = {
            'network': {'host': '192.168.1.50', 'port': 9100, 'timeout': 5},
            'usb': {'vendor_id': '04b8', 'product_id': '0e15', 'identifier': '04b8:0e15'},
            'bluetooth': {'device_name': 'Printer Bar', 'identifier': 'AA:BB:CC:DD'},
        }
        response = self.client.post('/api/v1/printer-devices/', {
            'name': name,
            'connection_type': connection_type,
            'status': 'active',
            'technical_configuration': configuration or configurations[connection_type],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return PrinterDevice.objects.get(pk=response.data['id'])

    def test_create_uses_name_as_internal_destination_and_active_is_not_online(self):
        printer = self.create_printer()

        self.assertEqual(printer.operational_status, PrinterOperationalStatus.NOT_TESTED)
        destination = printer.destinations.get()
        self.assertEqual(destination.name, 'Cozinha')
        self.assertEqual(destination.branch, self.branch)

        response = self.client.get('/api/v1/printer-devices/')
        self.assertEqual(response.status_code, 200, response.data)
        item = response.data['results'][0]
        self.assertEqual(item['connection_summary'], '192.168.1.50:9100')
        self.assertEqual(item['operational_status'], 'not_tested')

    @patch('apps.production.adapters.socket.create_connection')
    def test_network_test_sets_online_only_after_real_adapter_success(self, connect):
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        printer = self.create_printer()

        response = self.client.post(f'/api/v1/printer-devices/{printer.pk}/test/')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], PrintJobStatus.PRINTED)
        printer.refresh_from_db()
        self.assertEqual(printer.operational_status, PrinterOperationalStatus.ONLINE)
        self.assertIsNotNone(printer.last_test_at)
        connection.sendall.assert_called_once()

    @patch(
        'apps.production.adapters.socket.create_connection',
        side_effect=TimeoutError('timed out'),
    )
    def test_network_failure_sets_offline_with_friendly_error(self, _connect):
        printer = self.create_printer()

        response = self.client.post(f'/api/v1/printer-devices/{printer.pk}/test/')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], PrintJobStatus.FAILED)
        self.assertEqual(
            response.data['error_summary'],
            'Não foi possível conectar à impressora 192.168.1.50:9100.',
        )
        printer.refresh_from_db()
        self.assertEqual(printer.operational_status, PrinterOperationalStatus.OFFLINE)

    def test_usb_and_bluetooth_are_saved_without_fake_bridge_connection(self):
        usb = self.create_printer('Tickets', 'usb')
        bluetooth = self.create_printer('Bar', 'bluetooth')

        for printer in (usb, bluetooth):
            self.assertEqual(printer.operational_status, PrinterOperationalStatus.NOT_TESTED)

        response = self.client.post(f'/api/v1/printer-devices/{usb.pk}/test/')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], PrintJobStatus.FAILED)
        self.assertEqual(response.data['error_summary'], 'Print Bridge necessária para utilizar esta impressora.')
        usb.refresh_from_db()
        self.assertEqual(
            usb.operational_status, PrinterOperationalStatus.BRIDGE_UNAVAILABLE,
        )

    def test_history_is_paginated_and_archiving_preserves_jobs(self):
        printer = self.create_printer('Tickets', 'usb')
        self.client.post(f'/api/v1/printer-devices/{printer.pk}/test/')

        history = self.client.get(
            f'/api/v1/printer-devices/{printer.pk}/history/?page_size=1',
        )
        self.assertEqual(history.status_code, 200, history.data)
        self.assertEqual(history.data['count'], 1)
        self.assertTrue(history.data['results'][0]['is_test'])
        self.assertEqual(history.data['results'][0]['origin_label'], 'Teste de impressão')

        response = self.client.delete(f'/api/v1/printer-devices/{printer.pk}/')
        self.assertEqual(response.status_code, 204, response.data)
        printer.refresh_from_db()
        self.assertEqual(printer.status, 'inactive')
        self.assertEqual(printer.destinations.get().status, 'inactive')
        self.assertEqual(printer.print_jobs.count(), 1)

    def test_product_selects_printers_without_exposing_destination_management(self):
        printer = self.create_printer()
        other = self.create_printer('Bar')
        category = Category.objects.create(company=self.company, name='Bebidas')
        product = Product.objects.create(
            company=self.company, category=category, name='Suco',
            internal_code='SUCO-M8', sale_price='10.00',
        )

        available = self.client.get(
            f'/api/v1/products/{product.pk}/production-printers/?available=true',
        )
        self.assertEqual(available.status_code, 200, available.data)
        self.assertEqual(
            {item['id'] for item in available.data}, {printer.pk, other.pk},
        )
        response = self.client.put(
            f'/api/v1/products/{product.pk}/production-printers/',
            {'printers': [printer.pk]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        link = ProductProductionDestination.objects.get(product=product)
        self.assertEqual(link.destination, printer.destinations.get())

        response = self.client.put(
            f'/api/v1/products/{product.pk}/production-printers/',
            {'printers': [other.pk]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ProductProductionDestination.objects.filter(product=product).count(), 1)
        self.assertEqual(
            ProductProductionDestination.objects.get(product=product).destination,
            other.destinations.get(),
        )

    def test_reprint_is_explicit_audited_and_permission_protected(self):
        printer = self.create_printer()
        destination = printer.destinations.get()
        original = PrintJob.objects.create(
            company=self.company, branch=self.branch, destination=destination,
            printer_device=printer, status=PrintJobStatus.PRINTED,
        )
        response = self.client.post(
            f'/api/v1/print-jobs/{original.pk}/reprint/',
            {'reason': 'Pedido do cliente'}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['reprint_of'], original.pk)
        self.assertEqual(response.data['reprint_number'], 1)
        log = AuditLog.objects.get(action='print_job.reprint_requested')
        self.assertEqual(log.actor, self.owner)
        self.assertEqual(log.metadata['reason'], 'Pedido do cliente')

        operator = User.objects.create_user(
            email='operator.m8@example.com', password='Mission-M8-Operator-123!',
        )
        profile = self.company.access_profiles.get(name='Operador de Estoque')
        company_access = UserCompanyAccess(
            user=operator, company=self.company, access_profile=profile,
        )
        company_access.save(enforce_saas_limit=False)
        UserBranchAccess.objects.create(
            user=operator, branch=self.branch, access_profile=profile,
        )
        unauthorized = APIClient()
        unauthorized.force_authenticate(operator)
        response = unauthorized.post(
            f'/api/v1/print-jobs/{original.pk}/reprint/',
            HTTP_X_BRANCH_ID=str(self.branch.pk),
        )
        self.assertEqual(response.status_code, 403, response.data)
