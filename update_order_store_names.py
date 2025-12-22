#!/usr/bin/env python3
"""One-time script to update existing orders to use canonical store names from stores table."""

import sys
import os

import psycopg


def main():
    """Main entry point."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("Error: DATABASE_URL environment variable not set")
        return 1
    
    print("=" * 60)
    print("Update Order Store Names")
    print("=" * 60)
    print()
    
    try:
        conn = psycopg.connect(database_url)
        print("✓ Connected to database")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return 1
    
    try:
        with conn.cursor() as cur:
            # Update orders to use canonical store names from stores table
            cur.execute("""
                UPDATE orders o
                SET store_name = s.store_name
                FROM stores s
                WHERE o.customer_id = s.customer_id
                AND o.store_name != s.store_name
            """)
            
            updated_count = cur.rowcount
            conn.commit()
            
            print(f"✓ Updated {updated_count} orders with canonical store names")
            
            # Show summary
            cur.execute("""
                SELECT COUNT(*) as total_orders,
                       COUNT(DISTINCT store_name) as unique_store_names
                FROM orders
            """)
            total, unique = cur.fetchone()
            print(f"\nTotal orders: {total}")
            print(f"Unique store names: {unique}")
            
    finally:
        conn.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

