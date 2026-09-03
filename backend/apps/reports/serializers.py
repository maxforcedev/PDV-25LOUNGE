from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from apps.accounts.models import User
from apps.base.constants import MAX_BIGINT
from apps.cash.models import CashRegister, CashSession, CashSessionStatus, WithdrawalCategory
from apps.cash.services import redact_operational_summary, session_operational_summary
from apps.companies.models import Customer
from apps.commands.models import CommandPayment, CommandStatus, OrderItem, Table
from apps.inventory.models import (
    InventoryCountStatus,
    MovementType,
    StockTransferStatus,
    TransferResolutionType,
)
from apps.inventory.content import content_breakdown
from apps.inventory.serializers import StockMovementSerializer
from apps.products.models import Category, Product, SalesChannel
from apps.sales.models import OperationType, Payment, PaymentMethod, Sale, SaleItem, SaleStatus
from apps.sales.serializers import readable_user_name
from apps.suppliers.models import Supplier
from apps.purchases.models import (
    PayableInstallmentStatus,
    PurchaseOrderStatus,
    PurchaseOrderType,
)


class BaseReportQuerySerializer(serializers.Serializer):
    start_datetime = serializers.CharField(max_length=64, required=False)
    end_datetime = serializers.CharField(max_length=64, required=False)
    export = serializers.ChoiceField(choices=('csv', 'xlsx', 'pdf'), required=False)
    page = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=200, required=False)

    def validate_scoped_ids(self, attrs, fields):
        request = self.context['request']
        branch = request.branch_context
        querysets = {
            'operator': User.objects.filter(
                company_accesses__company_id=branch.company_id,
            ),
            'seller': User.objects.filter(
                branch_accesses__branch=branch,
            ),
            'beneficiary': User.objects.filter(
                company_accesses__company_id=branch.company_id,
            ),
            'user': User.objects.filter(
                company_accesses__company_id=branch.company_id,
            ),
            'responsible': User.objects.filter(
                company_accesses__company_id=branch.company_id,
            ),
            'product': Product.objects.filter(company_id=branch.company_id),
            'category': Category.objects.filter(branch=branch),
            'payment_method': PaymentMethod.objects.filter(company_id=branch.company_id),
            'cash_register': CashRegister.objects.filter(branch=branch),
            'cash_session': CashSession.objects.filter(branch=branch),
            'customer': Customer.objects.filter(company_id=branch.company_id),
            'supplier': Supplier.objects.filter(branch=branch),
            'table': Table.objects.filter(branch=branch),
        }
        errors = {}
        for field in fields:
            value = attrs.get(field)
            if value is not None and not querysets[field].filter(pk=value).exists():
                errors[field] = 'Identificador inválido para a filial atual.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class SalesReportQuerySerializer(BaseReportQuerySerializer):
    operator = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    seller = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    payment_method = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    payment_method_code = serializers.CharField(max_length=50, required=False)
    weekday = serializers.IntegerField(min_value=0, max_value=6, required=False)
    hour = serializers.IntegerField(min_value=0, max_value=23, required=False)
    status = serializers.ChoiceField(choices=SaleStatus.values, required=False)
    search = serializers.CharField(max_length=200, required=False, allow_blank=False)
    number = serializers.CharField(max_length=20, required=False, allow_blank=False)
    channel = serializers.ChoiceField(choices=SalesChannel.values, required=False)
    customer = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    minimum_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00'), required=False,
    )
    maximum_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00'), required=False,
    )

    def validate(self, attrs):
        attrs = self.validate_scoped_ids(
            attrs, (
                'operator', 'seller', 'product', 'category', 'payment_method',
                'customer',
            )
        )
        if (
            attrs.get('minimum_value') is not None
            and attrs.get('maximum_value') is not None
            and attrs['minimum_value'] > attrs['maximum_value']
        ):
            raise serializers.ValidationError({
                'maximum_value': 'O valor máximo deve ser maior ou igual ao mínimo.'
            })
        code = attrs.get('payment_method_code')
        if code and not PaymentMethod.objects.filter(
            company_id=self.context['request'].branch_context.company_id,
            code=code,
        ).exists():
            raise serializers.ValidationError({
                'payment_method_code': 'Forma de pagamento inválida para a empresa atual.'
            })
        return attrs


class OperationalResultQuerySerializer(BaseReportQuerySerializer):
    cash_session = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('cash_session',))


class ConsumptionsReportQuerySerializer(BaseReportQuerySerializer):
    beneficiary = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    user_type = serializers.ChoiceField(choices=User.UserType.values, required=False)
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    status = serializers.ChoiceField(choices=SaleStatus.values, required=False)
    channel = serializers.ChoiceField(choices=SalesChannel.values, required=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(
            attrs, ('beneficiary', 'product', 'category')
        )


class CashReportQuerySerializer(BaseReportQuerySerializer):
    cash_register = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    operator = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    status = serializers.ChoiceField(choices=CashSessionStatus.values, required=False)
    section = serializers.ChoiceField(
        choices=('sessions', 'movements'), required=False,
    )

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('cash_register', 'operator'))


class WithdrawalsReportQuerySerializer(BaseReportQuerySerializer):
    category = serializers.ChoiceField(choices=WithdrawalCategory.values, required=False)
    beneficiary = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    operator = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    cash_register = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(
            attrs, ('beneficiary', 'operator', 'cash_register')
        )


class InventoryReportQuerySerializer(BaseReportQuerySerializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    movement_type = serializers.ChoiceField(choices=MovementType.values, required=False)
    user = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('product', 'category', 'user'))


class StockConsumptionReportQuerySerializer(BaseReportQuerySerializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    origin = serializers.ChoiceField(
        choices=('sale', 'consumption', 'manual_exit', 'reversal'), required=False,
    )

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('product', 'category'))


