"""GHN (Giao Hang Nhanh) Shipping API Integration."""
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple
from django.conf import settings
from decimal import Decimal

logger = logging.getLogger('apps.shipping')


class GHNService:
    """
    GHN Shipping API Service.
    Docs: https://api.ghn.vn/home/docs/detail
    """
    
    # API Endpoints
    SANDBOX_URL = 'https://dev-online-gateway.ghn.vn/shiip/public-api'
    PRODUCTION_URL = 'https://online-gateway.ghn.vn/shiip/public-api'
    
    @staticmethod
    def _get_base_url() -> str:
        """Get base URL based on environment."""
        if getattr(settings, 'GHN_SANDBOX', True):
            return GHNService.SANDBOX_URL
        return GHNService.PRODUCTION_URL
    
    @staticmethod
    def _get_headers(include_shop_id: bool = True) -> Dict[str, str]:
        """Get API headers with token."""
        headers = {
            'Content-Type': 'application/json',
            'Token': settings.GHN_TOKEN,
        }
        # ShopId only needed for order operations, not master-data
        if include_shop_id and settings.GHN_SHOP_ID:
            headers['ShopId'] = str(settings.GHN_SHOP_ID)
        return headers
    
    @staticmethod
    def _make_request(endpoint: str, method: str = 'POST', data: Dict = None, include_shop_id: bool = True) -> Dict[str, Any]:
        """Make API request to GHN."""
        url = f"{GHNService._get_base_url()}{endpoint}"
        headers = GHNService._get_headers(include_shop_id=include_shop_id)
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=data, timeout=30)
            else:
                response = requests.post(url, headers=headers, json=data, timeout=30)
            
            result = response.json()
            
            if result.get('code') == 200:
                return {'success': True, 'data': result.get('data')}
            else:
                logger.error(f"GHN API error: {result.get('message')}")
                return {'success': False, 'error': result.get('message', 'Unknown error')}
                
        except requests.Timeout:
            logger.error(f"GHN request timeout: {endpoint}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.exception(f"GHN request error: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.exception(f"GHN unexpected error: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== Province/District/Ward ====================
    
    @staticmethod
    def get_provinces() -> Dict[str, Any]:
        """Get list of provinces/cities."""
        # Master-data endpoints don't require ShopId
        return GHNService._make_request('/master-data/province', 'GET', include_shop_id=False)
    
    @staticmethod
    def get_districts(province_id: int) -> Dict[str, Any]:
        """Get list of districts in a province."""
        return GHNService._make_request('/master-data/district', 'GET', {'province_id': province_id}, include_shop_id=False)
    
    @staticmethod
    def get_wards(district_id: int) -> Dict[str, Any]:
        """Get list of wards in a district."""
        return GHNService._make_request('/master-data/ward', 'GET', {'district_id': district_id}, include_shop_id=False)
    
    # ==================== Shipping Fee ====================
    
    @staticmethod
    def calculate_shipping_fee(
        to_district_id: int,
        to_ward_code: str,
        weight: int,  # grams
        length: int = 10,  # cm
        width: int = 10,  # cm
        height: int = 10,  # cm
        service_type_id: int = 2,  # 2 = E-commerce standard
        insurance_value: int = 0,
        coupon: str = None,
    ) -> Dict[str, Any]:
        """
        Calculate shipping fee.
        
        Args:
            to_district_id: Destination district ID from GHN
            to_ward_code: Destination ward code from GHN
            weight: Package weight in grams
            service_type_id: 1=Express, 2=Standard, 5=Same-day
            insurance_value: Declared value for insurance
        """
        data = {
            'service_type_id': service_type_id,
            'to_district_id': to_district_id,
            'to_ward_code': to_ward_code,
            'weight': weight,
            'length': length,
            'width': width,
            'height': height,
            'insurance_value': insurance_value,
        }
        
        if coupon:
            data['coupon'] = coupon
        
        result = GHNService._make_request('/v2/shipping-order/fee', data=data)
        
        if result['success']:
            fee_data = result['data']
            return {
                'success': True,
                'total_fee': fee_data.get('total'),
                'service_fee': fee_data.get('service_fee'),
                'insurance_fee': fee_data.get('insurance_fee'),
            }
        return result
    
    @staticmethod
    def get_available_services(
        from_district: int,
        to_district: int,
    ) -> Dict[str, Any]:
        """Get available shipping services between two districts."""
        data = {
            'shop_id': int(settings.GHN_SHOP_ID),
            'from_district': from_district,
            'to_district': to_district,
        }
        return GHNService._make_request('/v2/shipping-order/available-services', data=data)
    
    # ==================== Create Order ====================
    
    @staticmethod
    def create_order(
        order,  # Django Order object
        to_district_id: int,
        to_ward_code: str,
        weight: int = 500,  # grams
        service_type_id: int = 2,
        payment_type_id: int = 1,  # 1=Seller pays (Standard e-commerce model), 2=Buyer pays
        note: str = '',
        required_note: str = 'KHONGCHOXEMHANG',  # CHOTHUHANG, CHOXEMHANGKHONGTHU, KHONGCHOXEMHANG
        cod_amount: int = 0,
        insurance_value: int = 0,  # Declared value for insurance (should match checkout calculation)
    ) -> Dict[str, Any]:
        """
        Create shipping order on GHN.
        
        Args:
            order: Django Order object
            to_district_id: Destination district ID
            to_ward_code: Destination ward code
            weight: Total weight in grams
            service_type_id: 1=Express, 2=Standard
            payment_type_id: 1=Shop pays shipping (Default for full COD), 2=Buyer pays shipping
            required_note: Delivery requirement
            cod_amount: COD amount (0 if prepaid)
            insurance_value: Declared value for insurance (goods value)
        """
        # Build items list
        items = []
        for item in order.items.all():
            items.append({
                'name': item.product_name[:200],
                'quantity': item.quantity,
                'price': int(item.price),
                'code': str(item.product_id) if item.product else '',
            })
        
        data = {
            'payment_type_id': payment_type_id,
            'note': note,
            'required_note': required_note,
            'client_order_code': order.order_number,
            'to_name': order.recipient_name,
            'to_phone': order.phone,
            'to_address': order.address,
            'to_ward_code': to_ward_code,
            'to_district_id': to_district_id,
            'cod_amount': cod_amount,  # COD amount passed from caller (0 for prepaid orders)
            'weight': weight,
            'length': 30,
            'width': 20,
            'height': 10,
            'service_type_id': service_type_id,
            'insurance_value': insurance_value,  # Insurance value for package protection
            'items': items,
        }
        
        # Debug log the full request data
        logger.info(f"GHN create_order request for {order.order_number}: cod_amount={cod_amount}, payment_type_id={payment_type_id}, payment_method={order.payment_method}")
        
        result = GHNService._make_request('/v2/shipping-order/create', data=data)
        
        if result['success']:
            order_data = result['data']
            logger.info(f"GHN order created: {order_data.get('order_code')} for order {order.order_number}")
            return {
                'success': True,
                'order_code': order_data.get('order_code'),
                'tracking_number': order_data.get('order_code'),
                'expected_delivery_time': order_data.get('expected_delivery_time'),
                'total_fee': order_data.get('total_fee'),
                'data': order_data,
            }
        
        return result
    
    # ==================== Order Management ====================
    
    @staticmethod
    def get_order_detail(order_code: str) -> Dict[str, Any]:
        """Get order detail from GHN."""
        data = {'order_code': order_code}
        return GHNService._make_request('/v2/shipping-order/detail', data=data)
    
    @staticmethod
    def cancel_order(order_codes: List[str]) -> Dict[str, Any]:
        """Cancel shipping orders."""
        data = {'order_codes': order_codes}
        return GHNService._make_request('/v2/switch-status/cancel', data=data)
    
    @staticmethod
    def return_order(order_codes: List[str]) -> Dict[str, Any]:
        """Request order return."""
        data = {'order_codes': order_codes}
        return GHNService._make_request('/v2/switch-status/return', data=data)
    
    # ==================== Tracking ====================
    
    @staticmethod
    def track_order(order_code: str) -> Dict[str, Any]:
        """
        Get tracking info for an order.
        Returns list of tracking events.
        """
        data = {'order_code': order_code}
        result = GHNService._make_request('/v2/shipping-order/detail', data=data)
        
        if result['success']:
            order_data = result['data']
            
            # Map GHN status to readable status
            status_map = {
                'ready_to_pick': 'Chờ lấy hàng',
                'picking': 'Đang lấy hàng',
                'cancel': 'Đã hủy',
                'money_collect_picking': 'Đang thu tiền người gửi',
                'picked': 'Đã lấy hàng',
                'storing': 'Đang lưu kho',
                'transporting': 'Đang vận chuyển',
                'sorting': 'Đang phân loại',
                'delivering': 'Đang giao hàng',
                'money_collect_delivering': 'Đang thu tiền người nhận',
                'delivered': 'Đã giao hàng',
                'delivery_fail': 'Giao hàng thất bại',
                'waiting_to_return': 'Chờ trả hàng',
                'return': 'Đang trả hàng',
                'return_transporting': 'Đang vận chuyển trả',
                'return_sorting': 'Đang phân loại trả',
                'returning': 'Đang trả hàng cho shop',
                'return_fail': 'Trả hàng thất bại',
                'returned': 'Đã trả hàng',
                'exception': 'Ngoại lệ',
                'damage': 'Hư hỏng',
                'lost': 'Thất lạc',
            }
            
            status = order_data.get('status', '')
            
            return {
                'success': True,
                'order_code': order_data.get('order_code'),
                'status': status,
                'status_display': status_map.get(status, status),
                'to_name': order_data.get('to_name'),
                'to_phone': order_data.get('to_phone'),
                'to_address': order_data.get('to_address'),
                'weight': order_data.get('weight'),
                'cod_amount': order_data.get('cod_amount'),
                'total_fee': order_data.get('total_fee'),
                'expected_delivery_time': order_data.get('expected_delivery_time'),
                'finish_date': order_data.get('finish_date'),
                'leadtime': order_data.get('leadtime'),
                'log': order_data.get('log', []),
            }
        
        return result
    
    # ==================== Estimated Delivery Time ====================
    
    @staticmethod
    def get_leadtime(
        from_district_id: int,
        from_ward_code: str,
        to_district_id: int,
        to_ward_code: str,
        service_id: int = 53321,  # GHN Standard
    ) -> Dict[str, Any]:
        """Get estimated delivery time."""
        data = {
            'from_district_id': from_district_id,
            'from_ward_code': from_ward_code,
            'to_district_id': to_district_id,
            'to_ward_code': to_ward_code,
            'service_id': service_id,
        }
        return GHNService._make_request('/v2/shipping-order/leadtime', data=data)
    
    # ==================== Print ====================
    
    @staticmethod
    def get_print_url(order_codes: List[str]) -> Dict[str, Any]:
        """Get print URL for shipping labels."""
        data = {'order_codes': order_codes}
        result = GHNService._make_request('/v2/a5/gen-token', data=data)
        
        if result['success']:
            token = result['data'].get('token')
            print_url = f"https://dev-online-gateway.ghn.vn/a5/public-api/print?token={token}"
            return {'success': True, 'print_url': print_url}
        
        return result


class ShippingService:
    """Main shipping service dispatcher."""
    
    @staticmethod
    def calculate_fee(order, provider_code: str = 'ghn') -> Dict[str, Any]:
        """Calculate shipping fee based on provider."""
        if provider_code == 'ghn':
            # For GHN, we need district_id and ward_code
            # This should be stored in order or looked up
            # For now, return a placeholder
            return GHNService.calculate_shipping_fee(
                to_district_id=1542,  # Placeholder - Cau Giay
                to_ward_code='1A0807',  # Placeholder
                weight=500,  # Default 500g
            )
        return {'success': False, 'error': 'Provider not supported'}
    
    @staticmethod
    def create_shipment(order, provider_code: str = 'ghn', **kwargs) -> Dict[str, Any]:
        """Create shipment with provider."""
        if provider_code == 'ghn':
            return GHNService.create_order(
                order=order,
                to_district_id=kwargs.get('to_district_id', 1542),
                to_ward_code=kwargs.get('to_ward_code', '1A0807'),
                weight=kwargs.get('weight', 500),
            )
        return {'success': False, 'error': 'Provider not supported'}
    
    @staticmethod
    def track(tracking_number: str, provider_code: str = 'ghn') -> Dict[str, Any]:
        """Track shipment."""
        if provider_code == 'ghn':
            return GHNService.track_order(tracking_number)
        return {'success': False, 'error': 'Provider not supported'}
    
    @staticmethod
    def cancel(tracking_number: str, provider_code: str = 'ghn') -> Dict[str, Any]:
        """Cancel shipment."""
        if provider_code == 'ghn':
            return GHNService.cancel_order([tracking_number])
        return {'success': False, 'error': 'Provider not supported'}
