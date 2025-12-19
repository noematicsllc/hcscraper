# Hallmark Connect Scraper - Claude Code Reference

## Project Purpose

Automated extraction system for Hallmark Connect order/sales data from 39 Banner's Hallmark stores. Enables operational independence by extracting historical sales data without relying on Hallmark's portal limitations. Uses Salesforce Aura framework API endpoints with Playwright for MFA authentication + requests library for authenticated API calls.

---

## Tech Stack

- **Python**: 3.9+ (project uses 3.13)
- **Environment**: `uv` for dependency management
- **Core Libraries**:
  - `playwright` - Browser automation for login + MFA
  - `requests` - HTTP client for authenticated API calls
  - `python-dotenv` - Environment variable management

### Target System: Salesforce Aura Framework
- **Endpoint**: `POST https://services.hallmarkconnect.com/s/sfsites/aura`
- **Required Tokens**: `aura.token`, `fwuid`, `aura.context`
- **Authentication**: MFA required, extract session tokens from JavaScript

---

## Critical Patterns

### 1. Rate Limiting (MANDATORY)
```python
time.sleep(2.5)  # 2-3 seconds between ALL requests
# Conservative approach to avoid IP blocking
```

### 2. Session Token Extraction
After Playwright login, extract tokens from browser JavaScript:
```javascript
if (window.$A && window.$A.getToken) {
    return {
        token: window.$A.getToken(),
        context: window.$A.getContext().encodeForServer(),
        fwuid: window.$A.getContext().fwuid
    };
}
```

Fallback regex patterns if JS fails:
```python
token_pattern = r'"aura\.token":"([^"]+)"'
fwuid_pattern = r'"fwuid":"([^"]+)"'
```

### 3. Session Persistence (IMPORTANT!)
**Save session after first login to skip MFA on subsequent runs:**
```python
# First run: Full authentication + save session
authenticator.authenticate(save_session=True)
# → Saves to hallmark_session.json

# Subsequent runs: Load saved session (NO MFA!)
success = authenticator.authenticate_with_saved_session()
if not success:
    # Session expired, do full auth again
    authenticator.authenticate(save_session=True)
```

**Benefits:**
- ✅ Skip login/MFA on every run after the first
- ✅ Session valid for hours (until Hallmark expires it)
- ✅ Dramatically faster for batch processing
- ⚠️ **NEVER commit** `hallmark_session.json` (in .gitignore)

### 4. Aura API Request Structure
```python
# URL params
params = {
    'r': 81,  # Request number
    'aura.ApexAction.execute': 1
}

# Form data (application/x-www-form-urlencoded)
payload = {
    'message': json.dumps({
        'actions': [{
            'id': '761;a',
            'descriptor': 'aura://ApexActionController/ACTION$execute',
            'params': {
                'namespace': '',
                'classname': 'Portal_OrderDetailController',
                'method': 'getOrderDetailSAPSearchResult',
                'params': {
                    'orderId': order_id,
                    'pageSize': -1,
                    'pageNumber': -1,
                    # ... other params
                }
            }
        }]
    }),
    'aura.context': aura_context_json,
    'aura.pageURI': f'/s/orderdetail?orderId={order_id}',
    'aura.token': aura_token
}

# Required headers
headers = {
    'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
    'Origin': 'https://services.hallmarkconnect.com',
    'Referer': f'https://services.hallmarkconnect.com/s/orderdetail?orderId={order_id}',
}
```

### 4. Error Handling
- **Retry Logic**: 3 attempts with exponential backoff (2, 4, 8 seconds)
- **Retry on**: 429, 500, 502, 503, 504
- **Auth Expiration**: Re-authenticate if 401/403
- **Always log**: Request details, response status, error messages

---

## File Structure

```
hcscraper/
├── .env              # Credentials (NEVER commit!)
├── .env.example      # Template for credentials
├── main.py           # Entry point
├── src/
│   ├── auth/         # Playwright authentication, MFA handling
│   ├── api/          # API client, Aura request builders
│   ├── extractors/   # Order extraction logic
│   ├── storage/      # JSON/CSV writers
│   └── utils/        # Config, logging
├── tests/            # Unit and integration tests
└── data/             # Output directory (gitignored)
```

---

## Commands

