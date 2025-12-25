from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator
from decimal import Decimal


class Category(models.Model):
    """Product category model."""
    
    name = models.CharField(max_length=100, verbose_name='Tên danh mục')
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, verbose_name='Mô tả')
    image = models.ImageField(upload_to='categories/', blank=True, null=True, verbose_name='Hình ảnh')
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='children',
        verbose_name='Danh mục cha'
    )
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Danh mục'
        verbose_name_plural = 'Danh mục'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    @property
    def product_count(self):
        return self.products.filter(is_active=True).count()


class Product(models.Model):
    """Product model."""
    
    name = models.CharField(max_length=255, verbose_name='Tên sản phẩm')
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(verbose_name='Mô tả')
    short_description = models.CharField(max_length=500, blank=True, verbose_name='Mô tả ngắn')
    
    price = models.DecimalField(
        max_digits=12, 
        decimal_places=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Giá gốc'
    )
    sale_price = models.DecimalField(
        max_digits=12, 
        decimal_places=0, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Giá khuyến mãi'
    )
    
    category = models.ForeignKey(
        Category, 
        on_delete=models.CASCADE, 
        related_name='products',
        verbose_name='Danh mục'
    )
    
    stock = models.PositiveIntegerField(default=0, verbose_name='Tồn kho')
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name='Mã SKU')
    
    is_active = models.BooleanField(default=True, verbose_name='Đang bán')
    is_featured = models.BooleanField(default=False, verbose_name='Sản phẩm nổi bật')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Sản phẩm'
        verbose_name_plural = 'Sản phẩm'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    @property
    def current_price(self):
        """Return sale price if available, otherwise regular price."""
        return self.sale_price if self.sale_price else self.price
    
    @property
    def discount_percent(self):
        """Calculate discount percentage."""
        if self.sale_price and self.price > 0:
            return int(((self.price - self.sale_price) / self.price) * 100)
        return 0
    
    @property
    def is_in_stock(self):
        return self.stock > 0
    
    @property
    def primary_image(self):
        """Get primary product image."""
        primary = self.images.filter(is_primary=True).first()
        if primary:
            return primary.image
        first_image = self.images.first()
        return first_image.image if first_image else None
    
    @property
    def average_rating(self):
        """Calculate average rating from reviews."""
        from django.db.models import Avg
        avg = self.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else 0
    
    @property
    def review_count(self):
        return self.reviews.count()


class ProductImage(models.Model):
    """Product image model."""
    
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='images',
        verbose_name='Sản phẩm'
    )
    image = models.ImageField(upload_to='products/', verbose_name='Hình ảnh')
    alt_text = models.CharField(max_length=255, blank=True, verbose_name='Alt text')
    is_primary = models.BooleanField(default=False, verbose_name='Ảnh chính')
    order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    
    class Meta:
        verbose_name = 'Hình ảnh sản phẩm'
        verbose_name_plural = 'Hình ảnh sản phẩm'
        ordering = ['order', '-is_primary']
    
    def __str__(self):
        return f"Image for {self.product.name}"
    
    def save(self, *args, **kwargs):
        # Ensure only one primary image per product
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)
