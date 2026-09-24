import uuid
from decimal import Decimal
from hashlib import sha256
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.base.audit import audit_log
from apps.base.exceptions import DomainValidationError
from apps.companies.models import Company, Status
from apps.products.models import ProductProductionDestination

# Adapters remain available for explicitly legacy/manual dispatch. Network production
# jobs are always executed by a POS on the branch LAN.
from .adapters import adapter_for
from .models import (
    PrintDocument, PrintDocumentRequest, PrintDocumentType, PrintJob, PrintJobStatus, PrintRoute,
    PrintRouteMode, PrintRouteOverride, PrinterConnectionType, PrinterOperationalStatus,
    ProductionEvent, ProductionJob, Ticket, TicketRedemption, TicketStatus,
)


def _payload(item, destination, event, reason='', command=None, table_attendance=None, sale=None, user=None):
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
        'created_at': timezone.now().isoformat(),
        'destination': {'id': destination.pk, 'name': destination.name, 'code': destination.code},
        'branch_name': destination.branch.name,
        'operator': (
            user.get_full_name().strip() or user.email
            if user else ''
        ),
        **command_data,
        'source_item': {
            'id': item.pk, 'product_name': item.product_name, 'internal_code': item.internal_code,
            'quantity': str(item.quantity), 'unit': item.unit, 'modifiers': item.modifier_snapshot,
            'notes': getattr(item, 'notes', ''),
        },
        'cancellation_reason': reason,
        'sale': {'id': sale.pk, 'identifier': f'VENDA {sale.pk}'} if sale else {},
    }


def _batch_key(idempotency_key, destination_id, device_id, event):
    return uuid.uuid5(uuid.NAMESPACE_URL, f'print-batch:{idempotency_key}:{destination_id}:{device_id}:{event}')


INITIAL_DOCUMENT_TYPES = (
    PrintDocumentType.TABLE_BILL,
    PrintDocumentType.TABLE_CONFERENCE,
    PrintDocumentType.TABLE_FINAL_RECEIPT,
    PrintDocumentType.QUICK_SALE_RECEIPT,
    PrintDocumentType.PAYMENT_RECEIPT,
    PrintDocumentType.TICKET,
)


def normalize_print_document_type(document_type):
    if isinstance(document_type, PrintDocumentType):
        return document_type.value
    if isinstance(document_type, str):
        member = PrintDocumentType.__members__.get(document_type.upper())
        if member is not None:
            return member.value
        try:
            return PrintDocumentType(document_type).value
        except ValueError:
            pass
    raise ValueError('Tipo de documento não suportado.')


def ensure_print_routes(branch):
    """New branches inherit disabled document policies until an operator configures them."""
    for document_type in INITIAL_DOCUMENT_TYPES:
        PrintRoute.objects.get_or_create(
            branch=branch, document_type=document_type,
            defaults={'mode': PrintRouteMode.DISABLED, 'copies': 1},
        )


def effective_print_route(*, branch, document_type, pos_device=None):
    document_type = normalize_print_document_type(document_type)
    ensure_print_routes(branch)
    route = PrintRoute.objects.prefetch_related('printer_devices').get(
        branch=branch, document_type=document_type,
    )
    if pos_device is None:
        return route
    if pos_device.branch_id != branch.pk:
        raise ValueError('O dispositivo POS deve pertencer à filial do documento.')
    override = PrintRouteOverride.objects.filter(
        pos_device=pos_device, document_type=document_type,
    ).prefetch_related('printer_devices').first()
    return route if override is None or override.inherit_branch else override


def _number(value):
    return str(value) if value is not None else None


