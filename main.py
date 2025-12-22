#!/usr/bin/env python3
"""Hallmark Connect order data scraper.

This is the main entry point for the Hallmark Connect data extraction system.
"""

import sys
import csv
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple

from src.utils.config import get_config, DEFAULT_MAX_CONSECUTIVE_FAILURES
from src.utils.logger import setup_logging


def read_ids_from_csv(
    csv_path: str,
    default_column: str,
    column_patterns: List[Tuple[str, List[str]]]
) -> List[str]:
    """Generic function to read IDs from CSV file.
    
    Args:
        csv_path: Path to the CSV file
        default_column: Default column name to look for
        column_patterns: List of (pattern_type, patterns) tuples for column detection.
                        pattern_type can be "contains" (all patterns must be in field name)
                        or "exact" (field name must match one of the patterns)
        
    Returns:
        List of IDs as strings
    """
    ids = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # Find the correct column name
        column_name = default_column
        if column_name not in reader.fieldnames:
            for pattern_type, patterns in column_patterns:
                for field in reader.fieldnames:
                    field_lower = field.lower()
                    if pattern_type == "contains":
                        # All patterns must be present in field name
                        if all(pattern.lower() in field_lower for pattern in patterns):
                            column_name = field
                            break
                    elif pattern_type == "exact":
                        # Field name must exactly match one of the patterns
                        if field_lower in [p.lower() for p in patterns]:
                            column_name = field
                            break
                if column_name != default_column:
                    break
        
        for row in reader:
            id_value = row.get(column_name, '').strip()
            if id_value:
                ids.append(id_value)
    
    return ids


def read_order_ids_from_csv(csv_path: str, column_name: str = "Order #") -> List[str]:
    """Read order IDs from a CSV file.
    
    Args:
        csv_path: Path to the CSV file
        column_name: Name of the column containing order IDs (default: "Order #")
        
    Returns:
        List of order IDs as strings
    """
    return read_ids_from_csv(
        csv_path,
        column_name,
        [
            ("contains", ["order", "#"]),
            ("exact", ["order_id", "orderid", "order_number", "ordernumber"])
        ]
    )


def read_billing_document_ids_from_csv(csv_path: str, column_name: str = "Billing Document #") -> List[str]:
    """Read billing document IDs from a CSV file.
    
    Args:
        csv_path: Path to the CSV file
        column_name: Name of the column containing billing document IDs (default: "Billing Document #")
        
    Returns:
        List of billing document IDs as strings
    """
    return read_ids_from_csv(
        csv_path,
        column_name,
        [
            ("contains", ["billing", "#"]),
            ("contains", ["invoice", "#"]),
            ("contains", ["document", "#"]),
            ("exact", [
                "billing_document_id", "billingdocumentid", "invoice_id", "invoiceid",
                "billing_document_number", "billingdocumentnumber", "document_id", "documentid"
            ])
        ]
    )


