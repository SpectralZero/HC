"""
CareBox Bags Service

Handles bag/product lookups from Google Sheets.
Provides bag data with localized content for Arabic/English.
Supports image, price, customization options, and bag contents.
"""

import logging
import json
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Bag:
    """Bag data model with localized fields."""
    bag_id: str
    box_type: str
    title_en: str
    title_ar: str
    video_url: str
    tips_en: List[str]
    tips_ar: List[str]
    serial_last4: str
    is_active: bool
    # Extended fields
    image_url: str = ""
    price: float = 0.0
    options: List[Dict[str, Any]] = field(default_factory=list)
    contents: List[Dict[str, Any]] = field(default_factory=list)
    
    def get_title(self, lang: str = "en") -> str:
        """Get title in specified language."""
        return self.title_ar if lang == "ar" else self.title_en
    
    def get_tips(self, lang: str = "en") -> List[str]:
        """Get tips in specified language."""
        return self.tips_ar if lang == "ar" else self.tips_en
    
    def to_dict(self, lang: str = "en") -> Dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            "bag_id": self.bag_id,
            "box_type": self.box_type,
            "title": self.get_title(lang),
            "title_en": self.title_en,
            "title_ar": self.title_ar,
            "video_url": self.video_url,
            "tips": self.get_tips(lang),
            "is_active": self.is_active,
            "image_url": self.image_url,
            "price": self.price,
            "options": self.options,
            "contents": self.contents,
        }


