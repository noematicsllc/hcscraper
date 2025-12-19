# Hallmark Connect Data Extraction Automation - Implementation Specification

## Project Overview

**Objective**: Build an automated system to extract historical sales and order data from Hallmark Connect (services.hallmarkconnect.com) for 39 retail store locations operated by Banner's Hallmark.

**Business Context**:
- Banner's Hallmark operates 39 retail store locations
- Need complete historical data (3-6 months) for operational analysis and business intelligence
- Manual download of hundreds of individual reports is not feasible
- Currently using browser automation scripts, but need a more robust solution

**Technical Context**:
- Hallmark Connect is built on Salesforce Commerce Cloud with the Aura framework
- System requires Multi-Factor Authentication (MFA)
- Data is accessed through POST requests to Salesforce Aura API endpoints
- All data pertains to Banner's Hallmark's own 39 stores (authorized access)

---

## System Architecture

### Components

1. **Authentication Module**
   - Playwright-based browser automation for login
   - MFA code retrieval system (n8n webhook or manual input)
   - Session token management (aura.token, aura.context, fwuid)

2. **API Client Module**
   - HTTP session management with proper headers/cookies
   - Salesforce Aura framework API wrapper
   - Request construction and response parsing

3. **Data Extraction Module**
   - Order detail retrieval
   - Report generation and download
   - Batch processing with rate limiting

4. **Storage Module**
   - JSON file storage
   - CSV export capabilities
   - Summary/logging system

---

## Technical Requirements

### Environment Setup

**Python Version**: 3.9+

**Required Dependencies**:
```
requests>=2.31.0
playwright>=1.49.0
python-dotenv>=1.0.0
```

**Optional Dependencies**:
```
pandas>=2.1.0  # For CSV export
openpyxl>=3.1.0  # For Excel export
```

**Playwright Browsers**: Install with `playwright install chromium`

### Environment Variables

Create a `.env` file with:
```env
HALLMARK_USERNAME=your_username
HALLMARK_PASSWORD=your_password
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/mfa
BASE_URL=https://services.hallmarkconnect.com
OUTPUT_DIRECTORY=./hallmark_data
LOG_LEVEL=INFO
```

---

## API Documentation

### Salesforce Aura Framework Structure

#### Authentication Flow

1. **Initial Login**
   - URL: `https://services.hallmarkconnect.com/s/login/`
   - Method: Browser-based (Playwright required)
   - Fields:
     - `username`: User's email/username
     - `password`: User's password
   - MFA: Required after password entry

2. **Token Extraction**
   - After successful login, extract from JavaScript:
     - `aura.token`: Session authentication token
     - `fwuid`: Framework unique identifier
     - `aura.context`: Application context object

3. **Session Cookies**
   - Must preserve all cookies from Playwright session
   - Transfer to requests.Session object

#### API Request Structure

**Endpoint**: `https://services.hallmarkconnect.com/s/sfsites/aura`

**Method**: POST

**URL Parameters**:
```
r=81  # Request number (can increment)
aura.ApexAction.execute=1
```

**Content-Type**: `application/x-www-form-urlencoded;charset=UTF-8`

**Form Data Structure**:
```python
{
    "message": JSON string of action payload,
    "aura.context": JSON string of context object,
    "aura.pageURI": Current page URI,
    "aura.token": Authentication token
}
```

#### Action Payload Structure

**Example: Get Order Detail**
```json
{
    "actions": [{
        "id": "761;a",
        "descriptor": "aura://ApexActionController/ACTION$execute",
        "callingDescriptor": "UNKNOWN",
        "params": {
            "namespace": "",
            "classname": "Portal_OrderDetailController",
            "method": "getOrderDetailSAPSearchResult",
            "params": {
                "pageSize": -1,
                "pageNumber": -1,
                "searchSort": "[{\"columnName\":\"materialNumber\",\"sortorder\":\"asc\",\"priority\":1}]",
                "orderId": "3076428648",
                "cacheable": false,
                "isContinuation": false
            }
        }
    }]
}
```

#### Context Object Structure

```json
{
    "mode": "PROD",
    "fwuid": "NDdEUGVLTDZ2bz26ZUk5fekEtcFVvdzFLcUUxeUY3ZVB6dE9hR0VheDVpb2cxMy4zMzU1NDQz",
    "app": "siteforce:communityApp",
    "loaded": {
        "APPLICATION@markup://siteforce:communityApp": "1419_b1bLMAu5pI9zwW1jkVMf-w"
    },
    "dn": [],
    "globals": {},
    "uad": true
}
```

#### Response Structure

