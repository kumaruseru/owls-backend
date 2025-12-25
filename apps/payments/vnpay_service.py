"""
VNPay Payment Service
Documentation: https://sandbox.vnpayment.vn/apis/
"""

import hashlib
import hmac
import logging
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone
from .models import Payment
from apps.utils.security import mask_for_logging, get_safe_provider_data

logger = logging.getLogger('apps.payments')


class VNPayService:
    """Service class for VNPay payment integration."""
    
    def __init__(self):
        self.tmn_code = settings.VNPAY_TMN_CODE
        self.hash_secret = settings.VNPAY_HASH_SECRET
        self.payment_url = settings.VNPAY_PAYMENT_URL
        self.return_url = settings.VNPAY_RETURN_URL
        self.api_url = getattr(settings, 'VNPAY_REFUND_URL', 'https://sandbox.vnpayment.vn/merchant_webapi/api/transaction')
    
    def _hmac_sha512(self, key: str, data: str) -> str:
        """Generate HMAC SHA512 signature."""
        byte_key = key.encode('utf-8')
        byte_data = data.encode('utf-8')
        return hmac.new(byte_key, byte_data, hashlib.sha512).hexdigest()
    
    def create_payment_url(
        self,
        payment: Payment,
        ip_address: str,
        return_url: Optional[str] = None,
        bank_code: str = '',
        language: str = 'vn',
    ) -> Dict[str, Any]:
        """
        Create VNPay payment URL.
        
        Args:
            payment: Payment model instance
            ip_address: Customer IP address
            return_url: URL to redirect after payment
            bank_code: Bank code for direct bank payment
            language: Language code ('vn' or 'en')
        
        Returns:
            Dict with payment_url
        """
        try:
            # Generate transaction reference
            txn_ref = f"{payment.order.order_number}_{int(datetime.now().timestamp())}"
            
            # VNPay parameters
            vnp_params = {
                'vnp_Version': '2.1.0',
                'vnp_Command': 'pay',
                'vnp_TmnCode': self.tmn_code,
                'vnp_Amount': int(payment.amount) * 100,  # VNPay uses amount * 100
                'vnp_CurrCode': 'VND',
                'vnp_TxnRef': txn_ref,
                'vnp_OrderInfo': f"Thanh toan don hang {payment.order.order_number}",
                'vnp_OrderType': 'other',
                'vnp_Locale': language,
                'vnp_ReturnUrl': return_url or self.return_url,
                'vnp_IpAddr': ip_address,
                'vnp_CreateDate': datetime.now().strftime('%Y%m%d%H%M%S'),
            }
            
            if bank_code:
                vnp_params['vnp_BankCode'] = bank_code
            
            # Sort parameters and create query string
            sorted_params = sorted(vnp_params.items())
            query_string = urllib.parse.urlencode(sorted_params)
            
            # Generate secure hash
            secure_hash = self._hmac_sha512(self.hash_secret, query_string)
            
            # Build final payment URL
            payment_url = f"{self.payment_url}?{query_string}&vnp_SecureHash={secure_hash}"
            
            # Update payment record
            payment.transaction_id = txn_ref
            payment.payment_url = payment_url
            payment.status = 'processing'
            payment.provider_data = {
                'txn_ref': txn_ref,
                'vnp_params': vnp_params,
            }
            payment.save()
            logger.info(f"VNPay payment URL created for order {payment.order.order_number}")
            
            return {
                'success': True,
                'payment_url': payment_url,
                'txn_ref': txn_ref,
            }
            
        except Exception as e:
            logger.error(f"VNPay payment creation failed: {str(e)}")
            payment.mark_as_failed(str(e))
            return {
                'success': False,
                'error': str(e),
            }
    
    def verify_return(self, request_params: Dict[str, str]) -> Dict[str, Any]:
        """
        Verify VNPay return parameters.
        
        Args:
            request_params: Dictionary of return parameters
        
        Returns:
            Dict with verification result
        """
        try:
            # Get secure hash from params
            vnp_secure_hash = request_params.pop('vnp_SecureHash', '')
            request_params.pop('vnp_SecureHashType', None)
            
            # Sort and create query string
            sorted_params = sorted(request_params.items())
            query_string = urllib.parse.urlencode(sorted_params)
            
            # Verify signature
            expected_hash = self._hmac_sha512(self.hash_secret, query_string)
            
            if vnp_secure_hash != expected_hash:
                return {
                    'success': False,
                    'error': 'Invalid signature',
                    'is_valid': False,
                }
            
            # Get transaction info
            txn_ref = request_params.get('vnp_TxnRef', '')
            response_code = request_params.get('vnp_ResponseCode', '')
            transaction_no = request_params.get('vnp_TransactionNo', '')
            amount = int(request_params.get('vnp_Amount', 0)) // 100
            
            # Find payment
            try:
                payment = Payment.objects.get(transaction_id=txn_ref)
            except Payment.DoesNotExist:
                return {
                    'success': False,
                    'error': 'Payment not found',
                    'is_valid': True,
                }
            
            # Check response code
            if response_code == '00':
                # SECURITY: Verify amount matches database record
                expected_amount = int(payment.amount)
                if amount != expected_amount:
                    import logging
                    logger = logging.getLogger('apps.payments')
                    logger.warning(
                        f"VNPay amount mismatch! Payment {payment.id}: "
                        f"expected {expected_amount}, got {amount}"
                    )
                    payment.mark_as_failed(f"Amount mismatch: expected {expected_amount}, got {amount}")
                    return {
                        'success': False,
                        'is_valid': True,
                        'error': 'Amount mismatch - possible tampering detected',
                    }
                
                # Payment successful
                payment.provider_data.update({
                    'vnp_TransactionNo': transaction_no,
                    'vnp_ResponseCode': response_code,
                    'vnp_BankCode': request_params.get('vnp_BankCode', ''),
                    'vnp_PayDate': request_params.get('vnp_PayDate', ''),
                })
                payment.save()
                payment.mark_as_completed()
                
                return {
                    'success': True,
                    'is_valid': True,
                    'payment_id': str(payment.id),
                    'order_number': payment.order.order_number,
                    'amount': amount,
                    'message': 'Payment successful',
                }
            else:
                # Payment failed
                error_messages = {
                    '07': 'Trừ tiền thành công. Giao dịch bị nghi ngờ',
                    '09': 'Thẻ/Tài khoản chưa đăng ký dịch vụ',
                    '10': 'Xác thực không đúng quá 3 lần',
                    '11': 'Đã hết hạn chờ thanh toán',
                    '12': 'Thẻ/Tài khoản bị khóa',
                    '13': 'Nhập sai mật khẩu xác thực',
                    '24': 'Khách hàng hủy giao dịch',
                    '51': 'Tài khoản không đủ số dư',
                    '65': 'Tài khoản vượt quá hạn mức giao dịch trong ngày',
                    '75': 'Ngân hàng thanh toán đang bảo trì',
                    '79': 'Nhập sai mật khẩu quá số lần quy định',
                    '99': 'Lỗi không xác định',
                }
                
                error_msg = error_messages.get(response_code, f'Lỗi: {response_code}')
                payment.mark_as_failed(error_msg)
                
                return {
                    'success': False,
                    'is_valid': True,
                    'error': error_msg,
                    'response_code': response_code,
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'is_valid': False,
            }
    
    def query_transaction(self, payment: Payment) -> Dict[str, Any]:
        """
        Query transaction status from VNPay.
        
        Args:
            payment: Payment model instance
        
        Returns:
            Dict with transaction status
        """
        import requests
        
        try:
            txn_ref = payment.transaction_id
            request_id = f"query_{int(datetime.now().timestamp())}"
            
            params = {
                'vnp_RequestId': request_id,
                'vnp_Version': '2.1.0',
                'vnp_Command': 'querydr',
                'vnp_TmnCode': self.tmn_code,
                'vnp_TxnRef': txn_ref,
                'vnp_OrderInfo': f"Query {txn_ref}",
                'vnp_TransactionDate': payment.created_at.strftime('%Y%m%d%H%M%S'),
                'vnp_CreateDate': datetime.now().strftime('%Y%m%d%H%M%S'),
                'vnp_IpAddr': '127.0.0.1',
            }
            
            # Sort and create signature
            sorted_params = sorted(params.items())
            query_string = urllib.parse.urlencode(sorted_params)
            secure_hash = self._hmac_sha512(self.hash_secret, query_string)
            params['vnp_SecureHash'] = secure_hash
            
            response = requests.post(self.api_url, json=params, timeout=30)
            result = response.json()
            
            return {
                'success': True,
                'data': result,
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }
    
    def refund(
        self,
        payment: Payment,
        amount: int,
        reason: str,
        ip_address: str = '127.0.0.1',
    ) -> Dict[str, Any]:
        """
        Create refund request to VNPay.
        
        Args:
            payment: Payment model instance
            amount: Amount to refund
            reason: Refund reason
            ip_address: Admin IP address
        
        Returns:
            Dict with refund result
        """
        import requests
        
        try:
            txn_ref = payment.transaction_id
            request_id = f"refund_{int(datetime.now().timestamp())}"
            
            params = {
                'vnp_RequestId': request_id,
                'vnp_Version': '2.1.0',
                'vnp_Command': 'refund',
                'vnp_TmnCode': self.tmn_code,
                'vnp_TransactionType': '02',  # Full refund
                'vnp_TxnRef': txn_ref,
                'vnp_Amount': amount * 100,
                'vnp_OrderInfo': reason,
                'vnp_TransactionNo': payment.provider_data.get('vnp_TransactionNo', ''),
                'vnp_TransactionDate': payment.created_at.strftime('%Y%m%d%H%M%S'),
                'vnp_CreateDate': datetime.now().strftime('%Y%m%d%H%M%S'),
                'vnp_CreateBy': payment.user.email,
                'vnp_IpAddr': ip_address,
            }
            
            # Sort and create signature
            sorted_params = sorted(params.items())
            query_string = urllib.parse.urlencode(sorted_params)
            secure_hash = self._hmac_sha512(self.hash_secret, query_string)
            params['vnp_SecureHash'] = secure_hash
            
            response = requests.post(self.api_url, json=params, timeout=30)
            result = response.json()
            
            if result.get('vnp_ResponseCode') == '00':
                return {
                    'success': True,
                    'refund_id': result.get('vnp_TransactionNo'),
                    'data': result,
                }
            else:
                return {
                    'success': False,
                    'error': result.get('vnp_Message', 'Refund failed'),
                    'data': result,
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }
