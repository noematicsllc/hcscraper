#!/usr/bin/env python3
"""Analyze billing document CSV search results structure.

This script reads a billing document CSV file and displays its structure,
comparing it with the order CSV structure to understand differences.
"""

import csv
import sys
from pathlib import Path


def analyze_csv(csv_path: Path):
    """Analyze a CSV file and display its structure.
    
    Args:
        csv_path: Path to the CSV file to analyze
    """
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        return
    
    print("=" * 60)
    print(f"Analyzing: {csv_path.name}")
    print("=" * 60)
    print()
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # Display column names
        print("Column Names:")
        print("-" * 60)
        for i, column in enumerate(reader.fieldnames, 1):
            print(f"  {i:2d}. {column}")
        print()
        
        # Display first few rows
        print("Sample Data (first 3 rows):")
        print("-" * 60)
        
        rows = []
        for i, row in enumerate(reader):
            if i >= 3:
                break
            rows.append(row)
        
        if rows:
            # Print header
            print("Row | " + " | ".join(reader.fieldnames[:5]))  # First 5 columns
            if len(reader.fieldnames) > 5:
                print("     | ... (showing first 5 columns)")
            print("-" * 60)
            
            # Print rows
            for i, row in enumerate(rows, 1):
                values = [str(row.get(col, ''))[:20] for col in reader.fieldnames[:5]]
                print(f"  {i}  | " + " | ".join(values))
                if len(reader.fieldnames) > 5:
                    print("     | ...")
        
        print()
        print(f"Total columns: {len(reader.fieldnames)}")
        print(f"Sample rows shown: {len(rows)}")


def compare_with_orders(billing_csv: Path, orders_csv: Path):
    """Compare billing document CSV structure with orders CSV.
    
    Args:
        billing_csv: Path to billing document CSV
        orders_csv: Path to orders CSV for comparison
    """
    if not billing_csv.exists():
        print(f"Error: Billing CSV not found: {billing_csv}")
        return
    
    if not orders_csv.exists():
        print(f"Warning: Orders CSV not found: {orders_csv}")
        print("Skipping comparison.")
        return
    
    print()
    print("=" * 60)
    print("Comparison with Order CSV Structure")
    print("=" * 60)
    print()
    
    # Read both CSVs
    with open(billing_csv, 'r', encoding='utf-8') as f:
        billing_reader = csv.DictReader(f)
        billing_columns = set(billing_reader.fieldnames)
    
    with open(orders_csv, 'r', encoding='utf-8') as f:
        orders_reader = csv.DictReader(f)
        orders_columns = set(orders_reader.fieldnames)
    
    # Find differences
    only_in_billing = billing_columns - orders_columns
    only_in_orders = orders_columns - billing_columns
    common = billing_columns & orders_columns
    
    print("Columns only in Billing Documents CSV:")
    if only_in_billing:
        for col in sorted(only_in_billing):
            print(f"  - {col}")
    else:
        print("  (none)")
    print()
    
    print("Columns only in Orders CSV:")
    if only_in_orders:
        for col in sorted(only_in_orders):
            print(f"  - {col}")
    else:
        print("  (none)")
    print()
    
    print("Common columns:")
    if common:
        for col in sorted(common):
            print(f"  - {col}")
    else:
        print("  (none)")
    print()
    
    # Identify ID column candidates
    print("Potential ID column candidates (billing documents):")
    id_candidates = [
        col for col in billing_columns
        if any(keyword in col.lower() for keyword in ['billing', 'invoice', 'document', 'id', '#'])
    ]
    for col in id_candidates:
        print(f"  - {col}")
    if not id_candidates:
        print("  (none found - check column names manually)")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analyze billing document CSV search results structure"
    )
    parser.add_argument(
        "csv_file",
        type=str,
        nargs="?",
        help="Path to billing document CSV file (default: search for *.csv in search_results/)"
    )
    parser.add_argument(
        "--compare-orders",
        type=str,
        default="search_results/orders_20251220173722.csv",
        help="Path to orders CSV for comparison (default: search_results/orders_20251220173722.csv)"
    )
    args = parser.parse_args()
    
    # Find CSV file
    if args.csv_file:
        billing_csv = Path(args.csv_file)
    else:
        # Look for CSV files in search_results directory
        search_results_dir = Path("search_results")
        if not search_results_dir.exists():
            print("Error: search_results directory not found")
            print("Please provide the CSV file path as an argument")
            return 1
        
        csv_files = list(search_results_dir.glob("*.csv"))
        if not csv_files:
            print("Error: No CSV files found in search_results/")
            print("Please provide the CSV file path as an argument")
            return 1
        
        if len(csv_files) == 1:
            billing_csv = csv_files[0]
            print(f"Found CSV file: {billing_csv}")
        else:
            print("Multiple CSV files found. Please specify which one to analyze:")
            for i, csv_file in enumerate(csv_files, 1):
                print(f"  {i}. {csv_file.name}")
            return 1
    
    # Analyze billing CSV
    analyze_csv(billing_csv)
    
    # Compare with orders if requested
    orders_csv = Path(args.compare_orders)
    if orders_csv.exists():
        compare_with_orders(billing_csv, orders_csv)
    else:
        print(f"\nNote: Orders CSV not found at {orders_csv}")
        print("Skipping comparison. Use --compare-orders to specify a different path.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

