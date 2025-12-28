from rest_framework import serializers
from .models import Category, Product, ProductImage


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'description', 'image', 'parent', 'product_count')


class CategoryMinimalSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views or nested usage.
    """
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug')


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ('id', 'image', 'alt_text', 'is_primary', 'order')


class ProductListSerializer(serializers.ModelSerializer):
    category = CategoryMinimalSerializer(read_only=True)
    current_price = serializers.SerializerMethodField()
    discount_percent = serializers.ReadOnlyField()
    primary_image = serializers.SerializerMethodField()
    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    
    class Meta:
        model = Product
        fields = ('id', 'name', 'slug', 'short_description', 'price', 'sale_price',
                  'current_price', 'discount_percent', 'category', 'stock', 'brand',
                  'is_featured', 'primary_image', 'average_rating', 'review_count', 'is_in_stock', 'is_active')

    def get_primary_image(self, obj):
        """
        Optimized access using prefetched objects to avoid N+1 queries.
        Assuming 'images' is prefetched in the ViewSet.
        """
        # Try to use the prefetch cache usually populated by prefetch_related
        # Accessing obj.images.all() keeps the queryset cache if prefetch was done.
        # DO NOT use filter() here as it hits DB.
        
        images = list(obj.images.all())
        if not images:
            return None
            
        # Find primary in memory
        primary = next((img for img in images if img.is_primary), None)
        
        if primary:
            # Return absolute URL if request context available, or typically FileField returns url automatically 
            # but here we return specific object property or letting DRF handle logic if we returned object.
            # Returning string URL is safest for manual field.
            try:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(primary.image.url)
                return primary.image.url
            except ValueError:
                return None
                
        # Fallback to first image
        try:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(images[0].image.url)
            return images[0].image.url
        except ValueError:
            return None

    def get_current_price(self, obj):
        """
        Use effective_price if annotated (View Optimization), otherwise calculate.
        """
        if hasattr(obj, 'effective_price'):
            return obj.effective_price
        return obj.sale_price if obj.sale_price else obj.price


class ProductDetailSerializer(ProductListSerializer):
    # For detail view, we might want full category info? 
    # Let's keep minimal for consistency unless needed.
    # We DO add full images list.
    images = ProductImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True) # Full category for detail page
    
    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ('description', 'sku', 'color', 'attributes', 'images')


class ProductCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products with category ID and image handling."""
    image = serializers.ImageField(write_only=True, required=False)
    
    class Meta:
        model = Product
        fields = ('id', 'name', 'slug', 'description', 'price', 'sale_price',
                  'category', 'stock', 'brand', 'is_featured', 'image', 'sku', 'color', 'is_active', 'attributes')
        read_only_fields = ('id', 'slug')

    def validate_attributes(self, value):
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except ValueError:
                raise serializers.ValidationError("Invalid JSON format for attributes")
        return value

    def create(self, validated_data):
        image = validated_data.pop('image', None)
        product = Product.objects.create(**validated_data)
        
        if image:
            ProductImage.objects.create(product=product, image=image, is_primary=True)
            
        return product

    def update(self, instance, validated_data):
        image = validated_data.pop('image', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if image:
            # Create new image and set as primary. 
            # The ProductImage model's save() method will automatically unset is_primary for other images.
            ProductImage.objects.create(product=instance, image=image, is_primary=True)
            
        return instance
