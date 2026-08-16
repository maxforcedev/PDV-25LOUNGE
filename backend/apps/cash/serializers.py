from decimal import Decimal

from rest_framework import serializers

from .models import (
    CashMovement,
    CashRegister,
    CashSession,
    CashSessionStatus,
    WithdrawalCategory,
)
from .services import calculate_expected_amount, movement_totals


class StrictMoneyField(serializers.DecimalField):
    def to_internal_value(self, data):
        if isinstance(data, float):
            self.fail('invalid')
        return super().to_internal_value(data)


class CashRegisterSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    company = serializers.IntegerField(source='branch.company_id', read_only=True)
    company_name = serializers.CharField(
        source='branch.company.trade_name', read_only=True
    )
    open_session = serializers.SerializerMethodField()

    class Meta:
        model = CashRegister
        fields = (
            'id', 'branch', 'branch_name', 'company', 'company_name', 'name',
            'status', 'open_session', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'branch_name', 'company', 'company_name', 'status',
            'open_session', 'created_at', 'updated_at',
        )

    def validate(self, attrs):
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        if self.instance and 'branch' in attrs and branch != self.instance.branch:
            raise serializers.ValidationError({'branch': 'A filial nao pode ser alterada.'})
        current = getattr(self.context['request'], 'branch_context', None)
        if current and (not branch or current.pk != branch.pk):
            raise serializers.ValidationError({'branch': 'Filial fora do contexto atual.'})
        return attrs

    def validate_name(self, value):
        value = ' '.join(value.split())
        branch_id = self.initial_data.get('branch') or getattr(
            self.instance, 'branch_id', None
        )
        queryset = CashRegister.objects.filter(branch_id=branch_id, name__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if branch_id and queryset.exists():
            raise serializers.ValidationError('Ja existe um caixa com este nome na filial.')
        return value

    def get_open_session(self, obj):
        sessions = getattr(obj, 'current_open_sessions', None)
        session = sessions[0] if sessions else obj.sessions.filter(status='open').select_related(
            'opened_by'
        ).first()
        if not session:
            return None
        return {
            'id': session.pk,
            'status': session.status,
            'opened_at': session.opened_at,
            'opening_amount': f'{session.opening_amount:.2f}',
            'opened_by_name': session.opened_by.get_full_name().strip()
            or session.opened_by.email,
        }


class CashSessionSerializer(serializers.ModelSerializer):
    cash_register_name = serializers.CharField(
        source='cash_register.name', read_only=True
    )
    register_name = serializers.CharField(source='cash_register.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    company = serializers.IntegerField(source='branch.company_id', read_only=True)
    company_name = serializers.CharField(
        source='branch.company.trade_name', read_only=True
    )
    opened_by_name = serializers.SerializerMethodField()
    closed_by_name = serializers.SerializerMethodField()
    expected_amount = serializers.SerializerMethodField()
    manual_entries = serializers.SerializerMethodField()
    withdrawals = serializers.SerializerMethodField()

    class Meta:
        model = CashSession
        fields = (
            'id', 'cash_register', 'cash_register_name', 'register_name', 'branch',
            'branch_name', 'company', 'company_name', 'opened_by', 'opened_by_name',
            'opened_at', 'opening_amount', 'status', 'closed_by', 'closed_by_name',
            'closed_at', 'closing_expected_amount', 'closing_amount_informed',
            'closing_difference', 'expected_amount', 'manual_entries', 'withdrawals',
            'created_at', 'updated_at',
        )
        read_only_fields = fields

    def _totals(self, obj):
        if hasattr(obj, 'manual_entries_total'):
            return obj.manual_entries_total, obj.withdrawals_total
        totals = movement_totals(obj)
        return totals['manual_entries'], totals['withdrawals']

    def get_opened_by_name(self, obj):
        return obj.opened_by.get_full_name().strip() or obj.opened_by.email

    def get_closed_by_name(self, obj):
        if not obj.closed_by:
            return None
        return obj.closed_by.get_full_name().strip() or obj.closed_by.email

    def get_expected_amount(self, obj):
        value = (
            calculate_expected_amount(obj)
            if obj.status == CashSessionStatus.OPEN
            else obj.closing_expected_amount
        )
        return f'{value:.2f}'

    def get_manual_entries(self, obj):
        return f'{self._totals(obj)[0]:.2f}'

    def get_withdrawals(self, obj):
        return f'{self._totals(obj)[1]:.2f}'


class CashMovementSerializer(serializers.ModelSerializer):
    cash_register = serializers.IntegerField(
        source='cash_session.cash_register_id', read_only=True
    )
    register_name = serializers.CharField(
        source='cash_session.cash_register.name', read_only=True
    )
    branch = serializers.IntegerField(source='cash_session.branch_id', read_only=True)
    branch_name = serializers.CharField(
        source='cash_session.branch.name', read_only=True
    )
    user_name = serializers.SerializerMethodField()
    category = serializers.CharField(source='withdrawal_category', read_only=True)
    category_label = serializers.CharField(
        source='get_withdrawal_category_display', read_only=True
    )
    beneficiary = serializers.SerializerMethodField()

    class Meta:
        model = CashMovement
        fields = (
            'id', 'cash_session', 'cash_register', 'register_name', 'branch',
            'branch_name', 'movement_type', 'amount', 'user', 'user_name', 'reason',
            'category', 'category_label', 'beneficiary', 'created_at',
        )
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.get_full_name().strip() or obj.user.email

    def get_beneficiary(self, obj):
        user = obj.beneficiary_user
        if not user:
            return None
        return {
            'id': user.pk,
            'name': user.get_full_name().strip() or user.email or f'Usuario {user.pk}',
            'user_type': user.user_type,
            'can_login': user.can_login,
        }


class OpenSessionSerializer(serializers.Serializer):
    cash_register = serializers.IntegerField(min_value=1)
    opening_amount = StrictMoneyField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00')
    )


class ManualEntryRequestSerializer(serializers.Serializer):
    amount = StrictMoneyField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.01')
    )
    reason = serializers.CharField(trim_whitespace=True, allow_blank=False)


class WithdrawalRequestSerializer(ManualEntryRequestSerializer):
    category = serializers.ChoiceField(choices=WithdrawalCategory.choices)
    beneficiary_user = serializers.IntegerField(
        min_value=1, required=False, allow_null=True
    )


class CashBeneficiarySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.SerializerMethodField()
    user_type = serializers.CharField(read_only=True)

    def get_name(self, user):
        return user.get_full_name().strip() or user.email or f'Usuario {user.pk}'


class CloseSessionSerializer(serializers.Serializer):
    closing_amount_informed = StrictMoneyField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00')
    )
