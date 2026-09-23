from unittest.mock import MagicMock, patch
import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.models import AuditLog
from apps.companies.models import UserBranchAccess, UserCompanyAccess
from apps.companies.services import create_company_with_matrix
from apps.products.models import Category, Product, ProductProductionDestination
from apps.production.models import (
    PrintJob,
    PrintDocument,
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

    def create_printer(self, name='Cozinha', connection_type='network', configuration=None, destination_ids=None):
        configurations = {
            'network': {'host': '192.168.1.50', 'port': 9100, 'timeout': 5},
            'usb': {'vendor_id': '04b8', 'product_id': '0e15', 'identifier': '04b8:0e15'},
            'bluetooth': {'device_name': 'Printer Bar', 'identifier': 'AA:BB:CC:DD'},
        }
        payload = {
            'name': name,
            'connection_type': connection_type,
            'status': 'active',
            'technical_configuration': configuration or configurations[connection_type],
        }
        if destination_ids is not None:
            payload['destination_ids'] = destination_ids
        response = self.client.post('/api/v1/printer-devices/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return PrinterDevice.objects.get(pk=response.data['id'])

    def create_destination(self, name='Cozinha', code='kitchen'):
        from apps.products.models import ProductionDestination

        return ProductionDestination.objects.create(
            branch=self.branch, name=name, code=code,
        )

    def test_create_leaves_destinations_explicit_and_active_is_not_online(self):
        printer = self.create_printer()

        self.assertEqual(printer.operational_status, PrinterOperationalStatus.NOT_TESTED)
        self.assertFalse(printer.destinations.exists())

        response = self.client.get('/api/v1/printer-devices/')
        self.assertEqual(response.status_code, 200, response.data)
        item = response.data['results'][0]
        self.assertEqual(item['destination_ids'], [])
        self.assertEqual(item['connection_summary'], '192.168.1.50:9100')
        self.assertEqual(item['operational_status'], 'not_tested')

    def test_destinations_are_writable_and_shared_destination_stays_active_until_last_printer(self):
        destination = self.create_destination()
        first = self.create_printer(destination_ids=[destination.pk])
        second = self.create_printer('Bar', destination_ids=[destination.pk])

        response = self.client.patch(
            f'/api/v1/printer-devices/{first.pk}/',
            {'destination_ids': [destination.pk]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['destination_ids'], [destination.pk])
        self.assertEqual(set(destination.printer_devices.values_list('pk', flat=True)), {first.pk, second.pk})

        self.client.delete(f'/api/v1/printer-devices/{first.pk}/')
        destination.refresh_from_db()
        self.assertEqual(destination.status, 'active')

        self.client.delete(f'/api/v1/printer-devices/{second.pk}/')
        destination.refresh_from_db()
        self.assertEqual(destination.status, 'inactive')

    @patch('apps.production.adapters.socket.create_connection')
    def test_network_test_enqueues_for_local_pos_without_server_socket(self, connect):
        printer = self.create_printer()
        printer.destinations.add(self.create_destination())

        response = self.client.post(f'/api/v1/printer-devices/{printer.pk}/test/')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], PrintJobStatus.PENDING)
        printer.refresh_from_db()
        self.assertEqual(printer.operational_status, PrinterOperationalStatus.NOT_TESTED)
        self.assertIsNone(printer.last_test_at)
        connect.assert_not_called()

    def test_network_test_stays_pending_until_local_pos_reports_result(self):
        printer = self.create_printer()
        printer.destinations.add(self.create_destination())

        response = self.client.post(f'/api/v1/printer-devices/{printer.pk}/test/')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], PrintJobStatus.PENDING)
        printer.refresh_from_db()
        self.assertEqual(printer.operational_status, PrinterOperationalStatus.NOT_TESTED)

    def test_usb_and_bluetooth_are_saved_but_not_executed_by_network_pos(self):
        usb = self.create_printer('Tickets', 'usb')
        bluetooth = self.create_printer('Bar', 'bluetooth')

        for printer in (usb, bluetooth):
            self.assertEqual(printer.operational_status, PrinterOperationalStatus.NOT_TESTED)

        response = self.client.post(f'/api/v1/printer-devices/{usb.pk}/test/')
        self.assertEqual(response.status_code, 400, response.data)
        usb.refresh_from_db()
        self.assertEqual(usb.operational_status, PrinterOperationalStatus.NOT_TESTED)

    def test_history_is_paginated_and_archiving_preserves_jobs(self):
        printer = self.create_printer('Tickets')
        destination = self.create_destination('Tickets', 'tickets')
        printer.destinations.add(destination)
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
        destination.refresh_from_db()
        self.assertEqual(destination.status, 'inactive')
        self.assertEqual(printer.print_jobs.count(), 1)

    def test_product_selects_printers_without_exposing_destination_management(self):
        printer_destination = self.create_destination()
        other_destination = self.create_destination('Bar', 'bar')
        printer = self.create_printer(destination_ids=[printer_destination.pk])
        other = self.create_printer('Bar', destination_ids=[other_destination.pk])
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
        self.assertEqual(link.destination, printer_destination)

        response = self.client.put(
            f'/api/v1/products/{product.pk}/production-printers/',
            {'printers': [other.pk]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ProductProductionDestination.objects.filter(product=product).count(), 1)
        self.assertEqual(
            ProductProductionDestination.objects.get(product=product).destination,
            other_destination,
        )

    def test_reprint_is_explicit_audited_and_permission_protected(self):
        printer = self.create_printer()
        document = PrintDocument.objects.create(
            company=self.company, branch=self.branch, document_type='ticket',
            source_type='fixture', source_id=str(uuid.uuid4()), snapshot={},
            snapshot_hash=uuid.uuid4().hex,
        )
        original = PrintJob.objects.create(
            company=self.company, branch=self.branch,
            printer_device=printer, print_document=document, status=PrintJobStatus.PRINTED,
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
