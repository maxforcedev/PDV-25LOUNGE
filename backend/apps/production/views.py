from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot

from .models import PrintDocument, PrintDocumentType, PrintJob, PrintRoute, PrintRouteOverride, PrinterDevice, ProductionJob, Ticket
from .permissions import ProductionFunctionalPermission
from .serializers import (
    PrintDocumentIssueSerializer, PrintDocumentResultSerializer, PrintDocumentSerializer, PrintJobSerializer,
    PrintRouteOverrideSerializer, PrintRouteSerializer, PrinterDeviceSerializer,
    ProductionJobSerializer, ReprintSerializer, TicketSerializer,
)
from .services import (
    effective_print_route, enqueue_print_document, ensure_print_routes,
    expire_abandoned_print_dispatches, issue_print_document, manual_dispatch_print_job,
    reprint_print_document, reprint_print_job, retry_print_job, test_printer_device,
)


class PrinterDeviceViewSet(viewsets.ModelViewSet):
    serializer_class = PrinterDeviceSerializer
    permission_classes = (ProductionFunctionalPermission,)
    permission_codes = {action: 'printers.manage' for action in ('list', 'retrieve', 'create', 'update', 'partial_update', 'destroy', 'test', 'history')}

    def get_queryset(self):
        return PrinterDevice.objects.filter(branch=self.request.branch_context).prefetch_related('destinations')

    @transaction.atomic
    def perform_create(self, serializer):
        device = serializer.save(branch=self.request.branch_context)
        audit_log(actor=self.request.user, action='printer_device.create', obj=device, company=device.branch.company, branch=device.branch, after=model_snapshot(device, ('name', 'device_type', 'status', 'technical_configuration')))

    @transaction.atomic
    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('name', 'device_type', 'status', 'technical_configuration'))
        device = serializer.save()
        audit_log(actor=self.request.user, action='printer_device.update', obj=device, company=device.branch.company, branch=device.branch, before=before, after=model_snapshot(device, ('name', 'device_type', 'status', 'technical_configuration')))

    @transaction.atomic
    def perform_destroy(self, instance):
        before = model_snapshot(instance, ('name', 'device_type', 'status'))
        instance.status = 'inactive'
        instance.save(update_fields=('status', 'updated_at'))
        for destination in instance.destinations.all():
            # Destinations remain operational while another active printer serves them.
            if not destination.printer_devices.exclude(pk=instance.pk).filter(status='active').exists():
                destination.status = 'inactive'
                destination.save(update_fields=('status', 'updated_at'))
        audit_log(actor=self.request.user, action='printer_device.deactivate', obj=instance, company=instance.branch.company, branch=instance.branch, before=before, after=model_snapshot(instance, ('name', 'device_type', 'status')))

    @action(detail=True, methods=('post',))
    def test(self, request, pk=None):
        try:
            job = test_printer_device(device=self.get_object(), user=request.user)
        except ValueError as error:
            raise ValidationError({'detail': str(error)})
        return Response(PrintJobSerializer(job).data, status=201)

    @action(detail=True, methods=('get',))
    def history(self, request, pk=None):
        expire_abandoned_print_dispatches(branch=self.request.branch_context)
        queryset = self.get_object().print_jobs.select_related(
            'production_job', 'production_job__sale_item__sale',
            'destination', 'printer_device',
        ).order_by('-created_at', '-id')
        page = self.paginate_queryset(queryset)
        serializer = PrintJobSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class ProductionJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductionJobSerializer
    permission_classes = (ProductionFunctionalPermission,)
    permission_codes = {'list': 'production.view', 'retrieve': 'production.view'}

    def get_queryset(self):
        return ProductionJob.objects.filter(branch=self.request.branch_context).select_related('destination', 'order_item', 'sale_item')


class TicketViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TicketSerializer
    permission_classes = (ProductionFunctionalPermission,)
    permission_codes = {'list': 'tickets.view', 'retrieve': 'tickets.view', 'reprint': 'tickets.reprint'}

    def get_queryset(self):
        return Ticket.objects.filter(branch=self.request.branch_context).select_related('source_sale_item', 'source_order_item')

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def reprint(self, request, pk=None):
        ticket = Ticket.objects.select_for_update().get(pk=self.get_object().pk)
        try:
            document = PrintDocument.objects.filter(
                branch=ticket.branch, document_type=PrintDocumentType.TICKET,
                source_type='ticket', source_id=str(ticket.pk),
            ).order_by('-version', '-id').first()
            if document is None:
                raise ValueError('O ticket ainda não possui documento de impressão.')
            reprint_print_document(document=document, user=request.user, reason='Reimpressão de ticket')
        except ValueError as error:
            raise ValidationError({'detail': str(error)})
        ticket.reprint_count += 1
        ticket.save(update_fields=('reprint_count', 'updated_at'))
        audit_log(actor=request.user, action='ticket.reprint', obj=ticket, company=ticket.company, branch=ticket.branch, metadata={'reprint_count': ticket.reprint_count})
        return Response(self.get_serializer(ticket).data)


class PrintJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PrintJobSerializer
    permission_classes = (ProductionFunctionalPermission,)
    permission_codes = {'list': 'print_jobs.view', 'retrieve': 'print_jobs.view', 'retry': 'print_jobs.retry', 'reprint': 'print_jobs.reprint', 'manual_dispatch': 'print_jobs.retry'}

    def get_queryset(self):
        expire_abandoned_print_dispatches(branch=self.request.branch_context)
        queryset = PrintJob.objects.filter(branch=self.request.branch_context).select_related(
            'production_job', 'production_job__sale_item__sale',
            'print_document', 'destination', 'printer_device',
        ).order_by('-created_at', '-id')
        job_status = self.request.query_params.get('status')
        printer_id = self.request.query_params.get('printer_device')
        if job_status:
            queryset = queryset.filter(status=job_status)
        if printer_id:
            queryset = queryset.filter(printer_device_id=printer_id)
        return queryset

    @action(detail=True, methods=('post',))
    def retry(self, request, pk=None):
        try:
            job = retry_print_job(job=self.get_object(), user=request.user)
        except ValueError as error:
            raise ValidationError({'detail': str(error)})
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=('post',))
    def reprint(self, request, pk=None):
        serializer = ReprintSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            job = reprint_print_job(
                job=self.get_object(), user=request.user,
                reason=serializer.validated_data.get('reason', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)})
        return Response(self.get_serializer(job).data, status=201)

    @action(detail=True, methods=('post',), url_path='manual-dispatch')
    def manual_dispatch(self, request, pk=None):
        try:
            job = manual_dispatch_print_job(job=self.get_object(), user=request.user)
        except ValueError as error:
            raise ValidationError({'detail': str(error)})
        return Response(self.get_serializer(job).data)


class PrintRouteViewSet(viewsets.ModelViewSet):
    serializer_class = PrintRouteSerializer
    permission_classes = (ProductionFunctionalPermission,)
    permission_codes = {action: 'print_routes.manage' for action in ('list', 'retrieve', 'create', 'update', 'partial_update', 'destroy')}

    def get_queryset(self):
        ensure_print_routes(self.request.branch_context)
        return PrintRoute.objects.filter(branch=self.request.branch_context).prefetch_related('printer_devices')

    @transaction.atomic
    def perform_create(self, serializer):
        route = serializer.save(branch=self.request.branch_context)
        audit_log(actor=self.request.user, action='print_route.create', obj=route,
                  company=route.branch.company, branch=route.branch,
                  after=model_snapshot(route, ('document_type', 'mode', 'copies', 'document_format')),
                  metadata={'printer_device_ids': list(route.printer_devices.values_list('id', flat=True))})

    @transaction.atomic
    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('document_type', 'mode', 'copies', 'document_format'))
        route = serializer.save()
        audit_log(actor=self.request.user, action='print_route.update', obj=route,
                  company=route.branch.company, branch=route.branch, before=before,
                  after=model_snapshot(route, ('document_type', 'mode', 'copies', 'document_format')),
                  metadata={'printer_device_ids': list(route.printer_devices.values_list('id', flat=True))})

    @transaction.atomic
    def perform_destroy(self, instance):
        audit_log(actor=self.request.user, action='print_route.delete', obj=instance,
                  company=instance.branch.company, branch=instance.branch,
                  before=model_snapshot(instance, ('document_type', 'mode', 'copies', 'document_format')))
        instance.delete()


