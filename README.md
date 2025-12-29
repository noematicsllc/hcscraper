# Hallmark Connect Order Data Scraper

Automated extraction system for Hallmark Connect order and sales data. Built to enable operational independence by extracting historical sales data without relying on Hallmark's portal limitations.

## Features

- Playwright-based authentication with MFA support
- Salesforce Aura framework API integration
- Automatic session token extraction from browser storage
- Retry logic with exponential backoff
- Conservative rate limiting with configurable delays
- Periodic breaks to avoid rate limiting
- Hierarchical file organization (year/month/store)
- Bulk order search by date range
- Single order and batch processing
- Billing document extraction support
- PostgreSQL database integration with canonical store names
- Component-based logging (separate log files per component)
- Skip existing records by default (use `--update` to re-download)

## Prerequisites

- Python 3.13+
- uv (for dependency management)
- Valid Hallmark Connect credentials

## Installation

1. **Clone or navigate to the project directory**

2. **Install dependencies**
```bash
uv sync
playwright install chromium
```

3. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your credentials
```

Required environment variables:
```bash
HALLMARK_USERNAME=your_username
HALLMARK_PASSWORD=your_password
MFA_METHOD=manual  # or 'webhook'
```

Optional configuration variables:
```bash
# Basic settings
OUTPUT_DIRECTORY=./data
LOG_LEVEL=INFO
BASE_URL=https://services.hallmarkconnect.com

# MFA (if using webhook method)
N8N_WEBHOOK_URL=https://your-webhook.com/mfa

# Rate limiting
RATE_LIMIT_DETAIL_SECONDS=2.5
RATE_LIMIT_SEARCH_SECONDS=5.0
RATE_LIMIT_JITTER_SECONDS=0.5

# Periodic breaks
BREAK_AFTER_REQUESTS=25
BREAK_DURATION_SECONDS=60
BREAK_AFTER_JITTER=5
BREAK_JITTER_SECONDS=15

# Conservative mode
CONSERVATIVE_MODE=false

# Timeouts
REQUEST_TIMEOUT_SECONDS=30
SEARCH_TIMEOUT_SECONDS=120
MAX_RETRIES=3

# Browser (default: true - always headless)
HEADLESS_MODE=true

# Database (optional, for canonical store names)
DATABASE_URL=postgresql://hallmark:hallmark@localhost:5432/hallmark_orders
```

See `.env.example` for all available configuration options.

## Usage

### Test Authentication

Test your credentials and MFA setup:
```bash
python test_auth.py
```

### Extract Single Order

Download a single order by ID:
```bash
python main.py --order-id 3076428648
```

### Extract Multiple Orders

Create a file with order IDs (one per line):
```
3076428648
3076428649
3076428650
```

Then run:
```bash
python main.py --orders orders.txt
```

### Download Orders from Exported CSV

If you've manually exported a CSV of order search results from Hallmark Connect:
```bash
python main.py --orders-csv search_results/orders_20251220171139.csv
```

This reads the "Order #" column from the CSV and downloads each order's full details.

### Bulk Order Search by Date Range

Search and download orders for a specific date range across all Banner's Hallmark stores:
```bash
python main.py --bulk-orders --start-date 2025-01-01 --end-date 2025-01-31
```

Search for specific customer IDs:
```bash
python main.py --bulk-orders --start-date 2025-01-01 --end-date 2025-01-31 --customer-ids 1000055874,1000004735
```

Preview search results without downloading:
```bash
python main.py --bulk-orders --start-date 2025-01-01 --end-date 2025-01-31 --search-only
```

### Extract Billing Documents

Single billing document:
```bash
python main.py --billing-doc-id 5055177281
```

Multiple billing documents from CSV:
```bash
python main.py --billing-docs-csv search_results/billing_documents_202509.csv
```

### Command Line Options

```bash
python main.py --help
```

**Order Selection (mutually exclusive):**
- `--order-id ORDER_ID` - Single order ID to download
- `--orders FILE` - Path to file with order IDs (one per line, .txt format)
- `--orders-csv FILE` - Path to CSV with order search results (uses 'Order #' column)
- `--billing-doc-id ID` - Single billing document ID to download
- `--billing-docs-csv FILE` - Path to CSV with billing document search results (uses 'Billing Document #' column)
- `--bulk-orders` - Search and download orders by date range

**Bulk Order Options:**
- `--start-date DATE` - Start date for bulk order search (YYYY-MM-DD)
- `--end-date DATE` - End date for bulk order search (YYYY-MM-DD)
- `--customer-ids IDS` - Comma-separated customer IDs (default: all Banner's stores)
- `--search-only` - Only search and show summary, don't download orders

**Configuration:**
- `--output DIR` - Output directory (overrides OUTPUT_DIRECTORY env var)
- `--headless` - Run browser in headless mode (default: true - always headless, flag kept for compatibility)
- `--log-level LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR
- `--update` - Re-download existing records (default: skip existing records)
- `--max-consecutive-failures N` - Maximum consecutive failures before stopping (default: 3)

