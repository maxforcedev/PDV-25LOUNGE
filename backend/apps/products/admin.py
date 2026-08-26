from django.contrib import admin

from .models import (
    Category, FractionableProductConfig, Product, ProductBranchConfig,
    ProductComponent, ProductFractionComponent, ProductProductionDestination,
    ProductionDestination,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'status', 'updated_at')
    list_filter = ('status', 'company')
    search_fields = ('name',)


class ProductComponentInline(admin.TabularInline):
    model = ProductComponent
    fk_name = 'parent_product'
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'internal_code', 'company', 'inventory_behavior', 'status')
    list_filter = ('status', 'inventory_behavior', 'company')
    search_fields = ('name', 'internal_code', 'barcode')
    inlines = (ProductComponentInline,)


@admin.register(ProductComponent)
class ProductComponentAdmin(admin.ModelAdmin):
    list_display = ('parent_product', 'component_product', 'quantity')


class ReadOnlyProductConfigurationAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ProductBranchConfig, ReadOnlyProductConfigurationAdmin)
admin.site.register(FractionableProductConfig, ReadOnlyProductConfigurationAdmin)
admin.site.register(ProductFractionComponent, ReadOnlyProductConfigurationAdmin)
admin.site.register(ProductionDestination, ReadOnlyProductConfigurationAdmin)
admin.site.register(ProductProductionDestination, ReadOnlyProductConfigurationAdmin)
