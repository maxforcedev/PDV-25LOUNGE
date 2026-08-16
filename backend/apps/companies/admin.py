from django.contrib import admin

from .models import (
    AccessProfile,
    Branch,
    Company,
    FunctionalPermission,
    UserBranchAccess,
    UserCompanyAccess,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('trade_name', 'legal_name', 'cnpj', 'status')
    list_filter = ('status',)
    search_fields = ('trade_name', 'legal_name', 'cnpj')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'cnpj', 'status')
    list_filter = ('status',)
    search_fields = ('name', 'company__trade_name', 'cnpj')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserCompanyAccess)
class UserCompanyAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'access_profile', 'is_active')
    list_filter = ('access_profile', 'is_active')
    search_fields = ('user__email', 'company__trade_name')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserBranchAccess)
class UserBranchAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'branch', 'access_profile', 'is_active')
    list_filter = ('access_profile', 'is_active')
    search_fields = ('user__email', 'branch__name', 'branch__company__trade_name')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FunctionalPermission)
class FunctionalPermissionAdmin(admin.ModelAdmin):
    list_display = ('code', 'module', 'label', 'status')
    list_filter = ('module', 'status')
    search_fields = ('code', 'label')


@admin.register(AccessProfile)
class AccessProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'is_system', 'status')
    list_filter = ('is_system', 'status')
    search_fields = ('name', 'company__trade_name')
    filter_horizontal = ('permissions',)
