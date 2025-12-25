"""
Email service for OWLS e-commerce platform.
Handles all email notifications including registration, password reset, and order notifications.
"""

from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import logging

logger = logging.getLogger('apps.users')


class EmailService:
    """Service class for sending emails."""
    
    @staticmethod
    def send_email(subject, template_name, context, to_email, from_email=None):
        """
        Send an HTML email with a plain text fallback.
        
        Args:
            subject: Email subject
            template_name: Template name (without .html extension)
            context: Context dictionary for template
            to_email: Recipient email address
            from_email: Sender email (uses DEFAULT_FROM_EMAIL if not provided)
        """
        try:
            html_content = render_to_string(f'emails/{template_name}.html', context)
            text_content = strip_tags(html_content)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email or settings.DEFAULT_FROM_EMAIL,
                to=[to_email] if isinstance(to_email, str) else to_email,
            )
            email.attach_alternative(html_content, "text/html")
            email.send()
            
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    @classmethod
    def send_verification_email(cls, user, verification_url):
        """
        Send email verification link to new user.
        
        Args:
            user: User instance
            verification_url: Full URL for email verification
        """
        context = {
            'user': user,
            'verification_url': verification_url,
            'site_name': 'OWLS',
        }
        
        return cls.send_email(
            subject='Xác nhận email của bạn - OWLS',
            template_name='verification',
            context=context,
            to_email=user.email,
        )
    
    @classmethod
    def send_password_reset_email(cls, user, reset_url):
        """
        Send password reset link to user.
        
        Args:
            user: User instance
            reset_url: Full URL for password reset
        """
        context = {
            'user': user,
            'reset_url': reset_url,
            'site_name': 'OWLS',
        }
        
        return cls.send_email(
            subject='Đặt lại mật khẩu - OWLS',
            template_name='password_reset',
            context=context,
            to_email=user.email,
        )
    
    @classmethod
    def send_order_confirmation_email(cls, order):
        """
        Send order confirmation email to customer.
        
        Args:
            order: Order instance
        """
        context = {
            'order': order,
            'items': order.items.all(),
            'site_name': 'OWLS',
        }
        
        return cls.send_email(
            subject=f'Xác nhận đơn hàng #{order.order_number} - OWLS',
            template_name='order_confirmation',
            context=context,
            to_email=order.user.email,
        )
    
    @classmethod
    def send_order_status_update_email(cls, order):
        """
        Send order status update email to customer.
        
        Args:
            order: Order instance
        """
        context = {
            'order': order,
            'status_display': order.get_status_display(),
            'site_name': 'OWLS',
        }
        
        return cls.send_email(
            subject=f'Cập nhật đơn hàng #{order.order_number} - OWLS',
            template_name='order_status_update',
            context=context,
            to_email=order.user.email,
        )
    
    @classmethod
    def send_payment_confirmation_email(cls, payment):
        """
        Send payment confirmation email to customer.
        
        Args:
            payment: Payment instance
        """
        context = {
            'payment': payment,
            'order': payment.order,
            'site_name': 'OWLS',
        }
        
        return cls.send_email(
            subject=f'Thanh toán thành công - Đơn hàng #{payment.order.order_number}',
            template_name='payment_confirmation',
            context=context,
            to_email=payment.user.email,
        )
    
    @classmethod
    def generate_verification_token(cls, user):
        """Generate email verification token and uid."""
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return uid, token
    
    @classmethod
    def generate_password_reset_token(cls, user):
        """Generate password reset token and uid."""
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return uid, token
