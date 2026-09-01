from decimal import Decimal

from rest_framework import serializers

from apps.base.exceptions import DomainValidationError
from .models import (
    AccessProfile, Branch, BranchSettings, Company, Customer, FunctionalPermission, Status,
    UserBranchAccess, UserCommissionOverride, UserCompanyAccess, UserPermissionBlock,
)
from .rbac import PERMISSION_SCOPE_BRANCH, permission_scope
from .selectors import (
    accessible_branches,
    company_permission_codes,
    inherited_permission_codes,
    user_has_branch_permission,
    user_has_company_permission,
)
from .services import create_branch_with_access, create_company_with_matrix
from .validators import normalize_cnpj, validate_cnpj


class CustomerSerializer(serializers.ModelSerializer):
    duplicate_warning = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Customer
        fields = (
            'id', 'company', 'name', 'phone', 'document', 'email', 'birth_date', 'notes',
            'status', 'duplicate_warning', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'status', 'duplicate_warning', 'created_at', 'updated_at')

    def validate(self, attrs):
        company = attrs.get('company', getattr(self.instance, 'company', None))
        request = self.context['request']
        permission = 'customers.change' if self.instance else 'customers.add'
        if not company or not user_has_company_permission(request.user, company.pk, permission):
            raise serializers.ValidationError({'company': 'Empresa fora do contexto autorizado.'})
        if self.instance and company.pk != self.instance.company_id:
            raise serializers.ValidationError({'company': 'A empresa do cliente não pode ser alterada.'})
        return attrs

    def get_duplicate_warning(self, customer):
        matches = Customer.objects.filter(company_id=customer.company_id).exclude(pk=customer.pk)
        from django.db.models import Q
        query = Q()
        if customer.phone:
            query |= Q(phone=customer.phone)
        if customer.email:
            query |= Q(email=customer.email)
        if not query:
            return None
        duplicate = matches.filter(query).order_by('id').first()
        if not duplicate:
            return None
        return {'customer_id': duplicate.pk, 'name': duplicate.name, 'message': 'Possível cliente duplicado; nenhum merge foi realizado.'}


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
        validators = []
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
            'address_pending',
            'settings_summary',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'company_name',
            'status',
            'is_matrix',
            'address_pending',
            'settings_summary',
            'created_at',
            'updated_at',
        )

    def get_settings_summary(self, branch):
        try:
            settings = branch.settings
        except BranchSettings.DoesNotExist:
            return None
        result = {
            'allow_negative_stock': settings.allow_negative_stock,
            'service_fee_rate': f'{settings.service_fee_rate:.2f}',
            'fixed_daily_cost': f'{settings.fixed_daily_cost:.2f}',
        }
        from apps.inventory.models import Stock
        negative_count = Stock.objects.filter(
            branch=branch, current_quantity__lt=0
        ).count()
        result['negative_stock_count'] = negative_count
        result['negative_stock_state'] = (
            'clear' if not negative_count else
            'enabled_with_negatives' if settings.allow_negative_stock else
            'legacy_inconsistent'
        )
        request = self.context.get('request')
        if request and (
            request.user.is_superuser
            or user_has_branch_permission(request.user, branch.pk, 'commissions.view')
            or user_has_branch_permission(
                request.user, branch.pk, 'commissions.change_branch_default'
            )
        ):
            result['commission_rate'] = f'{settings.commission_rate:.2f}'
        return result

    def validate(self, attrs):
        request = self.context['request']
        company = attrs.get('company', getattr(self.instance, 'company', None))
        context_company_id = request.query_params.get('company')
        if not context_company_id:
            context_branch_id = request.headers.get('X-Branch-ID')
            if context_branch_id:
                context_company_id = Branch.objects.filter(pk=context_branch_id).values_list('company_id', flat=True).first()
        try:
            context_company_id = int(context_company_id) if context_company_id else None
        except (TypeError, ValueError) as error:
            raise serializers.ValidationError({'company': 'Informe uma empresa válida.'}) from error
        if context_company_id and company and context_company_id != company.pk:
            raise serializers.ValidationError({'company': 'A filial deve pertencer à empresa selecionada.'})
        if self.instance and 'company' in attrs and attrs['company'] != self.instance.company:
            raise serializers.ValidationError({'company': 'A empresa da filial nao pode ser alterada.'})
        permission = 'branches.change' if self.instance else 'branches.add'
        if not company or not user_has_company_permission(request.user, company.id, permission):
            raise serializers.ValidationError({'company': 'Empresa fora do contexto autorizado.'})
        if not self.instance and company.status != Status.ACTIVE:
            raise serializers.ValidationError({'company': 'Não é possível criar filial em empresa inativa.'})
        if attrs.get('status') == Status.ACTIVE and company.status != Status.ACTIVE:
            raise serializers.ValidationError({'status': 'Ative a empresa antes de ativar a filial.'})
        name = attrs.get('name')
        if name and company:
            duplicate = Branch.objects.filter(company=company, name=name)
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError({
                    'name': 'Já existe uma filial com esse nome nesta empresa.'
                })
        if self.instance and 'address' in attrs and attrs['address'] != self.instance.address:
            initial_matrix_completion = bool(
                self.instance.is_matrix and self.instance.address_pending
            )
            if not request.user.is_superuser and not initial_matrix_completion:
                raise serializers.ValidationError({
                    'address': 'O endereco concluido so pode ser alterado pelo superusuario da plataforma.'
                })
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
            raise serializers.ValidationError('Informe uma UF válida com 2 letras.')
        normalized['zip_code'] = zip_code
        normalized['state'] = state
        return normalized

    def create(self, validated_data):
        return create_branch_with_access(
            creator=self.context['request'].user,
            **validated_data,
        )

    def update(self, instance, validated_data):
        completing_address = bool(
            instance.is_matrix and instance.address_pending and 'address' in validated_data
        )
        instance = super().update(instance, validated_data)
        if completing_address:
            instance.address_pending = False
            instance.save(update_fields=('address_pending', 'updated_at'))
        return instance


