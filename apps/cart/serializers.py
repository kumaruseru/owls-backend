from rest_framework import serializers
from .models import Cart, CartItem
from apps.products.serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    """Serializer for cart items."""
    
    product = ProductListSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)
    unit_price = serializers.ReadOnlyField()
    subtotal = serializers.ReadOnlyField()
    
    class Meta:
        model = CartItem
        fields = ('id', 'product', 'product_id', 'quantity', 'unit_price', 'subtotal')
        read_only_fields = ('id',)


class CartItemCreateSerializer(serializers.Serializer):
    """Serializer for adding item to cart."""
    
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    
    def validate_product_id(self, value):
        from apps.products.models import Product
        try:
            product = Product.objects.get(id=value, is_active=True)
            if product.stock <= 0:
                raise serializers.ValidationError("Sản phẩm đã hết hàng.")
        except Product.DoesNotExist:
            raise serializers.ValidationError("Sản phẩm không tồn tại.")
        return value
    
    def validate(self, attrs):
        from apps.products.models import Product
        product = Product.objects.get(id=attrs['product_id'])
        if attrs['quantity'] > product.stock:
            raise serializers.ValidationError({
                'quantity': f"Chỉ còn {product.stock} sản phẩm trong kho."
            })
        return attrs


class CartItemUpdateSerializer(serializers.Serializer):
    """Serializer for updating cart item quantity."""
    
    quantity = serializers.IntegerField(min_value=1)
    
    def validate_quantity(self, value):
        cart_item = self.context.get('cart_item')
        if cart_item and value > cart_item.product.stock:
            raise serializers.ValidationError(
                f"Chỉ còn {cart_item.product.stock} sản phẩm trong kho."
            )
        return value


class CartSerializer(serializers.ModelSerializer):
    """Serializer for cart."""
    
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.ReadOnlyField()
    subtotal = serializers.ReadOnlyField()
    total = serializers.ReadOnlyField()
    
    class Meta:
        model = Cart
        fields = ('id', 'items', 'total_items', 'subtotal', 'total', 'updated_at')
