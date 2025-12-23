#!/usr/bin/env python3
"""Test script to verify we can perfectly recreate existing order JSON files.

This script:
1. Loads an existing order JSON file
2. Extracts the same order using the current code
3. Compares the structures to ensure they match exactly

Run this in Docker:
  docker compose run --rm -it hcscraper python test_order_recreation.py <order_id> [existing_file_path]
"""

import json
import sys
from pathlib import Path

# Add src to path (works both in Docker and locally)
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from api.client import HallmarkAPIClient
from api.request_builder import AuraRequestBuilder
from auth.authenticator import HallmarkAuthenticator
from storage.json_writer import JSONWriter
from utils.config import Config


def normalize_for_comparison(data: dict) -> dict:
    """Normalize data for comparison (sort keys, handle None vs empty string, etc.)."""
    if isinstance(data, dict):
        # Sort keys for consistent comparison
        result = {}
        for key in sorted(data.keys()):
            value = data[key]
            if isinstance(value, dict):
                result[key] = normalize_for_comparison(value)
            elif isinstance(value, list):
                result[key] = [normalize_for_comparison(item) if isinstance(item, dict) else item for item in value]
            else:
                result[key] = value
        return result
    return data


def compare_structures(existing: dict, extracted: dict, order_id: str) -> tuple[bool, list[str]]:
    """Compare two order structures and return (match, differences)."""
    differences = []
    
    # Normalize both for comparison
    existing_norm = normalize_for_comparison(existing)
    extracted_norm = normalize_for_comparison(extracted)
    
    # Get all keys from both
    all_keys = set(existing_norm.keys()) | set(extracted_norm.keys())
    
    for key in sorted(all_keys):
        if key not in existing_norm:
            differences.append(f"  - Key '{key}' exists in extracted but not in existing")
        elif key not in extracted_norm:
            differences.append(f"  - Key '{key}' exists in existing but not in extracted")
        else:
            existing_val = existing_norm[key]
            extracted_val = extracted_norm[key]
            
            if existing_val != extracted_val:
                # For lists, show more detail
                if isinstance(existing_val, list) and isinstance(extracted_val, list):
                    if len(existing_val) != len(extracted_val):
                        differences.append(
                            f"  - Key '{key}': list length differs "
                            f"(existing: {len(existing_val)}, extracted: {len(extracted_val)})"
                        )
                    else:
                        # Compare each item
                        for i, (existing_item, extracted_item) in enumerate(zip(existing_val, extracted_val)):
                            if existing_item != extracted_item:
                                differences.append(
                                    f"  - Key '{key}[{i}]': differs\n"
                                    f"      Existing: {existing_item}\n"
                                    f"      Extracted: {extracted_item}"
                                )
                else:
                    differences.append(
                        f"  - Key '{key}': value differs\n"
                        f"      Existing: {existing_val}\n"
                        f"      Extracted: {extracted_val}"
                    )
    
    return len(differences) == 0, differences


