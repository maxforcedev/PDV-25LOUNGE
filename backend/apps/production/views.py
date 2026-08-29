from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.base.audit import audit_log, model_snapshot

from .models import PrintJob, PrinterDevice, ProductionJob, Ticket
from .permissions import ProductionFunctionalPermission
from .serializers import (
    PrintJobSerializer, PrinterDeviceSerializer, ProductionJobSerializer,
    ReprintSerializer, TicketSerializer,
)
from .services import manual_dispatch_print_job, reprint_print_job, retry_print_job, test_printer_device


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
        ticket.reprint_count += 1
        ticket.save(update_fields=('reprint_count', 'updated_at'))
        audit_log(actor=request.user, action='ticket.reprint', obj=ticket, company=ticket.company, branch=ticket.branch, metadata={'reprint_count': ticket.reprint_count})
        return Response(self.get_serializer(ticket).data)


class PrintJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PrintJobSerializer
    permission_classes = (ProductionFunctionalPermission,)
    permission_codes = {'list': 'print_jobs.view', 'retrieve': 'print_jobs.view', 'retry': 'print_jobs.retry', 'reprint': 'print_jobs.reprint', 'manual_dispatch': 'print_jobs.retry'}

    def get_queryset(self):
        queryset = PrintJob.objects.filter(branch=self.request.branch_context).select_related(
            'production_job', 'production_job__sale_item__sale',
            'destination', 'printer_device',
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
        job = reprint_print_job(
            job=self.get_object(), user=request.user,
            reason=serializer.validated_data.get('reason', ''),
        )
        return Response(self.get_serializer(job).data, status=201)

    @action(detail=True, methods=('post',), url_path='manual-dispatch')
    def manual_dispatch(self, request, pk=None):
        try:
            job = manual_dispatch_print_job(job=self.get_object(), user=request.user)
        except ValueError as error:
            raise ValidationError({'detail': str(error)})
        return Response(self.get_serializer(job).data)
