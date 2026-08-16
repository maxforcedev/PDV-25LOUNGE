from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserChangeForm, UserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User
    ordering = ('email',)
    list_display = (
        'email', 'first_name', 'last_name', 'user_type', 'can_login', 'is_staff',
        'is_active',
    )
    search_fields = ('email', 'first_name', 'last_name')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal information', {'fields': ('first_name', 'last_name', 'user_type')}),
        (
            'Permissions',
            {
                'description': (
                    'O acesso de login e gerenciado pela API para garantir a revogacao '
                    'coerente de senha e acessos.'
                ),
                'fields': (
                    'is_active',
                    'can_login',
                    'is_staff',
                    'is_superuser',
                    'groups',
                    'user_permissions',
                )
            },
        ),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Audit', {'fields': ('created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email', 'password1', 'password2', 'user_type', 'can_login',
                    'is_staff', 'is_active',
                ),
            },
        ),
    )
    readonly_fields = ('can_login', 'created_at', 'updated_at')
