from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import ShippingProvider, Shipment
from .serializers import ShippingProviderSerializer, ShipmentSerializer
from .services import GHNService, ShippingService


class ShippingProviderListView(generics.ListAPIView):
    """List active shipping providers."""
    queryset = ShippingProvider.objects.filter(is_active=True)
    serializer_class = ShippingProviderSerializer


class ShipmentTrackingView(generics.RetrieveAPIView):
    """Track shipment by order number."""
    serializer_class = ShipmentSerializer
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_object(self):
        order_number = self.kwargs['order_number']
        return get_object_or_404(
            Shipment,
            order__order_number=order_number,
            order__user=self.request.user
        )


# ==================== GHN API Views ====================

class GHNProvincesView(APIView):
    """Get list of provinces/cities from GHN."""
    
    def get(self, request):
        result = GHNService.get_provinces()
        if result['success']:
            return Response(result['data'])
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


class GHNDistrictsView(APIView):
    """Get list of districts in a province from GHN."""
    
    def get(self, request, province_id):
        result = GHNService.get_districts(province_id)
        if result['success']:
            return Response(result['data'])
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


class GHNWardsView(APIView):
    """Get list of wards in a district from GHN."""
    
    def get(self, request, district_id):
        result = GHNService.get_wards(district_id)
        if result['success']:
            return Response(result['data'])
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


