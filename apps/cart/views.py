"""
Advanced Cart Views with robust error handling, stock validation,
atomic transactions, logging, and optimized queries.
"""
import logging
from decimal import Decimal

from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import F, Prefetch
from django.core.cache import cache

from .models import Cart, CartItem
from .serializers import (
    CartSerializer,
    CartItemSerializer,
    CartItemCreateSerializer,
    CartItemUpdateSerializer,
)
from apps.products.models import Product

logger = logging.getLogger(__name__)


class CartMixin:
    """
    Advanced mixin to get or create cart for current user/session.
    Includes cart merging, cache optimization, and error handling.
    """
    
    CART_CACHE_TTL = 300  # 5 minutes
    
    def get_cart(self, request):
        """
        Get or create cart with optimized queries and caching.
        Handles both authenticated users and anonymous sessions.
        """
        if request.user.is_authenticated:
            return self._get_user_cart(request)
        return self._get_session_cart(request)
    
    def _get_user_cart(self, request):
        """Get cart for authenticated user with session cart merging."""
        cache_key = f"cart_user_{request.user.id}"
        
        # Try cache first
        cached_cart_id = cache.get(cache_key)
        if cached_cart_id:
            try:
                return Cart.objects.prefetch_related(
                    Prefetch('items', queryset=CartItem.objects.select_related('product'))
                ).get(id=cached_cart_id)
            except Cart.DoesNotExist:
                cache.delete(cache_key)
        
        # Get or create cart
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        # Merge session cart if exists
        session_key = request.session.session_key
        if session_key:
            self._merge_session_cart(cart, session_key)
        
        # Cache the cart ID
        cache.set(cache_key, cart.id, self.CART_CACHE_TTL)
        
        return cart
    
    def _get_session_cart(self, request):
        """Get cart for anonymous session."""
        if not request.session.session_key:
            request.session.save()
        
        session_key = request.session.session_key
        cache_key = f"cart_session_{session_key}"
        
        # Try cache first
        cached_cart_id = cache.get(cache_key)
        if cached_cart_id:
            try:
                return Cart.objects.prefetch_related(
                    Prefetch('items', queryset=CartItem.objects.select_related('product'))
                ).get(id=cached_cart_id)
            except Cart.DoesNotExist:
                cache.delete(cache_key)
        
        cart, created = Cart.objects.get_or_create(
            session_key=session_key,
            user__isnull=True,
            defaults={'session_key': session_key}
        )
        
        cache.set(cache_key, cart.id, self.CART_CACHE_TTL)
        return cart
    
    def _merge_session_cart(self, user_cart, session_key):
        """
        Merge anonymous session cart into user cart.
        Uses atomic transaction to ensure data integrity.
        """
        try:
            session_cart = Cart.objects.prefetch_related('items').get(
                session_key=session_key, 
                user__isnull=True
            )
            
            if session_cart.items.exists():
                with transaction.atomic():
                    for session_item in session_cart.items.all():
                        user_item, created = CartItem.objects.get_or_create(
                            cart=user_cart,
                            product=session_item.product,
                            defaults={'quantity': session_item.quantity}
                        )
                        if not created:
                            # Combine quantities, respecting stock limits
                            new_qty = user_item.quantity + session_item.quantity
                            user_item.quantity = min(new_qty, session_item.product.stock)
                            user_item.save(update_fields=['quantity'])
                    
                    session_cart.delete()
                    logger.info(f"Merged session cart into user cart {user_cart.id}")
                    
        except Cart.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error merging carts: {e}")
    
    def invalidate_cart_cache(self, cart):
        """Invalidate cart cache after modifications."""
        if cart.user:
            cache.delete(f"cart_user_{cart.user.id}")
        if cart.session_key:
            cache.delete(f"cart_session_{cart.session_key}")


