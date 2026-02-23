"""
Google Sheets Client Service

Provides a connection wrapper for Google Sheets API with:
- Service account authentication
- Connection caching
- Error handling
- Type hints
"""

import logging
from typing import Optional, List, Dict, Any
from functools import lru_cache

import gspread
from google.oauth2.service_account import Credentials
from gspread import Worksheet, Spreadsheet
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound, APIError

logger = logging.getLogger(__name__)

# Google Sheets API scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",  # For opening by name
]


class SheetsClientError(Exception):
    """Base exception for Sheets client errors."""
    pass


class SheetNotFoundError(SheetsClientError):
    """Raised when a sheet or worksheet is not found."""
    pass


class SheetsClient:
    """
    Google Sheets API client wrapper.
    
    Usage:
        client = SheetsClient(credentials_path)
        worksheet = client.get_worksheet("CareBoxDB", "BAGS")
        records = client.get_all_records(worksheet)
    """

    def __init__(self, credentials_path: str):
        """
        Initialize the Sheets client with service account credentials.
        
        Args:
            credentials_path: Path to service account JSON file
        """
        self._credentials_path = credentials_path
        self._client: Optional[gspread.Client] = None
        self._spreadsheet_cache: Dict[str, Spreadsheet] = {}

    def _get_client(self) -> gspread.Client:
        """
        Get or create an authenticated gspread client.
        
        Returns:
            Authenticated gspread client
            
        Raises:
            SheetsClientError: If authentication fails
        """
        if self._client is None:
            try:
                creds = Credentials.from_service_account_file(
                    self._credentials_path,
                    scopes=SCOPES
                )
                self._client = gspread.authorize(creds)
                logger.info("Google Sheets client authenticated successfully")
            except Exception as e:
                logger.error(f"Failed to authenticate with Google Sheets: {e}")
                raise SheetsClientError(f"Authentication failed: {e}")
        
        return self._client

    def get_spreadsheet(self, doc_name: str) -> Spreadsheet:
        """
        Open a spreadsheet by name.
        
        Args:
            doc_name: Name of the Google Sheet document
            
        Returns:
            Spreadsheet object
            
        Raises:
            SheetNotFoundError: If spreadsheet not found
        """
        if doc_name in self._spreadsheet_cache:
            return self._spreadsheet_cache[doc_name]

        try:
            client = self._get_client()
            spreadsheet = client.open(doc_name)
            self._spreadsheet_cache[doc_name] = spreadsheet
            logger.debug(f"Opened spreadsheet: {doc_name}")
            return spreadsheet
        except SpreadsheetNotFound:
            logger.error(f"Spreadsheet not found: {doc_name}")
            raise SheetNotFoundError(f"Spreadsheet '{doc_name}' not found")
        except APIError as e:
            logger.error(f"API error opening spreadsheet: {e}")
            raise SheetsClientError(f"API error: {e}")

    def get_worksheet(self, doc_name: str, tab_name: str) -> Worksheet:
        """
        Get a specific worksheet from a spreadsheet.
        
        Args:
            doc_name: Name of the Google Sheet document
            tab_name: Name of the tab/worksheet
            
        Returns:
            Worksheet object
            
        Raises:
            SheetNotFoundError: If worksheet not found
        """
        try:
            spreadsheet = self.get_spreadsheet(doc_name)
            worksheet = spreadsheet.worksheet(tab_name)
            logger.debug(f"Accessed worksheet: {tab_name}")
            return worksheet
        except WorksheetNotFound:
            logger.error(f"Worksheet not found: {tab_name}")
            raise SheetNotFoundError(f"Worksheet '{tab_name}' not found in '{doc_name}'")

    def get_all_records(self, worksheet: Worksheet) -> List[Dict[str, Any]]:
        """
        Get all records from a worksheet as a list of dictionaries.
        
        Args:
            worksheet: Worksheet object
            
        Returns:
            List of row dictionaries (header row as keys)
        """
        try:
            records = worksheet.get_all_records()
            logger.debug(f"Retrieved {len(records)} records from worksheet")
            return records
        except APIError as e:
            logger.error(f"API error getting records: {e}")
            raise SheetsClientError(f"Failed to get records: {e}")

    def append_row(self, worksheet: Worksheet, row_data: List[Any]) -> None:
        """
        Append a new row to a worksheet.
        
        Args:
            worksheet: Worksheet object
            row_data: List of cell values
        """
        try:
            worksheet.append_row(row_data, value_input_option="USER_ENTERED")
            logger.debug(f"Appended row with {len(row_data)} columns")
        except APIError as e:
            logger.error(f"API error appending row: {e}")
            raise SheetsClientError(f"Failed to append row: {e}")

    def find_row_by_column(
        self, 
        worksheet: Worksheet, 
        column_name: str, 
        value: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find the first row where a column matches a value.
        
        Args:
            worksheet: Worksheet object
            column_name: Name of the column to search
            value: Value to match
            
        Returns:
            Row dictionary or None if not found
        """
        records = self.get_all_records(worksheet)
        for record in records:
            if str(record.get(column_name, "")).strip() == value:
                return record
        return None

    def clear_cache(self) -> None:
        """Clear the spreadsheet cache."""
        self._spreadsheet_cache.clear()
        logger.debug("Spreadsheet cache cleared")


# Global client instance (lazy initialization)
_sheets_client: Optional[SheetsClient] = None


def get_sheets_client(credentials_path: str) -> SheetsClient:
    """
    Get or create the global Sheets client.
    
    Args:
        credentials_path: Path to service account JSON
        
    Returns:
        SheetsClient instance
    """
    global _sheets_client
    if _sheets_client is None:
        _sheets_client = SheetsClient(credentials_path)
    return _sheets_client
