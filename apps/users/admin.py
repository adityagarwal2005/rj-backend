from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.users.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-created_at"]
    list_display = ["email", "full_name", "role", "is_active", "is_staff", "created_at"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["email", "full_name", "phone"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name", "phone")}),
        ("Role & permissions", {
            "fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        ("Important dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "password1", "password2", "role"),
        }),
    )
