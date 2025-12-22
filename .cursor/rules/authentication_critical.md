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

#### Token Extraction Methods (in order of preference):

1. **`$A?.getContext?.()?.getToken?.()` (Safe Optional Chaining)**
   - Safest method using optional chaining
   - Won't throw if any part of the chain is undefined
   - **This is the preferred method**

2. **`$A.getToken()`**
   - Direct method call
   - Requires `window.$A` and `getToken` function to exist

3. **`$A.getContext().getToken()`**
   - Gets token from context object
   - Requires context object to have `getToken` method

4. **`$A.get("$Storage")`**
   - Retrieves token from Aura storage
   - Looks for token-related keys in storage object

5. **Aura.token property**
   - Direct property access on `window.Aura` or `window.$A`
   - Checks `Aura.token` and `$A.token`

6. **Window Aura objects**
   - Searches various nested locations:
     - `window.$A.clientService.token`
     - `window.$A.services.client.token`
     - `window.aura.token`
     - `window.Aura.initConfig.token`

7. **Storage service**
   - Uses `$A.storageService.getStorage('actions')`
   - Looks for token in storage

8. **Page source regex extraction**
   - Deep scan of HTML page source
   - Multiple regex patterns for tokens in:
     - JSON objects
     - Inline JavaScript
     - Script tags
     - Data attributes
   - Patterns include:
     - JWT tokens: `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`
     - `aura.token` assignments
     - Context objects with tokens
     - Config objects

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

### JavaScript Objects

```javascript
// Primary locations (in order of reliability):
window.$A?.getContext?.()?.getToken?.()  // SAFEST - use optional chaining
window.$A.getToken()
window.$A.getContext().getToken()
window.$A.get("$Storage")
window.Aura.token
window.$A.token
```

### Page Source Patterns

```html
<!-- In script tags -->
<script>
  aura.token = "eyJ...";
  "token": "eyJ...",
  "fwuid": "...",
  "context": {"fwuid": "...", "token": "..."}
</script>

<!-- In data attributes -->
<div data-token="eyJ..."></div>

<!-- In JSON config -->
Aura.initConfig = {"token": "eyJ..."}
```

### Regex Patterns

Common patterns found in page source:

- JWT tokens: `"token"\s*:\s*"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+[^"]*)"`
- Aura token: `"aura\.token"\s*:\s*"([^"]+)"`
- Context object: `"context"\s*:\s*\{[^}]*"token"\s*:\s*"([^"]+)"`
- FWUID: `"fwuid"\s*:\s*"([^"]+)"`

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
  - `_extract_tokens()`: Main extraction coordinator
  - `_extract_tokens_js()`: JavaScript extraction methods
  - `_extract_tokens_regex()`: Regex extraction from page source
  - `_extract_tokens_from_page_source()`: Deep page source scan

- `src/api/client.py`: API client using tokens
  - `HallmarkAPIClient.__init__()`: Initializes with tokens
  - `_execute_request()`: Makes API calls with tokens

- `src/api/request_builder.py`: Builds Aura API requests
  - `_build_request()`: Creates form data with `aura.token` field

### Critical Code Sections

**DO NOT modify without thorough testing:**

1. Token extraction fallback logic (lines ~425-441 in `authenticator.py`)
   - **MUST fail if no token found**
   - **MUST NOT allow empty tokens**

2. API request building (lines ~200-205 in `request_builder.py`)
   - **MUST include `aura.token` field**
   - **MUST NOT be empty string**

3. Error handling in `_execute_request()` (lines ~383-403 in `client.py`)
   - **MUST detect empty responses**
   - **MUST log detailed error information**

## Best Practices

1. **Always use optional chaining** when accessing Aura objects
   ```javascript
   window.$A?.getContext?.()?.getToken?.()
   ```

2. **Log detailed errors** including stack traces
   ```python
   logger.warning(f"Error: {error_msg} (stack: {stack})")
   ```

3. **Test token extraction** after any changes
   - Verify tokens are extracted successfully
   - Verify tokens are not empty
   - Verify API calls work with extracted tokens

4. **Document any changes** to authentication flow
   - Update this file
   - Add comments in code
   - Test thoroughly before committing

## Session Persistence

Sessions are saved to `sessions/hallmark_session.json` to skip MFA on subsequent runs.

**Important:**
- Sessions expire after hours/days (Hallmark-controlled)
- Token extraction still required even with saved session
- Saved session only skips login/MFA, not token extraction

## Troubleshooting

### Token extraction fails

1. Check browser console for JavaScript errors
2. Verify Aura framework is loaded: `window.$A` exists
3. Check page source for token patterns
4. Try manual extraction in browser console:
   ```javascript
   window.$A?.getContext?.()?.getToken?.()
   ```

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

---

**Last Updated**: 2025-01-XX
**Maintainer**: Development Team
**Status**: CRITICAL - Do not modify without thorough testing

