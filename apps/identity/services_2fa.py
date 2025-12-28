import pyotp
import qrcode
import io
import base64
import secrets
from django.conf import settings
from django.core.cache import cache
from .services import EmailService

class TwoFactorService:
    @staticmethod
    def generate_secret():
        """Generates a random base32 secret."""
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(user, secret):
        """Generates the otpauth URI for the authenticator app."""
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name="OWLS Store"
        )

    @staticmethod
    def generate_qr_code(uri):
        """Generates a base64 encoded QR code image from the URI."""
        qr = qrcode.make(uri)
        img_buffer = io.BytesIO()
        qr.save(img_buffer, format='PNG')
        img_str = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{img_str}"

    @staticmethod
    def verify_totp(secret, code):
        """Verifies a TOTP code against the secret."""
        if not secret:
            return False
        totp = pyotp.TOTP(secret)
        return totp.verify(code)

    @staticmethod
    def generate_backup_codes(count=12, length=6):
        """Generates a list of random 6-digit backup codes."""
        codes = []
        for _ in range(count):
            # Generate a 6-digit number string
            token = "".join(secrets.choice("0123456789") for _ in range(length))
            codes.append(token)
        return codes

    @staticmethod
    def verify_backup_code(user, code):
        """
        Verifies if the code is in the user's backup codes.
        If found, removes it (one-time use) and saves the user.
        Returns True if valid, False otherwise.
        """
        if not user.backup_codes:
            return False
        
        if code in user.backup_codes:
            user.backup_codes.remove(code)
            user.save(update_fields=['backup_codes'])
            return True
        return False

    @staticmethod
    def generate_email_otp(user):
        """Generates a 6-digit OTP, caches it, and sends via email."""
        # Generate 6 digit crypto secure OTP
        otp = "".join(secrets.choice("0123456789") for _ in range(6))
        
        # Cache for 5 minutes
        cache_key = f"email_2fa_{user.id}"
        cache.set(cache_key, otp, timeout=300)
        
        # Send Email
        subject = "Mã xác thực 2 lớp - OWLS Store"
        message = f"""
Xin chào {user.full_name},

Mã xác thực 2 lớp (2FA) của bạn là: {otp}

Mã này sẽ hết hạn sau 5 phút. Vui lòng không chia sẻ mã này cho bất kỳ ai.

Nếu bạn không yêu cầu mã này, vui lòng đổi mật khẩu ngay lập tức.

Trân trọng,
OWLS Store Team
        """
        try:
            EmailService._send_email(subject, message, user.email)
            return True
        except Exception:
            return False

    @staticmethod
    def verify_email_otp(user, code):
        """Verifies the cached Email OTP."""
        cache_key = f"email_2fa_{user.id}"
        cached_otp = cache.get(cache_key)
        
        if cached_otp and str(cached_otp) == str(code):
            # Invalidate after use
            cache.delete(cache_key)
            return True
        return False
