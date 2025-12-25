from django.contrib import admin
from .models import Category, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    """Inline admin for product images."""
    model = ProductImage
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin configuration for Category."""
    
    list_display = ('name', 'parent', 'is_active', 'product_count', 'created_at')
    list_filter = ('is_active', 'parent')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin configuration for Product."""
    
    list_display = (
        'name', 'category', 'price', 'sale_price', 
        'stock', 'is_active', 'is_featured', 'created_at'
    )
    list_filter = ('is_active', 'is_featured', 'category', 'created_at')
    search_fields = ('name', 'description', 'sku')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active', 'is_featured', 'stock')
    ordering = ('-created_at',)
    
    inlines = [ProductImageInline]
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('name', 'slug', 'category', 'sku')
        }),
        ('Mô tả', {
            'fields': ('short_description', 'description')
        }),
        ('Giá & Tồn kho', {
            'fields': ('price', 'sale_price', 'stock')
        }),
        ('Trạng thái', {
            'fields': ('is_active', 'is_featured')
        }),
    )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Admin configuration for ProductImage."""
    
    list_display = ('product', 'is_primary', 'order')
    list_filter = ('is_primary',)
    search_fields = ('product__name',)
