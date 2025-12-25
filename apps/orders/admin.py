from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    """Inline admin for order items."""
    model = OrderItem
    extra = 0
    readonly_fields = ('subtotal',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin configuration for Order."""
    
    list_display = (
        'order_number', 'user', 'recipient_name', 'status',
        'payment_method', 'payment_status', 'total', 'created_at'
    )
    list_filter = ('status', 'payment_status', 'payment_method', 'created_at')
    search_fields = ('order_number', 'user__email', 'recipient_name', 'phone')
    readonly_fields = ('order_number', 'subtotal', 'total', 'created_at', 'updated_at')
    list_editable = ('status', 'payment_status')
    ordering = ('-created_at',)
    
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Thông tin đơn hàng', {
            'fields': ('order_number', 'user', 'status')
        }),
        ('Thông tin giao hàng', {
            'fields': ('recipient_name', 'phone', 'email', 'address', 'city', 'district', 'ward', 'note')
        }),
        ('Thanh toán', {
            'fields': ('payment_method', 'payment_status')
        }),
        ('Tổng tiền', {
            'fields': ('subtotal', 'shipping_fee', 'discount', 'total')
        }),
        ('Thời gian', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Admin configuration for OrderItem."""
    
    list_display = ('order', 'product_name', 'quantity', 'price', 'subtotal')
    list_filter = ('order__status',)
    search_fields = ('order__order_number', 'product_name')
