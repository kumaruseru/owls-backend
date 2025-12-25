from django.contrib import admin
from .models import Payment, PaymentRefund


class PaymentRefundInline(admin.TabularInline):
    """Inline admin for payment refunds."""
    model = PaymentRefund
    extra = 0
    readonly_fields = ('refund_id', 'created_at')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin configuration for Payment."""
    
    list_display = (
        'id', 'order', 'user', 'payment_method',
        'amount', 'status', 'transaction_id', 'created_at'
    )
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('id', 'order__order_number', 'user__email', 'transaction_id')
    readonly_fields = ('id', 'transaction_id', 'payment_url', 'provider_data', 'created_at', 'updated_at', 'paid_at')
    list_editable = ('status',)
    ordering = ('-created_at',)
    
    inlines = [PaymentRefundInline]
    
    fieldsets = (
        ('Thông tin giao dịch', {
            'fields': ('id', 'order', 'user', 'payment_method', 'amount', 'currency')
        }),
        ('Trạng thái', {
            'fields': ('status', 'transaction_id', 'payment_url')
        }),
        ('Dữ liệu nhà cung cấp', {
            'fields': ('provider_data',),
            'classes': ('collapse',)
        }),
        ('Thời gian', {
            'fields': ('created_at', 'updated_at', 'paid_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    """Admin configuration for PaymentRefund."""
    
    list_display = ('id', 'payment', 'amount', 'status', 'refund_id', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('payment__id', 'refund_id')
    readonly_fields = ('refund_id', 'provider_data', 'created_at', 'updated_at')
