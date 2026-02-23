"""
CareBox Test Suite

Basic tests for validation, security, and services.
Run with: pytest tests/ -v
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSecurityValidation:
    """Tests for security validation functions."""
    
    def test_sanitize_text_removes_dangerous_chars(self):
        from services.security import sanitize_text
        
        assert sanitize_text("<script>alert('xss')</script>") == "scriptalert(xss)/script"
        assert sanitize_text("normal text") == "normal text"
        assert sanitize_text(None) == ""
    
    def test_sanitize_text_limits_length(self):
        from services.security import sanitize_text
        
        long_text = "a" * 100
        result = sanitize_text(long_text, max_length=10)
        assert len(result) == 10
    
    def test_validate_phone_accepts_valid(self):
        from services.security import validate_phone
        
        assert validate_phone("+962791234567") is True
        assert validate_phone("0791234567") is True
        assert validate_phone("+1-555-123-4567") is True
    
    def test_validate_phone_rejects_invalid(self):
        from services.security import validate_phone
        
        assert validate_phone("abc") is False
        assert validate_phone("123") is False
        assert validate_phone("") is False
    
    def test_validate_bag_id_format(self):
        from services.security import validate_bag_id
        
        assert validate_bag_id("CBX-0001") is True
        assert validate_bag_id("CBX-9999") is True
        assert validate_bag_id("invalid") is False
        assert validate_bag_id("CBX0001") is False
    
    def test_validate_box_type(self):
        from services.security import validate_box_type
        
        assert validate_box_type("travel") is True
        assert validate_box_type("recovery") is True
        assert validate_box_type("mom") is True
        assert validate_box_type("pilgrim") is True
        assert validate_box_type("invalid") is False
    
    def test_validate_serial_last4(self):
        from services.security import validate_serial_last4
        
        assert validate_serial_last4("1234") is True
        assert validate_serial_last4("0000") is True
        assert validate_serial_last4("123") is False
        assert validate_serial_last4("12345") is False
        assert validate_serial_last4("abcd") is False


class TestIPHashing:
    """Tests for IP hashing functionality."""
    
    def test_hash_ip_produces_consistent_output(self):
        from services.security import hash_ip
        
        ip = "192.168.1.1"
        salt = "test_salt"
        
        hash1 = hash_ip(ip, salt)
        hash2 = hash_ip(ip, salt)
        
        assert hash1 == hash2
        assert len(hash1) == 16
    
    def test_hash_ip_different_salt_different_output(self):
        from services.security import hash_ip
        
        ip = "192.168.1.1"
        
        hash1 = hash_ip(ip, "salt1")
        hash2 = hash_ip(ip, "salt2")
        
        assert hash1 != hash2


class TestOrdersService:
    """Tests for orders service validation."""
    
    def test_validate_order_requires_name(self):
        from services.orders import OrdersService
        
        service = OrdersService()
        is_valid, error = service.validate_order(
            name="",
            phone="+962795246652",
            box_type="travel"
        )
        
        assert is_valid is False
        assert error is not None
    
    def test_validate_order_requires_valid_phone(self):
        from services.orders import OrdersService
        
        service = OrdersService()
        is_valid, error = service.validate_order(
            name="Test User",
            phone="invalid",
            box_type="travel"
        )
        
        assert is_valid is False
        assert error is not None
    
    def test_validate_order_requires_valid_box_type(self):
        from services.orders import OrdersService
        
        service = OrdersService()
        is_valid, error = service.validate_order(
            name="Test User",
            phone="+962795246652",
            box_type="invalid_type"
        )
        
        assert is_valid is False
        assert error is not None
    
    def test_validate_order_accepts_valid_data(self):
        from services.orders import OrdersService
        
        service = OrdersService()
        is_valid, error = service.validate_order(
            name="Test User",
            phone="91234567",
            box_type="travel"
        )
        
        assert is_valid is True
        assert error is None
    
    def test_generate_whatsapp_url(self):
        from services.orders import OrdersService
        
        service = OrdersService()
        url = service.generate_whatsapp_url(
            business_whatsapp="962795246652",
            name="Test",
            phone="+962795246652",
            box_type="travel",
            lang="en"
        )
        
        assert url.startswith("https://wa.me/962795246652")
        assert "text=" in url


class TestEventsService:
    """Tests for events service lockout functionality."""
    
    def test_lockout_after_max_failures(self):
        from services.events import EventsService
        
        service = EventsService(max_fails=3, lockout_minutes=15)
        ip_hash = "test_ip_hash_123"
        
        # Initially not locked out
        assert service.is_locked_out(ip_hash) is False
        
        # Record failures
        for _ in range(3):
            service._record_fail(ip_hash)
        
        # Now should be locked out
        assert service.is_locked_out(ip_hash) is True
    
    def test_remaining_attempts_decreases(self):
        from services.events import EventsService
        
        service = EventsService(max_fails=5, lockout_minutes=15)
        ip_hash = "test_ip_hash_456"
        
        assert service.get_remaining_attempts(ip_hash) == 5
        
        service._record_fail(ip_hash)
        assert service.get_remaining_attempts(ip_hash) == 4


class TestAppFactory:
    """Tests for Flask app creation."""
    
    def test_app_creates_successfully(self):
        from app import create_app
        
        app = create_app()
        assert app is not None
    
    def test_health_endpoint(self):
        from app import create_app
        
        app = create_app()
        with app.test_client() as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert b"healthy" in response.data
