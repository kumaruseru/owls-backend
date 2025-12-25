"""
Stripe Payment Service
Documentation: https://stripe.com/docs/api
"""

import logging
import stripe
from django.conf import settings
from django.urls import reverse
from typing import Optional, Dict, Any
from .models import Payment
from apps.utils.security import get_safe_provider_data

logger = logging.getLogger('apps.payments')


class StripeService:
    """Service class for Stripe payment integration."""
    
    def __init__(self):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.public_key = settings.STRIPE_PUBLIC_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    
    def create_checkout_session(
        self,
        payment: Payment,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout Session.
        
        Args:
            payment: Payment model instance
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment is cancelled
        
        Returns:
            Dict with session_id and checkout_url
        """
        try:
            # Build line items from order
            line_items = []
            for item in payment.order.items.all():
                line_items.append({
                    'price_data': {
                        'currency': 'vnd',
                        'product_data': {
                            'name': item.product_name,
                            'images': [item.product_image] if item.product_image else [],
                        },
                        'unit_amount': int(item.price),
                    },
                    'quantity': item.quantity,
                })
            
            # Add shipping fee if any
            if payment.order.shipping_fee > 0:
                line_items.append({
                    'price_data': {
                        'currency': 'vnd',
                        'product_data': {
                            'name': 'Phí vận chuyển',
                        },
                        'unit_amount': int(payment.order.shipping_fee),
                    },
                    'quantity': 1,
                })
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=cancel_url,
                client_reference_id=str(payment.id),
                customer_email=payment.user.email,
                metadata={
                    'payment_id': str(payment.id),
                    'order_number': payment.order.order_number,
                },
            )
            
            # Update payment with session info
            payment.transaction_id = session.id
            payment.payment_url = session.url
            payment.status = 'processing'
            payment.provider_data = {
                'session_id': session.id,
                'payment_intent': session.payment_intent,
            }
            payment.save()
            
            return {
                'success': True,
                'session_id': session.id,
                'checkout_url': session.url,
                'public_key': self.public_key,
            }
            
        except stripe.error.StripeError as e:
            payment.mark_as_failed(str(e))
            return {
                'success': False,
                'error': str(e),
            }
    
    def create_payment_intent(
        self,
        payment: Payment,
    ) -> Dict[str, Any]:
        """
        Create a Stripe Payment Intent for custom integration.
        
        Args:
            payment: Payment model instance
        
        Returns:
            Dict with client_secret for frontend
        """
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(payment.amount),
                currency='vnd',
                metadata={
                    'payment_id': str(payment.id),
                    'order_number': payment.order.order_number,
                },
                receipt_email=payment.user.email,
            )
            
            payment.transaction_id = intent.id
            payment.status = 'processing'
            payment.provider_data = {
                'payment_intent_id': intent.id,
                'client_secret': intent.client_secret,
            }
            payment.save()
            
            return {
                'success': True,
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id,
                'public_key': self.public_key,
            }
            
        except stripe.error.StripeError as e:
            payment.mark_as_failed(str(e))
            return {
                'success': False,
                'error': str(e),
            }
    
    def verify_webhook(self, payload: bytes, sig_header: str) -> Optional[Dict]:
        """
        Verify Stripe webhook signature.
        
        Args:
            payload: Raw request body
            sig_header: Stripe signature header
        
        Returns:
            Event dict if valid, None if invalid
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
            return event
        except (ValueError, stripe.error.SignatureVerificationError):
            return None
    
    def handle_webhook_event(self, event: Dict) -> bool:
        """
        Handle Stripe webhook events.
        
        Args:
            event: Stripe event dict
        
        Returns:
            True if handled successfully
        """
        event_type = event['type']
        data = event['data']['object']
        
        if event_type == 'checkout.session.completed':
            session_id = data['id']
            try:
                payment = Payment.objects.get(transaction_id=session_id)
                payment.mark_as_completed()
                return True
            except Payment.DoesNotExist:
                return False
        
        elif event_type == 'payment_intent.succeeded':
            intent_id = data['id']
            try:
                payment = Payment.objects.get(transaction_id=intent_id)
                payment.mark_as_completed()
                return True
            except Payment.DoesNotExist:
                return False
        
        elif event_type == 'payment_intent.payment_failed':
            intent_id = data['id']
            try:
                payment = Payment.objects.get(transaction_id=intent_id)
                payment.mark_as_failed(data.get('last_payment_error', {}).get('message'))
                return True
            except Payment.DoesNotExist:
                return False
        
        return True
    
    def create_refund(
        self,
        payment: Payment,
        amount: Optional[int] = None,
        reason: str = 'requested_by_customer',
    ) -> Dict[str, Any]:
        """
        Create a refund for a payment.
        
        Args:
            payment: Payment model instance
            amount: Amount to refund (None for full refund)
            reason: Refund reason
        
        Returns:
            Dict with refund info
        """
        try:
            payment_intent_id = payment.provider_data.get('payment_intent') or payment.transaction_id
            
            refund_params = {
                'payment_intent': payment_intent_id,
                'reason': reason,
            }
            if amount:
                refund_params['amount'] = amount
            
            refund = stripe.Refund.create(**refund_params)
            
            return {
                'success': True,
                'refund_id': refund.id,
                'amount': refund.amount,
                'status': refund.status,
            }
            
        except stripe.error.StripeError as e:
            return {
                'success': False,
                'error': str(e),
            }
