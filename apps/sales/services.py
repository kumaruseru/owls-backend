"""Sales services - Order business logic."""
import logging
from django.db import transaction
from django.db.models import F, Sum, Q, Count
from django.utils import timezone
from typing import Dict, Any, Tuple, Optional, List
from .models import Cart, Order, OrderItem
from apps.catalog.models import Product

logger = logging.getLogger('apps.sales')


class CartService:
    """Service for cart operations."""
    
    @staticmethod
    def get_or_create_cart(user=None, session_key=None) -> Cart:
        """Get or create cart for user or session."""
        if user and user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=user)
            return cart
        elif session_key:
            cart, _ = Cart.objects.get_or_create(session_key=session_key)
            return cart
        raise ValueError("Either user or session_key must be provided")
    
    @staticmethod
    def merge_carts(user_cart: Cart, session_cart: Cart):
        """Merge session cart into user cart on login."""
        if user_cart.id == session_cart.id:
            return
        
        for item in session_cart.items.all():
            existing = user_cart.items.filter(product=item.product).first()
            if existing:
                existing.quantity = min(existing.quantity + item.quantity, item.product.stock)
                existing.save()
            else:
                item.cart = user_cart
                item.save()
        
        session_cart.delete()
        logger.info(f"Merged session cart into user cart {user_cart.id}")
    
    @staticmethod
    def add_item(cart: Cart, product_id: str, quantity: int = 1) -> Tuple[bool, str]:
        """Add item to cart with stock validation."""
        from apps.catalog.models import Product
        
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return False, "Sản phẩm không tồn tại"
        
        if not product.is_in_stock:
            return False, "Sản phẩm hết hàng"
        
        from .models import CartItem
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        
        new_quantity = quantity if created else cart_item.quantity + quantity
        
        if new_quantity > product.stock:
            return False, f"Chỉ còn {product.stock} sản phẩm trong kho"
        
        cart_item.quantity = new_quantity
        cart_item.save()
        
        return True, "Đã thêm vào giỏ hàng"
    
    @staticmethod
    def update_item(cart: Cart, item_id: int, quantity: int) -> Tuple[bool, str]:
        """Update cart item quantity."""
        from .models import CartItem
        
        try:
            item = CartItem.objects.get(id=item_id, cart=cart)
        except CartItem.DoesNotExist:
            return False, "Không tìm thấy sản phẩm trong giỏ"
        
        if quantity <= 0:
            item.delete()
            return True, "Đã xóa sản phẩm khỏi giỏ"
        
        if quantity > item.product.stock:
            return False, f"Chỉ còn {item.product.stock} sản phẩm trong kho"
        
        item.quantity = quantity
        item.save()
        return True, "Đã cập nhật số lượng"