def test_order_recreation(order_id: str, existing_file: Path) -> bool:
    """Test recreating an order and compare with existing file.
    
    Args:
        order_id: The order ID to test
        existing_file: Path to existing JSON file
        
    Returns:
        True if structures match exactly, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"Testing order recreation for: {order_id}")
    print(f"{'='*80}")
    
    # Load existing file
    print(f"\n1. Loading existing file: {existing_file}")
    try:
        with open(existing_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        print(f"   ✓ Loaded existing file with {len(existing_data)} top-level keys")
        print(f"   Keys: {sorted(existing_data.keys())}")
    except Exception as e:
        print(f"   ✗ Failed to load existing file: {e}")
        return False
    
    # Authenticate
    print(f"\n2. Authenticating...")
    try:
        from auth.mfa_handler import ConsoleMFAHandler
        
        config = Config()
        mfa_handler = ConsoleMFAHandler()
        authenticator = HallmarkAuthenticator(
            username=config.username,
            password=config.password,
            mfa_handler=mfa_handler,
            base_url=config.base_url,
            headless=True,  # Required for Docker
            session_file=config.session_file
        )
        
        # Try saved session first
        success = authenticator.authenticate_with_saved_session()
        if not success:
            print("   No valid saved session, performing full login...")
            success = authenticator.authenticate(save_session=True)
        
        if not success:
            print(f"   ✗ Authentication failed")
            return False
        
        session = authenticator.get_session()
        tokens = authenticator.get_tokens()
        aura_token = tokens.get('aura.token', '')
        aura_context = tokens.get('aura.context', '')
        fwuid = tokens.get('fwuid', '')
        print(f"   ✓ Authentication successful")
    except Exception as e:
        print(f"   ✗ Authentication failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Create API client
    print(f"\n3. Creating API client...")
    try:
        request_builder = AuraRequestBuilder(
            base_url=config.base_url,
            aura_token=aura_token or '',
            aura_context=aura_context or '',
            fwuid=fwuid or ''
        )
        api_client = HallmarkAPIClient(
            session=session,
            aura_token=aura_token or '',
            aura_context=aura_context or '',
            fwuid=fwuid or '',
            base_url=config.base_url
        )
        print(f"   ✓ API client created")
    except Exception as e:
        print(f"   ✗ Failed to create API client: {e}")
        return False
    
    # Extract order
    print(f"\n4. Extracting order {order_id} from API...")
    try:
        order_data = api_client.get_order_detail(order_id)
        if order_data is None:
            print(f"   ✗ API returned None - check debug_responses/ directory for raw response")
            return False
        print(f"   ✓ Retrieved order data from API")
        print(f"   Top-level keys: {sorted(order_data.keys())}")
    except Exception as e:
        print(f"   ✗ Failed to extract order: {e}")
        return False
    
    # Flatten order data
    print(f"\n5. Flattening order data...")
    try:
        json_writer = JSONWriter(output_directory=Path("./test_output"))
        flattened = json_writer._flatten_order_data(order_id, order_data)
        print(f"   ✓ Flattened order data")
        print(f"   Top-level keys: {sorted(flattened.keys())}")
    except Exception as e:
        print(f"   ✗ Failed to flatten order data: {e}")
        return False
    
    # Compare structures
    print(f"\n6. Comparing structures...")
    match, differences = compare_structures(existing_data, flattened, order_id)
    
    if match:
        print(f"   ✓ Structures match exactly!")
        return True
    else:
        print(f"   ✗ Structures differ:")
        for diff in differences:
            print(diff)
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python test_order_recreation.py <order_id> [existing_file_path]")
        print("\nExample:")
        print("  python test_order_recreation.py 3069090941")
        print("  python test_order_recreation.py 3069090941 data/2025/09/store_9/order_3069090941.json")
        sys.exit(1)
    
    order_id = sys.argv[1]
    
    # Determine existing file path
    if len(sys.argv) >= 3:
        existing_file = Path(sys.argv[2])
    else:
        # Try to find it in data directory
        data_dir = Path("./data")
        pattern = f"**/order_{order_id}.json"
        matches = list(data_dir.glob(pattern))
        if not matches:
            print(f"Error: Could not find existing file for order {order_id}")
            print(f"Please provide the path explicitly:")
            print(f"  python test_order_recreation.py {order_id} <path_to_file>")
            sys.exit(1)
        existing_file = matches[0]
        print(f"Found existing file: {existing_file}")
    
    if not existing_file.exists():
        print(f"Error: File does not exist: {existing_file}")
        sys.exit(1)
    
    # Run test
    success = test_order_recreation(order_id, existing_file)
    
    if success:
        print(f"\n{'='*80}")
        print("✓ SUCCESS: Extracted order matches existing file exactly!")
        print(f"{'='*80}\n")
        sys.exit(0)
    else:
        print(f"\n{'='*80}")
        print("✗ FAILURE: Extracted order does not match existing file")
        print(f"{'='*80}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