def _document_request_fingerprint(*, action, branch, document_type=None,
                                  source_type=None, source_id=None,
                                  pos_device=None, document_id=None, reason='', snapshot_hash=None):
    intent = {
        'action': action, 'branch_id': str(branch.pk), 'document_type': str(document_type) if document_type is not None else None,
        'source_type': source_type, 'source_id': str(source_id) if source_id is not None else None,
        'pos_device_id': str(pos_device.pk) if pos_device is not None else None,
        'document_id': str(document_id) if document_id is not None else None,
        'reason': str(reason), 'snapshot_hash': str(snapshot_hash) if snapshot_hash is not None else None,
    }
    return sha256(json.dumps(intent, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _table_snapshot(attendance):
    from apps.attendance.models import AttendanceOrderItemStatus, AttendancePaymentStatus, TablePayment
    from apps.attendance.services import table_financial_state, table_summary

    items = attendance.orders.prefetch_related('items').all()
    rows = []
    for order in items:
        for item in order.items.all():
            rows.append({
                'id': item.pk, 'product_name': item.product_name, 'internal_code': item.internal_code,
                'quantity': _number(item.quantity), 'unit': item.unit,
                'unit_price': _number(item.unit_price), 'status': item.status,
                'modifiers': item.modifier_snapshot, 'notes': item.notes,
                'financial': item.financial_snapshot,
                'cancelled_at': item.cancelled_at.isoformat() if item.cancelled_at else None,
                'cancellation_reason': item.cancellation_reason,
            })
    payments = TablePayment.objects.filter(
        attendance=attendance, status=AttendancePaymentStatus.APPLIED, reversal__isnull=True,
    ).select_related('payment_method', 'operator').order_by('id')
    return {
        'table': {'id': attendance.table_id, 'name': attendance.table.name},
        'attendance_id': attendance.pk, 'status': attendance.status,
        'opened_at': attendance.created_at.isoformat(), 'closed_at': attendance.closed_at.isoformat() if attendance.closed_at else None,
        'attendant': _operator_name(attendance.seller_user or attendance.opened_by),
        'operator': _operator_name(attendance.closed_by) if attendance.closed_by else '',
        'customer': attendance.customer.name if attendance.customer_id else '',
        'responsible_name': attendance.responsible_name, 'notes': attendance.notes,
        'items': rows,
        'summary': table_summary(attendance),
        'payments': [{
            'id': payment.pk, 'method': payment.payment_method.name, 'method_code': payment.payment_method.code,
            'amount': _number(payment.amount), 'received_amount': _number(payment.received_amount),
            'change_amount': _number(payment.change_amount), 'status': payment.status,
            'operator': _operator_name(payment.operator), 'created_at': payment.created_at.isoformat(),
        } for payment in payments],
    }


def _operator_name(user):
    return (user.get_full_name().strip() or user.email) if user else ''


def _sale_snapshot(sale):
    return {
        'sale_id': sale.pk, 'sale_number': sale.sale_number, 'channel': sale.channel,
        'created_at': sale.created_at.isoformat(), 'customer': sale.customer_name_snapshot,
        'seller': _operator_name(sale.seller_user), 'operator': _operator_name(sale.created_by),
        'items': [{
            'id': item.pk, 'product_name': item.product_name, 'internal_code': item.internal_code,
            'quantity': _number(item.quantity), 'unit': item.unit, 'unit_price': _number(item.unit_price),
            'subtotal': _number(item.subtotal), 'modifiers': item.modifier_snapshot, 'notes': item.notes,
            'promotion_discount': _number(item.promotion_benefit), 'item_discount': _number(item.manual_discount),
            'net_subtotal': _number(item.net_subtotal),
        } for item in sale.items.all()],
        'summary': {
            'subtotal': _number(sale.subtotal), 'promotion_discount_total': _number(sale.promotion_discount_total),
            'item_discount_total': _number(sale.item_discount_total), 'discount': _number(sale.discount),
            'service_fee': _number(sale.service_fee_amount), 'total': _number(sale.total),
        },
        'payments': [{
            'method': payment.payment_method.name, 'method_code': payment.payment_method.code,
            'amount': _number(payment.amount), 'received_amount': _number(payment.received_amount),
            'change_amount': _number(payment.change_amount),
        } for payment in sale.payments.select_related('payment_method').all()],
    }


def _source_snapshot(*, document_type, source_type, source_id, branch):
    if source_type == 'table_attendance':
        from apps.attendance.models import TableAttendance

        attendance = TableAttendance.objects.select_related(
            'table', 'customer', 'opened_by', 'seller_user', 'closed_by',
        ).prefetch_related('orders__items').filter(pk=source_id, branch=branch).first()
        if not attendance:
            raise ValueError('Atendimento de mesa não encontrado na filial.')
        if document_type == PrintDocumentType.TABLE_FINAL_RECEIPT:
            from apps.attendance.models import TableAttendanceStatus
            from apps.products.models import SalesChannel
            from apps.sales.models import SaleStatus

            if (
                attendance.status != TableAttendanceStatus.CLOSED
                or not attendance.sale_id
                or attendance.sale.channel != SalesChannel.TABLE
                or attendance.sale.status != SaleStatus.FINALIZED
            ):
                raise ValueError('Recibo final exige uma mesa fechada com venda finalizada.')
        return attendance, _table_snapshot(attendance)
    if source_type == 'sale':
        from apps.sales.models import Sale

        sale = Sale.objects.select_related('customer', 'seller_user', 'created_by').prefetch_related(
            'items', 'payments__payment_method',
        ).filter(pk=source_id, branch=branch).first()
        if not sale:
            raise ValueError('Venda não encontrada na filial.')
        if document_type == PrintDocumentType.QUICK_SALE_RECEIPT:
            from apps.sales.models import SaleStatus

            if sale.channel != 'counter' or sale.status != SaleStatus.FINALIZED:
                raise ValueError('Recibo de venda rápida exige uma venda de balcão finalizada.')
        return sale, _sale_snapshot(sale)
    if source_type == 'table_payment':
        from apps.attendance.models import TablePayment

        payment = TablePayment.objects.select_related(
            'attendance__table', 'payment_method', 'operator',
        ).filter(pk=source_id, attendance__branch=branch).first()
        if not payment:
            raise ValueError('Pagamento de mesa não encontrado na filial.')
        if document_type == PrintDocumentType.PAYMENT_RECEIPT and (
            payment.status != 'applied' or hasattr(payment, 'reversal')
        ):
            raise ValueError('Comprovante exige um pagamento de mesa ativo.')
        return payment, {
            'payment_id': payment.pk, 'table': {'id': payment.attendance.table_id, 'name': payment.attendance.table.name},
            'method': payment.payment_method.name, 'method_code': payment.payment_method.code,
            'amount': _number(payment.amount), 'received_amount': _number(payment.received_amount),
            'change_amount': _number(payment.change_amount), 'status': payment.status,
            'operator': _operator_name(payment.operator), 'created_at': payment.created_at.isoformat(),
        }
    if source_type == 'quick_sale_payment':
        from apps.pos.models import QuickSalePayment, QuickSalePaymentStatus

        payment = QuickSalePayment.objects.select_related(
            'checkout__sale', 'operator', 'payment_method',
        ).filter(pk=source_id, checkout__branch=branch).first()
        if not payment:
            raise ValueError('Pagamento de venda rápida não encontrado na filial.')
        if document_type == PrintDocumentType.PAYMENT_RECEIPT and (
            payment.status != QuickSalePaymentStatus.APPLIED or hasattr(payment, 'reversal')
        ):
            raise ValueError('Comprovante exige um pagamento de venda rápida ativo.')
        return payment, {
            'payment_id': str(payment.pk), 'checkout_id': str(payment.checkout_id),
            'sale_id': payment.checkout.sale_id,
            'method': payment.payment_method_name, 'method_code': payment.payment_method_code,
            'amount': _number(payment.amount), 'received_amount': _number(payment.received_amount),
            'change_amount': _number(payment.change_amount), 'status': payment.status,
            'operator': _operator_name(payment.operator), 'created_at': payment.created_at.isoformat(),
        }
    if source_type == 'ticket':
        ticket = Ticket.objects.filter(pk=source_id, branch=branch).first()
        if not ticket:
            raise ValueError('Ticket não encontrado na filial.')
        return ticket, {
            'ticket_id': ticket.pk, 'number': ticket.number, 'quantity': _number(ticket.quantity),
            'status': ticket.status, 'validation_code': str(ticket.validation_code),
            'issued_at': ticket.issued_at.isoformat(), 'item': ticket.identification_snapshot,
        }
    raise ValueError('Origem de documento não suportada.')


def _document_snapshot(*, branch, document_type, source_type, source_id):
    source, snapshot = _source_snapshot(
        document_type=document_type, source_type=source_type, source_id=source_id, branch=branch,
    )
    snapshot = dict(snapshot)
    snapshot.setdefault('company_name', branch.company.trade_name or branch.company.legal_name)
    snapshot.setdefault('branch_name', branch.name)
    snapshot.setdefault('branch_address', ', '.join(
        str(value).strip() for value in (branch.address or {}).values() if str(value).strip()
    ))
    snapshot.setdefault('branch_phone', branch.phone)
    return source, snapshot


def _document_snapshot_hash(snapshot):
    return sha256(json.dumps(
        snapshot, sort_keys=True, separators=(',', ':'), default=str,
    ).encode()).hexdigest()


def _legacy_document_snapshot_hashes(snapshot):
    before_contact_fields = dict(snapshot)
    before_contact_fields.pop('branch_address', None)
    before_contact_fields.pop('branch_phone', None)
    before_header_fields = dict(before_contact_fields)
    before_header_fields.pop('company_name', None)
    before_header_fields.pop('branch_name', None)
    return {
        _document_snapshot_hash(before_contact_fields),
        _document_snapshot_hash(before_header_fields),
    }


def _existing_print_document(*, branch, document_type, source_type, source_id, snapshot_hash, snapshot):
    filters = {
        'branch': branch, 'document_type': document_type, 'source_type': source_type,
        'source_id': str(source_id),
    }
    document = PrintDocument.objects.filter(**filters, snapshot_hash=snapshot_hash).first()
    if document:
        return document
    # Documents emitted before the header fields were added remain immutable.
    return PrintDocument.objects.filter(
        **filters, snapshot_hash__in=_legacy_document_snapshot_hashes(snapshot),
    ).first()


def create_print_document(*, branch, document_type, source_type, source_id, user=None, metadata=None):
    document_type = normalize_print_document_type(document_type)
    valid_sources = {
        PrintDocumentType.TABLE_BILL: {'table_attendance'},
        PrintDocumentType.TABLE_CONFERENCE: {'table_attendance'},
        PrintDocumentType.TABLE_FINAL_RECEIPT: {'table_attendance'},
        PrintDocumentType.QUICK_SALE_RECEIPT: {'sale'},
        PrintDocumentType.PAYMENT_RECEIPT: {'table_payment', 'quick_sale_payment'},
        PrintDocumentType.TICKET: {'ticket'},
    }
    if source_type not in valid_sources.get(document_type, set()):
        raise ValueError('A origem não é válida para este tipo de documento.')
    _source, snapshot = _document_snapshot(
        document_type=document_type, source_type=source_type, source_id=source_id, branch=branch,
    )
    snapshot_hash = _document_snapshot_hash(snapshot)
    existing = _existing_print_document(
        branch=branch, document_type=document_type, source_type=source_type,
        source_id=source_id, snapshot_hash=snapshot_hash, snapshot=snapshot,
    )
    if existing:
        return existing, False
    version = (PrintDocument.objects.filter(
        branch=branch, document_type=document_type, source_type=source_type, source_id=str(source_id),
    ).aggregate(latest=Max('version'))['latest'] or 0) + 1
    try:
        # Savepoint keeps the surrounding business transaction usable on a
        # concurrent insert of this immutable source snapshot.
        with transaction.atomic():
            document = PrintDocument.objects.create(
                company=branch.company, branch=branch, document_type=document_type,
                source_type=source_type, source_id=str(source_id), snapshot=snapshot,
                snapshot_hash=snapshot_hash, version=version, created_by=user, metadata=metadata or {},
            )
    except IntegrityError:
        document = PrintDocument.objects.filter(
            branch=branch, document_type=document_type, source_type=source_type,
            source_id=str(source_id), snapshot_hash=snapshot_hash,
        ).first()
        if document:
            return document, False
        raise
    audit_log(actor=user, action='print_document.create', obj=document, company=branch.company, branch=branch,
              metadata={'document_type': document_type, 'source_type': source_type, 'source_id': str(source_id),
                        'snapshot_hash': snapshot_hash, 'version': version})
    return document, True


def current_print_document(*, branch, document_type, source_type, source_id):
    """Find the existing immutable document for the source's current snapshot.

    This selector is intentionally read-only: opening a screen must not emit a
    document, add audit history, or advance its version.
    """
    document_type = normalize_print_document_type(document_type)
    try:
        _source, snapshot = _document_snapshot(
            document_type=document_type, source_type=source_type,
            source_id=source_id, branch=branch,
        )
    except ValueError:
        return None
    snapshot_hash = _document_snapshot_hash(snapshot)
    return _existing_print_document(
        branch=branch, document_type=document_type, source_type=source_type,
        source_id=source_id, snapshot_hash=snapshot_hash, snapshot=snapshot,
    )


def enqueue_print_document(*, document, user=None, pos_device=None, retry_failed=False):
    """Enqueue the first physical copies once; retries and reprints stay PrintJob operations."""
    initial_jobs = list(document.print_jobs.filter(reprint_of__isnull=True).order_by('id'))
    if initial_jobs:
        if retry_failed:
            for job in initial_jobs:
                if job.status == PrintJobStatus.FAILED and not job.physical_dispatch_started_at:
                    retry_print_job(job=job, user=user)
        return list(document.print_jobs.filter(reprint_of__isnull=True).order_by('id'))
    policy = effective_print_route(
        branch=document.branch, document_type=document.document_type, pos_device=pos_device,
    )
    if policy.mode == PrintRouteMode.DISABLED:
        labels = {
            PrintDocumentType.TABLE_BILL: 'Conta da mesa',
            PrintDocumentType.TABLE_CONFERENCE: 'Conferência',
            PrintDocumentType.TABLE_FINAL_RECEIPT: 'Recibo final da mesa',
            PrintDocumentType.QUICK_SALE_RECEIPT: 'Recibo de venda rápida',
            PrintDocumentType.PAYMENT_RECEIPT: 'Comprovante de pagamento',
            PrintDocumentType.TICKET: 'Ticket',
        }
        source = 'por uma configuração específica deste POS' if isinstance(policy, PrintRouteOverride) else 'para esta filial'
        raise ValueError(
            f'A impressão de "{labels.get(document.document_type, document.document_type)}" está desabilitada '
            f'{source}. Configure em Produção > Rotas de impressão.'
        )
    devices = list(policy.printer_devices.filter(
        branch=document.branch, status=Status.ACTIVE,
        connection_type=PrinterConnectionType.NETWORK,
    ).order_by('id'))
    if not devices:
        raise ValueError('A rota exige ao menos uma impressora NETWORK ativa.')
    jobs = []
    for device in devices:
        for copy_number in range(1, policy.copies + 1):
            job_key = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f'document:{document.pk}:device:{device.pk}:copy:{copy_number}',
            )
            job, created = PrintJob.objects.get_or_create(
                print_document=document, printer_device=device, idempotency_key=job_key,
                defaults={
                    'company': document.company, 'branch': document.branch,
                    'payload_snapshot': {
                    'document': {
                        'id': document.pk, 'document_type': document.document_type,
                        'source_type': document.source_type, 'source_id': document.source_id,
                        'snapshot_hash': document.snapshot_hash, 'version': document.version,
                        'copy_number': copy_number, 'format': policy.document_format,
                    },
                    'snapshot': document.snapshot,
                },
                },
            )
            jobs.append(job)
            if created:
                audit_log(actor=user, action='print_job.enqueue_document', obj=job,
                          company=document.company, branch=document.branch,
                          metadata={'document_id': document.pk, 'printer_device_id': device.pk,
                                    'copy_number': copy_number, 'document_type': document.document_type})
    return jobs


@transaction.atomic
def issue_print_document(*, branch, document_type, source_type, source_id, user=None, pos_device=None,
                         automatic_only=False, metadata=None, idempotency_key=None):
    document_type = normalize_print_document_type(document_type)
    _source, current_snapshot = _document_snapshot(
        document_type=document_type, source_type=source_type,
        source_id=source_id, branch=branch,
    )
    current_snapshot_hash = _document_snapshot_hash(current_snapshot)
    fingerprint = None
    if idempotency_key:
        fingerprint = _document_request_fingerprint(
            action='issue', branch=branch, document_type=document_type,
            source_type=source_type, source_id=source_id, pos_device=pos_device,
            snapshot_hash=current_snapshot_hash,
        )
        prior = PrintDocumentRequest.objects.select_related('document').filter(
            branch=branch, action='issue', idempotency_key=idempotency_key,
        ).first()
        if prior:
            if prior.request_fingerprint != fingerprint:
                raise ValueError('Conflito de idempotência: a chave já foi usada para outra emissão.')
            return prior.document
    document, _created = create_print_document(
        branch=branch, document_type=document_type, source_type=source_type,
        source_id=source_id, user=user, metadata=metadata,
    )
    policy = effective_print_route(branch=branch, document_type=document_type, pos_device=pos_device)
    if automatic_only:
        if policy.mode == PrintRouteMode.AUTOMATIC:
            enqueue_print_document(document=document, user=user, pos_device=pos_device)
    else:
        enqueue_print_document(document=document, user=user, pos_device=pos_device, retry_failed=True)
    if idempotency_key:
        try:
            with transaction.atomic():
                request = PrintDocumentRequest.objects.create(
                    branch=branch, document=document, action='issue', idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                )
        except IntegrityError:
            request = PrintDocumentRequest.objects.select_related('document').get(
                branch=branch, action='issue', idempotency_key=idempotency_key,
            )
            if request.request_fingerprint != fingerprint:
                raise ValueError('Conflito de idempotência: a chave já foi usada para outra emissão.')
            return request.document
        request.generated_jobs.set(document.print_jobs.filter(reprint_of__isnull=True))
        audit_log(actor=user, action='print_document.issue', obj=document, company=branch.company,
                  branch=branch, metadata={'idempotency_key': str(idempotency_key)})
    return document


@transaction.atomic
def reprint_print_document(*, document, user, reason='', idempotency_key=None):
    document = PrintDocument.objects.select_for_update().get(pk=document.pk)
    fingerprint = _document_request_fingerprint(
        action='reprint', branch=document.branch, document_id=document.pk, reason=reason,
    )
    if idempotency_key:
        prior = PrintDocumentRequest.objects.prefetch_related('generated_jobs').filter(
            branch=document.branch, action='reprint', idempotency_key=idempotency_key,
        ).first()
        if prior:
            if prior.request_fingerprint != fingerprint:
                raise ValueError('Conflito de idempotência: a chave já foi usada para outra reimpressão.')
            return list(prior.generated_jobs.order_by('id'))
    sources = list(document.print_jobs.filter(reprint_of__isnull=True).order_by('id'))
    from .serializers import print_document_state
    if not print_document_state(document)['reprint_eligible']:
        raise ValueError('O documento só pode ser reimpresso após uma impressão inicial concluída.')
    reprints = [
        reprint_print_job(job=source, user=user, reason=reason)
        for source in sources
    ]
    if idempotency_key:
        try:
            with transaction.atomic():
                request = PrintDocumentRequest.objects.create(
                    branch=document.branch, document=document, action='reprint', idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                )
        except IntegrityError:
            request = PrintDocumentRequest.objects.prefetch_related('generated_jobs').get(
                branch=document.branch, action='reprint', idempotency_key=idempotency_key,
            )
            if request.request_fingerprint != fingerprint:
                raise ValueError('Conflito de idempotência: a chave já foi usada para outra reimpressão.')
            return list(request.generated_jobs.order_by('id'))
        request.generated_jobs.set(reprints)
        audit_log(actor=user, action='print_document.reprint', obj=document, company=document.company,
                  branch=document.branch, metadata={'idempotency_key': str(idempotency_key), 'reason': reason})
    return reprints


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
                'payload_snapshot': _payload(item, destination, ProductionEvent.NEW, command=command, user=user),
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
                batch_key=_batch_key(idempotency_key, destination.pk, device.pk, ProductionEvent.NEW),
            )
            audit_log(actor=user, action='print_job.enqueue', obj=job, company=command.company, branch=command.branch)


