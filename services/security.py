"""
Security Service Module

Provides security utilities for:
- Input sanitization (XSS prevention)
- Phone number validation
- IP address hashing for privacy
- CSRF token generation and validation
- Rate limiting helpers
- Security headers
"""

import re
import hmac
import hashlib
import secrets
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict

from flask import request, session, abort, Response

logger = logging.getLogger(__name__)

# =============================================================================
# INPUT VALIDATION PATTERNS
# =============================================================================

# Phone number: 7-20 characters, digits, +, -, spaces allowed
PHONE_PATTERN = re.compile(r"^[0-9+\-\s]{7,20}$")

# Bag ID format: CBX-XXXX (4 digits)
BAG_ID_PATTERN = re.compile(r"^CBX-\d{4}$")

# Box type whitelist
VALID_BOX_TYPES = {"travel", "recovery", "mom", "pilgrim"}

# Characters to strip from text input (XSS prevention)
DANGEROUS_CHARS = re.compile(r"[<>\"'`;&|]")


# =============================================================================
# INPUT SANITIZATION
# =============================================================================

def sanitize_text(text: Optional[str], max_length: int = 80) -> str:
    """
    Sanitize text input by removing dangerous characters and limiting length.
    
    Args:
        text: Input text (can be None)
        max_length: Maximum allowed length
        
    Returns:
        Sanitized string
    """
    if not text:
        return ""
    
    # Strip whitespace
    text = str(text).strip()
    
    # Remove dangerous characters
    text = DANGEROUS_CHARS.sub("", text)
    
    # Limit length
    return text[:max_length]


def validate_phone(phone: str) -> bool:
    """
    Validate phone number format.
    
    Args:
        phone: Phone number string
        
    Returns:
        True if valid format
    """
    phone = sanitize_text(phone, 20)
    return bool(PHONE_PATTERN.match(phone))


def validate_bag_id(bag_id: str) -> bool:
    """
    Validate bag ID format (CBX-XXXX).
    
    Args:
        bag_id: Bag identifier
        
    Returns:
        True if valid format
    """
    return bool(BAG_ID_PATTERN.match(bag_id))


def validate_box_type(box_type: str) -> bool:
    """
    Validate box type against whitelist.
    
    Args:
        box_type: Box type string
        
    Returns:
        True if valid type
    """
    return box_type.lower() in VALID_BOX_TYPES


def validate_serial_last4(last4: str) -> bool:
    """
    Validate that serial last 4 is exactly 4 digits.
    
    Args:
        last4: Last 4 digits of serial
        
    Returns:
        True if valid
    """
    return bool(last4 and len(last4) == 4 and last4.isdigit())


# =============================================================================
# IP HASHING
# =============================================================================

def hash_ip(ip_address: str, salt: str) -> str:
    """
    Hash an IP address with salt for privacy-preserving logging.
    
    Uses HMAC-SHA256 to create a consistent but irreversible hash.
    
    Args:
        ip_address: Raw IP address
        salt: Secret salt for hashing
        
    Returns:
        Hexadecimal hash string (first 16 chars)
    """
    if not ip_address:
        return "unknown"
    
    # Use HMAC for secure hashing with salt
    h = hmac.new(
        salt.encode("utf-8"),
        ip_address.encode("utf-8"),
        hashlib.sha256
    )
    
    # Return first 16 chars (64 bits) - enough for identification, not reversible
    return h.hexdigest()[:16]


def get_client_ip() -> str:
    """
    Get the client's real IP address, accounting for proxies.
    
    Returns:
        IP address string
    """
    # Check common proxy headers
    if request.headers.get("X-Forwarded-For"):
        # Take the first IP (client), not later proxies
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    
    if request.headers.get("X-Real-IP"):
        return request.headers["X-Real-IP"]
    
    return request.remote_addr or "unknown"


# =============================================================================
# CSRF PROTECTION
# =============================================================================

def generate_csrf_token() -> str:
    """
    Generate a new CSRF token and store in session.
    
    Returns:
        CSRF token string
    """
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def validate_csrf_token(token: str) -> bool:
    """
    Validate a CSRF token against the session token.
    
    Args:
        token: Token from form submission
        
    Returns:
        True if valid
    """
    session_token = session.get("_csrf_token")
    if not session_token or not token:
        return False
    
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(session_token, token)


