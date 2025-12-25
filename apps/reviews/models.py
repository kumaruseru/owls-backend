from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.products.models import Product


class Review(models.Model):
    """Product review model."""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='Người đánh giá'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='Sản phẩm'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='Đánh giá'
    )
    title = models.CharField(max_length=200, blank=True, verbose_name='Tiêu đề')
    comment = models.TextField(verbose_name='Nhận xét')
    is_verified_purchase = models.BooleanField(
        default=False, 
        verbose_name='Đã mua hàng'
    )
    is_approved = models.BooleanField(default=True, verbose_name='Đã duyệt')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Đánh giá'
        verbose_name_plural = 'Đánh giá'
        ordering = ['-created_at']
        unique_together = ['user', 'product']
    
    def __str__(self):
        return f"{self.user.email} - {self.product.name}: {self.rating}⭐"
    
    def save(self, *args, **kwargs):
        # Check if user has purchased this product
        from apps.orders.models import Order, OrderItem
        has_purchased = OrderItem.objects.filter(
            order__user=self.user,
            product=self.product,
            order__status='delivered'
        ).exists()
        self.is_verified_purchase = has_purchased
        super().save(*args, **kwargs)