class StockPositionReportQuerySerializer(BaseReportQuerySerializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    state = serializers.ChoiceField(
        choices=(
            'normal', 'below_minimum', 'zero', 'negative',
            'archived_with_stock',
        ),
        required=False,
    )
    search = serializers.CharField(max_length=200, required=False, allow_blank=False)
    ordering = serializers.ChoiceField(
        choices=('product', '-product', 'balance', '-balance'), required=False,
    )

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('product', 'category'))


class InventoryCountsReportQuerySerializer(BaseReportQuerySerializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    responsible = serializers.IntegerField(
        min_value=1, max_value=MAX_BIGINT, required=False,
    )
    status = serializers.ChoiceField(choices=InventoryCountStatus.values, required=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(
            attrs, ('product', 'category', 'responsible')
        )


class StockTransfersReportQuerySerializer(BaseReportQuerySerializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    responsible = serializers.IntegerField(
        min_value=1, max_value=MAX_BIGINT, required=False,
    )
    status = serializers.ChoiceField(choices=StockTransferStatus.values, required=False)
    direction = serializers.ChoiceField(
        choices=('incoming', 'outgoing'), required=False,
    )

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('product', 'responsible'))


class PurchaseReportQuerySerializer(BaseReportQuerySerializer):
    supplier = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    status = serializers.ChoiceField(choices=PurchaseOrderStatus.values, required=False)
    order_type = serializers.ChoiceField(choices=PurchaseOrderType.values, required=False)
    search = serializers.CharField(max_length=200, required=False, allow_blank=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('supplier', 'product'))


class SupplierReportQuerySerializer(BaseReportQuerySerializer):
    supplier = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    status = serializers.ChoiceField(choices=('active', 'inactive'), required=False)
    search = serializers.CharField(max_length=200, required=False, allow_blank=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('supplier',))


class PayablesReportQuerySerializer(BaseReportQuerySerializer):
    supplier = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    status = serializers.ChoiceField(
        choices=PayableInstallmentStatus.values, required=False,
    )
    date_basis = serializers.ChoiceField(
        choices=('due_date', 'settlement_date'), required=False, default='due_date',
    )
    search = serializers.CharField(max_length=200, required=False, allow_blank=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(attrs, ('supplier',))


class CommandsReportQuerySerializer(BaseReportQuerySerializer):
    section = serializers.ChoiceField(
        choices=('commands', 'items', 'payments', 'cancellations', 'operations'),
        required=False, default='commands',
    )
    status = serializers.ChoiceField(choices=CommandStatus.values, required=False)
    table = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    customer = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    operator = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    payment_method = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    command = serializers.CharField(max_length=100, required=False, allow_blank=False)

    def validate(self, attrs):
        return self.validate_scoped_ids(
            attrs, ('table', 'customer', 'operator', 'payment_method')
        )


class ReportSaleItemSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()
    cost_total = serializers.SerializerMethodField()
    margin_amount = serializers.SerializerMethodField()
    margin_percentage = serializers.SerializerMethodField()
    discount_approved_by = serializers.SerializerMethodField()
    commercial_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, source='subtotal', read_only=True,
    )
    charged_value = serializers.SerializerMethodField()
    subsidy_value = serializers.SerializerMethodField()
    commission_amount = serializers.SerializerMethodField()

    class Meta:
        model = SaleItem
        fields = (
            'id', 'product', 'product_name', 'internal_code', 'unit', 'quantity', 'unit_price',
            'base_unit_price', 'modifier_unit_total', 'modifier_snapshot', 'category',
            'subtotal', 'promotion', 'promotion_name', 'promotion_discount_type',
            'promotion_discount_value', 'promotion_benefit', 'manual_discount',
            'discount_approved_by',
            'commercial_value', 'charged_value', 'subsidy_value',
            'commission_amount',
            'net_subtotal', 'unit_cost', 'cost_total', 'margin_amount',
            'margin_percentage',
            'participates_in_service_fee', 'participates_in_commission',
        )

    def get_category(self, item):
        return {
            'id': item.category_id_snapshot,
            'name': item.category_name_snapshot or 'Sem categoria',
            'historical': True,
        }

    @staticmethod
    def get_cost_total(item):
        return f'{item.unit_cost * item.quantity:.2f}'

    def get_margin_amount(self, item):
        return f'{item.net_subtotal - item.unit_cost * item.quantity:.2f}'

    def get_margin_percentage(self, item):
        if not item.net_subtotal:
            return '0.00'
        margin = item.net_subtotal - item.unit_cost * item.quantity
        return f'{margin * Decimal("100") / item.net_subtotal:.2f}'

    def get_discount_approved_by(self, item):
        if item.discount_approved_by is None:
            return None
        return {
            'id': item.discount_approved_by_id,
            'name': readable_user_name(item.discount_approved_by),
        }

    def get_charged_value(self, item):
        if item.sale.operation_type != OperationType.CONSUMPTION:
            return f'{item.net_subtotal:.2f}'
        from .financials import allocate_money

        items = sorted(item.sale.items.all(), key=lambda row: row.pk)
        allocated = allocate_money(
            item.sale.total, [(row.pk, row.subtotal) for row in items]
        )
        return f'{allocated[item.pk]:.2f}'

    def get_subsidy_value(self, item):
        return f'{item.subtotal - Decimal(self.get_charged_value(item)):.2f}'

    def get_commission_amount(self, item):
        from .financials import FinancialAggregator

        if not hasattr(item.sale, '_report_item_commissions'):
            item.sale._report_item_commissions = {
                value['item'].pk: value['commission']
                for value in FinancialAggregator([item.sale]).item_rows(item.sale)
            }
        return f'{item.sale._report_item_commissions[item.pk]:.2f}'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        can_view_cost = bool(request and request.user.is_superuser)
        if request and branch and not request.user.is_superuser:
            from apps.companies.selectors import user_has_branch_permission

            can_view_cost = user_has_branch_permission(
                request.user, branch.pk, 'inventory.view_stock_costs'
            )
        if not can_view_cost:
            for key in ('unit_cost', 'cost_total', 'margin_amount', 'margin_percentage'):
                data.pop(key, None)
        can_view_commission = bool(request and request.user.is_superuser)
        if request and branch and not request.user.is_superuser:
            from apps.companies.selectors import user_has_branch_permission

            can_view_commission = user_has_branch_permission(
                request.user, branch.pk, 'commissions.view'
            )
        if not can_view_commission:
            data.pop('commission_amount', None)
        return data


class ReportPaymentSerializer(serializers.ModelSerializer):
    applied_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, source='amount', read_only=True,
    )
    occurred_at = serializers.SerializerMethodField()
    origin = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            'payment_method', 'payment_method_name', 'payment_method_code', 'amount',
            'applied_amount', 'received_amount', 'change_amount', 'occurred_at',
            'origin', 'operator', 'status',
        )

    def get_occurred_at(self, payment):
        return payment.occurred_at or payment.created_at

    def get_origin(self, payment):
        return 'command' if payment.source_command_payment_id else 'direct_sale'

    def get_operator(self, payment):
        source = payment.source_command_payment
        user = source.operator if source else payment.sale.created_by
        return {'id': user.pk, 'name': readable_user_name(user)}

    @staticmethod
    def get_status(payment):
        return 'applied'


