from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.users.models import Profile, User


class ProfileInline(admin.StackedInline):  # type: ignore[type-arg]  # not subscriptable at runtime
    model = Profile
    can_delete = False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    inlines = (ProfileInline,)
    ordering = ("-created_at",)
    list_display = ("email", "is_active", "is_staff", "created_at")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
