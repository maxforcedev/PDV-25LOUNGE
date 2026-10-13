from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.commands.permissions import CommandFunctionalPermission

from .models import AttendanceCommand, AttendanceCommandStatus, AttendanceOrderItem, AttendanceOrderItemStatus, AttendancePaymentStatus
from .serializers import (
    AttendanceLegacyServiceFeeRegularizationSerializer,
    AttendanceItemFinancialRegularizationInputSerializer,
    AttendanceServiceFeeRegularizationInputSerializer,
)
from .services import (
    AttendanceConflict,
    command_financial_status,
    _legacy_unfrozen_command_items,
    regularize_command_service_fee_rate,
    regularize_command_item_financials,
)


class AttendanceLegacyServiceFeeRegularizationsView(APIView):
    permission_classes = [CommandFunctionalPermission]
    action = 'legacy_service_fee_regularizations'

    def get(self, request):
        branch = getattr(request, 'branch_context', None)
        if branch is None:
            raise PermissionDenied('Selecione uma filial.')
        commands = AttendanceCommand.objects.filter(
            branch=branch,
            status=AttendanceCommandStatus.OPEN,
            payments__status=AttendancePaymentStatus.APPLIED,
        ).annotate(payment_count=Count('payments', filter=Q(
            payments__status=AttendancePaymentStatus.APPLIED,
        ))).order_by('-created_at', '-id')
        data = []
        for command in commands:
            financial_status = command_financial_status(command)
            if financial_status['state'] == 'NORMAL':
                continue
            data.append({**AttendanceLegacyServiceFeeRegularizationSerializer(command).data, 'financial_status': financial_status})
        return Response(data)


class AttendanceCommandServiceFeeRegularizationView(APIView):
    permission_classes = [CommandFunctionalPermission]
    action = 'regularize_service_fee_rate'

    def post(self, request, command_id):
        branch = getattr(request, 'branch_context', None)
        if branch is None:
            raise PermissionDenied('Selecione uma filial.')
        serializer = AttendanceServiceFeeRegularizationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = get_object_or_404(AttendanceCommand, pk=command_id, branch=branch)
        try:
            command, replayed = regularize_command_service_fee_rate(
                command=command, user=request.user, **serializer.validated_data,
            )
        except AttendanceConflict as error:
            return Response({'code': error.code, 'detail': error.message}, status=409)
        response = Response(AttendanceLegacyServiceFeeRegularizationSerializer(command).data)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response


class AttendanceCommandFinancialRegularizationView(APIView):
    permission_classes = [CommandFunctionalPermission]
    action = 'financial_regularization_detail'

    def get(self, request, command_id):
        branch = getattr(request, 'branch_context', None)
        if branch is None:
            raise PermissionDenied('Selecione uma filial.')
        command = get_object_or_404(AttendanceCommand, pk=command_id, branch=branch)
        confirmed = list(AttendanceOrderItem.objects.filter(order__command=command, status=AttendanceOrderItemStatus.CONFIRMED).order_by('id'))
        affected = _legacy_unfrozen_command_items(command, confirmed)
        return Response({
            'command': AttendanceLegacyServiceFeeRegularizationSerializer(command).data,
            'financial_status': command_financial_status(command, confirmed),
            'service_fee_rate_regularization_required': command.service_fee_rate_snapshot is None,
            'items': [{'id': item.pk, 'product_name': item.product_name, 'quantity': str(item.quantity), 'unit_price': str(item.unit_price), 'confirmed_at': item.confirmed_at, 'created_at': item.created_at, 'financial_snapshot': item.financial_snapshot, 'issue': 'inconsistent' if item.financial_snapshot else 'missing'} for item in affected],
            'payments': list(command.payments.select_related('payment_method').values('id', 'amount', 'status', 'payment_method__name', 'created_at', 'reversal_of_id')),
        })


class AttendanceCommandItemFinancialRegularizationView(APIView):
    permission_classes = [CommandFunctionalPermission]
    action = 'regularize_item_financials'

    def post(self, request, command_id):
        branch = getattr(request, 'branch_context', None)
        if branch is None:
            raise PermissionDenied('Selecione uma filial.')
        serializer = AttendanceItemFinancialRegularizationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = get_object_or_404(AttendanceCommand, pk=command_id, branch=branch)
        try:
            result, replayed = regularize_command_item_financials(command=command, user=request.user, **data)
        except AttendanceConflict as error:
            return Response({'code': error.code, 'detail': error.message}, status=409)
        response = Response(result)
        if replayed:
            response['Idempotency-Replayed'] = 'true'
        return response
