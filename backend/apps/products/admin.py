from django.contrib import admin

from .models import Category, Product, ProductComponent


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
