"""Identity services - Email verification, password reset, authentication logic."""
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from typing import Optional

logger = logging.getLogger('apps.identity')


class EmailService:
    """Service for sending transactional emails."""
    
    @staticmethod
    def _send_email(subject: str, message: str, recipient_email: str, html_message: Optional[str] = None) -> bool:
        """Send email with error handling."""
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                html_message=html_message,
                fail_silently=False,
            )
            logger.info(f"Email sent successfully to {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {e}")
            return False
    
    @staticmethod
    def send_verification_email(user, request=None) -> bool:
        """Send email verification link."""
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        frontend_url = settings.SITE_URL
        if request:
            frontend_url = request.headers.get('Origin', frontend_url)
        
        verification_url = f"{frontend_url}/verify-email/{uid}/{token}/"
        
        subject = "Xác thực email - OWLS Store"
        message = f"""
Xin chào {user.full_name},

Vui lòng xác thực email của bạn bằng cách click vào link sau:
{verification_url}

Link này sẽ hết hạn sau 24 giờ.

Trân trọng,
OWLS Store Team
        """
        
        return EmailService._send_email(subject, message, user.email)
    
    @staticmethod
    def send_password_reset_email(user, request=None) -> bool:
        """Send password reset link."""
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        frontend_url = settings.SITE_URL
        if request:
            frontend_url = request.headers.get('Origin', frontend_url)
        
        reset_url = f"{frontend_url}/reset-password/{uid}/{token}/"
        
        subject = "Đặt lại mật khẩu - OWLS Store"
        message = f"""
Xin chào {user.full_name},

Bạn đã yêu cầu đặt lại mật khẩu. Click vào link sau để tiếp tục:
{reset_url}

Link này sẽ hết hạn sau 1 giờ.

Nếu bạn không yêu cầu đặt lại mật khẩu, vui lòng bỏ qua email này.

Trân trọng,
OWLS Store Team
        """
        
        return EmailService._send_email(subject, message, user.email)
    
    @staticmethod
    def send_order_confirmation_email(order) -> bool:
        """Send order confirmation email."""
        subject = f"Xác nhận đơn hàng #{order.order_number} - OWLS Store"
        
        items_text = "\n".join([
            f"  - {item.product_name} x{item.quantity}: {item.subtotal:,.0f}đ"
            for item in order.items.all()
        ])
        
        message = f"""
Xin chào {order.recipient_name},

Cảm ơn bạn đã đặt hàng tại OWLS Store!

Mã đơn hàng: #{order.order_number}
Trạng thái: {order.get_status_display()}
Phương thức thanh toán: {order.get_payment_method_display()}

Sản phẩm:
{items_text}

Tạm tính: {order.subtotal:,.0f}đ
Phí vận chuyển: {order.shipping_fee:,.0f}đ
Giảm giá: {order.discount:,.0f}đ
Tổng cộng: {order.total:,.0f}đ

Địa chỉ giao hàng:
{order.full_address}

Chúng tôi sẽ liên hệ với bạn sớm nhất có thể.

Trân trọng,
OWLS Store Team
        """
        
        return EmailService._send_email(subject, message, order.email or order.user.email)
    
    @staticmethod
    def send_payment_success_email(payment) -> bool:
        """Send payment success notification."""
        order = payment.order
        subject = f"Thanh toán thành công - Đơn hàng #{order.order_number}"
        
        message = f"""
Xin chào {order.recipient_name},

Thanh toán cho đơn hàng #{order.order_number} đã thành công!

Số tiền: {payment.amount:,.0f}đ
Phương thức: {payment.get_payment_method_display()}
Mã giao dịch: {payment.transaction_id or 'N/A'}

Đơn hàng của bạn đang được xử lý.

Trân trọng,
OWLS Store Team
        """
        
        return EmailService._send_email(subject, message, order.email or order.user.email)


