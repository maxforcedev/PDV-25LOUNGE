from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.base.constants import MAX_BIGINT
from apps.companies.models import Branch
from apps.companies.selectors import user_has_branch_permission
from apps.products.models import Category, Product
from apps.products.serializers import ProductSerializer

from .models import (
    Payment, PaymentMethod, Promotion, PromotionDiscountType, PromotionSchedule,
    Sale, SaleItem, Weekday,
)
from .services import detect_promotion_conflict


def readable_user_name(user):
    if user is None:
        return None
    return user.get_full_name().strip() or user.email or f'Usuario {user.pk}'


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ('id', 'company', 'code', 'name', 'status', 'is_system', 'created_at', 'updated_at')
        read_only_fields = ('id', 'status', 'is_system', 'created_at', 'updated_at')

    def validate(self, attrs):
        branch = self.context['request'].branch_context
        company = attrs.get('company', getattr(self.instance, 'company', None))
        if not company or company.pk != branch.company_id:
            raise serializers.ValidationError({'company': 'Empresa fora do contexto da filial.'})
        if self.instance and company.pk != self.instance.company_id:
            raise serializers.ValidationError({'company': 'A empresa nao pode ser alterada.'})
        if self.instance and 'code' in attrs and attrs['code'] != self.instance.code:
            raise serializers.ValidationError({'code': 'O codigo nao pode ser alterado.'})
        if self.instance and self.instance.is_system and 'name' in attrs:
            if attrs['name'] != self.instance.name:
                raise serializers.ValidationError(
                    {'name': 'O nome de um metodo padrao nao pode ser alterado.'}
                )
        return attrs


class CanonicalDateTimeField(serializers.DateTimeField):
    def __init__(self, **kwargs):
        kwargs.setdefault('default_timezone', timezone.get_default_timezone())
        super().__init__(**kwargs)

    def to_representation(self, value):
        if value is None:
            return None
        return value.astimezone(timezone.get_default_timezone()).isoformat()


class PromotionScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromotionSchedule
        fields = ('id', 'weekday', 'start_time', 'end_time')
        read_only_fields = ('id',)

    def validate(self, attrs):
        start = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        if start and end and start == end:
            raise serializers.ValidationError({'end_time': 'O horario final deve diferir do inicial.'})
        return attrs


