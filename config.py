"""
CareBox Configuration Module

Loads configuration from environment variables with secure defaults.
Never hardcode secrets - all sensitive values come from .env or environment.
"""

import os
import base64
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # =========================================================================
    # FLASK CORE
    # =========================================================================
    SECRET_KEY: str = os.getenv("FLASK_SECRET", "")
    if not SECRET_KEY or SECRET_KEY == "CHANGE_ME_TO_A_RANDOM_64_CHAR_HEX_STRING":
        raise ValueError(
            "FLASK_SECRET must be set to a secure random value. "
            "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    ENV: str = os.getenv("FLASK_ENV", "production")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    BASE_URL: str = os.getenv("BASE_URL", "http://127.0.0.1:5000").rstrip("/")

    # =========================================================================
    # GOOGLE SHEETS DATABASE
    # =========================================================================
    SHEETS_DOC_NAME: str = os.getenv("SHEETS_DOC_NAME", "CareBoxDB")

    # Support both file-based and base64-encoded credentials
    _CREDS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "")
    _CREDS_BASE64: str = os.getenv("GOOGLE_CREDENTIALS_BASE64", "")

    @classmethod
    def get_google_credentials_path(cls) -> str:
        """
        Returns path to Google credentials JSON file.
        
        Supports two modes:
        1. File path (local development): GOOGLE_CREDENTIALS_FILE
        2. Base64 encoded (cloud deployment): GOOGLE_CREDENTIALS_BASE64
        
        For cloud deployment, decodes base64 and writes to temp file.
        """
        if cls._CREDS_FILE and Path(cls._CREDS_FILE).exists():
            return cls._CREDS_FILE

        if cls._CREDS_BASE64:
            # Decode base64 credentials and write to temp file
            try:
                creds_json = base64.b64decode(cls._CREDS_BASE64)
                temp_file = Path(tempfile.gettempdir()) / "gcp_creds.json"
                temp_file.write_bytes(creds_json)
                return str(temp_file)
            except Exception as e:
                raise ValueError(f"Failed to decode GOOGLE_CREDENTIALS_BASE64: {e}")

        raise ValueError(
            "Google credentials not configured. Set either "
            "GOOGLE_CREDENTIALS_FILE (path) or GOOGLE_CREDENTIALS_BASE64 (base64 encoded)."
        )

    # =========================================================================
    # BUSINESS CONFIGURATION
    # =========================================================================
    BUSINESS_WHATSAPP: str = os.getenv("BUSINESS_WHATSAPP", "9627XXXXXXXX")
    BUSINESS_NAME: str = os.getenv("BUSINESS_NAME", "CareBox")

    # =========================================================================
    # SECURITY FEATURES
    # =========================================================================
    ENABLE_SERIAL_CHECK: bool = os.getenv("ENABLE_SERIAL_CHECK", "true").lower() == "true"

    IP_HASH_SALT: str = os.getenv("IP_HASH_SALT", "")
    if not IP_HASH_SALT or IP_HASH_SALT == "CHANGE_ME_TO_A_RANDOM_32_CHAR_HEX_STRING":
        # Generate a random salt if not provided (not recommended for production)
        import secrets
        IP_HASH_SALT = secrets.token_hex(16)

    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    # Admin password check is done at runtime, not here

    MAX_SERIAL_ATTEMPTS: int = int(os.getenv("MAX_SERIAL_ATTEMPTS", "5"))
    LOCKOUT_DURATION_MINUTES: int = int(os.getenv("LOCKOUT_DURATION_MINUTES", "15"))

    # =========================================================================
    # PRODUCTION / HTTPS
    # =========================================================================
    FORCE_HTTPS: bool = os.getenv("FORCE_HTTPS", "false").lower() == "true"
    TRUSTED_PROXIES: list = os.getenv("TRUSTED_PROXIES", "X-Forwarded-For").split(",")

    # =========================================================================
    # SHEET TAB NAMES
    # =========================================================================
    SHEET_TAB_BAGS: str = "BAGS"
    SHEET_TAB_ORDERS: str = "ORDERS"
    SHEET_TAB_EVENTS: str = "EVENTS"


class DevelopmentConfig(Config):
    """Development-specific configuration with relaxed security for testing."""
    
    # Override the strict SECRET_KEY check for development
    SECRET_KEY: str = os.getenv("FLASK_SECRET", "dev-secret-key-not-for-production")
    DEBUG: bool = True
    ENV: str = "development"


class ProductionConfig(Config):
    """Production configuration with strict security."""
    
    DEBUG: bool = False
    ENV: str = "production"


def get_config():
    """Returns the appropriate config based on FLASK_ENV."""
    env = os.getenv("FLASK_ENV", "production")
    if env == "development":
        return DevelopmentConfig
    return ProductionConfig
