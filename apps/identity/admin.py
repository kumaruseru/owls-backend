from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserAddress


class UserAddressInline(admin.TabularInline):
    model = UserAddress
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'username', 'full_name', 'is_email_verified', 'is_staff', 'is_deleted', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'is_email_verified', 'is_deleted')
    search_fields = ('email', 'username', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    inlines = [UserAddressInline]
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Thông tin thêm', {'fields': ('phone', 'avatar', 'is_email_verified', 'email_verified_at', 'is_2fa_enabled')}),
        ('Địa chỉ', {'fields': ('address', 'ward', 'district', 'city')}),
        ('Bảo mật', {'fields': ('failed_login_attempts', 'locked_until', 'last_password_change')}),
        ('Trạng thái', {'fields': ('is_deleted', 'deleted_at')}),
    )
    readonly_fields = ('email_verified_at', 'failed_login_attempts', 'locked_until', 'last_password_change', 'deleted_at')


@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'recipient_name', 'phone', 'city', 'is_default')
    list_filter = ('is_default', 'city')
    search_fields = ('user__email', 'recipient_name', 'phone', 'address')
