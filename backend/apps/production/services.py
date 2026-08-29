import uuid

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.base.audit import audit_log
from apps.companies.models import Company, Status
from apps.products.models import ProductProductionDestination

from .adapters import adapter_for
from .models import (
    PrintJob, PrintJobStatus, PrinterConnectionType, PrinterOperationalStatus,
    ProductionEvent, ProductionJob, Ticket, TicketStatus,
)


def _payload(item, destination, event, reason='', command=None):
    command_data = {}
    if command:
        command_data = {
            'table': {'id': command.table_id, 'name': command.table.name if command.table_id else ''},
            'command': {'id': command.pk, 'number': command.command_number, 'identifier': command.identifier},
        }
    return {
        'event': event,
        'destination': {'id': destination.pk, 'name': destination.name, 'code': destination.code},
        **command_data,
        'source_item': {
            'id': item.pk, 'product_name': item.product_name, 'internal_code': item.internal_code,
            'quantity': str(item.quantity), 'unit': item.unit, 'modifiers': item.modifier_snapshot,
        },
        'cancellation_reason': reason,
    }


def create_production_jobs(*, item, command, user, idempotency_key):
    destinations = ProductProductionDestination.objects.filter(
        product_id=item.product_id, destination__branch=command.branch, destination__status=Status.ACTIVE,
    ).select_related('destination')
    for link in destinations:
        destination = link.destination
        production_job, created = ProductionJob.objects.get_or_create(
            order_item=item, destination=destination, event=ProductionEvent.NEW,
            defaults={
                'company': command.company, 'branch': command.branch,
                'payload_snapshot': _payload(item, destination, ProductionEvent.NEW, command=command),
            },
        )
        if not created:
            continue
        audit_log(actor=user, action='production_job.create', obj=production_job, company=command.company, branch=command.branch, metadata={'idempotency_key': str(idempotency_key)})
        for device in destination.printer_devices.filter(branch=command.branch, status=Status.ACTIVE):
            job = PrintJob.objects.create(
                company=command.company, branch=command.branch, production_job=production_job,
                destination=destination, printer_device=device, payload_snapshot=production_job.payload_snapshot,
                idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{production_job.pk}:device:{device.pk}'),
            )
            audit_log(actor=user, action='print_job.enqueue', obj=job, company=command.company, branch=command.branch)


