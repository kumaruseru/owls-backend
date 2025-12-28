from django.contrib import admin
from .models import Coupon, Banner


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'is_valid', 'used_count', 'valid_until')
    list_filter = ('discount_type', 'is_active')
    search_fields = ('code',)
    filter_horizontal = ('applicable_products', 'applicable_categories')


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'is_active')
    list_editable = ('order', 'is_active')
