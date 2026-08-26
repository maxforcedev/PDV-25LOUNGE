from django.contrib import admin

from .models import (
    PayableInstallment,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
)


class ReadOnlyPurchaseAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ReadOnlyPurchaseAdminMixin, admin.ModelAdmin):
    list_display = (
        'order_number', 'order_type', 'status', 'branch', 'supplier',
        'payable_total', 'created_at',
    )
    list_filter = ('order_type', 'status', 'company', 'branch')
    search_fields = ('order_number', 'supplier__trade_name', 'document_number', 'document_key')


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(ReadOnlyPurchaseAdminMixin, admin.ModelAdmin):
    list_display = ('purchase_order', 'line_number', 'product_name', 'ordered_quantity')
    list_filter = ('purchase_order__company', 'purchase_order__branch')


@admin.register(PurchaseReceipt)
class PurchaseReceiptAdmin(ReadOnlyPurchaseAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'purchase_order', 'branch', 'confirmed_by', 'confirmed_at')
    list_filter = ('company', 'branch')


@admin.register(PurchaseReceiptItem)
class PurchaseReceiptItemAdmin(ReadOnlyPurchaseAdminMixin, admin.ModelAdmin):
    list_display = (
        'receipt', 'product_name_snapshot', 'received_quantity', 'stock_quantity',
        'stock_content_quantity', 'stock_package_content_snapshot',
    )


@admin.register(PayableInstallment)
class PayableInstallmentAdmin(ReadOnlyPurchaseAdminMixin, admin.ModelAdmin):
    list_display = (
        'purchase_order', 'installment_number', 'amount', 'due_date', 'status'
    )
    list_filter = ('status', 'purchase_order__company', 'purchase_order__branch')