def create_cancellation_jobs(*, item, command, user, idempotency_key, reason):
    originals = ProductionJob.objects.filter(order_item=item, event=ProductionEvent.NEW).select_related('destination')
    for original in originals:
        cancellation, created = ProductionJob.objects.get_or_create(
            order_item=item, destination=original.destination, event=ProductionEvent.CANCEL,
            defaults={
                'company': command.company, 'branch': command.branch, 'original_job': original,
                'payload_snapshot': _payload(item, original.destination, ProductionEvent.CANCEL, reason, command=command, user=user),
            },
        )
        if not created:
            continue
        audit_log(actor=user, action='production_job.cancel_notice', obj=cancellation, company=command.company, branch=command.branch, metadata={'idempotency_key': str(idempotency_key)})
        device_ids = original.print_jobs.values_list('printer_device_id', flat=True)
        for device_id in device_ids:
            job = PrintJob.objects.create(company=command.company, branch=command.branch, production_job=cancellation, destination=original.destination, printer_device_id=device_id, payload_snapshot=cancellation.payload_snapshot, idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{cancellation.pk}:device:{device_id}'), batch_key=_batch_key(idempotency_key, original.destination_id, device_id, ProductionEvent.CANCEL))
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
                    'payload_snapshot': _payload(item, destination, ProductionEvent.NEW, sale=sale, user=user),
                },
            )
            if not created:
                continue
            audit_log(actor=user, action='production_job.create', obj=production_job, company=sale.company, branch=sale.branch, metadata={'idempotency_key': str(idempotency_key)})
            for device in destination.printer_devices.filter(branch=sale.branch, status=Status.ACTIVE):
                job = PrintJob.objects.create(company=sale.company, branch=sale.branch, production_job=production_job,
                    destination=destination, printer_device=device, payload_snapshot=production_job.payload_snapshot,
                    idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{production_job.pk}:device:{device.pk}'), batch_key=_batch_key(idempotency_key, destination.pk, device.pk, ProductionEvent.NEW))
                audit_log(actor=user, action='print_job.enqueue', obj=job, company=sale.company, branch=sale.branch)


def create_sale_cancellation_jobs(*, sale, user, idempotency_key, reason):
    for item in sale.items.all():
        originals = ProductionJob.objects.filter(sale_item=item, event=ProductionEvent.NEW).select_related('destination')
        for original in originals:
            cancellation, created = ProductionJob.objects.get_or_create(
                sale_item=item, destination=original.destination, event=ProductionEvent.CANCEL,
                defaults={'company': sale.company, 'branch': sale.branch, 'original_job': original,
                          'payload_snapshot': _payload(item, original.destination, ProductionEvent.CANCEL, reason, sale=sale, user=user)},
            )
            if not created:
                continue
            audit_log(actor=user, action='production_job.cancel_notice', obj=cancellation, company=sale.company, branch=sale.branch, metadata={'idempotency_key': str(idempotency_key)})
            for device_id in original.print_jobs.values_list('printer_device_id', flat=True):
                job = PrintJob.objects.create(company=sale.company, branch=sale.branch, production_job=cancellation,
                    destination=original.destination, printer_device_id=device_id, payload_snapshot=cancellation.payload_snapshot,
                    idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{cancellation.pk}:device:{device_id}'), batch_key=_batch_key(idempotency_key, original.destination_id, device_id, ProductionEvent.CANCEL))
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
    # A ticket remains a commercial record even when its route is disabled.
    issue_print_document(
        branch=branch, document_type=PrintDocumentType.TICKET, source_type='ticket',
        source_id=ticket.pk, user=user, automatic_only=True,
    )
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
                'payload_snapshot': _payload(item, destination, ProductionEvent.NEW, command=command, user=user),
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
                batch_key=_batch_key(idempotency_key, destination.pk, device.pk, ProductionEvent.NEW),
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
                'payload_snapshot': _payload(item, original.destination, ProductionEvent.CANCEL, reason, command=command, user=user),
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
                batch_key=_batch_key(idempotency_key, original.destination_id, device_id, ProductionEvent.CANCEL),
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
                    table_attendance=attendance, user=user,
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
                batch_key=_batch_key(idempotency_key, destination.pk, device.pk, ProductionEvent.NEW),
            )


def create_table_order_item_ticket(*, item, attendance, user):
    if not item.product.emits_ticket:
        return None
    return _create_ticket(
        item=item, company=attendance.company, branch=attendance.branch, user=user,
        source_field='source_table_order_item',
    )


def cancel_table_ticket_for_item(*, item, user):
    return cancel_ticket_for_source(
        source_field='source_table_order_item', item=item, user=user,
    )


def create_table_cancellation_jobs(*, item, attendance, user, idempotency_key, reason):
    originals = ProductionJob.objects.filter(
        table_order_item=item, event=ProductionEvent.NEW,
    ).select_related('destination')
    for original in originals:
        cancellation, created = ProductionJob.objects.get_or_create(
            table_order_item=item, destination=original.destination, event=ProductionEvent.CANCEL,
            defaults={
                'company': attendance.company, 'branch': attendance.branch,
                'original_job': original,
                'payload_snapshot': _payload(
                    item, original.destination, ProductionEvent.CANCEL, reason,
                    table_attendance=attendance, user=user,
                ),
            },
        )
        if not created:
            continue
        audit_log(actor=user, action='production_job.cancel_notice', obj=cancellation,
                  company=attendance.company, branch=attendance.branch,
                  metadata={'idempotency_key': str(idempotency_key)})
        for device_id in original.print_jobs.values_list('printer_device_id', flat=True):
            PrintJob.objects.create(
                company=attendance.company, branch=attendance.branch,
                production_job=cancellation, destination=original.destination,
                printer_device_id=device_id, payload_snapshot=cancellation.payload_snapshot,
                idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f'production:{cancellation.pk}:device:{device_id}'),
                batch_key=_batch_key(idempotency_key, original.destination_id, device_id, ProductionEvent.CANCEL),
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
    if job.status == PrintJobStatus.UNCERTAIN:
        raise ValueError('Resultado incerto exige reimpressão explícita; não faça retry automático.')
    if job.print_document_id:
        if job.status != PrintJobStatus.FAILED or job.physical_dispatch_started_at:
            raise ValueError('Somente falha comprovadamente anterior ao envio físico pode receber retry.')
        # Document copies/printers are independent physical executions.
        jobs = [job]
    else:
        jobs = list(
            PrintJob.objects.select_for_update().filter(batch_key=job.batch_key)
            if job.batch_key else [job]
        )
    if any(item.status not in (PrintJobStatus.FAILED, PrintJobStatus.PENDING) for item in jobs):
        raise ValueError('Todos os jobs do ticket físico precisam estar pendentes ou falhos para retry.')
    for item in jobs:
        item.status = PrintJobStatus.PENDING
        item.last_error = ''
        item.claimed_by = None
        item.lease_until = None
        item.physical_dispatch_started_at = None
        item.save(update_fields=(
            'status', 'last_error', 'claimed_by', 'lease_until',
            'physical_dispatch_started_at', 'updated_at',
        ))
        audit_log(actor=user, action='print_job.retry', obj=item, company=item.company, branch=item.branch)
    return next((item for item in jobs if item.pk == job.pk), job)


PRINT_LEASE_SECONDS = 60
PHYSICAL_DISPATCH_TIMEOUT_SECONDS = 300


def _claimed_batch(*, job, device):
    queryset = PrintJob.objects.select_for_update().filter(
        branch=device.branch, printer_device__connection_type=PrinterConnectionType.NETWORK,
    )
    if job.batch_key:
        return queryset.filter(batch_key=job.batch_key).order_by('id')
    return queryset.filter(pk=job.pk)


@transaction.atomic
def expire_abandoned_print_dispatches(*, branch):
    """Resolve expired physical dispatches without making them claimable again."""
    cutoff = timezone.now() - timedelta(seconds=PHYSICAL_DISPATCH_TIMEOUT_SECONDS)
    candidates = list(PrintJob.objects.filter(
        branch=branch,
        status=PrintJobStatus.PROCESSING,
        physical_dispatch_started_at__lte=cutoff,
    ).values_list('pk', 'batch_key'))
    expired = []
    handled_batches = set()
    for job_id, batch_key in candidates:
        group_key = batch_key or job_id
        if group_key in handled_batches:
            continue
        handled_batches.add(group_key)
        jobs_queryset = PrintJob.objects.select_for_update().filter(branch=branch)
        if batch_key:
            jobs_queryset = jobs_queryset.filter(batch_key=batch_key).order_by('id')
        else:
            jobs_queryset = jobs_queryset.filter(pk=job_id)
        jobs = list(jobs_queryset)
        if not any(
            item.status == PrintJobStatus.PROCESSING
            and item.physical_dispatch_started_at
            and item.physical_dispatch_started_at <= cutoff
            for item in jobs
        ):
            continue
        for item in jobs:
            if (
                item.status != PrintJobStatus.PROCESSING
                or item.physical_dispatch_started_at is None
            ):
                continue
            item.status = PrintJobStatus.UNCERTAIN
            item.lease_until = None
            item.last_error = 'Dispatch físico sem resultado dentro do prazo de segurança.'
            item.save(update_fields=('status', 'lease_until', 'last_error', 'updated_at'))
            audit_log(
                actor=None, action='print_job.uncertain_timeout', obj=item,
                company=item.company, branch=item.branch,
                metadata={
                    'batch_key': str(item.batch_key or ''),
                    'physical_dispatch_started_at': item.physical_dispatch_started_at.isoformat(),
                    'timeout_seconds': PHYSICAL_DISPATCH_TIMEOUT_SECONDS,
                },
            )
            expired.append(item.pk)
    return expired


@transaction.atomic
def claim_print_job(*, job_id, device):
    now = timezone.now()
    job = PrintJob.objects.select_related('printer_device').filter(
        pk=job_id, branch=device.branch, printer_device__connection_type=PrinterConnectionType.NETWORK,
        printer_device__status=Status.ACTIVE,
    ).first()
    if not job:
        raise ValueError('Job de impressão não disponível para esta filial.')
    jobs = list(_claimed_batch(job=job, device=device).select_related('printer_device'))
    if not jobs or any(
        item.status == PrintJobStatus.UNCERTAIN
        or item.physical_dispatch_started_at is not None
        or (
            item.status == PrintJobStatus.PROCESSING
            and item.claimed_by_id != device.pk
            and (not item.lease_until or item.lease_until > now)
        )
        or item.status not in (PrintJobStatus.PENDING, PrintJobStatus.PROCESSING)
        for item in jobs
    ):
        raise ValueError('Job já está em execução ou exige intervenção.')
    lease_until = now + timedelta(seconds=PRINT_LEASE_SECONDS)
    for item in jobs:
        item.status = PrintJobStatus.PROCESSING
        item.claimed_by = device
        item.lease_until = lease_until
        item.processing_at = now
        item.attempts += 1
        item.last_error = ''
        item.save(update_fields=('status', 'claimed_by', 'lease_until', 'processing_at', 'attempts', 'last_error', 'updated_at'))
        audit_log(actor=None, action='print_job.claimed', obj=item, company=item.company, branch=item.branch,
                  metadata={'device_id': str(device.pk), 'attempt': item.attempts, 'lease_until': lease_until.isoformat()})
    return jobs


@transaction.atomic
def renew_print_lease(*, job_id, device):
    job = PrintJob.objects.filter(pk=job_id, branch=device.branch).first()
    if not job:
        raise ValueError('Job de impressão não encontrado.')
    jobs = list(_claimed_batch(job=job, device=device))
    now = timezone.now()
    if not jobs or any(
        item.status != PrintJobStatus.PROCESSING
        or item.claimed_by_id != device.pk
        or item.physical_dispatch_started_at is not None
        or not item.lease_until
        or item.lease_until <= now
        for item in jobs
    ):
        raise ValueError('Lease de impressão inválida ou expirada.')
    lease_until = now + timedelta(seconds=PRINT_LEASE_SECONDS)
    for item in jobs:
        item.lease_until = lease_until
        item.save(update_fields=('lease_until', 'updated_at'))
    return jobs


@transaction.atomic
def start_print_dispatch(*, job_id, device):
    """Atomically cross the point after which automatic retry is unsafe."""
    job = PrintJob.objects.filter(pk=job_id, branch=device.branch).first()
    if not job:
        raise ValueError('Job de impressão não encontrado.')
    jobs = list(_claimed_batch(job=job, device=device).select_related('printer_device'))
    now = timezone.now()
    if not jobs or any(
        item.status != PrintJobStatus.PROCESSING
        or item.claimed_by_id != device.pk
        or item.physical_dispatch_started_at is not None
        or not item.lease_until
        or item.lease_until <= now
        for item in jobs
    ):
        raise ValueError('Este POS não possui o claim ativo para iniciar o dispatch.')
    for item in jobs:
        item.physical_dispatch_started_at = now
        item.save(update_fields=('physical_dispatch_started_at', 'updated_at'))
        audit_log(
            actor=None, action='print_job.dispatch_started', obj=item,
            company=item.company, branch=item.branch,
            metadata={'device_id': str(device.pk), 'batch_key': str(item.batch_key or '')},
        )
    return jobs


def _record_printer_observation(job, *, status, error='', observed=False):
    device = job.printer_device
    now = timezone.now()
    device.operational_status = status
    device.last_operational_error = error[:300]
    update_fields = ['operational_status', 'last_operational_error', 'updated_at']
    if observed:
        device.last_seen_at = now
        update_fields.append('last_seen_at')
        if job.is_test:
            device.last_test_at = now
            update_fields.append('last_test_at')
    device.save(update_fields=update_fields)


@transaction.atomic
def complete_print_job(*, job_id, device, outcome, error='', metadata=None):
    job = PrintJob.objects.select_related('printer_device').filter(pk=job_id, branch=device.branch).first()
    if not job:
        raise ValueError('Job de impressão não encontrado.')
    jobs = list(_claimed_batch(job=job, device=device).select_related('printer_device'))
    now = timezone.now()
    if not jobs or any(
        item.status != PrintJobStatus.PROCESSING or item.claimed_by_id != device.pk
        or item.physical_dispatch_started_at is None
        for item in jobs
    ):
        raise ValueError('Este POS não possui um dispatch físico iniciado para o job.')
    status = {
        'printed': PrintJobStatus.PRINTED,
        'failed': PrintJobStatus.FAILED,
        'uncertain': PrintJobStatus.UNCERTAIN,
    }.get(outcome)
    if not status:
        raise ValueError('Resultado de impressão inválido.')
    for item in jobs:
        item.status = status
        item.last_error = (error or '')[:1000]
        item.executor_metadata = {'device_id': str(device.pk), **(metadata or {})}
        item.lease_until = None
        if status == PrintJobStatus.PRINTED:
            item.printed_at = now
        item.save(update_fields=('status', 'last_error', 'executor_metadata', 'lease_until', 'printed_at', 'updated_at'))
        _record_printer_observation(
            item,
            status=PrinterOperationalStatus.ONLINE if status == PrintJobStatus.PRINTED else PrinterOperationalStatus.OFFLINE if item.is_test else PrinterOperationalStatus.FAILED,
            error=item.last_error,
            observed=status == PrintJobStatus.PRINTED or bool((metadata or {}).get('printer_observed')),
        )
        audit_log(actor=None, action=f'print_job.{outcome}', obj=item, company=item.company, branch=item.branch,
                  metadata={
                      'device_id': str(device.pk), 'attempt': item.attempts, 'error': item.last_error,
                      'document_id': item.print_document_id,
                      'document_type': item.print_document.document_type if item.print_document_id else None,
                  })
    return jobs


@transaction.atomic
def reconcile_print_jobs(*, device, entries):
    expire_abandoned_print_dispatches(branch=device.branch)
    reconciled = []
    for entry in entries:
        job_id = entry.get('job_id')
        state = entry.get('state')
        if not isinstance(job_id, int) or state not in ('attempted', 'sent', 'acknowledged', 'failed_before_send'):
            continue
        job = PrintJob.objects.filter(pk=job_id, branch=device.branch).first()
        if not job:
            continue
        terminal_statuses = {
            'acknowledged': (PrintJobStatus.PRINTED,),
            'sent': (PrintJobStatus.PRINTED, PrintJobStatus.UNCERTAIN),
            'failed_before_send': (PrintJobStatus.FAILED,),
        }
        if state == 'attempted':
            # No socket was opened before this ledger state. A pending/leased job
            # remains backend-owned; a persisted dispatch becomes explicitly uncertain.
            if job.status in (
                PrintJobStatus.PRINTED,
                PrintJobStatus.FAILED,
                PrintJobStatus.UNCERTAIN,
                PrintJobStatus.CANCELLED,
            ) or (
                job.status == PrintJobStatus.PENDING
                or (
                    job.status == PrintJobStatus.PROCESSING
                    and job.physical_dispatch_started_at is None
                )
            ):
                reconciled.append(job_id)
                continue
            outcome = 'uncertain'
        elif job.status in terminal_statuses[state]:
            reconciled.append(job_id)
            continue
        else:
            outcome = {
                'acknowledged': 'printed',
                'sent': 'uncertain',
                'failed_before_send': 'failed',
            }[state]
        try:
            complete_print_job(
                job_id=job_id, device=device,
                outcome=outcome,
                metadata={
                    'reconciled': True,
                    'printer_observed': entry.get('printer_observed') is True,
                },
            )
        except ValueError:
            continue
        reconciled.append(job_id)
    if reconciled:
        audit_log(actor=None, action='print_job.reconciled', company=device.branch.company, branch=device.branch,
                  metadata={'device_id': str(device.pk), 'job_ids': reconciled})
    return reconciled


@transaction.atomic
def reprint_print_job(*, job, user, reason=''):
    requested = PrintJob.objects.select_for_update().get(pk=job.pk)
    sources = list(
        PrintJob.objects.select_for_update().filter(batch_key=requested.batch_key).order_by('id')
        if requested.batch_key else [requested]
    )
    if requested.is_test or any(
        source.is_test
        or source.status not in (PrintJobStatus.PRINTED, PrintJobStatus.UNCERTAIN)
        for source in sources
    ):
        raise ValueError('Reimpressão exige jobs não-test já impressos ou com resultado incerto.')
    roots = {
        source.reprint_of_id or source.pk
        for source in sources
    }
    descendants = list(PrintJob.objects.select_for_update().filter(reprint_of_id__in=roots))
    number = max((copy.reprint_number for copy in descendants), default=0) + 1
    new_batch_key = uuid.uuid4() if requested.batch_key else None
    copies = {}
    for source in sources:
        root_id = source.reprint_of_id or source.pk
        copy = PrintJob.objects.create(
            company=source.company, branch=source.branch,
            production_job=source.production_job, print_document=source.print_document,
            destination=source.destination,
            printer_device=source.printer_device,
            payload_snapshot={**source.payload_snapshot, 'reprint': True, 'reprint_number': number},
            batch_key=new_batch_key, reprint_of_id=root_id, reprint_number=number,
        )
        copies[source.pk] = copy
        audit_log(
            actor=user, action='print_job.reprint_requested', obj=copy,
            company=copy.company, branch=copy.branch,
            metadata={
                'source_print_job_id': str(source.pk),
                'reprint_number': number,
                'reason': (reason or '').strip(),
                'batch_key': str(new_batch_key or ''),
                'document_id': copy.print_document_id,
                'document_type': copy.print_document.document_type if copy.print_document_id else None,
            },
        )
    return copies[requested.pk]


@transaction.atomic
def manual_dispatch_print_job(*, job, user):
    job = PrintJob.objects.select_for_update().get(pk=job.pk)
    if job.status not in (PrintJobStatus.PENDING, PrintJobStatus.FAILED):
        raise ValueError('Only pending or failed jobs can be manually dispatched.')
    if job.printer_device.connection_type == PrinterConnectionType.NETWORK:
        raise ValueError('Impressoras NETWORK são executadas apenas pelo CORE POS local.')
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
    if device.connection_type != PrinterConnectionType.NETWORK:
        raise ValueError('Este bloco executa testes apenas para impressoras NETWORK pelo CORE POS local.')
    job = PrintJob.objects.create(
        company=device.branch.company, branch=device.branch,
        printer_device=device, is_test=True,
        payload_snapshot={
            'test': True, 'title': 'CORE PDV', 'message': 'TESTE DE IMPRESSÃO',
            'branch': device.branch.name, 'printer': device.name,
            'host': (device.technical_configuration or {}).get('host', ''),
            'created_at': timezone.now().isoformat(),
        },
    )
    audit_log(actor=user, action='printer.test', obj=device, company=device.branch.company, branch=device.branch, metadata={'print_job_id': job.pk, 'status': job.status})
    return job
