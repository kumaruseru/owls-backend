from rest_framework import serializers
from .models import Category, Product, ProductImage


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for product categories."""
    
    product_count = serializers.ReadOnlyField()
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = (
            'id', 'name', 'slug', 'description', 'image', 
            'parent', 'is_active', 'product_count', 'children'
        )
    
    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        return CategoryListSerializer(children, many=True).data


class CategoryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for category listing."""
    
    product_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'image', 'product_count')


class ProductImageSerializer(serializers.ModelSerializer):
    """Serializer for product images."""
    
    class Meta:
        model = ProductImage
        fields = ('id', 'image', 'alt_text', 'is_primary', 'order')


class ProductListSerializer(serializers.ModelSerializer):
    """Serializer for product listing (lightweight)."""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    current_price = serializers.ReadOnlyField()
    discount_percent = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    primary_image = serializers.ImageField(read_only=True)
    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'short_description',
            'price', 'sale_price', 'current_price', 'discount_percent',
            'category', 'category_name', 'stock', 'is_in_stock',
            'is_featured', 'primary_image', 'average_rating', 'review_count',
            'created_at'
        )


class ProductDetailSerializer(serializers.ModelSerializer):
    """Serializer for product detail view."""
    
    category = CategoryListSerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    current_price = serializers.ReadOnlyField()
    discount_percent = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'description', 'short_description',
            'price', 'sale_price', 'current_price', 'discount_percent',
            'category', 'stock', 'sku', 'is_in_stock',
            'is_active', 'is_featured', 'images',
            'average_rating', 'review_count',
            'created_at', 'updated_at'
        )