def create_cancellation_jobs(*, item, command, user, idempotency_key, reason):
    originals = ProductionJob.objects.filter(order_item=item, event=ProductionEvent.NEW).select_related('destination')
    for original in originals:
        cancellation, created = ProductionJob.objects.get_or_create(
            order_item=item, destination=original.destination, event=ProductionEvent.CANCEL,
            defaults={
                'company': command.company, 'branch': command.branch, 'original_job': original,
                'payload_snapshot': _payload(item, original.destination, ProductionEvent.CANCEL, reason, command=command),
            },
        )
        if not created:
            continue
        audit_log(actor=user, action='production_job.cancel_notice', obj=cancellation, company=command.company, branch=command.branch, metadata={'idempotency_key': str(idempotency_key)})
        device_ids = original.print_jobs.values_list('printer_device_id', flat=True)
        for device_id in device_ids:
            job = PrintJob.objects.create(company=command.company, branch=command.branch, production_job=cancellation, destination=original.destination, printer_device_id=device_id, payload_snapshot=cancellation.payload_snapshot, idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{cancellation.pk}:device:{device_id}'))
            audit_log(actor=user, action='print_job.enqueue_cancellation', obj=job, company=command.company, branch=command.branch)


def create_sale_production_jobs(*, sale, user, idempotency_key):
    for item in sale.items.select_related('product').all():
        destinations = ProductProductionDestination.objects.filter(
            product_id=item.product_id, destination__branch=sale.branch, destination__status=Status.ACTIVE,
        ).select_related('destination')
        for link in destinations:
            destination = link.destination
            production_job, created = ProductionJob.objects.get_or_create(
                sale_item=item, destination=destination, event=ProductionEvent.NEW,
                defaults={
                    'company': sale.company, 'branch': sale.branch,
                    'payload_snapshot': _payload(item, destination, ProductionEvent.NEW),
                },
            )
            if not created:
                continue
            audit_log(actor=user, action='production_job.create', obj=production_job, company=sale.company, branch=sale.branch, metadata={'idempotency_key': str(idempotency_key)})
            for device in destination.printer_devices.filter(branch=sale.branch, status=Status.ACTIVE):
                job = PrintJob.objects.create(company=sale.company, branch=sale.branch, production_job=production_job,
                    destination=destination, printer_device=device, payload_snapshot=production_job.payload_snapshot,
                    idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{production_job.pk}:device:{device.pk}'))
                audit_log(actor=user, action='print_job.enqueue', obj=job, company=sale.company, branch=sale.branch)


def create_sale_cancellation_jobs(*, sale, user, idempotency_key, reason):
    for item in sale.items.all():
        originals = ProductionJob.objects.filter(sale_item=item, event=ProductionEvent.NEW).select_related('destination')
        for original in originals:
            cancellation, created = ProductionJob.objects.get_or_create(
                sale_item=item, destination=original.destination, event=ProductionEvent.CANCEL,
                defaults={'company': sale.company, 'branch': sale.branch, 'original_job': original,
                          'payload_snapshot': _payload(item, original.destination, ProductionEvent.CANCEL, reason)},
            )
            if not created:
                continue
            audit_log(actor=user, action='production_job.cancel_notice', obj=cancellation, company=sale.company, branch=sale.branch, metadata={'idempotency_key': str(idempotency_key)})
            for device_id in original.print_jobs.values_list('printer_device_id', flat=True):
                job = PrintJob.objects.create(company=sale.company, branch=sale.branch, production_job=cancellation,
                    destination=original.destination, printer_device_id=device_id, payload_snapshot=cancellation.payload_snapshot,
                    idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{cancellation.pk}:device:{device_id}'))
                audit_log(actor=user, action='print_job.enqueue_cancellation', obj=job, company=sale.company, branch=sale.branch)


def _ticket_snapshot(item):
    return {
        'product_id': item.product_id, 'product_name': item.product_name,
        'internal_code': item.internal_code, 'unit': item.unit,
        'quantity': str(item.quantity), 'modifiers': item.modifier_snapshot,
    }


def _create_ticket(*, item, company, branch, user, source_field):
    Company.objects.select_for_update().get(pk=company.pk)
    existing = Ticket.objects.filter(**{source_field: item}).first()
    if existing:
        return existing
    number = Ticket.objects.filter(company=company, branch=branch).aggregate(maximum=Max('number'))['maximum'] or 0
    ticket = Ticket.objects.create(company=company, branch=branch, number=number + 1, quantity=item.quantity,
        issued_at=timezone.now(), identification_snapshot=_ticket_snapshot(item), **{source_field: item})
    audit_log(actor=user, action='ticket.issue', obj=ticket, company=company, branch=branch)
    return ticket


def create_sale_tickets(*, sale, user):
    return [_create_ticket(item=item, company=sale.company, branch=sale.branch, user=user, source_field='source_sale_item')
            for item in sale.items.select_related('product').filter(product__emits_ticket=True)]


def create_order_item_ticket(*, item, command, user):
    if not item.product.emits_ticket:
        return None
    return _create_ticket(item=item, company=command.company, branch=command.branch, user=user, source_field='source_order_item')


def cancel_ticket_for_source(*, source_field, item, user):
    ticket = Ticket.objects.select_for_update().filter(**{source_field: item}).first()
    if not ticket or ticket.status == TicketStatus.CANCELLED:
        return ticket
    ticket.status = TicketStatus.CANCELLED
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=('status', 'cancelled_at', 'updated_at'))
    audit_log(actor=user, action='ticket.cancel', obj=ticket, company=ticket.company, branch=ticket.branch)
    return ticket


@transaction.atomic
def retry_print_job(*, job, user):
    job = PrintJob.objects.select_for_update().get(pk=job.pk)
    if job.status == PrintJobStatus.PRINTED:
        raise ValueError('Use reprint for a job already printed.')
    job.status = PrintJobStatus.PENDING
    job.last_error = ''
    job.save(update_fields=('status', 'last_error', 'updated_at'))
    audit_log(actor=user, action='print_job.retry_requested', obj=job, company=job.company, branch=job.branch)
    return job


@transaction.atomic
def reprint_print_job(*, job, user, reason=''):
    source = PrintJob.objects.only('pk', 'reprint_of_id').get(pk=job.pk)
    root = PrintJob.objects.select_for_update().get(pk=source.reprint_of_id or source.pk)
    descendants = list(PrintJob.objects.select_for_update().filter(reprint_of=root))
    number = max((copy.reprint_number for copy in descendants), default=0) + 1
    source = root if source.pk == root.pk else next(copy for copy in descendants if copy.pk == source.pk)
    copy = PrintJob.objects.create(company=source.company, branch=source.branch, production_job=source.production_job, destination=source.destination, printer_device=source.printer_device, payload_snapshot={**source.payload_snapshot, 'reprint': True, 'reprint_number': number}, reprint_of=root, reprint_number=number)
    audit_log(
        actor=user, action='print_job.reprint_requested', obj=copy,
        company=copy.company, branch=copy.branch,
        metadata={
            'source_print_job_id': str(source.pk),
            'reprint_number': number,
            'reason': (reason or '').strip(),
        },
    )
    return copy


@transaction.atomic
def manual_dispatch_print_job(*, job, user):
    job = PrintJob.objects.select_for_update().get(pk=job.pk)
    if job.status not in (PrintJobStatus.PENDING, PrintJobStatus.FAILED):
        raise ValueError('Only pending or failed jobs can be manually dispatched.')
    outcome = adapter_for(job).dispatch(job)
    job.attempts += 1
    job.processing_at = timezone.now()
    if outcome.status == 'manual_confirmed':
        job.status = PrintJobStatus.PRINTED
        job.printed_at = timezone.now()
        job.last_error = ''
    else:
        job.status = PrintJobStatus.FAILED
        job.last_error = outcome.detail
    job.save(update_fields=('attempts', 'processing_at', 'status', 'printed_at', 'last_error', 'updated_at'))
    audit_log(actor=user, action='print_job.manual_dispatch', obj=job, company=job.company, branch=job.branch, metadata={'adapter_outcome': outcome.status, 'detail': outcome.detail})
    return job


@transaction.atomic
def test_printer_device(*, device, user):
    device = device.__class__.objects.select_for_update().prefetch_related('destinations').get(pk=device.pk)
    if device.status != Status.ACTIVE:
        raise ValueError('Ative a impressora antes de executar o teste.')
    destination = device.destinations.filter(status=Status.ACTIVE).first()
    if not destination:
        raise ValueError('Associe ao menos um destino ativo antes de executar o teste.')
    job = PrintJob.objects.create(
        company=device.branch.company, branch=device.branch, destination=destination,
        printer_device=device, is_test=True,
        payload_snapshot={'test': True, 'title': 'CORE PDV', 'message': 'TESTE DE IMPRESSÃO', 'branch': device.branch.name, 'printer': device.name},
    )
    job = manual_dispatch_print_job(job=job, user=user)
    device.last_test_at = timezone.now()
    if job.status == PrintJobStatus.PRINTED:
        device.last_seen_at = device.last_test_at
        device.operational_status = PrinterOperationalStatus.ONLINE
        device.last_operational_error = ''
    else:
        device.operational_status = (
            PrinterOperationalStatus.BRIDGE_UNAVAILABLE
            if device.connection_type in (
                PrinterConnectionType.USB, PrinterConnectionType.BLUETOOTH,
            ) else PrinterOperationalStatus.OFFLINE
        )
        device.last_operational_error = job.last_error[:300]
    device.save(update_fields=(
        'last_test_at', 'last_seen_at', 'operational_status',
        'last_operational_error', 'updated_at',
    ))
    audit_log(actor=user, action='printer_device.test', obj=device, company=device.branch.company, branch=device.branch, metadata={'print_job_id': job.pk, 'status': job.status})
    return job
