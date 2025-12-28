"""
Security middleware for OWLS E-Commerce Platform.

This middleware adds security headers, logs suspicious activity,
and provides additional security checks for all requests.
"""

import logging
from django.conf import settings
from django.http import HttpResponseForbidden
from apps.utils.security import (
    add_security_headers,
    IPValidator,
    InputValidator,
    SecurityAuditLogger,
)

logger = logging.getLogger('security')


class SecurityHeadersMiddleware:
    """
    Middleware to add security headers to all responses.
    
    Headers added:
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - X-Content-Type-Options: nosniff
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy (production only)
    - Permissions-Policy
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        add_security_headers(response)
        return response


class RequestLoggingMiddleware:
    """
    Middleware to log all API requests for security audit.
    Logs: IP, path, method, user, response status.
    """
    
    SENSITIVE_PATHS = [
        '/api/auth/login/',
        '/api/auth/register/',
        '/api/auth/password/',
        '/api/admin/',
        '/api/checkout/',
        '/api/payments/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.audit = SecurityAuditLogger()
    
    def __call__(self, request):
        # Get client info
        ip = IPValidator.get_client_ip(request)
        user_id = getattr(request.user, 'id', None) if hasattr(request, 'user') else None
        
        response = self.get_response(request)
        
        # Log sensitive endpoint access
        if any(request.path.startswith(p) for p in self.SENSITIVE_PATHS):
            logger.info(
                f"API_ACCESS: path={request.path}, method={request.method}, "
                f"ip={ip}, user={user_id}, status={response.status_code}"
            )
        
        return response


class SuspiciousActivityMiddleware:
    """
    Middleware to detect and block suspicious requests.
    
    Detects:
    - XSS attempts in query parameters
    - SQL injection attempts
    - Unusual request patterns
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.audit = SecurityAuditLogger()
    
    def __call__(self, request):
        ip = IPValidator.get_client_ip(request)
        
        # Check for XSS in query parameters
        if request.GET:
            for key, value in request.GET.items():
                if InputValidator.detect_xss(value):
                    self.audit.log_suspicious_activity("XSS attempt in query params", {
                        'ip': ip, 'param': key, 'path': request.path
                    })
                    if not settings.DEBUG:
                        return HttpResponseForbidden("Request blocked for security reasons")
        
        # Check for SQL injection in query parameters
        if request.GET:
            for key, value in request.GET.items():
                if InputValidator.detect_sql_injection(value):
                    self.audit.log_suspicious_activity("SQL injection attempt", {
                        'ip': ip, 'param': key, 'path': request.path
                    })
                    if not settings.DEBUG:
                        return HttpResponseForbidden("Request blocked for security reasons")
        
        return self.get_response(request)


class PrivateIPBlockMiddleware:
    """
    Middleware to block access from private IPs in production.
    Useful for blocking internal network access to public APIs.
    
    Note: Only enable if you have a proper proxy setup.
    """
    
    PROTECTED_PATHS = [
        '/api/admin/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip in DEBUG mode
        if settings.DEBUG:
            return self.get_response(request)
        
        # Only check protected paths
        if not any(request.path.startswith(p) for p in self.PROTECTED_PATHS):
            return self.get_response(request)
        
        ip = IPValidator.get_client_ip(request)
        
        # Block suspicious IPs (implement your logic)
        if IPValidator.is_suspicious_ip(ip):
            logger.warning(f"Blocked suspicious IP: {ip} on {request.path}")
            return HttpResponseForbidden("Access denied")
        
        return self.get_response(request)