**Success Response**:
```json
{
    "actions": [{
        "id": "761;a",
        "state": "SUCCESS",
        "returnValue": {
            // Actual data here
        }
    }],
    "context": { ... },
    "perfSummary": { ... }
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

#### Required Request Headers

```python
{
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    "Host": "services.hallmarkconnect.com",
    "Origin": "https://services.hallmarkconnect.com",
    "Referer": "https://services.hallmarkconnect.com/s/orderdetail?orderId={ORDER_ID}",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0"
}
```

---

## Implementation Requirements

### Core Features

#### 1. Authentication System

**Requirements**:
- Use Playwright with Chromium browser
- Support both headless and headed modes (configurable)
- Handle MFA via two methods:
  - **Method A**: n8n webhook integration
  - **Method B**: Manual console input (fallback)
- Extract and store session tokens
- Transfer session from Playwright to requests library
- Validate authentication success before proceeding

**Playwright Selectors** (adjust as needed):
```python
USERNAME_FIELD = "input[name='username']"
PASSWORD_FIELD = "input[name='password']"
LOGIN_BUTTON = "button[type='submit']"
MFA_FIELD = "input[name='code']"  # May need adjustment
MFA_SUBMIT = "button[type='submit']"
```

**Token Extraction JavaScript**:
```javascript
if (window.$A && window.$A.getToken) {
    return {
        token: window.$A.getToken(),
        context: window.$A.getContext() ? 
            window.$A.getContext().encodeForServer() : null,
        fwuid: window.$A.getContext() ? 
            window.$A.getContext().fwuid : null
    };
}
return null;
```

**Fallback Regex Patterns**:
```python
token_pattern = r'"aura\.token":"([^"]+)"'
fwuid_pattern = r'"fwuid":"([^"]+)"'
```

#### 2. API Client

**Requirements**:
- Maintain requests.Session with cookies from authentication
- Build properly formatted Aura API requests
- Handle response parsing and error checking
- Implement retry logic (3 attempts with exponential backoff)
- Rate limiting (2-3 second delay between requests)
- Log all API calls and responses

**Error Handling**:
- HTTP errors (4xx, 5xx)
- Authentication expiration (token timeout)
- Network timeouts
- Invalid responses

**Retry Strategy**:
```python
max_retries = 3
backoff_factor = 2  # 2, 4, 8 seconds
retry_on_status = [429, 500, 502, 503, 504]
```

#### 3. Data Extraction

**Order Detail Extraction**:
- Input: List of order IDs
- Output: JSON files per order + consolidated CSV
- Progress tracking with ETA
- Resume capability (skip already downloaded)

**Required Fields to Extract** (from returnValue):
- Order ID
- Order Date
- Store Number/Name
- Line Items (materials, quantities, prices)
- Totals
- Status
- Any available metadata

**File Naming Convention**:
```
order_{ORDER_ID}_{TIMESTAMP}.json
order_{ORDER_ID}_{TIMESTAMP}.csv
```

#### 4. Batch Processing

**Requirements**:
- Process orders sequentially (no parallel requests to avoid rate limiting)
- 2-3 second delay between requests
- Save progress after each successful download
- Generate summary report at completion
- Handle interruptions gracefully (SIGINT/SIGTERM)

**Progress Tracking**:
```python
{
    "total_orders": 1000,
    "completed": 150,
    "failed": 5,
    "remaining": 845,
    "start_time": "2025-12-18T10:00:00",
    "estimated_completion": "2025-12-18T12:30:00"
}
```

---

## Data Types and Schemas

### Order Detail Response Schema

Based on observed API responses, the order detail contains:

```typescript
interface OrderDetail {
    orderId: string;
    orderDate: string;
    storeNumber: string;
    storeName: string;
    lineItems: Array<{
        materialNumber: string;
        materialDescription: string;
        locationID: string;
        quantity: number;
        unitPrice: number;
        totalPrice: number;
        // Additional fields as available
    }>;
    totalAmount: number;
    status: string;
    // Additional metadata fields
}
```

### Output File Formats

#### JSON Format
```json
{
    "order_id": "3076428648",
    "extracted_at": "2025-12-18T10:30:00",
    "data": {
        // Raw API response
    }
}
```

#### CSV Format
Flattened structure with one row per line item:
```csv
order_id,order_date,store_number,material_number,description,quantity,price,total
3076428648,2024-11-15,101,MAT001,Product A,5,10.00,50.00
```

---

## Error Handling and Logging

### Logging Requirements

**Log Levels**:
- `DEBUG`: Detailed request/response data
- `INFO`: Progress updates, successful operations
- `WARNING`: Retryable errors, missing data
- `ERROR`: Failed operations, authentication issues
- `CRITICAL`: System failures

**Log Format**:
```
[2025-12-18 10:30:15] [INFO] [OrderExtractor] Processing order 3076428648 (150/1000)
[2025-12-18 10:30:17] [DEBUG] [APIClient] POST /s/sfsites/aura?r=81 -> 200 (2.13 KB)
[2025-12-18 10:30:17] [INFO] [OrderExtractor] Successfully saved order 3076428648
```

**Log Files**:
- `hallmark_automation.log`: Main application log
- `api_requests.log`: Detailed API request/response log
- `errors.log`: Error-only log for debugging

### Error Recovery

**Authentication Failure**:
1. Log error details
2. Attempt re-authentication (max 3 times)
3. If all attempts fail, exit with clear error message

**Network Timeout**:
1. Log timeout
2. Wait 5 seconds
3. Retry request (up to 3 times)
4. If all retries fail, mark order as failed and continue

**Invalid Response**:
1. Log response content
2. Save raw response to file for debugging
3. Mark order as failed
4. Continue to next order

**Rate Limiting (429)**:
1. Extract retry-after header if present
2. Wait specified time (or 60 seconds default)
3. Retry request

---

## Security and Compliance Considerations

### Credentials Management

**Requirements**:
- NEVER hardcode credentials
- Use environment variables or .env file
- Add .env to .gitignore
- Consider using keyring/keychain for production

**Example .env.example**:
```env
# Hallmark Connect Credentials
HALLMARK_USERNAME=your_username_here
HALLMARK_PASSWORD=your_password_here

# MFA Configuration
N8N_WEBHOOK_URL=https://your-webhook-url.com/mfa
MFA_METHOD=webhook  # or 'manual'

# Application Configuration
BASE_URL=https://services.hallmarkconnect.com
OUTPUT_DIRECTORY=./hallmark_data
LOG_LEVEL=INFO
HEADLESS_MODE=false
RATE_LIMIT_SECONDS=2
MAX_RETRIES=3
```

### Data Handling

**Sensitive Data**:
- Order data contains business-sensitive information
- Store locally only, do not transmit to third parties
- Implement file permissions (chmod 600 for data files)
- Consider encryption at rest for production use

### Legal Compliance

**Authorization**:
- User has legitimate access to Hallmark Connect
- Data pertains to user's own 39 stores
- Access is for business necessity (operational independence)

**Risk Mitigation**:
- Conservative rate limiting (2-3 seconds between requests)
- Run during off-peak hours
- Monitor for any blocking/warnings from system
- Be prepared to stop immediately if contacted

---

## Testing Requirements

### Unit Tests

Test coverage for:
1. Authentication module (mocked Playwright)
2. API client request building
3. Response parsing
4. Error handling
5. File I/O operations

### Integration Tests

1. **Authentication Flow**:
   - Successful login
   - MFA handling
   - Token extraction
   - Session transfer

2. **API Calls**:
   - Single order retrieval
   - Error responses
   - Retry logic
   - Rate limiting

3. **Data Processing**:
   - JSON parsing
   - CSV export
   - File writing

### Manual Testing Checklist

- [ ] Authentication with MFA works
- [ ] Single order download succeeds
- [ ] Batch download of 5 orders completes
- [ ] Resume functionality works after interruption
- [ ] Error handling for invalid order ID
- [ ] Rate limiting delays are enforced
- [ ] Log files are created correctly
- [ ] Output files have correct format
- [ ] Summary report is accurate

---

## Implementation Phases

### Phase 1: Setup and Authentication (2-3 hours)
- [ ] Set up project structure
- [ ] Install dependencies
- [ ] Implement authentication module
- [ ] Test login with MFA
- [ ] Verify token extraction

**Deliverable**: Working authentication that returns valid tokens

### Phase 2: API Client (2-3 hours)
- [ ] Implement API client class
- [ ] Build request formatting
- [ ] Implement response parsing
- [ ] Add error handling
- [ ] Test with single order ID

**Deliverable**: Successfully retrieve one order's data

### Phase 3: Data Extraction (2-3 hours)
- [ ] Implement batch processing
- [ ] Add progress tracking
- [ ] Implement file storage (JSON/CSV)
- [ ] Add resume capability
- [ ] Test with 5-10 orders

**Deliverable**: Batch download of multiple orders

### Phase 4: Polish and Production (1-2 hours)
- [ ] Add comprehensive logging
- [ ] Implement summary reporting
- [ ] Add command-line interface
- [ ] Create documentation
- [ ] Final testing with larger batch

**Deliverable**: Production-ready script with documentation

---

## Code Structure

### Recommended Project Structure

```
hallmark-automation/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── setup.py
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── authenticator.py
│   │   └── mfa_handler.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── request_builder.py
│   ├── extractors/
│   │   ├── __init__.py
│   │   └── order_extractor.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── json_writer.py
│   │   └── csv_writer.py
│   └── utils/
│       ├── __init__.py
│       ├── config.py
│       └── logger.py
├── tests/
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_api.py
│   └── test_extractors.py
└── data/
    └── .gitkeep