## Session Persistence

**Important:** After the first successful login, your session is automatically saved to `sessions/hallmark_session.json`. Subsequent runs will **skip login/MFA entirely** and go straight to data extraction!

### How It Works

**First Run:**
```bash
python main.py --order-id 3076428648
# → Browser opens
# → You enter MFA code
# → Session saved to sessions/hallmark_session.json
# → Order extracted
```

**Subsequent Runs (NO MFA!):**
```bash
python main.py --orders my_orders.txt
# → Loads saved session
# → NO browser, NO login, NO MFA!
# → Starts extracting immediately
```

### Session Lifetime

- Session typically valid for several hours
- Automatically falls back to full login if session expires
- Saved in `sessions/hallmark_session.json` (in .gitignore - never committed)

### Clear Saved Session

If you need to force a fresh login:
```bash
rm sessions/hallmark_session.json
```

## Project Structure

```
hcscraper/
  src/
    auth/              # Playwright authentication + MFA handling
      authenticator.py
      mfa_handler.py
    api/               # API client + Aura request builders
      client.py
      request_builder.py
    extractors/        # Data extraction logic
      base_extractor.py
      order_extractor.py
      bulk_order_extractor.py
      billing_document_extractor.py
      delivery_extractor.py
    storage/           # JSON writer
      json_writer.py
    utils/             # Config + logging + date parsing
      config.py
      logger.py
      date_parser.py
  data/                # Output directory (gitignored)
  logs/                # Component-based log files (gitignored)
  sessions/            # Session persistence (gitignored)
  search_results/      # CSV input files
  main.py              # Main entry point
  test_auth.py         # Authentication test
  import_to_postgres.py  # Database import script
  create_stores_table.py  # Store mapping setup script
  schema.sql           # PostgreSQL schema
  .env                 # Configuration (gitignored)
```

## Output Files

Extracted data is saved in a hierarchical directory structure organized by year, month, and store:

```
data/
  2025/
    09/
      store_1403/
        order_3068921632.json
        billing_5055177281.json
      store_9/
        order_3076428648.json
```

### File Structure

**Orders:**
- `order_{ORDER_ID}.json` - Complete order data including header and line items

**Billing Documents:**
- `billing_{BILLING_DOCUMENT_ID}.json` - Complete billing document data

The JSON files contain all data including line items in a flattened, structured format.

### Directory Organization

Files are automatically organized into:
- `{output_dir}/{YEAR}/{MONTH}/store_{STORE_NUMBER}/`

The system extracts the year/month from the order date and uses the canonical store number from the database (if available) or falls back to the customer_id. Store numbers are looked up from the `stores` table using the order's `customer_id`.

### JSON Format

JSON files contain the complete data in a flattened structure:

```json
{
  "order_id": "3076428648",
  "customer_id": 1000055874,
  "store_name": "Reston",
  "order_creation_date": "09/01/2025",
  "order_total": "127.82",
  "order_status": "COMPLETED",
  "order_lines": [
    {
      "line_item_number": 1,
      "material_number": "000000007001038970",
      "material_description": "PRODUCT NAME",
      "quantity": 10,
      "unit_price": "12.78"
    }
  ]
}
```

All field names use snake_case, and the structure is flattened (no nested wrappers). The complete original data is preserved for reference when imported into PostgreSQL.

## Logging

The application uses component-based logging with separate log files for different components:

- `logs/auth.log` - Authentication operations
- `logs/extractors.log` - Data extraction operations
- `logs/api.log` - API requests and responses
- `logs/storage.log` - File storage operations
- `logs/main.log` - Main application flow

Console output shows WARNING level and above by default (or DEBUG if `--log-level DEBUG` is used), while all log files contain detailed information at the configured log level.

## PostgreSQL Import

The docker-compose.yml includes a PostgreSQL service that automatically starts with the application.