class OrderService:
    """Service xử lý business logic cho Order."""
    
    @staticmethod
    @transaction.atomic
    def create_order(user, checkout_data: Dict[str, Any], request=None) -> Tuple[Order, Optional[str]]:
        """
        Tạo đơn hàng từ giỏ hàng.
        Returns: (order, payment_url)
        """
        from rest_framework.exceptions import ValidationError
        
        cart = Cart.objects.filter(user=user).first()
        
        if not cart or not cart.items.exists():
            raise ValidationError({'error': 'Giỏ hàng trống'})
        
        cart_items = list(cart.items.select_related('product').all())
        product_ids = [item.product_id for item in cart_items]
        
        # Lock products for update to prevent race conditions
        products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)}
        
        # Validate stock
        errors = []
        for cart_item in cart_items:
            product = products.get(cart_item.product_id)
            if not product:
                errors.append(f"Sản phẩm '{cart_item.product.name}' không còn tồn tại")
            elif not product.is_active:
                errors.append(f"Sản phẩm '{cart_item.product.name}' đã ngừng bán")
            elif cart_item.quantity > product.stock:
                errors.append(f"Sản phẩm '{cart_item.product.name}' chỉ còn {product.stock} trong kho")
        
        if errors:
            raise ValidationError({'errors': errors})
        
        # Create Order
        order = Order.objects.create(
            user=user,
            recipient_name=checkout_data['recipient_name'],
            phone=checkout_data['phone'],
            email=checkout_data.get('email', user.email or ''),
            address=checkout_data['address'],
            city=checkout_data['city'],
            district=checkout_data['district'],
            ward=checkout_data.get('ward', ''),
            note=checkout_data.get('note', ''),
            payment_method=checkout_data['payment_method'],
            shipping_fee=checkout_data.get('shipping_fee', 0),
            to_district_id=checkout_data.get('to_district_id'),
            to_ward_code=checkout_data.get('to_ward_code', ''),
        )
        
        # Create OrderItems and update stock atomically
        for cart_item in cart_items:
            product = products.get(cart_item.product_id)
            
            # Get product image URL
            product_image = ''
            if product.primary_image:
                if request:
                    product_image = request.build_absolute_uri(product.primary_image.url)
                else:
                    product_image = product.primary_image.url
            
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                product_image=product_image,
                quantity=cart_item.quantity,
                price=product.current_price,
            )
            
            # Atomic stock update
            Product.objects.filter(id=product.id).update(stock=F('stock') - cart_item.quantity)
        
        order.calculate_totals()
        cart.clear()
        
        logger.info(f"Order {order.order_number} created for user {user.email}")
        
        # Process payment if needed
        payment_url = None
        if checkout_data['payment_method'] not in ['cod', 'bank_transfer']:
            payment_url = OrderService._process_payment(order, request)
            
            # If online payment (VNPay/MoMo) but payment URL creation failed,
            # we should fail the order to prevent orphan orders
            if payment_url is None:
                # Rollback: restore stock and delete order
                for cart_item in cart_items:
                    Product.objects.filter(id=cart_item.product_id).update(
                        stock=F('stock') + cart_item.quantity
                    )
                order.delete()
                raise ValidationError({
                    'error': 'Không thể kết nối đến cổng thanh toán. Vui lòng thử lại hoặc chọn phương thức khác.'
                })
        
        # Email is now sent upon Admin Confirmation (see update_order_status)
        
        return order, payment_url
    
    @staticmethod
    def _process_payment(order: Order, request) -> Optional[str]:
        """Xử lý thanh toán với payment gateway."""
        from apps.billing.models import Payment
        from apps.billing.services import PaymentService
        
        payment = Payment.objects.create(
            order=order,
            user=order.user,
            payment_method=order.payment_method,
            amount=order.total,
        )
        
        return PaymentService.create_payment_url(payment, request)
    
    @staticmethod
    def update_order_status(order: Order, new_status: str, admin_user=None) -> Tuple[bool, str]:
        """Update order status with validation."""
        valid_transitions = {
            'pending': ['confirmed', 'cancelled'],
            'confirmed': ['shipping', 'delivered', 'cancelled'],
            'processing': ['shipping', 'delivered'],
            'shipping': ['delivered'],
            'delivered': [],
            'cancelled': [],
        }
        
        if new_status not in valid_transitions.get(order.status, []):
            return False, f"Không thể chuyển từ '{order.get_status_display()}' sang '{new_status}'"
        
        old_status = order.status
        order.status = new_status
        order.save()
        
        logger.info(f"Order {order.order_number} status changed: {old_status} -> {new_status}")
        
        if new_status == 'confirmed':
            # 1. Send confirmation email
            try:
                from apps.identity.services import EmailService
                EmailService.send_order_confirmation_email(order)
                logger.info(f"Sent confirmation email for order {order.order_number}")
            except Exception as e:
                logger.error(f"Failed to send order confirmation email: {e}")

            # 2. Create GHN shipping order if address is improved
            if order.to_district_id and order.to_ward_code:
                try:
                    from apps.shipping.services import GHNService
                    
                    # Calculate total weight (500g per item as default)
                    total_weight = sum(item.quantity * 500 for item in order.items.all())
                    
                    # COD amount (only for COD orders)
                    cod_amount = int(order.total) if order.payment_method == 'cod' else 0
                    
                    logger.info(f"Creating GHN order for {order.order_number}: Total={order.total}, COD={cod_amount}, Method={order.payment_method}")

                    result = GHNService.create_order(
                        order=order,
                        to_district_id=order.to_district_id,
                        to_ward_code=order.to_ward_code,
                        weight=total_weight,
                        cod_amount=cod_amount,
                        # No insurance_value - to match GHN displayed service fee
                        payment_type_id=1, # Explicitly Shop Pays (Customer pays COD including ship fee)
                        note=order.note,
                    )
                    
                    if result.get('success'):
                        order.tracking_code = result.get('order_code', '')
                        order.save()
                        logger.info(f"GHN order created for {order.order_number}: {order.tracking_code}")
                    else:
                        import sys
                        print(f"GHN ERROR: {result.get('error')}", file=sys.stderr) # Force print to stderr
                        logger.error(f"Failed to create GHN order for {order.order_number}: {result.get('error')}")
                except Exception as e:
                    logger.exception(f"Error creating GHN order for {order.order_number}: {e}")
        
        # Handle COD payment on delivery
        if new_status == 'delivered' and order.payment_method == 'cod':
            order.payment_status = 'paid'
            order.save()
        
        return True, f"Đã cập nhật trạng thái thành '{order.get_status_display()}'"
    
    @staticmethod
    def cancel_order(order: Order, reason: str = '') -> Tuple[bool, str]:
        """Cancel order and restore stock."""
        if not order.can_cancel():
            return False, "Không thể hủy đơn hàng ở trạng thái này"
        
        with transaction.atomic():
            # Restore stock
            for item in order.items.all():
                if item.product:
                    Product.objects.filter(id=item.product.id).update(
                        stock=F('stock') + item.quantity
                    )
            
            order.status = 'cancelled'
            order.note = f"{order.note}\n[Cancelled] {reason}".strip()
            order.save()
        
        logger.info(f"Order {order.order_number} cancelled. Reason: {reason}")
        return True, "Đã hủy đơn hàng"
    
    @staticmethod
    def get_admin_dashboard_stats() -> Dict[str, Any]:
        """Calculate statistics for Admin Dashboard."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        
        # Revenue (Paid online OR Delivered COD)
        revenue_query = Order.objects.filter(
            Q(payment_status='paid') | 
            (Q(payment_method='cod') & Q(status='delivered'))
        )
        
        total_revenue = revenue_query.aggregate(total=Sum('total'))['total'] or 0
        monthly_revenue = revenue_query.filter(
            created_at__date__gte=this_month_start
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Orders by status
        orders_by_status = dict(
            Order.objects.values('status').annotate(count=Count('id')).values_list('status', 'count')
        )

        # Calculate dates for trend comparison (This Month vs Last Month)
        last_month = this_month_start.replace(day=1) - timezone.timedelta(days=1)
        last_month_start = last_month.replace(day=1)
        
        # 1. Revenue Trend
        last_month_revenue = revenue_query.filter(
            created_at__date__gte=last_month_start,
            created_at__date__lte=last_month
        ).aggregate(total=Sum('total'))['total'] or 0

        revenue_growth = 0
        if last_month_revenue > 0:
            revenue_growth = ((monthly_revenue - last_month_revenue) / last_month_revenue) * 100
        elif monthly_revenue > 0:
            revenue_growth = 100

        # 2. Orders Trend
        this_month_orders = Order.objects.filter(created_at__date__gte=this_month_start).count()
        last_month_orders = Order.objects.filter(
            created_at__date__gte=last_month_start,
            created_at__date__lte=last_month
        ).count()

        orders_growth = 0
        if last_month_orders > 0:
            orders_growth = ((this_month_orders - last_month_orders) / last_month_orders) * 100
        elif this_month_orders > 0:
            orders_growth = 100
            
        # 3. Customers Trend
        new_customers_this_month = User.objects.filter(
            is_staff=False, date_joined__date__gte=this_month_start
        ).count()
        new_customers_last_month = User.objects.filter(
            is_staff=False, 
            date_joined__date__gte=last_month_start,
            date_joined__date__lte=last_month
        ).count()

        customers_growth = 0
        if new_customers_last_month > 0:
            customers_growth = ((new_customers_this_month - new_customers_last_month) / new_customers_last_month) * 100
        elif new_customers_this_month > 0:
            customers_growth = 100
        
        # Counts
        stats = {
            'total_revenue': total_revenue,
            'monthly_revenue': monthly_revenue,
            'revenue_growth': round(revenue_growth, 1),
            
            'total_orders': Order.objects.count(),
            'orders_growth': round(orders_growth, 1),
            
            'pending_orders': orders_by_status.get('pending', 0),
            'processing_orders': orders_by_status.get('processing', 0) + orders_by_status.get('confirmed', 0),
            'shipping_orders': orders_by_status.get('shipping', 0),
            'completed_orders': orders_by_status.get('delivered', 0),
            'cancelled_orders': orders_by_status.get('cancelled', 0),
            
            'total_customers': User.objects.filter(is_staff=False, is_deleted=False).count(),
            'customers_growth': round(customers_growth, 1),
            'new_customers_this_month': new_customers_this_month,
        }
        
        # Recent orders
        from .serializers import OrderSerializer
        recent_orders = Order.objects.all().order_by('-created_at')[:10]
        stats['recent_orders'] = OrderSerializer(recent_orders, many=True).data
        
        # Top products this month
        top_products = OrderItem.objects.filter(
            order__created_at__date__gte=this_month_start,
            order__status__in=['confirmed', 'processing', 'shipping', 'delivered']
        ).values('product_name').annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum(F('price') * F('quantity'))
        ).order_by('-total_sold')[:5]
        
        stats['top_products'] = list(top_products)
        
        return stats
