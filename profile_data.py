#!/usr/bin/env python3
"""Profile downloaded data files using ydata_profiling.

This script generates HTML reports analyzing the structure and content of
downloaded order and billing document data.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pandas as pd
from ydata_profiling import ProfileReport


def find_metadata_files(directory: Path, file_type: str = "order") -> List[Path]:
    """Find all metadata JSON files of a given type.

    Args:
        directory: Root directory to search (searches recursively)
        file_type: Type of file to find ("order" or "billing")

    Returns:
        List of Path objects to metadata JSON files
    """
    pattern = f"**/{file_type}_*_meta.json"
    files = list(directory.glob(pattern))
    return sorted(files)


def load_metadata_file(metadata_path: Path) -> Dict[str, Any]:
    """Load and parse a metadata JSON file.

    Args:
        metadata_path: Path to the metadata JSON file

    Returns:
        Dictionary containing the parsed JSON data
    """
    with open(metadata_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Add source file path for tracking
    data['source_file'] = str(metadata_path.relative_to(metadata_path.parent.parent.parent.parent))
    return data


def load_items_file(items_path: Path) -> pd.DataFrame:
    """Load a CSV items file.

    Args:
        items_path: Path to the items CSV file

    Returns:
        DataFrame containing the CSV data, or None if file doesn't exist/empty
    """
    if not items_path.exists():
        return None
    
    try:
        df = pd.read_csv(items_path)
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"Warning: Failed to load {items_path}: {e}")
        return None


def load_sample_data(
    directory: Path,
    file_type: str,
    sample_size: int
) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """Load sample metadata and items data for a given file type.

    Args:
        directory: Root directory to search for files
        file_type: Type of files ("order" or "billing")
        sample_size: Maximum number of files to process

    Returns:
        Tuple of (metadata_list, items_dataframe)
    """
    # Find metadata files
    metadata_files = find_metadata_files(directory, file_type)
    
    if not metadata_files:
        print(f"No {file_type} metadata files found in {directory}")
        return [], pd.DataFrame()
    
    # Limit to sample size
    metadata_files = metadata_files[:sample_size]
    
    print(f"Loading {len(metadata_files)} {file_type} files for analysis...")
    
    metadata_data = []
    items_dataframes = []
    
    for metadata_file in metadata_files:
        # Load metadata JSON
        try:
            metadata = load_metadata_file(metadata_file)
            metadata_data.append(metadata)
        except Exception as e:
            print(f"Warning: Failed to load {metadata_file}: {e}")
            continue
        
        # Find and load matching items CSV
        items_file = metadata_file.parent / metadata_file.name.replace('_meta.json', '_items.csv')
        
        if items_file.exists():
            df_items = load_items_file(items_file)
            if df_items is not None and not df_items.empty:
                # Ensure we have a link to the parent document if not present
                if f'{file_type}_id' not in df_items.columns:
                    # Extract ID from metadata
                    doc_id = metadata.get('order_id') or metadata.get('billing_document_id')
                    if doc_id:
                        df_items[f'parent_{file_type}_id'] = doc_id
                
                items_dataframes.append(df_items)
    
    # Combine items dataframes
    if items_dataframes:
        df_items_combined = pd.concat(items_dataframes, ignore_index=True)
    else:
        df_items_combined = pd.DataFrame()
    
    return metadata_data, df_items_combined


def normalize_metadata_dataframe(metadata_list: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert metadata list to a normalized DataFrame.

    Args:
        metadata_list: List of metadata dictionaries

    Returns:
        DataFrame with normalized metadata
    """
    if not metadata_list:
        return pd.DataFrame()
    
    # Normalize nested dictionaries by flattening the 'data' field
    normalized_records = []
    for record in metadata_list:
        if not isinstance(record, dict):
            continue
            
        normalized_record = {}
        
        # Keep top-level fields
        for key, value in record.items():
            if key == 'data' and isinstance(value, dict):
                # Flatten nested data dict
                for nested_key, nested_value in value.items():
                    # Handle nested dicts/lists by converting to string
                    if isinstance(nested_value, (dict, list)):
                        normalized_record[f"data_{nested_key}"] = json.dumps(nested_value)
                    else:
                        normalized_record[f"data_{nested_key}"] = nested_value
            else:
                # Handle nested dicts/lists by converting to string
                if isinstance(value, (dict, list)):
                    normalized_record[key] = json.dumps(value)
                else:
                    normalized_record[key] = value
        
        normalized_records.append(normalized_record)
    
    if not normalized_records:
        return pd.DataFrame()
    
    return pd.DataFrame(normalized_records)


