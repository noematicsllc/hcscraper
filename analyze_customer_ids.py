#!/usr/bin/env python3
"""Analyze customer IDs to identify which ones are extra.

This script:
1. Queries the database for distinct customer_ids from orders
2. Compares them to the customer IDs in config
3. Identifies which customer IDs don't map to the 39 stores in STORE_DATA
"""

import sys
import os
from typing import Set, List

import psycopg

from src.utils.config import BANNER_HALLMARK_CUSTOMER_IDS
from create_stores_table import STORE_DATA


def get_customer_ids_from_orders(conn: psycopg.Connection) -> Set[int]:
    """Get all distinct customer_ids from orders table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT customer_id
            FROM orders
            WHERE customer_id IS NOT NULL
            ORDER BY customer_id
        """)
        return {row[0] for row in cur.fetchall()}


def get_customer_ids_from_stores(conn: psycopg.Connection) -> Set[int]:
    """Get all customer_ids from stores table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT customer_id
            FROM stores
            ORDER BY customer_id
        """)
        return {row[0] for row in cur.fetchall()}


def get_store_numbers_from_stores(conn: psycopg.Connection) -> Set[int]:
    """Get all store_numbers from stores table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT store_number
            FROM stores
            ORDER BY store_number
        """)
        return {row[0] for row in cur.fetchall()}


def main():
    """Main entry point."""
    # Get database connection string from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("Error: DATABASE_URL environment variable not set")
        print("Example: postgresql://user:password@localhost:5432/dbname")
        return 1
    
    print("=" * 60)
    print("Customer ID Analysis")
    print("=" * 60)
    print()
    
    # Connect to database
    try:
        conn = psycopg.connect(database_url)
        print("✓ Connected to database")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return 1
    
    try:
        # Get customer IDs from config (as integers for comparison)
        config_customer_ids = {int(cid) for cid in BANNER_HALLMARK_CUSTOMER_IDS}
        print(f"\nConfig has {len(config_customer_ids)} customer IDs")
        
        # Get customer IDs from orders
        order_customer_ids = get_customer_ids_from_orders(conn)
        print(f"Orders table has {len(order_customer_ids)} distinct customer IDs")
        
        # Get customer IDs from stores table (if it exists)
        try:
            store_customer_ids = get_customer_ids_from_stores(conn)
            print(f"Stores table has {len(store_customer_ids)} customer IDs")
        except Exception as e:
            print(f"Stores table doesn't exist or error: {e}")
            store_customer_ids = set()
        
        # Get store numbers from stores table
        try:
            store_numbers = get_store_numbers_from_stores(conn)
            print(f"Stores table has {len(store_numbers)} store numbers")
            expected_store_numbers = {store_num for store_num, _ in STORE_DATA}
            print(f"STORE_DATA has {len(expected_store_numbers)} store numbers")
            
            # Check for missing store numbers
            missing_store_numbers = expected_store_numbers - store_numbers
            if missing_store_numbers:
                print(f"\n⚠ Missing store numbers in stores table: {sorted(missing_store_numbers)}")
            
            extra_store_numbers = store_numbers - expected_store_numbers
            if extra_store_numbers:
                print(f"⚠ Extra store numbers in stores table: {sorted(extra_store_numbers)}")
        except Exception as e:
            print(f"Could not check store numbers: {e}")
            store_numbers = set()
        
        # Compare config to orders
        print("\n" + "=" * 60)
        print("Config vs Orders")
        print("=" * 60)
        
        config_not_in_orders = config_customer_ids - order_customer_ids
        if config_not_in_orders:
            print(f"\n⚠ {len(config_not_in_orders)} customer IDs in config but NOT in orders:")
            for cid in sorted(config_not_in_orders):
                print(f"  - {cid}")
        
        orders_not_in_config = order_customer_ids - config_customer_ids
        if orders_not_in_config:
            print(f"\n⚠ {len(orders_not_in_config)} customer IDs in orders but NOT in config:")
            for cid in sorted(orders_not_in_config):
                print(f"  - {cid}")
        
        if not config_not_in_orders and not orders_not_in_config:
            print("\n✓ All config customer IDs match orders table")
        
        # Compare config to stores table
        if store_customer_ids:
            print("\n" + "=" * 60)
            print("Config vs Stores Table")
            print("=" * 60)
            
            config_not_in_stores = config_customer_ids - store_customer_ids
            if config_not_in_stores:
                print(f"\n⚠ {len(config_not_in_stores)} customer IDs in config but NOT in stores table:")
                for cid in sorted(config_not_in_stores):
                    print(f"  - {cid}")
            
            stores_not_in_config = store_customer_ids - config_customer_ids
            if stores_not_in_config:
                print(f"\n⚠ {len(stores_not_in_config)} customer IDs in stores table but NOT in config:")
                for cid in sorted(stores_not_in_config):
                    print(f"  - {cid}")
            
            if not config_not_in_stores and not stores_not_in_config:
                print("\n✓ All config customer IDs match stores table")
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Config customer IDs: {len(config_customer_ids)}")
        print(f"Expected stores (STORE_DATA): {len(STORE_DATA)}")
        print(f"Difference: {len(config_customer_ids) - len(STORE_DATA)} extra customer IDs")
        
        if config_not_in_orders:
            print(f"\n🔍 Likely extra customer IDs (not in orders): {sorted(config_not_in_orders)}")
        
        if store_customer_ids and config_not_in_stores:
            print(f"\n🔍 Customer IDs in config but not in stores table: {sorted(config_not_in_stores)}")
        
    finally:
        conn.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

