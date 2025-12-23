# Data Extraction System - CRITICAL DOCUMENTATION

## ⚠️ CRITICAL WARNING

**Breaking data extraction is a CATASTROPHIC FAILURE.** This system is responsible for extracting and storing all order, billing document, and delivery data. Any changes to extraction or storage logic must be thoroughly tested and documented.

## Overview

The Hallmark Connect scraper extracts data from the Salesforce Aura API and stores it in a hierarchical JSON file structure. The extraction process involves:
1. API requests to retrieve entity details (orders, billing documents, deliveries)
2. Parsing and flattening the API response structure
3. Validating data completeness
4. Saving to JSON files in organized directory structure

## Default Behavior: Skip Existing Records

**CRITICAL SAFETY FEATURE**: By default, the system **skips records that have already been extracted**. This prevents:
- Wasting time re-downloading existing data
- Wasting API resources and rate limits
- Potential data loss if re-extraction fails

**To re-download existing records**, use the `--update` flag.

### Skip Behavior

- **Default (`update_mode=False`)**: Skip existing files, log skip message
- **Update mode (`--update` flag)**: Re-download all records, even if they exist
- **Skip tracking**: Skipped records are counted separately in extraction summary

## Data Extraction Flow

### Step 0: Check for Existing Record (SAFETY)

1. Check if order file already exists in directory structure
2. If exists and `update_mode=False`: Skip immediately, return success
3. If exists and `update_mode=True`: Continue to re-download
4. Track skipped records separately for reporting

### Step 1: API Request

1. Build Aura API request using `AuraRequestBuilder`
2. Execute request via `HallmarkAPIClient.get_order_detail()` (or similar)
3. Parse Aura response to extract `returnValue`
4. Validate that `returnValue` is not None or empty

### Step 2: Data Flattening

1. Extract `orderHeader` and `orderLines` from `returnValue`
2. Validate that `orderHeader` exists and is not empty
3. Flatten structure: move all `orderHeader` fields to top level
4. Convert camelCase keys to snake_case
5. Convert `orderLines` array with snake_case keys

### Step 3: Data Validation

1. Check that flattened data has required fields (`order_id`)
2. Check that data has actual content (not just `order_id` and empty `order_lines`)
3. Validate date extraction for directory structure
4. Validate store ID extraction for directory structure

### Step 4: File Storage

1. Extract date parts (year, month) from order data
2. Extract store ID (canonical store_number if available, otherwise customer_id)
3. Create hierarchical directory: `{year}/{month}/store_{store_id}/`
4. Save JSON file: `order_{order_id}.json`

## Expected Data Structures

### API Response Structure

**Success Response**:
```json
{
    "actions": [{
        "id": "761;a",
        "state": "SUCCESS",
        "returnValue": {
            "orderHeader": {
                "customerId": 1000004735,
                "storeName": "BANNER'S HALLMARK SHOP 1403",
                "orderCreationDate": "09/01/2025",
                ...
            },
            "orderLines": [
                {
                    "lineItemNumber": 1,
                    "materialNumber": "000000007001039005",
                    ...
                }
            ]
        }
    }]
}
```

**Error Response**:
```json
{
    "actions": [{
        "id": "761;a",
        "state": "ERROR",
        "error": [{
            "message": "Error description"
        }]
    }]
}
```

### Flattened JSON Structure

**Valid Order File**:
```json
{
    "order_id": "3068921632",
    "customer_id": 1000004735,
    "store_name": "BANNER'S HALLMARK SHOP 1403",
    "order_creation_date": "09/01/2025",
    "order_total": "45.730000000 ",
    "order_lines": [
        {
            "line_item_number": 1,
            "material_number": "000000007001039005",
            "material_description": "SHIP FROM STORE OMNI",
            ...
        }
    ]
}
```

**Invalid Order File (REGRESSION)**:
```json
{
    "order_id": "3070999613",
    "order_lines": []
}
```

This is invalid because:
- Missing all `orderHeader` fields (customer_id, store_name, order_creation_date, etc.)
- Will be saved in wrong directory (`store_unknown`, wrong month)
- Indicates API error or authentication failure

## Validation Requirements

### API Response Validation

**In `_parse_aura_response`** (`src/api/client.py`):
- Check that `returnValue` is not None
- Check that `returnValue` is not an empty dict
- Log warning and return None if invalid

### Data Structure Validation

**In `_flatten_order_data`** (`src/storage/json_writer.py`):
- Validate that `order_data` is a dict
- Validate that `orderHeader` exists and is a dict
- Validate that `orderHeader` is not empty
- Raise `ValueError` with descriptive message if invalid

**In `save_order`** (`src/storage/json_writer.py`):
- Validate that flattened data has `order_id`
- Validate that flattened data has additional fields beyond `order_id` and `order_lines`
- Raise `ValueError` if data is too incomplete

### Extraction Validation

**In `extract_single_order`** (`src/extractors/order_extractor.py`):
- Check that `order_data` is not None
- Check that `order_data` is not an empty dict
- Check that `order_data` has `orderHeader` key
- Log detailed error messages
- Return `False` to prevent saving invalid data

