from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse
from .models import Payment
from .services import VNPayService, MoMoService, StripeService, PaymentService
import logging

logger = logging.getLogger('apps.billing')


class VNPayReturnView(APIView):
    """Handle VNPay payment return."""
    permission_classes = (permissions.AllowAny,)
    
    def get(self, request):
        from django.conf import settings
        
        # Log incoming params
        params = request.GET.dict()
        logger.info(f"VNPay Return Params: {params}")
        
        try:
            result = VNPayService.verify_return(params)
            logger.info(f"VNPay Return Verification Result: {result}")
            
            if result['success']:
                payment_id = result['payment_id']
                logger.info(f"Looking for payment with ID: {payment_id}")
                
                payment = Payment.objects.filter(id=payment_id).first()
                if payment:
                    logger.info(f"Payment found: {payment.id}, Status: {payment.status}")
                    
                    if payment.status != 'completed':
                        payment.transaction_id = result.get('transaction_id')
                        payment.mark_as_completed()
                        logger.info(f"Payment {payment.id} marked as completed")
                        
                        # Send confirmation email
                        try:
                            from apps.identity.services import EmailService
                            EmailService.send_payment_success_email(payment)
                        except Exception as e:
                            logger.error(f"Failed to send email: {e}")
                        
                        return redirect(f"{settings.FRONTEND_URL}/checkout/success?order_number={payment.order.order_number}")
                    else:
                        logger.info(f"Payment {payment.id} was already completed")
                        return redirect(f"{settings.FRONTEND_URL}/checkout/success?order_number={payment.order.order_number}")
                else:
                    logger.error(f"Payment not found for ID: {payment_id}")
            else:
                 logger.warning(f"VNPay verify failed: {result.get('message')}")
                 
                 # Handle failure/cancellation
                 payment_id = result.get('payment_id')
                 if payment_id:
                     payment = Payment.objects.filter(id=payment_id).first()
                     if payment:
                         if payment.status not in ['completed', 'failed', 'cancelled']:
                             logger.warning(f"VNPay payment failed for {payment.id}: {result.get('message')}")
                             payment.mark_as_failed(reason=result.get('message'))
                         
                         return redirect(f"{settings.FRONTEND_URL}/orders/{payment.order.order_number}?payment=failed&reason={result.get('message')}")
            
            # Fallback if payment_id not found or severe error
            return redirect(f"{settings.FRONTEND_URL}/checkout?payment=failed")
            
        except Exception as e:
            logger.exception(f"Exception in VNPayReturnView: {e}")
            return redirect(f"{settings.FRONTEND_URL}/checkout?payment=failed")


class VNPayVerifyAPIView(APIView):
    """Handle VNPay verification from Frontend (Client-side flow)."""
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        logger.info(f"VNPay Verify API: {request.data}")
        result = VNPayService.verify_return(request.data)
        
        if result['success']:
            payment = Payment.objects.filter(id=result['payment_id']).first()
            if payment:
                if payment.status != 'completed':
                    payment.transaction_id = result.get('transaction_id')
                    payment.mark_as_completed()
                    
                    try:
                        from apps.identity.services import EmailService
                        EmailService.send_payment_success_email(payment)
                    except Exception as e:
                        logger.error(f"Failed to send email: {e}")
                        
                return Response({'success': True, 'order_number': payment.order.order_number})
            else:
                return Response({'success': False, 'message': 'Payment not found'}, status=404)
        else:
             return Response({'success': False, 'message': result.get('message')}, status=400)


class VNPayIPNView(APIView):
    """Handle VNPay IPN (Instant Payment Notification) webhook."""
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        result = VNPayService.verify_return(request.GET.dict())
        
        if result['success']:
            payment = Payment.objects.filter(id=result['payment_id']).first()
            if payment:
                # Check order amount
                if int(payment.amount) == result['amount']:
                    if payment.status != 'completed':
                        payment.transaction_id = result.get('transaction_id')
                        payment.mark_as_completed()
                        
                        from apps.identity.services import EmailService
                        EmailService.send_payment_success_email(payment)
                        
                        logger.info(f"VNPay IPN: Payment {payment.id} confirmed")
                    return Response({"RspCode": "00", "Message": "Confirm Success"})
                else:
                    logger.error(f"VNPay IPN: Invalid amount for {payment.id}")
                    return Response({"RspCode": "04", "Message": "Invalid Amount"})
            else:
                logger.error(f"VNPay IPN: Order not found {result.get('payment_id')}")
                return Response({"RspCode": "01", "Message": "Order not found"})
        else:
            logger.error(f"VNPay IPN: Invalid checksum")
            return Response({"RspCode": "97", "Message": "Invalid Checksum"})


