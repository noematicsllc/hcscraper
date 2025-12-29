# Authentication System - CRITICAL GUIDELINES

## ⚠️ CRITICAL WARNING

**Breaking authentication is a CATASTROPHIC FAILURE.** This system is the foundation of the entire application. Any changes to authentication must be thoroughly tested and documented.

## Core Principles

### 1. Never Allow Empty Tokens

**The Salesforce Aura API REQUIRES a valid `aura.token` field.** Empty tokens cause the API to return empty responses (status 200, empty body), which results in JSON decode errors.

**Rule**: Authentication MUST fail if token extraction fails. Do not proceed with empty tokens.

### 2. Token Extraction Strategy

- **Primary Method**: Extract tokens from browser storage (localStorage/sessionStorage)
- **Why**: This is the only reliable method that works in practice
- **Fallback Methods**: Do not add back removed methods that failed in practice
- **Validation**: Always validate that extracted tokens are non-empty before proceeding

### 3. Session Management

- Sessions should be saved after successful authentication to skip MFA on subsequent runs
- Token extraction is still required even with saved sessions
- Saved sessions only skip login/MFA, not token extraction

## Error Handling

### Critical Errors

If token extraction fails:
1. Log detailed error information (stack traces, available properties, page state)
2. **FAIL authentication** - do not proceed with empty tokens
3. Provide clear error messages indicating why authentication cannot proceed

### Error Logging

All authentication operations should log:
- Method name being tried
- Success/failure status
- Error messages with stack traces
- Available properties when methods fail

## Testing Requirements

Before modifying authentication:
1. Test token extraction with real credentials
2. Verify tokens are extracted successfully and are non-empty
3. Verify API calls work with extracted tokens
4. Test both full authentication and saved session flows

## Common Failure Modes

1. **Empty token fallback**
   - **Symptom**: API returns status 200 with empty body
   - **Fix**: Ensure token extraction succeeds, do not allow empty tokens

2. **Session expired**
   - **Symptom**: 401/403 responses from API
   - **Fix**: Re-authenticate, refresh session

## Best Practices

1. **Only use proven extraction methods** - Do not add back methods that have been removed due to failures
2. **Log detailed errors** including stack traces
3. **Test thoroughly** after any changes
4. **Document changes** to authentication flow
5. **Fail fast** - Do not allow authentication to proceed with invalid tokens

---

**Status**: CRITICAL - Do not modify without thorough testing
