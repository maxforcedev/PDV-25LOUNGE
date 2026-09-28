from django.contrib import admin

from .models import PaymentAttempt, PaymentIntent, PaymentProvider, PaymentProviderConnection, PaymentTerminal


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'integration_type', 'status', 'updated_at')
    search_fields = ('code', 'name')
    list_filter = ('status', 'integration_type')


@admin.register(PaymentProviderConnection)
class PaymentProviderConnectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'branch', 'provider', 'environment', 'status', 'updated_at')
    list_filter = ('status', 'environment', 'provider')
    search_fields = ('name',)


@admin.register(PaymentTerminal)
class PaymentTerminalAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'connection', 'pos_device', 'external_id', 'status', 'updated_at')
    list_filter = ('status', 'connection__provider')
    search_fields = ('name', 'external_id')


class HistoricalPaymentAdmin(admin.ModelAdmin):
    readonly_fields = tuple()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentIntent)
class PaymentIntentAdmin(HistoricalPaymentAdmin):
    list_display = ('id', 'company', 'branch', 'provider_connection', 'terminal', 'amount', 'status', 'created_at')
    list_filter = ('status', 'origin_type', 'provider_connection__provider')
    search_fields = ('id', 'origin_id', 'idempotency_key')
    readonly_fields = tuple(field.name for field in PaymentIntent._meta.fields)


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(HistoricalPaymentAdmin):
    list_display = ('id', 'intent', 'attempt_number', 'provider_connection', 'terminal', 'amount', 'status', 'created_at')
    list_filter = ('status', 'provider_connection__provider')
    search_fields = ('id', 'provider_transaction_id', 'provider_order_id', 'authorization_code', 'nsu')
    readonly_fields = tuple(field.name for field in PaymentAttempt._meta.fields)
