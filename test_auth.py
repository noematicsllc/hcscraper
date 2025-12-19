#!/usr/bin/env python3
"""Test authentication flow for Hallmark Connect.

This script tests the Playwright-based authentication and token extraction.
Run this first to verify your credentials and MFA setup work correctly.

Usage:
    python test_auth.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.auth.authenticator import HallmarkAuthenticator
from src.auth.mfa_handler import ConsoleMFAHandler, WebhookMFAHandler
from src.utils.config import get_config
from src.utils.logger import setup_logging


def main():
    """Test authentication flow."""
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

    print("=" * 60)
    print("Hallmark Connect Authentication Test")
    print("=" * 60)
    print(f"\nUsername: {config.username}")
    print(f"Base URL: {config.base_url}")
    print(f"MFA Method: {config.mfa_method}")
    print(f"Headless Mode: {config.headless_mode}")
    print()

    # Create MFA handler based on configuration
    if config.mfa_method == "webhook":
        print(f"Using webhook: {config.n8n_webhook_url}")
        mfa_handler = WebhookMFAHandler(config.n8n_webhook_url)
    else:
        print("Using manual console input for MFA")
        mfa_handler = ConsoleMFAHandler()

    # Create authenticator
    authenticator = HallmarkAuthenticator(
        username=config.username,
        password=config.password,
        mfa_handler=mfa_handler,
        base_url=config.base_url,
        headless=config.headless_mode
    )

    # Attempt authentication
    try:
        print("\nAttempting authentication...")
        print()

        # Try saved session first
        print("[Step 1] Trying saved session (skip login/MFA)...")
        success = authenticator.authenticate_with_saved_session()

        if not success:
            # No saved session or expired, do full auth
            print("[Step 2] No saved session, performing full login (with MFA)...")
            print("(Browser window will open unless headless=true)")
            print()
            success = authenticator.authenticate(save_session=True)

        if success:
            print("\n" + "=" * 60)
            print("✓ Authentication successful!")
            print("=" * 60)

            # Display extracted tokens
            tokens = authenticator.get_tokens()
            print(f"\nExtracted tokens:")
            print(f"  - aura.token: {tokens['token'][:50]}..." if len(tokens['token']) > 50 else f"  - aura.token: {tokens['token']}")
            print(f"  - fwuid: {tokens['fwuid']}")
            print(f"  - context: {'Present' if tokens['context'] else 'Not extracted'}")

            # Display session info
            session = authenticator.get_session()
            print(f"\nSession cookies: {len(session.cookies)} cookies transferred")

            print("\n✓ Ready to proceed with API calls")
            print("\n💡 Next time you run this, login/MFA will be skipped!")
            return 0

        else:
            print("\n✗ Authentication failed")
            return 1

    except Exception as e:
        print(f"\n✗ Authentication error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
