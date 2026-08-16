from django.contrib import admin

from .models import CashMovement, CashRegister, CashSession


@admin.register(CashRegister)
class CashRegisterAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'status', 'created_at')
    list_filter = ('status', 'branch__company', 'branch')
    search_fields = ('name', 'branch__name', 'branch__company__trade_name')


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = (
        'cash_register', 'branch', 'status', 'opened_by', 'opened_at', 'closed_at'
    )
    list_filter = ('status', 'branch__company', 'branch')
    readonly_fields = (
        'cash_register', 'branch', 'opened_by', 'opened_at', 'opening_amount',
        'status', 'closed_by', 'closed_at', 'closing_expected_amount',
        'closing_amount_informed', 'closing_difference', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CashMovement)
class CashMovementAdmin(admin.ModelAdmin):
    list_display = (
        'cash_session', 'movement_type', 'withdrawal_category', 'beneficiary_user',
        'amount', 'user', 'created_at',
    )
    list_filter = ('movement_type', 'withdrawal_category', 'cash_session__branch')
    search_fields = ('reason', 'cash_session__cash_register__name', 'user__email')
    readonly_fields = (
        'cash_session', 'movement_type', 'withdrawal_category', 'beneficiary_user',
        'amount', 'user', 'reason',
        'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
