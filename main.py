#!/usr/bin/env python3
"""Hallmark Connect order data scraper.

This is the main entry point for the Hallmark Connect data extraction system.
"""

import sys
import argparse
from pathlib import Path

from src.utils.config import get_config
from src.utils.logger import setup_logging


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract order data from Hallmark Connect"
    )

    # Order selection
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--order-id",
        type=str,
        help="Single order ID to download"
    )
    group.add_argument(
        "--orders",
        type=str,
        help="Path to file with order IDs (one per line)"
    )
    group.add_argument(
        "--resume",
        type=str,
        help="Resume from checkpoint file"
    )
    group.add_argument(
        "--bulk-orders",
        action="store_true",
        help="Search and download orders by date range"
    )

    # Bulk order options
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for bulk order search (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for bulk order search (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--customer-ids",
        type=str,
        help="Comma-separated customer IDs (default: all Banner's Hallmark stores)"
    )
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="Only search and show summary, don't download orders"
    )

    # Configuration overrides
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory (overrides OUTPUT_DIRECTORY env var)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (overrides LOG_LEVEL env var)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Load configuration
    try:
        config = get_config()
        config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease create a .env file based on .env.example")
        return 1

    # Setup logging
    log_level = args.log_level or config.log_level
    setup_logging(log_level=log_level, log_to_console=True)

    print("=" * 60)
    print("Hallmark Connect Order Data Scraper")
    print("=" * 60)
    print()

    # Import modules
    from src.auth.authenticator import HallmarkAuthenticator
    from src.auth.mfa_handler import ConsoleMFAHandler, WebhookMFAHandler
    from src.api.client import HallmarkAPIClient
    from src.extractors.order_extractor import OrderExtractor
    from src.extractors.bulk_order_extractor import BulkOrderExtractor

    # Step 1: Authenticate
    print("Step 1: Authenticating...")
    print("-" * 60)

    # Create MFA handler (only needed if saved session doesn't work)
    if config.mfa_method == "webhook":
        if not config.n8n_webhook_url:
            print("Error: N8N_WEBHOOK_URL not set but MFA_METHOD is 'webhook'")
            return 1
        mfa_handler = WebhookMFAHandler(config.n8n_webhook_url)
    else:
        mfa_handler = ConsoleMFAHandler()

    # Create authenticator
    headless = args.headless if args.headless else config.headless_mode
    authenticator = HallmarkAuthenticator(
        username=config.username,
        password=config.password,
        mfa_handler=mfa_handler,
        base_url=config.base_url,
        headless=headless
    )

    try:
        # Try to use saved session first (skips login/MFA!)
        success = authenticator.authenticate_with_saved_session()

        if not success:
            # Saved session failed or doesn't exist, do full authentication
            print("No valid saved session, performing full login...")
            success = authenticator.authenticate(save_session=True)

        if not success:
            print("✗ Authentication failed")
            return 1
        print("✓ Authentication successful\n")
    except Exception as e:
        print(f"✗ Authentication error: {e}")
        return 1

    # Step 2: Setup API client
    print("Step 2: Setting up API client...")
    print("-" * 60)

    tokens = authenticator.get_tokens()
    # Aura tokens are optional - session-based auth works with just sid cookie
    api_client = HallmarkAPIClient(
        session=authenticator.get_session(),
        aura_token=tokens.get('token', ''),
        aura_context=tokens.get('context', ''),
        fwuid=tokens.get('fwuid', ''),
        base_url=config.base_url,
        rate_limit_seconds=config.rate_limit_seconds,
        max_retries=config.max_retries
    )
    print("✓ API client ready\n")

    # Step 3: Extract orders
    print("Step 3: Extracting orders...")
    print("-" * 60)

    output_dir = Path(args.output) if args.output else config.output_directory
    extractor = OrderExtractor(
        api_client=api_client,
        output_directory=output_dir,
        save_json=True,
        save_csv=True
    )

    # Handle different input modes
    if args.order_id:
        # Single order
        success = extractor.extract_single_order(args.order_id)
        if success:
            print(f"\n✓ Successfully extracted order {args.order_id}")
            return 0
        else:
            print(f"\n✗ Failed to extract order {args.order_id}")
            return 1

    elif args.orders:
        # Multiple orders from file
        orders_file = Path(args.orders)
        if not orders_file.exists():
            print(f"✗ Orders file not found: {orders_file}")
            return 1

        order_ids = []
        with open(orders_file, 'r') as f:
            for line in f:
                order_id = line.strip()
                if order_id:
                    order_ids.append(order_id)

        print(f"Found {len(order_ids)} orders to extract\n")
        stats = extractor.extract_orders(order_ids)

        print("\n" + "=" * 60)
        print("Extraction Summary")
        print("=" * 60)
        print(f"Total orders: {stats['total']}")
        print(f"Successful: {stats['successful']}")
        print(f"Failed: {stats['failed']}")
        if stats['failed_order_ids']:
            print(f"\nFailed order IDs:")
            for oid in stats['failed_order_ids']:
                print(f"  - {oid}")

        return 0 if stats['failed'] == 0 else 1

    elif args.resume:
        # TODO: Implement resume functionality
        print("✗ Resume functionality not yet implemented")
        return 1

    elif args.bulk_orders:
        # Validate required arguments
        if not args.start_date or not args.end_date:
            print("✗ --bulk-orders requires --start-date and --end-date")
            return 1

        # Parse customer IDs if provided
        customer_ids = None
        if args.customer_ids:
            customer_ids = args.customer_ids.split(",")

        # Create bulk extractor
        bulk_extractor = BulkOrderExtractor(
            api_client=api_client,
            output_directory=output_dir,
            customer_ids=customer_ids,
            save_json=True,
            save_csv=True
        )

        if args.search_only:
            # Just show summary
            summary = bulk_extractor.get_search_summary(args.start_date, args.end_date)
            if summary:
                print(f"\nSearch Summary:")
                print(f"  Date range: {summary['start_date']} to {summary['end_date']}")
                print(f"  Total orders found: {summary['total_orders']}")
                print(f"  Customer IDs searched: {summary['customer_ids_count']}")
                return 0
            else:
                print("✗ Failed to get search summary")
                return 1
        else:
            # Search and download
            print(f"Searching for orders from {args.start_date} to {args.end_date}...")
            stats = bulk_extractor.search_and_download(args.start_date, args.end_date)

            print("\n" + "=" * 60)
            print("Bulk Extraction Summary")
            print("=" * 60)
            print(f"Orders found in search: {stats['total_found']}")
            print(f"Orders processed: {stats['total_downloaded']}")
            print(f"Successful: {stats['successful']}")
            print(f"Failed: {stats['failed']}")
            if stats['failed_order_ids']:
                print(f"\nFailed order IDs:")
                for oid in stats['failed_order_ids']:
                    print(f"  - {oid}")

            return 0 if stats['failed'] == 0 else 1

    else:
        print("✗ Please specify --order-id, --orders, --resume, or --bulk-orders")
        return 1


if __name__ == "__main__":
    sys.exit(main())
