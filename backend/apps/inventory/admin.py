from django.contrib import admin

from .models import Stock, StockMovement


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'branch', 'current_quantity', 'current_content', 'minimum_quantity',
        'average_unit_cost', 'last_unit_cost', 'updated_at',
    )
    list_filter = ('branch__company', 'branch')
    search_fields = ('product__name', 'product__internal_code')
    readonly_fields = (
        'current_quantity', 'current_content', 'average_unit_cost', 'last_unit_cost',
        'created_at', 'updated_at',
    )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'stock', 'movement_type', 'quantity', 'final_quantity', 'user'
    )
    list_filter = ('movement_type', 'stock__branch__company', 'stock__branch')
    search_fields = ('stock__product__name', 'stock__product__internal_code', 'reason')
    readonly_fields = (
        'stock', 'movement_type', 'previous_quantity', 'quantity', 'final_quantity',
        'previous_content', 'content_quantity', 'final_content',
        'unit_cost_snapshot', 'user', 'reason', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
