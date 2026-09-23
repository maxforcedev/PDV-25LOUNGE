from datetime import timedelta
import uuid

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Status
from apps.companies.services import create_company_with_matrix
from apps.pos.models import POSDevice
from apps.products.models import ProductionDestination
from apps.production.models import PrintDocument, PrintDocumentType, PrintJob, PrintJobStatus, PrinterDevice
from apps.production.serializers import PrintDocumentResultSerializer, PrintJobSerializer
from apps.production.services import (
    PHYSICAL_DISPATCH_TIMEOUT_SECONDS, claim_print_job, complete_print_job,
    expire_abandoned_print_dispatches, reconcile_print_jobs, reprint_print_job,
    retry_print_job, start_print_dispatch, test_printer_device,
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
        is_test = kwargs.get('is_test', False)
        document = None if is_test else PrintDocument.objects.create(
            company=self.company, branch=self.branch, document_type='ticket',
            source_type='fixture', source_id=str(uuid.uuid4()), snapshot={},
            snapshot_hash=uuid.uuid4().hex,
        )
        values = {
            'company': self.company, 'branch': self.branch, 'printer_device': self.printer,
            'print_document': document, 'payload_snapshot': {'event': 'new'}, **kwargs,
        }
        if is_test:
            values['destination'] = self.destination
        return PrintJob.objects.create(**values)

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

    def test_dispatch_started_batch_cannot_be_reclaimed_after_lease_expiry(self):
        batch_key = uuid.uuid4()
        first = self._job(batch_key=batch_key)
        second = self._job(batch_key=batch_key)
        claim_print_job(job_id=first.pk, device=self.first)
        start_print_dispatch(job_id=first.pk, device=self.first)
        PrintJob.objects.filter(batch_key=batch_key).update(
            lease_until=timezone.now() - timedelta(seconds=1),
        )

        with self.assertRaises(ValueError):
            claim_print_job(job_id=second.pk, device=self.second)

        # The original owner may still safely report the terminal batch result.
        complete_print_job(job_id=first.pk, device=self.first, outcome='printed')
        self.assertEqual(
            set(PrintJob.objects.filter(batch_key=batch_key).values_list('status', flat=True)),
            {PrintJobStatus.PRINTED},
        )

    def test_failed_is_retryable_but_uncertain_requires_explicit_reprint(self):
        failed = self._job()
        claim_print_job(job_id=failed.pk, device=self.first)
        start_print_dispatch(job_id=failed.pk, device=self.first)
        complete_print_job(job_id=failed.pk, device=self.first, outcome='failed', error='refused')
        retry_print_job(job=failed, user=self.owner)
        failed.refresh_from_db()
        self.assertEqual(failed.status, PrintJobStatus.PENDING)
        self.assertIsNone(failed.physical_dispatch_started_at)

        uncertain = self._job()
        claim_print_job(job_id=uncertain.pk, device=self.first)
        start_print_dispatch(job_id=uncertain.pk, device=self.first)
        complete_print_job(job_id=uncertain.pk, device=self.first, outcome='uncertain', error='connection dropped')
        with self.assertRaises(ValueError):
            retry_print_job(job=uncertain, user=self.owner)

    def test_completion_requires_dispatch_and_batch_reprint_keeps_the_ticket_whole(self):
        job = self._job()
        claim_print_job(job_id=job.pk, device=self.first)
        with self.assertRaises(ValueError):
            complete_print_job(job_id=job.pk, device=self.first, outcome='failed')

        batch_key = uuid.uuid4()
        first = self._job(batch_key=batch_key, status=PrintJobStatus.PRINTED)
        second = self._job(batch_key=batch_key, status=PrintJobStatus.PRINTED)
        reprint = reprint_print_job(job=first, user=self.owner, reason='Cozinha pediu')
        copies = list(PrintJob.objects.filter(batch_key=reprint.batch_key).order_by('id'))
        self.assertEqual(len(copies), 2)
        self.assertNotEqual(reprint.batch_key, batch_key)
        self.assertEqual({copy.reprint_number for copy in copies}, {1})
        self.assertEqual({copy.reprint_of_id for copy in copies}, {first.pk, second.pk})

    def test_reprint_requires_all_non_test_sources_to_be_printed_or_uncertain(self):
        batch_key = uuid.uuid4()
        first = self._job(batch_key=batch_key, status=PrintJobStatus.PRINTED)
        self._job(batch_key=batch_key, status=PrintJobStatus.FAILED)
        with self.assertRaises(ValueError):
            reprint_print_job(job=first, user=self.owner)

        test_job = self._job(is_test=True, status=PrintJobStatus.PRINTED)
        with self.assertRaises(ValueError):
            reprint_print_job(job=test_job, user=self.owner)

    def test_reconciliation_accepts_compatible_terminal_results(self):
        printed = self._job(status=PrintJobStatus.PRINTED)
        uncertain = self._job(status=PrintJobStatus.UNCERTAIN)
        failed = self._job(status=PrintJobStatus.FAILED)

        self.assertEqual(
            reconcile_print_jobs(device=self.first, entries=[
                {'job_id': printed.pk, 'state': 'sent'},
                {'job_id': uncertain.pk, 'state': 'sent'},
                {'job_id': failed.pk, 'state': 'failed_before_send'},
            ]),
            [printed.pk, uncertain.pk, failed.pk],
        )
        self.assertEqual(PrintJob.objects.get(pk=printed.pk).status, PrintJobStatus.PRINTED)
        self.assertEqual(PrintJob.objects.get(pk=uncertain.pk).status, PrintJobStatus.UNCERTAIN)
        self.assertEqual(PrintJob.objects.get(pk=failed.pk).status, PrintJobStatus.FAILED)

    def test_attempted_reconciliation_never_resends_and_resolves_dispatch_boundary(self):
        leased = self._job()
        claim_print_job(job_id=leased.pk, device=self.first)
        self.assertEqual(
            reconcile_print_jobs(device=self.first, entries=[
                {'job_id': leased.pk, 'state': 'attempted'},
            ]),
            [leased.pk],
        )
        leased.refresh_from_db()
        self.assertEqual(leased.status, PrintJobStatus.PROCESSING)

        dispatched = self._job()
        claim_print_job(job_id=dispatched.pk, device=self.first)
        start_print_dispatch(job_id=dispatched.pk, device=self.first)
        self.assertEqual(
            reconcile_print_jobs(device=self.first, entries=[
                {'job_id': dispatched.pk, 'state': 'attempted'},
            ]),
            [dispatched.pk],
        )
        dispatched.refresh_from_db()
        self.assertEqual(dispatched.status, PrintJobStatus.UNCERTAIN)

    def test_expired_physical_dispatch_marks_the_full_batch_uncertain(self):
        batch_key = uuid.uuid4()
        first = self._job(batch_key=batch_key)
        second = self._job(batch_key=batch_key)
        claim_print_job(job_id=first.pk, device=self.first)
        start_print_dispatch(job_id=first.pk, device=self.first)
        PrintJob.objects.filter(batch_key=batch_key).update(
            physical_dispatch_started_at=timezone.now() - timedelta(
                seconds=PHYSICAL_DISPATCH_TIMEOUT_SECONDS + 1,
            ),
        )

        expire_abandoned_print_dispatches(branch=self.branch)

        self.assertEqual(
            set(PrintJob.objects.filter(batch_key=batch_key).values_list('status', flat=True)),
            {PrintJobStatus.UNCERTAIN},
        )

    def test_failed_connection_does_not_claim_the_printer_was_seen(self):
        job = self._job()
        claim_print_job(job_id=job.pk, device=self.first)
        start_print_dispatch(job_id=job.pk, device=self.first)
        complete_print_job(
            job_id=job.pk, device=self.first, outcome='failed',
            error='connection refused', metadata={'printer_observed': False},
        )
        self.printer.refresh_from_db()
        self.assertIsNone(self.printer.last_seen_at)

    def test_printer_test_only_enqueues_a_network_job(self):
        job = test_printer_device(device=self.printer, user=self.owner)
        self.assertTrue(job.is_test)
        self.assertEqual(job.status, PrintJobStatus.PENDING)
        self.printer.refresh_from_db()
        self.assertIsNone(self.printer.last_test_at)

    def test_document_jobs_expose_raw_document_type_and_immutable_snapshot(self):
        for document_type in PrintDocumentType.values:
            with self.subTest(document_type=document_type):
                snapshot = {'document_type': document_type, 'source': 'fixture'}
                document = PrintDocument.objects.create(
                    company=self.company, branch=self.branch, document_type=document_type,
                    source_type='fixture', source_id=str(uuid.uuid4()), snapshot=snapshot,
                    snapshot_hash=uuid.uuid4().hex,
                )
                job = PrintJob.objects.create(
                    company=self.company, branch=self.branch, print_document=document,
                    printer_device=self.printer, payload_snapshot={'snapshot': snapshot},
                )

                data = PrintJobSerializer(job).data

                self.assertEqual(data['document_type'], document_type)
                self.assertEqual(data['document_snapshot'], snapshot)

    def test_document_result_reports_the_document_queue_and_reprint_state(self):
        job = self._job()

        data = PrintDocumentResultSerializer(job.print_document).data

        self.assertEqual(data['document']['id'], job.print_document_id)
        self.assertEqual(data['jobs'][0]['id'], job.pk)
        self.assertTrue(data['queued'])
        self.assertEqual(data['reprint_number'], 0)
        self.assertFalse(data['reprint_eligible'])
