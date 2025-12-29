# Authentication System - CRITICAL DOCUMENTATION

## ⚠️ CRITICAL WARNING

**Breaking authentication is a CATASTROPHIC FAILURE.** This system is the foundation of the entire application. Any changes to authentication must be thoroughly tested and documented.

## Overview

The Hallmark Connect scraper uses Salesforce Aura framework authentication with MFA. Authentication involves:
1. Playwright browser automation for login + MFA
2. Extraction of Aura framework tokens from the authenticated session
3. Transfer of session cookies and tokens to requests library for API calls

## Authentication Flow

### Step 1: Browser-Based Login (Playwright)

1. Navigate to `https://services.hallmarkconnect.com`
2. Click "Retailer Login" button
3. Redirect to PingOne login page
4. Enter username/password
5. Handle MFA (via n8n webhook or manual input)
6. Wait for redirect back to Hallmark Connect
7. Extract session tokens from URL and cookies

### Step 2: Aura Token Extraction (CRITICAL)

**The Salesforce Aura API REQUIRES a valid `aura.token` field.** Empty tokens cause the API to return empty responses (status 200, empty body), which results in JSON decode errors.

#### Token Extraction Methods:

**ONLY WORKING METHOD:**

1. **localStorage/sessionStorage extraction** ⭐ **ONLY RELIABLE METHOD**
   - **This is the ONLY method that works in practice**
   - Token is typically found in: `localStorage['$AuraClientService.token$siteforce:communityApp']`
   - Checks known working key patterns first, then broader search
   - Fast, reliable, and doesn't depend on Aura framework initialization
   - **All JavaScript-based methods have been removed** - they fail in practice
   - **Regex/page source extraction methods have been removed** - they were never reached in logs

**SUPPLEMENTARY METHODS (for context, not token):**

2. **URL parameter extraction** (for session ID only)
   - Extracts Salesforce session ID (`sid`) and org ID (`oid`) from URL parameters
   - Does NOT extract Aura token - only provides session context
   - Used to supplement storage-extracted tokens with session metadata

3. **FWUID extraction from page** (for context only)
   - Extracts framework unique identifier via regex from page source
   - Used for debugging and context, not required for authentication

#### Required Tokens

- **`aura.token`**: CSRF token (REQUIRED - cannot be empty)
- **`fwuid`**: Framework unique identifier (helpful but not always required)
- **`aura.context`**: Encoded context object (helpful but can be built if missing)

### Step 3: Session Transfer

1. Extract cookies from Playwright browser context
2. Create `requests.Session` with cookies
3. Initialize `HallmarkAPIClient` with:
   - Session (with cookies)
   - Aura token (REQUIRED - cannot be empty)
   - Aura context (optional - can be built if missing)
   - FWUID (optional)

## Common Token Locations

### Storage (ONLY WORKING METHOD)

```javascript
// ONLY RELIABLE METHOD - token found in localStorage
localStorage.getItem('$AuraClientService.token$siteforce:communityApp')

// Also checks these patterns:
// - '$AuraClientService.token'
// - 'aura.token'
// - 'auraToken'
// - 'sfdc.auraToken'
// - Any key containing 'token' and ('aura' or 'client')

// Checks both localStorage and sessionStorage
sessionStorage.getItem('$AuraClientService.token$siteforce:communityApp')
```

### JavaScript Objects (REMOVED - DO NOT USE)

**All JavaScript-based extraction methods have been removed** because they fail in practice:
- `window.$A?.getContext?.()?.getToken?.()` - fails
- `window.$A.getToken()` - fails
- `window.$A.getContext().getToken()` - fails
- `window.$A.get("$Storage")` - fails
- `window.Aura.token` - fails
- `window.$A.token` - fails

**These methods were removed based on authentication logs showing consistent failures.**

### Page Source Patterns (REMOVED - DO NOT USE)

**Regex extraction from page source has been removed** because:
- Storage extraction always succeeds, so regex methods are never reached
- Regex extraction was never used in successful authentication logs
- Storage extraction is faster and more reliable

### URL Parameters (For Session Context Only)

```javascript
// Extract from URL query parameters (NOT the Aura token):
// ?sid=... (Salesforce session ID)
// ?oid=... (Organization ID)
// These are used for session context, not authentication
```

## Error Handling

### Critical Errors

**DO NOT allow empty tokens.** If token extraction fails:

1. Log detailed error information including:
   - JavaScript error messages
   - Stack traces
   - Available Aura properties
   - Page source snippets (first 500 chars)

2. **FAIL authentication** - do not proceed with empty tokens

3. Error message should clearly indicate:
   ```
   ✗ CRITICAL: Cannot extract Aura token but have session ID.
   The API requires a valid aura.token - empty tokens will cause API failures.
   Authentication cannot proceed without a valid token.
   ```

### Error Logging

All extraction methods should log:
- Method name being tried
- Success/failure status
- Error messages with stack traces
- Available properties when methods fail

Example logging:
```python
logger.info(f"  Trying Aura extraction method: {method_name}")
logger.warning(f"  Method {method_name} error: {error_msg} (stack: {stack})")
logger.info(f"  ✓ Successfully extracted tokens via: {method_name}")
```

## Testing Authentication

### Manual Testing

1. Run authentication:
   ```bash
   python main.py --orders-csv search_results/orders_202509.csv
   ```

2. Check logs for:
   - Successful token extraction
   - Token value (first 50 chars logged)
   - No empty token warnings

3. Verify API calls work:
   - Order extraction should succeed
   - No "Invalid JSON in response" errors
   - No empty response body errors

### Common Failure Modes

