from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'knowledge_points', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('bio', 'knowledge_points')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('bio', 'knowledge_points')}),
    )


admin.site.register(CustomUser, CustomUserAdmin)