class CartView(CartMixin, APIView):
    """
    API view for viewing cart with stock validation.
    Returns cart with real-time stock availability.
    """
    
    permission_classes = (permissions.AllowAny,)
    
    def get(self, request):
        cart = self.get_cart(request)
        
        # Validate and update stock availability
        warnings = self._validate_cart_stock(cart)
        
        serializer = CartSerializer(cart)
        response_data = serializer.data
        
        if warnings:
            response_data['warnings'] = warnings
        
        return Response(response_data)
    
    def _validate_cart_stock(self, cart):
        """
        Validate cart items against current stock levels.
        Auto-adjusts quantities if stock has decreased.
        Returns list of warnings.
        """
        warnings = []
        items_to_update = []
        items_to_remove = []
        
        for item in cart.items.select_related('product').all():
            product = item.product
            
            if not product.is_active:
                items_to_remove.append(item)
                warnings.append({
                    'product_id': product.id,
                    'message': f'{product.name} không còn khả dụng'
                })
            elif product.stock == 0:
                items_to_remove.append(item)
                warnings.append({
                    'product_id': product.id,
                    'message': f'{product.name} đã hết hàng'
                })
            elif item.quantity > product.stock:
                old_qty = item.quantity
                item.quantity = product.stock
                items_to_update.append(item)
                warnings.append({
                    'product_id': product.id,
                    'message': f'{product.name}: số lượng giảm từ {old_qty} xuống {product.stock}'
                })
        
        # Batch update/delete for efficiency
        if items_to_update:
            CartItem.objects.bulk_update(items_to_update, ['quantity'])
        if items_to_remove:
            CartItem.objects.filter(id__in=[i.id for i in items_to_remove]).delete()
        
        return warnings


