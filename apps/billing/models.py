"""Billing app models - Payment and Refund."""
import uuid
from django.db import models
from django.conf import settings
from apps.sales.models import Order


class Payment(models.Model):
    """Giao dịch thanh toán."""
    
    PAYMENT_METHOD_CHOICES = [
        ('stripe', 'Stripe'),
        ('vnpay', 'VNPay'),
        ('momo', 'MoMo'),
        ('cod', 'COD'),
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
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    currency = models.CharField(max_length=3, default='VND')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    transaction_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    payment_url = models.TextField(blank=True, null=True)
    provider_data = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Thanh toán'
        verbose_name_plural = 'Thanh toán'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payment {self.id} - {self.order.order_number}"
    
    def mark_as_completed(self):
        """Đánh dấu thanh toán thành công. Idempotent."""
        if self.status == 'completed':
            return False
        
        from django.utils import timezone
        self.status = 'completed'
        self.paid_at = timezone.now()
        self.save()
        
        self.order.payment_status = 'paid'
        should_create_ghn = False
        if self.order.status == 'pending':
            self.order.status = 'confirmed'
            should_create_ghn = True
        self.order.save()
        
        # Create GHN shipping order when payment confirmed
        if should_create_ghn and self.order.to_district_id and self.order.to_ward_code:
            try:
                from apps.shipping.services import GHNService
                import logging
                logger = logging.getLogger('apps.billing')
                
                # Calculate total weight (500g per item as default)
                total_weight = sum(item.quantity * 500 for item in self.order.items.all())
                
                result = GHNService.create_order(
                    order=self.order,
                    to_district_id=self.order.to_district_id,
                    to_ward_code=self.order.to_ward_code,
                    weight=total_weight,
                    cod_amount=0,  # Prepaid order, no COD
                    note=self.order.note,
                )
                
                if result.get('success'):
                    self.order.tracking_code = result.get('order_code', '')
                    self.order.save()
                    logger.info(f"GHN order created for {self.order.order_number}: {self.order.tracking_code}")
                else:
                    logger.error(f"Failed to create GHN order for {self.order.order_number}: {result.get('error')}")
            except Exception as e:
                import logging
                logger = logging.getLogger('apps.billing')
                logger.exception(f"Error creating GHN order for {self.order.order_number}: {e}")
        
        return True
    
    def mark_as_failed(self, reason=None):
        """Đánh dấu thanh toán thất bại."""
        self.status = 'failed'
        if reason:
            self.provider_data['failure_reason'] = reason
        self.save()
        
        if self.order.status == 'pending':
            self.order.cancel()


class PaymentRefund(models.Model):
    """Hoàn tiền."""
    
    STATUS_CHOICES = [
        ('pending', 'Đang chờ'),
        ('processing', 'Đang xử lý'),
        ('completed', 'Hoàn thành'),
        ('failed', 'Thất bại'),
    ]
    
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    refund_id = models.CharField(max_length=255, blank=True, null=True)
    provider_data = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Hoàn tiền'
        verbose_name_plural = 'Hoàn tiền'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Refund {self.id} - {self.payment.order.order_number}"