## Failure Handling and Early Stopping

### Critical Safety Feature

**The extraction system will STOP IMMEDIATELY on validation failures** to prevent wasting hours processing thousands of records that will all fail.

### Failure Types

1. **Validation Failures (STOP IMMEDIATELY)**
   - Empty returnValue from API
   - Missing orderHeader in response
   - Data structure validation failures
   - **Action**: Extraction stops immediately, returns error code 1
   - **Reason**: Indicates systemic problem (authentication, API changes, etc.)

2. **Transient Failures (Consecutive Threshold)**
   - Network timeouts
   - Temporary API errors
   - **Action**: Stops after 3 consecutive failures (configurable)
   - **Reason**: May be temporary, can resume later

### Early Stop Behavior

When extraction stops early:
- **Validation failure**: Clear error message, exit code 1, DO NOT resume
- **Consecutive failures**: Warning message, exit code 1, can resume later
- Progress summary shows how many were processed before stopping
- Failed order IDs are logged for reference

## Common Failure Modes

### 1. Empty returnValue

**Symptom**: Extraction stops immediately with validation failure
**Error**: "CRITICAL: Failed to retrieve order {order_id}: API returned None/empty dict"
**Root Cause**: API returns empty response (usually authentication failure)
**Fix**: 
- Verify authentication is working (see `authentication_critical.md`)
- Check that Aura tokens are valid
- Verify API request format is correct
**Action**: Extraction stops immediately - DO NOT resume until fixed

### 2. Missing orderHeader

**Symptom**: Extraction stops immediately with validation failure
**Error**: "CRITICAL: Invalid order data structure for order {order_id}: missing 'orderHeader'"
**Root Cause**: API response structure changed or authentication failure
**Fix**:
- Check API response structure
- Verify authentication tokens
- Check for API changes
**Action**: Extraction stops immediately - DO NOT resume until fixed

### 3. Wrong Directory Structure

**Symptom**: Files saved in `store_unknown` or wrong month
**Error**: Date/store extraction fails
**Root Cause**: Missing date/store fields in order data
**Fix**:
- Ensure `orderHeader` has date fields (`orderCreationDate`, etc.)
- Ensure `orderHeader` has customer ID for store lookup
- Check database connection for store number lookup

### 4. Empty Files Saved (PREVENTED)

**Symptom**: This should no longer occur due to validation
**Error**: Validation failures now stop extraction immediately
**Root Cause**: Previously validation was insufficient
**Fix**: 
- Validation is now enforced at multiple levels
- Extraction stops immediately on validation failures
- Empty files cannot be saved due to validation checks

## Code Locations

### Key Files

- `src/api/client.py`:
  - `get_order_detail()`: Retrieves order data from API
  - `_parse_aura_response()`: Parses Aura response, validates returnValue

- `src/storage/json_writer.py`:
  - `_flatten_order_data()`: Flattens order structure, validates orderHeader
  - `save_order()`: Validates and saves order data
  - `_extract_date_parts()`: Extracts year/month for directory structure
  - `_extract_store_id()`: Extracts store ID for directory structure

- `src/extractors/order_extractor.py`:
  - `extract_single_order()`: Coordinates extraction, validates data before saving

### Critical Code Sections

**DO NOT modify without thorough testing:**

1. Validation in `_flatten_order_data` (lines ~317-330 in `json_writer.py`)
   - **MUST validate orderHeader exists and is not empty**
   - **MUST raise ValueError if invalid**

2. Validation in `save_order` (lines ~458-475 in `json_writer.py`)
   - **MUST validate minimum required fields**
   - **MUST check for actual data beyond order_id**

3. Validation in `_parse_aura_response` (lines ~534-546 in `client.py`)
   - **MUST check returnValue is not None or empty**
   - **MUST return None if invalid**

4. Error handling in `extract_single_order` (lines ~171-194 in `order_extractor.py`)
   - **MUST validate order_data before saving**
   - **MUST return False if validation fails**

## Billing Document Extraction

Billing documents use a separate flattening method (`_flatten_billing_document_data`) but follow similar patterns:

- Validates that billing data is not None/empty
- Handles nested `returnValue` wrapper
- Looks for multiple possible header field names
- Validates before saving

**Important**: Changes to order extraction should not affect billing document extraction. Test both when making changes.

## Directory Structure

Files are saved in hierarchical structure:
```
data/
  {year}/
    {month}/
      store_{store_id}/
        order_{order_id}.json
        billing_{billing_document_id}.json
```

**Example**:
```
data/2025/09/store_1403/order_3068921632.json
```

**Extraction Logic**:
- Year/Month: From `order_creation_date` field (MM/DD/YYYY format)
- Store ID: Canonical `store_number` from database lookup, fallback to `customer_id`, fallback to "unknown"

## Skip-by-Default Safety

### Why Skip by Default

1. **Time Efficiency**: Re-downloading thousands of existing records wastes hours
2. **Resource Conservation**: Saves API calls, rate limits, and bandwidth
3. **Data Protection**: Prevents accidental overwrite of valid data if re-extraction fails
4. **Resume Capability**: Failed extractions can be resumed without re-downloading completed records

