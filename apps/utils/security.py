"""
Security utilities for the OWLS e-commerce platform.
Contains functions for masking sensitive data in logs and responses.
"""

import re
from typing import Any, Dict, List, Union


# Patterns to detect sensitive data
SENSITIVE_PATTERNS = {
    'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    'phone': r'(?:\+84|84|0)\d{9,10}',
    'card_number': r'\b\d{13,19}\b',
    'cvv': r'\b\d{3,4}\b',
}

# Keys that should be masked in dictionaries
SENSITIVE_KEYS = [
    'password', 'passwd', 'pwd', 'secret', 'token', 'access_token',
    'refresh_token', 'api_key', 'apikey', 'auth', 'authorization',
    'credential', 'private_key', 'secret_key', 'access_key',
    'card_number', 'cvv', 'cvc', 'expiry', 'bank_account',
    'signature', 'hash', 'vnp_SecureHash', 'stripe_signature',
]


def mask_string(value: str, visible_chars: int = 4, mask_char: str = '*') -> str:
    """
    Mask a string, keeping only first and last few characters visible.
    
    Args:
        value: String to mask
        visible_chars: Number of characters to show at start and end
        mask_char: Character to use for masking
    
    Returns:
        Masked string
    
    Example:
        >>> mask_string("secret_key_12345")
        "secr********2345"
    """
    if not value or len(value) <= visible_chars * 2:
        return mask_char * len(value) if value else ''
    
    return value[:visible_chars] + mask_char * (len(value) - visible_chars * 2) + value[-visible_chars:]


def mask_email(email: str) -> str:
    """
    Mask an email address.
    
    Example:
        >>> mask_email("user@example.com")
        "u***@e***.com"
    """
    if not email or '@' not in email:
        return email
    
    local, domain = email.rsplit('@', 1)
    domain_parts = domain.rsplit('.', 1)
    
    masked_local = local[0] + '***' if local else '***'
    masked_domain = domain_parts[0][0] + '***' if domain_parts[0] else '***'
    
    return f"{masked_local}@{masked_domain}.{domain_parts[-1]}"


def mask_phone(phone: str) -> str:
    """
    Mask a phone number, keeping first 3 and last 2 digits.
    
    Example:
        >>> mask_phone("0912345678")
        "091*****78"
    """
    if not phone:
        return phone
    
    # Remove non-digits for processing
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) < 6:
        return '*' * len(digits)
    
    return digits[:3] + '*' * (len(digits) - 5) + digits[-2:]


def mask_card_number(card: str) -> str:
    """
    Mask a card number, showing only last 4 digits.
    
    Example:
        >>> mask_card_number("4111111111111111")
        "************1111"
    """
    if not card:
        return card
    
    digits = re.sub(r'\D', '', card)
    
    if len(digits) < 4:
        return '*' * len(digits)
    
    return '*' * (len(digits) - 4) + digits[-4:]


def mask_dict(data: Dict[str, Any], depth: int = 0, max_depth: int = 10) -> Dict[str, Any]:
    """
    Recursively mask sensitive values in a dictionary.
    
    Args:
        data: Dictionary to mask
        depth: Current recursion depth
        max_depth: Maximum recursion depth
    
    Returns:
        Dictionary with sensitive values masked
    """
    if depth > max_depth:
        return data
    
    masked = {}
    for key, value in data.items():
        key_lower = key.lower()
        
        # Check if key indicates sensitive data
        is_sensitive = any(
            sensitive in key_lower 
            for sensitive in SENSITIVE_KEYS
        )
        
        if is_sensitive:
            if isinstance(value, str):
                masked[key] = mask_string(value)
            else:
                masked[key] = '[REDACTED]'
        elif isinstance(value, dict):
            masked[key] = mask_dict(value, depth + 1, max_depth)
        elif isinstance(value, list):
            masked[key] = [
                mask_dict(item, depth + 1, max_depth) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, str):
            # Auto-detect and mask emails and phones
            if '@' in value and re.match(SENSITIVE_PATTERNS['email'], value):
                masked[key] = mask_email(value)
            elif re.match(SENSITIVE_PATTERNS['phone'], value):
                masked[key] = mask_phone(value)
            else:
                masked[key] = value
        else:
            masked[key] = value
    
    return masked


def mask_for_logging(data: Union[Dict, str, Any]) -> Union[Dict, str, Any]:
    """
    Prepare data for safe logging by masking sensitive information.
    
    Args:
        data: Data to prepare for logging
    
    Returns:
        Masked data safe for logging
    """
    if isinstance(data, dict):
        return mask_dict(data)
    elif isinstance(data, str):
        # Try to detect and mask common patterns
        result = data
        
        # Mask emails
        for match in re.finditer(SENSITIVE_PATTERNS['email'], result):
            result = result.replace(match.group(), mask_email(match.group()))
        
        # Mask phone numbers
        for match in re.finditer(SENSITIVE_PATTERNS['phone'], result):
            result = result.replace(match.group(), mask_phone(match.group()))
        
        return result
    else:
        return data


class SensitiveDataFilter:
    """
    Logging filter that masks sensitive data in log records.
    
    Usage in Django settings:
        'filters': {
            'mask_sensitive': {
                '()': 'apps.utils.security.SensitiveDataFilter',
            },
        },
    """
    
    def filter(self, record):
        """Filter log record and mask sensitive data."""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = mask_for_logging(record.msg)
        
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, dict):
                record.args = mask_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_for_logging(arg) if isinstance(arg, (str, dict)) else arg
                    for arg in record.args
                )
        
        return True


def get_safe_provider_data(provider_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a copy of provider data with sensitive fields masked.
    Useful for logging payment provider responses.
    
    Args:
        provider_data: Raw provider data
    
    Returns:
        Masked provider data safe for logging
    """
    return mask_dict(provider_data.copy())
