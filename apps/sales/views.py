from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from .models import Cart, CartItem, Order
from .serializers import CartSerializer, CartItemSerializer, OrderSerializer, CheckoutSerializer
from .services import OrderService, CartService
from apps.catalog.models import Product


# ============ CART VIEWS ============

class CartView(generics.RetrieveAPIView):
    """Get current user's cart."""
    serializer_class = CartSerializer
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_object(self):
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        return cart


class CartAddView(APIView):
    """Add item to cart."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        product_id = request.data.get('product_id')
        
        # Security: Validate quantity input
        try:
            quantity = int(request.data.get('quantity', 1))
            if quantity < 1:
                return Response({'error': 'Số lượng phải lớn hơn 0'}, status=status.HTTP_400_BAD_REQUEST)
            if quantity > 100:  # Reasonable max limit
                return Response({'error': 'Số lượng tối đa là 100'}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({'error': 'Số lượng không hợp lệ'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not product_id:
            return Response({'error': 'Product ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        success, message = CartService.add_item(cart, product_id, quantity)
        
        if success:
            return Response({
                'message': message,
                'cart': CartSerializer(cart).data
            })
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


class CartItemView(generics.RetrieveUpdateDestroyAPIView):
    """Update or delete cart item."""
    serializer_class = CartItemSerializer
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user)
    
    def update(self, request, *args, **kwargs):
        item = self.get_object()
        
        # Security: Validate quantity input
        try:
            quantity = int(request.data.get('quantity', 1))
        except (ValueError, TypeError):
            return Response({'error': 'Số lượng không hợp lệ'}, status=status.HTTP_400_BAD_REQUEST)
        
        success, message = CartService.update_item(item.cart, item.id, quantity)
        
        if success:
            if quantity <= 0:
                return Response(status=status.HTTP_204_NO_CONTENT)
            item.refresh_from_db()
            return Response(CartItemSerializer(item).data)
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


class CartClearView(APIView):
    """Clear all items from cart."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def delete(self, request):
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            cart.clear()
        return Response({'message': 'Đã xóa giỏ hàng'})


# ============ ORDER VIEWS ============

class CheckoutView(APIView):
    """Create order from cart."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            import logging
            logger = logging.getLogger('apps.sales')
            logger.error(f"Checkout serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            order, payment_url = OrderService.create_order(
                user=request.user,
                checkout_data=serializer.validated_data,
                request=request
            )
            
            response_data = OrderSerializer(order).data
            if payment_url:
                response_data['payment_url'] = payment_url
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except ValidationError as e:
            # Specific validation errors from OrderService
            import logging
            logger = logging.getLogger('apps.sales')
            logger.error(f"Checkout validation error: {e.detail}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Security: don't expose internal error details
            import logging
            logging.getLogger('apps.sales').exception(f"Checkout error for user {request.user.id}: {e}")
            return Response({'error': 'Có lỗi xảy ra khi tạo đơn hàng. Vui lòng thử lại.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OrderListView(generics.ListAPIView):
    """List user's orders."""
    serializer_class = OrderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class OrderDetailView(generics.RetrieveAPIView):
    """Get order details."""
    serializer_class = OrderSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = 'order_number'
    
    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all().prefetch_related('items')
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class OrderCancelView(APIView):
    """Cancel an order."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number, user=request.user)
        reason = request.data.get('reason', 'Customer request')
        
        success, message = OrderService.cancel_order(order, reason)
        
        if success:
            return Response({
                'message': message,
                'order': OrderSerializer(order).data
            })
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


# ============ ADMIN VIEWS ============

class AdminOrderListView(generics.ListAPIView):
    """Admin: List all orders with filtering."""
    serializer_class = OrderSerializer
    permission_classes = (permissions.IsAdminUser,)
    
    def get_queryset(self):
        queryset = Order.objects.all().prefetch_related('items').order_by('-created_at')
        
        # Filters
        status_filter = self.request.query_params.get('status')
        payment_status = self.request.query_params.get('payment_status')
        
        return queryset

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        
        # Manual filters (keeping existing logic or enhancing it)
        status_filter = self.request.query_params.get('status')
        payment_status = self.request.query_params.get('payment_status')
        search_term = self.request.query_params.get('search')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
            
        if search_term:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(order_number__icontains=search_term) |
                Q(recipient_name__icontains=search_term) |
                Q(phone__icontains=search_term) |
                Q(user__email__icontains=search_term)
            )
            
        return queryset


class AdminOrderDetailView(generics.RetrieveUpdateAPIView):
    """Admin: View and update order."""
    serializer_class = OrderSerializer
    permission_classes = (permissions.IsAdminUser,)
    queryset = Order.objects.all()
    lookup_field = 'order_number'


class AdminOrderStatusUpdateView(APIView):
    """Admin: Update order status."""
    permission_classes = (permissions.IsAdminUser,)
    
    def post(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)
        new_status = request.data.get('status')
        
        if not new_status:
            return Response({'error': 'Status is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        success, message = OrderService.update_order_status(order, new_status, request.user)
        
        if success:
            return Response({
                'message': message,
                'order': OrderSerializer(order).data
            })
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


class AdminDashboardView(APIView):
    """Admin: Dashboard statistics."""
    permission_classes = (permissions.IsAdminUser,)
    
    def get(self, request):
        stats = OrderService.get_admin_dashboard_stats()
        return Response(stats)