**Starting PostgreSQL:**
```bash
# Start PostgreSQL (and keep it running)
docker compose up -d postgres

# Check if it's running
docker compose ps postgres
```

**Importing Data:**
```bash
# Import all order JSON files into the database
docker compose run --rm hcscraper python import_to_postgres.py
```

The import script will:
- Connect to the PostgreSQL service automatically (using default DATABASE_URL)
- Create database tables if they don't exist (`orders`, `order_items`, `order_deliveries`, `order_billing_documents`, `stores`)
- Find all `order_*.json` and `billing_*.json` files in the data directory
- Extract entity headers and line items from the flattened JSON structure
- Insert data into PostgreSQL with proper data types
- Store the full raw JSON in JSONB columns for reference
- Handle duplicates (updates existing records if re-imported)
- Use canonical store names from the `stores` table

**Setting Up Store Mapping:**
Before importing orders, set up the store mapping:
```bash
docker compose run --rm hcscraper python create_stores_table.py
```

This creates the `stores` table that maps `customer_id` to canonical store numbers and names. Orders will use these canonical names during import.

**Database Connection:**
The default connection (set automatically):
- Host: `postgres` (Docker service name)
- Port: `5432`
- Database: `hallmark_orders`
- User: `hallmark`
- Password: `hallmark`

**Accessing the Database:**
```bash
# Connect to PostgreSQL from host machine
docker compose exec postgres psql -U hallmark -d hallmark_orders

# Or from the application container
docker compose run --rm hcscraper psql $DATABASE_URL
```

**Custom Database:**
To use a different PostgreSQL instance, set `DATABASE_URL` in your `.env` file:
```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

**Database Schema:**
- `stores` table: Maps customer_id to canonical store_number and store_name
- `orders` table: One row per order with all header fields (uses canonical store_name from stores table)
- `order_items` table: One row per line item, linked to orders via foreign key
- `order_deliveries` table: Junction table linking orders to delivery IDs
- `order_billing_documents` table: Junction table linking orders to billing document numbers
- All tables include `raw_data` JSONB columns containing the complete original JSON

**Manual Schema Creation:**
If you prefer to create the schema manually:
```bash
docker compose exec postgres psql -U hallmark -d hallmark_orders -f schema.sql
```

**Stopping PostgreSQL:**
```bash
# Stop the PostgreSQL service
docker compose stop postgres

# Stop and remove data (WARNING: deletes all data)
docker compose down -v postgres
```

## Rate Limiting

**IMPORTANT**: The scraper uses conservative rate limiting to avoid being blocked. Default settings include:
- 2.5 seconds between detail requests
- 5.0 seconds between search requests
- Periodic breaks every ~25 requests

### Rate Limiting Configuration

```bash
# In .env
RATE_LIMIT_DETAIL_SECONDS=2.5    # Delay between detail requests
RATE_LIMIT_SEARCH_SECONDS=5.0    # Delay between search requests
RATE_LIMIT_JITTER_SECONDS=0.5    # Random jitter to add to delays

# Periodic breaks
BREAK_AFTER_REQUESTS=25          # Requests before taking a break
BREAK_DURATION_SECONDS=60        # Break duration in seconds
BREAK_AFTER_JITTER=5             # Randomize break interval
BREAK_JITTER_SECONDS=15          # Randomize break duration

