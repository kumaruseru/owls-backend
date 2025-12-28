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
    def verify_totp(secret, code, user_id=None):
        """Verifies a TOTP code against the secret with brute-force protection."""
        if not secret:
            return False
        
        # Brute-force protection
        if user_id:
            cache_key = f"2fa_attempts_{user_id}"
            attempts = cache.get(cache_key, 0)
            if attempts >= 5:
                return False  # Locked out
            
        totp = pyotp.TOTP(secret)
        is_valid = totp.verify(code)
        
        if user_id:
            if not is_valid:
                cache.set(cache_key, attempts + 1, timeout=1800)  # 30 min lockout
            else:
                cache.delete(cache_key)  # Reset on success
        
        return is_valid

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
        """Verifies the cached Email OTP with brute-force protection."""
        # Brute-force protection
        lock_key = f"2fa_email_lock_{user.id}"
        attempts_key = f"2fa_email_attempts_{user.id}"
        
        if cache.get(lock_key):
            return False  # User is locked out
            
        attempts = cache.get(attempts_key, 0)
        
        cache_key = f"email_2fa_{user.id}"
        cached_otp = cache.get(cache_key)
        
        if cached_otp and str(cached_otp) == str(code):
            # Invalidate after use and reset attempts
            cache.delete(cache_key)
            cache.delete(attempts_key)
            return True
        
        # Failed attempt
        attempts += 1
        if attempts >= 5:
            cache.set(lock_key, True, timeout=1800)  # 30 min lockout
            cache.delete(attempts_key)
        else:
            cache.set(attempts_key, attempts, timeout=300)  # Track for 5 min
        
        return False