```

### Class Structure

#### HallmarkAuthenticator
```python
class HallmarkAuthenticator:
    def __init__(self, username: str, password: str, mfa_handler: MFAHandler)
    def authenticate(self) -> bool
    def get_session(self) -> requests.Session
    def get_tokens(self) -> Dict[str, str]
    def is_authenticated(self) -> bool
```

#### MFAHandler (Abstract)
```python
class MFAHandler(ABC):
    @abstractmethod
    def get_mfa_code(self) -> str

class WebhookMFAHandler(MFAHandler):
    def __init__(self, webhook_url: str)
    def get_mfa_code(self) -> str

class ConsoleMFAHandler(MFAHandler):
    def get_mfa_code(self) -> str
```

#### HallmarkAPIClient
```python
class HallmarkAPIClient:
    def __init__(self, session: requests.Session, tokens: Dict[str, str])
    def get_order_detail(self, order_id: str) -> Optional[Dict]
    def build_request(self, action: str, params: Dict) -> requests.Request
    def parse_response(self, response: requests.Response) -> Dict
```

#### OrderExtractor
```python
class OrderExtractor:
    def __init__(self, api_client: HallmarkAPIClient, storage_handler: StorageHandler)
    def extract_orders(self, order_ids: List[str]) -> ExtractionReport
    def extract_single_order(self, order_id: str) -> bool
    def resume_extraction(self, checkpoint_file: str) -> ExtractionReport
```

---

## Command-Line Interface

### Basic Usage

```bash
# Authenticate and download orders
python -m src.main \
    --orders orders.txt \
    --output ./data \
    --mfa-method webhook

# Resume interrupted download
python -m src.main \
    --resume checkpoint.json

# Download single order (testing)
python -m src.main \
    --order-id 3076428648 \
    --output ./test_data
