from rest_framework import serializers
from .models import Order, OrderItem
from apps.products.serializers import ProductListSerializer


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializer for order items."""
    
    subtotal = serializers.ReadOnlyField()
    
    class Meta:
        model = OrderItem
        fields = (
            'id', 'product', 'product_name', 'product_image',
            'quantity', 'price', 'subtotal'
        )


class OrderListSerializer(serializers.ModelSerializer):
    """Serializer for order listing."""
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    item_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'status', 'status_display',
            'payment_status', 'payment_status_display',
            'total', 'item_count', 'created_at'
        )


class OrderDetailSerializer(serializers.ModelSerializer):
    """Serializer for order detail."""
    
    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    full_address = serializers.ReadOnlyField()
    item_count = serializers.ReadOnlyField()
    can_cancel = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'status', 'status_display',
            'recipient_name', 'phone', 'email', 'address',
            'city', 'district', 'ward', 'full_address', 'note',
            'payment_method', 'payment_method_display',
            'payment_status', 'payment_status_display',
            'subtotal', 'shipping_fee', 'discount', 'total',
            'items', 'item_count', 'can_cancel',
            'created_at', 'updated_at'
        )
    
    def get_can_cancel(self, obj):
        return obj.can_cancel()


class CheckoutSerializer(serializers.Serializer):
    """Serializer for checkout process."""
    
    recipient_name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=15)
    email = serializers.EmailField(required=False, allow_blank=True)
    address = serializers.CharField()
    city = serializers.CharField(max_length=100)
    district = serializers.CharField(max_length=100)
    ward = serializers.CharField(max_length=100, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=Order.PAYMENT_METHOD_CHOICES,
        default='cod'
    )
    
    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Check if user has items in cart
            if not hasattr(request.user, 'cart') or not request.user.cart.items.exists():
                raise serializers.ValidationError("Giỏ hàng trống.")
            
            # Check stock availability
            for item in request.user.cart.items.all():
                if item.quantity > item.product.stock:
                    raise serializers.ValidationError(
                        f"Sản phẩm '{item.product.name}' chỉ còn {item.product.stock} trong kho."
                    )
        return attrs
