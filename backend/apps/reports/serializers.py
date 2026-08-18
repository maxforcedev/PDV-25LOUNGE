from rest_framework import serializers

from apps.accounts.models import User
from apps.base.constants import MAX_BIGINT
from apps.cash.models import CashRegister, CashSession, CashSessionStatus, WithdrawalCategory
from apps.cash.services import session_operational_summary
from apps.inventory.models import MovementType
from apps.products.models import Category, Product
from apps.sales.models import Payment, PaymentMethod, Sale, SaleItem, SaleStatus
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
                errors[field] = 'Identificador invalido para a filial atual.'
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

    def validate(self, attrs):
        return self.validate_scoped_ids(
            attrs, ('operator', 'seller', 'product', 'category', 'payment_method')
        )


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
            'product', 'product_name', 'internal_code', 'unit', 'quantity', 'unit_price',
            'subtotal', 'promotion', 'promotion_name', 'promotion_discount_type',
            'promotion_discount_value', 'promotion_benefit', 'net_subtotal',
        )


class ReportPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ('payment_method_name', 'payment_method_code', 'amount')


class ReportSaleSerializer(serializers.ModelSerializer):
    operator = serializers.SerializerMethodField()
    seller = serializers.SerializerMethodField()
    discount_approved_by = serializers.SerializerMethodField()
    beneficiary = serializers.SerializerMethodField()
    items = ReportSaleItemSerializer(many=True, read_only=True)
    payments = ReportPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = (
            'id', 'sale_number', 'operation_type', 'status', 'operator', 'seller',
            'discount_approved_by', 'beneficiary', 'subtotal',
            'promotion_discount_total', 'discount', 'service_fee_rate',
            'service_fee_amount', 'commission_rate', 'commission_amount', 'total', 'created_at',
            'cancelled_at', 'items', 'payments',
        )

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
        if request and branch and not request.user.is_superuser:
            from apps.companies.selectors import user_has_company_permission

            if not user_has_company_permission(request.user, branch.company_id, 'commissions.view'):
                data.pop('commission_rate', None)
                data.pop('commission_amount', None)
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
    previous_quantity = serializers.DecimalField(max_digits=20, decimal_places=3)
    quantity = serializers.DecimalField(max_digits=20, decimal_places=3)
    final_quantity = serializers.DecimalField(max_digits=20, decimal_places=3)
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

    def get_user(self, movement):
        return {'id': movement.user_id, 'name': readable_user_name(movement.user)}

    def get_sale(self, movement):
        if movement.sale is None:
            return None
        return {'id': movement.sale_id, 'number': movement.sale.sale_number}


class StockConsumptionSummarySerializer(serializers.Serializer):
    product = serializers.SerializerMethodField()
    gross_quantity = serializers.DecimalField(max_digits=20, decimal_places=3)
    returned_quantity = serializers.DecimalField(max_digits=20, decimal_places=3)
    net_quantity = serializers.DecimalField(max_digits=20, decimal_places=3)
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