class MoMoReturnView(APIView):
    """Handle MoMo payment return."""
    permission_classes = (permissions.AllowAny,)
    
    def get(self, request):
        from django.conf import settings
        result = MoMoService.verify_return(request.GET.dict())
        
        if result.get('success'):
            payment = Payment.objects.filter(id=result.get('payment_id')).first()
            if payment and payment.status != 'completed':
                payment.transaction_id = result.get('transaction_id')
                payment.mark_as_completed()
                
                from apps.identity.services import EmailService
                EmailService.send_payment_success_email(payment)
                
                return redirect(f"{settings.FRONTEND_URL}/checkout/success?order_number={payment.order.order_number}")
        else:
            # Handle failure
            payment_id = result.get('payment_id')
            if payment_id:
                payment = Payment.objects.filter(id=payment_id).first()
                if payment:
                    if payment.status not in ['completed', 'failed', 'cancelled']:
                        logger.warning(f"MoMo payment failed for {payment.id}: {result.get('message')}")
                        payment.mark_as_failed(reason=result.get('message'))
                    
                    return redirect(f"{settings.FRONTEND_URL}/orders/{payment.order.order_number}?payment=failed&reason={result.get('message')}")
        
        return redirect(f"{settings.FRONTEND_URL}/checkout?payment=failed")


@method_decorator(csrf_exempt, name='dispatch')
class MoMoWebhookView(APIView):
    """Handle MoMo IPN webhook."""
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        logger.info(f"MoMo webhook received: {request.data}")
        
        result = MoMoService.verify_webhook(request.data)
        
        if result.get('success'):
            payment = Payment.objects.filter(id=result.get('payment_id')).first()
            if payment and payment.status != 'completed':
                payment.transaction_id = result.get('transaction_id')
                payment.mark_as_completed()
                
                from apps.identity.services import EmailService
                EmailService.send_payment_success_email(payment)
        else:
            # Handle failure via webhook (e.g. user cancelled)
            payment_id = result.get('payment_id') or request.data.get('orderId')
            if payment_id:
                payment = Payment.objects.filter(id=payment_id).first()
                if payment and payment.status not in ['completed', 'failed', 'cancelled']:
                    logger.warning(f"MoMo webhook failed for {payment_id}")
                    payment.mark_as_failed(reason=request.data.get('message', 'Webhook Reported Failure'))
        
        # Always return 200 to acknowledge receipt
        return Response({'received': True})


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """Handle Stripe webhook events."""
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        
        result = StripeService.handle_webhook(payload, sig_header)
        
        if result['success']:
            return Response({'received': True})
        
        logger.error(f"Stripe webhook error: {result.get('error')}")
        return Response({'error': result.get('error')}, status=status.HTTP_400_BAD_REQUEST)


class PaymentStatusView(APIView):
    """Check payment status."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def get(self, request, payment_id):
        try:
            payment = Payment.objects.get(id=payment_id, user=request.user)
            return Response({
                'id': str(payment.id),
                'status': payment.status,
                'amount': payment.amount,
                'payment_method': payment.payment_method,
                'created_at': payment.created_at,
                'paid_at': payment.paid_at,
            })
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)


class PaymentRefundView(APIView):
    """Request payment refund (Admin only)."""
    permission_classes = (permissions.IsAdminUser,)
    
    def post(self, request, payment_id):
        try:
            payment = Payment.objects.get(id=payment_id)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        
        amount = request.data.get('amount', payment.amount)
        reason = request.data.get('reason', 'Admin refund request')
        
        result = PaymentService.process_refund(payment, int(amount), reason, request)
        
        if result['success']:
            return Response({
                'message': 'Hoàn tiền thành công',
                'refund_id': str(result['refund'].id),
            })
        
        return Response({'error': result.get('error')}, status=status.HTTP_400_BAD_REQUEST)


class StripeClientSecretView(APIView):
    """Get Stripe client secret for frontend."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def get(self, request, payment_id):
        try:
            payment = Payment.objects.get(id=payment_id, user=request.user)
            client_secret = payment.provider_data.get('client_secret')
            
            if not client_secret:
                return Response({'error': 'No client secret'}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({'client_secret': client_secret})
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
