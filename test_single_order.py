#!/usr/bin/env python3
"""Test end-to-end flow: authenticate and download a single order.

This script tests the complete flow from authentication to order extraction.

Usage:
    python test_single_order.py <order_id>

Example:
    python test_single_order.py 3076428648
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.auth.authenticator import HallmarkAuthenticator
from src.auth.mfa_handler import ConsoleMFAHandler, WebhookMFAHandler
from src.api.client import HallmarkAPIClient
from src.extractors.order_extractor import OrderExtractor
from src.utils.config import get_config
from src.utils.logger import setup_logging


def main():
    """Test end-to-end order extraction."""
    # Check for order ID argument
    if len(sys.argv) < 2:
        print("Usage: python test_single_order.py <order_id>")
        print("\nExample:")
        print("  python test_single_order.py 3076428648")
        return 1

    order_id = sys.argv[1]

    # Load configuration
    try:
        config = get_config()
        config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease create a .env file based on .env.example")
        return 1

    # Setup logging
    setup_logging(
        log_level=config.log_level,
        log_to_console=True
    )

    print("=" * 70)
    print("Hallmark Connect - Single Order Extraction Test")
    print("=" * 70)
    print(f"\nOrder ID: {order_id}")
    print(f"Output Directory: {config.output_directory}")
    print(f"Base URL: {config.base_url}")
    print(f"Rate Limit: {config.rate_limit_seconds} seconds")
    print()

    # Step 1: Authenticate
    print("[1/3] Authenticating...")
    print("-" * 70)

    # Create MFA handler
    if config.mfa_method == "webhook":
        print(f"Using webhook: {config.n8n_webhook_url}")
        mfa_handler = WebhookMFAHandler(config.n8n_webhook_url)
    else:
        print("Using manual console input for MFA")
        mfa_handler = ConsoleMFAHandler()

    # Create and run authenticator
    authenticator = HallmarkAuthenticator(
        username=config.username,
        password=config.password,
        mfa_handler=mfa_handler,
        base_url=config.base_url,
        headless=config.headless_mode
    )

    try:
        # Try saved session first
        success = authenticator.authenticate_with_saved_session()

        if not success:
            # No saved session, do full auth
            print("No saved session, performing full login...")
            success = authenticator.authenticate(save_session=True)

        if not success:
            print("\n✗ Authentication failed")
            return 1

        print("✓ Authentication successful")
        tokens = authenticator.get_tokens()
        token = tokens.get('token', '')
        fwuid = tokens.get('fwuid', '')
        print(f"  - Token: {token[:30]}..." if token else "  - Token: (using session auth)")
        print(f"  - FWUID: {fwuid}" if fwuid else "  - FWUID: (not extracted)")

    except Exception as e:
        print(f"\n✗ Authentication error: {e}")
        return 1

    # Step 2: Create API client
    print("\n[2/3] Setting up API client...")
    print("-" * 70)

    try:
        api_client = HallmarkAPIClient(
            session=authenticator.get_session(),
            aura_token=tokens.get('token', ''),
            aura_context=tokens.get('context', ''),
            fwuid=tokens.get('fwuid', ''),
            base_url=config.base_url,
            rate_limit_seconds=config.rate_limit_seconds,
            max_retries=config.max_retries
        )
        print("✓ API client configured")

    except Exception as e:
        print(f"\n✗ API client setup error: {e}")
        return 1

    # Step 3: Extract order
    print(f"\n[3/3] Extracting order {order_id}...")
    print("-" * 70)

    try:
        extractor = OrderExtractor(
            api_client=api_client,
            output_directory=config.output_directory,
            save_json=True,
            save_csv=True
        )

        success = extractor.extract_single_order(order_id)

        if success:
            print("\n" + "=" * 70)
            print("✓ Order extraction successful!")
            print("=" * 70)
            print(f"\nFiles saved to: {config.output_directory}/")
            print(f"  - order_{order_id}_*.json")
            print(f"  - order_{order_id}_*.csv")
            return 0
        else:
            print("\n✗ Order extraction failed")
            return 1

    except Exception as e:
        print(f"\n✗ Extraction error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
