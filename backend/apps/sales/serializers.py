from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.base.constants import MAX_BIGINT
from apps.companies.selectors import user_has_branch_permission
from apps.products.models import Category, Product
from apps.products.serializers import ProductSerializer

from .models import (
    Payment, PaymentMethod, Promotion, PromotionDiscountType, Sale, SaleItem,
)


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
    product_names = serializers.SerializerMethodField()
    category_names = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    category_count = serializers.SerializerMethodField()
    starts_at = CanonicalDateTimeField()
    ends_at = CanonicalDateTimeField()
    discount_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.01'),
        coerce_to_string=True,
    )

    class Meta:
        model = Promotion
        fields = (
            'id', 'name', 'discount_type', 'discount_value', 'starts_at', 'ends_at',
            'status', 'product_ids', 'category_ids', 'product_names', 'category_names',
            'product_count', 'category_count', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'status', 'product_names', 'category_names', 'product_count',
            'category_count', 'created_at', 'updated_at',
        )

    def get_product_names(self, promotion):
        return [product.name for product in promotion.products.all()]

    def get_category_names(self, promotion):
        return [category.name for category in promotion.categories.all()]

    def get_product_count(self, promotion):
        return len(promotion.products.all())

    def get_category_count(self, promotion):
        return len(promotion.categories.all())

    def validate(self, attrs):
        branch = self.context['request'].branch_context
        company_id = branch.company_id
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
        if discount_type == PromotionDiscountType.PERCENTAGE and discount_value > 100:
            errors['discount_value'] = 'O percentual nao pode ser maior que 100.'
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

    @transaction.atomic
    def create(self, validated_data):
        products = validated_data.pop('products', [])
        categories = validated_data.pop('categories', [])
        promotion = Promotion.objects.create(
            company=self.context['request'].branch_context.company,
            **validated_data,
        )
        promotion.products.set(products)
        promotion.categories.set(categories)
        return promotion

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = Promotion.objects.select_for_update().get(pk=instance.pk)
        products = validated_data.pop('products', None)
        categories = validated_data.pop('categories', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if products is not None:
            instance.products.set(products)
        if categories is not None:
            instance.categories.set(categories)
        return instance


class SaleItemSerializer(serializers.ModelSerializer):
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
        return fields

    class Meta:
        model = SaleItem
        fields = (
            'id', 'product', 'quantity', 'product_name', 'internal_code', 'unit',
            'unit_cost', 'unit_price', 'subtotal', 'promotion', 'promotion_name',
            'promotion_discount_type', 'promotion_discount_value', 'promotion_benefit',
            'net_subtotal', 'created_at',
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
    created_by_name = serializers.SerializerMethodField()
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
            'sale_number', 'operation_type', 'status', 'created_by', 'created_by_name',
            'beneficiary_user', 'beneficiary_user_name', 'subtotal',
            'promotion_discount_total', 'discount',
            'charged_amount', 'total', 'cancelled_at', 'cancelled_by', 'cancelled_by_name',
            'cancellation_reason', 'items', 'payments', 'created_at', 'updated_at',
        )

    def get_created_by_name(self, sale):
        return readable_user_name(sale.created_by)

    def get_beneficiary_user_name(self, sale):
        return readable_user_name(sale.beneficiary_user)

    def get_cancelled_by_name(self, sale):
        return readable_user_name(sale.cancelled_by)


class SaleBeneficiarySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'name', 'user_type', 'can_login')
        read_only_fields = fields

    def get_name(self, user):
        return readable_user_name(user)


class SaleCatalogProductSerializer(ProductSerializer):
    class Meta(ProductSerializer.Meta):
        read_only_fields = ProductSerializer.Meta.fields


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


class PaymentInputSerializer(serializers.Serializer):
    payment_method = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT)
    amount = StrictDecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.01')
    )
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
    discount = InternalDecimalField(
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
    cash_session = serializers.PrimaryKeyRelatedField(
        queryset=Sale._meta.get_field('cash_session').remote_field.model.objects.all(),
        pk_field=serializers.IntegerField(min_value=1, max_value=MAX_BIGINT),
        required=False,
        allow_null=True,
    )
    payments = PaymentInputSerializer(many=True, required=False, default=list)


class SalesQuerySerializer(serializers.Serializer):
    operation_type = serializers.ChoiceField(
        choices=('sale', 'consumption'), required=False, default='sale'
    )
    category = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)
    beneficiary = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT, required=False)


class CancelSaleSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='', trim_whitespace=True)