class BranchSettingsSerializer(serializers.ModelSerializer):
    negative_stock_count = serializers.SerializerMethodField()
    negative_stock_state = serializers.SerializerMethodField()
    feature_flags = serializers.SerializerMethodField()
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
    uses_tables = serializers.BooleanField(required=False)
    uses_commands = serializers.BooleanField(required=False)
    uses_counter = serializers.BooleanField(required=False)
    uses_consumption = serializers.BooleanField(required=False)
    uses_cash_register = serializers.BooleanField(required=False)
    charges_service_fee = serializers.BooleanField(required=False)
    default_table_quantity = serializers.IntegerField(min_value=1, max_value=500, required=False)
    table_range_start = serializers.IntegerField(min_value=1, max_value=500, required=False)
    table_range_end = serializers.IntegerField(min_value=1, max_value=500, required=False)
    default_table_seats = serializers.IntegerField(min_value=0, required=False)
    default_table_prefix = serializers.CharField(max_length=50, required=False, allow_blank=True)
    consumption_limit_enabled = serializers.BooleanField(required=False)
    command_consumption_limit = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'), required=False, allow_null=True)
    table_consumption_limit = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'), required=False, allow_null=True)

    class Meta:
        model = BranchSettings
        fields = (
            'id', 'branch', 'allow_negative_stock', 'service_fee_rate',
            'commission_rate', 'fixed_daily_cost',
            'uses_tables', 'uses_commands', 'uses_counter',
            'uses_consumption', 'uses_cash_register', 'charges_service_fee',
            'default_table_quantity', 'default_table_seats', 'default_table_prefix',
            'table_range_start', 'table_range_end',
            'consumption_limit_enabled', 'command_consumption_limit', 'table_consumption_limit',
            'feature_flags',
            'created_at', 'updated_at',
            'negative_stock_count', 'negative_stock_state',
        )
        read_only_fields = (
            'id', 'branch', 'feature_flags',
            'created_at', 'updated_at',
            'negative_stock_count', 'negative_stock_state',
        )

    def get_feature_flags(self, settings):
        return settings.feature_flags()

    def get_negative_stock_count(self, settings):
        from apps.inventory.models import Stock
        return Stock.objects.filter(
            branch=settings.branch, current_quantity__lt=0
        ).count()

    def get_negative_stock_state(self, settings):
        count = self.get_negative_stock_count(settings)
        if not count:
            return 'clear'
        return 'enabled_with_negatives' if settings.allow_negative_stock else 'legacy_inconsistent'

    def _entitled_features(self, company):
        try:
            from apps.saas.services import get_entitled_features
            return set(get_entitled_features(company))
        except Exception:
            return set()

    def validate(self, attrs):
        range_start = attrs.get(
            'table_range_start', self.instance.table_range_start if self.instance else 1,
        )
        range_end = attrs.get(
            'table_range_end', self.instance.table_range_end if self.instance else 20,
        )
        if range_end < range_start or range_end - range_start >= 500:
            raise serializers.ValidationError({
                'table_range_end': 'Informe um intervalo entre 1 e 500 mesas.'
            })
        dependent_features = {
            'uses_counter': 'Balcão',
            'uses_consumption': 'Consumação',
            'uses_commands': 'Comandas',
        }
        effective_cash_register = attrs.get(
            'uses_cash_register',
            self.instance.uses_cash_register if self.instance else False,
        )
        enabled_dependents = [
            field for field in dependent_features
            if attrs.get(field, getattr(self.instance, field, False))
        ]
        dependency_errors = {}
        if not effective_cash_register:
            for field in enabled_dependents:
                if attrs.get(field) is True:
                    dependency_errors[field] = (
                        f'{dependent_features[field]} requer Caixa habilitado nesta filial.'
                    )
            if attrs.get('uses_cash_register') is False and enabled_dependents:
                labels = ', '.join(dependent_features[field] for field in enabled_dependents)
                dependency_errors['uses_cash_register'] = (
                    f'Não é possível desabilitar Caixa enquanto {labels} estiver habilitado.'
                )
        if dependency_errors:
            raise serializers.ValidationError(dependency_errors)

        request = self.context.get('request')
        commission_changed = bool(
            self.instance
            and 'commission_rate' in attrs
            and attrs['commission_rate'] != self.instance.commission_rate
        )
        if request and commission_changed:
            branch = self.instance.branch if self.instance else None
            if branch and not user_has_branch_permission(
                request.user, branch.pk, 'commissions.change_branch_default'
            ):
                raise serializers.ValidationError({'commission_rate': 'Você não possui permissão para alterar comissão padrão.'})
        if (
            self.instance
            and self.instance.allow_negative_stock
            and attrs.get('allow_negative_stock') is False
        ):
            from apps.inventory.models import Stock

            negatives = Stock.objects.filter(
                branch=self.instance.branch, current_quantity__lt=0
            ).select_related('product')
            if negatives.exists():
                rows = list(negatives.values('id', 'product_id', 'product__name', 'current_quantity')[:100])
                for row in rows:
                    row['current_quantity'] = str(row['current_quantity'])
                raise DomainValidationError(
                    code='negative_stocks_must_be_regularized',
                    message='Regularize os estoques negativos antes de desativar esta opcao.',
                    details={'count': negatives.count(), 'stocks': rows},
                )
        if (
            self.instance
            and self.instance.uses_commands
            and attrs.get('uses_commands') is False
        ):
            from apps.commands.models import Command, CommandStatus

            open_commands = Command.objects.filter(
                branch=self.instance.branch, status=CommandStatus.OPEN
            )
            if open_commands.exists():
                raise DomainValidationError(
                    code='open_commands_must_be_closed',
                    message='Existem Comandas abertas. Encerre-as antes de desativar o recurso.',
                    details={'count': open_commands.count()},
                )
        if self.instance and request and not request.user.is_superuser:
            company = self.instance.branch.company
            entitled = self._entitled_features(company)
            feature_map = {
                'uses_tables': 'feature.tables',
                'uses_commands': 'feature.commands',
                'uses_counter': 'feature.counter',
                'uses_consumption': 'feature.consumption',
                'uses_cash_register': 'feature.cash_register',
            }
            for field, feature in feature_map.items():
                if attrs.get(field) is True and feature not in entitled:
                    raise serializers.ValidationError(
                        {field: f'O plano não permite a funcionalidade "{feature}".'}
                    )
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and not (
            request.user.is_superuser
            or user_has_branch_permission(
                request.user, instance.branch_id, 'commissions.view'
            )
            or user_has_branch_permission(
                request.user, instance.branch_id, 'commissions.change_branch_default'
            )
        ):
            data.pop('commission_rate', None)
        return data