def print_extraction_summary(stats: Dict[str, Any], entity_type: str = "orders") -> None:
    """Print extraction summary statistics.
    
    Args:
        stats: Dictionary containing extraction statistics
        entity_type: Type of entity being extracted (e.g., "orders", "billing documents")
    """
    print("\n" + "=" * 60)
    print("Extraction Summary")
    print("=" * 60)
    print(f"Total {entity_type}: {stats['total']}")
    print(f"Processed: {stats.get('processed', stats['total'])}")
    print(f"Successful: {stats['successful']}")
    print(f"Failed: {stats['failed']}")
    if stats.get('stopped_early'):
        print(f"\n⚠ Extraction stopped early due to consecutive failures")
    
    # Handle different failed ID key names
    failed_ids = (
        stats.get('failed_order_ids') or 
        stats.get('failed_billing_document_ids') or 
        []
    )
    if failed_ids:
        print(f"\nFailed {entity_type} IDs:")
        for oid in failed_ids:
            print(f"  - {oid}")


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
        help="Path to file with order IDs (one per line, .txt format)"
    )
    group.add_argument(
        "--orders-csv",
        type=str,
        help="Path to CSV file with order search results (uses 'Order #' column)"
    )
    group.add_argument(
        "--billing-doc-id",
        type=str,
        help="Single billing document ID to download"
    )
    group.add_argument(
        "--billing-docs-csv",
        type=str,
        help="Path to CSV file with billing document search results (uses 'Billing Document #' column)"
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
    parser.add_argument(
        "--update",
        action="store_true",
        help="Re-download existing records (default: skip existing records)"
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=DEFAULT_MAX_CONSECUTIVE_FAILURES,
        help=f"Maximum consecutive failures before stopping (default: {DEFAULT_MAX_CONSECUTIVE_FAILURES})"
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
    from src.api.request_builder import AuraRequestBuilder
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
        headless=headless,
        session_file=str(config.session_file)
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
    
    # Define session refresh callback (after api_client is created)
    def refresh_session() -> bool:
        """Callback to refresh session when expired."""
        print("\nSession expired, attempting to refresh...")
        try:
            # Try to use saved session first
            success = authenticator.authenticate_with_saved_session()
            if not success:
                # Saved session failed, do full authentication
                print("Saved session invalid, performing full login...")
                success = authenticator.authenticate(save_session=True)
            
            if success:
                # Update API client session and tokens
                new_tokens = authenticator.get_tokens()
                api_client.session = authenticator.get_session()
                api_client.request_builder = AuraRequestBuilder(
                    base_url=config.base_url,
                    aura_token=new_tokens.get('token', ''),
                    aura_context=new_tokens.get('context', ''),
                    fwuid=new_tokens.get('fwuid', '')
                )
                print("✓ Session refreshed successfully\n")
                return True
            else:
                print("✗ Session refresh failed\n")
                return False
        except Exception as e:
            print(f"✗ Session refresh error: {e}\n")
            return False
    
    # Set the callback after api_client is created
    api_client.on_session_expired = refresh_session
    print("✓ API client ready\n")

    # Step 3: Extract data
    if args.billing_doc_id or args.billing_docs_csv:
        print("Step 3: Extracting billing documents...")
        print("-" * 60)
    else:
        print("Step 3: Extracting orders...")
        print("-" * 60)

    output_dir = Path(args.output) if args.output else config.output_directory
    
    # Handle different input modes
    if args.order_id or args.orders or args.orders_csv:
        # Order extraction - use context manager
        with OrderExtractor(
            api_client=api_client,
            output_directory=output_dir,
            save_json=True,
            update_mode=args.update,
            max_consecutive_failures=args.max_consecutive_failures
        ) as extractor:
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

                print_extraction_summary(stats, "orders")

                return 0 if stats['failed'] == 0 else 1

            elif args.orders_csv:
                # Multiple orders from CSV file (e.g., exported from Hallmark Connect)
                csv_file = Path(args.orders_csv)
                if not csv_file.exists():
                    print(f"✗ CSV file not found: {csv_file}")
                    return 1

                order_ids = read_order_ids_from_csv(str(csv_file))
                
                if not order_ids:
                    print(f"✗ No order IDs found in CSV file: {csv_file}")
                    return 1

                print(f"Found {len(order_ids)} orders in CSV file\n")
                stats = extractor.extract_orders(order_ids)

                print_extraction_summary(stats, "orders")

                return 0 if stats['failed'] == 0 else 1

    elif args.billing_doc_id:
        # Single billing document
        from src.extractors.billing_document_extractor import BillingDocumentExtractor
        
        with BillingDocumentExtractor(
            api_client=api_client,
            output_directory=output_dir,
            save_json=True,
            update_mode=args.update,
            max_consecutive_failures=args.max_consecutive_failures
        ) as billing_extractor:
            success = billing_extractor.extract_single_billing_document(args.billing_doc_id)
            if success:
                print(f"\n✓ Successfully extracted billing document {args.billing_doc_id}")
                return 0
            else:
                print(f"\n✗ Failed to extract billing document {args.billing_doc_id}")
                return 1

    elif args.billing_docs_csv:
        # Multiple billing documents from CSV file
        from src.extractors.billing_document_extractor import BillingDocumentExtractor
        
        csv_file = Path(args.billing_docs_csv)
        if not csv_file.exists():
            print(f"✗ CSV file not found: {csv_file}")
            return 1

        billing_doc_ids = read_billing_document_ids_from_csv(str(csv_file))
        
        if not billing_doc_ids:
            print(f"✗ No billing document IDs found in CSV file: {csv_file}")
            return 1

        print(f"Found {len(billing_doc_ids)} billing documents in CSV file\n")
        
        with BillingDocumentExtractor(
            api_client=api_client,
            output_directory=output_dir,
            save_json=True,
            update_mode=args.update,
            max_consecutive_failures=args.max_consecutive_failures
        ) as billing_extractor:
            stats = billing_extractor.extract_billing_documents(billing_doc_ids)

            print_extraction_summary(stats, "billing documents")

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

        # Use bulk extractor with context manager
        with BulkOrderExtractor(
            api_client=api_client,
            output_directory=output_dir,
            customer_ids=customer_ids,
            save_json=True,
            update_mode=args.update,
            max_consecutive_failures=args.max_consecutive_failures
        ) as bulk_extractor:
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
                print(f"Orders processed: {stats.get('processed', stats['total_downloaded'])}")
                print(f"Successful: {stats['successful']}")
                print(f"Failed: {stats['failed']}")
                if stats.get('stopped_early'):
                    print(f"\n⚠ Extraction stopped early due to consecutive failures")
                if stats.get('failed_order_ids'):
                    print(f"\nFailed order IDs:")
                    for oid in stats['failed_order_ids']:
                        print(f"  - {oid}")

                return 0 if stats['failed'] == 0 else 1

    else:
        print("✗ Please specify --order-id, --orders, --resume, or --bulk-orders")
        return 1


if __name__ == "__main__":
    sys.exit(main())