class PaymentEventReportSerializer(serializers.Serializer):
    event_id = serializers.CharField()
    occurred_at = serializers.DateTimeField()
    status = serializers.CharField()
    is_reversal = serializers.BooleanField()
    applied_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    received_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    change_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    origin = serializers.CharField()
    operator = serializers.DictField(allow_null=True)
    payment_method = serializers.DictField()
    sale = serializers.DictField(allow_null=True)
    command = serializers.DictField(allow_null=True)
    cash_session = serializers.DictField(allow_null=True)
    cash_register = serializers.DictField(allow_null=True)
    reversal_reason = serializers.CharField(allow_blank=True)


class ReportSaleSerializer(serializers.ModelSerializer):
    operation_id = serializers.IntegerField(source='id', read_only=True)
    operation_key = serializers.SerializerMethodField()
    event_type = serializers.SerializerMethodField()
    event_at = serializers.SerializerMethodField()
    event_sign = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    seller = serializers.SerializerMethodField()
    discount_approved_by = serializers.SerializerMethodField()
    beneficiary = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    cash_session = serializers.SerializerMethodField()
    cancelled_by = serializers.SerializerMethodField()
    service_fee_waived_by = serializers.SerializerMethodField()
    service_fee_waived_value = serializers.SerializerMethodField()
    items = ReportSaleItemSerializer(many=True, read_only=True)
    payments = ReportPaymentSerializer(many=True, read_only=True)
    sales_revenue = serializers.SerializerMethodField()
    consumption_charged = serializers.SerializerMethodField()
    effective_revenue = serializers.SerializerMethodField()
    service_fee = serializers.DecimalField(
        max_digits=14, decimal_places=2, source='service_fee_amount', read_only=True
    )
    total_received = serializers.DecimalField(
        max_digits=14, decimal_places=2, source='total', read_only=True
    )
    payment_total = serializers.SerializerMethodField()
    reconciliation_delta = serializers.SerializerMethodField()
    total_received_sales = serializers.SerializerMethodField()
    customer_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, source='total', read_only=True
    )
    payment_reconciliation_delta = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = (
            'id', 'operation_id', 'operation_key', 'event_type', 'event_at', 'event_sign', 'sale_number',
            'operation_type', 'channel', 'status', 'operator', 'seller',
            'discount_approved_by', 'beneficiary', 'customer', 'cash_session', 'subtotal',
            'promotion_discount_total', 'item_discount_total', 'discount', 'service_fee_rate',
            'service_fee_amount', 'service_fee_waived', 'service_fee_waived_by',
            'service_fee_waived_value',
            'commission_rate', 'commission_amount', 'total', 'created_at',
            'sales_revenue', 'consumption_charged', 'effective_revenue', 'service_fee',
            'total_received', 'payment_total', 'reconciliation_delta',
            'payment_reconciliation_delta',
            'total_received_sales', 'customer_total', 'cancelled_at', 'cancelled_by',
            'cancellation_reason', 'items', 'payments',
        )

    def get_event_type(self, sale):
        return getattr(sale, '_report_event_type', 'record')

    def get_operation_key(self, sale):
        # A sale can be represented by more than one report event (for example,
        # its original record and its reversal), so the event is part of the UI key.
        return f'{sale.operation_type}:{sale.pk}:{self.get_event_type(sale)}'

    def get_event_at(self, sale):
        value = getattr(sale, '_report_event_at', sale.created_at)
        return serializers.DateTimeField().to_representation(value)

    def get_event_sign(self, sale):
        return getattr(sale, '_report_event_sign', 1)

    def get_sales_revenue(self, sale):
        value = sale.total - sale.service_fee_amount if sale.operation_type == OperationType.SALE else 0
        return f'{value:.2f}'

    def get_consumption_charged(self, sale):
        value = sale.total if sale.operation_type == OperationType.CONSUMPTION else 0
        return f'{value:.2f}'

    def get_effective_revenue(self, sale):
        return f'{sale.total - sale.service_fee_amount:.2f}' if sale.operation_type == OperationType.SALE else f'{sale.total:.2f}'

    def get_payment_total(self, sale):
        return f'{sum((payment.amount for payment in sale.payments.all()), 0):.2f}'

    def get_reconciliation_delta(self, sale):
        received = sum((payment.amount for payment in sale.payments.all()), 0)
        return f'{received - sale.total:.2f}'

    def get_total_received_sales(self, sale):
        return self.get_payment_total(sale)

    def get_payment_reconciliation_delta(self, sale):
        received = sum((payment.amount for payment in sale.payments.all()), 0)
        return f'{received - sale.total:.2f}'

    def get_operator(self, sale):
        return {'id': sale.created_by_id, 'name': readable_user_name(sale.created_by)}

    def get_seller(self, sale):
        if sale.seller_user is None:
            return None
        return {'id': sale.seller_user_id, 'name': readable_user_name(sale.seller_user)}

    def get_discount_approved_by(self, sale):
        if sale.discount_approved_by is None:
            return None
        return {
            'id': sale.discount_approved_by_id,
            'name': readable_user_name(sale.discount_approved_by),
        }

    def get_beneficiary(self, sale):
        if sale.beneficiary_user is None:
            return None
        return {
            'id': sale.beneficiary_user_id,
            'name': readable_user_name(sale.beneficiary_user),
            'user_type': sale.beneficiary_user.user_type,
        }

    def get_customer(self, sale):
        if sale.customer is None:
            return None
        return {
            'id': sale.customer_id,
            'name': sale.customer.name,
            'document': sale.customer.document,
            'phone': sale.customer.phone,
        }

    def get_cash_session(self, sale):
        if sale.cash_session is None:
            return None
        return {
            'id': sale.cash_session_id,
            'status': sale.cash_session.status,
            'register': {
                'id': sale.cash_session.cash_register_id,
                'name': sale.cash_session.cash_register.name,
            },
        }

    def get_cancelled_by(self, sale):
        if sale.cancelled_by is None:
            return None
        return {
            'id': sale.cancelled_by_id,
            'name': readable_user_name(sale.cancelled_by),
        }

    def get_service_fee_waived_by(self, sale):
        if sale.service_fee_waived_by is None:
            return None
        return {
            'id': sale.service_fee_waived_by_id,
            'name': readable_user_name(sale.service_fee_waived_by),
        }

    def get_service_fee_waived_value(self, sale):
        if not sale.service_fee_waived or not sale.service_fee_rate:
            return '0.00'
        eligible = sum((
            item.net_subtotal for item in sale.items.all()
            if item.participates_in_service_fee
        ), Decimal('0.00'))
        return f'{eligible * sale.service_fee_rate / Decimal("100"):.2f}'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if request and (request.query_params.get('product') or request.query_params.get('category')):
            from .selectors import (
                _scoped_consumption_values, _scoped_payment_rows, _scoped_sale_values,
            )

            filters = {}
            for key in ('product', 'category'):
                try:
                    if request.query_params.get(key):
                        filters[key] = int(request.query_params[key])
                except (TypeError, ValueError):
                    pass
            if instance.operation_type == OperationType.CONSUMPTION:
                scoped = _scoped_consumption_values(instance, filters)
                data.update({
                    'subtotal': f"{scoped['reference']:.2f}",
                    'promotion_discount_total': '0.00',
                    'item_discount_total': '0.00',
                    'discount': '0.00',
                    'service_fee_amount': '0.00',
                    'service_fee': '0.00',
                    'commission_amount': '0.00',
                    'total': f"{scoped['total_received']:.2f}",
                    'sales_revenue': '0.00',
                    'consumption_charged': f"{scoped['consumption_charged']:.2f}",
                    'effective_revenue': f"{scoped['effective_revenue']:.2f}",
                    'total_received': f"{scoped['total_received']:.2f}",
                    'customer_total': f"{scoped['total_received']:.2f}",
                })
            else:
                scoped = _scoped_sale_values(instance, filters)
                data.update({
                    'subtotal': f"{scoped['gross']:.2f}",
                    'promotion_discount_total': f"{scoped['promotion_discount']:.2f}",
                    'item_discount_total': f"{scoped['item_discount']:.2f}",
                    'discount': f"{scoped['account_discount']:.2f}",
                    'service_fee_amount': f"{scoped['service_fee']:.2f}",
                    'service_fee': f"{scoped['service_fee']:.2f}",
                    'commission_amount': f"{scoped['commission']:.2f}",
                    'total': f"{scoped['total_received']:.2f}",
                    'sales_revenue': f"{scoped['sales_revenue']:.2f}",
                    'consumption_charged': '0.00',
                    'effective_revenue': f"{scoped['effective_revenue']:.2f}",
                    'total_received': f"{scoped['total_received']:.2f}",
                    'customer_total': f"{scoped['total_received']:.2f}",
                })
            category_by_id = {
                item.pk: item.category_id_snapshot for item in instance.items.all()
            }
            data['items'] = [
                item for item in data['items']
                if (
                    filters.get('product') is None
                    or item['product'] == filters['product']
                ) and (
                    filters.get('category') is None
                    or category_by_id[item['id']] == filters['category']
                )
            ]
            data['payments'] = [
                {
                    'payment_method': payment['payment_method_id'],
                    'payment_method_name': payment['payment_method_name'],
                    'payment_method_code': payment['payment_method_code'],
                    'amount': f"{payment['amount']:.2f}",
                }
                for payment in _scoped_payment_rows(instance, filters)
                if payment['amount']
            ]
            received = sum((Decimal(payment['amount']) for payment in data['payments']), Decimal('0.00'))
            data['payment_total'] = f'{received:.2f}'
            data['reconciliation_delta'] = f"{received - scoped['total_received']:.2f}"
            data['total_received_sales'] = f'{received:.2f}'
            data['payment_reconciliation_delta'] = (
                f"{received - scoped['total_received']:.2f}"
            )
        for payment in data['payments']:
            payment.pop('payment_method', None)
        if request and branch and not request.user.is_superuser:
            from apps.companies.selectors import user_has_branch_permission

            if not user_has_branch_permission(request.user, branch.pk, 'commissions.view'):
                data.pop('commission_rate', None)
                data.pop('commission_amount', None)
        if data['event_sign'] < 0:
            for key in (
                'subtotal', 'promotion_discount_total', 'item_discount_total',
                'discount', 'service_fee_amount', 'commission_amount', 'total',
                'sales_revenue', 'consumption_charged', 'effective_revenue',
                'service_fee', 'total_received', 'payment_total',
                'total_received_sales', 'customer_total',
            ):
                if data.get(key) not in (None, ''):
                    data[key] = f'{-Decimal(data[key]):.2f}'
            data['reconciliation_delta'] = f'{-Decimal(data["reconciliation_delta"]):.2f}'
            data['payment_reconciliation_delta'] = data['reconciliation_delta']
            for payment in data['payments']:
                payment['amount'] = f'{-Decimal(payment["amount"]):.2f}'
            for item in data['items']:
                item['quantity'] = f'{-Decimal(item["quantity"]):.3f}'
                for key in (
                    'subtotal', 'promotion_benefit', 'manual_discount', 'net_subtotal',
                ):
                    item[key] = f'{-Decimal(item[key]):.2f}'
        return data