class AddToCartView(CartMixin, APIView):
    """
    Advanced API view for adding items to cart.
    Includes stock validation, atomic transactions, and detailed responses.
    """
    
    permission_classes = (permissions.AllowAny,)
    
    @transaction.atomic
    def post(self, request):
        serializer = CartItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        cart = self.get_cart(request)
        product_id = serializer.validated_data['product_id']
        requested_quantity = serializer.validated_data['quantity']
        
        # Lock the product row for stock validation
        try:
            product = Product.objects.select_for_update().get(
                id=product_id,
                is_active=True
            )
        except Product.DoesNotExist:
            return Response({
                'error': 'Sản phẩm không tồn tại hoặc không khả dụng',
                'code': 'PRODUCT_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Validate stock
        if product.stock == 0:
            return Response({
                'error': 'Sản phẩm đã hết hàng',
                'code': 'OUT_OF_STOCK'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get or create cart item
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 0}
        )
        
        # Calculate new quantity
        current_quantity = cart_item.quantity if not created else 0
        new_quantity = current_quantity + requested_quantity
        
        # Apply stock limit
        actual_quantity = min(new_quantity, product.stock)
        quantity_adjusted = actual_quantity < new_quantity
        
        cart_item.quantity = actual_quantity
        cart_item.save()
        
        self.invalidate_cart_cache(cart)
        
        # Build response
        response_data = {
            'success': True,
            'message': 'Đã thêm vào giỏ hàng!' if created else 'Đã cập nhật giỏ hàng!',
            'cart': CartSerializer(cart).data,
            'added_item': {
                'product_id': product.id,
                'product_name': product.name,
                'quantity': cart_item.quantity,
                'unit_price': float(product.current_price),
            }
        }
        
        if quantity_adjusted:
            response_data['warning'] = f'Số lượng được giới hạn bởi tồn kho ({product.stock})'
        
        logger.info(f"Cart {cart.id}: Added product {product.id} x{requested_quantity}")
        
        return Response(response_data, status=status.HTTP_200_OK)


class UpdateCartItemView(CartMixin, APIView):
    """
    Advanced API view for updating cart item quantity.
    Includes stock validation and optimistic update support.
    """
    
    permission_classes = (permissions.AllowAny,)
    
    @transaction.atomic
    def post(self, request):
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity')
        
        # Validate input
        if not product_id:
            return Response({
                'error': 'Product ID là bắt buộc',
                'code': 'MISSING_PRODUCT_ID'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({
                'error': 'Số lượng không hợp lệ',
                'code': 'INVALID_QUANTITY'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        cart = self.get_cart(request)
        
        # Get cart item with product lock
        try:
            cart_item = CartItem.objects.select_related('product').select_for_update().get(
                cart=cart,
                product_id=product_id
            )
        except CartItem.DoesNotExist:
            return Response({
                'error': 'Sản phẩm không có trong giỏ hàng',
                'code': 'ITEM_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        product = cart_item.product
        
        # Handle removal
        if quantity <= 0:
            cart_item.delete()
            self.invalidate_cart_cache(cart)
            
            return Response({
                'success': True,
                'message': 'Đã xóa sản phẩm khỏi giỏ hàng',
                'cart': CartSerializer(cart).data
            })
        
        # Validate against stock
        actual_quantity = min(quantity, product.stock)
        quantity_adjusted = actual_quantity < quantity
        
        cart_item.quantity = actual_quantity
        cart_item.save(update_fields=['quantity'])
        
        self.invalidate_cart_cache(cart)
        
        response_data = {
            'success': True,
            'message': 'Cập nhật thành công!',
            'cart': CartSerializer(cart).data,
            'updated_item': {
                'product_id': product.id,
                'quantity': cart_item.quantity,
            }
        }
        
        if quantity_adjusted:
            response_data['warning'] = f'Số lượng được giới hạn bởi tồn kho ({product.stock})'
        
        logger.info(f"Cart {cart.id}: Updated product {product.id} to qty {actual_quantity}")
        
        return Response(response_data)


class RemoveFromCartView(CartMixin, APIView):
    """API view for removing item from cart with confirmation."""
    
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        product_id = request.data.get('product_id')
        
        if not product_id:
            return Response({
                'error': 'Product ID là bắt buộc',
                'code': 'MISSING_PRODUCT_ID'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        cart = self.get_cart(request)
        
        try:
            cart_item = CartItem.objects.select_related('product').get(
                cart=cart,
                product_id=product_id
            )
        except CartItem.DoesNotExist:
            return Response({
                'error': 'Sản phẩm không có trong giỏ hàng',
                'code': 'ITEM_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)
        
        product_name = cart_item.product.name
        cart_item.delete()
        
        self.invalidate_cart_cache(cart)
        
        logger.info(f"Cart {cart.id}: Removed product {product_id}")
        
        return Response({
            'success': True,
            'message': f'Đã xóa "{product_name}" khỏi giỏ hàng!',
            'cart': CartSerializer(cart).data
        })


class ClearCartView(CartMixin, APIView):
    """API view for clearing all items from cart."""
    
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        cart = self.get_cart(request)
        
        items_count = cart.items.count()
        
        if items_count == 0:
            return Response({
                'success': True,
                'message': 'Giỏ hàng đã trống',
                'cart': CartSerializer(cart).data
            })
        
        cart.items.all().delete()
        
        self.invalidate_cart_cache(cart)
        
        logger.info(f"Cart {cart.id}: Cleared {items_count} items")
        
        return Response({
            'success': True,
            'message': f'Đã xóa {items_count} sản phẩm khỏi giỏ hàng!',
            'cart': CartSerializer(cart).data
        })


class BulkUpdateCartView(CartMixin, APIView):
    """
    API view for bulk updating multiple cart items at once.
    Useful for cart page "Update All" functionality.
    """
    
    permission_classes = (permissions.AllowAny,)
    
    @transaction.atomic
    def post(self, request):
        items = request.data.get('items', [])
        
        if not items:
            return Response({
                'error': 'Danh sách sản phẩm không hợp lệ',
                'code': 'INVALID_ITEMS'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        cart = self.get_cart(request)
        warnings = []
        updated_count = 0
        removed_count = 0
        
        for item_data in items:
            product_id = item_data.get('product_id')
            quantity = item_data.get('quantity', 0)
            
            if not product_id:
                continue
            
            try:
                cart_item = CartItem.objects.select_related('product').get(
                    cart=cart,
                    product_id=product_id
                )
                
                if quantity <= 0:
                    cart_item.delete()
                    removed_count += 1
                else:
                    actual_quantity = min(int(quantity), cart_item.product.stock)
                    if actual_quantity < quantity:
                        warnings.append({
                            'product_id': product_id,
                            'message': f'Số lượng giới hạn: {actual_quantity}'
                        })
                    cart_item.quantity = actual_quantity
                    cart_item.save(update_fields=['quantity'])
                    updated_count += 1
                    
            except CartItem.DoesNotExist:
                warnings.append({
                    'product_id': product_id,
                    'message': 'Sản phẩm không tồn tại trong giỏ'
                })
        
        self.invalidate_cart_cache(cart)
        
        logger.info(f"Cart {cart.id}: Bulk update - {updated_count} updated, {removed_count} removed")
        
        return Response({
            'success': True,
            'message': f'Đã cập nhật {updated_count} sản phẩm, xóa {removed_count} sản phẩm',
            'cart': CartSerializer(cart).data,
            'warnings': warnings if warnings else None
        })
