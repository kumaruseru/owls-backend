"""
Advanced Security Utilities for OWLS E-Commerce Platform.

This module provides comprehensive security utilities including:
- Sensitive data filtering for logs
- Input sanitization
- Rate limiting helpers
- Security headers management
- HMAC signature verification
- IP address validation
- Password strength validation
- XSS/SQL injection detection
- Secure token generation
"""

import logging
import re
import hmac
import hashlib
import secrets
import string
import ipaddress
from typing import Optional, List, Dict, Any, Tuple
from functools import wraps
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest


# ==================== LOGGING SECURITY ====================

class SensitiveDataFilter(logging.Filter):
    """
    Advanced logging filter to mask sensitive data in log messages.
    Prevents accidental exposure of credentials, tokens, PII in logs.
    """
    
    PATTERNS = [
        # Credentials
        (r'password["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'password=***MASKED***'),
        (r'token["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'token=***MASKED***'),
        (r'secret["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'secret=***MASKED***'),
        (r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'api_key=***MASKED***'),
        (r'auth["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'auth=***MASKED***'),
        (r'bearer\s+[a-zA-Z0-9._-]+', 'Bearer ***MASKED***'),
        
        # Credit cards
        (r'\b(?:\d{4}[- ]?){3}\d{4}\b', '****-****-****-****'),
        
        # Email masking (partial)
        (r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'\1[...]@\2'),
        
        # Phone numbers
        (r'\b0\d{9,10}\b', '***PHONE***'),
        
        # Vietnamese ID
        (r'\b\d{9,12}\b', '***ID***'),
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Apply all masking patterns to log message."""
        if record.msg:
            msg = str(record.msg)
            for pattern, replacement in self.PATTERNS:
                msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
            record.msg = msg
        return True


class SecurityAuditLogger:
    """
    Centralized security audit logging for tracking security-related events.
    """
    
    def __init__(self, logger_name: str = 'security.audit'):
        self.logger = logging.getLogger(logger_name)
    
    def log_login_attempt(self, email: str, success: bool, ip: str, user_agent: str = ''):
        """Log login attempts for security monitoring."""
        status = 'SUCCESS' if success else 'FAILED'
        self.logger.info(
            f"LOGIN_{status}: email={email[:3]}***@***.com, ip={ip}, ua={user_agent[:50]}"
        )
    
    def log_password_change(self, user_id: str, ip: str):
        """Log password changes."""
        self.logger.info(f"PASSWORD_CHANGE: user={user_id}, ip={ip}")
    
    def log_suspicious_activity(self, activity: str, details: Dict[str, Any]):
        """Log suspicious activity for security review."""
        self.logger.warning(f"SUSPICIOUS: {activity}, details={details}")
    
    def log_rate_limit_exceeded(self, endpoint: str, ip: str, user_id: str = None):
        """Log rate limit violations."""
        self.logger.warning(f"RATE_LIMIT: endpoint={endpoint}, ip={ip}, user={user_id}")


# ==================== INPUT VALIDATION & SANITIZATION ====================

class InputValidator:
    """
    Comprehensive input validation and sanitization utilities.
    """
    
    # Dangerous patterns for XSS/SQL injection
    XSS_PATTERNS = [
        r'<script[^>]*>',
        r'javascript:',
        r'on\w+\s*=',
        r'<iframe',
        r'<object',
        r'<embed',
        r'<form',
        r'expression\s*\(',
        r'eval\s*\(',
    ]
    
    SQL_PATTERNS = [
        r'\bOR\b.*\b=\b',
        r'\bAND\b.*\b=\b',
        r'\bUNION\b.*\bSELECT\b',
        r'\bDROP\b.*\bTABLE\b',
        r'\bDELETE\b.*\bFROM\b',
        r'\bINSERT\b.*\bINTO\b',
        r'--\s*$',
        r'/\*.*\*/',
    ]
    
    @classmethod
    def detect_xss(cls, input_str: str) -> bool:
        """Detect potential XSS attack patterns in input."""
        if not input_str:
            return False
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, input_str, re.IGNORECASE):
                return True
        return False
    
    @classmethod
    def detect_sql_injection(cls, input_str: str) -> bool:
        """Detect potential SQL injection patterns in input."""
        if not input_str:
            return False
        for pattern in cls.SQL_PATTERNS:
            if re.search(pattern, input_str, re.IGNORECASE):
                return True
        return False
    
    @classmethod
    def sanitize_html(cls, input_str: str) -> str:
        """Remove HTML tags and dangerous content from input."""
        if not input_str:
            return ''
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', input_str)
        # Escape special characters
        clean = clean.replace('&', '&amp;')
        clean = clean.replace('<', '&lt;')
        clean = clean.replace('>', '&gt;')
        clean = clean.replace('"', '&quot;')
        clean = clean.replace("'", '&#x27;')
        return clean
    
    @classmethod
    def validate_phone(cls, phone: str) -> Tuple[bool, str]:
        """Validate Vietnamese phone number format."""
        if not phone:
            return False, "Số điện thoại không được để trống"
        
        # Remove spaces and dashes
        phone = re.sub(r'[\s\-]', '', phone)
        
        # Vietnamese phone patterns
        if re.match(r'^(0[3-9])\d{8}$', phone):
            return True, phone
        if re.match(r'^(\+84)[3-9]\d{8}$', phone):
            return True, '0' + phone[3:]
        
        return False, "Số điện thoại không hợp lệ"
    
    @classmethod
    def validate_email(cls, email: str) -> Tuple[bool, str]:
        """Validate email format with strict rules."""
        if not email:
            return False, "Email không được để trống"
        
        email = email.lower().strip()
        pattern = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        
        if len(email) > 254:
            return False, "Email quá dài"
        
        if not re.match(pattern, email):
            return False, "Email không hợp lệ"
        
        return True, email


# ==================== PASSWORD SECURITY ====================

class PasswordValidator:
    """
    Advanced password strength validation.
    """
    
    WEAK_PASSWORDS = [
        'password', '123456', 'qwerty', 'abc123', 'admin',
        'letmein', 'welcome', 'monkey', 'dragon', 'master',
        'password1', '123456789', '12345678', '1234567890',
    ]
    
    @classmethod
    def validate_strength(cls, password: str) -> Tuple[bool, List[str], int]:
        """
        Validate password strength.
        Returns: (is_valid, error_messages, strength_score)
        Strength score: 0-5 (weak to very strong)
        """
        errors = []
        score = 0
        
        if len(password) < 8:
            errors.append("Mật khẩu phải có ít nhất 8 ký tự")
        elif len(password) >= 12:
            score += 1
        elif len(password) >= 16:
            score += 2
        
        if not re.search(r'[a-z]', password):
            errors.append("Mật khẩu phải có ít nhất 1 chữ thường")
        else:
            score += 1
        
        if not re.search(r'[A-Z]', password):
            errors.append("Mật khẩu phải có ít nhất 1 chữ hoa")
        else:
            score += 1
        
        if not re.search(r'\d', password):
            errors.append("Mật khẩu phải có ít nhất 1 số")
        else:
            score += 1
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Mật khẩu nên có ít nhất 1 ký tự đặc biệt")
        else:
            score += 1
        
        if password.lower() in cls.WEAK_PASSWORDS:
            errors.append("Mật khẩu quá phổ biến")
            score = 0
        
        return len(errors) == 0, errors, min(score, 5)


# ==================== TOKEN & SIGNATURE SECURITY ====================

class TokenManager:
    """
    Secure token generation and verification utilities.
    """
    
    @staticmethod
    def generate_token(length: int = 32) -> str:
        """Generate cryptographically secure random token."""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def generate_otp(length: int = 6) -> str:
        """Generate numeric OTP code."""
        return ''.join(secrets.choice(string.digits) for _ in range(length))
    
    @staticmethod
    def generate_api_key() -> str:
        """Generate API key with prefix."""
        return f"owls_{secrets.token_hex(24)}"


class SignatureVerifier:
    """
    HMAC signature verification for webhooks and API requests.
    """
    
    @staticmethod
    def verify_hmac_sha256(payload: bytes, signature: str, secret: str) -> bool:
        """Verify HMAC-SHA256 signature."""
        expected = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    
    @staticmethod
    def verify_hmac_sha512(payload: bytes, signature: str, secret: str) -> bool:
        """Verify HMAC-SHA512 signature."""
        expected = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    
    @staticmethod
    def create_signature(data: str, secret: str, algorithm: str = 'sha256') -> str:
        """Create HMAC signature for data."""
        hash_func = getattr(hashlib, algorithm, hashlib.sha256)
        return hmac.new(
            secret.encode('utf-8'),
            data.encode('utf-8'),
            hash_func
        ).hexdigest()


# ==================== IP SECURITY ====================

class IPValidator:
    """
    IP address validation and security utilities.
    """
    
    # Known VPN/Proxy IP ranges (sample - would need updating regularly)
    SUSPICIOUS_RANGES = []
    
    @staticmethod
    def get_client_ip(request: HttpRequest) -> str:
        """Extract real client IP from request, handling proxies."""
        # Check for forwarded headers (in order of reliability)
        headers = [
            'HTTP_X_REAL_IP',
            'HTTP_X_FORWARDED_FOR',
            'HTTP_CF_CONNECTING_IP',  # Cloudflare
            'REMOTE_ADDR',
        ]
        
        for header in headers:
            ip = request.META.get(header)
            if ip:
                # X-Forwarded-For can contain multiple IPs
                if ',' in ip:
                    ip = ip.split(',')[0].strip()
                return ip
        
        return '127.0.0.1'
    
    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """Check if IP address is valid."""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def is_private_ip(ip: str) -> bool:
        """Check if IP is in private range (local network)."""
        try:
            return ipaddress.ip_address(ip).is_private
        except ValueError:
            return False
    
    @classmethod
    def is_suspicious_ip(cls, ip: str) -> bool:
        """Check if IP is in suspicious range."""
        try:
            ip_obj = ipaddress.ip_address(ip)
            for range_str in cls.SUSPICIOUS_RANGES:
                if ip_obj in ipaddress.ip_network(range_str, strict=False):
                    return True
        except ValueError:
            pass
        return False


# ==================== RATE LIMITING HELPERS ====================

class RateLimiter:
    """
    Advanced rate limiting utilities using Redis/cache.
    """
    
    @staticmethod
    def check_rate_limit(key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Check if rate limit is exceeded.
        Returns: (is_allowed, remaining_requests)
        """
        cache_key = f"rate_limit:{key}"
        current = cache.get(cache_key, 0)
        
        if current >= limit:
            return False, 0
        
        # Increment counter
        if current == 0:
            cache.set(cache_key, 1, window_seconds)
        else:
            cache.incr(cache_key)
        
        return True, limit - current - 1
    
    @staticmethod
    def get_remaining_time(key: str) -> int:
        """Get remaining time until rate limit resets (in seconds)."""
        cache_key = f"rate_limit:{key}"
        ttl = cache.ttl(cache_key)
        return max(0, ttl) if ttl else 0
    
    @staticmethod
    def reset_rate_limit(key: str):
        """Reset rate limit for a key."""
        cache.delete(f"rate_limit:{key}")


# ==================== SECURITY MIDDLEWARE HELPERS ====================

def add_security_headers(response) -> None:
    """Add security headers to HTTP response."""
    # Prevent clickjacking
    response['X-Frame-Options'] = 'DENY'
    
    # Prevent XSS
    response['X-XSS-Protection'] = '1; mode=block'
    
    # Prevent MIME type sniffing
    response['X-Content-Type-Options'] = 'nosniff'
    
    # Referrer policy
    response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Content Security Policy (basic)
    if not settings.DEBUG:
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com; "
        )
    
    # Permissions Policy
    response['Permissions-Policy'] = (
        'geolocation=(), '
        'microphone=(), '
        'camera=()'
    )


# ==================== DECORATORS ====================

def require_https(view_func):
    """Decorator to require HTTPS for a view."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not settings.DEBUG and not request.is_secure():
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("HTTPS required")
        return view_func(request, *args, **kwargs)
    return wrapper


def log_security_event(event_type: str):
    """Decorator to log security events for views."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            logger = SecurityAuditLogger()
            ip = IPValidator.get_client_ip(request)
            
            try:
                response = view_func(request, *args, **kwargs)
                logger.logger.info(
                    f"SECURITY_EVENT: type={event_type}, ip={ip}, "
                    f"user={getattr(request, 'user', 'anonymous')}, "
                    f"status={'success' if response.status_code < 400 else 'failed'}"
                )
                return response
            except Exception as e:
                logger.log_suspicious_activity(
                    f"Exception in {event_type}",
                    {'ip': ip, 'error': str(e)}
                )
                raise
        return wrapper
    return decorator


# ==================== EXPORTS ====================

__all__ = [
    'SensitiveDataFilter',
    'SecurityAuditLogger',
    'InputValidator',
    'PasswordValidator',
    'TokenManager',
    'SignatureVerifier',
    'IPValidator',
    'RateLimiter',
    'add_security_headers',
    'require_https',
    'log_security_event',
]