class CancellationReportSerializer(serializers.Serializer):
    def to_representation(self, instance):
        if isinstance(instance, Sale):
            data = ReportSaleSerializer(instance, context=self.context).data
            data.update({
                'event_id': f'sale:{instance.pk}:cancelled',
                'event_type': 'sale_cancellation',
                'cancelled_at': instance.cancelled_at,
                'operation_id': instance.pk,
                'operation_number': instance.sale_number,
                'operation_type': instance.operation_type,
                'cancellation_kind': 'sale',
                'cancellation_actor': data.get('cancelled_by'),
                'cancellation_impact': f'{instance.total:.2f}',
                'financial_impact': f'{instance.total:.2f}',
                'stock_impact': 'Itens da venda revertidos ao estoque conforme configuração',
                'reason': instance.cancellation_reason,
                'reversed_amount': f'{sum((row.amount for row in instance.payments.all()), Decimal("0.00")):.2f}',
                'reference': instance.sale_number,
            })
            return data
        if isinstance(instance, OrderItem):
            command = instance.order.command
            return {
                'id': f'order-item:{instance.pk}',
                'event_id': f'order-item:{instance.pk}',
                'cancelled_at': instance.cancelled_at,
                'operation_id': command.pk,
                'operation_number': command.command_number,
                'operation_type': 'command',
                'cancellation_kind': 'command_item',
                'event_type': 'item_cancellation',
                'event_at': instance.cancelled_at,
                'status': instance.status,
                'reference': command.command_number,
                'command': {
                    'id': command.pk,
                    'number': command.command_number,
                    'table': ({'id': command.table_id, 'name': command.table.name}
                              if command.table_id else None),
                },
                'product': {
                    'id': instance.product_id,
                    'name': instance.product_name,
                    'internal_code': instance.internal_code,
                },
                'quantity': f'{instance.quantity:.3f}',
                'cancellation_actor': ({
                    'id': instance.cancelled_by_id,
                    'name': readable_user_name(instance.cancelled_by),
                } if instance.cancelled_by else None),
                'cancellation_reason': instance.cancellation_reason,
                'reason': instance.cancellation_reason,
                'cancellation_impact': f'{instance.quantity * instance.unit_price:.2f}',
                'financial_impact': f'{instance.quantity * instance.unit_price:.2f}',
                'stock_impact': 'Quantidade do item cancelado',
                'reversed_amount': '0.00',
            }
        payment = instance
        command = payment.command
        return {
            'id': f'command-payment:{payment.pk}',
            'event_id': f'command-payment:{payment.pk}',
            'cancelled_at': payment.created_at,
            'operation_id': command.pk,
            'operation_number': command.command_number,
            'operation_type': 'command',
            'cancellation_kind': 'payment_reversal',
            'event_type': 'payment_reversal',
            'event_at': payment.created_at,
            'status': payment.status,
            'reference': command.command_number,
            'command': {
                'id': command.pk,
                'number': command.command_number,
                'table': ({'id': command.table_id, 'name': command.table.name}
                          if command.table_id else None),
            },
            'payment_method': {
                'id': payment.payment_method_id,
                'code': payment.payment_method.code,
                'name': payment.payment_method.name,
            },
            'cancellation_actor': ({
                'id': payment.operator_id,
                'name': readable_user_name(payment.operator),
            } if payment.operator else None),
            'cancellation_reason': payment.reversal_reason,
            'reason': payment.reversal_reason,
            'cancellation_impact': f'{payment.amount:.2f}',
            'financial_impact': f'{payment.amount:.2f}',
            'stock_impact': 'Sem impacto direto no estoque',
            'reversed_amount': f'{payment.amount:.2f}',
        }


class CashSessionReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    opened_at = serializers.DateTimeField()
    closed_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    register = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    operators = serializers.SerializerMethodField()
    opened_by = serializers.SerializerMethodField()
    closed_by = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()
    opening = serializers.DecimalField(max_digits=20, decimal_places=2, source='opening_amount')
    fund = serializers.DecimalField(max_digits=20, decimal_places=2, source='opening_amount')
    manual_entries = serializers.DecimalField(max_digits=20, decimal_places=2)
    entries = serializers.DecimalField(max_digits=20, decimal_places=2, source='manual_entries')
    sale_cash = serializers.DecimalField(max_digits=20, decimal_places=2)
    consumption_cash = serializers.DecimalField(max_digits=20, decimal_places=2)
    cash_reversals = serializers.DecimalField(max_digits=20, decimal_places=2)
    cash_cancellations = serializers.IntegerField()
    cash_payments = serializers.DecimalField(max_digits=20, decimal_places=2)
    withdrawals = serializers.DecimalField(max_digits=20, decimal_places=2)
    expected = serializers.DecimalField(max_digits=20, decimal_places=2)
    informed = serializers.DecimalField(
        max_digits=20, decimal_places=2, source='closing_amount_informed', allow_null=True
    )
    difference = serializers.DecimalField(
        max_digits=20, decimal_places=2, source='closing_difference', allow_null=True
    )
    operational_summary = serializers.SerializerMethodField()

    def get_register(self, session):
        return {'id': session.cash_register_id, 'name': session.cash_register.name}

    def get_operator(self, session):
        return {'id': session.opened_by_id, 'name': readable_user_name(session.opened_by)}

    def get_operators(self, session):
        return getattr(session, '_report_operators', [self.get_operator(session)])

    def get_opened_by(self, session):
        return self.get_operator(session)

    def get_closed_by(self, session):
        if session.closed_by is None:
            return None
        return {'id': session.closed_by_id, 'name': readable_user_name(session.closed_by)}

    def get_duration_seconds(self, session):
        from django.utils import timezone

        end = session.closed_at or timezone.now()
        return max(0, int((end - session.opened_at).total_seconds()))

    def get_operational_summary(self, session):
        summary = session_operational_summary(session)
        request = self.context.get('request')
        include_commission = bool(request and request.user.is_superuser)
        include_costs = bool(request and request.user.is_superuser)
        if request and not request.user.is_superuser:
            from apps.companies.selectors import user_has_branch_permission

            permissions = {}
            for name, code in (
                ('commission', 'commissions.view'),
                ('costs', 'inventory.view_stock_costs'),
            ):
                cache_name = f'_report_{name}_permission_{session.branch_id}'
                if not hasattr(request, cache_name):
                    setattr(
                        request, cache_name,
                        user_has_branch_permission(request.user, session.branch_id, code),
                    )
                permissions[name] = getattr(request, cache_name)
            include_commission = permissions['commission']
            include_costs = permissions['costs']
        summary = redact_operational_summary(
            summary, include_costs=include_costs,
            include_commission=include_commission,
        )

        def serialize(value):
            from decimal import Decimal
            if isinstance(value, Decimal):
                return f'{value:.2f}'
            if isinstance(value, dict):
                return {key: serialize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [serialize(item) for item in value]
            return value
        return serialize(summary)


class CashMovementReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    movement_type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    reason = serializers.CharField()
    operator = serializers.SerializerMethodField()
    cash_session = serializers.IntegerField(source='cash_session_id')
    cash_register = serializers.SerializerMethodField()

    def get_operator(self, movement):
        return {
            'id': movement.user_id,
            'name': readable_user_name(movement.user),
        }

    def get_cash_register(self, movement):
        register = movement.cash_session.cash_register
        return {'id': register.pk, 'name': register.name}


class WithdrawalReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    category = serializers.CharField(source='withdrawal_category')
    category_label = serializers.CharField(source='get_withdrawal_category_display')
    beneficiary = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    cash_register = serializers.SerializerMethodField()
    cash_session = serializers.SerializerMethodField()
    reason = serializers.CharField()
    result_effect = serializers.CharField()

    def get_beneficiary(self, movement):
        if movement.beneficiary_user is None:
            return None
        return {'id': movement.beneficiary_user_id, 'name': readable_user_name(movement.beneficiary_user)}

    def get_operator(self, movement):
        return {'id': movement.user_id, 'name': readable_user_name(movement.user)}

    def get_cash_register(self, movement):
        register = movement.cash_session.cash_register
        return {'id': register.pk, 'name': register.name}

    def get_cash_session(self, movement):
        return {
            'id': movement.cash_session_id,
            'status': movement.cash_session.status,
            'opened_at': movement.cash_session.opened_at,
            'closed_at': movement.cash_session.closed_at,
        }


class InventoryMovementReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    movement_type = serializers.CharField()
    nature = serializers.CharField()
    operation_reference = serializers.UUIDField()
    domain_origin = serializers.CharField()
    origin = serializers.SerializerMethodField()
    product = serializers.SerializerMethodField()
    unit = serializers.CharField(source='stock.product.unit')
    previous_quantity = serializers.DecimalField(max_digits=24, decimal_places=9)
    quantity = serializers.DecimalField(max_digits=24, decimal_places=9)
    final_quantity = serializers.DecimalField(max_digits=24, decimal_places=9)
    previous_content = serializers.DecimalField(
        max_digits=24, decimal_places=9, allow_null=True
    )
    content_quantity = serializers.DecimalField(
        max_digits=24, decimal_places=9, allow_null=True
    )
    final_content = serializers.DecimalField(
        max_digits=24, decimal_places=9, allow_null=True
    )
    equivalent_quantity = serializers.SerializerMethodField()
    legacy_equivalent_quantity = serializers.SerializerMethodField()
    exact_content_equivalent_quantity = serializers.SerializerMethodField()
    package_content = serializers.SerializerMethodField()
    content_unit = serializers.SerializerMethodField()
    complete_packages = serializers.SerializerMethodField()
    residual_content = serializers.SerializerMethodField()
    reason = serializers.CharField()
    user = serializers.SerializerMethodField()
    sale = serializers.SerializerMethodField()
    unit_cost_snapshot = serializers.DecimalField(
        max_digits=28, decimal_places=12, allow_null=True,
    )
    cost_impact = serializers.SerializerMethodField()

    def get_product(self, movement):
        product = movement.stock.product
        return {
            'id': product.pk,
            'name': product.name,
            'internal_code': product.internal_code,
            'category': {'id': product.category_id, 'name': product.category.name},
        }

    @staticmethod
    def _content_details(movement):
        if movement.content_quantity is None:
            return None
        try:
            config = movement.stock.product.fraction_config
        except ObjectDoesNotExist:
            return None
        complete, residual = content_breakdown(
            movement.content_quantity, config.package_content
        )
        return config, complete, residual

    def get_equivalent_quantity(self, movement):
        return format(movement.equivalent_quantity(), 'f')

    def get_legacy_equivalent_quantity(self, movement):
        quantity = movement.legacy_equivalent_quantity()
        return format(quantity, 'f') if quantity is not None else None

    def get_exact_content_equivalent_quantity(self, movement):
        quantity = movement.exact_content_equivalent_quantity()
        return format(quantity, 'f') if quantity is not None else None

    def get_package_content(self, movement):
        details = self._content_details(movement)
        return format(details[0].package_content, 'f') if details else None

    def get_content_unit(self, movement):
        details = self._content_details(movement)
        return details[0].content_unit if details else None

    def get_complete_packages(self, movement):
        details = self._content_details(movement)
        return format(details[1], 'f') if details else None

    def get_residual_content(self, movement):
        details = self._content_details(movement)
        return format(details[2], 'f') if details else None

    def get_user(self, movement):
        return {'id': movement.user_id, 'name': readable_user_name(movement.user)}

    def get_sale(self, movement):
        if movement.sale is None:
            return None
        return {'id': movement.sale_id, 'number': movement.sale.sale_number}

    def get_origin(self, movement):
        origin = StockMovementSerializer(context=self.context).get_origin(movement)
        if origin:
            return origin
        return {
            'kind': movement.domain_origin.lower(),
            'id': str(movement.operation_reference),
            'label': movement.get_domain_origin_display(),
        }

    def get_cost_impact(self, movement):
        if movement.unit_cost_snapshot is None:
            return None
        return f'{movement.equivalent_quantity() * movement.unit_cost_snapshot:.2f}'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        can_view_cost = bool(request and request.user.is_superuser)
        if request and not request.user.is_superuser:
            from apps.companies.selectors import user_has_branch_permission

            can_view_cost = user_has_branch_permission(
                request.user, instance.stock.branch_id, 'inventory.view_stock_costs'
            )
        if not can_view_cost:
            data.pop('unit_cost_snapshot', None)
            data.pop('cost_impact', None)
        return data


class StockConsumptionSummarySerializer(serializers.Serializer):
    product = serializers.SerializerMethodField()
    gross_quantity = serializers.CharField()
    returned_quantity = serializers.CharField()
    net_quantity = serializers.CharField()
    legacy_gross_equivalent_quantity = serializers.CharField()
    legacy_returned_equivalent_quantity = serializers.CharField()
    legacy_net_equivalent_quantity = serializers.CharField()
    exact_gross_equivalent_quantity = serializers.CharField()
    exact_returned_equivalent_quantity = serializers.CharField()
    exact_net_equivalent_quantity = serializers.CharField()
    combined_exact_equivalent_total = serializers.CharField(source='net_quantity')
    gross_content = serializers.SerializerMethodField()
    returned_content = serializers.SerializerMethodField()
    net_content = serializers.SerializerMethodField()
    package_content = serializers.SerializerMethodField()
    content_unit = serializers.CharField(allow_null=True)
    complete_packages = serializers.SerializerMethodField()
    residual_content = serializers.SerializerMethodField()
    estimated_cost = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    movement_count = serializers.IntegerField()

    def get_product(self, row):
        product = row['product']
        return {
            'id': product.pk,
            'name': product.name,
            'internal_code': product.internal_code,
            'unit': product.unit,
            'category': {'id': product.category_id, 'name': product.category.name},
        }

    @staticmethod
    def get_gross_content(row):
        return format(row['gross_content'], 'f') if row['package_content'] else None

    @staticmethod
    def get_returned_content(row):
        return format(row['returned_content'], 'f') if row['package_content'] else None

    @staticmethod
    def get_net_content(row):
        return format(row['net_content'], 'f') if row['package_content'] else None

    @staticmethod
    def get_package_content(row):
        return format(row['package_content'], 'f') if row['package_content'] else None

    @staticmethod
    def _net_breakdown(row):
        if not row['package_content']:
            return None
        return content_breakdown(row['net_content'], row['package_content'])

    def get_complete_packages(self, row):
        breakdown = self._net_breakdown(row)
        return format(breakdown[0], 'f') if breakdown else None

    def get_residual_content(self, row):
        breakdown = self._net_breakdown(row)
        return format(breakdown[1], 'f') if breakdown else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get('include_cost'):
            data.pop('estimated_cost', None)
        return data


class StockConsumptionMovementSerializer(InventoryMovementReportSerializer):
    origin = serializers.SerializerMethodField()
    sale = serializers.SerializerMethodField()

    def get_origin(self, movement):
        mapping = {
            MovementType.SALE: 'sale',
            MovementType.CONSUMPTION: 'consumption',
            MovementType.EXIT: 'manual_exit',
            MovementType.SALE_CANCELLATION: 'reversal',
            MovementType.CONSUMPTION_CANCELLATION: 'reversal',
        }
        return mapping.get(movement.movement_type)


class StockPositionReportSerializer(serializers.Serializer):
    def to_representation(self, stock):
        quantity = stock.equivalent_quantity()
        archived = stock.product.archived_at is not None
        if archived and quantity != 0:
            state = 'archived_with_stock'
        elif quantity < 0:
            state = 'negative'
        elif quantity == 0:
            state = 'zero'
        elif quantity < stock.minimum_quantity:
            state = 'below_minimum'
        else:
            state = 'normal'
        config = next(
            iter(getattr(stock.product, '_report_branch_configs', ())), None
        )
        data = {
            'id': stock.pk,
            'product': {
                'id': stock.product_id,
                'name': stock.product.name,
                'internal_code': stock.product.internal_code,
            },
            'category': (
                {'id': config.category_id, 'name': config.category.name}
                if config and config.category_id else None
            ),
            'unit': stock.product.unit,
            'current_quantity': format(quantity, 'f'),
            'minimum_quantity': format(stock.minimum_quantity, 'f'),
            'maximum_quantity': (
                format(stock.maximum_quantity, 'f')
                if stock.maximum_quantity is not None else None
            ),
            'state': state,
            'archived': archived,
        }
        if self.context.get('include_cost'):
            unit_cost = (
                stock.average_unit_cost
                if stock.average_unit_cost is not None else stock.product.cost
            )
            data.update({
                'average_unit_cost': (
                    format(stock.average_unit_cost, 'f')
                    if stock.average_unit_cost is not None else None
                ),
                'last_unit_cost': (
                    format(stock.last_unit_cost, 'f')
                    if stock.last_unit_cost is not None else None
                ),
                'inventory_value': f'{max(quantity, Decimal("0")) * unit_cost:.2f}',
            })
        return data


class InventoryCountReportSerializer(serializers.Serializer):
    def to_representation(self, inventory_count):
        items = list(getattr(inventory_count, '_report_items', ()))
        include_cost = self.context.get('include_cost', False)
        details = []
        for item in items:
            difference = item.difference_quantity
            detail = {
                'id': item.pk,
                'product': {
                    'id': item.product_id,
                    'name': item.product.name,
                    'internal_code': item.product.internal_code,
                },
                'unit': item.product.unit,
                'expected_quantity': format(item.theoretical_quantity, 'f'),
                'counted_quantity': format(item.counted_quantity, 'f'),
                'difference_quantity': format(difference, 'f'),
                'type': (
                    'shortage' if difference < 0
                    else 'surplus' if difference > 0 else 'exact'
                ),
            }
            if (
                item.theoretical_content is not None
                and item.package_content_snapshot is not None
            ):
                expected_complete, expected_residual = content_breakdown(
                    item.theoretical_content, item.package_content_snapshot
                )
                difference_complete, difference_residual = content_breakdown(
                    item.difference_content, item.package_content_snapshot
                )
                detail.update({
                    'theoretical_content': format(item.theoretical_content, 'f'),
                    'counted_content': format(item.counted_content, 'f'),
                    'difference_content': format(item.difference_content, 'f'),
                    'package_content': format(item.package_content_snapshot, 'f'),
                    'content_unit': item.content_unit,
                    'expected_complete_packages': format(expected_complete, 'f'),
                    'expected_residual_content': format(expected_residual, 'f'),
                    'counted_complete_packages': format(
                        item.counted_complete_packages, 'f'
                    ),
                    'counted_residual_content': format(
                        item.counted_residual_content, 'f'
                    ),
                    'difference_complete_packages': format(
                        difference_complete, 'f'
                    ),
                    'difference_residual_content': format(
                        difference_residual, 'f'
                    ),
                })
            if include_cost:
                detail.update({
                    'unit_cost_snapshot': format(item.unit_cost_snapshot, 'f'),
                    'cost_impact': f'{item.cost_impact:.2f}',
                })
            details.append(detail)
        responsible = inventory_count.created_by
        data = {
            'id': str(inventory_count.pk),
            'date': inventory_count.confirmed_at or inventory_count.created_at,
            'branch': {
                'id': inventory_count.branch_id,
                'name': inventory_count.branch.name,
            },
            'responsible': {
                'id': responsible.pk,
                'name': readable_user_name(responsible),
            },
            'status': inventory_count.status,
            'mode': inventory_count.mode,
            'item_count': len(details),
            'correct_count': sum(item['type'] == 'exact' for item in details),
            'shortage_count': sum(item['type'] == 'shortage' for item in details),
            'surplus_count': sum(item['type'] == 'surplus' for item in details),
            'items': details,
        }
        if include_cost:
            financial_impact = sum(
                (item.cost_impact for item in items), Decimal('0')
            )
            data['financial_impact'] = f'{financial_impact:.2f}'
        return data


class StockTransferReportSerializer(serializers.Serializer):
    @staticmethod
    def _received_quantity(item):
        received = sum(
            (receipt.received_quantity for receipt in item.receipt_items.all()),
            Decimal('0'),
        )
        try:
            resolutions = item.divergence.resolutions.all()
        except ObjectDoesNotExist:
            resolutions = ()
        return received + sum(
            (
                resolution.quantity for resolution in resolutions
                if resolution.resolution_type == TransferResolutionType.FOUND_RECEIPT
            ),
            Decimal('0'),
        )

    def to_representation(self, transfer):
        items = list(getattr(transfer, '_report_items', ()))
        include_cost = self.context.get('include_cost', False)
        details = []
        for item in items:
            sent = item.dispatched_quantity or Decimal('0')
            received = self._received_quantity(item)
            difference = sent - received
            detail = {
                'id': item.pk,
                'product': {
                    'id': item.product_id,
                    'name': item.product_name_snapshot,
                    'internal_code': item.product_internal_code_snapshot,
                },
                'unit': item.product_unit_snapshot,
                'sent_quantity': format(sent, 'f'),
                'received_quantity': format(received, 'f'),
                'difference_quantity': format(difference, 'f'),
            }
            if include_cost:
                detail.update({
                    'unit_cost_snapshot': (
                        format(item.origin_unit_cost_snapshot, 'f')
                        if item.origin_unit_cost_snapshot is not None else None
                    ),
                    'cost_value': (
                        f'{sent * item.origin_unit_cost_snapshot:.2f}'
                        if item.origin_unit_cost_snapshot is not None else None
                    ),
                })
            details.append(detail)
        quantities_by_unit = {}
        for item in details:
            unit = item['unit']
            group = quantities_by_unit.setdefault(unit, {
                'unit': unit,
                'sent_quantity': Decimal('0'),
                'received_quantity': Decimal('0'),
                'difference_quantity': Decimal('0'),
            })
            for field in (
                'sent_quantity', 'received_quantity', 'difference_quantity',
            ):
                group[field] += Decimal(item[field])
        responsible = transfer.dispatched_by or transfer.created_by
        data = {
            'id': str(transfer.pk),
            'date': transfer.dispatched_at or transfer.created_at,
            'origin': {
                'id': transfer.origin_branch_id,
                'name': transfer.origin_branch.name,
            },
            'destination': {
                'id': transfer.destination_branch_id,
                'name': transfer.destination_branch.name,
            },
            'responsible': {
                'id': responsible.pk,
                'name': readable_user_name(responsible),
            },
            'status': transfer.status,
            'item_count': len(details),
            'quantities_by_unit': [
                {
                    key: format(value, 'f') if isinstance(value, Decimal) else value
                    for key, value in group.items()
                }
                for _unit, group in sorted(quantities_by_unit.items())
            ],
            'items': details,
        }
        if include_cost:
            cost_value = sum(
                (
                    Decimal(item['cost_value']) for item in details
                    if item.get('cost_value') is not None
                ),
                Decimal('0'),
            )
            data['cost_value'] = f'{cost_value:.2f}'
        return data
