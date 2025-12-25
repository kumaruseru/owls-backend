from django.db import models
from django.conf import settings
from apps.products.models import Product


class Cart(models.Model):
    """Shopping cart model."""
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='cart',
        verbose_name='Người dùng'
    )
    session_key = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        verbose_name='Session key'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Giỏ hàng'
        verbose_name_plural = 'Giỏ hàng'
    
    def __str__(self):
        if self.user:
            return f"Giỏ hàng của {self.user.email}"
        return f"Giỏ hàng (session: {self.session_key[:8]}...)"
    
    @property
    def total_items(self):
        """Total number of items in cart."""
        return sum(item.quantity for item in self.items.all())
    
    @property
    def subtotal(self):
        """Subtotal before any discounts."""
        return sum(item.subtotal for item in self.items.all())
    
    @property
    def total(self):
        """Total amount."""
        return self.subtotal
    
    def clear(self):
        """Remove all items from cart."""
        self.items.all().delete()
    
    def merge_with(self, other_cart):
        """Merge another cart into this one."""
        for item in other_cart.items.all():
            existing_item = self.items.filter(product=item.product).first()
            if existing_item:
                existing_item.quantity += item.quantity
                existing_item.save()
            else:
                item.cart = self
                item.save()
        other_cart.delete()


class CartItem(models.Model):
    """Cart item model."""
    
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Giỏ hàng'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name='Sản phẩm'
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name='Số lượng')
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
        """Get current price of product."""
        return self.product.current_price
    
    @property
    def subtotal(self):
        """Calculate subtotal for this item."""
        return self.unit_price * self.quantity
    
    def save(self, *args, **kwargs):
        # Ensure quantity doesn't exceed stock
        if self.quantity > self.product.stock:
            self.quantity = self.product.stock
        super().save(*args, **kwargs)
