from django.contrib import admin

from .models import Payment, PaymentMethod, Promotion, Sale, SaleItem


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'status', 'is_system')
    list_filter = ('status', 'is_system', 'company')


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'discount_type', 'discount_value', 'starts_at', 'ends_at', 'status')
    list_filter = ('status', 'discount_type', 'company')
    filter_horizontal = ('products', 'categories')


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('sale_number', 'operation_type', 'channel', 'branch', 'status', 'total', 'created_at')
    list_filter = ('operation_type', 'channel', 'status', 'company', 'branch')
    readonly_fields = (
        'company', 'branch', 'cash_session', 'sale_number', 'operation_type', 'channel', 'status',
        'created_by', 'beneficiary_user', 'subtotal', 'promotion_discount_total',
        'discount', 'charged_amount',
        'total', 'cancelled_at', 'cancelled_by', 'cancellation_reason',
        'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ImmutableHistoryAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(SaleItem, ImmutableHistoryAdmin)
admin.site.register(Payment, ImmutableHistoryAdmin)
