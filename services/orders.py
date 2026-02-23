"""
CareBox Orders Service

Handles order processing:
- Form validation
- Order storage to Google Sheets
- WhatsApp message generation with professional formatting
"""

import logging
import json
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, Tuple, List, Any

from services.security import sanitize_text, validate_phone, validate_box_type

logger = logging.getLogger(__name__)


class OrdersService:
    """Service for order operations."""
    
    # Valid box types
    VALID_BOX_TYPES = ["travel", "recovery", "mom", "pilgrim"]
    
    # Box type display names
    BOX_TYPE_NAMES = {
        "travel": {"en": "Travel Box", "ar": "صندوق السفر"},
        "recovery": {"en": "Recovery Box", "ar": "صندوق التعافي"},
        "mom": {"en": "Mom Box", "ar": "صندوق الأم"},
        "pilgrim": {"en": "Pilgrim Box", "ar": "صندوق الحج"},
    }
    
    # Box type emojis
    BOX_TYPE_EMOJI = {
        "travel": "✈️",
        "recovery": "💊",
        "mom": "👶",
        "pilgrim": "🕌",
    }
    
    def __init__(self):
        """Initialize orders service."""
        self._sheets_client = None  # Lazy initialized
    
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
    
    def _get_orders_worksheet(self):
        """Get the ORDERS worksheet."""
        client = self._get_sheets_client()
        if not client:
            return None
        try:
            from config import get_config
            config = get_config()
            return client.get_worksheet(config.SHEETS_DOC_NAME, config.SHEET_TAB_ORDERS)
        except Exception as e:
            logger.warning(f"Could not get ORDERS worksheet: {e}")
            return None
    
    def validate_order(
        self,
        name: str,
        phone: str,
        box_type: str,
        notes: str = "",
        lang: str = "en"
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate order form data.
        
        Args:
            name: Customer name
            phone: Customer phone
            box_type: Selected box type
            notes: Optional notes
            lang: Language for error messages
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate name
        if not name or len(name.strip()) < 2:
            error = "Please enter your name." if lang == "en" else "يرجى إدخال اسمك."
            return False, error
        
        if len(name) > 60:
            error = "Name is too long." if lang == "en" else "الاسم طويل جداً."
            return False, error
        
        # Validate phone
        if not phone or not validate_phone(phone):
            error = "Please enter a valid phone number." if lang == "en" else "يرجى إدخال رقم هاتف صحيح."
            return False, error
        
        # Validate box type
        if not box_type or not validate_box_type(box_type):
            error = "Please select a box type." if lang == "en" else "يرجى اختيار نوع الصندوق."
            return False, error
        
        # Notes length check
        if len(notes) > 200:
            error = "Notes are too long." if lang == "en" else "الملاحظات طويلة جداً."
            return False, error
        
        return True, None
    
    def save_order(
        self,
        name: str,
        phone: str,
        box_type: str,
        notes: str = "",
        bag_id: Optional[str] = None,
        ip_hash: Optional[str] = None
    ) -> bool:
        """
        Save order to Google Sheets.
        
        Args:
            name: Customer name
            phone: Customer phone
            box_type: Box type
            notes: Optional notes
            bag_id: Optional bag ID if ordering specific bag
            ip_hash: Hashed IP for tracking
            
        Returns:
            True if saved successfully
        """
        try:
            worksheet = self._get_orders_worksheet()
            if not worksheet:
                logger.warning("Orders worksheet not available, order not saved to sheets")
                return False
            
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            row = [
                timestamp,
                sanitize_text(name, 60),
                sanitize_text(phone, 20),
                box_type,
                bag_id or "",
                sanitize_text(notes, 200),
                "NEW",  # Status
                ip_hash or ""
            ]
            
            worksheet.append_row(row, value_input_option="USER_ENTERED")
            logger.info(f"Order saved: {box_type} for {phone[:4]}****")
            return True
        except Exception as e:
            logger.error(f"Failed to save order: {e}")
            return False
    
    def get_all_orders(self) -> List[Dict[str, Any]]:
        """Get all orders from Google Sheets for admin view."""
        orders = []
        try:
            worksheet = self._get_orders_worksheet()
            if not worksheet:
                return []
            
            rows = worksheet.get_all_values()
            for row in rows[1:]:  # Skip header
                if len(row) >= 7:
                    orders.append({
                        "timestamp": row[0][:16] if row[0] else "",
                        "name": row[1],
                        "phone": row[2],
                        "box_type": row[3],
                        "bag_id": row[4] if len(row) > 4 else "",
                        "notes": row[5] if len(row) > 5 else "",
                        "status": row[6] if len(row) > 6 else "NEW",
                    })
        except Exception as e:
            logger.warning(f"Failed to get orders: {e}")
        return orders
    
    def generate_whatsapp_url(
        self,
        business_whatsapp: str,
        name: str,
        phone: str,
        box_type: str,
        notes: str = "",
        lang: str = "en",
        product_name: str = "",
        bag_id: str = "",
        price: float = 0.0,
        bag_contents: Optional[List[Dict]] = None,
        selected_addons: Optional[List[Dict]] = None
    ) -> str:
        """
        Generate WhatsApp redirect URL with professionally formatted message.
        
        Args:
            business_whatsapp: Business WhatsApp number
            name: Customer name
            phone: Customer phone
            box_type: Box type
            notes: Optional notes
            lang: Language for message
            product_name: Product title
            bag_id: Product ID
            price: Base product price
            bag_contents: List of bag contents dicts
            selected_addons: List of selected add-on dicts with name/price
            
        Returns:
            WhatsApp URL with encoded message
        """
        # Clean phone number format
        clean_phone = ''.join(c for c in business_whatsapp if c.isdigit())
        
        emoji = self.BOX_TYPE_EMOJI.get(box_type, "📦")
        box_name = self.BOX_TYPE_NAMES.get(box_type, {}).get(lang, box_type.title())
        
        # Calculate totals
        base_price = price
        addons_total = 0.0
        if selected_addons:
            for addon in selected_addons:
                try:
                    addons_total += float(addon.get("price", 0))
                except (ValueError, TypeError):
                    pass
        grand_total = base_price + addons_total
        
        if lang == "ar":
            message = self._format_message_ar(
                emoji=emoji,
                box_name=box_name,
                product_name=product_name,
                bag_id=bag_id,
                name=name,
                phone=phone,
                notes=notes,
                base_price=base_price,
                addons_total=addons_total,
                grand_total=grand_total,
                bag_contents=bag_contents,
                selected_addons=selected_addons,
            )
        else:
            message = self._format_message_en(
                emoji=emoji,
                box_name=box_name,
                product_name=product_name,
                bag_id=bag_id,
                name=name,
                phone=phone,
                notes=notes,
                base_price=base_price,
                addons_total=addons_total,
                grand_total=grand_total,
                bag_contents=bag_contents,
                selected_addons=selected_addons,
            )
        
        encoded_message = urllib.parse.quote(message, safe='')
        return f"https://wa.me/{clean_phone}?text={encoded_message}"
    
    def _format_message_en(
        self, emoji, box_name, product_name, bag_id,
        name, phone, notes, base_price, addons_total, grand_total,
        bag_contents, selected_addons
    ) -> str:
        """Format professional English WhatsApp message."""
        divider = "━━━━━━━━━━━━━━━━━━━━"
        
        lines = [
            f"📦 *CareBox — New Order*",
            divider,
            "",
            f"{emoji} *{product_name or box_name}*",
        ]
        
        if bag_id:
            lines.append(f"🆔 Product ID: {bag_id}")
        
        lines.append("")
        
        # Bag contents section
        if bag_contents and len(bag_contents) > 0:
            lines.append("📋 *Bag Contents:*")
            for item in bag_contents:
                item_name = item.get("name", "")
                qty = item.get("qty", 1)
                lines.append(f"   • {item_name} × {qty}")
            lines.append("")
        
        # Add-ons section
        if selected_addons and len(selected_addons) > 0:
            lines.append("✨ *Selected Add-ons:*")
            for addon in selected_addons:
                addon_name = addon.get("name", "")
                addon_price = addon.get("price", 0)
                lines.append(f"   ✚ {addon_name}  (+{addon_price} JOD)")
            lines.append("")
        
        # Price breakdown
        lines.append(divider)
        lines.append("💰 *Price Summary:*")
        if base_price > 0:
            lines.append(f"   Base Price: {base_price:.2f} JOD")
        if addons_total > 0:
            lines.append(f"   Add-ons:    +{addons_total:.2f} JOD")
        if grand_total > 0:
            lines.append(f"   *Total:     {grand_total:.2f} JOD*")
        lines.append(divider)
        lines.append("")
        
        # Customer info
        lines.append("👤 *Customer Details:*")
        lines.append(f"   Name:  {name}")
        lines.append(f"   Phone: {phone}")
        
        if notes:
            lines.append(f"   Notes: {notes}")
        
        lines.extend([
            "",
            divider,
            "✅ I would like to confirm this order.",
            "🙏 Thank you!",
        ])
        
        return "\n".join(lines)
    
    def _format_message_ar(
        self, emoji, box_name, product_name, bag_id,
        name, phone, notes, base_price, addons_total, grand_total,
        bag_contents, selected_addons
    ) -> str:
        """Format professional Arabic WhatsApp message."""
        divider = "━━━━━━━━━━━━━━━━━━━━"
        
        lines = [
            f"📦 *CareBox — طلب جديد*",
            divider,
            "",
            f"{emoji} *{product_name or box_name}*",
        ]
        
        if bag_id:
            lines.append(f"🆔 رقم المنتج: {bag_id}")
        
        lines.append("")
        
        # Bag contents section
        if bag_contents and len(bag_contents) > 0:
            lines.append("📋 *محتويات الحقيبة:*")
            for item in bag_contents:
                item_name = item.get("name_ar", item.get("name", ""))
                qty = item.get("qty", 1)
                lines.append(f"   • {item_name} × {qty}")
            lines.append("")
        
        # Add-ons section
        if selected_addons and len(selected_addons) > 0:
            lines.append("✨ *الإضافات المختارة:*")
            for addon in selected_addons:
                addon_name = addon.get("name_ar", addon.get("name", ""))
                addon_price = addon.get("price", 0)
                lines.append(f"   ✚ {addon_name}  (+{addon_price} د.أ)")
            lines.append("")
        
        # Price breakdown
        lines.append(divider)
        lines.append("💰 *ملخص السعر:*")
        if base_price > 0:
            lines.append(f"   السعر الأساسي: {base_price:.2f} د.أ")
        if addons_total > 0:
            lines.append(f"   الإضافات:     +{addons_total:.2f} د.أ")
        if grand_total > 0:
            lines.append(f"   *الإجمالي:    {grand_total:.2f} د.أ*")
        lines.append(divider)
        lines.append("")
        
        # Customer info
        lines.append("👤 *بيانات العميل:*")
        lines.append(f"   الاسم:  {name}")
        lines.append(f"   الهاتف: {phone}")
        
        if notes:
            lines.append(f"   ملاحظات: {notes}")
        
        lines.extend([
            "",
            divider,
            "✅ أريد تأكيد هذا الطلب.",
            "🙏 شكراً لكم!",
        ])
        
        return "\n".join(lines)
    
    def get_box_type_name(self, box_type: str, lang: str = "en") -> str:
        """Get display name for box type."""
        return self.BOX_TYPE_NAMES.get(box_type, {}).get(lang, box_type.title())


# Singleton instance
_orders_service: Optional[OrdersService] = None


def get_orders_service() -> OrdersService:
    """Get or create orders service singleton."""
    global _orders_service
    if _orders_service is None:
        _orders_service = OrdersService()
    return _orders_service
