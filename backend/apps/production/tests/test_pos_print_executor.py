from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Status
from apps.companies.services import create_company_with_matrix
from apps.pos.models import POSDevice
from apps.products.models import ProductionDestination
from apps.production.models import PrintJob, PrintJobStatus, PrinterDevice
from apps.production.services import (
    claim_print_job, complete_print_job, retry_print_job, test_printer_device,
)


class POSPrintExecutorTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='print-owner@example.com', password='Print-123!')
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Print Co', legal_name='Print Co Ltd',
            enforce_saas_limits=False,
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.destination = ProductionDestination.objects.create(
            branch=self.branch, name='Cozinha', code='kitchen', status=Status.ACTIVE,
        )
        self.printer = PrinterDevice.objects.create(
            branch=self.branch, name='Impressora Cozinha', status=Status.ACTIVE,
            connection_type='network', technical_configuration={
                'host': '192.168.0.150', 'port': 9100, 'timeout': 5, 'paper_width': 80,
            },
        )
        self.printer.destinations.add(self.destination)
        self.first = self._device('POS 1')
        self.second = self._device('POS 2')

    def _device(self, name):
        return POSDevice.objects.create(
            branch=self.branch, name=name, status=POSDevice.Status.ACTIVE,
            capabilities={'network_printing': True},
        )

    def _job(self, **kwargs):
        return PrintJob.objects.create(
            company=self.company, branch=self.branch, destination=self.destination,
            printer_device=self.printer, payload_snapshot={'event': 'new'}, **kwargs,
        )

    def test_atomic_claim_and_expired_lease_can_be_reclaimed(self):
        job = self._job()
        claim_print_job(job_id=job.pk, device=self.first)
        with self.assertRaises(ValueError):
            claim_print_job(job_id=job.pk, device=self.second)
        PrintJob.objects.filter(pk=job.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
        claim_print_job(job_id=job.pk, device=self.second)
        job.refresh_from_db()
        self.assertEqual(job.claimed_by, self.second)
        self.assertEqual(job.status, PrintJobStatus.PROCESSING)

    def test_failed_is_retryable_but_uncertain_requires_explicit_reprint(self):
        failed = self._job()
        claim_print_job(job_id=failed.pk, device=self.first)
        complete_print_job(job_id=failed.pk, device=self.first, outcome='failed', error='refused')
        retry_print_job(job=failed, user=self.owner)
        failed.refresh_from_db()
        self.assertEqual(failed.status, PrintJobStatus.PENDING)

        uncertain = self._job()
        claim_print_job(job_id=uncertain.pk, device=self.first)
        complete_print_job(job_id=uncertain.pk, device=self.first, outcome='uncertain', error='connection dropped')
        with self.assertRaises(ValueError):
            retry_print_job(job=uncertain, user=self.owner)

    def test_printer_test_only_enqueues_a_network_job(self):
        job = test_printer_device(device=self.printer, user=self.owner)
        self.assertTrue(job.is_test)
        self.assertEqual(job.status, PrintJobStatus.PENDING)
        self.printer.refresh_from_db()
        self.assertIsNone(self.printer.last_test_at)
