#!/usr/bin/env python3
"""Test bulk billing document search functionality for September 2025.

This script tests searching for billing documents across all Banner's Hallmark stores
for a specific date range.

Usage:
    python test_bulk_billing.py

This will:
1. Authenticate with Hallmark Connect
2. Search for billing documents from September 1-30, 2025
3. Display summary and optionally download billing documents
"""

import sys
from pathlib import Path

from src.utils.config import get_config, BANNER_HALLMARK_CUSTOMER_IDS
from src.utils.logger import setup_logging


def main():
    """Run bulk billing document search test."""
    # Load configuration
    try:
        config = get_config()
        config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease create a .env file based on .env.example")
        return 1

    # Setup logging
    setup_logging(log_level="INFO", log_to_console=True)

    print("=" * 60)
    print("Bulk Billing Document Search Test - September 2025")
    print("=" * 60)
    print()
    print(f"Searching {len(BANNER_HALLMARK_CUSTOMER_IDS)} Banner's Hallmark stores")
    print()

    # Import modules
    from src.auth.authenticator import HallmarkAuthenticator
    from src.auth.mfa_handler import ConsoleMFAHandler, WebhookMFAHandler
    from src.api.client import HallmarkAPIClient
    from src.extractors.bulk_billing_extractor import BulkBillingExtractor

    # Step 1: Authenticate
    print("Step 1: Authenticating...")
    print("-" * 60)

    # Create MFA handler
    if config.mfa_method == "webhook":
        if not config.n8n_webhook_url:
            print("Error: N8N_WEBHOOK_URL not set but MFA_METHOD is 'webhook'")
            return 1
        mfa_handler = WebhookMFAHandler(config.n8n_webhook_url)
    else:
        mfa_handler = ConsoleMFAHandler()

    # Create authenticator
    authenticator = HallmarkAuthenticator(
        username=config.username,
        password=config.password,
        mfa_handler=mfa_handler,
        base_url=config.base_url,
        headless=config.headless_mode
    )

    try:
        # Try to use saved session first
        success = authenticator.authenticate_with_saved_session()

        if not success:
            print("No valid saved session, performing full login...")
            success = authenticator.authenticate(save_session=True)

        if not success:
            print("Authentication failed")
            return 1
        print("Authentication successful\n")
    except Exception as e:
        print(f"Authentication error: {e}")
        return 1

    # Step 2: Setup API client
    print("Step 2: Setting up API client...")
    print("-" * 60)

    tokens = authenticator.get_tokens()
    api_client = HallmarkAPIClient(
        session=authenticator.get_session(),
        aura_token=tokens.get('token', ''),
        aura_context=tokens.get('context', ''),
        fwuid=tokens.get('fwuid', ''),
        base_url=config.base_url,
        rate_limit_seconds=config.rate_limit_seconds,
        max_retries=config.max_retries
    )
    print("API client ready\n")

    # Step 3: Create bulk extractor
    print("Step 3: Searching for billing documents...")
    print("-" * 60)

    output_dir = config.output_directory / "bulk_billing_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    bulk_extractor = BulkBillingExtractor(
        api_client=api_client,
        output_directory=output_dir,
        customer_ids=BANNER_HALLMARK_CUSTOMER_IDS,
        billing_status="All",
        save_json=True,
        save_csv=True
    )

    # Test dates: September 2025
    start_date = "2025-09-01"
    end_date = "2025-09-30"

    # First, get just the summary
    print(f"\nSearching for billing documents from {start_date} to {end_date}...")
    summary = bulk_extractor.get_search_summary(start_date, end_date)

    if summary:
        print(f"\nSearch Summary:")
        print(f"  Date range: {summary['start_date']} to {summary['end_date']}")
        print(f"  Billing status: {summary['billing_status']}")
        print(f"  Total billing documents found: {summary['total_billing_documents']}")
        print(f"  Customer IDs searched: {summary['customer_ids_count']}")
    else:
        print("Failed to get search summary")
        return 1

    # Ask if user wants to download
    if summary['total_billing_documents'] > 0:
        print(f"\nFound {summary['total_billing_documents']} billing documents.")
        response = input("\nDownload all billing documents? (y/n): ").strip().lower()

        if response == 'y':
            print("\nDownloading billing documents...")
            stats = bulk_extractor.search_and_download(start_date, end_date)

            print("\n" + "=" * 60)
            print("Download Summary")
            print("=" * 60)
            print(f"Billing documents found: {stats['total_found']}")
            print(f"Billing documents processed: {stats['total_downloaded']}")
            print(f"Successful: {stats['successful']}")
            print(f"Failed: {stats['failed']}")

            if stats['failed_billing_document_ids']:
                print(f"\nFailed billing document IDs:")
                for doc_id in stats['failed_billing_document_ids']:
                    print(f"  - {doc_id}")

            print(f"\nFiles saved to: {output_dir}")
        else:
            print("Skipping download.")
    else:
        print("No billing documents found for the specified date range.")

    print("\nTest complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
