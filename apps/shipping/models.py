"""Shipping app models - Shipping providers and tracking."""
from django.db import models
from apps.sales.models import Order


class ShippingProvider(models.Model):
    """Nhà cung cấp vận chuyển."""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    logo = models.ImageField(upload_to='shipping/', blank=True, null=True)
    base_fee = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Nhà vận chuyển'
        verbose_name_plural = 'Nhà vận chuyển'
    
    def __str__(self):
        return self.name


class Shipment(models.Model):
    """Theo dõi vận chuyển."""
    
    STATUS_CHOICES = [
        ('pending', 'Chờ lấy hàng'),
        ('picked_up', 'Đã lấy hàng'),
        ('in_transit', 'Đang vận chuyển'),
        ('out_for_delivery', 'Đang giao'),
        ('delivered', 'Đã giao'),
        ('failed', 'Giao thất bại'),
    ]
    
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='shipment')
    provider = models.ForeignKey(ShippingProvider, on_delete=models.SET_NULL, null=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Vận chuyển'
        verbose_name_plural = 'Vận chuyển'
    
    def __str__(self):
        return f"Shipment for {self.order.order_number}"
