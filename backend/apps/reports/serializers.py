from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from apps.accounts.models import User
from apps.base.constants import MAX_BIGINT
from apps.cash.models import CashRegister, CashSession, CashSessionStatus, WithdrawalCategory
from apps.cash.services import redact_operational_summary, session_operational_summary
from apps.inventory.models import MovementType
from apps.inventory.content import content_breakdown
from apps.products.models import Category, Product, SalesChannel
from apps.sales.models import OperationType, Payment, PaymentMethod, Sale, SaleItem, SaleStatus
from apps.sales.serializers import readable_user_name


class BaseReportQuerySerializer(serializers.Serializer):
    start_datetime = serializers.CharField(max_length=64, required=False)
    end_datetime = serializers.CharField(max_length=64, required=False)
    export = serializers.ChoiceField(choices=('csv',), required=False)
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
            'product': Product.objects.filter(company_id=branch.company_id),
            'category': Category.objects.filter(company_id=branch.company_id),
            'payment_method': PaymentMethod.objects.filter(company_id=branch.company_id),
            'cash_register': CashRegister.objects.filter(branch=branch),
            'cash_session': CashSession.objects.filter(branch=branch),
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

    def validate(self, attrs):
        attrs = self.validate_scoped_ids(
            attrs, ('operator', 'seller', 'product', 'category', 'payment_method')
        )
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


class ReportSaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = (
            'id', 'product', 'product_name', 'internal_code', 'unit', 'quantity', 'unit_price',
            'subtotal', 'promotion', 'promotion_name', 'promotion_discount_type',
            'promotion_discount_value', 'promotion_benefit', 'manual_discount',
            'net_subtotal',
            'participates_in_service_fee', 'participates_in_commission',
        )


class ReportPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ('payment_method', 'payment_method_name', 'payment_method_code', 'amount')


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
            'discount_approved_by', 'beneficiary', 'subtotal',
            'promotion_discount_total', 'item_discount_total', 'discount', 'service_fee_rate',
            'service_fee_amount', 'commission_rate', 'commission_amount', 'total', 'created_at',
            'sales_revenue', 'consumption_charged', 'effective_revenue', 'service_fee',
            'total_received', 'payment_total', 'reconciliation_delta',
            'payment_reconciliation_delta',
            'total_received_sales', 'customer_total', 'cancelled_at', 'items', 'payments',
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
                item.pk: item.product.category_id for item in instance.items.all()
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


class CashSessionReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    opened_at = serializers.DateTimeField()
    closed_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    register = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    opening = serializers.DecimalField(max_digits=20, decimal_places=2, source='opening_amount')
    manual_entries = serializers.DecimalField(max_digits=20, decimal_places=2)
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


class WithdrawalReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    category = serializers.CharField(source='withdrawal_category')
    category_label = serializers.CharField(source='get_withdrawal_category_display')
    beneficiary = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    cash_register = serializers.SerializerMethodField()
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


class InventoryMovementReportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    movement_type = serializers.CharField()
    nature = serializers.CharField()
    operation_reference = serializers.UUIDField()
    product = serializers.SerializerMethodField()
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
