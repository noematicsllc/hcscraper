# Order Structure Validation

This document validates that the current extraction code can perfectly recreate existing order JSON files.

## Existing Order Structure Analysis

Based on `data/2025/09/store_9/order_3069090941.json`:

### Top-Level Fields (19 fields)
1. `order_id` - string
2. `customer_id` - integer
3. `store_name` - string (canonical name from stores table)
4. `ship_to_location` - string
5. `season_description` - string
6. `po_number` - string (can be empty)
7. `order_reason` - string
8. `order_source` - string
9. `planogram_description` - string (can be empty)
10. `delivery_id` - string (comma-separated)
11. `billing_document_number` - string (comma-separated)
12. `order_status` - string
13. `order_total` - string (with trailing space)
14. `order_creation_date` - string (MM/DD/YYYY format)
15. `actual_delivery_date` - string (MM/DD/YYYY format)
16. `requested_delivery_date` - string (MM/DD/YYYY format)
17. `comment_description` - string
18. `source_system_id` - string
19. `order_lines` - array of objects

### Order Lines Structure
Each line item has:
- `line_item_number` - integer
- `location_id` - string
- `material_number` - string
- `stock_number` - string
- `upc` - string
- `material_description` - string
- `wholesales` - integer
- `retailsin1_wholesale` - integer

## Current Code Structure

### `_flatten_order_data()` in `src/storage/json_writer.py`

**Process:**
1. Validates `order_data` has `orderHeader` (required)
2. Extracts `order_id` (from parameter)
3. Flattens all `orderHeader` fields to top level with snake_case conversion
4. Converts `orderLines` to `order_lines` with snake_case keys

**Key Points:**
- All `orderHeader` fields are preserved and converted to snake_case
- All `orderLines` items are preserved and converted to snake_case
- No data transformation (values preserved exactly as received)
- `store_name` is looked up from database if available (canonical name)

## Validation Checklist

✅ **Field Preservation**: All fields from `orderHeader` are extracted
✅ **Snake Case Conversion**: All camelCase keys converted to snake_case
✅ **Order Lines**: All line items preserved with snake_case keys
✅ **Data Types**: Values preserved exactly (strings, integers, etc.)
✅ **Empty Values**: Empty strings and nulls preserved
✅ **Comma-Separated Values**: Preserved as strings (e.g., `delivery_id`, `billing_document_number`)

## Potential Issues to Watch For

1. **Missing Fields**: If API response structure changes, new fields might be missing
2. **Field Name Changes**: If API changes field names, snake_case conversion might produce different keys
3. **Store Name**: Database lookup might return different name than original (but original preserved in raw_data if using database)
4. **Date Format**: Dates should be preserved exactly as received from API

## Testing Recommendation

Before running large extractions:
1. Extract a single known order with `--update` flag
2. Compare the new file with the existing file
3. Verify all fields match exactly
4. Check that no fields are missing or added unexpectedly