class GHNCalculateFeeView(APIView):
    """Calculate shipping fee via GHN."""
    
    def post(self, request):
        to_district_id = request.data.get('to_district_id')
        to_ward_code = request.data.get('to_ward_code')
        weight = request.data.get('weight', 500)
        insurance_value = request.data.get('insurance_value', 0)
        service_type_id = request.data.get('service_type_id', 2)
        
        if not to_district_id or not to_ward_code:
            return Response(
                {'error': 'to_district_id and to_ward_code are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = GHNService.calculate_shipping_fee(
            to_district_id=int(to_district_id),
            to_ward_code=str(to_ward_code),
            weight=int(weight),
            insurance_value=int(insurance_value),
            service_type_id=int(service_type_id),
        )
        
        if result['success']:
            return Response(result)
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


class GHNServicesView(APIView):
    """Get available shipping services between two districts."""
    
    def get(self, request):
        from_district = request.query_params.get('from_district')
        to_district = request.query_params.get('to_district')
        
        if not from_district or not to_district:
            return Response(
                {'error': 'from_district and to_district are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = GHNService.get_available_services(
            from_district=int(from_district),
            to_district=int(to_district),
        )
        
        if result['success']:
            return Response(result['data'])
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


class GHNCreateShipmentView(APIView):
    """Create shipment on GHN (Admin only)."""
    permission_classes = (permissions.IsAdminUser,)
    
    def post(self, request, order_number):
        from apps.sales.models import Order
        
        order = get_object_or_404(Order, order_number=order_number)
        
        to_district_id = request.data.get('to_district_id')
        to_ward_code = request.data.get('to_ward_code')
        weight = request.data.get('weight', 500)
        
        if not to_district_id or not to_ward_code:
            return Response(
                {'error': 'to_district_id and to_ward_code are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = GHNService.create_order(
            order=order,
            to_district_id=int(to_district_id),
            to_ward_code=str(to_ward_code),
            weight=int(weight),
        )
        
        if result['success']:
            # Create local Shipment record
            provider, _ = ShippingProvider.objects.get_or_create(
                code='ghn',
                defaults={'name': 'Giao Hàng Nhanh', 'is_active': True}
            )
            
            shipment = Shipment.objects.create(
                order=order,
                provider=provider,
                tracking_number=result['order_code'],
                status='shipped',
            )
            
            # Update order status
            order.status = 'shipping'
            order.save()
            
            return Response({
                'success': True,
                'order_code': result['order_code'],
                'tracking_number': result['order_code'],
                'expected_delivery_time': result.get('expected_delivery_time'),
                'total_fee': result.get('total_fee'),
                'shipment': ShipmentSerializer(shipment).data,
            })
        
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


class GHNTrackingView(APIView):
    """Get GHN tracking info by order code."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def get(self, request, order_code):
        result = GHNService.track_order(order_code)
        
        if result['success']:
            return Response(result)
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


class GHNCancelShipmentView(APIView):
    """Cancel GHN shipment (Admin only)."""
    permission_classes = (permissions.IsAdminUser,)
    
    def post(self, request, order_code):
        result = GHNService.cancel_order([order_code])
        
        if result['success']:
            # Update local shipment
            try:
                shipment = Shipment.objects.get(tracking_number=order_code)
                shipment.status = 'cancelled'
                shipment.save()
                
                # Update order status
                shipment.order.status = 'cancelled'
                shipment.order.save()
            except Shipment.DoesNotExist:
                pass
            
            return Response({'success': True, 'message': 'Shipment cancelled'})
        
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


class GHNPrintLabelView(APIView):
    """Get print URL for GHN shipping label (Admin only)."""
    permission_classes = (permissions.IsAdminUser,)
    
    def get(self, request, order_code):
        result = GHNService.get_print_url([order_code])
        
        if result['success']:
            return Response(result)
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class GHNWebhookView(APIView):
    """
    Webhook endpoint to receive GHN order status updates.
    GHN will POST status updates to this endpoint.
    
    GHN Status Codes:
    - ready_to_pick: Đã tạo đơn, chờ lấy hàng
    - picking: Đang lấy hàng
    - picked: Đã lấy hàng
    - storing: Đang lưu kho
    - transporting: Đang vận chuyển
    - sorting: Đang phân loại
    - delivering: Đang giao hàng
    - delivered: Đã giao hàng
    - delivery_fail: Giao hàng thất bại
    - waiting_to_return: Chờ trả hàng
    - return: Đang trả hàng
    - returned: Đã trả hàng
    - cancel: Đơn hàng bị hủy
    """
    # No authentication required for webhook
    authentication_classes = []
    permission_classes = []
    
    # GHN status to Order status mapping
    GHN_STATUS_MAP = {
        'ready_to_pick': 'confirmed',
        'picking': 'processing',
        'picked': 'processing',
        'storing': 'processing',
        'transporting': 'shipping',
        'sorting': 'shipping',
        'delivering': 'shipping',
        'delivered': 'delivered',
        'delivery_fail': 'shipping',  # Still in shipping, but failed attempt
        'waiting_to_return': 'shipping',
        'return': 'shipping',
        'returned': 'cancelled',
        'cancel': 'cancelled',
    }
    
    def post(self, request):
        import logging
        logger = logging.getLogger('apps.shipping')
        
        try:
            data = request.data
            logger.info(f"GHN Webhook received: {data}")
            
            # Get order code (GHN tracking number)
            order_code = data.get('OrderCode')
            ghn_status = data.get('Status')
            client_order_code = data.get('ClientOrderCode')  # Our order_number
            
            if not order_code or not ghn_status:
                logger.warning("GHN Webhook: Missing OrderCode or Status")
                return Response({'success': False, 'message': 'Missing required fields'})
            
            # Find order by tracking_code or client_order_code
            from apps.sales.models import Order
            
            order = None
            if client_order_code:
                order = Order.objects.filter(order_number=client_order_code).first()
            if not order:
                order = Order.objects.filter(tracking_code=order_code).first()
            
            if not order:
                logger.warning(f"GHN Webhook: Order not found for {order_code}")
                return Response({'success': False, 'message': 'Order not found'})
            
            # Map GHN status to our status
            new_status = self.GHN_STATUS_MAP.get(ghn_status.lower())
            if not new_status:
                logger.warning(f"GHN Webhook: Unknown status {ghn_status}")
                return Response({'success': True, 'message': f'Unknown status: {ghn_status}'})
            
            # Update order status if valid transition
            old_status = order.status
            
            # Only update if it's a "forward" transition
            status_order = ['pending', 'confirmed', 'processing', 'shipping', 'delivered', 'cancelled']
            old_idx = status_order.index(old_status) if old_status in status_order else -1
            new_idx = status_order.index(new_status) if new_status in status_order else -1
            
            if new_idx > old_idx or new_status == 'cancelled':
                order.status = new_status
                
                # Mark as paid if delivered and COD
                if new_status == 'delivered' and order.payment_method == 'cod':
                    order.payment_status = 'paid'
                
                order.save()
                logger.info(f"Order {order.order_number} status updated: {old_status} -> {new_status} (GHN: {ghn_status})")
            else:
                logger.info(f"Order {order.order_number} status NOT updated: {old_status} -> {new_status} (invalid transition)")
            
            return Response({'success': True, 'message': 'Webhook processed'})
            
        except Exception as e:
            import logging
            logger = logging.getLogger('apps.shipping')
            logger.exception(f"GHN Webhook error: {e}")
            return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

