from decimal import Decimal

from rest_framework import serializers

from apps.companies.models import Status

from .models import (
    PresentationPreset, PresentationType, ProductPurchasePresentation, ProductSupplier,
    ProductSupplierUnit, Supplier,
)
from .services import (
    _save_presentation_preset, _save_product_purchase_presentation,
    _save_product_supplier, _save_product_supplier_unit, _save_supplier,
)
from .validators import normalize_tax_id, validate_tax_id


class ImmutableTenantSerializer(serializers.ModelSerializer):
    identity_fields = ('company',)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        support_session = getattr(request, 'support_session', None) if request else None
        company_id = (
            support_session.company_id
            if support_session
            else request.query_params.get('company') if request else None
        ) or getattr(self.instance, 'company_id', None)
        if company_id is None and isinstance(getattr(self, 'initial_data', None), dict):
            company_id = self.initial_data.get('company')
        if not company_id:
            return fields

        scoped_fields = {
            'company': 'pk',
            'product': 'company_id',
            'supplier': 'company_id',
            'product_supplier': 'company_id',
            'presentation_preset': 'company_id',
            'purchase_presentation': 'company_id',
        }
        for name, lookup in scoped_fields.items():
            field = fields.get(name)
            if field is not None and getattr(field, 'queryset', None) is not None:
                field.queryset = field.queryset.filter(**{lookup: company_id})
        return fields

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
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    legal_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    trade_name = serializers.CharField(required=True, allow_blank=False, max_length=200)
    tax_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=18
    )
    address = serializers.JSONField(required=False)

    class Meta:
        model = Supplier
        fields = (
            'id', 'company', 'company_name', 'branch', 'branch_name', 'legal_name', 'trade_name', 'tax_id',
            'phone', 'email', 'contact_name', 'address', 'notes', 'status',
            'deleted_at', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company_name', 'branch', 'branch_name', 'status', 'deleted_at',
            'created_at', 'updated_at',
        )
        validators = []

    def validate_tax_id(self, value):
        value = normalize_tax_id(value)
        validate_tax_id(value)
        return value

    def validate_trade_name(self, value):
        value = ' '.join(value.split())
        if not value:
            raise serializers.ValidationError('Informe o nome fantasia.')
        return value

    def validate_address(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Informe o endereço como um objeto.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        company = attrs.get('company', getattr(self.instance, 'company', None))
        branch = getattr(self.context.get('request'), 'branch_context', None)
        tax_id = attrs.get('tax_id', getattr(self.instance, 'tax_id', None))
        if company and branch and company.pk != branch.company_id:
            raise serializers.ValidationError({'company': 'Empresa fora da filial atual.'})
        if branch and tax_id:
            duplicate = Supplier.objects.filter(
                branch=branch, tax_id=tax_id, deleted_at__isnull=True,
            )
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError({
                    'tax_id': 'Outro fornecedor desta filial já utiliza este CPF/CNPJ.'
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


class ProductPurchasePresentationSerializer(ImmutableTenantSerializer):
    identity_fields = ('company', 'product')
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    conversion_factor = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal('0.000001')
    )
    unit_code = serializers.CharField(required=False, max_length=20)
    description = serializers.CharField(required=False, max_length=200)
    presentation_type = serializers.ChoiceField(
        choices=PresentationType.choices, required=False, write_only=True
    )
    custom_code = serializers.CharField(required=False, allow_blank=False, max_length=20, write_only=True)
    custom_name = serializers.CharField(required=False, allow_blank=False, max_length=100, write_only=True)

    class Meta:
        model = ProductPurchasePresentation
        fields = (
            'id', 'company', 'company_name', 'product', 'product_name', 'unit_code',
            'description', 'conversion_factor', 'presentation_type', 'custom_code', 'custom_name',
            'status', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company_name', 'product_name', 'status', 'created_at', 'updated_at',
        )
        validators = []

    def validate_unit_code(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError('Informe o código da apresentação.')
        return value

    def validate_description(self, value):
        value = ' '.join(value.split())
        if not value:
            raise serializers.ValidationError('Informe a descrição da apresentação.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        company = attrs.get('company', getattr(self.instance, 'company', None))
        product = attrs.get('product', getattr(self.instance, 'product', None))
        factor = attrs.get(
            'conversion_factor', getattr(self.instance, 'conversion_factor', None)
        )
        presentation_type = attrs.pop('presentation_type', None)
        custom_code = attrs.pop('custom_code', '')
        custom_name = attrs.pop('custom_name', '')
        if presentation_type:
            if presentation_type == PresentationType.OTHER and (not custom_code or not custom_name):
                raise serializers.ValidationError({
                    'custom_code': 'Informe a sigla e o nome da apresentação personalizada.'
                })
            quantity = PresentationPreset._quantity_text(factor)
            unit_code = custom_code.strip().upper() if presentation_type == PresentationType.OTHER else presentation_type
            friendly_name = (
                ' '.join(custom_name.split())
                if presentation_type == PresentationType.OTHER
                else PresentationType(presentation_type).label
            )
            attrs['unit_code'] = unit_code
            attrs['description'] = f'{friendly_name} com {quantity} {product.unit.upper()}'
        unit_code = attrs.get('unit_code', getattr(self.instance, 'unit_code', ''))
        description = attrs.get('description', getattr(self.instance, 'description', ''))
        errors = {}
        if company and product and company.pk != product.company_id:
            errors['product'] = 'O produto deve pertencer à empresa da apresentação.'
        if product and unit_code and factor is not None:
            duplicate = ProductPurchasePresentation.objects.filter(
                product=product, unit_code__iexact=unit_code, conversion_factor=factor
            )
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                errors['non_field_errors'] = 'Esta apresentação já existe para o produto.'
        if not unit_code:
            errors['unit_code'] = 'Escolha o código da apresentação.'
        if not description:
            errors['description'] = 'A descrição da apresentação é obrigatória.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        return _save_product_purchase_presentation(**validated_data)

    def update(self, instance, validated_data):
        return _save_product_purchase_presentation(instance=instance, **validated_data)


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
        max_digits=18, decimal_places=6, min_value=Decimal('0.000001'), required=False
    )
    unit_code = serializers.CharField(required=False, max_length=20)
    description = serializers.CharField(required=False, allow_blank=False, max_length=200)
    presentation_preset = serializers.PrimaryKeyRelatedField(
        queryset=PresentationPreset.objects.all(), required=False, allow_null=True
    )
    purchase_presentation = serializers.PrimaryKeyRelatedField(
        queryset=ProductPurchasePresentation.objects.all(), required=False, allow_null=True
    )
    presentation_type = serializers.ChoiceField(
        choices=PresentationType.choices, required=False, write_only=True
    )
    custom_code = serializers.CharField(required=False, allow_blank=False, max_length=20, write_only=True)
    custom_name = serializers.CharField(required=False, allow_blank=False, max_length=100, write_only=True)
    save_as_preset = serializers.BooleanField(required=False, default=False, write_only=True)

    class Meta:
        model = ProductSupplierUnit
        fields = (
            'id', 'company', 'company_name', 'product_supplier', 'product_name',
            'supplier_name', 'purchase_presentation', 'unit_code', 'description', 'conversion_factor', 'barcode',
            'is_default', 'status', 'presentation_preset', 'presentation_type', 'custom_code',
            'custom_name', 'save_as_preset', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'company_name', 'product_name', 'supplier_name', 'status',
            'created_at', 'updated_at',
        )
        validators = []

    def validate_unit_code(self, value):
        return value.strip().upper()

    def validate_description(self, value):
        value = ' '.join(value.split())
        if not value:
            raise serializers.ValidationError('Informe a descrição da apresentação.')
        return value

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
        preset = attrs.get('presentation_preset')
        presentation = attrs.get(
            'purchase_presentation', getattr(self.instance, 'purchase_presentation', None)
        )
        presentation_type = attrs.get('presentation_type')
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
        if preset and presentation_type:
            errors['presentation_preset'] = 'Escolha um padrão existente ou informe um novo tipo.'
        if presentation and relation and (
            presentation.company_id != relation.company_id
            or presentation.product_id != relation.product_id
        ):
            errors['purchase_presentation'] = 'A apresentação deve pertencer ao produto deste fornecedor.'
        elif presentation and presentation.status != Status.ACTIVE:
            errors['purchase_presentation'] = 'A apresentação do produto deve estar ativa.'
        if (
            self.instance
            and self.instance.purchase_presentation_id
            and presentation
            and presentation.pk != self.instance.purchase_presentation_id
        ):
            errors['purchase_presentation'] = 'A apresentação vinculada não pode ser alterada.'
        if not self.instance and not presentation and not preset and not presentation_type:
            legacy_fields = ('unit_code', 'description', 'conversion_factor')
            missing_legacy = [field for field in legacy_fields if attrs.get(field) in (None, '')]
            if missing_legacy and len(missing_legacy) < len(legacy_fields):
                for field in missing_legacy:
                    errors[field] = 'Informe este campo para a apresentação legada.'
            elif missing_legacy:
                errors['presentation_type'] = 'Escolha um padrão ou informe tipo e quantidade por apresentação.'
        if presentation_type == PresentationType.OTHER:
            if not attrs.get('custom_code'):
                errors['custom_code'] = 'Informe a sigla personalizada.'
            if not attrs.get('custom_name'):
                errors['custom_name'] = 'Informe o nome personalizado.'
        if not self.instance and presentation_type and attrs.get('conversion_factor') is None:
            errors['conversion_factor'] = 'Informe a quantidade por apresentação.'
        if preset and company and preset.company_id != company.pk:
            errors['presentation_preset'] = 'O padrão deve pertencer à mesma empresa.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        return _save_product_supplier_unit(**validated_data)

    def update(self, instance, validated_data):
        return _save_product_supplier_unit(instance=instance, **validated_data)


class PresentationPresetSerializer(ImmutableTenantSerializer):
    conversion_factor = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal('0.000001')
    )
    code = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    usage_count = serializers.SerializerMethodField(read_only=True)
    custom_code = serializers.CharField(required=False, allow_blank=True, max_length=20)
    custom_name = serializers.CharField(required=False, allow_blank=True, max_length=100)

    class Meta:
        model = PresentationPreset
        fields = (
            'id', 'company', 'presentation_type', 'conversion_factor', 'code', 'description',
            'custom_code', 'custom_name', 'usage_count', 'status', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'code', 'description', 'status', 'created_at', 'updated_at')
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        presentation_type = attrs.get('presentation_type', getattr(self.instance, 'presentation_type', None))
        custom_code = attrs.get('custom_code', getattr(self.instance, 'custom_code', ''))
        custom_name = attrs.get('custom_name', getattr(self.instance, 'custom_name', ''))
        errors = {}
        if presentation_type == PresentationType.OTHER:
            if not custom_code.strip():
                errors['custom_code'] = 'Informe a sigla personalizada.'
            if not custom_name.strip():
                errors['custom_name'] = 'Informe o nome personalizado.'
        elif custom_code or custom_name:
            errors['presentation_type'] = 'Campos personalizados são exclusivos do tipo Outro.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        return _save_presentation_preset(**validated_data)

    def update(self, instance, validated_data):
        return _save_presentation_preset(instance=instance, **validated_data)

    def get_usage_count(self, instance):
        return instance.product_supplier_units.count()
