from django.contrib import admin

from .models import PresentationPreset, ProductSupplier, ProductSupplierUnit, Supplier


class ReadOnlySupplierAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Supplier)
class SupplierAdmin(ReadOnlySupplierAdminMixin, admin.ModelAdmin):
    list_display = ('trade_name', 'legal_name', 'company', 'tax_id', 'status')
    list_filter = ('status', 'company')
    search_fields = ('trade_name', 'legal_name', 'tax_id', 'email', 'phone')


class ProductSupplierUnitInline(ReadOnlySupplierAdminMixin, admin.TabularInline):
    model = ProductSupplierUnit
    extra = 0


@admin.register(ProductSupplier)
class ProductSupplierAdmin(ReadOnlySupplierAdminMixin, admin.ModelAdmin):
    list_display = ('product', 'supplier', 'is_preferred', 'is_exclusive', 'status')
    list_filter = ('status', 'is_preferred', 'is_exclusive', 'company')
    search_fields = ('product__name', 'supplier__trade_name', 'supplier_code')
    inlines = (ProductSupplierUnitInline,)


@admin.register(ProductSupplierUnit)
class ProductSupplierUnitAdmin(ReadOnlySupplierAdminMixin, admin.ModelAdmin):
    list_display = (
        'product_supplier', 'unit_code', 'conversion_factor', 'is_default', 'status'
    )
    list_filter = ('status', 'is_default', 'company')
    search_fields = ('unit_code', 'description', 'barcode')


@admin.register(PresentationPreset)
class PresentationPresetAdmin(ReadOnlySupplierAdminMixin, admin.ModelAdmin):
    list_display = ('code', 'description', 'company', 'conversion_factor', 'status')
    list_filter = ('presentation_type', 'status', 'company')
    search_fields = ('code', 'description', 'custom_code', 'custom_name')
