# Code Smells Analysis

This document identifies 1 code smell found in the codebase and suggests solutions for addressing it.

---

## 1. Long Method with Multiple Responsibilities

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

This code smell represents a common issue that can be addressed through refactoring:

1. **Long method with multiple responsibilities** → Break into smaller, focused methods

The solution follows established design principles (SRP, Single Responsibility) and will improve maintainability, testability, and code clarity.

---

## Resolved Issues

### ✅ Duplicated Date Parsing Logic (Resolved)
**Status**: Implemented and resolved

Date parsing logic has been centralized in `src/utils/date_parser.py` with the following utilities:
- `parse_date_string()`: Parses date strings in various formats
- `parse_date_value()`: Parses dates from strings, timestamps, or datetime objects
- `extract_year_month()`: Extracts year and month from any date value

Both `import_to_postgres.py` and `src/storage/json_writer.py` now use these centralized utilities, eliminating code duplication.

### ✅ Duplicated Database Connection Logic (Resolved)
**Status**: Implemented and resolved

Database connection logic has been centralized in `src/extractors/base_extractor.py` with the `BaseExtractor` base class. The base class provides:
- `_connect_to_database()`: Handles optional database connection setup
- `close()`: Closes database connections and cleans up resources
- `__enter__()` and `__exit__()`: Context manager protocol implementation

Both `OrderExtractor` and `BillingDocumentExtractor` now inherit from `BaseExtractor`, eliminating ~40 lines of duplicated code from each class. The context manager pattern is preserved and all existing functionality remains unchanged.

