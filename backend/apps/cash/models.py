from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.base.models import BaseModel
from apps.companies.models import Branch


class CashRegisterStatus(models.TextChoices):
    ACTIVE = 'active', 'Ativo'
    INACTIVE = 'inactive', 'Inativo'


class CashSessionStatus(models.TextChoices):
    OPEN = 'open', 'Aberto'
    CLOSED = 'closed', 'Fechado'


class CashMovementType(models.TextChoices):
    MANUAL_ENTRY = 'manual_entry', 'Entrada manual'
    WITHDRAWAL = 'withdrawal', 'Sangria'


class WithdrawalCategory(models.TextChoices):
    DJ = 'dj', 'DJ'
    ARTIST = 'artist', 'Pagode/Artista'
    ADVANCE = 'advance', 'Vale/Adiantamento'
    PROMOTER = 'promoter', 'Promoter'
    SUPPLIER = 'supplier', 'Fornecedor'
    OTHER = 'other', 'Outros'


class ResultEffect(models.TextChoices):
    UNCLASSIFIED = 'unclassified', 'Não classificado'
    OPERATING_EXPENSE = 'operating_expense', 'Despesa operacional'
    NEUTRAL = 'neutral', 'Não afeta o resultado'


class CashRegister(BaseModel):
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='cash_registers'
    )
    name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=10,
        choices=CashRegisterStatus.choices,
        default=CashRegisterStatus.ACTIVE,
    )

    class Meta:
        ordering = ('branch__company__trade_name', 'branch__name', 'name')
        constraints = [
            models.UniqueConstraint(
                F('branch'),
                Lower('name'),
                name='cash_register_branch_name_ci_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.name = ' '.join((self.name or '').split())
        if not self.name:
            raise ValidationError({'name': 'Informe o nome do caixa.'})
        if (
            self.pk
            and self.status == CashRegisterStatus.INACTIVE
            and self.sessions.filter(status=CashSessionStatus.OPEN).exists()
        ):
            raise ValidationError({'status': 'Não é possível inativar um caixa aberto.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.branch} - {self.name}'


class CashSession(BaseModel):
    cash_register = models.ForeignKey(
        CashRegister, on_delete=models.PROTECT, related_name='sessions'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='cash_sessions'
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='opened_cash_sessions',
    )
    opened_at = models.DateTimeField()
    opening_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=10,
        choices=CashSessionStatus.choices,
        default=CashSessionStatus.OPEN,
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='closed_cash_sessions',
        blank=True,
        null=True,
    )
    closed_at = models.DateTimeField(blank=True, null=True)
    closing_expected_amount = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True
    )
    closing_amount_informed = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True
    )
    closing_difference = models.DecimalField(
        max_digits=14, decimal_places=2, blank=True, null=True
    )

    class Meta:
        ordering = ('-opened_at', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=Q(opening_amount__gte=0),
                name='cash_session_opening_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(closing_amount_informed__isnull=True)
                | Q(closing_amount_informed__gte=0),
                name='cash_session_closing_informed_nonnegative',
            ),
            models.UniqueConstraint(
                fields=('cash_register',),
                condition=Q(status=CashSessionStatus.OPEN),
                name='cash_session_one_open_per_register',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=CashSessionStatus.OPEN)
                    & Q(closed_by__isnull=True)
                    & Q(closed_at__isnull=True)
                    & Q(closing_expected_amount__isnull=True)
                    & Q(closing_amount_informed__isnull=True)
                    & Q(closing_difference__isnull=True)
                )
                | (
                    Q(status=CashSessionStatus.CLOSED)
                    & Q(closed_by__isnull=False)
                    & Q(closed_at__isnull=False)
                    & Q(closing_expected_amount__isnull=False)
                    & Q(closing_amount_informed__isnull=False)
                    & Q(closing_difference__isnull=False)
                ),
                name='cash_session_status_closing_coherent',
            ),
        ]

    def clean(self):
        super().clean()
        if self.cash_register_id and self.branch_id:
            if self.cash_register.branch_id != self.branch_id:
                raise ValidationError(
                    {'branch': 'A filial deve ser a mesma do caixa.'}
                )
        closing_values = (
            self.closed_by_id,
            self.closed_at,
            self.closing_expected_amount,
            self.closing_amount_informed,
            self.closing_difference,
        )
        if self.status == CashSessionStatus.OPEN and any(
            value is not None for value in closing_values
        ):
            raise ValidationError({'status': 'Uma sessão aberta não pode ter fechamento.'})
        if self.status == CashSessionStatus.CLOSED and any(
            value is None for value in closing_values
        ):
            raise ValidationError({'status': 'O fechamento da sessão está incompleto.'})
        if self.opening_amount is not None and self.opening_amount < Decimal('0'):
            raise ValidationError({'opening_amount': 'O valor não pode ser negativo.'})
        if (
            self.closing_amount_informed is not None
            and self.closing_amount_informed < Decimal('0')
        ):
            raise ValidationError(
                {'closing_amount_informed': 'O valor não pode ser negativo.'}
            )

    def save(self, *args, **kwargs):
        if self.pk and CashSession.objects.filter(
            pk=self.pk, status=CashSessionStatus.CLOSED
        ).exists():
            raise ValidationError('Sessões de caixa fechadas são imutáveis.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.cash_register} - {self.opened_at:%d/%m/%Y %H:%M}'


class CashMovement(BaseModel):
    cash_session = models.ForeignKey(
        CashSession, on_delete=models.PROTECT, related_name='movements'
    )
    movement_type = models.CharField(max_length=20, choices=CashMovementType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cash_movements',
    )
    reason = models.TextField()
    withdrawal_category = models.CharField(
        max_length=20,
        choices=WithdrawalCategory.choices,
        blank=True,
        null=True,
    )
    beneficiary_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='beneficiary_cash_withdrawals',
        blank=True,
        null=True,
    )
    result_effect = models.CharField(
        max_length=24,
        choices=ResultEffect.choices,
        default=ResultEffect.UNCLASSIFIED,
    )
    operation_reference = models.UUIDField(
        default=uuid.uuid4, db_index=True, editable=False
    )

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name='cash_movement_amount_positive'
            ),
            models.CheckConstraint(
                condition=~Q(reason=''), name='cash_movement_reason_not_empty'
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        movement_type=CashMovementType.MANUAL_ENTRY,
                        withdrawal_category__isnull=True,
                        beneficiary_user__isnull=True,
                        result_effect=ResultEffect.NEUTRAL,
                    )
                    | Q(
                        movement_type=CashMovementType.WITHDRAWAL,
                        withdrawal_category__isnull=False,
                    )
                ),
                name='cash_movement_withdrawal_classification_coherent',
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(
                        withdrawal_category__in=(
                            WithdrawalCategory.DJ,
                            WithdrawalCategory.ARTIST,
                            WithdrawalCategory.ADVANCE,
                            WithdrawalCategory.PROMOTER,
                        )
                    )
                    | Q(beneficiary_user__isnull=False)
                ),
                name='cash_movement_required_beneficiary_coherent',
            ),
            models.UniqueConstraint(
                fields=('cash_session', 'movement_type', 'operation_reference'),
                name='cash_movement_operation_reference_unique',
            ),
        ]

    def clean(self):
        super().clean()
        self.reason = (self.reason or '').strip()
        if not self.reason:
            raise ValidationError({'reason': 'Informe o motivo da movimentação.'})
        if self.amount is not None and self.amount <= Decimal('0'):
            raise ValidationError({'amount': 'O valor deve ser maior que zero.'})
        if self.cash_session_id and CashSession.objects.filter(
            pk=self.cash_session_id, status=CashSessionStatus.CLOSED
        ).exists():
            raise ValidationError(
                {'cash_session': 'Não é possível movimentar uma sessão fechada.'}
            )
        required_beneficiary_categories = {
            WithdrawalCategory.DJ,
            WithdrawalCategory.ARTIST,
            WithdrawalCategory.ADVANCE,
            WithdrawalCategory.PROMOTER,
        }
        if self.movement_type == CashMovementType.MANUAL_ENTRY:
            if self.withdrawal_category or self.beneficiary_user_id:
                raise ValidationError(
                    {'withdrawal_category': 'Entradas não aceitam classificação de sangria.'}
                )
            self.result_effect = ResultEffect.NEUTRAL
        elif self.movement_type == CashMovementType.WITHDRAWAL:
            if not self.withdrawal_category:
                raise ValidationError(
                    {'withdrawal_category': 'Informe a categoria da sangria.'}
                )
            if (
                self.withdrawal_category in required_beneficiary_categories
                and not self.beneficiary_user_id
            ):
                raise ValidationError(
                    {'beneficiary_user': 'Informe o beneficiário desta sangria.'}
                )

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Movimentações de caixa são imutáveis.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Movimentações de caixa são imutáveis.')

    def __str__(self):
        return f'{self.get_movement_type_display()} - {self.amount:.2f}'
