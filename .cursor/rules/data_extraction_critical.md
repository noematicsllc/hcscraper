# Data Extraction System - CRITICAL GUIDELINES

## ⚠️ CRITICAL WARNING

**Breaking data extraction is a CATASTROPHIC FAILURE.** This system is responsible for extracting and storing all order, billing document, and delivery data. Any changes to extraction or storage logic must be thoroughly tested and documented.

## Core Principles

### 1. Skip Existing Records by Default

**CRITICAL SAFETY FEATURE**: By default, the system **skips records that have already been extracted**. This prevents:
- Wasting time re-downloading existing data
- Wasting API resources and rate limits
- Potential data loss if re-extraction fails

**To re-download existing records**, use an update flag.

### 2. Always Validate Before Saving

**Rule**: Never save incomplete or invalid data. Incomplete data is worse than no data.

**Validation Requirements**:
- Validate API response structure before processing
- Validate required fields exist and are not empty
- Validate data completeness (not just IDs and empty arrays)
- Fail fast on validation failures - do not continue processing

### 3. Early Stopping on Validation Failures

**Critical Safety Feature**: The extraction system will STOP IMMEDIATELY on validation failures to prevent wasting hours processing thousands of records that will all fail.

**Failure Types**:
- **Validation Failures**: Stop immediately (indicates systemic problem)
- **Transient Failures**: Stop after consecutive threshold (may be temporary)

### 4. Data Structure Requirements

**Flattened Structure**:
- All data fields must be at the top level (no nested wrappers)
- Use snake_case for all field names
- Preserve all data exactly as received (only convert field names)
- Store complete data in structured format

**Directory Organization**:
- Organize files hierarchically by date and store
- Extract date parts from data for directory structure
- Use canonical store identifiers when available

## Error Handling

### Validation Failures

When validation fails:
1. Log detailed error information (missing fields, available keys, root cause hints)
2. **STOP extraction immediately** - do not continue processing
3. Return clear error messages indicating why extraction cannot proceed

### Transient Failures

For network errors, timeouts, temporary API issues:
- Implement retry logic with exponential backoff
- Stop after consecutive failure threshold
- Allow resumption after fixing issues

## Common Failure Modes

1. **Empty API Response**
   - **Symptom**: API returns empty response
   - **Fix**: Verify authentication, check API request format
   - **Action**: Stop immediately - indicates systemic problem

2. **Missing Required Fields**
   - **Symptom**: Data structure missing expected fields
   - **Fix**: Check API response structure, verify authentication
   - **Action**: Stop immediately - indicates systemic problem

3. **Incomplete Data**
   - **Symptom**: Files saved with only IDs and empty arrays
   - **Fix**: Ensure validation checks for data completeness
   - **Action**: Prevent saving - validation should catch this

## Best Practices

1. **Always validate before saving**
   - Check data structure
   - Check required fields
   - Check data completeness

2. **Log detailed errors**
   - Include entity ID in error messages
   - Include available keys when structure is wrong
   - Include root cause hints

3. **Fail fast**
   - Don't save incomplete data
   - Stop immediately on validation failures
   - Return clear error messages

4. **Test thoroughly**
   - Test with valid data
   - Test with invalid data
   - Test skip behavior
   - Test update behavior

## Testing Strategy

1. **Single Entity Test**: Extract one entity and verify structure
2. **Skip Test**: Verify existing records are skipped
3. **Update Test**: Verify update flag re-downloads existing records
4. **Validation Test**: Verify invalid data is rejected
5. **Failure Test**: Verify extraction stops on validation failures

---

**Status**: CRITICAL - Do not modify without thorough testing