class CompanySerializer(serializers.ModelSerializer):
    branches = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
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
            'owner',
            'branches',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id', 'status', 'owner', 'branches', 'created_at', 'updated_at'
        )

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

    def get_owner(self, company):
        owner_accesses = getattr(company, 'owner_accesses', None)
        access = (
            owner_accesses[0]
            if owner_accesses
            else UserCompanyAccess.objects.filter(company=company, is_owner=True)
            .select_related('user')
            .first()
        )
        if not access:
            return None
        return {
            'membership_id': access.pk,
            'user_id': access.user_id,
            'name': access.user.get_full_name().strip() or str(access.user),
            'email': access.user.email,
        }


class TransferCompanyOwnerSerializer(serializers.Serializer):
    target_user_id = serializers.IntegerField(min_value=1)
    current_password = serializers.CharField(trim_whitespace=False, write_only=True)
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)


class FunctionalPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunctionalPermission
        fields = ('code', 'module', 'scope', 'label', 'description')


class AccessProfileSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    user_count = serializers.SerializerMethodField()
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
            'receives_commission',
            'commission_rate',
            'permission_codes',
            'user_count',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'company_name',
            'is_system',
            'status',
            'user_count',
            'created_at',
            'updated_at',
        )

    def get_user_count(self, obj):
        if hasattr(obj, '_user_count'):
            return obj._user_count
        return (
            UserBranchAccess.objects.filter(
                access_profile=obj,
                is_active=True,
                user__is_active=True,
                user__archived_at__isnull=True,
            )
            .values('user_id').distinct().count()
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
        commission_fields = {
            field for field in ('receives_commission', 'commission_rate')
            if field in attrs and (
                self.instance is None or attrs[field] != getattr(self.instance, field)
            )
        }
        if commission_fields and not user_has_company_permission(
            request.user, company.id, 'commissions.change_profile'
        ):
            raise serializers.ValidationError({'commission_rate': 'Você não possui permissão para alterar comissão de perfil.'})
        if permissions is not None and not request.user.is_superuser:
            requested_codes = {permission.code for permission in permissions}
            requested_operating = {
                code for code in requested_codes
                if permission_scope(code) == PERMISSION_SCOPE_BRANCH
            }
            requested_company = requested_codes - requested_operating
            actor_company = company_permission_codes(request.user, company.id)
            unauthorized = requested_company - actor_company

            branch_ids = list(UserBranchAccess.objects.filter(
                access_profile=self.instance,
                is_active=True,
            ).values_list('branch_id', flat=True).distinct()) if self.instance else []
            if branch_ids:
                unauthorized.update(
                    code for code in requested_operating
                    if any(
                        not user_has_branch_permission(request.user, branch_id, code)
                        for branch_id in branch_ids
                    )
                )
            else:
                unauthorized.update(
                    code for code in requested_operating
                    if not accessible_branches(request.user, code).filter(
                        company_id=company.id
                    ).exists()
                )
            if unauthorized:
                raise serializers.ValidationError(
                    {'permission_codes': 'Você não pode conceder permissões que não possui.'}
                )
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and not (
            request.user.is_superuser
            or user_has_company_permission(
                request.user, instance.company_id, 'commissions.change_profile'
            )
        ):
            data.pop('receives_commission', None)
            data.pop('commission_rate', None)
        return data

    def validate_commission_rate(self, value):
        if value is not None and not (Decimal('0') <= value <= Decimal('100')):
            raise serializers.ValidationError('A comissão deve estar entre 0 e 100.')
        return value


class UserPermissionBlockSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    permission_code = serializers.SlugRelatedField(
        source='permission', slug_field='code',
        queryset=FunctionalPermission.objects.filter(status=Status.ACTIVE),
    )
    permission_label = serializers.CharField(source='permission.label', read_only=True)
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    revoked_by_name = serializers.SerializerMethodField()

    class Meta:
        model = UserPermissionBlock
        fields = (
            'id', 'company', 'company_name', 'branch', 'branch_name', 'user', 'user_name',
            'permission_code', 'permission_label', 'reason', 'is_active', 'created_by', 'created_by_name',
            'revoked_by', 'revoked_by_name', 'revoked_at', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'is_active', 'created_by', 'revoked_by', 'revoked_at', 'created_at', 'updated_at')

    def validate(self, attrs):
        request = self.context['request']
        company = attrs.get('company')
        branch = attrs.get('branch')
        if branch and branch.company_id != company.id:
            raise serializers.ValidationError({'branch': 'A filial deve pertencer a empresa.'})
        user = attrs.get('user')
        permission = attrs.get('permission')
        if user.is_superuser:
            raise serializers.ValidationError({'user': 'Permissoes de superusuario nao podem ser bloqueadas.'})
        company_access = user.company_accesses.filter(company=company, is_active=True).first()
        if not company_access:
            raise serializers.ValidationError({'user': 'O usuário não possui acesso ativo a esta empresa.'})
        if permission.code not in inherited_permission_codes(
            user, company.id, branch.id if branch else None
        ):
            raise serializers.ValidationError({
                'permission_code': 'Esta permissão não é herdada pelo usuário no escopo selecionado.'
            })
        if UserPermissionBlock.objects.filter(
            company=company,
            branch=branch,
            user=user,
            permission=permission,
            is_active=True,
        ).exists():
            raise serializers.ValidationError({
                'permission_code': 'Esta permissão já está bloqueada no escopo selecionado.'
            })
        if not user_has_company_permission(request.user, company.id, 'user_permission_blocks.change'):
            raise serializers.ValidationError({'company': 'Você não possui permissão para bloquear permissões nesta empresa.'})
        return attrs

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

    def get_user_name(self, block):
        return str(block.user)

    def get_created_by_name(self, block):
        return str(block.created_by) if block.created_by_id else None

    def get_revoked_by_name(self, block):
        return str(block.revoked_by) if block.revoked_by_id else None


class UserCommissionOverrideSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = UserCommissionOverride
        fields = (
            'id', 'branch', 'branch_name', 'user', 'user_name', 'receives_commission',
            'commission_rate', 'updated_by', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'updated_by', 'created_at', 'updated_at')

    def validate(self, attrs):
        request = self.context['request']
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        if not branch:
            raise serializers.ValidationError({'branch': 'Informe a filial.'})
        if self.instance:
            if 'branch' in attrs and attrs['branch'] != self.instance.branch:
                raise serializers.ValidationError({'branch': 'A filial do override nao pode ser alterada.'})
            if 'user' in attrs and attrs['user'] != self.instance.user:
                raise serializers.ValidationError({'user': 'O usuário da configuração individual não pode ser alterado.'})
        if not user_has_branch_permission(request.user, branch.pk, 'commissions.change_user_override'):
            raise serializers.ValidationError({'branch': 'Você não possui permissão para alterar comissão individual nesta filial.'})
        user = attrs.get('user', getattr(self.instance, 'user', None))
        if user and not UserCommissionOverride.target_has_active_branch_access(
            branch.pk, user.pk
        ):
            raise serializers.ValidationError({
                'user': 'O usuário deve estar ativo e possuir acesso e perfil ativos nesta filial.'
            })
        rate = attrs.get('commission_rate', getattr(self.instance, 'commission_rate', None))
        if rate is not None and not (Decimal('0') <= rate <= Decimal('100')):
            raise serializers.ValidationError({'commission_rate': 'A comissão deve estar entre 0 e 100.'})
        return attrs

    def create(self, validated_data):
        validated_data['updated_by'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data['updated_by'] = self.context['request'].user
        return super().update(instance, validated_data)

    def get_user_name(self, override):
        return str(override.user)
