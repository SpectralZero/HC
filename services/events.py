"""
CareBox Events Service

Handles event logging to Google Sheets for:
- SCAN: Bag QR code scanned
- SERIAL_OK: Serial verification successful
- SERIAL_FAIL: Serial verification failed
- ORDER: New order submitted

Also manages IP-based lockout for failed serial attempts.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class LockoutInfo:
    """Tracks lockout state for an IP."""
    fail_count: int = 0
    lockout_until: Optional[datetime] = None
    last_fail: Optional[datetime] = None


class EventsService:
    """Service for event logging and rate limiting."""
    
    # Event types
    EVENT_SCAN = "SCAN"
    EVENT_SERIAL_OK = "SERIAL_OK"
    EVENT_SERIAL_FAIL = "SERIAL_FAIL"
    EVENT_ORDER = "ORDER"
    
    # Default lockout configuration (can be overridden)
    DEFAULT_MAX_FAILS = 5
    DEFAULT_LOCKOUT_MINUTES = 15
    DEFAULT_FAIL_WINDOW_MINUTES = 30
    
    def __init__(
        self,
        max_fails: int = DEFAULT_MAX_FAILS,
        lockout_minutes: int = DEFAULT_LOCKOUT_MINUTES,
        fail_window_minutes: int = DEFAULT_FAIL_WINDOW_MINUTES
    ):
        """Initialize events service."""
        self._sheets_client = None  # Lazy initialized
        self._lockouts: Dict[str, LockoutInfo] = defaultdict(LockoutInfo)
        self._lock = Lock()
        self.max_fails = max_fails
        self.lockout_minutes = lockout_minutes
        self.fail_window_minutes = fail_window_minutes
    
    def _get_sheets_client(self):
        """Lazy load sheets client."""
        if self._sheets_client is None:
            try:
                from config import get_config
                from services.sheets_client import SheetsClient
                config = get_config()
                creds_path = config.get_google_credentials_path()
                self._sheets_client = SheetsClient(creds_path)
            except Exception as e:
                logger.warning(f"Could not initialize sheets client: {e}")
                return None
        return self._sheets_client
    
    def _get_events_worksheet(self):
        """Get the EVENTS worksheet."""
        client = self._get_sheets_client()
        if not client:
            return None
        try:
            from config import get_config
            config = get_config()
            return client.get_worksheet(config.SHEETS_DOC_NAME, config.SHEET_TAB_EVENTS)
        except Exception as e:
            logger.warning(f"Could not get EVENTS worksheet: {e}")
            return None
    
    def log_event(
        self,
        event_type: str,
        bag_id: Optional[str] = None,
        box_type: Optional[str] = None,
        ip_hash: Optional[str] = None,
        user_agent: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log an event to the EVENTS sheet.
        
        Args:
            event_type: Type of event (SCAN, SERIAL_OK, SERIAL_FAIL, ORDER)
            bag_id: Related bag ID if applicable
            box_type: Box type if applicable
            ip_hash: Hashed client IP for privacy
            user_agent: Truncated user agent string
            extra_data: Additional event data
            
        Returns:
            True if logged successfully, False otherwise
        """
        try:
            worksheet = self._get_events_worksheet()
            if not worksheet:
                logger.debug("Events worksheet not available, skipping log")
                return False
            
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            row = [
                timestamp,
                event_type,
                bag_id or "",
                box_type or "",
                ip_hash or "",
                user_agent or "",
                str(extra_data) if extra_data else ""
            ]
            
            worksheet.append_row(row, value_input_option="USER_ENTERED")
            logger.debug(f"Logged event: {event_type}")
            return True
        except Exception as e:
            logger.warning(f"Failed to log event: {e}")
            return False
    
    def log_scan(
        self,
        bag_id: str,
        box_type: str,
        ip_hash: str,
        user_agent: str
    ) -> bool:
        """Log a bag scan event."""
        return self.log_event(
            event_type=self.EVENT_SCAN,
            bag_id=bag_id,
            box_type=box_type,
            ip_hash=ip_hash,
            user_agent=user_agent
        )
    
    def log_serial_attempt(
        self,
        bag_id: str,
        ip_hash: str,
        success: bool,
        user_agent: str = ""
    ) -> bool:
        """
        Log a serial verification attempt and update lockout state.
        
        Args:
            bag_id: The bag being verified
            ip_hash: Hashed IP for rate limiting
            success: Whether verification succeeded
            user_agent: Client user agent
            
        Returns:
            True if logged successfully
        """
        event_type = self.EVENT_SERIAL_OK if success else self.EVENT_SERIAL_FAIL
        
        # Update lockout tracking
        if not success:
            self._record_fail(ip_hash)
        else:
            self._clear_fails(ip_hash)
        
        return self.log_event(
            event_type=event_type,
            bag_id=bag_id,
            ip_hash=ip_hash,
            user_agent=user_agent
        )
    
    def log_order(
        self,
        box_type: str,
        bag_id: Optional[str],
        ip_hash: str,
        user_agent: str
    ) -> bool:
        """Log an order submission event."""
        return self.log_event(
            event_type=self.EVENT_ORDER,
            bag_id=bag_id,
            box_type=box_type,
            ip_hash=ip_hash,
            user_agent=user_agent
        )
    
    def is_locked_out(self, ip_hash: str) -> bool:
        """
        Check if an IP is currently locked out.
        
        Args:
            ip_hash: Hashed IP to check
            
        Returns:
            True if locked out, False otherwise
        """
        with self._lock:
            info = self._lockouts.get(ip_hash)
            if not info:
                return False
            
            if info.lockout_until and datetime.utcnow() < info.lockout_until:
                return True
            
            # Lockout expired
            if info.lockout_until:
                info.lockout_until = None
                info.fail_count = 0
            
            return False
    
    def get_lockout_remaining(self, ip_hash: str) -> int:
        """
        Get remaining lockout time in seconds.
        
        Args:
            ip_hash: Hashed IP to check
            
        Returns:
            Remaining seconds, or 0 if not locked out
        """
        with self._lock:
            info = self._lockouts.get(ip_hash)
            if not info or not info.lockout_until:
                return 0
            
            remaining = (info.lockout_until - datetime.utcnow()).total_seconds()
            return max(0, int(remaining))
    
    def get_fail_count(self, ip_hash: str) -> int:
        """Get current fail count for an IP."""
        with self._lock:
            info = self._lockouts.get(ip_hash)
            if not info:
                return 0
            
            # Check if fails have expired
            if info.last_fail:
                window = timedelta(minutes=self.fail_window_minutes)
                if datetime.utcnow() - info.last_fail > window:
                    info.fail_count = 0
                    info.last_fail = None
            
            return info.fail_count
    
    def get_remaining_attempts(self, ip_hash: str) -> int:
        """Get remaining verification attempts before lockout."""
        return max(0, self.max_fails - self.get_fail_count(ip_hash))
    
    def _record_fail(self, ip_hash: str) -> None:
        """Record a failed attempt and potentially trigger lockout."""
        with self._lock:
            info = self._lockouts[ip_hash]
            now = datetime.utcnow()
            
            # Check if previous fails have expired
            if info.last_fail:
                window = timedelta(minutes=self.fail_window_minutes)
                if now - info.last_fail > window:
                    info.fail_count = 0
            
            info.fail_count += 1
            info.last_fail = now
            
            # Trigger lockout if threshold reached
            if info.fail_count >= self.max_fails:
                info.lockout_until = now + timedelta(minutes=self.lockout_minutes)
    
    def _clear_fails(self, ip_hash: str) -> None:
        """Clear fail count after successful verification."""
        with self._lock:
            if ip_hash in self._lockouts:
                self._lockouts[ip_hash] = LockoutInfo()


# Singleton instance
_events_service: Optional[EventsService] = None


def get_events_service() -> EventsService:
    """Get or create events service singleton."""
    global _events_service
    if _events_service is None:
        try:
            from config import get_config
            config = get_config()
            _events_service = EventsService(
                max_fails=config.MAX_SERIAL_ATTEMPTS,
                lockout_minutes=config.LOCKOUT_DURATION_MINUTES
            )
        except Exception:
            _events_service = EventsService()
    return _events_service
