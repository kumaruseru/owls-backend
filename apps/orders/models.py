from django.db import models
from django.conf import settings
from apps.products.models import Product
import uuid
from decimal import Decimal


class Order(models.Model):
    """Order model."""
    
    STATUS_CHOICES = [
        ('pending', 'Chờ xác nhận'),
        ('confirmed', 'Đã xác nhận'),
        ('processing', 'Đang xử lý'),
        ('shipping', 'Đang giao hàng'),
        ('delivered', 'Đã giao hàng'),
        ('cancelled', 'Đã hủy'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Chưa thanh toán'),
        ('paid', 'Đã thanh toán'),
        ('refunded', 'Đã hoàn tiền'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('cod', 'Thanh toán khi nhận hàng'),
        ('bank_transfer', 'Chuyển khoản ngân hàng'),
        ('momo', 'Ví MoMo'),
        ('vnpay', 'VNPay'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders',
        verbose_name='Người đặt'
    )
    order_number = models.CharField(
        max_length=20, 
        unique=True, 
        editable=False,
        verbose_name='Mã đơn hàng'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Trạng thái'
    )
    
    # Shipping info
    recipient_name = models.CharField(max_length=100, verbose_name='Tên người nhận')
    phone = models.CharField(max_length=15, verbose_name='Số điện thoại')
    email = models.EmailField(blank=True, verbose_name='Email')
    address = models.TextField(verbose_name='Địa chỉ')
    city = models.CharField(max_length=100, verbose_name='Thành phố')
    district = models.CharField(max_length=100, verbose_name='Quận/Huyện')
    ward = models.CharField(max_length=100, blank=True, verbose_name='Phường/Xã')
    note = models.TextField(blank=True, verbose_name='Ghi chú')
    
    # Payment info
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cod',
        verbose_name='Phương thức thanh toán'
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid',
        verbose_name='Trạng thái thanh toán'
    )
    
    # Amounts
    subtotal = models.DecimalField(
        max_digits=12, 
        decimal_places=0, 
        default=0,
        verbose_name='Tạm tính'
    )
    shipping_fee = models.DecimalField(
        max_digits=12, 
        decimal_places=0, 
        default=0,
        verbose_name='Phí vận chuyển'
    )
    discount = models.DecimalField(
        max_digits=12, 
        decimal_places=0, 
        default=0,
        verbose_name='Giảm giá'
    )
    total = models.DecimalField(
        max_digits=12, 
        decimal_places=0, 
        default=0,
        verbose_name='Tổng cộng'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Đơn hàng'
        verbose_name_plural = 'Đơn hàng'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Đơn hàng #{self.order_number}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_order_number():
        """Generate unique order number."""
        import time
        timestamp = str(int(time.time()))[-8:]
        unique_id = str(uuid.uuid4().int)[:4]
        return f"OWL{timestamp}{unique_id}"
    
    def calculate_totals(self):
        """Calculate order totals from items."""
        self.subtotal = sum(item.subtotal for item in self.items.all())
        self.total = self.subtotal + self.shipping_fee - self.discount
        self.save()
    
    @property
    def full_address(self):
        parts = [self.address, self.ward, self.district, self.city]
        return ', '.join(filter(None, parts))
    
    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())
    
    def can_cancel(self):
        """Check if order can be cancelled."""
        return self.status in ['pending', 'confirmed']


class OrderItem(models.Model):
    """Order item model."""
    
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Đơn hàng'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Sản phẩm'
    )
    product_name = models.CharField(max_length=255, verbose_name='Tên sản phẩm')
    product_image = models.URLField(blank=True, verbose_name='Hình ảnh')
    quantity = models.PositiveIntegerField(verbose_name='Số lượng')
    price = models.DecimalField(max_digits=12, decimal_places=0, verbose_name='Đơn giá')
    
    class Meta:
        verbose_name = 'Sản phẩm trong đơn'
        verbose_name_plural = 'Sản phẩm trong đơn'
    
    def __str__(self):
        return f"{self.quantity}x {self.product_name}"
    
    @property
    def subtotal(self):
        return self.price * self.quantity