class PrintRouteOverrideViewSet(viewsets.ModelViewSet):
    serializer_class = PrintRouteOverrideSerializer
    permission_classes = (ProductionFunctionalPermission,)
    permission_codes = {action: 'print_routes.manage' for action in ('list', 'retrieve', 'create', 'update', 'partial_update', 'destroy')}

    def get_queryset(self):
        return PrintRouteOverride.objects.filter(pos_device__branch=self.request.branch_context).select_related('pos_device').prefetch_related('printer_devices')

    @transaction.atomic
    def perform_create(self, serializer):
        override = serializer.save()
        audit_log(actor=self.request.user, action='print_route_override.create', obj=override,
                  company=override.pos_device.branch.company, branch=override.pos_device.branch,
                  after=model_snapshot(override, ('document_type', 'inherit_branch', 'mode', 'copies', 'document_format')),
                  metadata={'printer_device_ids': list(override.printer_devices.values_list('id', flat=True))})

    @transaction.atomic
    def perform_update(self, serializer):
        before = model_snapshot(serializer.instance, ('document_type', 'inherit_branch', 'mode', 'copies', 'document_format'))
        override = serializer.save()
        audit_log(actor=self.request.user, action='print_route_override.update', obj=override,
                  company=override.pos_device.branch.company, branch=override.pos_device.branch, before=before,
                  after=model_snapshot(override, ('document_type', 'inherit_branch', 'mode', 'copies', 'document_format')),
                  metadata={'printer_device_ids': list(override.printer_devices.values_list('id', flat=True))})

    @transaction.atomic
    def perform_destroy(self, instance):
        audit_log(actor=self.request.user, action='print_route_override.delete', obj=instance,
                  company=instance.pos_device.branch.company, branch=instance.pos_device.branch,
                  before=model_snapshot(instance, ('document_type', 'inherit_branch', 'mode', 'copies', 'document_format')))
        instance.delete()


class PrintDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PrintDocumentSerializer
    permission_classes = (ProductionFunctionalPermission,)
    permission_codes = {'list': 'print_documents.view', 'retrieve': 'print_documents.view', 'issue': 'print_documents.print', 'reprint': 'print_documents.reprint'}

    def get_queryset(self):
        queryset = PrintDocument.objects.filter(branch=self.request.branch_context).prefetch_related(
            'print_jobs__printer_device',
        ).order_by('-created_at', '-id')
        source_type = self.request.query_params.get('source_type')
        source_id = self.request.query_params.get('source_id')
        document_type = self.request.query_params.get('document_type')
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        if source_id:
            queryset = queryset.filter(source_id=source_id)
        if document_type:
            queryset = queryset.filter(document_type=document_type)
        return queryset

    @action(detail=False, methods=('post',))
    @transaction.atomic
    def issue(self, request):
        serializer = PrintDocumentIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            document = issue_print_document(branch=request.branch_context, user=request.user, **serializer.validated_data)
        except ValueError as error:
            raise ValidationError({'detail': str(error)})
        return Response(PrintDocumentResultSerializer(document, context={'request': request}).data, status=201)

    @action(detail=True, methods=('post',))
    @transaction.atomic
    def reprint(self, request, pk=None):
        serializer = ReprintSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = self.get_object()
        try:
            reprint_print_document(
                document=document, user=request.user,
                reason=serializer.validated_data.get('reason', ''),
                idempotency_key=serializer.validated_data.get('idempotency_key'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)})
        audit_log(actor=request.user, action='print_document.reprint_requested', obj=document,
                  company=document.company, branch=document.branch,
                  metadata={'document_type': document.document_type, 'source_type': document.source_type,
                            'source_id': document.source_id})
        return Response(PrintDocumentResultSerializer(document, context={'request': request}).data, status=201)
