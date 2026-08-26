from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.base.audit import audit_log, model_snapshot
from apps.cash.models import CashSession, CashSessionStatus
from apps.companies.selectors import eligible_branch_users, user_has_branch_permission
from apps.sales.models import PaymentMethod
from apps.sales.serializers import CalculationOutputSerializer, SaleUserOptionSerializer
from apps.sales.services import calculate_command_preview
from .models import Command, CommandStatus, OrderItem, Table, TableStatus
from .permissions import CommandFunctionalPermission
from .serializers import (
    BatchTableSerializer, CancelOrderItemSerializer, CommandCalculationSerializer,
    CommandSerializer, ConfirmOrderItemSerializer, CreateOrderItemSerializer,
    FinalizeCommandSerializer, OpenCommandSerializer, OperationalTableSerializer,
    OrderItemSerializer, TableSerializer,
)
from .services import (
    add_order_item, batch_create_tables, cancel_order_item, confirm_order_item,
    create_table, finalize_command, open_command,
)


class TableViewSet(viewsets.ModelViewSet):
    serializer_class = TableSerializer
    permission_classes = [CommandFunctionalPermission]
    http_method_names = ('get', 'post', 'patch', 'head', 'options')

    def get_queryset(self):
        return Table.objects.filter(branch=self.request.branch_context).select_related('branch')

    def perform_create(self, serializer):
        branch = getattr(self.request, 'branch_context', None)
        if not branch:
            raise PermissionDenied('Selecione uma filial.')
        if serializer.validated_data.get('branch') and serializer.validated_data['branch'].pk != branch.pk:
            raise PermissionDenied({'branch': 'A mesa deve pertencer à filial atual.'})
        table = create_table(
            branch=branch,
            name=serializer.validated_data['name'],
            seats=serializer.validated_data.get('seats', 0),
            user=self.request.user,
        )
        serializer.instance = table

    def perform_update(self, serializer):
        branch = getattr(self.request, 'branch_context', None)
        if branch and serializer.validated_data.get('branch') and serializer.validated_data['branch'].pk != branch.pk:
            raise PermissionDenied({'branch': 'A mesa deve pertencer à filial atual.'})
        if (
            serializer.validated_data.get('status') == TableStatus.INACTIVE
            and serializer.instance.commands.filter(status=CommandStatus.OPEN).exists()
        ):
            raise ValidationError({'status': 'Existem comandas abertas vinculadas a esta mesa.'})
        fields = ('branch_id', 'name', 'seats', 'status')
        before = model_snapshot(serializer.instance, fields)
        table = serializer.save()
        audit_log(
            actor=self.request.user, action='table.update', obj=table,
            company=table.branch.company, branch=table.branch,
            before=before, after=model_snapshot(table, fields),
        )

    @action(detail=False, methods=('post',), url_path='batch')
    def batch_create(self, request):
        serializer = BatchTableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = getattr(request, 'branch_context', None)
        if not branch:
            raise PermissionDenied('Selecione uma filial.')
        created = batch_create_tables(
            branch=branch,
            prefix=serializer.validated_data['prefix'],
            start=serializer.validated_data['start'],
            end=serializer.validated_data['end'],
            seats=serializer.validated_data.get('seats', 0),
            user=request.user,
        )
        return Response(
            {'created': len(created), 'tables': TableSerializer(created, many=True).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=('post',))
    def activate(self, request, pk=None):
        table = self.get_object()
        table.status = TableStatus.ACTIVE
        table.save(update_fields=('status', 'updated_at'))
        audit_log(
            actor=request.user, action='table.activate', obj=table,
            company=table.branch.company, branch=table.branch,
            after=model_snapshot(table, ('name', 'status')),
        )
        return Response(TableSerializer(table).data)

    @action(detail=True, methods=('post',))
    def deactivate(self, request, pk=None):
        table = self.get_object()
        if table.commands.filter(status=CommandStatus.OPEN).exists():
            raise ValidationError({'status': 'Existem comandas abertas vinculadas a esta mesa.'})
        table.status = TableStatus.INACTIVE
        table.save(update_fields=('status', 'updated_at'))
        audit_log(
            actor=request.user, action='table.deactivate', obj=table,
            company=table.branch.company, branch=table.branch,
            after=model_snapshot(table, ('name', 'status')),
        )
        return Response(TableSerializer(table).data)

    @action(detail=False, methods=('get',), url_path='operational')
    def operational(self, request):
        tables = list(self.get_queryset())
        table_ids = [table.pk for table in tables]
        money_field = DecimalField(max_digits=14, decimal_places=2)
        open_commands = Command.objects.filter(
            table_id__in=table_ids, status=CommandStatus.OPEN
        ).annotate(
            open_items_count=Count(
                'orders__items', filter=Q(orders__items__status='pending')
            ),
            confirmed_total=Coalesce(
                Sum(
                    F('orders__items__unit_price') * F('orders__items__quantity'),
                    filter=Q(orders__items__status='confirmed'), output_field=money_field,
                ),
                Value(Decimal('0.00'), output_field=money_field),
            ),
        ).order_by('table_id', 'created_at', 'id')
        by_table = {table_id: [] for table_id in table_ids}
        for command in open_commands:
            by_table[command.table_id].append(command)
        for table in tables:
            commands = by_table[table.pk]
            table.open_commands = commands
            table.open_commands_count = len(commands)
            table.open_commands_total = sum(
                (command.confirmed_total for command in commands), Decimal('0.00')
            )
        return Response(OperationalTableSerializer(tables, many=True).data)


class CommandViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CommandSerializer
    permission_classes = [CommandFunctionalPermission]
    http_method_names = ('get', 'post', 'head', 'options')

    def get_queryset(self):
        money_field = DecimalField(max_digits=14, decimal_places=2)
        return Command.objects.filter(branch=self.request.branch_context).select_related(
            'company', 'branch', 'table', 'opened_by', 'closed_by', 'sale'
        ).annotate(
            open_items_count=Count('orders__items', filter=Q(orders__items__status='pending')),
            confirmed_total=Coalesce(
                Sum(
                    F('orders__items__unit_price') * F('orders__items__quantity'),
                    filter=Q(orders__items__status='confirmed'), output_field=money_field,
                ),
                Value(Decimal('0.00'), output_field=money_field),
            ),
        )

    @action(detail=False, methods=('post',))
    def open(self, request):
        branch = getattr(request, 'branch_context', None)
        if not branch:
            raise PermissionDenied('Selecione uma filial.')
        serializer = OpenCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        table_id = serializer.validated_data.get('table')
        table = None
        if table_id:
            table = Table.objects.filter(pk=table_id, branch=branch).first()
            if not table:
                raise ValidationError({'table': 'Mesa não encontrada nesta filial.'})
        command = open_command(
            branch=branch, user=request.user, table=table,
            identifier=serializer.validated_data['identifier'],
            support_session=getattr(request, 'support_session', None),
        )
        return Response(self.get_serializer(command).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=('get',), url_path='open-list')
    def open_list(self, request):
        commands = self.get_queryset().filter(status=CommandStatus.OPEN)
        page = self.paginate_queryset(commands)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(commands, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=('post',), url_path='add-item')
    def add_item(self, request, pk=None):
        command = self.get_object()
        serializer = CreateOrderItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = add_order_item(
            command=command, user=request.user,
            support_session=getattr(request, 'support_session', None),
            product_id=serializer.validated_data['product'],
            quantity=serializer.validated_data['quantity'],
            modifiers=serializer.validated_data['modifiers'],
        )
        return Response(OrderItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=('post',), url_path='add-items')
    @transaction.atomic
    def add_items(self, request, pk=None):
        command = self.get_object()
        items_data = request.data.get('items', [])
        if not items_data:
            raise ValidationError({'items': 'Informe ao menos um item.'})
        results = []
        order = None
        for entry in items_data:
            serializer = CreateOrderItemSerializer(data=entry)
            serializer.is_valid(raise_exception=True)
            item = add_order_item(
                command=command, user=request.user,
                support_session=getattr(request, 'support_session', None),
                order=order,
                product_id=serializer.validated_data['product'],
                quantity=serializer.validated_data['quantity'],
                modifiers=serializer.validated_data['modifiers'],
            )
            if order is None:
                order = item.order
            results.append(item)
        return Response(
            OrderItemSerializer(results, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=('post',), url_path='finalize')
    def finalize(self, request, pk=None):
        command = self.get_object()
        serializer = FinalizeCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = finalize_command(
            command=command, user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(self.get_serializer(result).data)

    @action(detail=True, methods=('post',), url_path='calculate')
    def calculate(self, request, pk=None):
        command = self.get_object()
        if command.status != CommandStatus.OPEN:
            raise ValidationError({'command': 'A comanda deve estar aberta.'})
        serializer = CommandCalculationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        seller_user = None
        seller_id = serializer.validated_data.get('seller_user')
        if seller_id:
            seller_user = eligible_branch_users(command.branch, 'sales.create').filter(
                pk=seller_id
            ).first()
            if not seller_user:
                raise ValidationError({'seller_user': 'Atendente sem acesso ativo à filial.'})
        confirmed_items = list(OrderItem.objects.filter(
            order__command=command, status='confirmed'
        ).select_related('product__category').order_by('id'))
        if not confirmed_items:
            raise ValidationError({'items': 'A comanda não possui itens confirmados.'})
        result = calculate_command_preview(
            branch=command.branch, order_items=confirmed_items,
            seller_user=seller_user, discount=serializer.validated_data['discount'],
            service_fee_waived=serializer.validated_data['service_fee_waived'],
        )
        output = CalculationOutputSerializer(data=result)
        output.is_valid(raise_exception=True)
        request.audit_fallback_suppressed = True
        response_data = dict(output.data)
        if not (
            request.user.is_superuser
            or user_has_branch_permission(request.user, command.branch_id, 'commissions.view')
        ):
            response_data.pop('commission_rate', None)
            response_data.pop('commission_amount', None)
        return Response(response_data)

    @action(detail=False, methods=('get',), url_path='checkout-options')
    def checkout_options(self, request):
        methods = PaymentMethod.objects.filter(
            company_id=request.branch_context.company_id, status='active'
        ).order_by('name', 'id').values('id', 'code', 'name', 'status', 'is_system')
        sessions = CashSession.objects.filter(
            branch=request.branch_context, status=CashSessionStatus.OPEN
        ).select_related('cash_register', 'opened_by').order_by('id')
        return Response({
            'payment_methods': list(methods),
            'cash_sessions': [
                {
                    'id': session.pk,
                    'register_name': session.cash_register.name,
                    'opened_by_name': session.opened_by.get_full_name().strip()
                    or session.opened_by.email,
                }
                for session in sessions
            ],
        })

    @action(detail=False, methods=('get',))
    def sellers(self, request):
        return Response(SaleUserOptionSerializer(
            eligible_branch_users(request.branch_context, 'sales.create'), many=True
        ).data)

    @action(detail=False, methods=('get',), url_path='discount-authorizers')
    def discount_authorizers(self, request):
        return Response(SaleUserOptionSerializer(
            eligible_branch_users(request.branch_context, 'sales.apply_discount'), many=True
        ).data)

    @action(detail=False, methods=('get',), url_path='service-fee-authorizers')
    def service_fee_authorizers(self, request):
        return Response(SaleUserOptionSerializer(
            eligible_branch_users(request.branch_context, 'sales.waive_service_fee'), many=True
        ).data)


class OrderItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderItemSerializer
    permission_classes = [CommandFunctionalPermission]
    http_method_names = ('get', 'post', 'head', 'options')

    def get_queryset(self):
        queryset = OrderItem.objects.filter(
            order__command__branch=self.request.branch_context
        ).select_related('order__command', 'product', 'confirmed_by', 'cancelled_by')
        command_id = self.request.query_params.get('order__command')
        if command_id:
            queryset = queryset.filter(order__command_id=command_id)
        return queryset

    @action(detail=True, methods=('post',), url_path='confirm')
    def confirm(self, request, pk=None):
        item = self.get_object()
        serializer = ConfirmOrderItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = confirm_order_item(
            item=item, user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(OrderItemSerializer(result).data)

    @action(detail=True, methods=('post',), url_path='cancel')
    def cancel(self, request, pk=None):
        item = self.get_object()
        serializer = CancelOrderItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = cancel_order_item(
            item=item, user=request.user,
            support_session=getattr(request, 'support_session', None),
            **serializer.validated_data,
        )
        return Response(OrderItemSerializer(result).data)