# Conservative mode (doubles delays, halves requests between breaks)
CONSERVATIVE_MODE=false
```

### Timeout Settings

```bash
# In .env
REQUEST_TIMEOUT_SECONDS=30       # Timeout for detail requests
SEARCH_TIMEOUT_SECONDS=120       # Timeout for search requests
MAX_RETRIES=3                    # Maximum retry attempts
```

## MFA Methods

### Manual Console Input (Default)

You'll be prompted to enter the MFA code during authentication:
```
Enter MFA code: 123456
```

### Webhook Integration

Configure an n8n webhook to receive MFA codes:
```bash
# In .env
MFA_METHOD=webhook
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/mfa
```

The webhook should return:
```json
{"code": "123456"}
```

## Skip Existing Records

By default, the system **skips records that have already been extracted** to save time and resources. This prevents:
- Wasting time re-downloading existing data
- Wasting API resources and rate limits
- Potential data loss if re-extraction fails

**To re-download existing records**, use the `--update` flag:
```bash
python main.py --orders-csv orders.csv --update
```

## Troubleshooting

### Authentication Issues

1. **MFA timeout**: Increase timeout in webhook handler or use manual method
2. **Token extraction fails**: Check `logs/auth.log` for detailed error information
3. **Session expired**: Delete `sessions/hallmark_session.json` to force fresh login

### API Issues

1. **401/403 errors**: Session token expired - re-authenticate
2. **429 rate limiting**: Increase `RATE_LIMIT_DETAIL_SECONDS` or `RATE_LIMIT_SEARCH_SECONDS`
3. **Timeout errors**: Check network connection and increase `MAX_RETRIES`
4. **Empty responses**: Check authentication - see `logs/auth.log` for token extraction details

### Debug Mode

Enable detailed logging:
```bash
python main.py --order-id 3076428648 --log-level DEBUG
```

Check component-specific log files in `logs/` directory for detailed information.

## Security Notes

- **NEVER** commit `.env` file (it's in `.gitignore`)
- **NEVER** hardcode credentials in code
- Store output data securely (contains business-sensitive information)
- Review `.gitignore` to ensure data files, logs, and sessions are excluded

## Docker Usage

The application can be run in a Docker container with files accessible on the host machine.

### Prerequisites

- Docker and Docker Compose installed
- `.env` file configured with credentials

### Initial Setup

Before the first run, create the required directories:
```bash
mkdir -p data sessions logs search_results
```

This ensures Docker mounts these as directories (not files) and the application can write to them.

### Building the Image

```bash
docker compose build
```

Or build directly with Docker:
```bash
docker build -t hcscraper .
```

### Running with Docker Compose

The container is configured for interactive use, allowing you to:
- Enter MFA codes when prompted
- See real-time progress messages and logs
- Monitor extraction progress

**Single order:**
```bash
docker compose run --rm -it hcscraper python main.py --order-id 3076428648
```

**Multiple orders from file:**
```bash
docker compose run --rm -it hcscraper python main.py --orders orders.txt
```

**Bulk order search:**
```bash
docker compose run --rm -it hcscraper python main.py --bulk-orders --start-date 2025-01-01 --end-date 2025-01-31
```

**Billing documents from CSV:**
```bash
docker compose run --rm -it hcscraper python main.py --billing-docs-csv search_results/billing_documents_202509.csv
```

**Note:** 
- The `-it` flags are needed for interactive MFA code input (when using manual MFA method)
- Browser always runs in headless mode by default
- You can see all progress messages and logs in real-time
- Interrupt the process with Ctrl+C if needed

### Volume Mounts

The `docker-compose.yml` file mounts the following directories to the host:
- `./data` → `/app/data` - Downloaded data files
- `./sessions` → `/app/sessions` - Session persistence (contains `hallmark_session.json`)
- `./logs` → `/app/logs` - Component-based log files
- `./search_results` → `/app/search_results:ro` - CSV input files (read-only)

Files downloaded in the container will be immediately accessible in the `./data` directory on your host machine.

### Running with Docker directly

```bash
# Build
docker build -t hcscraper .

# Run with volume mounts (interactive mode)
docker run --rm -it \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/sessions:/app/sessions" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/.env:/app/.env:ro" \
  hcscraper python main.py --order-id 3076428648
```

**Note:** 
- Use `-it` flags for interactive MFA code input (when using manual MFA method)
- Browser always runs in headless mode by default
- For webhook MFA, you can omit `-it` since no manual input is needed:
```bash
# Non-interactive (webhook MFA only)
docker run --rm \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/sessions:/app/sessions" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/.env:/app/.env:ro" \
  hcscraper python main.py --order-id 3076428648
```

### Interactive Mode (for MFA input)

When using manual MFA method, use `-it` flags to enter MFA codes:
```bash
# Manual MFA (interactive)
docker compose run --rm -it hcscraper python main.py --order-id 3076428648
```

**For webhook MFA (non-interactive, no manual input needed):**
```bash
docker compose run --rm hcscraper python main.py --order-id 3076428648
```

**Note:** The `-it` flags enable:
- `-i` (--interactive): Keeps STDIN open for input (needed for MFA codes)
- `-t` (--tty): Allocates a pseudo-TTY for proper output formatting and color

Without `-it`, you'll still see output but won't be able to enter MFA codes interactively. Browser always runs in headless mode by default.

## Development

Run tests:
```bash
pytest tests/
```

Install additional dependencies:
```bash
uv sync
```

Code structure follows the patterns documented in `.cursorrules`.

## License

Private/Internal Use

## Support

For issues or questions, contact the project maintainer.
