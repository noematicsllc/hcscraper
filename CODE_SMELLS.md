# Code Smells Analysis

This document identifies 3 code smells found in the codebase and suggests solutions for addressing them.

---

## 1. Duplicated Date Parsing Logic

### Problem
Date parsing logic is duplicated across multiple files with slightly different implementations:

- **`import_to_postgres.py`** (lines 14-37): `parse_date()` function
- **`src/storage/json_writer.py`** (lines 105-131): Date parsing in `_extract_date_parts()` method

Both handle similar date formats (MM/DD/YYYY, ISO format, YYYY-MM-DD, timestamps) but with different error handling and return types.

### Impact
- **Maintenance burden**: Changes to date format handling must be made in multiple places
- **Inconsistency risk**: Different implementations may handle edge cases differently
- **Testing overhead**: Each implementation must be tested separately
- **Bug propagation**: Fixes in one location may not be applied to others

### Solution
Create a centralized date parsing utility module:

```python
# src/utils/date_parser.py
"""Centralized date parsing utilities."""

from datetime import datetime
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def parse_date_string(date_str: str) -> Optional[datetime]:
    """Parse date string in various formats.
    
    Args:
        date_str: Date string (MM/DD/YYYY, YYYY-MM-DD, ISO format, etc.)
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    try:
        # Try MM/DD/YYYY format first
        if '/' in date_str and len(date_str.split('/')) == 3:
            return datetime.strptime(date_str, '%m/%d/%Y')
        # Try ISO format
        elif 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        # Try YYYY-MM-DD
        else:
            return datetime.strptime(date_str[:10], '%Y-%m-%d')
    except (ValueError, AttributeError) as e:
        logger.debug(f"Failed to parse date '{date_str}': {e}")
        return None


def parse_date_value(value: Any) -> Optional[datetime]:
    """Parse date from various value types.
    
    Args:
        value: Can be string, int (timestamp), float (timestamp), or None
        
    Returns:
        datetime object or None if parsing fails
    """
    if value is None:
        return None
    
    if isinstance(value, str):
        return parse_date_string(value)
    elif isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (ValueError, OSError):
            return None
    
    return None


def extract_year_month(date_value: Any) -> Tuple[str, str]:
    """Extract year and month from date value.
    
    Args:
        date_value: Date string, datetime, timestamp, or None
        
    Returns:
        Tuple of (year, month) as strings (e.g., ("2025", "01"))
        Falls back to current date if parsing fails
    """
    date_obj = None
    
    if isinstance(date_value, datetime):
        date_obj = date_value
    else:
        date_obj = parse_date_value(date_value)
    
    if date_obj:
        return date_obj.strftime('%Y'), date_obj.strftime('%m')
    
    # Fallback to current date
    now = datetime.now()
    return now.strftime('%Y'), now.strftime('%m')
```

**Refactoring steps:**
1. Create `src/utils/date_parser.py` with the utility functions
2. Update `import_to_postgres.py` to use `parse_date_string()` instead of `parse_date()`
3. Update `json_writer.py` to use `extract_year_month()` and `parse_date_value()` in `_extract_date_parts()`
4. Add unit tests for the centralized utilities

---

## 2. Duplicated Database Connection Logic

### Problem
Both `OrderExtractor` and `BillingDocumentExtractor` contain nearly identical database connection setup and cleanup code:

- **`src/extractors/order_extractor.py`** (lines 143-153, 368-382): Database connection setup and `close()` method
- **`src/extractors/billing_document_extractor.py`** (lines 49-59, 189-203): Identical database connection setup and `close()` method

The code is duplicated verbatim, including:
- Optional `psycopg` import check
- `DATABASE_URL` environment variable retrieval
- Connection attempt with error handling
- Identical `close()` method implementation
- Context manager support

### Impact
- **DRY violation**: Code duplication increases maintenance burden
- **Inconsistency risk**: Changes to connection logic must be synchronized manually
- **Testing duplication**: Same connection logic must be tested in multiple places
- **Future extractors**: New extractors will likely copy the same pattern

### Solution
Create a base extractor class with shared database connection logic:

```python
# src/extractors/base_extractor.py
"""Base extractor class with shared functionality."""

import os
import logging
from pathlib import Path
from typing import Optional

try:
    import psycopg
except ImportError:
    psycopg = None

from ..storage.json_writer import JSONWriter
from ..api.client import HallmarkAPIClient

logger = logging.getLogger(__name__)


class BaseExtractor:
    """Base class for extractors with shared database connection logic."""
    
    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        save_json: bool = True,
        update_mode: bool = False
    ):
        """Initialize base extractor.
        
        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            save_json: Whether to save JSON files (default: True)
            update_mode: If True, re-download existing files (default: False)
        """
        self.api_client = api_client
        self.output_directory = Path(output_directory)
        self.save_json = save_json
        self.update_mode = update_mode
        
        # Try to connect to database for store number lookup (optional)
        self._db_connection = self._connect_to_database()
        
        # Initialize storage handler
        if self.save_json:
            self.json_writer = JSONWriter(output_directory, db_connection=self._db_connection)
    
    def _connect_to_database(self) -> Optional[Any]:
        """Connect to database for store number lookup (optional).
        
        Returns:
            Database connection or None if connection fails or psycopg not available
        """
        if not psycopg:
            return None
        
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            return None
        
        try:
            connection = psycopg.connect(database_url)
            logger.info("Connected to database for store number lookup")
            return connection
        except Exception as e:
            logger.debug(f"Could not connect to database for store lookup: {e}")
            return None
    
    def close(self) -> None:
        """Close database connection if it exists.
        
        Should be called when done with the extractor to prevent connection leaks.
        """
        if self._db_connection:
            try:
                self._db_connection.close()
                logger.debug("Database connection closed")
                self._db_connection = None
                # Clear reference in json_writer as well
                if hasattr(self, 'json_writer'):
                    self.json_writer.db_connection = None
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")
    
    def __enter__(self):
        """Context manager entry - returns self."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes database connection."""
        self.close()
        return False  # Don't suppress exceptions
```

**Refactoring steps:**
1. Create `src/extractors/base_extractor.py` with `BaseExtractor` class
2. Update `OrderExtractor` to inherit from `BaseExtractor` and remove duplicated code
3. Update `BillingDocumentExtractor` to inherit from `BaseExtractor` and remove duplicated code
4. Ensure all existing functionality is preserved
5. Add unit tests for the base class

---

## 3. Long Method with Multiple Responsibilities

### Problem
The `_parse_aura_response()` method in `src/api/client.py` (lines 543-654) is approximately 110 lines long and handles multiple responsibilities:

- Parsing different response structures (actions array, top-level returnValue, nested returnValue)
- Multiple validation checks (None checks, empty dict checks, structure validation)
- Complex nested conditionals with multiple levels of indentation
- Different handling for orders vs billing documents vs deliveries
- Logging at multiple levels

### Impact
- **Single Responsibility Principle violation**: Method does too many things
- **Testability**: Difficult to test all code paths due to complexity
- **Maintainability**: Hard to understand and modify
- **Readability**: Deep nesting makes logic flow hard to follow
- **Error handling**: Complex error paths are hard to reason about

### Solution
Break down into smaller, focused methods:

