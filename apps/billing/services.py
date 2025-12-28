"""Billing services - Payment gateway integrations (VNPay, MoMo, Stripe)."""
import hashlib
import hmac
import logging
import requests
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional
from django.conf import settings
from .models import Payment, PaymentRefund

logger = logging.getLogger('apps.billing')


class PaymentService:
    """Main payment service dispatcher."""
    
    @staticmethod
    def create_payment_url(payment: Payment, request) -> Optional[str]:
        """Tạo payment URL dựa trên phương thức thanh toán."""
        from apps.utils.security import IPValidator
        
        frontend_url = request.headers.get('Origin', settings.SITE_URL)
        return_url = f"{frontend_url}/orders/{payment.order.order_number}?payment=success"
        
        try:
            if payment.payment_method == 'vnpay':
                # Use IPValidator for consistent IP extraction
                ip = IPValidator.get_client_ip(request)
                result = VNPayService.create_payment_url(payment, ip, return_url)
            elif payment.payment_method == 'momo':
                result = MoMoService.create_payment(payment, return_url)
            elif payment.payment_method == 'stripe':
                result = StripeService.create_payment_intent(payment, return_url)
            else:
                return None
            
            if result.get('success'):
                logger.info(f"Payment URL created for payment {payment.id}")
                return result.get('payment_url')
            else:
                logger.error(f"Failed to create payment URL: {result.get('error')}")
                return None
                
        except Exception as e:
            logger.exception(f"Exception creating payment URL for {payment.id}: {e}")
            return None
    
    @staticmethod
    def process_refund(payment: Payment, amount: int, reason: str, request=None) -> Dict[str, Any]:
        """Process refund for a payment."""
        if payment.status != 'completed':
            return {'success': False, 'error': 'Chỉ có thể hoàn tiền cho thanh toán đã hoàn thành'}
        
        # Check if amount is valid
        total_refunded = sum(r.amount for r in payment.refunds.filter(status='completed'))
        if amount > (payment.amount - total_refunded):
            return {'success': False, 'error': 'Số tiền hoàn vượt quá số có thể hoàn'}
        
        # Create refund record
        refund = PaymentRefund.objects.create(
            payment=payment,
            amount=amount,
            reason=reason,
            status='processing'
        )
        
        try:
            if payment.payment_method == 'vnpay':
                ip = '127.0.0.1'
                if request:
                    ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
                result = VNPayService.refund(payment, amount, reason, ip)
            elif payment.payment_method == 'momo':
                result = MoMoService.refund(payment, amount, reason)
            elif payment.payment_method == 'stripe':
                result = StripeService.refund(payment, amount)
            else:
                result = {'success': False, 'error': 'Phương thức không hỗ trợ hoàn tiền'}
            
            if result.get('success'):
                refund.status = 'completed'
                refund.refund_id = result.get('refund_id')
                refund.provider_data = result.get('data', {})
                refund.save()
                
                # Update payment status if fully refunded
                total_refunded = sum(r.amount for r in payment.refunds.filter(status='completed'))
                if total_refunded >= payment.amount:
                    payment.status = 'refunded'
                    payment.save()
                    payment.order.payment_status = 'refunded'
                    payment.order.save()
                
                return {'success': True, 'refund': refund}
            else:
                refund.status = 'failed'
                refund.provider_data = {'error': result.get('error')}
                refund.save()
                return result
                
        except Exception as e:
            refund.status = 'failed'
            refund.provider_data = {'error': str(e)}
            refund.save()
            logger.exception(f"Refund error for payment {payment.id}: {e}")
            return {'success': False, 'error': str(e)}


class VNPayService:
    """VNPay payment gateway service."""
    
    @staticmethod
    def _hmac_sha512(key: str, data: str) -> str:
        return hmac.new(key.encode(), data.encode(), hashlib.sha512).hexdigest()
    
    @staticmethod
    def create_payment_url(payment: Payment, ip_address: str, return_url: str) -> Dict[str, Any]:
        """Tạo VNPay payment URL."""
        params = {
            'vnp_Version': '2.1.0',
            'vnp_Command': 'pay',
            'vnp_TmnCode': settings.VNPAY_TMN_CODE,
            'vnp_Amount': int(payment.amount) * 100,
            'vnp_CurrCode': 'VND',
            'vnp_TxnRef': str(payment.id),
            'vnp_OrderInfo': f"Thanh toan don hang {payment.order.order_number}",
            'vnp_OrderType': 'other',
            'vnp_Locale': 'vn',
            'vnp_ReturnUrl': settings.VNPAY_RETURN_URL,
            'vnp_IpAddr': ip_address,
            'vnp_CreateDate': datetime.now().strftime('%Y%m%d%H%M%S'),
        }
        
        sorted_params = sorted(params.items())
        query_string = urllib.parse.urlencode(sorted_params)
        signature = VNPayService._hmac_sha512(settings.VNPAY_HASH_SECRET, query_string)
        
        payment_url = f"{settings.VNPAY_PAYMENT_URL}?{query_string}&vnp_SecureHash={signature}"
        payment.payment_url = payment_url
        payment.status = 'processing'
        payment.save()
        
        logger.info(f"VNPay URL created for payment {payment.id}")
        return {'success': True, 'payment_url': payment_url}
    
    @staticmethod
    def verify_return(params: Dict[str, Any]) -> Dict[str, Any]:
        """Verify VNPay return parameters."""
        # Check raw params first
        secure_hash = str(params.get('vnp_SecureHash', ''))
        
        # Filter only vnp_ parameters, exclude hash fields, convert to string
        data = {}
        for k, v in params.items():
            if k.startswith('vnp_') and k not in ['vnp_SecureHash', 'vnp_SecureHashType']:
                val = str(v)
                if val != '' and val is not None:
                    data[k] = val
        
        # Sort and build query string manually to ensure consistency
        sorted_params = sorted(data.items())
        
        # VNPay requires 'key=value' joined by '&'. Values must be URL-encoded.
        # urllib.parse.quote_plus replaces spaces with '+' (Standard application/x-www-form-urlencoded)
        # This matches what we use in create_payment_url
        query_parts = []
        for k, v in sorted_params:
            if k.startswith('vnp_') and k not in ['vnp_SecureHash', 'vnp_SecureHashType']:
                # Ensure value is string
                val = str(v) 
                if val:
                    query_parts.append(f"{k}={urllib.parse.quote_plus(val)}")
        
        query_string = '&'.join(query_parts)
            
        # Verify hash
        expected_hash = VNPayService._hmac_sha512(settings.VNPAY_HASH_SECRET, query_string)
        
        payment_id = data.get('vnp_TxnRef')
        
        if secure_hash != expected_hash:
            logger.warning(f"VNPay signature mismatch for {payment_id}")
            # Log hash for investigation if needed, but not full string to keep logs clean
            logger.warning(f"Expected: {expected_hash}, Received: {secure_hash}")
            return {'success': False, 'message': 'Invalid signature', 'payment_id': payment_id}
        
        response_code = data.get('vnp_ResponseCode')
        if response_code != '00':
            logger.warning(f"VNPay payment failed: {response_code}")
            return {
                'success': False, 
                'message': f'Payment failed: {response_code}',
                'payment_id': payment_id,
                'response_code': response_code
            }
        
        return {
            'success': True,
            'payment_id': payment_id,
            'transaction_id': data.get('vnp_TransactionNo'),
            'amount': int(data.get('vnp_Amount', 0)) // 100,
        }