def csrf_protect(f):
    """
    Decorator to require valid CSRF token for POST requests.
    
    Usage:
        @app.route("/submit", methods=["POST"])
        @csrf_protect
        def submit():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "POST":
            token = request.form.get("_csrf_token")
            if not validate_csrf_token(token):
                logger.warning(f"CSRF validation failed from {get_client_ip()}")
                abort(403)
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# RATE LIMITING (In-Memory)
# =============================================================================

# Store: key -> (attempt_count, first_attempt_time, lockout_until)
_rate_limit_store: dict = defaultdict(lambda: {"attempts": 0, "first": None, "locked_until": None})


def check_rate_limit(
    key: str,
    max_attempts: int = 5,
    lockout_minutes: int = 15
) -> Tuple[bool, Optional[int]]:
    """
    Check if a key is rate limited.
    
    Args:
        key: Unique key (e.g., "serial_{ip_hash}_{bag_id}")
        max_attempts: Maximum attempts before lockout
        lockout_minutes: Duration of lockout
        
    Returns:
        Tuple of (is_allowed, seconds_until_unlock or None)
    """
    now = datetime.utcnow()
    entry = _rate_limit_store[key]
    
    # Check if currently locked out
    if entry["locked_until"] and now < entry["locked_until"]:
        remaining = (entry["locked_until"] - now).seconds
        return False, remaining
    
    # Reset if lockout has expired
    if entry["locked_until"] and now >= entry["locked_until"]:
        _rate_limit_store[key] = {"attempts": 0, "first": None, "locked_until": None}
    
    return True, None


def record_attempt(
    key: str,
    max_attempts: int = 5,
    lockout_minutes: int = 15
) -> Tuple[bool, Optional[int]]:
    """
    Record a failed attempt and check if lockout should be triggered.
    
    Args:
        key: Unique key
        max_attempts: Maximum attempts before lockout
        lockout_minutes: Duration of lockout
        
    Returns:
        Tuple of (is_now_locked, seconds_until_unlock or None)
    """
    now = datetime.utcnow()
    entry = _rate_limit_store[key]
    
    # Increment attempts
    entry["attempts"] += 1
    if entry["first"] is None:
        entry["first"] = now
    
    # Check if should lock out
    if entry["attempts"] >= max_attempts:
        entry["locked_until"] = now + timedelta(minutes=lockout_minutes)
        remaining = lockout_minutes * 60
        logger.warning(f"Rate limit lockout triggered for key: {key[:20]}...")
        return True, remaining
    
    return False, None


def clear_rate_limit(key: str) -> None:
    """
    Clear rate limit for a key (e.g., after successful verification).
    
    Args:
        key: Unique key to clear
    """
    if key in _rate_limit_store:
        del _rate_limit_store[key]


# =============================================================================
# HONEYPOT VALIDATION
# =============================================================================

def check_honeypot(form_data: dict, field_name: str = "_hp_email") -> bool:
    """
    Check if honeypot field was filled (indicating bot).
    
    Args:
        form_data: Form data dictionary
        field_name: Name of honeypot field
        
    Returns:
        True if honeypot is empty (legitimate user), False if filled (bot)
    """
    honeypot_value = form_data.get(field_name, "")
    if honeypot_value:
        logger.warning(f"Honeypot triggered from {get_client_ip()}")
        return False
    return True


# =============================================================================
# SECURITY HEADERS
# =============================================================================

def add_security_headers(response: Response, is_https: bool = False) -> Response:
    """
    Add security headers to a response.
    
    Args:
        response: Flask response object
        is_https: Whether the connection is HTTPS
        
    Returns:
        Modified response with security headers
    """
    # Content Security Policy - allow YouTube embeds
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "frame-src https://www.youtube.com https://youtube.com; "
        "connect-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self' https://wa.me; "
    )
    response.headers["Content-Security-Policy"] = csp
    
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    
    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Control referrer information
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # XSS Protection (legacy browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # HSTS for HTTPS connections
    if is_https:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Permissions Policy (formerly Feature-Policy)
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    
    return response


def get_truncated_user_agent(max_length: int = 200) -> str:
    """
    Get truncated user agent string for logging.
    
    Args:
        max_length: Maximum length
        
    Returns:
        Truncated user agent string
    """
    ua = request.headers.get("User-Agent", "unknown")
    return ua[:max_length]