1. **Empty token fallback**
   - **Symptom**: API returns status 200 with empty body
   - **Error**: "Invalid JSON in response: Expecting value: line 1 column 1 (char 0)"
   - **Fix**: Ensure token extraction succeeds, do not allow empty tokens

2. **Token extraction timing**
   - **Symptom**: `$A` not defined, all methods fail
   - **Error**: "All JavaScript Aura extraction methods failed"
   - **Fix**: Wait for Aura framework to initialize before extraction

3. **Session expired**
   - **Symptom**: 401/403 responses from API
   - **Error**: "Session expired" warnings
   - **Fix**: Re-authenticate, refresh session

## Code Locations

### Key Files

- `src/auth/authenticator.py`: Main authentication logic
  - `_extract_tokens()`: Main extraction coordinator (only uses storage method)
  - `_extract_tokens_from_storage()`: **ONLY WORKING METHOD** - localStorage/sessionStorage extraction
  - `_extract_tokens_from_url()`: Extracts session ID from URL (supplementary, not for token)
  - `_extract_fwuid_from_page()`: Extracts FWUID via regex (for context only)
  - **REMOVED**: All JavaScript-based extraction methods (they fail in practice)
  - **REMOVED**: Regex/page source extraction methods (never reached in logs)

- `src/api/client.py`: API client using tokens
  - `HallmarkAPIClient.__init__()`: Initializes with tokens
  - `_execute_request()`: Makes API calls with tokens

- `src/api/request_builder.py`: Builds Aura API requests
  - `_build_request()`: Creates form data with `aura.token` field

### Critical Code Sections

**DO NOT modify without thorough testing:**

1. Token extraction logic (`_extract_tokens()` in `authenticator.py`)
   - **ONLY uses storage extraction method** - all other methods removed
   - **MUST fail if storage extraction fails** - no fallback to empty tokens
   - **MUST NOT allow empty tokens** - authentication fails if token not found

2. Storage extraction (`_extract_tokens_from_storage()` in `authenticator.py`)
   - **ONLY RELIABLE METHOD** - checks localStorage/sessionStorage
   - Checks known working key patterns first, then broader search
   - **MUST return None if no token found** - triggers authentication failure

3. API request building (lines ~200-205 in `request_builder.py`)
   - **MUST include `aura.token` field**
   - **MUST NOT be empty string**

4. Error handling in `_execute_request()` (lines ~383-403 in `client.py`)
   - **MUST detect empty responses**
   - **MUST log detailed error information**

## Best Practices

1. **ONLY use storage extraction** - all other methods have been removed
   ```javascript
   // ONLY WORKING METHOD:
   localStorage.getItem('$AuraClientService.token$siteforce:communityApp')
   ```

2. **Log detailed errors** including stack traces
   ```python
   logger.error(f"Error: {error_msg}", exc_info=True)
   ```

3. **Test token extraction** after any changes
   - Verify tokens are extracted successfully from storage
   - Verify tokens are not empty
   - Verify API calls work with extracted tokens

4. **Document any changes** to authentication flow
   - Update this file
   - Add comments in code
   - Test thoroughly before committing

5. **DO NOT add back removed methods** - JavaScript and regex extraction methods were removed because they fail in practice

## Session Persistence

Sessions are saved to `sessions/hallmark_session.json` to skip MFA on subsequent runs.

**Important:**
- Sessions expire after hours/days (Hallmark-controlled)
- Token extraction still required even with saved session
- Saved session only skips login/MFA, not token extraction

## Troubleshooting

### Token extraction fails

1. Check browser storage for token:
   ```javascript
   // In browser console:
   localStorage.getItem('$AuraClientService.token$siteforce:communityApp')
   // Or check all localStorage keys:
   Object.keys(localStorage).filter(k => k.includes('token') && k.includes('aura'))
   ```

2. Verify you're on the authenticated page (`/s/`) after login
3. Check authentication logs for storage extraction details
4. Verify session cookies are present (check browser DevTools)
5. **DO NOT try JavaScript methods** - they have been removed because they fail

### API returns empty responses

1. Verify token is not empty
2. Check token format (should be JWT-like string)
3. Verify session cookies are valid
4. Check API request includes `aura.token` field

### Authentication works but API fails

1. Verify token is passed to API client
2. Check request builder includes token in form data
3. Verify session cookies are transferred correctly
4. Check for session expiration (401/403 responses)

## Related Documentation

- `CLAUDE.md`: General project documentation
- `hallmark_automation_spec.md`: API specification
- `.cursor/rules/database_connection_management.md`: Database setup

## History of Issues

### 2025-01: Empty Token Regression
- **Issue**: Code allowed empty tokens as fallback
- **Symptom**: API returned empty responses (status 200, empty body)
- **Root Cause**: Assumed session cookies alone sufficient, but API requires `aura.token`
- **Fix**: Removed empty token fallback, improved extraction methods, added comprehensive error logging
- **Lesson**: **Never allow empty tokens - API requires valid token**

### 2025-01: Method Cleanup - Removed Failed Extraction Methods
- **Issue**: Multiple token extraction methods existed but only storage extraction worked
- **Symptom**: JavaScript-based methods consistently failed in authentication logs
- **Root Cause**: JavaScript methods (`window.$A.getToken()`, etc.) fail in practice; regex methods never reached
- **Fix**: Removed all JavaScript-based extraction methods and regex/page source extraction methods
- **Current State**: Only `_extract_tokens_from_storage()` remains - the ONLY reliable method
- **Lesson**: **Remove code that doesn't work - don't keep fallbacks that never succeed**

---

**Last Updated**: 2025-01-XX
**Maintainer**: Development Team
**Status**: CRITICAL - Do not modify without thorough testing

