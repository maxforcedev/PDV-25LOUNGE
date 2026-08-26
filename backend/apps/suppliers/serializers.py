from decimal import Decimal

from rest_framework import serializers

from apps.companies.models import Status

from .models import ProductSupplier, ProductSupplierUnit, Supplier
from .services import _save_product_supplier, _save_product_supplier_unit, _save_supplier
from .validators import normalize_tax_id, validate_tax_id


class ImmutableTenantSerializer(serializers.ModelSerializer):
    identity_fields = ('company',)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance:
            errors = {}
            for field in self.identity_fields:
                value = attrs.get(field)
                if value is not None and value.pk != getattr(self.instance, f'{field}_id'):
                    errors[field] = 'A identidade da relação não pode ser alterada.'
            if errors:
                raise serializers.ValidationError(errors)
        return attrs


class SupplierSerializer(ImmutableTenantSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    tax_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=18
    )
    address = serializers.JSONField(required=False)

    class Meta:
        model = Supplier
        fields = (
            'id', 'company', 'company_name', 'legal_name', 'trade_name', 'tax_id',
            'phone', 'email', 'contact_name', 'address', 'notes', 'status',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'company_name', 'status', 'created_at', 'updated_at')
        validators = []

    def validate_tax_id(self, value):
        value = normalize_tax_id(value)
        validate_tax_id(value)
        return value

    def validate_address(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Informe o endereço como um objeto.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        company = attrs.get('company', getattr(self.instance, 'company', None))
        tax_id = attrs.get('tax_id', getattr(self.instance, 'tax_id', None))
        if company and tax_id:
            duplicate = Supplier.objects.filter(company=company, tax_id=tax_id)
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError({
                    'tax_id': 'Outro fornecedor desta empresa já utiliza este CPF/CNPJ.'
                })
        return attrs

    def create(self, validated_data):
        return _save_supplier(**validated_data)

    def update(self, instance, validated_data):
        return _save_supplier(instance=instance, **validated_data)


class ProductSupplierSerializer(ImmutableTenantSerializer):
    identity_fields = ('company', 'product', 'supplier')
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.trade_name', read_only=True)

    class Meta:
        model = ProductSupplier
        fields = (
            'id', 'company', 'company_name', 'product', 'product_name', 'supplier',
            'supplier_name', 'supplier_code', 'is_preferred', 'is_exclusive', 'status',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company_name', 'product_name', 'supplier_name', 'status',
            'created_at', 'updated_at',
        )
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        company = attrs.get('company', getattr(self.instance, 'company', None))
        product = attrs.get('product', getattr(self.instance, 'product', None))
        supplier = attrs.get('supplier', getattr(self.instance, 'supplier', None))
        status = getattr(self.instance, 'status', Status.ACTIVE)
        preferred = attrs.get('is_preferred', getattr(self.instance, 'is_preferred', False))
        exclusive = attrs.get('is_exclusive', getattr(self.instance, 'is_exclusive', False))
        errors = {}
        if company and product and company.pk != product.company_id:
            errors['product'] = 'O produto deve pertencer à empresa da relação.'
        if company and supplier and company.pk != supplier.company_id:
            errors['supplier'] = 'O fornecedor deve pertencer à empresa da relação.'
        if exclusive and status == Status.ACTIVE:
            preferred = True
            attrs['is_preferred'] = True
        if product and supplier:
            duplicate = ProductSupplier.objects.filter(product=product, supplier=supplier)
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                errors['non_field_errors'] = 'Este fornecedor já está vinculado ao produto.'
        if status == Status.ACTIVE and product:
            siblings = ProductSupplier.objects.filter(product=product, status=Status.ACTIVE)
            if self.instance:
                siblings = siblings.exclude(pk=self.instance.pk)
            if preferred and siblings.filter(is_preferred=True).exists():
                errors['is_preferred'] = 'O produto já possui um fornecedor preferencial ativo.'
            if exclusive and siblings.filter(is_exclusive=True).exists():
                errors['is_exclusive'] = 'O produto já possui um fornecedor exclusivo ativo.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        return _save_product_supplier(**validated_data)

    def update(self, instance, validated_data):
        return _save_product_supplier(instance=instance, **validated_data)


class ProductSupplierUnitSerializer(ImmutableTenantSerializer):
    identity_fields = ('company', 'product_supplier')
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    product_name = serializers.CharField(
        source='product_supplier.product.name', read_only=True
    )
    supplier_name = serializers.CharField(
        source='product_supplier.supplier.trade_name', read_only=True
    )
    conversion_factor = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal('0.000001')
    )

    class Meta:
        model = ProductSupplierUnit
        fields = (
            'id', 'company', 'company_name', 'product_supplier', 'product_name',
            'supplier_name', 'unit_code', 'description', 'conversion_factor', 'barcode',
            'is_default', 'status', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company_name', 'product_name', 'supplier_name', 'status',
            'created_at', 'updated_at',
        )
        validators = []

    def validate_unit_code(self, value):
        return value.strip().upper()

    def validate_barcode(self, value):
        return value.strip()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        company = attrs.get('company', getattr(self.instance, 'company', None))
        relation = attrs.get(
            'product_supplier', getattr(self.instance, 'product_supplier', None)
        )
        status = getattr(self.instance, 'status', Status.ACTIVE)
        is_default = attrs.get('is_default', getattr(self.instance, 'is_default', False))
        errors = {}
        if company and relation and company.pk != relation.company_id:
            errors['product_supplier'] = 'A relação deve pertencer à empresa da apresentação.'
        if status == Status.ACTIVE and is_default and relation:
            siblings = ProductSupplierUnit.objects.filter(
                product_supplier=relation, status=Status.ACTIVE, is_default=True
            )
            if self.instance:
                siblings = siblings.exclude(pk=self.instance.pk)
            if siblings.exists():
                errors['is_default'] = 'A relação já possui uma apresentação padrão ativa.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        return _save_product_supplier_unit(**validated_data)

    def update(self, instance, validated_data):
        return _save_product_supplier_unit(instance=instance, **validated_data)
