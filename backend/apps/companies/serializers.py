from decimal import Decimal

from rest_framework import serializers

from .models import AccessProfile, Branch, BranchSettings, Company, FunctionalPermission, Status
from .selectors import (
    accessible_branches,
    company_permission_codes,
    user_has_company_permission,
)
from .services import create_branch_with_access, create_company_with_matrix
from .validators import normalize_cnpj, validate_cnpj


class BranchSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    settings_summary = serializers.SerializerMethodField()
    cnpj = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        max_length=18,
        required=False,
        validators=[validate_cnpj],
    )
    address = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=200),
        required=True,
    )

    class Meta:
        model = Branch
        fields = (
            'id',
            'company',
            'company_name',
            'name',
            'cnpj',
            'phone',
            'email',
            'address',
            'status',
            'is_matrix',
            'settings_summary',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'company_name',
            'status',
            'is_matrix',
            'settings_summary',
            'created_at',
            'updated_at',
        )

    def get_settings_summary(self, branch):
        try:
            settings = branch.settings
        except BranchSettings.DoesNotExist:
            return None
        return {
            'allow_negative_stock': settings.allow_negative_stock,
            'service_fee_rate': f'{settings.service_fee_rate:.2f}',
            'commission_rate': f'{settings.commission_rate:.2f}',
            'fixed_daily_cost': f'{settings.fixed_daily_cost:.2f}',
        }

    def validate(self, attrs):
        request = self.context['request']
        company = attrs.get('company', getattr(self.instance, 'company', None))
        if self.instance and 'company' in attrs and attrs['company'] != self.instance.company:
            raise serializers.ValidationError({'company': 'A empresa da filial nao pode ser alterada.'})
        permission = 'branches.change' if self.instance else 'branches.add'
        if not company or not user_has_company_permission(request.user, company.id, permission):
            raise serializers.ValidationError({'company': 'Empresa fora do contexto autorizado.'})
        if not self.instance and company.status != Status.ACTIVE:
            raise serializers.ValidationError({'company': 'Nao e possivel criar filial em empresa inativa.'})
        if attrs.get('status') == Status.ACTIVE and company.status != Status.ACTIVE:
            raise serializers.ValidationError({'status': 'Ative a empresa antes de ativar a filial.'})
        return attrs

    def validate_cnpj(self, value):
        return normalize_cnpj(value)

    def validate_address(self, value):
        allowed_fields = {
            'street',
            'number',
            'complement',
            'neighborhood',
            'city',
            'state',
            'zip_code',
        }
        unknown_fields = set(value) - allowed_fields
        if unknown_fields:
            raise serializers.ValidationError('O endereco possui campos desconhecidos.')
        normalized = {
            key: item.strip() if isinstance(item, str) else item
            for key, item in value.items()
        }
        required_fields = {
            'zip_code': 'CEP',
            'street': 'logradouro',
            'number': 'numero',
            'neighborhood': 'bairro',
            'city': 'cidade',
            'state': 'UF',
        }
        missing = [label for key, label in required_fields.items() if not normalized.get(key)]
        if missing:
            raise serializers.ValidationError(
                f'Preencha os campos obrigatorios: {", ".join(missing)}.'
            )
        zip_code = ''.join(character for character in normalized['zip_code'] if character.isdigit())
        if len(zip_code) != 8:
            raise serializers.ValidationError('O CEP deve conter 8 digitos.')
        state = normalized['state'].upper()
        if len(state) != 2 or not state.isalpha():
            raise serializers.ValidationError('Informe uma UF valida com 2 letras.')
        normalized['zip_code'] = zip_code
        normalized['state'] = state
        return normalized

    def create(self, validated_data):
        return create_branch_with_access(
            creator=self.context['request'].user,
            **validated_data,
        )


class BranchSettingsSerializer(serializers.ModelSerializer):
    allow_negative_stock = serializers.BooleanField(required=False)
    service_fee_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal('0.00'), max_value=Decimal('100.00'),
        coerce_to_string=True, required=False,
    )
    commission_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal('0.00'), max_value=Decimal('100.00'),
        coerce_to_string=True, required=False,
    )
    fixed_daily_cost = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00'),
        coerce_to_string=True, required=False,
    )

    class Meta:
        model = BranchSettings
        fields = (
            'id', 'branch', 'allow_negative_stock', 'service_fee_rate',
            'commission_rate', 'fixed_daily_cost', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'branch', 'created_at', 'updated_at')


class CompanySerializer(serializers.ModelSerializer):
    branches = serializers.SerializerMethodField()
    cnpj = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        max_length=18,
        required=False,
        validators=[validate_cnpj],
    )

    class Meta:
        model = Company
        fields = (
            'id',
            'trade_name',
            'legal_name',
            'cnpj',
            'email',
            'phone',
            'status',
            'branches',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'status', 'branches', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['status'] = Status.ACTIVE
        return create_company_with_matrix(
            creator=self.context['request'].user,
            **validated_data,
        )

    def validate_cnpj(self, value):
        cnpj = normalize_cnpj(value)
        queryset = Company.objects.filter(cnpj=cnpj)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if cnpj and queryset.exists():
            raise serializers.ValidationError('Ja existe uma empresa com este CNPJ.')
        return cnpj

    def validate_trade_name(self, value):
        trade_name = ' '.join(value.split())
        queryset = Company.objects.filter(trade_name__iexact=trade_name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('Ja existe uma empresa com este nome fantasia.')
        return trade_name

    def validate_legal_name(self, value):
        legal_name = ' '.join(value.split())
        queryset = Company.objects.filter(legal_name__iexact=legal_name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('Ja existe uma empresa com esta razao social.')
        return legal_name

    def get_branches(self, company):
        visible_branches = getattr(company, 'visible_branches', None)
        if visible_branches is None:
            visible_branches = accessible_branches(
                self.context['request'].user
            ).filter(company=company)
        return BranchSerializer(
            visible_branches,
            many=True,
            context=self.context,
        ).data


class FunctionalPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunctionalPermission
        fields = ('code', 'module', 'label', 'description')


class AccessProfileSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    permission_codes = serializers.SlugRelatedField(
        source='permissions',
        slug_field='code',
        queryset=FunctionalPermission.objects.filter(status=Status.ACTIVE),
        many=True,
        required=False,
    )

    class Meta:
        model = AccessProfile
        fields = (
            'id',
            'company',
            'company_name',
            'name',
            'description',
            'is_system',
            'status',
            'permission_codes',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'company_name',
            'is_system',
            'status',
            'created_at',
            'updated_at',
        )

    def validate(self, attrs):
        request = self.context['request']
        company = attrs.get('company', getattr(self.instance, 'company', None))
        if self.instance and 'company' in attrs and company != self.instance.company:
            raise serializers.ValidationError(
                {'company': 'A empresa do perfil nao pode ser alterada.'}
            )
        if not company:
            raise serializers.ValidationError({'company': 'Informe a empresa do perfil.'})

        permissions = attrs.get('permissions')
        if permissions is not None and not request.user.is_superuser:
            actor_codes = company_permission_codes(request.user, company.id)
            requested_codes = {permission.code for permission in permissions}
            if requested_codes - actor_codes:
                raise serializers.ValidationError(
                    {'permission_codes': 'Voce nao pode conceder permissoes que nao possui.'}
                )
        return attrs
