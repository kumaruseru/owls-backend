"""
MoMo Payment Service
Documentation: https://developers.momo.vn/
"""

import hashlib
import hmac
import json
import logging
import uuid
import requests
from typing import Dict, Any, Optional
from django.conf import settings
from .models import Payment
from apps.utils.security import get_safe_provider_data

logger = logging.getLogger('apps.payments')


class MoMoService:
    """Service class for MoMo payment integration."""
    
    def __init__(self):
        self.partner_code = settings.MOMO_PARTNER_CODE
        self.access_key = settings.MOMO_ACCESS_KEY
        self.secret_key = settings.MOMO_SECRET_KEY
        self.endpoint = settings.MOMO_ENDPOINT
        self.return_url = settings.MOMO_RETURN_URL
        self.notify_url = settings.MOMO_NOTIFY_URL
        self.refund_url = getattr(settings, 'MOMO_REFUND_URL', 'https://test-payment.momo.vn/v2/gateway/api/refund')
    
    def _generate_signature(self, raw_data: str) -> str:
        """Generate HMAC SHA256 signature."""
        return hmac.new(
            self.secret_key.encode('utf-8'),
            raw_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def create_payment(
        self,
        payment: Payment,
        return_url: Optional[str] = None,
        notify_url: Optional[str] = None,
        request_type: str = 'captureWallet',
    ) -> Dict[str, Any]:
        """
        Create MoMo payment request.
        
        Args:
            payment: Payment model instance
            return_url: URL to redirect after payment
            notify_url: URL for IPN callback
            request_type: 'captureWallet' or 'payWithATM' or 'payWithCC'
        
        Returns:
            Dict with payment URL
        """
        try:
            order_id = f"{payment.order.order_number}_{uuid.uuid4().hex[:8]}"
            request_id = str(uuid.uuid4())
            amount = int(payment.amount)
            order_info = f"Thanh toan don hang {payment.order.order_number}"
            
            # Extra data (can be used for custom data)
            extra_data = json.dumps({
                'payment_id': str(payment.id),
                'order_number': payment.order.order_number,
            })
            
            # Build raw signature
            raw_signature = (
                f"accessKey={self.access_key}"
                f"&amount={amount}"
                f"&extraData={extra_data}"
                f"&ipnUrl={notify_url or self.notify_url}"
                f"&orderId={order_id}"
                f"&orderInfo={order_info}"
                f"&partnerCode={self.partner_code}"
                f"&redirectUrl={return_url or self.return_url}"
                f"&requestId={request_id}"
                f"&requestType={request_type}"
            )
            
            signature = self._generate_signature(raw_signature)
            
            # Build request body
            request_body = {
                'partnerCode': self.partner_code,
                'accessKey': self.access_key,
                'requestId': request_id,
                'amount': amount,
                'orderId': order_id,
                'orderInfo': order_info,
                'redirectUrl': return_url or self.return_url,
                'ipnUrl': notify_url or self.notify_url,
                'extraData': extra_data,
                'requestType': request_type,
                'signature': signature,
                'lang': 'vi',
            }
            
            # Send request to MoMo
            response = requests.post(
                self.endpoint,
                json=request_body,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            result = response.json()
            
            if result.get('resultCode') == 0:
                # Success
                payment.transaction_id = order_id
                payment.payment_url = result.get('payUrl')
                payment.status = 'processing'
                payment.provider_data = {
                    'request_id': request_id,
                    'order_id': order_id,
                    'pay_url': result.get('payUrl'),
                    'qr_code_url': result.get('qrCodeUrl'),
                    'deeplink': result.get('deeplink'),
                }
                payment.save()
                
                return {
                    'success': True,
                    'payment_url': result.get('payUrl'),
                    'qr_code_url': result.get('qrCodeUrl'),
                    'deeplink': result.get('deeplink'),
                    'order_id': order_id,
                }
            else:
                # Failed
                error_msg = result.get('message', 'MoMo payment creation failed')
                payment.mark_as_failed(error_msg)
                
                return {
                    'success': False,
                    'error': error_msg,
                    'result_code': result.get('resultCode'),
                }
                
        except Exception as e:
            payment.mark_as_failed(str(e))
            return {
                'success': False,
                'error': str(e),
            }
    
    def verify_ipn(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify MoMo IPN (Instant Payment Notification).
        
        Args:
            request_data: IPN request body
        
        Returns:
            Dict with verification result
        """
        try:
            # Extract data
            partner_code = request_data.get('partnerCode')
            order_id = request_data.get('orderId')
            request_id = request_data.get('requestId')
            amount = request_data.get('amount')
            order_info = request_data.get('orderInfo')
            order_type = request_data.get('orderType')
            trans_id = request_data.get('transId')
            result_code = request_data.get('resultCode')
            message = request_data.get('message')
            pay_type = request_data.get('payType')
            response_time = request_data.get('responseTime')
            extra_data = request_data.get('extraData')
            signature = request_data.get('signature')
            
            # Build raw signature for verification
            raw_signature = (
                f"accessKey={self.access_key}"
                f"&amount={amount}"
                f"&extraData={extra_data}"
                f"&message={message}"
                f"&orderId={order_id}"
                f"&orderInfo={order_info}"
                f"&orderType={order_type}"
                f"&partnerCode={partner_code}"
                f"&payType={pay_type}"
                f"&requestId={request_id}"
                f"&responseTime={response_time}"
                f"&resultCode={result_code}"
                f"&transId={trans_id}"
            )
            
            expected_signature = self._generate_signature(raw_signature)
            
            if signature != expected_signature:
                return {
                    'success': False,
                    'error': 'Invalid signature',
                    'is_valid': False,
                }
            
            # Find payment
            try:
                payment = Payment.objects.get(transaction_id=order_id)
            except Payment.DoesNotExist:
                return {
                    'success': False,
                    'error': 'Payment not found',
                    'is_valid': True,
                }
            
            # Check result code
            if result_code == 0:
                # Payment successful
                payment.provider_data.update({
                    'trans_id': trans_id,
                    'pay_type': pay_type,
                    'response_time': response_time,
                })
                payment.save()
                payment.mark_as_completed()
                
                return {
                    'success': True,
                    'is_valid': True,
                    'payment_id': str(payment.id),
                    'order_number': payment.order.order_number,
                    'trans_id': trans_id,
                }
            else:
                # Payment failed
                payment.mark_as_failed(message)
                
                return {
                    'success': False,
                    'is_valid': True,
                    'error': message,
                    'result_code': result_code,
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'is_valid': False,
            }
    
    def verify_return(self, request_params: Dict[str, str]) -> Dict[str, Any]:
        """
        Verify MoMo return parameters (same as IPN).
        
        Args:
            request_params: Return query parameters
        
        Returns:
            Dict with verification result
        """
        return self.verify_ipn(request_params)
    
    def query_transaction(self, payment: Payment) -> Dict[str, Any]:
        """
        Query transaction status from MoMo.
        
        Args:
            payment: Payment model instance
        
        Returns:
            Dict with transaction status
        """
        try:
            order_id = payment.transaction_id
            request_id = str(uuid.uuid4())
            
            raw_signature = (
                f"accessKey={self.access_key}"
                f"&orderId={order_id}"
                f"&partnerCode={self.partner_code}"
                f"&requestId={request_id}"
            )
            
            signature = self._generate_signature(raw_signature)
            
            request_body = {
                'partnerCode': self.partner_code,
                'accessKey': self.access_key,
                'requestId': request_id,
                'orderId': order_id,
                'signature': signature,
                'lang': 'vi',
            }
            
            query_url = self.endpoint.replace('/create', '/query')
            
            response = requests.post(
                query_url,
                json=request_body,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
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
        description: str = 'Refund',
    ) -> Dict[str, Any]:
        """
        Create refund request to MoMo.
        
        Args:
            payment: Payment model instance
            amount: Amount to refund
            description: Refund description
        
        Returns:
            Dict with refund result
        """
        try:
            order_id = f"refund_{payment.transaction_id}_{uuid.uuid4().hex[:8]}"
            request_id = str(uuid.uuid4())
            trans_id = payment.provider_data.get('trans_id', '')
            
            raw_signature = (
                f"accessKey={self.access_key}"
                f"&amount={amount}"
                f"&description={description}"
                f"&orderId={order_id}"
                f"&partnerCode={self.partner_code}"
                f"&requestId={request_id}"
                f"&transId={trans_id}"
            )
            
            signature = self._generate_signature(raw_signature)
            
            request_body = {
                'partnerCode': self.partner_code,
                'accessKey': self.access_key,
                'requestId': request_id,
                'orderId': order_id,
                'amount': amount,
                'transId': trans_id,
                'description': description,
                'signature': signature,
                'lang': 'vi',
            }
            
            response = requests.post(
                self.refund_url,
                json=request_body,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            result = response.json()
            
            if result.get('resultCode') == 0:
                return {
                    'success': True,
                    'refund_id': result.get('transId'),
                    'data': result,
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'Refund failed'),
                    'data': result,
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }
