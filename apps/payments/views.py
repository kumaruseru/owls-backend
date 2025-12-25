from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse
import json

from .models import Payment, PaymentRefund
from .serializers import (
    PaymentSerializer,
    PaymentCreateSerializer,
    RefundCreateSerializer,
    PaymentRefundSerializer,
)
from .stripe_service import StripeService
from .vnpay_service import VNPayService
from .momo_service import MoMoService
from apps.orders.models import Order


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class PaymentListView(generics.ListAPIView):
    """List user's payments."""
    
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = PaymentSerializer
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)


class PaymentDetailView(generics.RetrieveAPIView):
    """Get payment details."""
    
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = PaymentSerializer
    lookup_field = 'id'
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)


class CreatePaymentView(APIView):
    """Create a new payment for an order."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        order = get_object_or_404(Order, id=data['order_id'], user=request.user)
        payment_method = data['payment_method']
        
        # Create payment record
        payment = Payment.objects.create(
            order=order,
            user=request.user,
            payment_method=payment_method,
            amount=order.total,
        )
        
        # Handle COD (Cash on Delivery)
        if payment_method == 'cod':
            payment.status = 'completed'
            payment.save()
            return Response({
                'success': True,
                'message': 'Đơn hàng sẽ được thanh toán khi nhận hàng.',
                'payment': PaymentSerializer(payment).data,
            })
        
        # Get return/cancel URLs
        return_url = data.get('return_url', request.build_absolute_uri('/payment/success/'))
        cancel_url = data.get('cancel_url', request.build_absolute_uri('/payment/cancel/'))
        
        # Handle Stripe
        if payment_method == 'stripe':
            service = StripeService()
            result = service.create_checkout_session(
                payment=payment,
                success_url=return_url,
                cancel_url=cancel_url,
            )
            
            if result['success']:
                return Response({
                    'success': True,
                    'payment': PaymentSerializer(payment).data,
                    'checkout_url': result['checkout_url'],
                    'session_id': result['session_id'],
                    'public_key': result['public_key'],
                })
            else:
                return Response({
                    'success': False,
                    'error': result['error'],
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle VNPay
        elif payment_method == 'vnpay':
            service = VNPayService()
            result = service.create_payment_url(
                payment=payment,
                ip_address=get_client_ip(request),
                return_url=return_url,
                bank_code=data.get('bank_code', ''),
            )
            
            if result['success']:
                return Response({
                    'success': True,
                    'payment': PaymentSerializer(payment).data,
                    'payment_url': result['payment_url'],
                    'txn_ref': result['txn_ref'],
                })
            else:
                return Response({
                    'success': False,
                    'error': result['error'],
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle MoMo
        elif payment_method == 'momo':
            service = MoMoService()
            result = service.create_payment(
                payment=payment,
                return_url=return_url,
                request_type=data.get('request_type', 'captureWallet'),
            )
            
            if result['success']:
                return Response({
                    'success': True,
                    'payment': PaymentSerializer(payment).data,
                    'payment_url': result['payment_url'],
                    'qr_code_url': result.get('qr_code_url'),
                    'deeplink': result.get('deeplink'),
                })
            else:
                return Response({
                    'success': False,
                    'error': result['error'],
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': False,
            'error': 'Phương thức thanh toán không hợp lệ.',
        }, status=status.HTTP_400_BAD_REQUEST)


# ==================== STRIPE WEBHOOKS ====================

@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """Handle Stripe webhooks."""
    
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        
        service = StripeService()
        event = service.verify_webhook(payload, sig_header)
        
        if not event:
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        
        service.handle_webhook_event(event)
        
        return Response({'status': 'success'})


# ==================== VNPAY CALLBACKS ====================

class VNPayReturnView(APIView):
    """Handle VNPay return callback."""
    
    permission_classes = (permissions.AllowAny,)
    
    def get(self, request):
        params = dict(request.query_params)
        # Flatten the params (QueryDict returns lists)
        params = {k: v[0] if isinstance(v, list) else v for k, v in params.items()}
        
        service = VNPayService()
        result = service.verify_return(params)
        
        if result['success']:
            return Response({
                'success': True,
                'message': 'Thanh toán thành công!',
                'order_number': result.get('order_number'),
                'amount': result.get('amount'),
            })
        else:
            return Response({
                'success': False,
                'error': result.get('error'),
            }, status=status.HTTP_400_BAD_REQUEST if result.get('is_valid') else status.HTTP_403_FORBIDDEN)


@method_decorator(csrf_exempt, name='dispatch')
class VNPayIPNView(APIView):
    """Handle VNPay IPN callback."""
    
    permission_classes = (permissions.AllowAny,)
    
    def get(self, request):
        params = dict(request.query_params)
        params = {k: v[0] if isinstance(v, list) else v for k, v in params.items()}
        
        service = VNPayService()
        result = service.verify_return(params)
        
        if result.get('is_valid'):
            # Return response in VNPay format
            return HttpResponse(json.dumps({
                'RspCode': '00' if result['success'] else '99',
                'Message': 'Confirm Success' if result['success'] else result.get('error', 'Unknown error'),
            }), content_type='application/json')
        else:
            return HttpResponse(json.dumps({
                'RspCode': '97',
                'Message': 'Invalid Signature',
            }), content_type='application/json')


# ==================== MOMO CALLBACKS ====================

class MoMoReturnView(APIView):
    """Handle MoMo return callback."""
    
    permission_classes = (permissions.AllowAny,)
    
    def get(self, request):
        params = dict(request.query_params)
        params = {k: v[0] if isinstance(v, list) else v for k, v in params.items()}
        
        service = MoMoService()
        result = service.verify_return(params)
        
        if result['success']:
            return Response({
                'success': True,
                'message': 'Thanh toán thành công!',
                'order_number': result.get('order_number'),
                'trans_id': result.get('trans_id'),
            })
        else:
            return Response({
                'success': False,
                'error': result.get('error'),
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class MoMoWebhookView(APIView):
    """Handle MoMo IPN webhook."""
    
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
        
        service = MoMoService()
        result = service.verify_ipn(data)
        
        # Always return 204 to acknowledge receipt
        return Response(status=status.HTTP_204_NO_CONTENT)


# ==================== REFUNDS ====================

class CreateRefundView(APIView):
    """Create a refund for a payment."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        serializer = RefundCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        payment = get_object_or_404(Payment, id=data['payment_id'], user=request.user)
        amount = data.get('amount') or int(payment.amount)
        reason = data['reason']
        
        # Create refund record
        refund = PaymentRefund.objects.create(
            payment=payment,
            amount=amount,
            reason=reason,
        )
        
        # Process refund based on payment method
        result = {'success': False, 'error': 'Refund not supported'}
        
        if payment.payment_method == 'stripe':
            service = StripeService()
            result = service.create_refund(payment, amount, reason)
        
        elif payment.payment_method == 'vnpay':
            service = VNPayService()
            result = service.refund(payment, amount, reason, get_client_ip(request))
        
        elif payment.payment_method == 'momo':
            service = MoMoService()
            result = service.refund(payment, amount, reason)
        
        if result['success']:
            refund.status = 'completed'
            refund.refund_id = result.get('refund_id')
            refund.provider_data = result.get('data', {})
            refund.save()
            
            payment.status = 'refunded'
            payment.save()
            
            return Response({
                'success': True,
                'message': 'Hoàn tiền thành công!',
                'refund': PaymentRefundSerializer(refund).data,
            })
        else:
            refund.status = 'failed'
            refund.provider_data = {'error': result.get('error')}
            refund.save()
            
            return Response({
                'success': False,
                'error': result.get('error'),
            }, status=status.HTTP_400_BAD_REQUEST)


class PaymentStatusView(APIView):
    """Check payment status."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def get(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)
        
        return Response({
            'payment_id': str(payment.id),
            'status': payment.status,
            'status_display': payment.get_status_display(),
            'payment_method': payment.payment_method,
            'amount': payment.amount,
            'paid_at': payment.paid_at,
        })
