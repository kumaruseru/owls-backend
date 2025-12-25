from django.contrib import admin
from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    """Inline admin for cart items."""
    model = CartItem
    extra = 0
    readonly_fields = ('unit_price', 'subtotal')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Admin configuration for Cart."""
    
    list_display = ('id', 'user', 'session_key', 'total_items', 'total', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__email', 'session_key')
    readonly_fields = ('total_items', 'subtotal', 'total')
    
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """Admin configuration for CartItem."""
    
    list_display = ('cart', 'product', 'quantity', 'unit_price', 'subtotal')
    list_filter = ('created_at',)
    search_fields = ('product__name', 'cart__user__email')