```python
# In src/api/client.py

def _parse_aura_response(
    self,
    response_data: Dict[str, Any],
    entity_id: str
) -> Optional[Dict[str, Any]]:
    """Parse Aura framework API response.
    
    Args:
        response_data: Raw response JSON
        entity_id: Entity ID (for logging)
        
    Returns:
        Extracted return value, or None if response indicates error
    """
    if not isinstance(response_data, dict):
        logger.error(f"Invalid response format for {entity_id}")
        return None
    
    # Try parsing as actions array (standard Aura response)
    if 'actions' in response_data:
        return self._parse_actions_response(response_data, entity_id)
    
    # Try parsing as top-level returnValue
    if 'returnValue' in response_data:
        return self._parse_top_level_return_value(response_data, entity_id)
    
    # Unexpected structure
    logger.error(
        f"Unexpected response structure for {entity_id}. "
        f"Expected 'actions' array or 'returnValue' at top level. "
        f"Available keys: {list(response_data.keys())}"
    )
    logger.debug(f"Full response structure (first 1000 chars): {str(response_data)[:1000]}")
    return None


def _parse_actions_response(
    self,
    response_data: Dict[str, Any],
    entity_id: str
) -> Optional[Dict[str, Any]]:
    """Parse Aura response with actions array structure.
    
    Args:
        response_data: Response with 'actions' array
        entity_id: Entity ID (for logging)
        
    Returns:
        Extracted return value or None
    """
    actions = response_data.get('actions', [])
    if not actions:
        logger.error(f"No actions in response for {entity_id}")
        return None
    
    action = actions[0]
    state = action.get('state')
    
    if state == 'SUCCESS':
        return_value = action.get('returnValue')
        return self._extract_return_value(return_value, entity_id)
    
    elif state == 'ERROR':
        errors = action.get('error', [])
        error_messages = [err.get('message', 'Unknown error') for err in errors]
        logger.error(f"Action failed for {entity_id}: {', '.join(error_messages)}")
        return None
    
    else:
        logger.error(f"Unknown action state '{state}' for {entity_id}")
        return None


def _parse_top_level_return_value(
    self,
    response_data: Dict[str, Any],
    entity_id: str
) -> Optional[Dict[str, Any]]:
    """Parse response with returnValue at top level.
    
    Args:
        response_data: Response with 'returnValue' at top level
        entity_id: Entity ID (for logging)
        
    Returns:
        Extracted return value or None
    """
    logger.debug(f"Found returnValue at top level for {entity_id}")
    return_value = response_data.get('returnValue')
    return self._extract_return_value(return_value, entity_id)


def _extract_return_value(
    self,
    return_value: Any,
    entity_id: str
) -> Optional[Dict[str, Any]]:
    """Extract and validate return value, handling nested structures.
    
    Args:
        return_value: The returnValue from API response
        entity_id: Entity ID (for logging)
        
    Returns:
        Validated return value or None
    """
    # Validate not None or empty
    if return_value is None:
        logger.warning(f"Empty returnValue (None) for {entity_id}")
        return None
    
    if isinstance(return_value, dict) and len(return_value) == 0:
        logger.warning(f"Empty returnValue (empty dict) for {entity_id}")
        return None
    
    # Handle nested returnValue structures
    if isinstance(return_value, dict) and 'returnValue' in return_value:
        nested = return_value.get('returnValue')
        return self._unwrap_nested_return_value(return_value, nested, entity_id)
    
    # Check for expected structure (orderHeader, billingDocumentHeader, etc.)
    if isinstance(return_value, dict):
        if self._has_expected_structure(return_value):
            logger.debug(f"returnValue contains expected structure for {entity_id}")
            return return_value
    
    return return_value


def _unwrap_nested_return_value(
    self,
    outer: Dict[str, Any],
    nested: Any,
    entity_id: str
) -> Optional[Dict[str, Any]]:
    """Unwrap nested returnValue structure.
    
    Args:
        outer: Outer returnValue dict
        nested: Nested returnValue
        entity_id: Entity ID (for logging)
        
    Returns:
        Unwrapped return value or None
    """
    if not isinstance(nested, dict):
        return outer
    
    # If nested has expected structure, use nested
    if self._has_expected_structure(nested):
        logger.debug(f"Using nested returnValue with expected structure for {entity_id}")
        return nested
    
    # If outer has cacheable but nested doesn't, nested is likely the actual data
    if 'cacheable' in outer and 'cacheable' not in nested:
        logger.debug(f"Unwrapping nested returnValue (outer has cacheable) for {entity_id}")
        return nested
    
    # Prefer nested if it exists
    logger.debug(f"Using nested returnValue for {entity_id}")
    return nested


def _has_expected_structure(self, data: Dict[str, Any]) -> bool:
    """Check if data has expected entity structure.
    
    Args:
        data: Data dictionary to check
        
    Returns:
        True if data contains expected keys (orderHeader, billingDocumentHeader, etc.)
    """
    expected_keys = ['orderHeader', 'billingDocumentHeader', 'billingHeader', 
                     'documentHeader', 'invoiceHeader']
    return any(key in data for key in expected_keys)
```

**Refactoring steps:**
1. Break down `_parse_aura_response()` into smaller methods as shown above
2. Extract validation logic into separate methods
3. Extract nested structure handling into separate methods
4. Add unit tests for each extracted method
5. Ensure all existing functionality is preserved

---

## Summary

These three code smells represent common issues that can be addressed through refactoring:

1. **Duplicated date parsing** → Centralize in utility module
2. **Duplicated database connection** → Extract to base class
3. **Long method with multiple responsibilities** → Break into smaller, focused methods

All three solutions follow established design principles (DRY, SRP, Single Responsibility) and will improve maintainability, testability, and code clarity.

