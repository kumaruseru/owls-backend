"""Sales app models - Cart and Order."""
import uuid
import time
from django.db import models
from django.conf import settings
from apps.catalog.models import Product


class Cart(models.Model):
    """Giỏ hàng."""
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='cart'
    )
    session_key = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Giỏ hàng'
        verbose_name_plural = 'Giỏ hàng'
    
    def __str__(self):
        if self.user:
            return f"Giỏ hàng của {self.user.email}"
        return f"Giỏ hàng (session)"
    
    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())
    
    @property
    def subtotal(self):
        return sum(item.subtotal for item in self.items.all())
    
    @property
    def total(self):
        return self.subtotal
    
    def clear(self):
        self.items.all().delete()
    
    def merge_with(self, other_cart):
        for item in other_cart.items.all():
            existing = self.items.filter(product=item.product).first()
            if existing:
                existing.quantity += item.quantity
                existing.save()
            else:
                item.cart = self
                item.save()
        other_cart.delete()


class CartItem(models.Model):
    """Sản phẩm trong giỏ hàng."""
    
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Sản phẩm trong giỏ'
        verbose_name_plural = 'Sản phẩm trong giỏ'
        unique_together = ['cart', 'product']
    
    def __str__(self):
        return f"{self.quantity}x {self.product.name}"
    
    @property
    def unit_price(self):
        return self.product.current_price
    
    @property
    def subtotal(self):
        return self.unit_price * self.quantity
    
    def save(self, *args, **kwargs):
        if self.quantity > self.product.stock:
            self.quantity = self.product.stock
        super().save(*args, **kwargs)


class Order(models.Model):
    """Đơn hàng."""
    
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
        ('bank_transfer', 'Chuyển khoản'),
        ('momo', 'Ví MoMo'),
        ('vnpay', 'VNPay'),
        ('stripe', 'Stripe'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Shipping info
    recipient_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    ward = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    
    # Payment info
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cod')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    
    # Amounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    
    # GHN Shipping
    tracking_code = models.CharField(max_length=50, blank=True, help_text="GHN order code / tracking number")
    to_district_id = models.IntegerField(null=True, blank=True, help_text="GHN district ID for shipping")
    to_ward_code = models.CharField(max_length=20, blank=True, help_text="GHN ward code for shipping")
    
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
        timestamp = str(int(time.time()))[-8:]
        unique_id = str(uuid.uuid4().int)[:4]
        return f"OWL{timestamp}{unique_id}"
    
    def calculate_totals(self):
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
        return self.status in ['pending', 'confirmed']
    
    def cancel(self):
        if not self.can_cancel():
            return False
        from django.db.models import F
        for item in self.items.all():
            if item.product:
                Product.objects.filter(id=item.product.id).update(stock=F('stock') + item.quantity)
        self.status = 'cancelled'
        self.save()
        return True


class OrderItem(models.Model):
    """Sản phẩm trong đơn hàng."""
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255)
    product_image = models.URLField(blank=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=0)
    
    class Meta:
        verbose_name = 'Sản phẩm trong đơn'
        verbose_name_plural = 'Sản phẩm trong đơn'
    
    def __str__(self):
        return f"{self.quantity}x {self.product_name}"
    
    @property
    def subtotal(self):
        return self.price * self.quantity
