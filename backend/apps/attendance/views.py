from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.commands.permissions import CommandFunctionalPermission

from .models import AttendanceCommand, AttendanceCommandStatus, AttendancePaymentStatus
from .serializers import (
    AttendanceLegacyServiceFeeRegularizationSerializer,
    AttendanceServiceFeeRegularizationInputSerializer,
)
from .services import (
    AttendanceConflict,
    regularize_command_service_fee_rate,
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
            service_fee_rate_snapshot__isnull=True,
            payments__status=AttendancePaymentStatus.APPLIED,
        ).annotate(payment_count=Count('payments', filter=Q(
            payments__status=AttendancePaymentStatus.APPLIED,
        ))).order_by('-created_at', '-id')
        return Response(AttendanceLegacyServiceFeeRegularizationSerializer(commands, many=True).data)


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