### Implementation

- `order_file_exists()` checks directory tree for existing files
- Skip happens before any API call (fast, no wasted requests)
- Skipped records counted separately in summary
- Clear logging: "Order {id} already exists, skipping to save time and resources"

### When to Use --update

- Data structure changed and need to re-extract
- Suspect existing files are corrupted
- Need to refresh all data (rare)

**Warning**: Using `--update` on large batches will take significantly longer and may hit rate limits.

## Testing Strategy

### Manual Testing

1. Extract a single order:
   ```bash
   python main.py --order-id 3068921632
   ```

2. Verify file structure:
   - Check file exists in correct directory
   - Check file has all required fields
   - Check file is not empty

3. Test skip behavior:
   - Run same command again - should skip
   - Run with `--update` - should re-download
   - Check summary shows skipped count

4. Test with invalid order (should fail gracefully):
   - Order that doesn't exist
   - Order with API error
   - Order with authentication failure

### Validation Testing

1. Test with empty returnValue (should not save file)
2. Test with missing orderHeader (should raise ValueError)
3. Test with incomplete data (should raise ValueError)
4. Test with valid data (should save correctly)

## Best Practices

1. **Always validate before saving**
   - Check data structure
   - Check required fields
   - Check data completeness

2. **Log detailed errors**
   - Include order ID in error messages
   - Include available keys when structure is wrong
   - Include root cause hints (authentication, API error, etc.)

3. **Fail fast**
   - Don't save incomplete data
   - Return False/None on validation failure
   - Raise exceptions with descriptive messages

4. **Test both orders and billing documents**
   - Changes to one should not break the other
   - Test with real data when possible

## Troubleshooting

### Files saved in wrong directory

1. Check date extraction:
   - Verify `order_creation_date` field exists
   - Check date format (MM/DD/YYYY)
   - Verify date parsing logic

2. Check store extraction:
   - Verify `customer_id` field exists
   - Check database connection for store lookup
   - Verify fallback logic

### Empty files being saved

1. Check validation is working:
   - Verify `_flatten_order_data` validates orderHeader
   - Verify `save_order` validates minimum fields
   - Verify `extract_single_order` validates before saving

2. Check API response:
   - Verify authentication is working
   - Check API response structure
   - Verify returnValue is not empty

### Validation errors

1. Check error messages:
   - Look for specific field that's missing
   - Check available keys in error message
   - Verify data structure matches expected format

2. Check API changes:
   - Verify API response structure hasn't changed
   - Check for new required fields
   - Verify authentication tokens are valid

## Related Documentation

- `authentication_critical.md`: Authentication system documentation
- `database_connection_management.md`: Database setup and connection
- `hallmark_automation_spec.md`: API specification

## Early Stopping Mechanism

### How It Works

The extraction system has a **critical safety feature** that stops execution immediately when validation failures are detected:

1. **Validation Failures** → **STOP IMMEDIATELY**
   - Detected when: Empty returnValue, missing orderHeader, data structure invalid
   - Action: Extraction stops on first validation failure
   - Reason: Indicates systemic problem that will affect all subsequent requests
   - Exit Code: 1 (error)
   - Message: Clear CRITICAL error with instructions

2. **Transient Failures** → **STOP AFTER THRESHOLD**
   - Detected when: Network errors, timeouts, temporary API issues
   - Action: Stops after 3 consecutive failures (configurable)
   - Reason: May be temporary, can resume later
   - Exit Code: 1 (error)
   - Message: Warning that extraction stopped early

### Implementation

- `extract_single_order()` returns `(success: bool, is_validation_failure: bool)`
- Validation failures are tracked separately from transient errors
- Main script checks `stopped_early` and `stop_reason` in stats
- Exit code is always 1 when extraction stops early

### Why This Matters

**Without early stopping**: A validation failure on the first order would cause thousands of subsequent orders to fail, wasting hours of processing time.

**With early stopping**: The first validation failure stops immediately, alerting you to fix the issue before wasting time.

## History of Issues

### 2025-01: Empty Order Files Regression
- **Issue**: Files saved with only `order_id` and empty `order_lines`
- **Symptom**: Files in `store_unknown` directory, wrong month, missing all header data
- **Root Cause**: No validation when API returns empty `returnValue` or missing `orderHeader`
- **Fix**: Added validation at multiple levels:
  - `_parse_aura_response`: Check returnValue is not None/empty
  - `_flatten_order_data`: Validate orderHeader exists and is not empty
  - `save_order`: Validate minimum required fields
  - `extract_single_order`: Validate data before saving
  - **Early stopping**: Stop immediately on validation failures
- **Skip-by-default**: Enhanced tracking and reporting of skipped records
- **Lesson**: **Always validate data structure before saving - incomplete data is worse than no data. Stop immediately on validation failures to prevent wasting hours on broken requests. Skip existing records by default to save time and protect data.**

---

**Last Updated**: 2025-01-XX
**Maintainer**: Development Team
**Status**: CRITICAL - Do not modify without thorough testing