class AuthService:
    """Authentication and authorization service with security integration."""
    
    @staticmethod
    def authenticate_user(email: str, password: str, request=None):
        """Authenticate user with security checks and audit logging."""
        from django.contrib.auth import get_user_model
        from apps.utils.security import SecurityAuditLogger, IPValidator
        
        User = get_user_model()
        audit = SecurityAuditLogger()
        
        # Get client IP for logging
        ip = IPValidator.get_client_ip(request) if request else '0.0.0.0'
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:100] if request else ''
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            audit.log_login_attempt(email, False, ip, user_agent)
            return None, "Email hoặc mật khẩu không đúng"
        
        # Check if account is locked
        if user.is_locked:
            audit.log_suspicious_activity("Login to locked account", {
                'email': email, 'ip': ip
            })
            return None, "Tài khoản đã bị khóa. Vui lòng thử lại sau 30 phút"
        
        # Check if account is deleted
        if user.is_deleted:
            return None, "Tài khoản không tồn tại"
        
        # Verify password
        if not user.check_password(password):
            user.record_failed_login()
            audit.log_login_attempt(email, False, ip, user_agent)
            
            remaining = 5 - user.failed_login_attempts
            if remaining > 0:
                return None, f"Email hoặc mật khẩu không đúng. Còn {remaining} lần thử"
            
            audit.log_suspicious_activity("Account locked due to failed logins", {
                'email': email, 'ip': ip, 'attempts': user.failed_login_attempts
            })
            return None, "Tài khoản đã bị khóa do nhập sai mật khẩu quá nhiều lần"
        
        # Successful login
        user.reset_failed_logins()
        audit.log_login_attempt(email, True, ip, user_agent)
        
        return user, None
    
    @staticmethod
    def verify_email_token(uidb64: str, token: str):
        """Verify email verification token."""
        from django.utils.http import urlsafe_base64_decode
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None, "Link không hợp lệ"
        
        if not default_token_generator.check_token(user, token):
            return None, "Link đã hết hạn hoặc không hợp lệ"
        
        return user, None
    
    @staticmethod
    def reset_password(uidb64: str, token: str, new_password: str, request=None):
        """Reset password with token validation and security checks."""
        from apps.utils.security import PasswordValidator, SecurityAuditLogger, IPValidator
        
        # Validate password strength
        is_valid, errors, score = PasswordValidator.validate_strength(new_password)
        if not is_valid:
            return None, errors[0] if errors else "Mật khẩu không đủ mạnh"
        
        user, error = AuthService.verify_email_token(uidb64, token)
        if error:
            return None, error
        
        from django.utils import timezone
        user.set_password(new_password)
        user.last_password_change = timezone.now()
        user.save()
        
        # Log password change
        audit = SecurityAuditLogger()
        ip = IPValidator.get_client_ip(request) if request else '0.0.0.0'
        audit.log_password_change(str(user.id), ip)
        
        return user, None
    
    @staticmethod
    def change_password(user, old_password: str, new_password: str, request=None):
        """Change password with validation and audit logging."""
        from apps.utils.security import PasswordValidator, SecurityAuditLogger, IPValidator
        
        # Verify old password
        if not user.check_password(old_password):
            return False, "Mật khẩu cũ không đúng"
        
        # Validate new password strength
        is_valid, errors, score = PasswordValidator.validate_strength(new_password)
        if not is_valid:
            return False, errors[0] if errors else "Mật khẩu mới không đủ mạnh"
        
        # Check password not same as old
        if old_password == new_password:
            return False, "Mật khẩu mới không được trùng với mật khẩu cũ"
        
        from django.utils import timezone
        user.set_password(new_password)
        user.last_password_change = timezone.now()
        user.save()
        
        # Log password change
        audit = SecurityAuditLogger()
        ip = IPValidator.get_client_ip(request) if request else '0.0.0.0'
        audit.log_password_change(str(user.id), ip)
        
        return True, "Đổi mật khẩu thành công"