class BagsService:
    """Service for bag/product operations."""
    
    # Column indices in BAGS sheet (0-indexed)
    COL_BAG_ID = 0
    COL_BOX_TYPE = 1
    COL_TITLE_EN = 2
    COL_TITLE_AR = 3
    COL_IMAGE_URL = 4
    COL_VIDEO_URL = 5
    COL_TIPS_EN = 6
    COL_TIPS_AR = 7
    COL_PRICE = 8
    COL_OPTIONS = 9      # JSON: [{"name":"Extra vitamins","name_ar":"فيتامينات","price":5}]
    COL_SERIAL_LAST4 = 10
    COL_IS_ACTIVE = 11
    COL_CONTENTS = 12    # JSON: [{"name":"Bandages","name_ar":"ضمادات","qty":2}]
    
    TOTAL_COLS = 13
    
    def __init__(self):
        """Initialize bags service."""
        self._sheets_client = None
        self._cache: Dict[str, Bag] = {}
    
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
    
    def _get_bags_worksheet(self):
        """Get the BAGS worksheet."""
        client = self._get_sheets_client()
        if not client:
            return None
        try:
            from config import get_config
            config = get_config()
            return client.get_worksheet(config.SHEETS_DOC_NAME, config.SHEET_TAB_BAGS)
        except Exception as e:
            logger.warning(f"Could not get BAGS worksheet: {e}")
            return None
    
    def _parse_tips(self, tips_str: str) -> List[str]:
        """Parse pipe-separated tips string into list."""
        if not tips_str:
            return []
        return [tip.strip() for tip in tips_str.split("|") if tip.strip()]
    
    def _parse_json_field(self, json_str: str) -> List[Dict[str, Any]]:
        """Parse JSON string field (options or contents)."""
        if not json_str:
            return []
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def _row_to_bag(self, row: List[str]) -> Optional[Bag]:
        """Convert sheet row to Bag object."""
        try:
            # Pad row to expected length
            while len(row) < self.TOTAL_COLS:
                row.append("")
            
            # Parse price safely
            try:
                price = float(row[self.COL_PRICE]) if row[self.COL_PRICE] else 0.0
            except (ValueError, TypeError):
                price = 0.0
            
            return Bag(
                bag_id=row[self.COL_BAG_ID],
                box_type=row[self.COL_BOX_TYPE],
                title_en=row[self.COL_TITLE_EN],
                title_ar=row[self.COL_TITLE_AR] or row[self.COL_TITLE_EN],
                video_url=row[self.COL_VIDEO_URL],
                tips_en=self._parse_tips(row[self.COL_TIPS_EN]),
                tips_ar=self._parse_tips(row[self.COL_TIPS_AR]) or self._parse_tips(row[self.COL_TIPS_EN]),
                serial_last4=row[self.COL_SERIAL_LAST4],
                is_active=row[self.COL_IS_ACTIVE].upper() == "TRUE",
                image_url=row[self.COL_IMAGE_URL],
                price=price,
                options=self._parse_json_field(row[self.COL_OPTIONS]),
                contents=self._parse_json_field(row[self.COL_CONTENTS]),
            )
        except (IndexError, ValueError) as e:
            logger.warning(f"Failed to parse bag row: {e}")
            return None
    
    def _row_to_raw_dict(self, row: List[str]) -> Dict[str, Any]:
        """Convert sheet row to raw dict."""
        while len(row) < self.TOTAL_COLS:
            row.append("")
        try:
            price = float(row[self.COL_PRICE]) if row[self.COL_PRICE] else 0.0
        except (ValueError, TypeError):
            price = 0.0
        return {
            "bag_id": row[self.COL_BAG_ID],
            "box_type": row[self.COL_BOX_TYPE],
            "title_en": row[self.COL_TITLE_EN],
            "title_ar": row[self.COL_TITLE_AR],
            "image_url": row[self.COL_IMAGE_URL],
            "video_url": row[self.COL_VIDEO_URL],
            "tips_en": row[self.COL_TIPS_EN],
            "tips_ar": row[self.COL_TIPS_AR],
            "price": price,
            "options": row[self.COL_OPTIONS],
            "serial_last4": row[self.COL_SERIAL_LAST4],
            "is_active": row[self.COL_IS_ACTIVE].upper() == "TRUE" if row[self.COL_IS_ACTIVE] else False,
            "contents": row[self.COL_CONTENTS],
        }
    
    def get_all_rows(self) -> List[List[str]]:
        """Get all rows from BAGS sheet."""
        worksheet = self._get_bags_worksheet()
        if not worksheet:
            return []
        try:
            return worksheet.get_all_values()
        except Exception as e:
            logger.warning(f"Failed to get bag rows: {e}")
            return []
    
    def get_bag_by_id(self, bag_id: str) -> Optional[Bag]:
        """Get bag by its unique ID."""
        if bag_id in self._cache:
            return self._cache[bag_id]
        
        try:
            rows = self.get_all_rows()
            for row in rows[1:]:
                if len(row) > 0 and row[self.COL_BAG_ID] == bag_id:
                    bag = self._row_to_bag(row)
                    if bag and bag.is_active:
                        self._cache[bag_id] = bag
                        return bag
            return None
        except Exception as e:
            logger.warning(f"Error getting bag by ID: {e}")
            return None
    
    def get_bag_by_type(self, box_type: str) -> Optional[Bag]:
        """Get first active bag of specified type."""
        try:
            rows = self.get_all_rows()
            for row in rows[1:]:
                if len(row) > self.COL_BOX_TYPE and row[self.COL_BOX_TYPE].lower() == box_type.lower():
                    bag = self._row_to_bag(row)
                    if bag and bag.is_active:
                        return bag
            return None
        except Exception as e:
            logger.warning(f"Error getting bag by type: {e}")
            return None
    
    def get_all_active_bags(self) -> List[Bag]:
        """Get all active bags."""
        bags = []
        try:
            rows = self.get_all_rows()
            for row in rows[1:]:
                bag = self._row_to_bag(row)
                if bag and bag.is_active:
                    bags.append(bag)
        except Exception as e:
            logger.warning(f"Error getting all active bags: {e}")
        return bags
    
    def verify_serial(self, bag_id: str, serial_last4: str) -> bool:
        """Verify serial number for a bag."""
        bag = self.get_bag_by_id(bag_id)
        if not bag:
            return False
        return bag.serial_last4 == serial_last4
    
    def clear_cache(self) -> None:
        """Clear the bag cache."""
        self._cache.clear()
    
    # =========================================================================
    # ADMIN CRUD METHODS
    # =========================================================================
    
    def get_all_bags(self, include_inactive: bool = False) -> List[Bag]:
        """Get all bags, optionally including inactive ones."""
        bags = []
        try:
            rows = self.get_all_rows()
            for row in rows[1:]:
                bag = self._row_to_bag(row)
                if bag and (include_inactive or bag.is_active):
                    bags.append(bag)
        except Exception as e:
            logger.warning(f"Error getting all bags: {e}")
        return bags
    
    def get_all_bags_raw(self) -> List[Dict[str, Any]]:
        """Get all bags as raw dicts for admin listing."""
        bags = []
        try:
            rows = self.get_all_rows()
            for row in rows[1:]:
                if len(row) > 0 and row[0]:
                    bags.append(self._row_to_raw_dict(row))
        except Exception as e:
            logger.warning(f"Error getting all bags raw: {e}")
        return bags
    
    def _find_row_index(self, bag_id: str) -> int:
        """Find row index (1-based) for bag_id. Returns 0 if not found."""
        try:
            rows = self.get_all_rows()
            for i, row in enumerate(rows):
                if len(row) > 0 and row[self.COL_BAG_ID] == bag_id:
                    return i + 1
        except Exception as e:
            logger.warning(f"Error finding row: {e}")
        return 0
    
    def add_bag(self, data: Dict[str, Any]) -> bool:
        """Add new bag to sheet."""
        try:
            worksheet = self._get_bags_worksheet()
            if not worksheet:
                return False
            
            row = [
                data.get("bag_id", ""),
                data.get("box_type", ""),
                data.get("title_en", ""),
                data.get("title_ar", ""),
                data.get("image_url", ""),
                data.get("video_url", ""),
                data.get("tips_en", ""),
                data.get("tips_ar", ""),
                str(data.get("price", 0)),
                data.get("options", ""),
                data.get("serial_last4", ""),
                "TRUE" if data.get("is_active", True) else "FALSE",
                data.get("contents", ""),
            ]
            worksheet.append_row(row, value_input_option="USER_ENTERED")
            self.clear_cache()
            logger.info(f"Added bag: {data.get('bag_id')}")
            return True
        except Exception as e:
            logger.error(f"Failed to add bag: {e}")
            return False
    
    def update_bag(self, bag_id: str, data: Dict[str, Any]) -> bool:
        """Update existing bag in sheet."""
        try:
            worksheet = self._get_bags_worksheet()
            if not worksheet:
                return False
            
            row_index = self._find_row_index(bag_id)
            if row_index == 0:
                return False
            
            updates = [
                (row_index, self.COL_BOX_TYPE + 1, data.get("box_type", "")),
                (row_index, self.COL_TITLE_EN + 1, data.get("title_en", "")),
                (row_index, self.COL_TITLE_AR + 1, data.get("title_ar", "")),
                (row_index, self.COL_IMAGE_URL + 1, data.get("image_url", "")),
                (row_index, self.COL_VIDEO_URL + 1, data.get("video_url", "")),
                (row_index, self.COL_TIPS_EN + 1, data.get("tips_en", "")),
                (row_index, self.COL_TIPS_AR + 1, data.get("tips_ar", "")),
                (row_index, self.COL_PRICE + 1, str(data.get("price", 0))),
                (row_index, self.COL_OPTIONS + 1, data.get("options", "")),
                (row_index, self.COL_SERIAL_LAST4 + 1, data.get("serial_last4", "")),
                (row_index, self.COL_IS_ACTIVE + 1, "TRUE" if data.get("is_active") else "FALSE"),
                (row_index, self.COL_CONTENTS + 1, data.get("contents", "")),
            ]
            
            for r, c, val in updates:
                worksheet.update_cell(r, c, val)
            
            self.clear_cache()
            logger.info(f"Updated bag: {bag_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update bag: {e}")
            return False
    
    def delete_bag(self, bag_id: str) -> bool:
        """Delete bag from sheet."""
        try:
            worksheet = self._get_bags_worksheet()
            if not worksheet:
                return False
            
            row_index = self._find_row_index(bag_id)
            if row_index == 0:
                return False
            
            worksheet.delete_rows(row_index)
            self.clear_cache()
            logger.info(f"Deleted bag: {bag_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete bag: {e}")
            return False
    
    def toggle_active(self, bag_id: str) -> bool:
        """Toggle bag active status."""
        try:
            worksheet = self._get_bags_worksheet()
            if not worksheet:
                return False
            
            row_index = self._find_row_index(bag_id)
            if row_index == 0:
                return False
            
            current = worksheet.cell(row_index, self.COL_IS_ACTIVE + 1).value
            new_value = "FALSE" if current and current.upper() == "TRUE" else "TRUE"
            worksheet.update_cell(row_index, self.COL_IS_ACTIVE + 1, new_value)
            
            self.clear_cache()
            logger.info(f"Toggled bag {bag_id} to {new_value}")
            return True
        except Exception as e:
            logger.error(f"Failed to toggle bag: {e}")
            return False
    
    def get_bag_raw(self, bag_id: str) -> Optional[Dict[str, Any]]:
        """Get bag as raw dict for editing."""
        try:
            rows = self.get_all_rows()
            for row in rows[1:]:
                if len(row) > 0 and row[self.COL_BAG_ID] == bag_id:
                    return self._row_to_raw_dict(row)
        except Exception as e:
            logger.warning(f"Error getting bag raw: {e}")
        return None


# Singleton instance
_bags_service: Optional[BagsService] = None


def get_bags_service() -> BagsService:
    """Get or create bags service singleton."""
    global _bags_service
    if _bags_service is None:
        _bags_service = BagsService()
    return _bags_service
