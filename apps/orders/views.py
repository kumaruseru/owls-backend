from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import F

from .models import Order, OrderItem
from .serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    CheckoutSerializer,
)
from apps.products.models import Product
from apps.payments.models import Payment
from apps.payments.vnpay_service import VNPayService
from apps.payments.momo_service import MoMoService


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip


class OrderListView(generics.ListAPIView):
    """List user's orders."""
    
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = OrderListSerializer
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')


class OrderDetailView(generics.RetrieveAPIView):
    """Get order details."""
    
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = OrderDetailSerializer
    lookup_field = 'order_number'
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class CheckoutView(APIView):
    """
    API view for checkout process.
    Supports COD, VNPay, and MoMo payment methods.
    """
    
    permission_classes = (permissions.IsAuthenticated,)
    
    @transaction.atomic
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        cart = user.cart
        
        if not cart.items.exists():
            return Response({
                'error': 'Giỏ hàng trống.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        cart_items = list(cart.items.select_related('product').all())
        product_ids = [item.product_id for item in cart_items]
        
        # Lock the products for update
        products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)}
        
        # Recheck stock availability with lock
        for cart_item in cart_items:
            product = products.get(cart_item.product_id)
            if not product or cart_item.quantity > product.stock:
                return Response({
                    'error': f"Sản phẩm '{cart_item.product.name}' không đủ số lượng trong kho."
                }, status=status.HTTP_400_BAD_REQUEST)
        
        payment_method = serializer.validated_data['payment_method']
        
        # Create order
        order = Order.objects.create(
            user=user,
            recipient_name=serializer.validated_data['recipient_name'],
            phone=serializer.validated_data['phone'],
            email=serializer.validated_data.get('email', user.email or ''),
            address=serializer.validated_data['address'],
            city=serializer.validated_data['city'],
            district=serializer.validated_data['district'],
            ward=serializer.validated_data.get('ward', ''),
            note=serializer.validated_data.get('note', ''),
            payment_method=payment_method,
        )
        
        # Create order items and update stock atomically
        for cart_item in cart_items:
            product = products.get(cart_item.product_id)
            
            # Get product image URL
            product_image = ''
            if product.primary_image:
                product_image = request.build_absolute_uri(product.primary_image.url)
            
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                product_image=product_image,
                quantity=cart_item.quantity,
                price=product.current_price,
            )
            
            # Atomic stock update using F() to prevent race condition
            Product.objects.filter(id=product.id).update(
                stock=F('stock') - cart_item.quantity
            )
        
        # Calculate totals
        order.calculate_totals()
        
        # Clear cart
        cart.clear()
        
        # Handle payment based on method
        payment_url = None
        
        if payment_method == 'cod':
            # Cash on Delivery - no payment needed
            order.payment_status = 'unpaid'  # Will be paid on delivery
            order.save()
        
        elif payment_method in ['vnpay', 'momo']:
            # Create payment record
            payment = Payment.objects.create(
                order=order,
                user=user,
                payment_method=payment_method,
                amount=order.total,
            )
            
            # Get frontend return URL
            frontend_url = request.headers.get('Origin', 'http://localhost:3000')
            return_url = f"{frontend_url}/orders/{order.order_number}?payment=success"
            
            if payment_method == 'vnpay':
                service = VNPayService()
                result = service.create_payment_url(
                    payment=payment,
                    ip_address=get_client_ip(request),
                    return_url=return_url,
                )
                
                if result['success']:
                    payment_url = result['payment_url']
                else:
                    # Payment creation failed, but order is still valid
                    # User can retry payment later
                    pass
            
            elif payment_method == 'momo':
                service = MoMoService()
                result = service.create_payment(
                    payment=payment,
                    return_url=return_url,
                )
                
                if result['success']:
                    payment_url = result['payment_url']
                else:
                    # Payment creation failed, but order is still valid
                    pass
        
        # Send order confirmation email
        try:
            from apps.users.email_service import EmailService
            EmailService.send_order_confirmation_email(order)
        except Exception:
            pass  # Don't fail order if email fails
        
        # Build response
        response_data = {
            'message': 'Đặt hàng thành công!',
            'order': OrderDetailSerializer(order).data,
        }
        
        if payment_url:
            response_data['payment_url'] = payment_url
        
        return Response(response_data, status=status.HTTP_201_CREATED)


class CancelOrderView(APIView):
    """API view for cancelling an order."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    @transaction.atomic
    def post(self, request, order_number):
        order = get_object_or_404(
            Order, 
            order_number=order_number, 
            user=request.user
        )
        
        if not order.can_cancel():
            return Response({
                'error': 'Không thể hủy đơn hàng này.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Restore stock
        for item in order.items.all():
            if item.product:
                Product.objects.filter(id=item.product.id).update(
                    stock=F('stock') + item.quantity
                )
        
        order.status = 'cancelled'
        order.save()
        
        return Response({
            'message': 'Đã hủy đơn hàng.',
            'order': OrderDetailSerializer(order).data
        })