### Setup
```bash
uv sync                    # Install dependencies
playwright install chromium  # Install browser for Playwright
cp .env.example .env       # Create config file
# Edit .env with credentials
```

### Development
```bash
# Test authentication
python -m src.auth.test_auth

# Single order test
python main.py --order-id 3076428648 --output ./test_data

# Batch processing
python main.py --orders orders.txt --output ./data

# Resume interrupted run
python main.py --resume checkpoint.json
```

### Testing
```bash
pytest tests/              # Run all tests
pytest tests/test_auth.py  # Test authentication only
```

---

## Environment Variables

Required in `.env`:
```bash
# Credentials (NEVER commit these)
HALLMARK_USERNAME=your_username
HALLMARK_PASSWORD=your_password

# Optional MFA automation
N8N_WEBHOOK_URL=https://your-webhook.com/mfa
MFA_METHOD=manual  # or 'webhook'

# Configuration
BASE_URL=https://services.hallmarkconnect.com
OUTPUT_DIRECTORY=./data
LOG_LEVEL=INFO
RATE_LIMIT_SECONDS=2.5
MAX_RETRIES=3
HEADLESS_MODE=false
```

---

## Things to AVOID

### Critical Errors
- **NEVER** hardcode credentials in code
- **NEVER** skip error handling on API calls
- **NEVER** rush rate limits (minimum 2 seconds between requests)
- **NEVER** commit `.env` files (must be in `.gitignore`)

### Implementation Errors
- Don't skip session token validation before API calls
- Don't process requests in parallel (sequential only for rate limiting)
- Don't ignore 429 rate limit responses (wait and retry)
- Don't assume tokens are valid forever (check for 401/403)
- Don't skip logging API calls (you'll need it for debugging)

### Security
- Don't log full credentials or tokens in non-debug mode
- Don't expose API responses in public logs (business-sensitive)

---

## Testing Approach

### Phase 1: Single Order (Start Here)
1. Authenticate with Playwright + MFA
2. Extract tokens successfully
3. Make ONE API call for ONE order ID
4. Validate response structure
5. Save to JSON file

**Success criteria**: One order successfully downloaded and saved

### Phase 2: Small Batch (5-10 orders)
1. Process 5-10 orders sequentially
2. Verify rate limiting is working (2-3 sec delays)
3. Check error handling with invalid order ID
4. Validate JSON/CSV output format

**Success criteria**: All valid orders downloaded, errors handled gracefully

### Phase 3: Resume Capability
1. Start batch processing
2. Interrupt mid-run (Ctrl+C)
3. Resume from checkpoint
4. Verify no duplicate downloads

**Success criteria**: Resume picks up where it left off

### Phase 4: Full Batch
1. Process 100+ orders
2. Monitor for rate limiting issues
3. Verify no authentication timeouts
4. Check summary report accuracy

**Success criteria**: Reliable processing of large batches

### Manual Testing Checklist
- [ ] Auth with MFA works (both manual and webhook)
- [ ] Token extraction successful
- [ ] Single order download succeeds
- [ ] Rate limiting enforced (measure delays)
- [ ] Error handling for invalid order IDs
- [ ] JSON output has correct structure
- [ ] CSV output is properly formatted
- [ ] Resume from checkpoint works
- [ ] Summary report is accurate

---

## Quick Reference

### Response Structure
```json
{
    "actions": [{
        "id": "761;a",
        "state": "SUCCESS",  // or "ERROR"
        "returnValue": {
            // Order data here
        }
    }]
}
```

### File Naming Convention
```
data/
  order_3076428648_20251218_103015.json
  order_3076428648_20251218_103015.csv
  checkpoint.json
  summary.json
```

### Common Issues
- **401/403**: Token expired → Re-authenticate
- **429**: Rate limited → Increase delay, wait longer
- **Timeout**: Network issue → Retry with backoff
- **MFA fails**: Check webhook URL or use manual input
- **Can't extract tokens**: Check Salesforce page loaded fully

---

## Development Notes

- Start with authentication module first (everything depends on it)
- Test incrementally (don't build everything at once)
- Log everything in DEBUG mode during development
- Use small test batches (5-10 orders) before going large
- Handle Ctrl+C gracefully (save progress on interrupt)
