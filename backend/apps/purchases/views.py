import mimetypes

from django.http import FileResponse
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.companies.models import Branch
from apps.companies.selectors import accessible_branches

from .models import PayableInstallment, PurchaseOrder, PurchaseReceipt
from .permissions import PurchaseFunctionalPermission
from .serializers import (
    PayableInstallmentSerializer,
    PayInstallmentSerializer,
    PurchaseAttachmentSerializer,
    PurchaseOrderCreateSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderUpdateSerializer,
    PurchaseReceiptCreateSerializer,
    PurchaseReceiptSerializer,
    ReasonSerializer,
    SetInstallmentsSerializer,
)
from .services import (
    cancel_installment,
    cancel_purchase_order,
    close_partial_purchase_order,
    create_purchase_order,
    pay_installment,
    place_purchase_order,
    receive_purchase_order,
    set_purchase_attachment,
    set_installments,
    update_purchase_order,
)
from .storage import purchase_attachment_download_name


def _scoped_branches(request, code):
    support = getattr(request, 'support_session', None)
    branches = accessible_branches(request.user, code)
    if support:
        branches = Branch.objects.filter(company_id=support.company_id)
    current = getattr(request, 'branch_context', None)
    if current:
        branches = branches.filter(pk=current.pk)
    return branches


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = (PurchaseFunctionalPermission,)
    http_method_names = ('get', 'post', 'put', 'patch', 'head', 'options')
    permission_codes = {
        'list': 'purchases.view',
        'retrieve': 'purchases.view',
        'create': 'purchases.create',
        'update': 'purchases.create',
        'partial_update': 'purchases.create',
        'destroy': 'purchases.close',
        'place': 'purchases.place',
        'receive': 'purchases.receive',
        'close_partial': 'purchases.close',
        'cancel': 'purchases.close',
        'set_installments': 'purchases.manage_payables',
        'attachment': 'purchases.view',
    }

    def get_queryset(self):
        code = self.permission_codes.get(self.action, 'purchases.view')
        queryset = PurchaseOrder.objects.select_related(
            'company', 'branch', 'supplier', 'created_by', 'placed_by', 'closed_by'
        ).prefetch_related(
            'items__receipt_items', 'installments__supplier',
            'receipts__items', 'receipts__purchase_order',
        ).filter(branch__in=_scoped_branches(self.request, code))
        params = self.request.query_params
        for parameter, field in (
            ('status', 'status'), ('order_type', 'order_type'),
            ('supplier', 'supplier_id'),
        ):
            if params.get(parameter):
                queryset = queryset.filter(**{field: params[parameter]})
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search)
                | Q(supplier__trade_name__icontains=search)
                | Q(document_number__icontains=search)
                | Q(document_key__icontains=search)
            )
        return queryset.distinct()

    def create(self, request, *args, **kwargs):
        serializer = PurchaseOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        current = getattr(request, 'branch_context', None)
        if current and current.pk != data['branch']:
            raise PermissionDenied('Filial fora do contexto autorizado.')
        order = create_purchase_order(
            user=request.user,
            support_session=getattr(request, 'support_session', None),
            **data,
        )
        return Response(
            PurchaseOrderSerializer(order, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    def _update(self, request, partial):
        order = self.get_object()
        serializer = PurchaseOrderUpdateSerializer(
            data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        order = update_purchase_order(
            purchase_order=order, user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(PurchaseOrderSerializer(order, context={'request': request}).data)

    def update(self, request, *args, **kwargs):
        return self._update(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update(request, partial=True)

    @action(detail=True, methods=('post',))
    def place(self, request, pk=None):
        order = place_purchase_order(
            purchase_order=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
        )
        return Response(PurchaseOrderSerializer(order, context={'request': request}).data)

    @action(detail=True, methods=('post',))
    def receive(self, request, pk=None):
        serializer = PurchaseReceiptCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = receive_purchase_order(
            purchase_order=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        replayed = bool(getattr(receipt, '_idempotency_replayed', False))
        request.audit_fallback_suppressed = replayed
        return Response(
            PurchaseReceiptSerializer(receipt, context={'request': request}).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=('post',), url_path='close-partial')
    def close_partial(self, request, pk=None):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = close_partial_purchase_order(
            purchase_order=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(PurchaseOrderSerializer(order, context={'request': request}).data)

    @action(detail=True, methods=('post',))
    def cancel(self, request, pk=None):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = cancel_purchase_order(
            purchase_order=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(PurchaseOrderSerializer(order, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='installments')
    def set_installments(self, request, pk=None):
        serializer = SetInstallmentsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = set_installments(
            purchase_order=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(
            PayableInstallmentSerializer(items, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=('get', 'post'),
        parser_classes=(MultiPartParser, FormParser),
    )
    def attachment(self, request, pk=None):
        order = self.get_object()
        if request.method == 'POST':
            serializer = PurchaseAttachmentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            order = set_purchase_attachment(
                purchase_order=order,
                attachment=serializer.validated_data['attachment'],
                user=request.user,
                support_session=getattr(request, 'support_session', None),
            )
            return Response(
                PurchaseOrderSerializer(order, context={'request': request}).data
            )
        if not order.attachment or not order.attachment.storage.exists(order.attachment.name):
            raise NotFound('Anexo nao encontrado.')
        filename = purchase_attachment_download_name(order.attachment)
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        return FileResponse(
            order.attachment.open('rb'),
            as_attachment=True,
            filename=filename,
            content_type=content_type,
        )


class PurchaseReceiptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PurchaseReceiptSerializer
    permission_classes = (PurchaseFunctionalPermission,)
    permission_codes = {'list': 'purchases.view', 'retrieve': 'purchases.view'}

    def get_queryset(self):
        return PurchaseReceipt.objects.select_related(
            'purchase_order__supplier', 'company', 'branch', 'confirmed_by'
        ).prefetch_related('items').filter(
            branch__in=_scoped_branches(self.request, 'purchases.view')
        )


class PayableInstallmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayableInstallmentSerializer
    permission_classes = (PurchaseFunctionalPermission,)
    permission_codes = {
        'list': 'purchases.manage_payables',
        'retrieve': 'purchases.manage_payables',
        'pay': 'purchases.manage_payables',
        'cancel': 'purchases.manage_payables',
    }

    def get_queryset(self):
        queryset = PayableInstallment.objects.select_related(
            'purchase_order__branch', 'purchase_order__company', 'supplier',
            'paid_by', 'cancelled_by',
        ).filter(
            purchase_order__branch__in=_scoped_branches(
                self.request, 'purchases.manage_payables'
            )
        )
        for parameter, field in (
            ('status', 'status'), ('supplier', 'supplier_id'),
            ('purchase_order', 'purchase_order_id'),
        ):
            if self.request.query_params.get(parameter):
                queryset = queryset.filter(**{field: self.request.query_params[parameter]})
        return queryset

    @action(detail=True, methods=('post',))
    def pay(self, request, pk=None):
        serializer = PayInstallmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = pay_installment(
            installment=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=('post',))
    def cancel(self, request, pk=None):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = cancel_installment(
            installment=self.get_object(), user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(self.get_serializer(item).data)