```

### CLI Arguments

```python
parser.add_argument('--orders', type=str, help='Path to file with order IDs (one per line)')
parser.add_argument('--order-id', type=str, help='Single order ID to download')
parser.add_argument('--output', type=str, default='./data', help='Output directory')
parser.add_argument('--mfa-method', choices=['webhook', 'manual'], default='manual')
parser.add_argument('--resume', type=str, help='Resume from checkpoint file')
parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
parser.add_argument('--rate-limit', type=float, default=2.0, help='Seconds between requests')
parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO')
parser.add_argument('--format', choices=['json', 'csv', 'both'], default='both')
```

---

## Known Issues and Limitations

### Current Challenges

1. **MFA Requirement**: Requires manual intervention or webhook setup
2. **Token Expiration**: Session tokens may expire during long-running extractions
3. **Rate Limiting**: Unknown rate limit thresholds; using conservative 2-3 second delays
4. **Incomplete Documentation**: Salesforce Aura framework is not well-documented publicly

### Potential Issues to Watch For

1. **Session Timeout**: 
   - Monitor for 401/403 responses
   - Implement automatic re-authentication
   - Save progress frequently

2. **Captcha/Bot Detection**:
   - If detected, slow down rate limiting
   - Add random jitter to request timing
   - Vary user agent strings

3. **HTML Structure Changes**:
   - Playwright selectors may break if Hallmark updates UI
   - Implement fallback selectors
   - Add graceful degradation

4. **API Changes**:
   - Salesforce Aura API structure may change
   - Monitor for API version updates
   - Log raw responses for debugging

---

## Alternative Approaches

### If Playwright Authentication Fails

**Option 1: Manual Cookie Export**
1. Login manually in browser
2. Export cookies using browser extension
3. Import cookies into requests session
4. Limitation: Requires manual step each session

**Option 2: Browser Developer Tools**
1. Login manually
2. Copy network requests as cURL
3. Convert cURL to Python requests
4. Extract tokens manually
5. Limitation: Very manual, not scalable

### If API Approach Fails

**Option 3: Full Browser Automation**
- Use Playwright for entire process
- Navigate UI, click download buttons
- Intercept download requests
- Pro: More reliable if API changes
- Con: Much slower, resource-intensive

---

## Success Criteria

### Minimum Viable Product (MVP)
- [ ] Successfully authenticate with MFA
- [ ] Download data for single order
- [ ] Save data as JSON file
- [ ] Basic error handling and logging

### Production Ready
- [ ] Batch download 100+ orders without failure
- [ ] Resume capability after interruption
- [ ] Comprehensive error handling
- [ ] Multiple output formats (JSON, CSV)
- [ ] Clear logging and progress reporting
- [ ] Command-line interface
- [ ] Documentation complete

### Ideal Solution
- [ ] Process 1000+ orders reliably
- [ ] Automatic re-authentication on timeout
- [ ] Webhook integration for MFA
- [ ] Performance optimizations
- [ ] Unit and integration tests
- [ ] Docker containerization
- [ ] Scheduling capability (cron/systemd)

---

## Support Information

### Resources

**Salesforce Aura Framework**:
- Official docs: https://developer.salesforce.com/docs/atlas.en-us.lightning.meta/lightning/
- Community forums: https://developer.salesforce.com/forums/

**Python Libraries**:
- Requests: https://requests.readthedocs.io/
- Playwright: https://playwright.dev/python/

**Debugging**:
- Chrome DevTools Network tab for request inspection
- Playwright's built-in network interception
- mitmproxy for deep packet inspection

### Contact Information

**Project Owner**: Marshall (Banner's Hallmark)
- 39 retail stores in Virginia and surrounding areas
- Stores include: Reston, Ashburn, Charlottesville, Winchester, Bradlee, Chesapeake, Burke, etc.

---

## Appendix A: Sample Data Structures

### Sample Order IDs File (orders.txt)
```
3076428648
3076428649
3076428650
```

### Sample Checkpoint File (checkpoint.json)
```json
{
    "last_processed": "3076428650",
    "completed": ["3076428648", "3076428649"],
    "failed": [],
    "remaining": ["3076428651", "3076428652"],
    "timestamp": "2025-12-18T10:30:00"
}
```

### Sample Summary Report (summary.json)
```json
{
    "execution": {
        "start_time": "2025-12-18T10:00:00",
        "end_time": "2025-12-18T12:30:00",
        "duration_seconds": 9000
    },
    "results": {
        "total_orders": 1000,
        "successful": 985,
        "failed": 15,
        "success_rate": 0.985
    },
    "failed_orders": [
        {
            "order_id": "3076428999",
            "error": "HTTP 404 - Order not found",
            "timestamp": "2025-12-18T11:15:00"
        }
    ],
    "performance": {
        "avg_request_time": 2.5,
        "requests_per_minute": 24,
        "data_downloaded_mb": 150.5
    }
}
```

---

## Appendix B: Quick Start Guide

### For the Coding Agent

1. **Review this entire document** - Understand the context and requirements
2. **Set up environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```
3. **Create .env file** from .env.example
4. **Start with Phase 1** - Get authentication working first
5. **Test incrementally** - Don't build everything at once
6. **Ask for clarification** - If anything is unclear, ask before proceeding

### Testing Credentials

**DO NOT** hardcode actual credentials. Use these placeholder patterns:
```python
# Testing mode - use fake credentials
username = os.getenv('HALLMARK_USERNAME', 'test_user')
password = os.getenv('HALLMARK_PASSWORD', 'test_pass')
```

### First Working Version

Focus on this minimal flow first:
1. Authenticate with Playwright (MFA via manual console input)
2. Extract tokens
3. Make ONE API call for ONE order ID
4. Print the response
5. Save to JSON file

Once that works, expand to batch processing.

---

## Document Version History

- **v1.0** - 2025-12-18 - Initial specification document created
- **Author**: Claude (Anthropic AI Assistant)
- **For**: Marshall @ Banner's Hallmark
- **Purpose**: Coding agent handoff for automation implementation

---

## Notes for Implementation

### Critical Success Factors

1. **Get authentication right first** - Everything else depends on this
2. **Be conservative with rate limiting** - Better slow and reliable than fast and blocked
3. **Log everything** - You'll need it for debugging
4. **Test with small batches** - Don't try to download 1000 orders on first run
5. **Handle interruptions gracefully** - Long-running processes will be interrupted

### Red Flags to Watch For

- 429 (Too Many Requests) responses → Slow down
- 401/403 (Unauthorized) responses → Re-authenticate
- Sudden CAPTCHA appearance → You're going too fast
- Contact from Hallmark IT → Stop immediately and explain situation

### When to Ask for Help

- Can't extract tokens from authenticated session
- API responses don't match expected structure
- Authentication keeps failing despite correct credentials
- Getting blocked/rate limited despite conservative delays

---

**END OF SPECIFICATION DOCUMENT**
