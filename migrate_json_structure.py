#!/usr/bin/env python3
"""One-time script to migrate existing JSON files to the new flattened structure.

This script:
- Removes extracted_at field
- Flattens orderHeader fields to top level with snake_case
- Converts orderLines to order_lines with snake_case keys
- Removes the nested data.returnValue structure

Run this once to convert all existing JSON files to the new format.
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def convert_dict_keys_to_snake_case(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively convert dictionary keys from camelCase to snake_case."""
    result = {}
    for key, value in data.items():
        snake_key = camel_to_snake(key)
        if isinstance(value, dict):
            result[snake_key] = convert_dict_keys_to_snake_case(value)
        elif isinstance(value, list):
            result[snake_key] = [
                convert_dict_keys_to_snake_case(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[snake_key] = value
    return result


def migrate_order_json(order_json: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate old JSON structure to new flattened structure.
    
    Args:
        order_json: Old JSON structure with data.returnValue.orderHeader
        
    Returns:
        New flattened structure with all fields at top level
    """
    order_id = order_json.get('order_id')
    if not order_id:
        raise ValueError("order_id not found in JSON")
    
    # Navigate to returnValue structure (old format)
    return_value = order_json.get('data', {}).get('returnValue', {})
    if not return_value:
        raise ValueError("data.returnValue not found in JSON")
    
    order_header = return_value.get('orderHeader', {})
    order_lines = return_value.get('orderLines', [])
    
    # Start with order_id
    flattened = {'order_id': order_id}
    
    # Flatten all orderHeader fields to top level with snake_case keys
    if isinstance(order_header, dict):
        for key, value in order_header.items():
            snake_key = camel_to_snake(key)
            flattened[snake_key] = value
    
    # Convert orderLines to order_lines with snake_case keys in each item
    if isinstance(order_lines, list):
        flattened['order_lines'] = [
            convert_dict_keys_to_snake_case(item) if isinstance(item, dict) else item
            for item in order_lines
        ]
    else:
        flattened['order_lines'] = []
    
    return flattened


def find_order_json_files(directory: Path) -> List[Path]:
    """Find all order JSON files recursively."""
    pattern = "**/order_*.json"
    files = list(directory.glob(pattern))
    return sorted(files)


def main():
    """Main entry point."""
    import os
    
    # Get data directory
    data_dir = Path(os.getenv('DATA_DIRECTORY', './data'))
    if not data_dir.exists():
        print(f"Error: Data directory does not exist: {data_dir}")
        return 1
    
    print("=" * 60)
    print("JSON Structure Migration Script")
    print("=" * 60)
    print(f"Data directory: {data_dir}")
    print()
    
    # Find all order JSON files
    print("Finding order JSON files...")
    json_files = find_order_json_files(data_dir)
    print(f"  Found {len(json_files)} order files")
    
    if not json_files:
        print("  ✗ No order files found")
        return 1
    
    # Process files
    print(f"\nMigrating {len(json_files)} files...")
    migrated = 0
    errors = 0
    
    for i, json_file in enumerate(json_files, 1):
        if i % 50 == 0:
            print(f"  Processed {i}/{len(json_files)} files...")
        
        try:
            # Load old JSON
            with open(json_file, 'r', encoding='utf-8') as f:
                old_json = json.load(f)
            
            # Check if already migrated (has order_lines instead of data.returnValue)
            if 'order_lines' in old_json and 'data' not in old_json:
                # Already migrated, skip
                continue
            
            # Migrate to new structure
            new_json = migrate_order_json(old_json)
            
            # Write back to file
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(new_json, f, indent=2, ensure_ascii=False)
            
            migrated += 1
            
        except Exception as e:
            print(f"Error migrating {json_file}: {e}")
            errors += 1
            continue
    
    print()
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Files migrated: {migrated}")
    print(f"Errors: {errors}")
    print(f"Skipped (already migrated): {len(json_files) - migrated - errors}")
    print()
    
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

