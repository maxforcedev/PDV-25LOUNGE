import uuid
from decimal import Decimal
from hashlib import sha256
import json

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.base.audit import audit_log
from apps.base.exceptions import DomainValidationError
from apps.companies.models import Company, Status
from apps.products.models import ProductProductionDestination

from .adapters import adapter_for
from .models import (
    PrintJob, PrintJobStatus, PrinterConnectionType, PrinterOperationalStatus,
    ProductionEvent, ProductionJob, Ticket, TicketRedemption, TicketStatus,
)


def _payload(item, destination, event, reason='', command=None, table_attendance=None):
    command_data = {}
    if command:
        command_data = {
            'table': {'id': command.table_id, 'name': command.table.name if command.table_id else ''},
            'command': {
                'id': command.pk,
                'number': getattr(command, 'command_number', None) or command.number,
                'identifier': command.identifier,
            },
        }
    elif table_attendance:
        command_data = {
            'table': {
                'id': table_attendance.table_id,
                'name': table_attendance.table.name,
            },
            'table_attendance': {'id': table_attendance.pk},
        }
    return {
        'event': event,
        'destination': {'id': destination.pk, 'name': destination.name, 'code': destination.code},
        **command_data,
        'source_item': {
            'id': item.pk, 'product_name': item.product_name, 'internal_code': item.internal_code,
            'quantity': str(item.quantity), 'unit': item.unit, 'modifiers': item.modifier_snapshot,
            'notes': getattr(item, 'notes', ''),
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
        'notes': getattr(item, 'notes', ''),
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


def create_attendance_production_jobs(*, item, command, user, idempotency_key):
    """Use the canonical ProductionJob/PrintJob pipeline for POS-5 items."""
    destinations = ProductProductionDestination.objects.filter(
        product_id=item.product_id, destination__branch=command.branch,
        destination__status=Status.ACTIVE,
    ).select_related('destination')
    for link in destinations:
        destination = link.destination
        job, created = ProductionJob.objects.get_or_create(
            attendance_order_item=item, destination=destination, event=ProductionEvent.NEW,
            defaults={
                'company': command.company,
                'branch': command.branch,
                'payload_snapshot': _payload(item, destination, ProductionEvent.NEW, command=command),
            },
        )
        if not created:
            continue
        audit_log(actor=user, action='production_job.create', obj=job, company=command.company,
                  branch=command.branch, metadata={'idempotency_key': str(idempotency_key)})
        for device in destination.printer_devices.filter(branch=command.branch, status=Status.ACTIVE):
            print_job = PrintJob.objects.create(
                company=command.company, branch=command.branch, production_job=job,
                destination=destination, printer_device=device, payload_snapshot=job.payload_snapshot,
                idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{job.pk}:device:{device.pk}'),
            )
            audit_log(actor=user, action='print_job.enqueue', obj=print_job,
                      company=command.company, branch=command.branch)


def create_attendance_order_item_ticket(*, item, command, user):
    if not item.product.emits_ticket:
        return None
    return _create_ticket(
        item=item, company=command.company, branch=command.branch, user=user,
        source_field='source_attendance_order_item',
    )


def create_attendance_cancellation_jobs(*, item, command, user, idempotency_key, reason):
    originals = ProductionJob.objects.filter(
        attendance_order_item=item, event=ProductionEvent.NEW,
    ).select_related('destination')
    for original in originals:
        cancellation, created = ProductionJob.objects.get_or_create(
            attendance_order_item=item, destination=original.destination,
            event=ProductionEvent.CANCEL,
            defaults={
                'company': command.company, 'branch': command.branch, 'original_job': original,
                'payload_snapshot': _payload(item, original.destination, ProductionEvent.CANCEL, reason, command=command),
            },
        )
        if not created:
            continue
        audit_log(actor=user, action='production_job.cancel_notice', obj=cancellation,
                  company=command.company, branch=command.branch,
                  metadata={'idempotency_key': str(idempotency_key)})
        for device_id in original.print_jobs.values_list('printer_device_id', flat=True):
            job = PrintJob.objects.create(
                company=command.company, branch=command.branch, production_job=cancellation,
                destination=original.destination, printer_device_id=device_id,
                payload_snapshot=cancellation.payload_snapshot,
                idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{cancellation.pk}:device:{device_id}'),
            )
            audit_log(actor=user, action='print_job.enqueue_cancellation', obj=job,
                      company=command.company, branch=command.branch)


def cancel_attendance_ticket_for_item(*, item, user):
    return cancel_ticket_for_source(
        source_field='source_attendance_order_item', item=item, user=user,
    )


def create_table_production_jobs(*, item, attendance, user, idempotency_key):
    destinations = ProductProductionDestination.objects.filter(
        product_id=item.product_id, destination__branch=attendance.branch,
        destination__status=Status.ACTIVE,
    ).select_related('destination')
    for link in destinations:
        destination = link.destination
        job, created = ProductionJob.objects.get_or_create(
            table_order_item=item, destination=destination, event=ProductionEvent.NEW,
            defaults={
                'company': attendance.company, 'branch': attendance.branch,
                'payload_snapshot': _payload(
                    item, destination, ProductionEvent.NEW,
                    table_attendance=attendance,
                ),
            },
        )
        if not created:
            continue
        audit_log(actor=user, action='production_job.create', obj=job, company=attendance.company,
                  branch=attendance.branch, metadata={'idempotency_key': str(idempotency_key)})
        for device in destination.printer_devices.filter(branch=attendance.branch, status=Status.ACTIVE):
            PrintJob.objects.create(
                company=attendance.company, branch=attendance.branch, production_job=job,
                destination=destination, printer_device=device, payload_snapshot=job.payload_snapshot,
                idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{job.pk}:device:{device.pk}'),
            )


def create_table_order_item_ticket(*, item, attendance, user):
    if not item.product.emits_ticket:
        return None
    return _create_ticket(
        item=item, company=attendance.company, branch=attendance.branch, user=user,
        source_field='source_table_order_item',
    )


def cancel_ticket_for_source(*, source_field, item, user):
    ticket = Ticket.objects.select_for_update().filter(**{source_field: item}).first()
    if not ticket or ticket.status == TicketStatus.CANCELLED:
        return ticket
    ticket.status = TicketStatus.CANCELLED
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=('status', 'cancelled_at', 'updated_at'))
    audit_log(actor=user, action='ticket.cancel', obj=ticket, company=ticket.company, branch=ticket.branch)
    return ticket


def _ticket_error(code, message, *, conflict=False):
    error = DomainValidationError(code=code, message=message)
    if conflict:
        error.status_code = 409
    raise error


def _redeemed_quantity(ticket):
    return ticket.redemptions.aggregate(total=Sum('quantity'))['total'] or Decimal('0.000')


def ticket_validation_data(ticket):
    redeemed = _redeemed_quantity(ticket)
    cancelled = ticket.status == TicketStatus.CANCELLED
    remaining = Decimal('0.000') if cancelled else ticket.quantity - redeemed
    snapshot = ticket.identification_snapshot or {}
    return {
        'number': ticket.number,
        'status': ticket.status,
        'product_name': snapshot.get('product_name', ''),
        'unit': snapshot.get('unit', ''),
        'total_quantity': str(ticket.quantity),
        'redeemed_quantity': str(redeemed),
        'redeemable_quantity': str(remaining),
        'cancelled_unredeemed_quantity': str(ticket.quantity - redeemed) if cancelled else '0.000',
        'modifiers': snapshot.get('modifiers', []),
        'notes': snapshot.get('notes', ''),
        'issued_at': ticket.issued_at,
        'source_type': (
            'sale' if ticket.source_sale_item_id
            else 'attendance_order' if ticket.source_attendance_order_item_id
            else 'table_order' if ticket.source_table_order_item_id
            else 'order'
        ),
    }


def lookup_ticket_for_validation(*, branch, validation_code=None, ticket_number=None):
    filters = {'branch': branch}
    if validation_code:
        filters['validation_code'] = validation_code
    else:
        filters['number'] = ticket_number
    ticket = Ticket.objects.prefetch_related('redemptions').filter(**filters).first()
    if ticket is None:
        _ticket_error('ticket_not_found', 'Ticket não encontrado.')
    return ticket


@transaction.atomic
def redeem_ticket(*, branch, operator, device, validation_code=None, ticket_number=None,
                  quantity, idempotency_key, input_method):
    filters = {'branch': branch}
    if validation_code:
        filters['validation_code'] = validation_code
    else:
        filters['number'] = ticket_number
    ticket = Ticket.objects.select_for_update().prefetch_related('redemptions').filter(**filters).first()
    if ticket is None:
        _ticket_error('ticket_not_found', 'Ticket não encontrado.')
    fingerprint = sha256(json.dumps({
        'ticket': str(validation_code) if validation_code else ticket_number,
        'quantity': str(quantity), 'input_method': input_method,
    }, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    replay = TicketRedemption.objects.filter(ticket=ticket, idempotency_key=idempotency_key).first()
    if replay:
        if replay.request_fingerprint != fingerprint:
            _ticket_error('ticket_idempotency_conflict', 'A chave de idempotência já foi usada com outros dados.', conflict=True)
        return ticket, replay, True
    if ticket.status == TicketStatus.CANCELLED:
        _ticket_error('ticket_cancelled', 'Este ticket foi cancelado e não pode ser utilizado.', conflict=True)
    redeemed_before = _redeemed_quantity(ticket)
    remaining = ticket.quantity - redeemed_before
    if remaining <= 0 or ticket.status == TicketStatus.USED:
        _ticket_error('ticket_already_used', 'Este ticket já foi utilizado.', conflict=True)
    if quantity <= 0:
        _ticket_error('ticket_invalid_quantity', 'Informe uma quantidade positiva.')
    if quantity > remaining:
        _ticket_error('ticket_quantity_unavailable', 'A quantidade solicitada excede o saldo disponível.', conflict=True)
    redemption = TicketRedemption.objects.create(
        ticket=ticket, quantity=quantity, operator=operator, device=device,
        redeemed_at=timezone.now(), idempotency_key=idempotency_key,
        request_fingerprint=fingerprint, input_method=input_method,
    )
    redeemed_after = redeemed_before + quantity
    ticket.status = TicketStatus.USED if redeemed_after == ticket.quantity else TicketStatus.PARTIALLY_USED
    if ticket.status == TicketStatus.USED:
        ticket.used_at = redemption.redeemed_at
    ticket.save(update_fields=('status', 'used_at', 'updated_at'))
    audit_log(actor=operator, action='ticket.redeem', obj=ticket, company=ticket.company, branch=ticket.branch,
              metadata={'ticket_id': ticket.pk, 'ticket_number': ticket.number, 'quantity_redeemed_now': str(quantity),
                        'redeemed_before': str(redeemed_before), 'redeemed_after': str(redeemed_after),
                        'remaining_after': str(ticket.quantity - redeemed_after), 'device_id': str(device.pk),
                        'idempotency_key': str(idempotency_key), 'input_method': input_method})
    return ticket, redemption, False


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