class PromotionSerializer(serializers.ModelSerializer):
    product_ids = serializers.PrimaryKeyRelatedField(
        source='products', many=True, queryset=Product.objects.all(),
        required=False,
    )
    category_ids = serializers.PrimaryKeyRelatedField(
        source='categories', many=True,
        queryset=Category.objects.all(),
        required=False,
    )
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), pk_field=serializers.IntegerField(min_value=1, max_value=MAX_BIGINT),
        required=False, allow_null=True,
    )
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='Todas as filiais')
    broker_all_branches = serializers.SerializerMethodField()
    schedules = PromotionScheduleSerializer(many=True, required=False)
    product_names = serializers.SerializerMethodField()
    category_names = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    category_count = serializers.SerializerMethodField()
    starts_at = CanonicalDateTimeField()
    ends_at = CanonicalDateTimeField(allow_null=True, required=False)
    discount_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.01'),
        coerce_to_string=True,
    )

    class Meta:
        model = Promotion
        fields = (
            'id', 'name', 'branch', 'branch_name', 'broker_all_branches',
            'discount_type', 'discount_value', 'starts_at', 'ends_at',
            'schedules', 'status', 'product_ids', 'category_ids',
            'product_names', 'category_names', 'product_count', 'category_count',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'status', 'branch_name', 'broker_all_branches',
            'product_names', 'category_names', 'product_count', 'category_count',
            'created_at', 'updated_at',
        )

    def get_broker_all_branches(self, promotion):
        return promotion.branch_id is None

    def get_product_names(self, promotion):
        return [product.name for product in promotion.products.all()]

    def get_category_names(self, promotion):
        return [category.name for category in promotion.categories.all()]

    def get_product_count(self, promotion):
        return len(promotion.products.all())

    def get_category_count(self, promotion):
        return len(promotion.categories.all())

    def validate(self, attrs):
        branch_context = self.context['request'].branch_context
        company_id = branch_context.company_id
        chosen_branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        products = attrs.get(
            'products', list(self.instance.products.all()) if self.instance else []
        )
        categories = attrs.get(
            'categories', list(self.instance.categories.all()) if self.instance else []
        )
        errors = {}
        if not products and not categories:
            errors['targets'] = 'Informe ao menos um produto ou categoria.'
        if any(product.company_id != company_id for product in products):
            errors['product_ids'] = 'Todos os produtos devem pertencer a empresa atual.'
        if any(category.company_id != company_id for category in categories):
            errors['category_ids'] = 'Todas as categorias devem pertencer a empresa atual.'
        if chosen_branch is not None and chosen_branch.company_id != company_id:
            errors['branch'] = 'A filial deve pertencer a empresa atual.'
        starts_at = attrs.get('starts_at', getattr(self.instance, 'starts_at', None))
        ends_at = attrs.get('ends_at', getattr(self.instance, 'ends_at', None))
        if starts_at and ends_at and starts_at >= ends_at:
            errors['ends_at'] = 'A data final deve ser posterior a data inicial.'
        discount_type = attrs.get(
            'discount_type', getattr(self.instance, 'discount_type', None)
        )
        discount_value = attrs.get(
            'discount_value', getattr(self.instance, 'discount_value', None)
        )
        if discount_value is not None and discount_value <= 0:
            errors['discount_value'] = 'O desconto deve ser maior que zero.'
        if discount_type == PromotionDiscountType.PERCENTAGE and discount_value and discount_value > 100:
            errors['discount_value'] = 'O percentual nao pode ser maior que 100.'
        schedules = attrs.get('schedules', [])
        seen = set()
        for schedule in schedules:
            key = (schedule.get('weekday'), str(schedule.get('start_time')), str(schedule.get('end_time')))
            if key in seen:
                errors.setdefault('schedules', []).append('Nao repita intervalos de agenda.')
                break
            seen.add(key)
        name = ' '.join(attrs.get('name', getattr(self.instance, 'name', '')).split())
        attrs['name'] = name
        duplicate = Promotion.objects.filter(company_id=company_id, name__iexact=name)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            errors['name'] = 'Ja existe uma promocao com este nome na empresa.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _validate_conflict(self, promotion):
        conflict = detect_promotion_conflict(promotion)
        if conflict:
            raise serializers.ValidationError({'targets': conflict})

    @transaction.atomic
    def create(self, validated_data):
        products = validated_data.pop('products', [])
        categories = validated_data.pop('categories', [])
        schedules_data = validated_data.pop('schedules', [])
        promotion = Promotion.objects.create(
            company=self.context['request'].branch_context.company,
            **validated_data,
        )
        promotion.products.set(products)
        promotion.categories.set(categories)
        for item in schedules_data:
            PromotionSchedule.objects.create(promotion=promotion, **item)
        self._validate_conflict(promotion)
        return promotion

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = Promotion.objects.select_for_update().get(pk=instance.pk)
        products = validated_data.pop('products', None)
        categories = validated_data.pop('categories', None)
        schedules_data = validated_data.pop('schedules', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if products is not None:
            instance.products.set(products)
        if categories is not None:
            instance.categories.set(categories)
        if schedules_data is not None:
            instance.schedules.all().delete()
            for item in schedules_data:
                PromotionSchedule.objects.create(promotion=instance, **item)
        self._validate_conflict(instance)
        return instance


class SaleItemSerializer(serializers.ModelSerializer):
    discount_approved_by_name = serializers.SerializerMethodField()
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, read_only=True, coerce_to_string=True
    )
    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    subtotal = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    promotion_discount_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True,
        coerce_to_string=True,
    )
    promotion_benefit = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    manual_discount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    net_subtotal = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if not request or not (
            request.user.is_superuser
            or branch and user_has_branch_permission(
                request.user, branch.pk, 'inventory.view_stock_costs'
            )
        ):
            fields.pop('unit_cost', None)
            fields.pop('component_cost_snapshot', None)
        return fields

    def get_discount_approved_by_name(self, item):
        return readable_user_name(item.discount_approved_by)

    class Meta:
        model = SaleItem
        fields = (
            'id', 'product', 'quantity', 'product_name', 'internal_code', 'unit',
            'unit_cost', 'unit_price', 'subtotal', 'promotion', 'promotion_name',
            'promotion_discount_type', 'promotion_discount_value', 'promotion_benefit',
            'manual_discount', 'discount_approved_by', 'discount_approved_by_name',
            'component_cost_snapshot', 'net_subtotal', 'created_at',
        )


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            'id', 'payment_method', 'payment_method_name', 'payment_method_code',
            'amount', 'received_amount', 'change_amount', 'created_at',
        )


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    cash_session_status = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    seller_user_name = serializers.SerializerMethodField()
    discount_approved_by_name = serializers.SerializerMethodField()
    service_fee_waived_by_name = serializers.SerializerMethodField()
    beneficiary_user_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    discount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    promotion_discount_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    item_discount_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    service_fee_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True, coerce_to_string=True
    )
    service_fee_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    commission_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True, coerce_to_string=True
    )
    commission_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )
    charged_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True,
        coerce_to_string=True,
    )
    total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, coerce_to_string=True
    )

    class Meta:
        model = Sale
        fields = (
            'id', 'company', 'company_name', 'branch', 'branch_name', 'cash_session',
            'cash_session_status', 'sale_number', 'operation_type', 'status',
            'idempotency_key',
            'created_by', 'created_by_name', 'seller_user', 'seller_user_name',
            'discount_approved_by', 'discount_approved_by_name',
            'service_fee_waived', 'service_fee_waived_by', 'service_fee_waived_by_name',
            'beneficiary_user', 'beneficiary_user_name',
            'subtotal', 'promotion_discount_total', 'item_discount_total', 'discount',
            'service_fee_rate', 'service_fee_amount',
            'commission_rate', 'commission_amount',
            'charged_amount', 'total', 'cancelled_at', 'cancelled_by', 'cancelled_by_name',
            'cancellation_reason', 'items', 'payments', 'created_at', 'updated_at',
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        branch = getattr(request, 'branch_context', None) if request else None
        if not request or not (
            request.user.is_superuser
            or branch and user_has_branch_permission(
                request.user, branch.pk, 'commissions.view'
            )
        ):
            fields.pop('commission_rate', None)
            fields.pop('commission_amount', None)
        return fields

    def get_created_by_name(self, sale):
        return readable_user_name(sale.created_by)

    def get_seller_user_name(self, sale):
        return readable_user_name(sale.seller_user)

    def get_discount_approved_by_name(self, sale):
        return readable_user_name(sale.discount_approved_by)

    def get_service_fee_waived_by_name(self, sale):
        return readable_user_name(sale.service_fee_waived_by)

    def get_beneficiary_user_name(self, sale):
        return readable_user_name(sale.beneficiary_user)

    def get_cancelled_by_name(self, sale):
        return readable_user_name(sale.cancelled_by)

    def get_cash_session_status(self, sale):
        if not sale.cash_session_id:
            return None
        return sale.cash_session.status


class SaleBeneficiarySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'name', 'user_type', 'can_login')
        read_only_fields = fields

    def get_name(self, user):
        return readable_user_name(user)


class SaleUserOptionSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'name', 'email')
        read_only_fields = fields

    def get_name(self, user):
        return readable_user_name(user)


class SaleCatalogProductSerializer(ProductSerializer):
    sale_price = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        read_only_fields = ProductSerializer.Meta.fields

    def get_sale_price(self, product):
        price = getattr(product, 'effective_sale_price', product.sale_price)
        return f'{price:.2f}'


class StrictDecimalField(serializers.DecimalField):
    def to_internal_value(self, data):
        if isinstance(data, (float, bool)):
            self.fail('invalid')
        return super().to_internal_value(data)


class InternalDecimalField(serializers.DecimalField):
    def to_internal_value(self, data):
        if not isinstance(data, Decimal):
            self.fail('invalid')
        return super().to_internal_value(data)


class ItemInputSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    quantity = StrictDecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal('0.001')
    )
    discount = serializers.JSONField(required=False, default='0.00')


class PaymentInputSerializer(serializers.Serializer):
    payment_method = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    amount = serializers.JSONField(required=False, allow_null=True)
    received_amount = StrictDecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00'),
        required=False, allow_null=True,
    )


class CalculationSerializer(serializers.Serializer):
    operation_type = serializers.ChoiceField(choices=('sale', 'consumption'))
    items = ItemInputSerializer(many=True, allow_empty=False)
    discount = serializers.JSONField(required=False)
    charged_amount = serializers.JSONField(required=False)
    beneficiary_user = serializers.PrimaryKeyRelatedField(
        queryset=Sale._meta.get_field('beneficiary_user').remote_field.model.objects.all(),
        pk_field=serializers.IntegerField(min_value=1, max_value=MAX_BIGINT),
        required=False,
        allow_null=True,
    )
    service_fee_waived = serializers.BooleanField(required=False, default=False)


class CalculationItemOutputSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    quantity = InternalDecimalField(
        max_digits=14, decimal_places=3, coerce_to_string=True
    )
    product_name = serializers.CharField()
    internal_code = serializers.CharField()
    unit = serializers.CharField()
    unit_price = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    subtotal = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    promotion = serializers.IntegerField(
        min_value=1, max_value=MAX_BIGINT, allow_null=True
    )
    promotion_name = serializers.CharField(allow_null=True)
    promotion_discount_type = serializers.ChoiceField(
        choices=PromotionDiscountType.values, allow_null=True
    )
    promotion_discount_value = InternalDecimalField(
        max_digits=14, decimal_places=2, allow_null=True, coerce_to_string=True
    )
    promotion_benefit = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    manual_discount = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    net_subtotal = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )


class CalculationOutputSerializer(serializers.Serializer):
    operation_type = serializers.ChoiceField(choices=('sale', 'consumption'))
    items = CalculationItemOutputSerializer(many=True, allow_empty=False)
    subtotal = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    promotion_discount_total = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    item_discount_total = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    discount = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    service_fee_rate = InternalDecimalField(
        max_digits=5, decimal_places=2, coerce_to_string=True
    )
    service_fee_amount = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    service_fee_waived = serializers.BooleanField()
    commission_rate = InternalDecimalField(
        max_digits=5, decimal_places=2, coerce_to_string=True
    )
    commission_amount = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    charged_amount = InternalDecimalField(
        max_digits=14, decimal_places=2, allow_null=True, coerce_to_string=True
    )
    reference_total = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )
    total = InternalDecimalField(
        max_digits=14, decimal_places=2, coerce_to_string=True
    )


class FinalizeSaleSerializer(CalculationSerializer):
    idempotency_key = serializers.UUIDField()
    seller_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        pk_field=serializers.IntegerField(min_value=1, max_value=MAX_BIGINT),
        required=False,
        allow_null=True,
    )
    cash_session = serializers.PrimaryKeyRelatedField(
        queryset=Sale._meta.get_field('cash_session').remote_field.model.objects.all(),
        pk_field=serializers.IntegerField(min_value=1, max_value=MAX_BIGINT),
        required=False,
        allow_null=True,
    )
    payments = PaymentInputSerializer(many=True, required=False, default=list)
    discount_authorization = serializers.DictField(required=False, write_only=True)
    item_discount_authorization = serializers.DictField(required=False, write_only=True)
    service_fee_authorization = serializers.DictField(required=False, write_only=True)

    def validate_discount_authorization(self, value):
        allowed = {'user', 'method', 'credential'}
        if set(value) - allowed:
            raise serializers.ValidationError('A autorizacao possui campos desconhecidos.')
        try:
            user_id = int(value.get('user'))
        except (TypeError, ValueError):
            raise serializers.ValidationError('Informe o autorizador.')
        if value.get('method') != 'password':
            raise serializers.ValidationError('Metodo de autorizacao invalido.')
        credential = value.get('credential')
        if not isinstance(credential, str) or not credential:
            raise serializers.ValidationError('Informe a credencial do autorizador.')
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError('Autorizacao de desconto invalida.')
        return {'user': user, 'method': 'password', 'credential': credential}

    def validate_service_fee_authorization(self, value):
        return self.validate_discount_authorization(value)

    def validate_item_discount_authorization(self, value):
        return self.validate_discount_authorization(value)


class SalesQuerySerializer(serializers.Serializer):
    operation_type = serializers.ChoiceField(
        choices=('sale', 'consumption'), required=False, default='sale'
    )
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    beneficiary = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)


class CancelSaleSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='', trim_whitespace=True)