# ... (omitted parts)


    
    @staticmethod
    def refund(payment: Payment, amount: int, reason: str, ip_address: str) -> Dict[str, Any]:
        """
        VNPay refund API implementation.
        Docs: https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/thanh-toan-pay.html#hoan-tien-giao-dich
        """
        import uuid
        from datetime import datetime
        
        if not payment.transaction_id:
            return {'success': False, 'error': 'Không có mã giao dịch VNPay'}
        
        request_id = str(uuid.uuid4().int)[:8]
        create_date = datetime.now().strftime('%Y%m%d%H%M%S')
        
        # VNPay refund params
        params = {
            'vnp_RequestId': request_id,
            'vnp_Version': '2.1.0',
            'vnp_Command': 'refund',
            'vnp_TmnCode': settings.VNPAY_TMN_CODE,
            'vnp_TransactionType': '02',  # 02 = Partial refund, 03 = Full refund
            'vnp_TxnRef': str(payment.id),
            'vnp_Amount': amount * 100,
            'vnp_OrderInfo': reason[:255],  # Max 255 chars
            'vnp_TransactionNo': payment.transaction_id,
            'vnp_TransactionDate': payment.paid_at.strftime('%Y%m%d%H%M%S') if payment.paid_at else create_date,
            'vnp_CreateBy': 'system',
            'vnp_CreateDate': create_date,
            'vnp_IpAddr': ip_address,
        }
        
        # Generate signature
        sorted_params = sorted(params.items())
        sign_data = '|'.join([f"{k}={v}" for k, v in sorted_params])
        signature = VNPayService._hmac_sha512(settings.VNPAY_HASH_SECRET, sign_data)
        params['vnp_SecureHash'] = signature
        
        try:
            # VNPay refund endpoint
            refund_url = settings.VNPAY_PAYMENT_URL.replace('/paymentv2/vpcpay.html', '/merchant_webapi/api/transaction')
            
            response = requests.post(
                refund_url,
                json=params,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            data = response.json()
            logger.info(f"VNPay refund response for {payment.id}: {data}")
            
            response_code = data.get('vnp_ResponseCode')
            
            if response_code == '00':
                return {
                    'success': True,
                    'refund_id': data.get('vnp_TransactionNo'),
                    'data': {
                        'response_code': response_code,
                        'message': data.get('vnp_Message'),
                        'bank_code': data.get('vnp_BankCode'),
                    }
                }
            else:
                error_messages = {
                    '02': 'TMN Code không hợp lệ',
                    '03': 'Dữ liệu gửi đi không hợp lệ',
                    '91': 'Không tìm thấy giao dịch yêu cầu hoàn',
                    '94': 'Yêu cầu trùng lặp',
                    '95': 'Giao dịch không thành công bên VNPay',
                    '97': 'Chữ ký không hợp lệ',
                    '99': 'Lỗi không xác định',
                }
                error_msg = error_messages.get(response_code, f"Mã lỗi: {response_code}")
                logger.error(f"VNPay refund failed: {response_code} - {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except requests.Timeout:
            logger.error(f"VNPay refund timeout for payment {payment.id}")
            return {'success': False, 'error': 'Kết nối VNPay timeout'}
        except requests.RequestException as e:
            logger.exception(f"VNPay refund request error: {e}")
            return {'success': False, 'error': 'Lỗi kết nối VNPay'}
        except Exception as e:
            logger.exception(f"VNPay refund unexpected error: {e}")
            return {'success': False, 'error': str(e)}


class MoMoService:
    """MoMo payment gateway service."""
    
    @staticmethod
    def _sign(data: str) -> str:
        return hmac.new(
            settings.MOMO_SECRET_KEY.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
    
    @staticmethod
    def create_payment(payment: Payment, return_url: str) -> Dict[str, Any]:
        """Tạo MoMo payment."""
        import uuid
        
        request_id = str(uuid.uuid4())
        order_id = str(payment.id)
        
        raw_signature = (
            f"accessKey={settings.MOMO_ACCESS_KEY}"
            f"&amount={int(payment.amount)}"
            f"&extraData="
            f"&ipnUrl={settings.MOMO_NOTIFY_URL}"
            f"&orderId={order_id}"
            f"&orderInfo=Thanh toan don hang {payment.order.order_number}"
            f"&partnerCode={settings.MOMO_PARTNER_CODE}"
            f"&redirectUrl={return_url}"
            f"&requestId={request_id}"
            f"&requestType=payWithMethod"
        )
        signature = MoMoService._sign(raw_signature)
        
        payload = {
            'partnerCode': settings.MOMO_PARTNER_CODE,
            'accessKey': settings.MOMO_ACCESS_KEY,
            'requestId': request_id,
            'amount': int(payment.amount),
            'orderId': order_id,
            'orderInfo': f"Thanh toan don hang {payment.order.order_number}",
            'redirectUrl': return_url,
            'ipnUrl': settings.MOMO_NOTIFY_URL,
            'extraData': '',
            'requestType': 'payWithMethod',
            'signature': signature,
            'lang': 'vi',
        }
        
        try:
            logger.info(f"Sending MoMo request to {settings.MOMO_ENDPOINT}")
            response = requests.post(settings.MOMO_ENDPOINT, json=payload, timeout=30)
            
            try:
                data = response.json()
            except ValueError as e:
                logger.error(f"MoMo JSON Decode Error. Status: {response.status_code}, Body: {response.text}")
                return {'success': False, 'error': f"MoMo Gateway Error: {response.status_code} - Invalid Response"}

            if data.get('resultCode') == 0:
                payment.payment_url = data.get('payUrl')
                payment.transaction_id = request_id
                payment.status = 'processing'
                payment.provider_data = {'momo_order_id': data.get('orderId')}
                payment.save()
                
                logger.info(f"MoMo payment created for {payment.id}")
                return {'success': True, 'payment_url': data.get('payUrl')}
            
            logger.error(f"MoMo error: {data.get('message')}")
            return {'success': False, 'error': data.get('message')}
            
        except Exception as e:
            logger.exception(f"MoMo exception: {e}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def verify_return(params: Dict[str, str]) -> Dict[str, Any]:
        """Verify MoMo return parameters."""
        result_code = params.get('resultCode')
        if str(result_code) == '0':
            return {
                'success': True,
                'payment_id': params.get('orderId'),
                'transaction_id': params.get('transId'),
            }
        return {'success': False}
    
    @staticmethod
    def verify_webhook(data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify MoMo webhook/IPN."""
        result_code = data.get('resultCode')
        if result_code == 0:
            return {
                'success': True,
                'payment_id': data.get('orderId'),
                'transaction_id': data.get('transId'),
            }
        return {'success': False}
    
    @staticmethod
    def refund(payment: Payment, amount: int, reason: str) -> Dict[str, Any]:
        """
        MoMo refund API implementation.
        Docs: https://developers.momo.vn/v3/vi/docs/payment/api/wallet/refund
        """
        import uuid
        
        if not payment.transaction_id:
            return {'success': False, 'error': 'Không có mã giao dịch MoMo'}
        
        momo_trans_id = payment.provider_data.get('momo_trans_id')
        if not momo_trans_id:
            # Try to get from transaction_id
            momo_trans_id = payment.transaction_id
        
        request_id = str(uuid.uuid4())
        order_id = f"REFUND_{payment.id}_{request_id[:8]}"
        
        # Build signature
        raw_signature = (
            f"accessKey={settings.MOMO_ACCESS_KEY}"
            f"&amount={amount}"
            f"&description={reason[:255]}"
            f"&orderId={order_id}"
            f"&partnerCode={settings.MOMO_PARTNER_CODE}"
            f"&requestId={request_id}"
            f"&transId={momo_trans_id}"
        )
        signature = MoMoService._sign(raw_signature)
        
        payload = {
            'partnerCode': settings.MOMO_PARTNER_CODE,
            'orderId': order_id,
            'requestId': request_id,
            'amount': amount,
            'transId': momo_trans_id,
            'lang': 'vi',
            'description': reason[:255],
            'signature': signature,
        }
        
        try:
            # MoMo refund endpoint
            refund_endpoint = settings.MOMO_ENDPOINT.replace('/create', '/refund')
            
            response = requests.post(
                refund_endpoint,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            data = response.json()
            logger.info(f"MoMo refund response for {payment.id}: {data}")
            
            result_code = data.get('resultCode')
            
            if result_code == 0:
                return {
                    'success': True,
                    'refund_id': data.get('transId'),
                    'data': {
                        'result_code': result_code,
                        'message': data.get('message'),
                        'order_id': data.get('orderId'),
                    }
                }
            else:
                error_messages = {
                    1: 'Hệ thống đang bảo trì',
                    2: 'Giao dịch không hợp lệ',
                    3: 'Tài khoản không đủ tiền',
                    4: 'Số tiền không hợp lệ',
                    7: 'Giao dịch đang được xử lý',
                    9: 'Giao dịch bị từ chối',
                    10: 'Số tiền hoàn vượt quá số tiền gốc',
                    11: 'Giao dịch không tìm thấy',
                    21: 'Giao dịch không tìm thấy trong hệ thống MoMo',
                    1001: 'Giao dịch thanh toán bị lỗi',
                    1002: 'Giao dịch bị từ chối bởi bên thanh toán',
                    1003: 'Giao dịch bị hủy',
                    1004: 'Số tiền thanh toán vượt quá hạn mức',
                    1005: 'URL hoặc QR code đã hết hạn',
                    1006: 'Người dùng từ chối thanh toán',
                }
                error_msg = error_messages.get(result_code, data.get('message', f'Mã lỗi: {result_code}'))
                logger.error(f"MoMo refund failed: {result_code} - {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except requests.Timeout:
            logger.error(f"MoMo refund timeout for payment {payment.id}")
            return {'success': False, 'error': 'Kết nối MoMo timeout'}
        except requests.RequestException as e:
            logger.exception(f"MoMo refund request error: {e}")
            return {'success': False, 'error': 'Lỗi kết nối MoMo'}
        except Exception as e:
            logger.exception(f"MoMo refund unexpected error: {e}")
            return {'success': False, 'error': str(e)}


class StripeService:
    """Stripe payment gateway service."""
    
    @staticmethod
    def _get_stripe():
        """Get configured Stripe module."""
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        return stripe
    
    @staticmethod
    def create_payment_intent(payment: Payment, return_url: str) -> Dict[str, Any]:
        """Create Stripe PaymentIntent."""
        if not settings.STRIPE_SECRET_KEY:
            return {'success': False, 'error': 'Stripe not configured'}
        
        try:
            stripe = StripeService._get_stripe()
            
            # Create PaymentIntent
            intent = stripe.PaymentIntent.create(
                amount=int(payment.amount),  # Stripe uses smallest currency unit
                currency='vnd',
                metadata={
                    'payment_id': str(payment.id),
                    'order_number': payment.order.order_number,
                },
                automatic_payment_methods={'enabled': True},
            )
            
            payment.transaction_id = intent.id
            payment.provider_data = {'client_secret': intent.client_secret}
            payment.status = 'processing'
            payment.save()
            
            logger.info(f"Stripe PaymentIntent created: {intent.id}")
            
            # For Stripe, we return client_secret for frontend
            return {
                'success': True,
                'payment_url': None,  # Stripe uses client-side SDK
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id,
            }
            
        except Exception as e:
            logger.exception(f"Stripe error: {e}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def handle_webhook(payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Handle Stripe webhook events."""
        if not settings.STRIPE_WEBHOOK_SECRET:
            return {'success': False, 'error': 'Webhook secret not configured'}
        
        try:
            stripe = StripeService._get_stripe()
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            return {'success': False, 'error': 'Invalid payload'}
        except stripe.error.SignatureVerificationError:
            return {'success': False, 'error': 'Invalid signature'}
        
        # Handle the event
        if event['type'] == 'payment_intent.succeeded':
            intent = event['data']['object']
            payment_id = intent['metadata'].get('payment_id')
            
            if payment_id:
                try:
                    payment = Payment.objects.get(id=payment_id)
                    if payment.status != 'completed':
                        payment.transaction_id = intent['id']
                        payment.mark_as_completed()
                        logger.info(f"Stripe payment completed: {payment_id}")
                except Payment.DoesNotExist:
                    logger.error(f"Payment not found: {payment_id}")
        
        elif event['type'] == 'payment_intent.payment_failed':
            intent = event['data']['object']
            payment_id = intent['metadata'].get('payment_id')
            
            if payment_id:
                try:
                    payment = Payment.objects.get(id=payment_id)
                    payment.mark_as_failed(intent.get('last_payment_error', {}).get('message'))
                    logger.warning(f"Stripe payment failed: {payment_id}")
                except Payment.DoesNotExist:
                    pass
        
        return {'success': True}
    
    @staticmethod
    def refund(payment: Payment, amount: int) -> Dict[str, Any]:
        """Create Stripe refund."""
        if not settings.STRIPE_SECRET_KEY:
            return {'success': False, 'error': 'Stripe not configured'}
        
        try:
            stripe = StripeService._get_stripe()
            
            refund = stripe.Refund.create(
                payment_intent=payment.transaction_id,
                amount=amount,
            )
            
            logger.info(f"Stripe refund created: {refund.id}")
            return {
                'success': True,
                'refund_id': refund.id,
                'data': {'status': refund.status},
            }
            
        except Exception as e:
            logger.exception(f"Stripe refund error: {e}")
            return {'success': False, 'error': str(e)}
