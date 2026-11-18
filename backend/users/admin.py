from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    ordering = ('email',)
    list_display = ('email', 'full_name', 'role', 'is_senior', 'is_active')
    list_filter = ('role', 'is_active', 'client_type')
    search_fields = ('email', 'full_name', 'phone')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Профиль', {'fields': ('full_name', 'phone', 'client_type', 'company_name', 'consent_at')}),
        ('Права', {'fields': ('role', 'is_senior', 'is_active', 'is_staff', 'is_superuser', 'groups',
                              'user_permissions')}),
    )
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('email', 'role', 'password1', 'password2')}),)
