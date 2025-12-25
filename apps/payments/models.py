from django.db import models
from django.conf import settings
from apps.orders.models import Order
import uuid


class Payment(models.Model):
    """Payment transaction model."""
    
    PAYMENT_METHOD_CHOICES = [
        ('stripe', 'Stripe'),
        ('vnpay', 'VNPay'),
        ('momo', 'MoMo'),
        ('cod', 'Thanh toán khi nhận hàng'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Đang chờ'),
        ('processing', 'Đang xử lý'),
        ('completed', 'Hoàn thành'),
        ('failed', 'Thất bại'),
        ('cancelled', 'Đã hủy'),
        ('refunded', 'Đã hoàn tiền'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name='Đơn hàng'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name='Người dùng'
    )
    
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        verbose_name='Phương thức thanh toán'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name='Số tiền'
    )
    currency = models.CharField(max_length=3, default='VND', verbose_name='Đơn vị tiền')
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Trạng thái'
    )
    
    # External payment info
    transaction_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        verbose_name='Mã giao dịch'
    )
    payment_url = models.TextField(blank=True, null=True, verbose_name='URL thanh toán')
    
    # Provider-specific data
    provider_data = models.JSONField(default=dict, blank=True, verbose_name='Dữ liệu từ nhà cung cấp')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name='Thời gian thanh toán')
    
    class Meta:
        verbose_name = 'Thanh toán'
        verbose_name_plural = 'Thanh toán'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payment {self.id} - {self.order.order_number} - {self.get_status_display()}"
    
    def mark_as_completed(self):
        """Mark payment as completed and update order. Idempotent operation."""
        from django.utils import timezone
        
        # Idempotency check: prevent double processing
        if self.status == 'completed':
            import logging
            logger = logging.getLogger('apps.payments')
            logger.info(f"Payment {self.id} already completed. Skipping duplicate call.")
            return False
        
        self.status = 'completed'
        self.paid_at = timezone.now()
        self.save()
        
        # Update order payment status
        self.order.payment_status = 'paid'
        self.order.save()
        
        return True
    
    def mark_as_failed(self, reason=None):
        """Mark payment as failed."""
        self.status = 'failed'
        if reason:
            self.provider_data['failure_reason'] = reason
        self.save()


class PaymentRefund(models.Model):
    """Payment refund model."""
    
    STATUS_CHOICES = [
        ('pending', 'Đang chờ'),
        ('processing', 'Đang xử lý'),
        ('completed', 'Hoàn thành'),
        ('failed', 'Thất bại'),
    ]
    
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='refunds',
        verbose_name='Thanh toán'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name='Số tiền hoàn'
    )
    reason = models.TextField(verbose_name='Lý do hoàn tiền')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Trạng thái'
    )
    refund_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Mã hoàn tiền'
    )
    provider_data = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Hoàn tiền'
        verbose_name_plural = 'Hoàn tiền'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Refund {self.id} - {self.payment.order.order_number}"