def generate_reports(
    directory: Path,
    orders_metadata: List[Dict[str, Any]],
    orders_items: pd.DataFrame,
    billing_metadata: List[Dict[str, Any]],
    billing_items: pd.DataFrame,
    output_dir: Path
) -> None:
    """Generate profiling reports for all data types.

    Args:
        directory: Source data directory
        orders_metadata: List of order metadata dictionaries
        orders_items: DataFrame of order items
        billing_metadata: List of billing document metadata dictionaries
        billing_items: DataFrame of billing document items
        output_dir: Directory to save reports
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Profile Order Metadata
    if orders_metadata:
        print("Generating Orders Metadata Report...")
        df_orders_meta = normalize_metadata_dataframe(orders_metadata)
        if not df_orders_meta.empty:
            profile_orders_meta = ProfileReport(
                df_orders_meta,
                title="Orders Metadata Schema Analysis",
                minimal=False
            )
            report_path = output_dir / "report_orders_metadata.html"
            profile_orders_meta.to_file(str(report_path))
            print(f"  ✓ Saved to {report_path}")
        else:
            print("  ✗ No order metadata to profile")
    
    # 2. Profile Order Items
    if not orders_items.empty:
        print("Generating Order Items Report...")
        profile_orders_items = ProfileReport(
            orders_items,
            title="Order Items Schema Analysis",
            minimal=False
        )
        report_path = output_dir / "report_orders_items.html"
        profile_orders_items.to_file(str(report_path))
        print(f"  ✓ Saved to {report_path}")
    else:
        print("  ✗ No order items to profile")
    
    # 3. Profile Billing Document Metadata
    if billing_metadata:
        print("Generating Billing Documents Metadata Report...")
        df_billing_meta = normalize_metadata_dataframe(billing_metadata)
        if not df_billing_meta.empty:
            profile_billing_meta = ProfileReport(
                df_billing_meta,
                title="Billing Documents Metadata Schema Analysis",
                minimal=False
            )
            report_path = output_dir / "report_billing_metadata.html"
            profile_billing_meta.to_file(str(report_path))
            print(f"  ✓ Saved to {report_path}")
        else:
            print("  ✗ No billing metadata to profile")
    
    # 4. Profile Billing Document Items
    if not billing_items.empty:
        print("Generating Billing Document Items Report...")
        profile_billing_items = ProfileReport(
            billing_items,
            title="Billing Document Items Schema Analysis",
            minimal=False
        )
        report_path = output_dir / "report_billing_items.html"
        profile_billing_items.to_file(str(report_path))
        print(f"  ✓ Saved to {report_path}")
    else:
        print("  ✗ No billing items to profile")
    
    print(f"\nDone! Reports saved to {output_dir}/")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Profile downloaded order and billing document data using ydata_profiling"
    )
    
    parser.add_argument(
        "--data-dir",
        type=str,
        default="./data",
        help="Root directory containing data files (default: ./data)"
    )
    
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Maximum number of files to analyze per type (default: 100)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./reports",
        help="Directory to save HTML reports (default: ./reports)"
    )
    
    parser.add_argument(
        "--orders-only",
        action="store_true",
        help="Only profile orders (skip billing documents)"
    )
    
    parser.add_argument(
        "--billing-only",
        action="store_true",
        help="Only profile billing documents (skip orders)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.orders_only and args.billing_only:
        print("Error: Cannot specify both --orders-only and --billing-only")
        return 1
    
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: Data directory does not exist: {data_dir}")
        return 1
    
    print("=" * 60)
    print("Data Profiling with ydata_profiling")
    print("=" * 60)
    print(f"Data directory: {data_dir}")
    print(f"Sample size: {args.sample_size}")
    print(f"Output directory: {args.output_dir}")
    print()
    
    # Load order data
    orders_metadata = []
    orders_items = pd.DataFrame()
    
    if not args.billing_only:
        print("Processing Orders...")
        orders_metadata, orders_items = load_sample_data(data_dir, "order", args.sample_size)
        print(f"  Loaded {len(orders_metadata)} order metadata files")
        print(f"  Loaded {len(orders_items)} order item rows")
        print()
    
    # Load billing document data
    billing_metadata = []
    billing_items = pd.DataFrame()
    
    if not args.orders_only:
        print("Processing Billing Documents...")
        billing_metadata, billing_items = load_sample_data(data_dir, "billing", args.sample_size)
        print(f"  Loaded {len(billing_metadata)} billing document metadata files")
        print(f"  Loaded {len(billing_items)} billing document item rows")
        print()
    
    # Generate reports
    if orders_metadata or not orders_items.empty or billing_metadata or not billing_items.empty:
        generate_reports(
            data_dir,
            orders_metadata,
            orders_items,
            billing_metadata,
            billing_items,
            Path(args.output_dir)
        )
    else:
        print("No data found to profile.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

